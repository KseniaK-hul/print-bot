# ==========================================================================
# tasks/janitor.py — сторож: закрывает брошенные диалоги и чистит память.
#
# Заказ (KIND_ORDER) — самое дорогое: в нём скачанные PDF и работа, которую
# жалко потерять, поэтому сначала предупреждение:
#   молчит IDLE_WARN_SEC (15 мин)        -> предупреждение + кнопка «Продолжить»
#   молчит ещё IDLE_GRACE_SEC (30 сек)   -> диалог закрыт, сессия и файлы удалены
#
# Побочные сессии — чат с оператором и незаконченный отзыв. Терять там
# нечего и файлов они не держат, поэтому предупреждения нет: просто
# закрываем после IDLE_SIDE_SEC. Главное здесь не память, а то, что человек
# иначе навсегда остаётся в режиме оператора — шаг operator_chat сам себя
# не завершает.
#
# Одна фоновая задача на весь бот, а не таймер на каждого пользователя:
# при тысяче диалогов это тысяча запланированных задач против одного прохода
# по словарю раз в 10 секунд.
# ==========================================================================

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import IDLE_GRACE_SEC, IDLE_SIDE_SEC, IDLE_WARN_SEC, logger
from core.session import KIND_OPERATOR, KIND_ORDER
from core.store import store
from texts import translate


async def sweep(context) -> None:
    for user_id, session in store.items():
        idle = session.idle_seconds()

        if session.kind == KIND_ORDER:
            if not session.warned and idle >= IDLE_WARN_SEC:
                await _warn(context, session)
            elif session.warned and idle >= IDLE_WARN_SEC + IDLE_GRACE_SEC:
                await _close_order(context, session)
        elif idle >= IDLE_SIDE_SEC:
            await _close_side(context, session)


async def _warn(context, session) -> None:
    session.warned = True
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            translate(session.lang, "idle_continue"), callback_data="idle_continue"
        )]]
    )
    try:
        message = await context.bot.send_message(
            chat_id=session.user_id,
            text=translate(session.lang, "idle_warning", seconds=IDLE_GRACE_SEC),
            reply_markup=keyboard,
        )
        session.warn_message_id = message.message_id
    except Exception as e:
        # Не смогли достучаться (заблокировали бота, сеть) — просто закроем
        # диалог на следующем проходе, ронять сторож из-за этого нельзя.
        logger.warning("не удалось предупредить uid=%s: %s", session.user_id, e)


async def remove_warning(bot, session) -> None:
    """Убирает сообщение «диалог закроется через 30 сек» вместе с кнопкой.

    Вызывается и когда диалог закрылся (кнопка уже ни к чему), и когда
    человек всё-таки ответил (предупреждение перестало быть правдой).
    Иначе в чате остаётся живая кнопка под неактуальным текстом.
    """
    message_id = session.warn_message_id
    if not message_id:
        return
    session.warn_message_id = None

    try:
        await bot.delete_message(chat_id=session.user_id, message_id=message_id)
    except Exception as e:
        # Удалять чужие и старые (>48 ч) сообщения Telegram не даёт —
        # тогда хотя бы снимаем кнопку, чтобы её нельзя было нажать.
        logger.debug("не удалось удалить предупреждение: %s", e)
        try:
            await bot.edit_message_reply_markup(
                chat_id=session.user_id, message_id=message_id, reply_markup=None
            )
        except Exception:
            pass


async def _close_order(context, session) -> None:
    await remove_warning(context.bot, session)
    await _notify(context, session, "idle_closed")
    store.drop(session.user_id, reason="idle_timeout")
    logger.info("заказ uid=%s закрыт по таймауту", session.user_id)


async def _close_side(context, session) -> None:
    # Про закрытый чат с оператором сказать надо — человек ждёт ответа.
    # Про брошенный отзыв молчим: напоминание о нём выглядело бы навязчиво.
    if session.kind == KIND_OPERATOR:
        await _notify(context, session, "operator_closed")
    store.drop(session.user_id, reason=f"idle_{session.kind}")
    logger.info("сессия %s uid=%s закрыта по таймауту", session.kind, session.user_id)


async def _notify(context, session, key: str) -> None:
    try:
        await context.bot.send_message(
            chat_id=session.user_id, text=translate(session.lang, key)
        )
    except Exception as e:
        logger.warning("не удалось уведомить uid=%s: %s", session.user_id, e)
