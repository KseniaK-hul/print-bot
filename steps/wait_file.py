# ==========================================================================
# Шаг 3 — приём PDF (LOGIC.md §2.3).
#
# Тяжёлый анализ цвета отсюда УБРАН: раньше бот распаковывал каждую картинку
# в сырой RGB (скан A0 в 300 dpi = ~400 МБ на один файл), из-за чего процесс
# на 512 МБ падал от одного крупного чертежа. Теперь мы открываем PDF только
# ради количества страниц, а цвет спрашиваем у пользователя дальше.
# ==========================================================================

import os

from config import MAX_FILE_SIZE_MB, MIN_FILE_SIZE_KB, TEMP_DIR_PREFIX, logger
from core.ctx import Ctx
from core.models import PrintFile
from core.step import DOCUMENT, Again, Answer, Next, Outcome, Step
from core.store import store
from tasks.monitor import log_snapshot
from tasks.pdf import count_pages


class WaitFileStep(Step):
    id = "wait_file"
    accepts = (DOCUMENT,)

    async def ask(self, ctx: Ctx) -> None:
        # Первый файл — приветственный текст после авторизации,
        # последующие — короткое «отправьте следующий».
        key = "add_file" if ctx.order.files else "auth_success"
        await ctx.say(key)

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        doc = answer.document

        if not doc or not doc.file_name or not doc.file_name.lower().endswith(".pdf"):
            return Again("bad_file")
        if doc.file_size and doc.file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            return Again("file_too_big", {"max_mb": MAX_FILE_SIZE_MB})
        if doc.file_size and doc.file_size < MIN_FILE_SIZE_KB * 1024:
            return Again("file_too_small", {"min_kb": MIN_FILE_SIZE_KB})

        folder = f"{TEMP_DIR_PREFIX}{ctx.user_id}"
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{ctx.user_id}_{doc.file_id}.pdf")

        tg_file = await ctx.tg.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(path)

        total_pages = await count_pages(path)
        if total_pages == 0:
            self._remove(path)
            return Again("pdf_error")

        ctx.order.files.append(
            PrintFile(path=path, name=doc.file_name, total_pages=total_pages)
        )
        logger.info("uid=%s файл принят: %s, страниц %d, всего файлов %d",
                    ctx.user_id, doc.file_name, total_pages, len(ctx.order.files))
        log_snapshot(store.sessions(), f"file uid={ctx.user_id}")
        return Next()

    @staticmethod
    def _remove(path: str) -> None:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as e:
            logger.warning("Не удалось удалить %s: %s", path, e)


STEP = WaitFileStep()
