# ==========================================================================
# Шаг 5 — ввод конкретных страниц: "1,3,5-7" (LOGIC.md §2.4.1).
# ==========================================================================

from core.ctx import Ctx
from core.models import PageSelection
from core.step import TEXT, Again, Answer, Next, Outcome, Step


class InputPagesStep(Step):
    id = "input_pages"
    accepts = (TEXT,)

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say("choose_pages", total=ctx.order.current_file.total_pages)

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        f = ctx.order.current_file
        try:
            f.pages = PageSelection.parse(answer.text or "", f.total_pages)
        except (ValueError, AttributeError):
            # Текст ошибки сам содержит инструкцию и число страниц,
            # поэтому переспрашивать отдельным сообщением не нужно.
            return Again("choose_pages", {"total": f.total_pages})
        return Next()


STEP = InputPagesStep()
