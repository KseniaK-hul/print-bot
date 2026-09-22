# ==========================================================================
# Шаг 7 — какие страницы печатать цветом (LOGIC.md §2.4.2).
#
# Пересекаем с уже выбранными для печати: если печатаем 1-10, а цветными
# названы 5-20, цветными станут только 5-10 — за остальные денег не берём.
# ==========================================================================

from core.ctx import Ctx
from core.models import PageSelection
from core.step import TEXT, Again, Answer, Next, Outcome, Step


class InputColorPagesStep(Step):
    id = "input_color_pages"
    accepts = (TEXT,)

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say("choose_color_pages")

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        f = ctx.order.current_file
        try:
            requested = PageSelection.parse(answer.text or "", f.total_pages)
        except (ValueError, AttributeError):
            return Again("choose_color_pages")

        f.color = requested.intersect(f.pages, f.total_pages)
        return Next()


STEP = InputColorPagesStep()
