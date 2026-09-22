# ==========================================================================
# admin/panel.py — кнопки и ответы админа.
#
# Все админские callback_data начинаются с 'adm_' — так их невозможно
# перепутать с клиентскими кнопками (в старой версии 'cancel_' у админа и
# отмена заказа у клиента жили опасно близко).
#
# Клиенту всё пишется на ЕГО языке: store.remembered_lang(client_id).
# Язык переживает удаление сессии, поэтому уведомление об отмене через час
# после заказа всё равно придёт правильным.
# ==========================================================================

from __future__ import annotations

import time

from config import ADMIN_ID, ADMIN_PENDING_TTL_SEC, DEBUG_MODE, logger
from core.session import KIND_FEEDBACK
from core.store import store
from core.summary import admin_report
from tasks.clock import is_business_hours
from texts import LANG_RU, translate

# Что админ сейчас вводит текстом: причину отмены или ответ клиенту.
# Словарь на одного человека — держать это в сессии незачем.
# Запись живёт не дольше ADMIN_PENDING_TTL_SEC: иначе админ, нажавший
# «Отмена» и отвлёкшийся на час, отправил бы клиенту как причину отмены
# первое, что напишет боту потом.
pending: dict = {}


def _set_pending(mode: str, client_id: int) -> None:
    pending[ADMIN_ID] = {"mode": mode, "client_id": client_id, "at": time.monotonic()}


def _clear_pending() -> None:
    """Любая другая кнопка отменяет незаконченный ввод."""
    pending.pop(ADMIN_ID, None)


# --------------------------------------------------------------------------
# Статус заказа
#
# Кнопки под заказом живут вечно: client_id зашит в callback_data, и старое
# сообщение можно нажать хоть через месяц. Без учёта статуса админ мог
# выдать уже выданный заказ (клиент получал просьбу оценить второй раз) или
# отменить то, что уже отдал.
#
# Хранится только статус последнего заказа клиента — несколько байт. Словарь
# ограничен MAX_TRACKED_ORDERS: после перезапуска бота он пуст, и старые
# кнопки снова сработают — это осознанный размен, чтобы не заводить базу.
# --------------------------------------------------------------------------
NEW, READY, ISSUED, CANCELLED = "new", "ready", "issued", "cancelled"
MAX_TRACKED_ORDERS = 500
order_status: dict = {}

_STATUS_MESSAGE = {
    READY: "Заказ уже отмечен готовым.",
    ISSUED: "Заказ уже выдан — действие недоступно.",
    CANCELLED: "Заказ отменён — действие недоступно.",
}


def _status(client_id: int) -> str:
    return order_status.get(client_id, NEW)


def _set_status(client_id: int, status: str) -> None:
    order_status.pop(client_id, None)
    order_status[client_id] = status
    while len(order_status) > MAX_TRACKED_ORDERS:
        order_status.pop(next(iter(order_status)))


async def _hide_buttons(query) -> None:
    """Убирает кнопки у нажатого сообщения, чтобы не звали нажать ещё раз."""
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logger.debug("не удалось убрать кнопки: %s", e)


def _t_admin(key: str, **kwargs) -> str:
    return translate(LANG_RU, key, **kwargs)


async def _tell_client(tg, client_id: int, key: str, **kwargs) -> None:
    lang = store.remembered_lang(client_id)
    await tg.bot.send_message(chat_id=client_id, text=translate(lang, key, **kwargs))


async def _to_admin(tg, text: str, reply_markup=None):
    """Служебное сообщение админу.

    В DEBUG_MODE админ и клиент — один аккаунт, и оба типа сообщений падают
    в один чат. Метка «👑» показывает, что это админская панель, а не ответ
    клиенту: без неё «Ваш заказ выдан» и «Клиент N уведомлён о выдаче»
    выглядят как одно и то же сообщение, присланное дважды.
    """
    prefix = "👑 " if DEBUG_MODE else ""
    return await tg.bot.send_message(
        chat_id=ADMIN_ID, text=f"{prefix}{text}", reply_markup=reply_markup
    )


