import sys

import rich

from . import Interview as I
from . import Question__ as Q__

if __name__ == "__main__":  # interactive showcase

	def ___str_to_py_version(s: str) -> tuple[int, int] | tuple[int, int, int]:
		return tuple(int(x) for x in s.split(".", maxsplit=2))

	rich.get_console().print(
		I(
			name=(
				Q__
				.Str("What is your name", default="default")
				.with_valid_if_not_empty_answer()
				.with_valid_if(
					lambda iv, q, a: a.__len__() % 2 == 1,
					msg="[red]answer len must NOT be divisible by 2",
				)
				# .map(lambda s: s)
			),
			favorite_numbers=(
				I(
					label=Q__.Label("Enter your favorite numbers, [u]Ctrl+D to finish[/u]"),
					tup=Q__.Tuple(
						lambda items_so_far: Q__.Int(Q__.Tuple.default_item_text(items_so_far)),
						min_items=1,
						ensure_unique=True,
					),
				)
				.set_indent("| ")
				.flatten_to("tup")
			),
			lvl=Q__.Int("What is your lvl", default=18),
			money=Q__.Float("Enter a fair amount").with_valid_if_positive(),
			default_for_next_question=Q__.YesNo("Choose next question's default", default=True),
			start_subinterview=Q__.Dynamic(
				lambda iv: Q__.YesNo("Start a subinterview?", default=iv["default_for_next_question"]),
			),
			subinterview=(
				I(
					label=Q__.Label("== Label =="),
					name=Q__.Str("Product [white]name[/white]"),
					amt=Q__.Int("Product [white]amount[/white]"),
				)
				.set_default_style("i")
				.with_keep_if_previous_answer("start_subinterview")
				.set_indent("[not i]| ")
			),
		)
		.set_default_style("yellow b")
		.with_rich_console(rich.console.Console(highlight=False))
		.ask()
	)
