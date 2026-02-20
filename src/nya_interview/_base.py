import abc
import functools
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from numbers import Real
from operator import itemgetter
from typing import Any, Self

import rich
import rich.markup
import rich.prompt
from nya_scope import Scope
from rich.markup import escape as esc
from rich.text import Text

MISSING_IN_DICT = object()


type Textish = rich.text.TextType


def render_textish_to_text(textish: Textish) -> rich.text.Text:
	if isinstance(textish, str):
		textish = rich.markup.render(textish)

	return textish


class BaseTransformation[T]:
	type TransformFn[R] = Callable[[Interview, QuestionABC], R]
	type ValidateFn[A] = Callable[[Interview, QuestionABC[A], A], bool]

	def transform(self, iv: "Interview", q: "QuestionABC[T]", /) -> "QuestionABC[T]":
		return q

	def validate(self, iv: "Interview", q: "QuestionABC[T]", a: T) -> bool:
		return True

	def validate__invalid_message(self, iv: "Interview", q: "QuestionABC[T]", a: T) -> rich.text.Text | None:
		return rich.markup.render("[red]Invalid value, try again[/]")


class Transformation__(Scope):
	class KeepIf[T](BaseTransformation[T]):
		def __init__(self, predicate: BaseTransformation.TransformFn[bool]) -> None:
			self.predicate = predicate

		def transform(self, iv: "Interview", q: "QuestionABC[T]") -> "QuestionABC[T]":
			if not self.predicate(iv, q):
				q.is_skipped = True

			return super().transform(iv, q)

	class ValidIf[T](BaseTransformation[T]):
		def __init__(
			self,
			predicate: BaseTransformation.ValidateFn[T],
			*,
			msg: rich.text.Text | str | None = "[red]Invalid value, try again[/]",
		) -> None:
			msg = render_textish_to_text(msg) if msg is not None else msg

			self.predicate = predicate
			self.msg = msg

		def validate(self, iv: "Interview", q: "QuestionABC[T]", a: T) -> bool:
			return self.predicate(iv, q, a)

		def validate__invalid_message(self, iv: "Interview", q: "QuestionABC[T]", a: T) -> rich.prompt.Text | None:
			return self.msg


@dataclass
class QuestionABC[T](abc.ABC):
	transformations: list[BaseTransformation] = field(init=False, default_factory=list)
	is_skipped: bool = field(init=False, default=False)

	def skip(self) -> Self:
		"""Same as `self.is_skipped = True`, but with chaining support."""
		self.is_skipped = True
		return self

	@abc.abstractmethod
	def _ask(self, iv: "Interview", /) -> T: ...

	def _ask_with_validation(self, iv: "Interview", /) -> T:
		try:
			answer = self._ask(iv)
		except (KeyboardInterrupt, EOFError) as e:
			raise iv.UserExitException(e) from e

		# code duplication, but i dont really want to make it more complex by adding a function
		# PLEASE, why  is there no do-while loop in python :sob:

		def key(trans: BaseTransformation[T]):
			result = trans.validate(iv, self, answer)

			if not result:
				text = trans.validate__invalid_message(iv, self, answer)

				if text is not None:
					iv.print_label(text)

			return result  # short-circuit the all()

		while not all(key(trans) for trans in self.transformations):  # 🏳️‍⚧️
			try:
				answer = self._ask(iv)
			except (KeyboardInterrupt, EOFError) as e:
				raise iv.UserExitException(e) from e

		return answer

	def invoke_subquestion[SubT](self, subq: "QuestionABC[SubT]", iv: "Interview", *, propagate_skip: bool = True) -> SubT:
		ans = subq._ask_with_validation(iv)

		if propagate_skip and subq.is_skipped:
			self.is_skipped = True

		return ans

	def with_transformation(self, transformation: BaseTransformation) -> Self:
		self.transformations.append(transformation)

		return self

	def with_keep_if(self, predicate: BaseTransformation.TransformFn[bool]) -> Self:
		return self.with_transformation(Transformation__.KeepIf[T](predicate))

	def with_keep_if_previous_answer(self, of_question_named: str, predicate: Callable[[Any], bool] = bool) -> Self:
		def keep_if(iv: Interview, _: QuestionABC[T], *, name=of_question_named, predicate=predicate) -> bool:
			return predicate(iv.answers.get(name))

		return self.with_keep_if(keep_if)

	def with_valid_if(
		self,
		predicate: BaseTransformation.ValidateFn[T],
		*,
		msg: rich.text.Text | str | None = "[red]Invalid value, try again[/]",
	) -> Self:
		msg = render_textish_to_text(msg) if msg is not None else msg

		return self.with_transformation(Transformation__.ValidIf[T](predicate, msg=msg))