# --------------------------------------------------------------------------
# Уведомления админу
#
# Всё, что видит админ, собирается здесь, а не внутри клиентских шагов:
# админ-панель у нас русскоязычная по определению (одна мастерская), и
# держать её строки в steps/ означало бы мешать два разных интерфейса.
# --------------------------------------------------------------------------
async def notify_new_order(tg, client_id: int, order) -> None:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    # Новый заказ обнуляет статус: кнопки прошлого, уже выданного заказа
    # не должны блокировать кнопки этого.
    _set_status(client_id, NEW)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Готов", callback_data=f"adm_ready_{client_id}")],
        [InlineKeyboardButton("📦 Выдан", callback_data=f"adm_issue_{client_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"adm_cancel_{client_id}")],
    ])
    await _to_admin(tg, admin_report(order, client_id), reply_markup=keyboard)

    # Файлы отправляем сразу же: после этого заказ в памяти держать не нужно.
    for f in order.files:
        try:
            with open(f.path, "rb") as document:
                # filename обязателен: на диске файл лежит под техническим
                # именем "<user_id>_<file_id>.pdf" (чтобы два файла с
                # одинаковым названием не затирали друг друга), и без этого
                # параметра Telegram показал бы админу именно его.
                await tg.bot.send_document(
                    chat_id=ADMIN_ID,
                    document=document,
                    filename=f.name,
                    caption=f"📎 {f.name}",
                )
        except Exception as e:
            # Один непрочитавшийся файл не должен обрушить отправку заказа:
            # сводка админу уже ушла, остальные файлы тоже надо доставить.
            logger.error("не удалось отправить админу файл %s: %s", f.name, e)


async def notify_feedback(tg, client_id: int, rating, comment: str) -> None:
    await _to_admin(
        tg,
        f"⭐ ОТЗЫВ ОТ {client_id}\nОценка: {rating}/10\nКомментарий: {comment}",
    )


async def notify_operator_request(tg, client_id: int) -> None:
    await _to_admin(tg, _t_admin("admin_operator_request", client_id=client_id))


async def notify_operator_message(tg, client_id: int, text: str) -> None:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            _t_admin("admin_reply_button"), callback_data=f"adm_reply_{client_id}"
        )],
        [InlineKeyboardButton("🔚 Завершить разговор", callback_data=f"adm_end_{client_id}")],
    ])
    await _to_admin(
        tg,
        _t_admin("admin_operator_message", client_id=client_id, text=text),
        reply_markup=keyboard,
    )


async def notify_operator_closed(tg, client_id: int, by_admin: bool) -> None:
    who = "оператор" if by_admin else "клиент"
    await _to_admin(tg, f"🔚 Разговор с клиентом {client_id} завершён ({who}).")


