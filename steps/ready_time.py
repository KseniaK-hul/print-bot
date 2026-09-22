# ==========================================================================
# Шаг 17 — срок готовности (LOGIC.md §2.8).
#
# В order.ready_time кладём КЛЮЧ ('time_1h'), а не готовую строку — иначе
# админу и в сводке уходит «Day» вместо «📅 День».
# ==========================================================================

from config import EXPRESS_MARKUP_PERCENT
from core.ctx import Ctx
from core.step import CALLBACK, Answer, Next, Outcome, Step

TIME_OPTIONS = ("time_express", "time_1h", "time_3h", "time_day")


class ReadyTimeStep(Step):
    id = "ready_time"
    accepts = (CALLBACK,)
    buttons = ("rt_",)

    async def ask(self, ctx: Ctx) -> None:
        rows = [(key, f"rt_{key}") for key in TIME_OPTIONS]
        # Наценку называем до выбора, а не в итоговой сумме: иначе человек
        # узнаёт о ней, когда уже согласился.
        await ctx.say("time_choice", ctx.kb(*rows), markup=EXPRESS_MARKUP_PERCENT)

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        choice = answer.suffix if answer.suffix in TIME_OPTIONS else "time_day"
        ctx.order.ready_time = choice
        ctx.order.is_express = choice == "time_express"
        return Next()


STEP = ReadyTimeStep()
