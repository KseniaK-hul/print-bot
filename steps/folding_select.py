# ==========================================================================
# Шаг 15 — выбор конкретных чертежей для складывания (LOGIC.md §2.6).
#
# Префикс кнопок здесь 'foldsel_', а не 'fold_' как на предыдущем шаге:
# в старой версии оба состояния слушали один паттерн ^fold_, и какой
# обработчик сработает, зависело от порядка регистрации.
# ==========================================================================

from core.ctx import Ctx
from core.step import CALLBACK, Answer, Next, Outcome, Stay, Step


def _keyboard(ctx: Ctx):
    selected = ctx.scratch.setdefault("folding", set())
    rows = []
    for i, f in ctx.order.standalone_big_format_files():
        mark = "✅ " if i in selected else "⬜ "
        rows.append((f"{mark}{f.name} ({f.format})", f"foldsel_{i}"))
    rows.append((ctx.t("fold_done"), "foldsel_done"))
    return ctx.raw_kb(*rows)


class FoldingSelectStep(Step):
    id = "folding_select"
    accepts = (CALLBACK,)
    buttons = ("foldsel_",)

    async def on_enter(self, ctx: Ctx) -> None:
        ctx.scratch["folding"] = set()

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say("fold_select", _keyboard(ctx))

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        selected = ctx.scratch.setdefault("folding", set())

        if answer.data == "foldsel_done":
            for index in selected:
                ctx.order.files[index].needs_folding = True
            return Next()

        try:
            index = int(answer.suffix)
        except ValueError:
            return Stay()

        selected.symmetric_difference_update({index})
        await ctx.replace_raw(ctx.t("fold_select"), _keyboard(ctx))
        return Stay()


STEP = FoldingSelectStep()
