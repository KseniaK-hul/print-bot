# ==========================================================================
# core/flow.py — КАРТА ВСЕГО ДИАЛОГА. Один экран, который надо открыть,
# чтобы понять «а куда бот пойдёт после этого вопроса».
#
# Шаги сами не решают, куда идти дальше: они возвращают смысл произошедшего
# (Next('A4'), Next('more')), а маршрут описан здесь. Именно поэтому логику
# сценария можно менять, не трогая ни один шаг, и наоборот.
#
# Значение словаря — либо id следующего шага, либо функция
# (session, value) -> id, если переход зависит от заказа.
# ==========================================================================

from core.session import Session

TERMINAL = None   # дальше некуда, сессию закрываем


# --------------------------------------------------------------------------
# Условия переходов — именованные, чтобы карта ниже читалась словами
# --------------------------------------------------------------------------
def after_brochures(session: Session) -> str:
    """Куда идти, когда с брошюрами закончили.

    Вопрос про складывание задаём, ТОЛЬКО если есть отдельные чертежи
    большого формата вне брошюр. Для заказа из одних A4 или когда все
    чертежи уже внутри брошюр (там складывание автоматическое) — вопроса
    быть не должно (ТЗ §2.4.4, §2.6.1).
    """
    if session.order.standalone_big_format_files():
        return "folding_ask"
    return "copies"


def more_brochures_possible(session: Session) -> bool:
    """Есть ли смысл собирать следующую брошюру: и лимит не исчерпан,
    и свободные файлы ещё остались."""
    state = session.scratch.get("brochure")
    if not state:
        return False
    if state["current"] > state["planned"]:
        return False
    return bool(session.order.free_file_indices())


# --------------------------------------------------------------------------
# Сама карта
# --------------------------------------------------------------------------
FLOW = {
    # старт
    "language": "auth",
    "auth": "wait_file",

    # файл и его параметры (цикл: add_file может вернуть обратно на wait_file)
    "wait_file": "print_mode",
    "print_mode": lambda s, v: "input_pages" if v == "specific" else "color_mode",
    "input_pages": "color_mode",
    "color_mode": lambda s, v: "input_color_pages" if v == "specific" else "format",
    "input_color_pages": "format",
    "format": lambda s, v: "sided" if v == "A4" else "add_file",
    "sided": "add_file",
    "add_file": lambda s, v: "wait_file" if v == "more" else "brochure_count",

    # брошюры (цикл по количеству заявленных брошюр)
    "brochure_count": lambda s, v: "brochure_assemble" if v else after_brochures(s),
    "brochure_assemble": "brochure_type",
    "brochure_type": lambda s, v: (
        "brochure_assemble" if more_brochures_possible(s) else after_brochures(s)
    ),

    # складывание (шаги открываются только если есть что складывать)
    "folding_ask": lambda s, v: "folding_select" if v == "yes" else "copies",
    "folding_select": "copies",

    # финал (copies — цикл по файлам и брошюрам внутри самого шага)
    "copies": "ready_time",
    "ready_time": "confirm",
    "confirm": TERMINAL,

    # параллельные ветки
    "operator_chat": TERMINAL,
    "feedback_rating": "feedback_comment",
    "feedback_comment": TERMINAL,
}


def resolve(session: Session, current_step: str, value=None):
    """Вычисляет следующий шаг. Возвращает None, если диалог закончен."""
    route = FLOW.get(current_step, TERMINAL)
    if callable(route):
        return route(session, value)
    return route
