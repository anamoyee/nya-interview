import rich

from . import Interview as I
from . import Question__ as Q__

if __name__ == "__main__":  # interactive showcase
	rich.get_console().print(
		I(
			name=(
				Q__
				.Str("[b]What is your name", default="default__value")
				.with_valid_if_not_empty_answer()
				.with_valid_if(
					lambda iv, q, a: a.__len__() % 2 == 0,
					msg="[red]answer len must be divisible by 2",
				)
			),
			favorite_numbers=(
				I(
					label=Q__.Label("[b]Enter your favorite numbers, [u]Ctrl+D to finish[/u]"),
					tup=Q__.Tuple(
						lambda items_so_far: Q__.Int(Q__.Tuple.default_item_text(items_so_far)),
						min_items=1,
						ensure_unique=True,
					),
				)
				.set_indent("[b]| ")
				.flatten_to("tup")
			),
			lvl=Q__.Int("[b]What is your lvl"),
			money=Q__.Float("[b]Enter a fair amount").with_valid_if_positive(),
			default_for_next_question=Q__.YesNo("[b]Choose next question's default", default=True),
			start_subinterview=Q__.Dynamic(
				lambda iv: Q__.YesNo("[b]Start a subinterview?", default=iv.answers["default_for_next_question"]),
			),
			subinterview=(
				I(
					label=Q__.Label("[i]== Label =="),
					name=Q__.Str("[i]Product name"),
					amt=Q__.Int("[i]Product amount"),
				)
				.with_keep_if_previous_answer("start_subinterview")
				.set_indent("[b]| ")
			),
		)
		.with_rich_console(rich.console.Console(highlight=False))
		.ask()
	)
