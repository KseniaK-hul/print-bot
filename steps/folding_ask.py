# ==========================================================================
# Шаг 14 — нужно ли складывать чертежи (LOGIC.md §2.6).
#
# Шаг вообще не открывается, если складывать нечего: чертежи внутри брошюр
# складываются автоматически, а для заказа из одних A4 вопрос бессмысленен.
# Проверка живёт в core/flow.py (after_brochures) — здесь её дублировать не
# нужно.
# ==========================================================================

from core.ctx import Ctx
from core.step import CALLBACK, Answer, Next, Outcome, Step


class FoldingAskStep(Step):
    id = "folding_ask"
    accepts = (CALLBACK,)
    buttons = ("fold_yes", "fold_no")

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say("fold_choice", ctx.kb(("yes", "fold_yes"), ("no", "fold_no")))

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        return Next("yes" if answer.data == "fold_yes" else "no")


STEP = FoldingAskStep()
