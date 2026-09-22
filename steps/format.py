# ==========================================================================
# Шаг 8 — формат листа (LOGIC.md §2.4.3).
# ==========================================================================

from config import FORMATS
from core.ctx import Ctx
from core.step import CALLBACK, Answer, Next, Outcome, Step


class FormatStep(Step):
    id = "format"
    accepts = (CALLBACK,)
    buttons = ("fmt_",)

    async def ask(self, ctx: Ctx) -> None:
        # Подписи A4/A3/... не переводятся — это обозначения форматов.
        rows = [(fmt, f"fmt_{fmt}") for fmt in FORMATS]
        await ctx.say("format_choice", ctx.raw_kb(*rows))

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        fmt = answer.suffix
        if fmt not in FORMATS:
            return Next(None)

        f = ctx.order.current_file
        f.format = fmt
        if fmt != "A4":
            # Двусторонняя печать бывает только на A4 — остальным ставим
            # одностороннюю молча, не тратя вопрос.
            f.sided = "s"
        return Next(fmt)


STEP = FormatStep()
