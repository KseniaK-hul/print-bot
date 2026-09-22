# ==========================================================================
# Шаг 11 — сколько брошюр сшить (LOGIC.md §2.5).
# ==========================================================================

from core.ctx import Ctx
from core.step import TEXT, Again, Answer, Next, Outcome, Step


class BrochureCountStep(Step):
    id = "brochure_count"
    accepts = (TEXT,)

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say("brochure_count")

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        text = (answer.text or "").strip()
        if not text.isdigit():
            return Again("enter_number")

        count = int(text)
        ctx.order.brochures.clear()

        if count == 0:
            await ctx.say("no_brochure")
            return Next(0)

        # Больше брошюр, чем файлов, собрать физически нельзя — молча
        # ограничиваем, иначе цикл сборки упрётся в пустой список файлов.
        count = min(count, len(ctx.order.files))
        ctx.scratch["brochure"] = {"planned": count, "current": 1, "picked": []}
        return Next(count)


STEP = BrochureCountStep()
