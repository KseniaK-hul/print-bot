# ==========================================================================
# Шаг 12 — сборка одной брошюры: выбор файлов в нужном порядке (LOGIC.md §2.5).
#
# Здесь жил баг «диалог о брошюрах зависает»: условие выхода из цикла было
# размазано между показом клавиатуры и обработчиком типа переплёта, и когда
# свободные файлы заканчивались раньше заявленного числа брошюр, шаг
# возвращал одно состояние, а сообщение уходило про другое.
#
# Теперь цикл один и решение «есть ли ещё что собирать» принимается в
# core/flow.py в одном месте (см. more_brochures_possible).
# ==========================================================================

from core.ctx import Ctx
from core.step import CALLBACK, Again, Answer, Jump, Next, Outcome, Stay, Step


def _keyboard(ctx: Ctx):
    """Свободные файлы с галочками и порядковыми номерами."""
    picked = ctx.scratch["brochure"]["picked"]
    rows = []
    for i in ctx.order.free_file_indices():
        name = ctx.order.files[i].name
        if i in picked:
            label = f"✅ {picked.index(i) + 1}. {name}"
        else:
            label = f"⬜ {name}"
        rows.append((label, f"proj_{i}"))
    rows.append((ctx.t("fold_done"), "proj_done"))
    rows.append((ctx.t("brochure_back"), "proj_back"))
    return ctx.raw_kb(*rows)


class BrochureAssembleStep(Step):
    id = "brochure_assemble"
    accepts = (CALLBACK,)
    buttons = ("proj_",)

    async def ask(self, ctx: Ctx) -> None:
        state = ctx.scratch["brochure"]
        await ctx.say("choose_brochure", _keyboard(ctx), num=state["current"])

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        state = ctx.scratch["brochure"]
        picked = state["picked"]

        if answer.data == "proj_done":
            if not picked:
                return Again("brochure_no_files")
            return Next()

        if answer.data == "proj_back":
            return Jump("brochure_count")

        # переключение файла: нажали второй раз — сняли выбор
        try:
            index = int(answer.suffix)
        except ValueError:
            return Stay()

        if index in picked:
            picked.remove(index)
        else:
            picked.append(index)

        await ctx.replace_raw(
            ctx.t("choose_brochure", num=state["current"]), _keyboard(ctx)
        )
        return Stay()


STEP = BrochureAssembleStep()
