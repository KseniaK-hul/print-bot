# ==========================================================================
# Проверки маршрута диалога — тоже без Telegram.
#
# Ловят класс багов «бот увёл не туда» и «диалог упёрся в несуществующий
# шаг» ещё до запуска.
#
# Запуск:  cd printbot && python -m pytest tests -q
# ==========================================================================

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.flow import FLOW, resolve  # noqa: E402
from core.models import BrochureProject, PrintFile  # noqa: E402
from core.session import Session  # noqa: E402
from steps import STEPS  # noqa: E402


def make_session(step: str = "language") -> Session:
    return Session(user_id=1, step=step)


def test_every_step_has_a_route():
    """У каждого шага описан переход — иначе диалог молча упрётся в тупик."""
    missing = sorted(set(STEPS) - set(FLOW))
    assert not missing, f"нет маршрута для шагов: {missing}"


def test_every_route_points_to_existing_step():
    """Статические переходы ведут на существующие шаги (опечатку в id
    иначе можно поймать только вживую)."""
    for step_id, route in FLOW.items():
        if route is None or callable(route):
            continue
        assert route in STEPS, f"{step_id} -> несуществующий шаг {route!r}"


def test_a4_asks_about_sides_and_others_do_not():
    session = make_session("format")
    assert resolve(session, "format", "A4") == "sided"
    assert resolve(session, "format", "A1") == "add_file"


def test_add_file_loops_back_for_another_file():
    session = make_session("add_file")
    assert resolve(session, "add_file", "more") == "wait_file"
    assert resolve(session, "add_file", "done") == "brochure_count"


def test_folding_question_skipped_when_nothing_to_fold():
    """Заказ из одних A4 — вопрос про складывание не должен появляться."""
    session = make_session("brochure_count")
    session.order.files.append(PrintFile(path="", name="a.pdf", total_pages=1, format="A4"))
    assert resolve(session, "brochure_count", 0) == "copies"


def test_folding_question_asked_for_standalone_drawing():
    session = make_session("brochure_count")
    session.order.files.append(PrintFile(path="", name="a.pdf", total_pages=1, format="A1"))
    assert resolve(session, "brochure_count", 0) == "folding_ask"


def test_folding_skipped_when_drawing_is_inside_brochure():
    """Чертёж внутри брошюры складывается автоматически — спрашивать нечего."""
    session = make_session("brochure_type")
    session.order.files.append(PrintFile(path="", name="a.pdf", total_pages=1, format="A1"))
    session.order.brochures.append(BrochureProject(file_indices=[0], binding="spring"))
    session.scratch["brochure"] = {"planned": 1, "current": 2, "picked": []}
    assert resolve(session, "brochure_type", None) == "copies"


def test_brochure_loop_stops_when_files_run_out():
    """Заявили 2 брошюры, а файл был один: после первой брошюры цикл
    обязан закончиться, а не крутиться дальше (тот самый зависон)."""
    session = make_session("brochure_type")
    session.order.files.append(PrintFile(path="", name="a.pdf", total_pages=1, format="A4"))
    session.order.brochures.append(BrochureProject(file_indices=[0], binding="spring"))
    session.scratch["brochure"] = {"planned": 2, "current": 2, "picked": []}

    assert resolve(session, "brochure_type", None) == "copies"


def test_brochure_loop_continues_while_files_remain():
    session = make_session("brochure_type")
    session.order.files.append(PrintFile(path="", name="a.pdf", total_pages=1, format="A4"))
    session.order.files.append(PrintFile(path="", name="b.pdf", total_pages=1, format="A4"))
    session.order.brochures.append(BrochureProject(file_indices=[0], binding="spring"))
    session.scratch["brochure"] = {"planned": 2, "current": 2, "picked": []}

    assert resolve(session, "brochure_type", None) == "brochure_assemble"


def test_full_happy_path_reaches_confirm():
    """Проходим весь линейный маршрут и убеждаемся, что он приводит к
    подтверждению, а не теряется по дороге."""
    session = make_session()
    session.order.files.append(PrintFile(path="", name="a.pdf", total_pages=5, format="A4"))

    step = "language"
    values = {
        "print_mode": "all",
        "color_mode": "bw",
        "format": "A4",
        "add_file": "done",
        "brochure_count": 0,
    }

    visited = []
    for _ in range(30):
        visited.append(step)
        if step == "confirm":
            break
        step = resolve(session, step, values.get(step))
        assert step is not None, f"маршрут оборвался на {visited[-1]}"

    assert visited[-1] == "confirm", f"дошли только до {visited}"
    assert "sided" in visited          # A4 обязан спросить про сторонность
    assert "folding_ask" not in visited  # складывать нечего