class Interview(QuestionABC[dict[str, Any]]):
	class UserExitException(SystemExit):
		"""Raised when the user wishes to exit the interview, at any point of it, either by pressing Ctrl+C (`KeyboardInterrupt`) or Ctrl+D (`EOFError`). The specific error can be viewed through `.__cause__` but it's not recommended to build any functionality around the difference between the two."""

		def __init__(
			self,
			/,
			e: KeyboardInterrupt | EOFError,
			print_newline: bool = True,
			print_ctrl_d: bool = True,
			print_ctrl_c: bool = os.name == "nt",
		):
			self.e = e

			extra_text = ""

			if print_ctrl_d and self.originates_from_ctrl_d():
				extra_text += "^D"
			if print_ctrl_c and self.originates_from_ctrl_c():
				extra_text += "^C"

			if print_newline:
				extra_text += "\n"

			print(extra_text, end="")

			super().__init__(2)

		def originates_from_ctrl_d(self) -> bool:
			return isinstance(self.e, EOFError)

		def originates_from_ctrl_c(self) -> bool:
			return isinstance(self.e, KeyboardInterrupt)

	class KeyOccupiedError(ValueError):
		"""Raised when adding a question at a key that is already occupied."""

		def __init__(self, /, *, keys: set[str], interview: "Interview") -> None:
			self.keys = keys
			self.interview = interview

			super().__init__(f"Cannot add questions with the following keys to {interview!r}, because they are already occupied by previously added questions: {keys!r}")

	def __repr__(self) -> str:
		return f"""
{self.__class__.__name__}(
	questions.keys()={list(self.questions)!r},
	answers={self.answers!r},
)"""[1:-1]

	def __init__(self, /, **questions: QuestionABC[Any]):
		super().__init__()

		self.questions: dict[str, QuestionABC[Any]] = {}
		self._answers: dict[str, Any] | None = None
		self.parent_interview: Self | None = None
		self._rich_console: rich.console.Console | None = None
		self._indent = ""

		self.add_questions(**questions)

	def set_indent(self, indent: Textish) -> Self:
		self._indent = indent
		return self

	@property
	def total_indent_text(self) -> rich.text.Text:
		return functools.reduce(rich.text.Text.append, (render_textish_to_text(iv._indent).copy() for iv in self.parent_interviews))

	def prepend_total_indent_to_text(self, content_text: rich.text.Text) -> rich.text.Text:
		return self.total_indent_text.append(content_text)

	@property
	def parent_interviews(self) -> tuple["Interview", ...]:
		ivs = []

		current: Interview | None = self

		while current is not None:
			ivs.append(current)
			current = current.parent_interview

		return tuple(ivs)

	@property
	def root_interview(self) -> Self:
		"""Iteratively find the root-most `.parent_interview`."""

		deepest_iv = self

		while deepest_iv.parent_interview is not None:
			deepest_iv = deepest_iv.parent_interview

		return deepest_iv

	@property
	def answers(self):
		if self._answers is None:
			raise RuntimeError("You cannot access this helper when this Interview isn't in progress!")

		return self._answers

	def with_rich_console(self, rich_console: rich.console.Console | None) -> Self:
		"""Provide a custom console used in this `Interview` and any child `Interview`s."""
		self._rich_console = rich_console

		return self

	@property
	def rich_console(self) -> rich.console.Console:
		"""Get the `rich.console.Console` object from the closest `Interview` in the tree, if not found on any, return a new Console()."""

		deepest_iv = self

		while deepest_iv.parent_interview is not None:
			if deepest_iv._rich_console is not None:
				return deepest_iv._rich_console

			deepest_iv = deepest_iv.parent_interview

		if deepest_iv._rich_console is not None:
			return deepest_iv._rich_console

		return rich.get_console()

	def add_questions(self, /, **questions: QuestionABC[Any]) -> Self:
		"""Add a question (or multiple at a time) to this Interview, if any keys would be overwritten, raise a Interview.KeyOccupiedError. This operation is atomic."""
		occupied_keys = {k for k in questions if k in self.questions}

		if occupied_keys:
			raise Interview.KeyOccupiedError(keys=occupied_keys, interview=self)

		self.questions.update(questions)

		return self

	def flatten_to[T](self, name: str) -> "Question__.PostConvert[T, Any]":
		return Question__.PostConvert(self, itemgetter(name))

	def print_label(self, msg: rich.text.Text) -> None:
		if msg is not None:
			msg = self.prepend_total_indent_to_text(msg)

		if msg is not None:
			self.rich_console.print(msg)

	def _ask(self, parent_interview: Self | None) -> dict[str, Any]:
		self.parent_interview = parent_interview
		self._answers = {}

		for name, question in self.questions.items():
			for transformation in question.transformations.copy():
				question = transformation.transform(self, question)

			if question.is_skipped:
				continue

			answer = question._ask_with_validation(self)

			if question.is_skipped:
				# this check is already present higher in this loop, however this one checks if during the process of asking this flag was set, in which case simply dont include the given result.
				continue

			self._answers[name] = answer

		try:
			return self._answers
		finally:
			self._answers = None
			self.parent_interview = None

	def ask(self) -> dict[str, Any]:
		return self._ask(None)


