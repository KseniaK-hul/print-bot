# ==========================================================================
# main.py — запуск бота.
#
# Обработчиков всего пять, и они не пересекаются: одна команда — один
# обработчик, всё остальное уходит в core/router.py. Сравни со старой
# версией, где на фильтр TEXT висело три разных обработчика и работал
# только первый.
# ==========================================================================

import threading

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from admin import panel
from config import (
    ENABLE_HEALTHCHECK,
    JANITOR_INTERVAL_SEC,
    MONITOR_INTERVAL_SEC,
    PORT,
    TOKEN,
    logger,
)
from core import router
from core.store import store
from tasks import monitor
from tasks.janitor import sweep
from tasks.tempfiles import sweep_stale_dirs


def build_application() -> Application:
    app = Application.builder().token(TOKEN).build()

    app.add_error_handler(router.on_error)

    # Команды
    app.add_handler(CommandHandler("start", router.cmd_start))
    app.add_handler(CommandHandler("cancel", router.cmd_cancel))
    app.add_handler(CommandHandler("reply", panel.cmd_reply))
    app.add_handler(CommandHandler("status", panel.cmd_status))

    # Всё остальное — в один роутер
    app.add_handler(CallbackQueryHandler(router.dispatch))
    app.add_handler(MessageHandler(~filters.COMMAND, router.dispatch))

    # Фоновые задачи: сторож брошенных диалогов и замер нагрузки
    if app.job_queue is not None:
        app.job_queue.run_repeating(sweep, interval=JANITOR_INTERVAL_SEC, first=JANITOR_INTERVAL_SEC)
        if MONITOR_INTERVAL_SEC > 0:
            app.job_queue.run_repeating(
                monitor.periodic, interval=MONITOR_INTERVAL_SEC, first=MONITOR_INTERVAL_SEC
            )
    else:
        logger.warning(
            "JobQueue недоступна — таймауты диалогов работать не будут. "
            "Установи python-telegram-bot[job-queue]."
        )

    return app


def run_healthcheck() -> None:
    """Мини-сервер, который нужен только хостингу (Render, тип Web Service),
    чтобы он видел открытый порт. К логике бота отношения не имеет."""
    from flask import Flask

    flask_app = Flask(__name__)

    @flask_app.route("/")
    def health():
        return "Bot is running!"

    flask_app.run(host="0.0.0.0", port=PORT)


def main() -> None:
    if not TOKEN:
        raise SystemExit("Не задан V2_BOT_TOKEN (или BOT_TOKEN) в .env")

    sweep_stale_dirs()

    if ENABLE_HEALTHCHECK:
        threading.Thread(target=run_healthcheck, daemon=True).start()

    app = build_application()
    logger.info("🤖 Бот запущен")
    # Точка отсчёта: сколько бот занимает, пока с ним никто не разговаривает.
    monitor.log_snapshot(store.sessions(), "старт, пользователей нет")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
