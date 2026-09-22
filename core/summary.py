# ==========================================================================
# core/summary.py — сборка текстов заказа: для клиента и для админа.
#
# Здесь живёт исправление главного бага (баг-репорт п.1): админу теперь
# уходят КОНКРЕТНЫЕ номера страниц — что печатать и что из этого цветное, —
# а не только их количество. Без этого физически нельзя выполнить заказ, где
# человек попросил «страницы 1-3,5,7-9, из них цветные 5 и 8».
# ==========================================================================

from __future__ import annotations

from config import EXPRESS_MARKUP_PERCENT
from core.models import Order
from pricing.calculator import (
    brochure_price,
    file_price,
    folding_price,
    folding_total,
    order_total,
    paid_folded_files,
)
from texts import LANG_RU, translate


def _pages_block(order: Order, f, lang: str) -> str:
    """Строки с точными номерами страниц. Показываем только то, что
    действительно нужно: если печатаем всё и всё ЧБ — лишних строк нет."""
    t = lambda key, **kw: translate(lang, key, **kw)  # noqa: E731
    all_label = t("pages_all")
    none_label = t("pages_none")
    block = ""

    if f.pages.ranges is not None:
        block += t("summary_pages_print", pages=f.pages.render(all_label, none_label))

    if f.color_pages and f.bw_pages:
        # смешанный файл — админу нужны обе раскладки
        block += t("summary_pages_color", pages=f.color.render(all_label, none_label))
        block += t(
            "summary_pages_bw",
            pages=f.bw_selection.render(all_label, none_label),
        )
    elif f.color_pages and not f.bw_pages:
        block += t("summary_pages_color", pages=all_label)
    return block


def client_summary(order: Order, lang: str) -> str:
    """Итоговая сводка, которую видит клиент перед подтверждением."""
    t = lambda key, **kw: translate(lang, key, **kw)  # noqa: E731

    out = t("order_summary_header") + "\n"

    for i, f in enumerate(order.files, 1):
        out += t(
            "order_summary_file",
            num=i,
            name=f.name,
            format=f.format,
            sided=t("sided_double" if f.sided == "d" else "sided_single"),
            color=f.color_pages,
            bw=f.bw_pages,
            copies=f.copies,
            price=file_price(f) * f.copies,
        )
        out += _pages_block(order, f, lang)

    for i, project in enumerate(order.brochures, 1):
        out += t(
            "order_summary_brochure",
            num=i,
            type=t(project.binding),          # «🔄 Пружинка», а не 'spring'
            file_count=len(project.file_indices),
            copies=project.copies,
            price=brochure_price(order, project) * project.copies,
        )

    folding = folding_total(order)
    if folding:
        out += t("order_summary_folding", price=folding)

    # Наценка за срочность заложена в итог — говорим, откуда она взялась.
    if order.is_express:
        out += t("order_summary_express", markup=EXPRESS_MARKUP_PERCENT)

    out += t(
        "order_summary_total",
        total=order_total(order),
        ready_time=t(order.ready_time) if order.ready_time else "-",
    )
    return out


# --------------------------------------------------------------------------
# Сообщение админу.
#
# Админ-панель намеренно всегда на русском: это внутренний интерфейс одной
# печатной мастерской, а не клиентский. Переводимыми остаются только те
# куски, которые пришли из выбора клиента (тип переплёта, срок).
# --------------------------------------------------------------------------
def admin_report(order: Order, client_id: int) -> str:
    t = lambda key, **kw: translate(LANG_RU, key, **kw)  # noqa: E731

    ready = t(order.ready_time) if order.ready_time else "-"
    out = (
        f"🆕 НОВЫЙ ЗАКАЗ!\n"
        f"👤 Клиент: {order.user_info}\n"
        f"🆔 ID: {client_id}\n"
        f"⏱ Готовность: {ready}\n\n"
        f"🖨 ПЕЧАТЬ:\n"
    )

    for i, f in enumerate(order.files, 1):
        side = "Односторонняя" if f.sided == "s" else "Двусторонняя"
        out += f"Файл #{i}: {f.name}\n"
        out += f"  {f.format}, {side}, копий: {f.copies}\n"
        out += f"  Страниц в печать: {f.pages_to_print} (цв: {f.color_pages}, чб: {f.bw_pages})\n"
        out += _pages_block(order, f, LANG_RU)

    if order.brochures:
        out += "\n📚 БРОШЮРЫ:\n"
        for i, project in enumerate(order.brochures, 1):
            out += f"Брошюра #{i} ({t(project.binding)}) — {project.copies} экз.:\n"
            for index in project.file_indices:
                f = order.files[index]
                out += f"  - {f.name} ({f.format})\n"

    folded = order.folded_files()
    if folded:
        out += "\n📐 СКЛАДЫВАНИЕ:\n"
        paid = paid_folded_files(order)
        for f in folded:
            mark = f"{folding_price(f)} руб." if f in paid else "в составе брошюры"
            out += f"  - {f.name} ({f.format}) — {mark}\n"

    out += f"\n💵 ИТОГО: {order_total(order)} руб."
    return out
