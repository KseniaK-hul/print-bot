# ==========================================================================
# Шаг 9 — одно- или двусторонняя печать (только для A4, LOGIC.md §2.4.4).
# ==========================================================================

from core.ctx import Ctx
from core.step import CALLBACK, Answer, Next, Outcome, Step


class SidedStep(Step):
    id = "sided"
    accepts = (CALLBACK,)
    buttons = ("sided_",)

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say(
            "sided_choice",
            ctx.kb(("one_side", "sided_s"), ("two_side", "sided_d")),
        )

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        ctx.order.current_file.sided = "d" if answer.data == "sided_d" else "s"
        return Next()


STEP = SidedStep()
