# ==========================================================================
# pricing/calculator.py — ВСЕ деньги считаются здесь и только здесь.
#
# Ни одна функция в этом файле не знает про Telegram, сессии и шаги: на вход
# модели из core/models.py, на выход числа. Если цена посчиталась неправильно —
# баг здесь, и его можно воспроизвести обычным тестом за секунду.
# ==========================================================================

from config import (
    AUTO_FOLD_BROCHURE_FILES_IS_PAID,
    BROCHURE_A3_BASE,
    BROCHURE_A3_FREE_PAGES,
    BROCHURE_A3_PAGE_PRICE,
    BROCHURE_A4_BASE,
    BROCHURE_A4_PAGES_PER_STEP,
    BROCHURE_A4_STEP_PRICE,
    BROCHURE_BIG_FLAT,
    EXPRESS_MULTIPLIER,
    FOLDING_PRICES,
    PRICES_BW,
    PRICES_COLOR,
)
from core.models import BrochureProject, Order, PrintFile


def file_price(f: PrintFile) -> int:
    """Цена печати ОДНОГО экземпляра файла."""
    if not f.format:
        return 0
    return (
        f.color_pages * PRICES_COLOR[f.format]
        + f.bw_pages * PRICES_BW[f.format]
    )


def folding_price(f: PrintFile) -> int:
    return FOLDING_PRICES.get(f.format or "", 0)


def brochure_price(order: Order, project: BrochureProject) -> int:
    """Цена ОДНОГО экземпляра брошюры.

    Формат берём по первому файлу брошюры: листы одной брошюры сшиваются
    вместе, значит формат у них общий.
    """
    if not project.file_indices:
        return 0

    fmt = order.files[project.file_indices[0]].format
    pages = sum(order.files[i].pages_to_print for i in project.file_indices)

    if fmt == "A4":
        if pages <= BROCHURE_A4_PAGES_PER_STEP:
            return BROCHURE_A4_BASE
        extra = pages - BROCHURE_A4_PAGES_PER_STEP
        steps = -(-extra // BROCHURE_A4_PAGES_PER_STEP)   # округление вверх
        return BROCHURE_A4_BASE + steps * BROCHURE_A4_STEP_PRICE

    if fmt == "A3":
        return BROCHURE_A3_BASE + max(0, pages - BROCHURE_A3_FREE_PAGES) * BROCHURE_A3_PAGE_PRICE

    if fmt in ("A0", "A1", "A2"):
        return BROCHURE_BIG_FLAT

    return 0


def paid_folded_files(order: Order) -> list:
    """Файлы, за складывание которых реально берём деньги.

    Отдельные чертежи — всегда платно. Чертежи внутри брошюры складываются
    автоматически, и платно это или нет — решает флаг в config.py
    (открытый вопрос к заказчику, см. LOGIC.md §7).
    """
    result = [f for _, f in order.standalone_big_format_files() if f.needs_folding]
    if AUTO_FOLD_BROCHURE_FILES_IS_PAID:
        for i in sorted(order.brochure_file_indices()):
            if order.files[i].is_big_format():
                result.append(order.files[i])
    return result


def folding_total(order: Order) -> int:
    return sum(folding_price(f) for f in paid_folded_files(order))


def printing_total(order: Order) -> int:
    return sum(file_price(f) * f.copies for f in order.files)


def brochures_total(order: Order) -> int:
    return sum(brochure_price(order, p) * p.copies for p in order.brochures)


def order_total(order: Order) -> int:
    """Итоговая сумма заказа с учётом наценки за срочность."""
    total = printing_total(order) + folding_total(order) + brochures_total(order)
    if order.is_express:
        total = int(total * EXPRESS_MULTIPLIER)
    return total
