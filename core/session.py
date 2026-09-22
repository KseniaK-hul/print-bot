# ==========================================================================
# core/session.py — ВСЁ состояние одного пользователя в одном объекте.
#
# В старой версии состояние было размазано по пяти местам: глобальный
# user_orders, глобальный user_language, context.user_data['brochure'],
# ['copy_queue'], ['selected_folding'] — и половина утечек памяти была
# именно из-за того, что чистили одно и забывали другое.
#
# Здесь: одна сессия = один объект = одна кнопка «удалить».
# ==========================================================================

from __future__ import annotations

import time
from dataclasses import dataclass, field

from core.models import Order
from texts import DEFAULT_LANG

# Виды сессий. От вида зависит, что делает сторож (tasks/janitor.py) и
# какие шаги вообще доступны пользователю.
KIND_ORDER = "order"        # обычное оформление заказа
KIND_FEEDBACK = "feedback"  # клиент оставляет отзыв после выдачи
KIND_OPERATOR = "operator"  # клиент переписывается с оператором


@dataclass(slots=True)
class Session:
    user_id: int
    lang: str = DEFAULT_LANG
    kind: str = KIND_ORDER

    # Единственный источник правды о том, где пользователь находится.
    # Строка, а не число — чтобы в логах читалось 'color_mode', а не '14'.
    step: str = "language"

    order: Order = field(default_factory=Order)

    # Временные данные текущего шага: очередь копий, собираемая брошюра и т.п.
    # Всё, что живёт короче заказа, кладётся сюда и умирает вместе с сессией.
    scratch: dict = field(default_factory=dict)

    last_seen: float = field(default_factory=time.monotonic)
    warned: bool = False              # предупреждение о таймауте уже отправлено
    warn_message_id: int | None = None  # чтобы убрать кнопку «Продолжить»

    def touch(self) -> None:
        """Пользователь подал признаки жизни — сбрасываем таймер молчания."""
        self.last_seen = time.monotonic()
        self.warned = False

    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_seen
