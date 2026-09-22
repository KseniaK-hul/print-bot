# ==========================================================================
# core/store.py — хранилище сессий в памяти + ЕДИНСТВЕННАЯ точка очистки.
#
# Про память (расчёт под 512 МБ):
#   одна активная сессия  ~ 3-6 КБ  (диапазоны страниц вместо списков!)
#   Python + PTB + PyMuPDF ~ 100-120 МБ базового потребления
#   => даже 10 000 одновременных диалогов это ~50 МБ, то есть предел
#      сервера упирается НЕ в число заказов.
#
# Заказ живёт в памяти ровно до подтверждения: после отправки админу сессия
# сносится целиком — админу уже ушли и сводка, и сами PDF, а кнопки
# «Готов/Выдан/Отмена» несут client_id прямо в callback_data.
# ==========================================================================

from __future__ import annotations

from config import logger
from core.session import KIND_ORDER, Session
from tasks.monitor import log_snapshot
from texts import DEFAULT_LANG


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[int, Session] = {}
        # Язык переживает удаление сессии: если человек вернулся через час,
        # незачем снова спрашивать русский/английский.
        self._lang_cache: dict[int, str] = {}

    # ---------------- чтение ----------------
    def get(self, user_id: int) -> Session | None:
        return self._sessions.get(user_id)

    def has(self, user_id: int) -> bool:
        return user_id in self._sessions

    def items(self) -> list:
        # список, а не итератор: сторож удаляет сессии прямо во время обхода
        return list(self._sessions.items())

    def count(self) -> int:
        return len(self._sessions)

    def sessions(self) -> dict:
        """Все живые сессии — только для мониторинга, менять снаружи нельзя."""
        return self._sessions

    def remembered_lang(self, user_id: int) -> str:
        return self._lang_cache.get(user_id, DEFAULT_LANG)

    # ---------------- запись ----------------
    def start(self, user_id: int, kind: str = KIND_ORDER, step: str = "language") -> Session:
        """Создаёт новую сессию, снося предыдущую (со всеми её файлами)."""
        self.drop(user_id)
        session = Session(
            user_id=user_id,
            lang=self.remembered_lang(user_id),
            kind=kind,
            step=step,
        )
        self._sessions[user_id] = session
        logger.info("session start uid=%s kind=%s step=%s", user_id, kind, step)
        log_snapshot(self._sessions, f"start uid={user_id}")
        return session

    def set_lang(self, user_id: int, lang: str) -> None:
        self._lang_cache[user_id] = lang
        session = self._sessions.get(user_id)
        if session:
            session.lang = lang

    def drop(self, user_id: int, reason: str = "") -> None:
        """Единственный способ удалить сессию.

        Вызывается из четырёх мест: /start, /cancel, подтверждение заказа,
        таймаут. Всё остальное обязано ходить через него, чтобы временные
        файлы гарантированно удалялись.
        """
        session = self._sessions.pop(user_id, None)
        if session is None:
            return
        session.order.cleanup_files()
        logger.info(
            "session drop uid=%s step=%s reason=%s (осталось сессий: %d)",
            user_id, session.step, reason or "-", len(self._sessions),
        )
        # Замер ПОСЛЕ удаления файлов и сессии — в логе видно, что убралось.
        log_snapshot(self._sessions, f"drop uid={user_id} {reason or '-'}")


store = SessionStore()
