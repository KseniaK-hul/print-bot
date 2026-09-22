# ==========================================================================
# core/ctx.py — то, что получает КАЖДЫЙ шаг вместо голых update/context.
#
# ГЛАВНАЯ ИДЕЯ: шаг не имеет доступа к готовым строкам — только к ключам.
# ctx.say('fold_choice') вместо reply_text("📐 Нужно ли сложить чертежи?").
# Язык подставляется из сессии автоматически, поэтому «текст на русском в
# английском диалоге» перестаёт быть возможным по построению, а не по
# внимательности. tests/test_texts.py дополнительно ловит попытки написать
# русский текст прямо в шаге.
# ==========================================================================

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import logger
from core.models import Order
from core.session import Session
from texts import translate


class Ctx:
    """Фасад над Telegram-апдейтом, сессией и текстами."""

    __slots__ = ("update", "tg", "session", "_edited")

    def __init__(self, update: Update, tg: ContextTypes.DEFAULT_TYPE, session: Session):
        self.update = update
        self.tg = tg
        self.session = session
        # Ответил ли бот заменой сообщения с кнопкой в этом апдейте.
        # Ctx создаётся один раз на апдейт, поэтому флаг живёт ровно столько,
        # сколько длится обработка одного действия пользователя.
        self._edited = False

    # ---------------- быстрый доступ ----------------
    @property
    def user_id(self) -> int:
        return self.session.user_id

    @property
    def order(self) -> Order:
        return self.session.order

    @property
    def scratch(self) -> dict:
        return self.session.scratch

    @property
    def chat_id(self) -> int:
        return self.update.effective_chat.id

    # ---------------- тексты ----------------
    def t(self, key: str, **kwargs) -> str:
        """Единственный способ получить текст внутри шага."""
        return translate(self.session.lang, key, **kwargs)

    # ---------------- клавиатуры ----------------
    def kb(self, *rows) -> InlineKeyboardMarkup:
        """Клавиатура из ключей текстов: ctx.kb(('yes','add_y'), ('no','add_n')).

        Каждая строка — либо кортеж (ключ_текста, callback_data), либо список
        таких кортежей, если нужно несколько кнопок в ряд. Подписи переводятся
        автоматически.
        """
        keyboard = []
        for row in rows:
            buttons = row if isinstance(row, list) else [row]
            keyboard.append([
                InlineKeyboardButton(self.t(key), callback_data=data)
                for key, data in buttons
            ])
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def raw_kb(*rows) -> InlineKeyboardMarkup:
        """Клавиатура с готовыми подписями — для случаев, где подпись это
        имя файла или номер формата, а не переводимый текст."""
        keyboard = []
        for row in rows:
            buttons = row if isinstance(row, list) else [row]
            keyboard.append([
                InlineKeyboardButton(label, callback_data=data)
                for label, data in buttons
            ])
        return InlineKeyboardMarkup(keyboard)

    # ---------------- отправка ----------------
    #
    # Если пользователь ответил КНОПКОЙ, следующий вопрос заменяет собой то
    # сообщение, на котором он нажал: чат не забивается, и в нём не остаётся
    # старых клавиатур, по которым можно нажать второй раз. Так вёл себя
    # первоначальный бот, где везде вызывался edit_message_text.
    #
    # Заменяется только ПЕРВОЕ сообщение в рамках одного действия: если шаг
    # шлёт ещё что-то следом («Брошюра #1 готова», а затем новый вопрос),
    # остальное уходит обычными сообщениями, иначе второе затёрло бы первое.
    async def say(self, key: str, kb: InlineKeyboardMarkup | None = None, **kwargs):
        return await self._send(self.t(key, **kwargs), kb)

    async def say_raw(self, text: str, kb: InlineKeyboardMarkup | None = None):
        """Готовый текст — только для сводок, собранных из переведённых кусков."""
        return await self._send(text, kb)

    async def replace(self, key: str, kb: InlineKeyboardMarkup | None = None, **kwargs):
        """Заменить сообщение с кнопкой принудительно, даже если в этом
        апдейте бот уже что-то заменял."""
        return await self._send(self.t(key, **kwargs), kb, force_edit=True)

    async def replace_raw(self, text: str, kb: InlineKeyboardMarkup | None = None):
        return await self._send(text, kb, force_edit=True)

    async def notify(self, key: str, **kwargs):
        """Отдельное сообщение, которое НИКОГДА не затирает вопрос.

        Для сообщений об ошибке: заменить ими вопрос значило бы съесть
        клавиатуру, на которую человек как раз и должен нажать («вы не
        выбрали ни одного файла» вместо списка файлов — и диалог встал).
        """
        return await self.tg.bot.send_message(chat_id=self.chat_id, text=self.t(key, **kwargs))

    async def _send(self, text: str, kb: InlineKeyboardMarkup | None, force_edit: bool = False):
        query = self.update.callback_query
        if query is not None and (force_edit or not self._edited):
            self._edited = True
            try:
                return await query.edit_message_text(text=text, reply_markup=kb)
            except Exception as e:
                if "not modified" in str(e).lower():
                    # На экране уже ровно этот текст с этой же клавиатурой.
                    # Слать копию новым сообщением нельзя — получится дубль.
                    return None
                # Сообщение могло быть удалено или оказаться слишком старым
                # для правки — тогда просто пишем новое, а не роняем шаг.
                logger.warning("не удалось заменить сообщение: %s", e)

        return await self.tg.bot.send_message(chat_id=self.chat_id, text=text, reply_markup=kb)

    async def alert(self, key: str, **kwargs) -> None:
        """Всплывашка поверх кнопки (не создаёт сообщения в чате)."""
        query = self.update.callback_query
        if query is not None:
            await query.answer(self.t(key, **kwargs), show_alert=True)