class QABCs__(Scope):
	@dataclass(init=False)
	class WithText[T](QuestionABC[T]):
		_textish: Textish
		_text: rich.text.Text | None = field(init=False, default=None)

		@property
		def text(self):
			if self._text is None:
				self._text = render_textish_to_text(self._textish)

			return self._text

		@text.setter
		def text(self, text: rich.text.Text):
			self._text = text

	@dataclass
	class WithDefault[T](QuestionABC[T]):
		default: T | None = field(kw_only=True, default=None)
		show_default: bool = field(kw_only=True, default=True)
		render_default: Callable[[Self], rich.text.Text] = field(default=lambda self: rich.text.Text(f" [{self.default}]"))

	@dataclass
	class WithChoices[T](QuestionABC[T]):
		choices: Iterable[T] = field(default=())
		show_choices: bool = field(kw_only=True, default=True)
		render_choices: Callable[[Self], rich.text.Text] = field(default=lambda self: rich.text.Text(f" ({', '.join(str(x) for x in self.choices)})"))

	@dataclass
	class WithInvalidMsg[T](QuestionABC[T]):
		invalid_msg: Textish = field(kw_only=True, default="[red]Provide a valid value")
		_invalid_msg_text: rich.text.Text | None = field(init=False, default=None)

		@property
		def invalid_msg_text(self):
			if self._invalid_msg_text is None:
				self._invalid_msg_text = render_textish_to_text(self.invalid_msg)

			return self._invalid_msg_text

	@dataclass
	class WithNumberOrdering[T: Real](QuestionABC[T]):
		def with_valid_if_positive(self) -> Self:
			return self.with_valid_if(lambda iv, q, a: a > a.__class__(), msg="[red]Value must be positive[/]")  # use .__class__() to summon the identity

		def with_valid_if_negative(self) -> Self:
			return self.with_valid_if(lambda iv, q, a: a < a.__class__(), msg="[red]Value must be negative[/]")

		def with_valid_if_non_positive(self) -> Self:
			return self.with_valid_if(lambda iv, q, a: a <= a.__class__(), msg="[red]Value must be non-positive[/]")

		def with_valid_if_non_negative(self) -> Self:
			return self.with_valid_if(lambda iv, q, a: a >= a.__class__(), msg="[red]Value must be non-negative[/]")

		def with_valid_if_not_zero(self) -> Self:
			return self.with_valid_if(lambda iv, q, a: a != a.__class__(), msg="[red]Value must not be zero[/]")


