# ==========================================================================
# core/router.py — единственная точка входа для ВСЕХ сообщений и кнопок.
#
# Почему свой роутер вместо ConversationHandler: у PTB состояния и паттерны
# кнопок регистрируются отдельно, и когда состояний два десятка, обработчики
# начинают перехватывать чужие апдейты. Именно так появились баги «отзыв на
# английском не отвечает», «оператор не может ответить» и «комментарий к
# отзыву не доходит до админа» — там на один фильтр TEXT висело несколько
# обработчиков, а срабатывал только первый.
#
# Здесь состояние ровно одно — session.step, и оно наше. Каждый апдейт
# оставляет одну строку в логе: uid, шаг, что пришло, куда ушли.
# ==========================================================================

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from admin import panel
from config import (
    ADMIN_ID,
    DEBUG_MODE,
    ERROR_CHAT_ID,
    MAX_FILE_SIZE_MB,
    MIN_FILE_SIZE_KB,
    logger,
)
from core.ctx import Ctx
from core.flow import resolve
from core.session import KIND_OPERATOR, KIND_ORDER, Session
from core.step import (
    CALLBACK,
    DOCUMENT,
    TEXT,
    Again,
    Answer,
    Finish,
    Jump,
    Next,
    Repeat,
    Stay,
)
from core.store import store
from steps import STEPS
from tasks.clock import is_business_hours
from tasks.janitor import remove_warning
from texts import translate

FIRST_STEP = "language"


# --------------------------------------------------------------------------
# Разбор апдейта
# --------------------------------------------------------------------------
def build_answer(update: Update) -> Answer | None:
    if update.callback_query is not None:
        return Answer(kind=CALLBACK, data=update.callback_query.data)
    if update.message is None:
        return None
    if update.message.document is not None:
        return Answer(kind=DOCUMENT, document=update.message.document)
    if update.message.text is not None:
        return Answer(kind=TEXT, text=update.message.text)
    return None


async def _ack(update: Update) -> None:
    """Гасим «часики» на кнопке. Сетевой сбой тут не должен ронять апдейт —
    именно на этой строке падал старый бот при обрыве связи."""
    if update.callback_query is None:
        return
    try:
        await update.callback_query.answer()
    except Exception as e:
        logger.warning("не удалось подтвердить нажатие кнопки: %s", e)


