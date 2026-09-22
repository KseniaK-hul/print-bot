# ==========================================================================
# Шаг 13 — тип переплёта собранной брошюры (LOGIC.md §2.5).
#
# В BrochureProject кладём КЛЮЧ текста ('spring'/'string'), а не готовую
# строку. Из-за готовой строки админу и в сводке раньше приходило
# «Брошюра #1 (Spring)» вместо «Пружинка» (баг-репорт п.4).
# ==========================================================================

from core.ctx import Ctx
from core.models import BrochureProject
from core.step import CALLBACK, Answer, Next, Outcome, Step


class BrochureTypeStep(Step):
    id = "brochure_type"
    accepts = (CALLBACK,)
    buttons = ("btype_",)

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say(
            "brochure_type",
            ctx.kb(("spring", "btype_spring"), ("string", "btype_string")),
        )

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        state = ctx.scratch["brochure"]
        binding = "string" if answer.data == "btype_string" else "spring"

        ctx.order.brochures.append(
            BrochureProject(file_indices=list(state["picked"]), binding=binding)
        )
        await ctx.say("brochure_saved", num=state["current"])

        state["picked"] = []
        state["current"] += 1

        # Заявили больше брошюр, чем осталось свободных файлов — честно
        # сообщаем и идём дальше (раньше диалог в этом месте вставал).
        done = len(ctx.order.brochures)
        if state["current"] <= state["planned"] and not ctx.order.free_file_indices():
            await ctx.say("brochure_files_exhausted", done=done, planned=state["planned"])
        elif state["current"] > state["planned"]:
            await ctx.say("brochures_all_done")

        return Next()


STEP = BrochureTypeStep()