class Question__(Scope):
	@dataclass
	class Label(QABCs__.WithText[None]):
		def _ask(self, iv: Interview) -> None:
			iv.print_label(self.text)
			self.is_skipped = True  # do not include in the results dict

	@dataclass
	class Str(QABCs__.WithDefault[str], QABCs__.WithChoices[str], QABCs__.WithText[str]):
		def __post_init__(self):
			if self.choices and self.show_choices:
				self.text.append(self.render_choices(self))

			if self.show_default and self.default is not None:
				self.text.append(self.render_default(self))

		def _ask(self, iv: Interview) -> str:
			result = rich.prompt.Prompt.ask(iv.prepend_total_indent_to_text(self.text), console=iv.rich_console)

			if self.default is not None:
				result = result or self.default

			return result

		def with_valid_if_not_empty_answer(self, *, msg: rich.text.Text | str | None = "[red]Provide a non-empty answer[/]") -> Self:
			self.with_valid_if(lambda iv, q, a: bool(a), msg=msg)
			return self

	@dataclass
	class Int(QABCs__.WithText[int], QABCs__.WithInvalidMsg[int], QABCs__.WithNumberOrdering[int]):  # type: ignore # <-- fuck you mypy, int is registered in Real ABC
		invalid_msg: Textish = field(kw_only=True, default="[red]Provide a valid integer")

		def __post_init__(self) -> None:
			self.str_question = Question__.Str(self.text).with_valid_if(
				lambda iv, q, a: self._str_is_int_parsable(a),
				msg=self.invalid_msg_text,
			)

		@staticmethod
		def _str_is_int_parsable(s: str) -> bool:
			try:
				int(s)
			except ValueError:
				return False

			return True

		def _ask(self, iv: Interview) -> int:
			ans = self.invoke_subquestion(self.str_question, iv)

			return int(ans)

	@dataclass
	class Float(QABCs__.WithText[float], QABCs__.WithInvalidMsg[float], QABCs__.WithNumberOrdering[float]):  # type: ignore # <-- same explaination as Int's
		invalid_msg: Textish = field(kw_only=True, default="[red]Provide a valid float")

		def __post_init__(self) -> None:
			self.str_question = Question__.Str(self.text).with_valid_if(
				lambda iv, q, a: self._str_is_float_parsable(a),
				msg=self.invalid_msg_text,
			)

		@staticmethod
		def _str_is_float_parsable(s: str) -> bool:
			try:
				float(s)
			except ValueError:
				return False

			return True

		def _ask(self, iv: Interview) -> float:
			ans = self.invoke_subquestion(self.str_question, iv)

			return float(ans)

	@dataclass
	class YesNo(QABCs__.WithText[bool]):
		default: bool | None = field(kw_only=True, default=None)
		show_choices: bool = field(kw_only=True, default=True)

		def __post_init__(self) -> None:
			self.default_str = {True: "yes", False: "no", None: None}[self.default]

			if self.show_choices:
				parens = ("(", ")") if self.default is None else ("[", "]")

				self.text.append(rich.markup.render(f"[default] {esc(parens[0])}[green b]{'Y' if self.default is True else 'y'}[/]/[red b]{'N' if self.default is False else 'n'}[/]{esc(parens[1])}"))

			self.str_question = Question__.Str(self.text)

			if self.default is None:
				self.str_question.with_valid_if_not_empty_answer()

		def _ask(self, iv: Interview) -> bool:
			ans = self.invoke_subquestion(self.str_question, iv) or self.default_str

			if ans is None:
				raise RuntimeError("Should be unreachable: self.default is only None, if self.str_question enforces truthy string.")  # unreachable

			return ans.lower() in ("y", "yes")

	class Dynamic[T](QuestionABC[T]):
		"""A thin wrapper around `QuestionABC[T]`, lets you create the question at the time it's asked, not immediately. A new instance (copy) of the question will always be created if this question is asked multiple times.

		```python
		result = Interview(
			q1=Question__.YesNo("Choose next question's default", default=True),
			q2=Question__.Dynamic(
				lambda iv: Question__.YesNo("Start a subinterview?", default=iv.answers["q1"]),
			),
		).ask()
		```

		under the hood it literally does this:
		```python
		def ask(self, iv: Interview) -> T:
			return self.invoke_subquestion(self.make_question(iv), iv)
		```
		"""

		def __init__(self, make_question: Callable[[Interview], QuestionABC[T]]) -> None:
			super().__init__()
			self.make_question = make_question

		def _ask(self, iv: Interview) -> T:
			return self.invoke_subquestion(self.make_question(iv), iv)

	@dataclass
	class PostConvert[To, From](QuestionABC[To]):
		"""A thin wrapper around an inner sub-`QuestionABC[From]` that lets you apply a converter function after the inner question has been."""

		inner_question: QuestionABC[From]
		post_converter: Callable[[From], To]

		def _ask(self, iv: Interview) -> To:
			return self.post_converter(self.invoke_subquestion(self.inner_question, iv))

	@dataclass
	class Tuple[T](QuestionABC[tuple[T, ...]]):
		make_item_question: Callable[[tuple[T, ...]], QuestionABC[T]]
		end_condition: Callable[[T], bool] = field(
			kw_only=True,
			# default=lambda x: not x,
			default=lambda _: False,  # only make use of the ^D exit.
		)
		end_on_ctrl_d: bool = field(kw_only=True, default=True)
		end_on_ctrl_c: bool = field(kw_only=True, default=False)
		ensure_unique: bool = field(kw_only=True, default=False)
		min_items: int = field(kw_only=True, default=0)
		max_items: int = field(kw_only=True, default=2**31 - 1)

		def get_error_text__too_few_items(self) -> Text:
			return rich.markup.render(f"[red]You must input at least {self.min_items} item(s)")

		def get_error_text__not_unique(self) -> Text:
			return rich.markup.render(f"[red]You already provided this item, unique values are requested.")

		def _ask(self, iv: Interview) -> tuple[T, ...]:
			lst: list[T] = []

			while True:
				try:
					if len(lst) >= self.max_items:
						break

					if self.end_condition(item := self.invoke_subquestion(self.make_item_question(tuple(lst)), iv)):
						if len(lst) < self.min_items:
							iv.print_label(self.get_error_text__too_few_items())
							continue

						break

					if self.ensure_unique and item in lst:
						iv.print_label(self.get_error_text__not_unique())
						continue

					lst.append(item)
				except Interview.UserExitException as e:
					if (
						   (self.end_on_ctrl_d and e.originates_from_ctrl_d())
						or (self.end_on_ctrl_c and e.originates_from_ctrl_c())
					):  # fmt: skip
						if len(lst) < self.min_items:
							iv.print_label(self.get_error_text__too_few_items())
							continue

						break

					raise

			return tuple(lst)

		@staticmethod
		def default_item_text(answers_to_far: tuple[Any, ...]):
			return f"[b]\\[{len(answers_to_far)}]"