# --------------------------------------------------------------------------
# Команды
# --------------------------------------------------------------------------
async def cmd_start(update: Update, tg: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    lang = store.remembered_lang(user_id)

    if user_id == ADMIN_ID and not DEBUG_MODE:
        await update.message.reply_text(translate(lang, "admin_start_blocked"))
        return

    if not is_business_hours():
        await update.message.reply_text(translate(lang, "working_hours"))
        return

    session = store.start(user_id, kind=KIND_ORDER, step=FIRST_STEP)
    ctx = Ctx(update, tg, session)
    await STEPS[FIRST_STEP].on_enter(ctx)
    await STEPS[FIRST_STEP].ask(ctx)


async def cmd_cancel(update: Update, tg: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    lang = store.remembered_lang(user_id)
    store.drop(user_id, reason="/cancel")
    await update.message.reply_text(
        translate(lang, "order_cancelled") + translate(lang, "order_again")
    )


# --------------------------------------------------------------------------
# Главный диспетчер
# --------------------------------------------------------------------------
async def dispatch(update: Update, tg: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None:
        return

    user_id = update.effective_user.id
    answer = build_answer(update)
    if answer is None:
        return

    await _ack(update)

    # 1) кнопка «Продолжить» из предупреждения о таймауте
    if answer.kind == CALLBACK and answer.data == "idle_continue":
        await _handle_continue(update, tg, user_id)
        return

    # 2) админские кнопки и админский ввод текста
    if answer.kind == CALLBACK and await panel.handle_callback(update, tg, answer.data or ""):
        return
    if answer.kind == TEXT and await panel.handle_text(update, tg, answer.text or ""):
        return

    # 3) ответ на предложение оператора (кнопка живёт и без активной сессии)
    if answer.kind == CALLBACK and answer.data in ("op_yes", "op_no"):
        await _handle_operator_offer(update, tg, user_id, answer.data)
        return

    # 4) обычный ход диалога
    session = store.get(user_id)
    if session is None:
        await _no_session(update, tg, user_id, answer)
        return

    session.touch()
    # Человек ответил — предупреждение «диалог закроется через 30 сек»
    # больше не соответствует правде, а его кнопка ведёт в никуда.
    if session.warn_message_id:
        await remove_warning(tg.bot, session)

    step = STEPS.get(session.step)
    if step is None:
        logger.error("uid=%s неизвестный шаг %r — закрываю сессию", user_id, session.step)
        store.drop(user_id, reason="unknown_step")
        return

    ctx = Ctx(update, tg, session)

    # СНАЧАЛА отсеиваем чужие нажатия — до проверки типа ввода.
    #
    # Кнопка «не наша» в двух случаях: шаг вообще не работает с кнопками
    # (ждёт текст) или ждёт кнопки, но другие. И то и другое означает одно:
    # человек нажал на старую клавиатуру, которую Telegram ещё показывает,
    # пока первое нажатие уже увело диалог дальше.
    #
    # Раньше этот случай попадал в _mismatch и бот отвечал «я не умею читать
    # текст, перевести на оператора?» — на каждое лишнее нажатие. Молчание
    # правильнее: на экране у человека уже висит актуальный вопрос.
    if answer.kind == CALLBACK:
        if CALLBACK not in step.accepts or not step.owns(answer.data or ""):
            logger.info(
                "uid=%s шаг %s: чужая кнопка %r — игнорирую",
                user_id, session.step, answer.data,
            )
            return
    elif answer.kind not in step.accepts:
        await _mismatch(ctx, step, answer)
        return

    outcome = await step.handle(ctx, answer)
    await _apply(ctx, step, outcome)


# --------------------------------------------------------------------------
# Применение результата шага
# --------------------------------------------------------------------------
async def _apply(ctx: Ctx, step, outcome) -> None:
    session = ctx.session
    came_from = session.step

    if isinstance(outcome, Stay):
        logger.info("uid=%s %s -> (остаёмся)", session.user_id, came_from)
        return

    if isinstance(outcome, Again):
        # notify, а не say: ошибка приходит отдельным сообщением и не
        # затирает вопрос вместе с его клавиатурой.
        await ctx.notify(outcome.error_key, **outcome.kwargs)
        logger.info("uid=%s %s -> переспрашиваем (%s)", session.user_id, came_from, outcome.error_key)
        return

    if isinstance(outcome, Repeat):
        await step.ask(ctx)
        logger.info("uid=%s %s -> следующий пункт того же шага", session.user_id, came_from)
        return

    if isinstance(outcome, Finish):
        store.drop(session.user_id, reason=outcome.reason)
        logger.info("uid=%s %s -> конец (%s)", session.user_id, came_from, outcome.reason)
        return

    if isinstance(outcome, Jump):
        next_step = outcome.step
    elif isinstance(outcome, Next):
        next_step = resolve(session, came_from, outcome.value)
    else:
        logger.error("uid=%s шаг %s вернул непонятный результат %r", session.user_id, came_from, outcome)
        return

    if next_step is None:
        store.drop(session.user_id, reason="flow_end")
        logger.info("uid=%s %s -> конец маршрута", session.user_id, came_from)
        return

    if next_step not in STEPS:
        logger.error("uid=%s маршрут ведёт на несуществующий шаг %r", session.user_id, next_step)
        store.drop(session.user_id, reason="broken_flow")
        return

    session.step = next_step
    logger.info("uid=%s %s -> %s", session.user_id, came_from, next_step)

    following = STEPS[next_step]
    await following.on_enter(ctx)
    await following.ask(ctx)


# --------------------------------------------------------------------------
# Нештатные ситуации
# --------------------------------------------------------------------------
async def _mismatch(ctx: Ctx, step, answer: Answer) -> None:
    """Пришло не то, что шаг ждёт."""
    # Прислали ещё файлы, пока настраиваем текущий (баг-репорт п.10):
    # объясняем правила, а не отвечаем «формат не поддерживается».
    if answer.kind == DOCUMENT:
        await ctx.say(
            "file_one_at_a_time",
            min_kb=MIN_FILE_SIZE_KB,
            max_mb=MAX_FILE_SIZE_MB,
        )
        return

    # Текст там, где ждали кнопку (ТЗ §4): предлагаем оператора, но заказ
    # НЕ выбрасываем — если человек откажется, продолжим с того же места.
    await ctx.say("operator_text", ctx.kb(("operator_yes", "op_yes"), ("operator_no", "op_no")))


async def _no_session(update: Update, tg: ContextTypes.DEFAULT_TYPE, user_id: int, answer: Answer) -> None:
    """Пишут боту вне какого-либо диалога."""
    lang = store.remembered_lang(user_id)

    if user_id == ADMIN_ID and not DEBUG_MODE:
        return  # админ просто что-то печатает у себя — молчим

    if answer.kind == DOCUMENT:
        await update.message.reply_text(translate(lang, "bad_file"))
        return
    if answer.kind == CALLBACK:
        # Кнопка из уже закрытого диалога. Молчим — ровно как со старыми
        # кнопками внутри диалога.
        #
        # Отвечать здесь текстом нельзя: при двойном клике на «Заказать»
        # второе нажатие прилетает уже после того, как заказ отправлен и
        # сессия удалена, и человек получал «диалог закрыт из-за молчания»
        # вместо тишины — на каждый лишний клик по одному сообщению.
        # Почему диалога больше нет, ему в любом случае уже сказали: либо
        # «заказ принят», либо сообщение о закрытии по таймауту.
        logger.info("uid=%s кнопка %r вне диалога — игнорирую", user_id, answer.data)
        await _drop_keyboard(update)
        return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(translate(lang, "operator_yes"), callback_data="op_yes")],
        [InlineKeyboardButton(translate(lang, "operator_no"), callback_data="op_no")],
    ])
    await update.message.reply_text(translate(lang, "operator_text"), reply_markup=keyboard)


