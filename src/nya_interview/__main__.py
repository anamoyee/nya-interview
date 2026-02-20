import rich

from . import Interview as I
from . import Question__ as Q__

if __name__ == "__main__":  # interactive tests
	results = (
		I(
			name1=Q__.Label("1").with_keep_if(lambda iv, q: 1 == 2),
			name2=Q__.Label("2"),
			name3=Q__.Label("3"),
			string=(
				Q__
				.Str("What is your name", default="bruh")
				.with_valid_if_not_empty_answer()
				.with_valid_if(
					lambda iv, q, a: a.lower() not in ["gay", "meow"],
					msg="[red]You must NOT respond with 'gay' or 'meow'!!!!!!",
				)
				.with_valid_if(
					lambda iv, q, a: a.__len__() % 2 == 0,
					msg="[red]answer len must be divisible by 2",
				)
			),
			favorite_numbers=(
				I(
					label=Q__.Label("Enter your favorite numbers, [u]Ctrl+D to finish[/u]"),
					tup=Q__.Tuple(
						lambda ans_tup: Q__.Int(f"Item #{len(ans_tup) + 1}"),
						end_condition=lambda _: False,  # never end, except for ^D, accept 0 as a valid input
					),
				)
				.set_indent("| ")
				.flatten_to("tup")
			),
			lvl=Q__.Int("What is your lvl"),
			money=Q__.Float("Enter a fair amount").with_valid_if_positive(),
			default_for_next_question=Q__.YesNo("[black on white]Choose next question's default", default=True),
			start_subinterview=Q__.Dynamic(
				lambda iv: Q__.YesNo("Start a subinterview?", default=iv.answers["default_for_next_question"]),
			),
			subinterview=(
				I(
					label=Q__.Label("Label"),
					name=Q__.Str("Your name"),
					lvl=Q__.Int("Your lvl"),
				)
				.with_keep_if_previous_answer("start_subinterview")
				.set_indent("| ")
			),
		)
		.with_valid_if(lambda iv, q, a: False)
		.with_rich_console(rich.console.Console(highlight=False))
		.ask()
	)

	rich.get_console().print(results)
