# ==========================================================================
# core/step.py — контракт одного шага диалога.
#
# Один вопрос пользователю = один класс = один файл в steps/.
# Хочешь понять, как работает выбор цвета — открываешь steps/color_mode.py,
# и там ВСЁ: текст вопроса, кнопки, разбор ответа, запись в заказ.
#
# handle() возвращает не «номер следующего состояния», а СМЫСЛ произошедшего
# (Next / Again / Repeat / Jump). Куда идти дальше — решает core/flow.py.
# Благодаря этому шаг можно проверить обычным тестом, без Telegram.
# ==========================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from core.ctx import Ctx

# --------------------------------------------------------------------------
# Что пришло от пользователя
# --------------------------------------------------------------------------
TEXT = "text"
CALLBACK = "callback"
DOCUMENT = "document"


@dataclass(slots=True)
class Answer:
    kind: str                       # TEXT | CALLBACK | DOCUMENT
    text: Optional[str] = None      # текст сообщения
    data: Optional[str] = None      # callback_data нажатой кнопки
    document: Any = None            # telegram.Document

    @property
    def suffix(self) -> str:
        """'fmt_A4' -> 'A4'. Удобно для кнопок вида префикс_значение."""
        if not self.data:
            return ""
        _, _, tail = self.data.partition("_")
        return tail


# --------------------------------------------------------------------------
# Что шаг решил делать дальше
# --------------------------------------------------------------------------
class Outcome:
    """Базовый результат обработки ответа."""


@dataclass(slots=True)
class Next(Outcome):
    """Ответ принят, идём дальше по маршруту из flow.py.

    value передаётся в правило перехода — например, 'A4' решает, спрашивать
    ли про одностороннюю печать.
    """
    value: Any = None


@dataclass(slots=True)
class Again(Outcome):
    """Ответ не подошёл — показать ошибку и переспросить тот же вопрос."""
    error_key: str
    kwargs: dict = field(default_factory=dict)


@dataclass(slots=True)
class Repeat(Outcome):
    """Остаёмся на этом же шаге и задаём его заново.

    Так устроены циклы: «сколько копий» спрашивается по каждому файлу и
    каждой брошюре, «собери брошюру» — по каждой брошюре. Условие выхода из
    цикла живёт внутри одного шага, а не размазано по двум функциям, как
    было раньше (из-за чего диалог о брошюрах и зависал).
    """


@dataclass(slots=True)
class Jump(Outcome):
    """Явно перейти на конкретный шаг, минуя обычный маршрут."""
    step: str
    value: Any = None


@dataclass(slots=True)
class Stay(Outcome):
    """Шаг всё сделал сам (перерисовал клавиатуру и т.п.) — ничего не менять."""


@dataclass(slots=True)
class Finish(Outcome):
    """Диалог закончен, сессию удалить."""
    reason: str = "finished"


# --------------------------------------------------------------------------
# Сам шаг
# --------------------------------------------------------------------------
class Step(ABC):
    #: идентификатор шага, он же значение session.step
    id: str = ""

    #: какой ввод шаг ожидает: TEXT, CALLBACK или DOCUMENT
    accepts: tuple = (TEXT,)

    #: Начала callback_data, которые принадлежат ЭТОМУ шагу.
    #:
    #: Проверять только тип ввода мало. Пользователь может быстро нажать
    #: кнопку дважды: первое нажатие уже перевело диалог на следующий шаг и
    #: заменило сообщение, а второе прилетает со старой клавиатурой, которую
    #: Telegram ещё показывает. Без этой проверки следующий шаг принимал
    #: чужое нажатие за свой ответ — например, шаг «формат» получал
    #: «color_bw», формат оставался пустым, и заказ выходил на 0 рублей.
    buttons: tuple = ()

    def owns(self, data: str) -> bool:
        """Наша ли это кнопка. Пустой buttons = шаг без кнопок."""
        if not self.buttons:
            return True
        return any(data.startswith(prefix) for prefix in self.buttons)

    async def on_enter(self, ctx: Ctx) -> None:
        """Подготовка при входе на шаг: собрать очередь, обнулить счётчики.

        Вызывается один раз при переходе НА шаг, до первого ask().
        При Repeat() не вызывается — цикл должен видеть свой прогресс.
        """

    @abstractmethod
    async def ask(self, ctx: Ctx) -> None:
        """Задать вопрос пользователю."""

    @abstractmethod
    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        """Разобрать ответ, записать его в заказ и сказать, что дальше."""
