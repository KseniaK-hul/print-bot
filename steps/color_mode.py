# ==========================================================================
# Шаг 6 — цвет: всё цветом / всё ЧБ / выбрать страницы (LOGIC.md §2.4.2).
#
# Это единственный источник правды о цвете: PDF мы больше не анализируем,
# пользователь говорит сам. Заодно исчезла ситуация, когда угаданный ботом
# цвет расходился с тем, что человек имел в виду.
# ==========================================================================

from core.ctx import Ctx
from core.models import PageSelection
from core.step import CALLBACK, Answer, Next, Outcome, Step


class ColorModeStep(Step):
    id = "color_mode"
    accepts = (CALLBACK,)
    buttons = ("color_",)

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say(
            "color_choice",
            ctx.kb(
                ("color_all", "color_all"),
                ("bw_all", "color_bw"),
                ("color_specific", "color_spec"),
            ),
        )

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        f = ctx.order.current_file

        if answer.data == "color_all":
            # цветные = ровно те страницы, которые печатаем
            f.color = PageSelection(ranges=f.pages.ranges)
            if f.pages.ranges is None:
                f.color = PageSelection.parse(f"1-{f.total_pages}", f.total_pages)
            return Next("all")

        if answer.data == "color_bw":
            f.color = PageSelection(ranges=[])
            return Next("bw")

        return Next("specific")


STEP = ColorModeStep()