async def _drop_keyboard(update: Update) -> None:
    """Снимает клавиатуру с сообщения, на кнопку которого только что нажали.

    Чтобы мёртвая кнопка не осталась висеть и не звала нажать ещё раз.
    Сообщение могло быть уже отредактировано или удалено — это нормально.
    """
    try:
        await update.callback_query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logger.debug("не удалось снять клавиатуру: %s", e)


async def _handle_operator_offer(update: Update, tg, user_id: int, data: str) -> None:
    lang = store.remembered_lang(user_id)

    if data == "op_no":
        session = store.get(user_id)
        if session is not None:
            # Отказался от оператора посреди заказа — возвращаем к вопросу,
            # на котором остановились, ничего не потеряв.
            ctx = Ctx(update, tg, session)
            await STEPS[session.step].ask(ctx)
            return
        await update.effective_message.reply_text(translate(lang, "operator_declined"))
        return

    session = store.start(user_id, kind=KIND_OPERATOR, step="operator_chat")
    ctx = Ctx(update, tg, session)
    await STEPS["operator_chat"].ask(ctx)
    await panel.notify_operator_request(tg, user_id)


async def _handle_continue(update: Update, tg, user_id: int) -> None:
    session = store.get(user_id)
    if session is None:
        await update.effective_message.reply_text(
            translate(store.remembered_lang(user_id), "idle_closed")
        )
        return

    session.touch()
    # Само предупреждение сейчас превратится в «Продолжаем!», удалять его
    # потом не надо — просто забываем про него.
    session.warn_message_id = None

    ctx = Ctx(update, tg, session)
    await ctx.replace("idle_continue_ok")
    # Повторяем вопрос, на котором человек застрял.
    await STEPS[session.step].ask(ctx)


# --------------------------------------------------------------------------
# Ошибки
# --------------------------------------------------------------------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("необработанная ошибка: %s", context.error, exc_info=context.error)
    try:
        # ERROR_CHAT_ID, а не ADMIN_ID: трейсбек — дело разработчика.
        await context.bot.send_message(
            chat_id=ERROR_CHAT_ID, text=f"⚠️ Ошибка в боте: {context.error}"
        )
    except Exception:
        pass
