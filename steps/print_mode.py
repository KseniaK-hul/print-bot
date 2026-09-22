# ==========================================================================
# Шаг 4 — какие страницы печатать: все или выбранные (LOGIC.md §2.4.1).
# ==========================================================================

from core.ctx import Ctx
from core.models import PageSelection
from core.step import CALLBACK, Answer, Next, Outcome, Step


class PrintModeStep(Step):
    id = "print_mode"
    accepts = (CALLBACK,)
    buttons = ("print_",)

    async def ask(self, ctx: Ctx) -> None:
        f = ctx.order.current_file
        await ctx.say(
            "file_accepted",
            ctx.kb(("print_all", "print_all"), ("print_specific", "print_specific")),
            name=f.name,
            total=f.total_pages,
        )

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        if answer.data == "print_all":
            ctx.order.current_file.pages = PageSelection.all_pages()
            return Next("all")
        return Next("specific")


STEP = PrintModeStep()
