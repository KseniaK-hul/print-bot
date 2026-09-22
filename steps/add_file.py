# ==========================================================================
# Шаг 10 — цена файла и вопрос «добавить ещё?» (LOGIC.md §2.4.5-2.5).
# ==========================================================================

from core.ctx import Ctx
from core.step import CALLBACK, Answer, Next, Outcome, Step
from pricing.calculator import file_price


class AddFileStep(Step):
    id = "add_file"
    accepts = (CALLBACK,)
    buttons = ("add_",)

    async def ask(self, ctx: Ctx) -> None:
        price = file_price(ctx.order.current_file)
        await ctx.say(
            "total_price",
            ctx.kb(("yes", "add_yes"), ("no", "add_no")),
            price=price,
        )

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        return Next("more" if answer.data == "add_yes" else "done")


STEP = AddFileStep()
