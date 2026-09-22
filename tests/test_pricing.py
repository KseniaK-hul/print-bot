# ==========================================================================
# Проверки денег и выборки страниц — БЕЗ запуска бота.
#
# Именно ради этого расчёты вынесены в pricing/ и не знают про Telegram:
# сложный заказ из ТЗ §3.1 проверяется за долю секунды, а не десятью
# нажатиями кнопок в чате.
#
# Запуск:  cd printbot && python -m pytest tests -q
# ==========================================================================

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.models import BrochureProject, Order, PageSelection, PrintFile  # noqa: E402
from pricing.calculator import (  # noqa: E402
    brochure_price,
    file_price,
    folding_total,
    order_total,
)


# --------------------------------------------------------------------------
# Диапазоны страниц
# --------------------------------------------------------------------------
def test_parse_and_render_roundtrip():
    selection = PageSelection.parse("1-3,5,7-9", 10)
    assert selection.render() == "1-3,5,7-9"
    assert selection.count(10) == 7


def test_parse_merges_touching_ranges():
    assert PageSelection.parse("1-3,4-5", 10).render() == "1-5"


def test_parse_rejects_garbage():
    for bad in ("0", "5-3", "11", "abc", ""):
        try:
            PageSelection.parse(bad, 10)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} должен был быть отклонён")


def test_color_intersects_with_printed_pages():
    """Печатаем 1-10, цветными названы 5-20 — цветными станут только 5-10."""
    f = PrintFile(path="", name="x.pdf", total_pages=20)
    f.pages = PageSelection.parse("1-10", 20)
    requested = PageSelection.parse("5-20", 20)
    f.color = requested.intersect(f.pages, 20)

    assert f.color.render() == "5-10"
    assert f.color_pages == 6
    assert f.bw_pages == 4
    assert f.bw_selection.render() == "1-4"


# --------------------------------------------------------------------------
# Цены
# --------------------------------------------------------------------------
def test_file_price_mixed_color():
    f = PrintFile(path="", name="x.pdf", total_pages=10, format="A4")
    f.pages = PageSelection.all_pages()
    f.color = PageSelection.parse("1-3", 10)
    # 3 цветных по 60 + 7 ЧБ по 18
    assert file_price(f) == 3 * 60 + 7 * 18


def test_brochure_price_a4_steps():
    order = Order()
    f = PrintFile(path="", name="b.pdf", total_pages=25, format="A4")
    order.files.append(f)
    project = BrochureProject(file_indices=[0], binding="spring")
    # 25 страниц: 150 за первые 20 + 50 за следующую неполную двадцатку
    assert brochure_price(order, project) == 200


def test_complex_order_from_spec():
    """Сценарий из ТЗ §3.1: A4 с частичным цветом + A1 целиком цветной
    со складыванием + одна брошюра, и всё это экспрессом."""
    order = Order(user_info="Иванов Иван Иванович, ИКГ-01-20")

    a4 = PrintFile(path="", name="doc.pdf", total_pages=10, format="A4", sided="s", copies=2)
    a4.pages = PageSelection.all_pages()
    a4.color = PageSelection.parse("1-2", 10)

    a1 = PrintFile(path="", name="draw.pdf", total_pages=1, format="A1", sided="s", copies=1)
    a1.pages = PageSelection.all_pages()
    a1.color = PageSelection.parse("1", 1)
    a1.needs_folding = True

    order.files.extend([a4, a1])
    order.brochures.append(BrochureProject(file_indices=[0], binding="spring", copies=3))

    # печать: (2*60 + 8*18) * 2 копии + (1*500) * 1
    printing = (2 * 60 + 8 * 18) * 2 + 500
    # A1 в брошюру не входит и выбран для складывания -> 50 руб.
    assert folding_total(order) == 50
    # брошюра из A4 на 10 страниц: 150, три экземпляра
    brochures = 150 * 3

    expected = int((printing + 50 + brochures) * 1.3)
    order.is_express = True
    assert order_total(order) == expected


def test_folding_not_charged_for_a4():
    order = Order()
    f = PrintFile(path="", name="x.pdf", total_pages=1, format="A4", needs_folding=True)
    order.files.append(f)
    # A4 не складывается — в выборку крупных форматов он не попадает
    assert folding_total(order) == 0


def test_standalone_big_format_excludes_brochure_files():
    order = Order()
    order.files.append(PrintFile(path="", name="a.pdf", total_pages=1, format="A1"))
    order.files.append(PrintFile(path="", name="b.pdf", total_pages=1, format="A1"))
    order.brochures.append(BrochureProject(file_indices=[0], binding="spring"))

    standalone = order.standalone_big_format_files()
    assert [name for _, f in standalone for name in [f.name]] == ["b.pdf"]