# --------------------------------------------------------------------------
# Кнопки под заказом
# --------------------------------------------------------------------------
async def handle_callback(update, tg, data: str) -> bool:
    """Обрабатывает adm_*-кнопки. Возвращает True, если кнопка была наша."""
    if not data.startswith("adm_"):
        return False

    query = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await query.answer(_t_admin("no_rights"), show_alert=True)
        return True

    _, action, raw_id = data.split("_", 2)
    client_id = int(raw_id)

    # Кнопки заказа работают, только пока заказ не закрыт. Кнопки оператора
    # ('reply', 'end') к статусу заказа отношения не имеют.
    if action in ("ready", "issue", "cancel"):
        status = _status(client_id)
        blocked = status in (ISSUED, CANCELLED) or (action == "ready" and status == READY)
        if blocked:
            await query.answer(_STATUS_MESSAGE[status], show_alert=True)
            await _hide_buttons(query)
            return True

    if action == "ready":
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        _clear_pending()
        _set_status(client_id, READY)
        await _tell_client(tg, client_id, "order_ready_client")
        # Кнопки «Готов» здесь уже нет — заказ только что отмечен готовым,
        # осталось только выдать его или отменить.
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Выдан", callback_data=f"adm_issue_{client_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"adm_cancel_{client_id}")],
        ])
        await _to_admin(
            tg, f"Клиент {client_id} уведомлён: заказ готов.", reply_markup=keyboard
        )
        return True

    if action == "issue":
        if not is_business_hours():
            await query.answer(_t_admin("issue_only_hours"), show_alert=True)
            return True
        _clear_pending()
        _set_status(client_id, ISSUED)
        # Заводим клиенту сессию отзыва: его следующее сообщение попадёт
        # прямо в шаг feedback_rating общего роутера.
        store.start(client_id, kind=KIND_FEEDBACK, step="feedback_rating")
        await _tell_client(tg, client_id, "feedback_ask")
        await _hide_buttons(query)
        await _to_admin(tg, f"Клиент {client_id} уведомлён о выдаче, ждём оценку.")
        return True

    if action == "cancel":
        _set_pending("cancel", client_id)
        await _to_admin(tg, _t_admin("cancel_ask_reason", client_id=client_id))
        return True

    if action == "reply":
        _set_pending("reply", client_id)
        await _to_admin(tg, _t_admin("admin_reply_ask", client_id=client_id))
        return True

    if action == "end":
        # Оператор закрывает разговор со своей стороны: клиент выходит из
        # режима оператора, иначе он остался бы в нём навсегда.
        _clear_pending()
        session = store.get(client_id)
        store.drop(client_id, reason="operator_closed_by_admin")
        if session is not None:
            await _tell_client(tg, client_id, "operator_closed")
        await _to_admin(tg, f"🔚 Разговор с клиентом {client_id} завершён (оператор).")
        return True

    return True


# --------------------------------------------------------------------------
# Текст от админа: причина отмены или ответ клиенту
# --------------------------------------------------------------------------
async def handle_text(update, tg, text: str) -> bool:
    """True, если текст был админским вводом и уже обработан."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID or user_id not in pending:
        return False

    task = pending.pop(user_id)
    client_id = task["client_id"]

    # Слишком долго думал — текст мог быть про что-то совсем другое,
    # клиенту его отправлять нельзя.
    if time.monotonic() - task["at"] > ADMIN_PENDING_TTL_SEC:
        await update.message.reply_text(
            f"⌛ Прошло больше {ADMIN_PENDING_TTL_SEC // 60} мин — текст клиенту "
            f"{client_id} НЕ отправлен.\nНажмите кнопку под заказом ещё раз."
        )
        logger.info("админский ввод (%s) для %s просрочен", task["mode"], client_id)
        return True

    if task["mode"] == "cancel":
        # Статус ставим только сейчас: если админ нажал «Отмена» и передумал,
        # не дописав причину, заказ должен остаться рабочим.
        _set_status(client_id, CANCELLED)
        await _tell_client(tg, client_id, "cancel_notified", reason=text)
        await _to_admin(tg, _t_admin("cancel_done_admin", client_id=client_id))
        logger.info("админ отменил заказ клиента %s", client_id)
    else:
        await _tell_client(tg, client_id, "operator_reply_prefix", text=text)
        await _to_admin(tg, _t_admin("admin_reply_sent", client_id=client_id))
        logger.info("админ ответил клиенту %s", client_id)

    return True


# --------------------------------------------------------------------------
# Команды
# --------------------------------------------------------------------------
async def cmd_reply(update, tg) -> None:
    """/reply <id> <текст> — старый способ ответа, оставлен как запасной."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(_t_admin("no_rights"))
        return

    args = tg.args
    if len(args) < 2 or not args[0].lstrip("-").isdigit():
        await update.message.reply_text("❌ Формат: /reply <ID> <текст>")
        return

    client_id = int(args[0])
    await _tell_client(tg, client_id, "operator_reply_prefix", text=" ".join(args[1:]))
    await update.message.reply_text(_t_admin("admin_reply_sent", client_id=client_id))


async def cmd_status(update, tg) -> None:
    """/status — нагрузка на сервер прямо сейчас, то же, что пишется в лог."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(_t_admin("no_rights"))
        return
    from tasks.monitor import snapshot

    details = snapshot(store.sessions()).replace(" | ", "\n")
    await update.message.reply_text(f"✅ Бот работает.\n{details}")
