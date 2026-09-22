# ==========================================================================
# Шаг 16 — копии: по каждому файлу И по каждой брошюре (LOGIC.md §2.7).
#
# Раньше копии брошюр не спрашивались вообще (в коде стояло copies=1), из-за
# чего разваливался типовой студенческий заказ «1 файл × 18 копий + 18
# брошюр» (ТЗ §3.3).
#
# Цикл сделан очередью: она строится один раз при входе на шаг, а Repeat()
# заставляет шаг задать следующий вопрос. Условие выхода — одно, в handle().
# ==========================================================================

from core.ctx import Ctx
from core.step import TEXT, Again, Answer, Next, Outcome, Repeat, Step

FILE = "file"
BROCHURE = "brochure"


class CopiesStep(Step):
    id = "copies"
    accepts = (TEXT,)

    async def on_enter(self, ctx: Ctx) -> None:
        queue = [(FILE, i) for i in range(len(ctx.order.files))]
        queue += [(BROCHURE, i) for i in range(len(ctx.order.brochures))]
        ctx.scratch["copies_queue"] = queue
        ctx.scratch["copies_pos"] = 0

    async def ask(self, ctx: Ctx) -> None:
        kind, index = self._current(ctx)
        if kind == FILE:
            await ctx.say("copies_ask_file", name=ctx.order.files[index].name)
        else:
            project = ctx.order.brochures[index]
            await ctx.say(
                "copies_ask_brochure",
                num=index + 1,
                type=ctx.t(project.binding),   # 'spring' -> «🔄 Пружинка»
            )

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        text = (answer.text or "").strip()
        if not text.isdigit() or int(text) <= 0:
            return Again("enter_number")

        kind, index = self._current(ctx)
        if kind == FILE:
            ctx.order.files[index].copies = int(text)
        else:
            ctx.order.brochures[index].copies = int(text)

        ctx.scratch["copies_pos"] += 1
        if ctx.scratch["copies_pos"] < len(ctx.scratch["copies_queue"]):
            return Repeat()

        await ctx.say("copies_set")
        return Next()

    @staticmethod
    def _current(ctx: Ctx):
        queue = ctx.scratch["copies_queue"]
        return queue[ctx.scratch["copies_pos"]]


STEP = CopiesStep()
