# ==========================================================================
# core/models.py — данные заказа. Ни одной строчки про Telegram.
#
# Всё здесь можно создать и проверить в обычном тесте, без запуска бота —
# см. tests/test_pricing.py.
# ==========================================================================

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from config import BIG_FORMATS, logger


# ==========================================================================
# Выбор страниц
# ==========================================================================
@dataclass(slots=True)
class PageSelection:
    """Набор страниц, заданный диапазонами: [(1,3), (5,5), (7,9)].

    Почему диапазоны, а не список номеров:
      1) память — 500-страничный документ это 3 кортежа вместо 500 int'ов;
      2) админу нужно показать ИМЕННО "1-3,5,7-9" (баг-репорт п.1), а из
         развёрнутого списка эту запись пришлось бы собирать обратно.

    ranges = None означает "все страницы документа".
    """

    ranges: Optional[list] = None

    @classmethod
    def all_pages(cls) -> "PageSelection":
        return cls(ranges=None)

    @classmethod
    def parse(cls, text: str, max_page: int) -> "PageSelection":
        """'1,3,5-7' -> PageSelection([(1,1),(3,3),(5,7)]).

        Бросает ValueError на любом некорректном вводе — единая точка
        валидации, шагам остаётся только поймать исключение.
        """
        result: list = []
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                left, _, right = part.partition("-")
                start, end = int(left.strip()), int(right.strip())
            else:
                start = end = int(part)
            if start < 1 or end > max_page or start > end:
                raise ValueError(f"Некорректный диапазон: {part!r}")
            result.append((start, end))

        if not result:
            raise ValueError("Пустой список страниц")
        return cls(ranges=cls._merge(result))

    @staticmethod
    def _merge(ranges: list) -> list:
        """Склеивает пересекающиеся и соседние диапазоны: (1,3)+(4,5) -> (1,5)."""
        merged: list = []
        for start, end in sorted(ranges):
            if merged and start <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    def count(self, total_pages: int) -> int:
        if self.ranges is None:
            return total_pages
        return sum(end - start + 1 for start, end in self.ranges)

    def contains(self, page: int) -> bool:
        if self.ranges is None:
            return True
        return any(start <= page <= end for start, end in self.ranges)

    def to_list(self, total_pages: int) -> list:
        if self.ranges is None:
            return list(range(1, total_pages + 1))
        pages: list = []
        for start, end in self.ranges:
            pages.extend(range(start, end + 1))
        return pages

    def intersect(self, other: "PageSelection", total_pages: int) -> "PageSelection":
        """Пересечение двух наборов — нужно, когда пользователь просит печатать
        страницы 1-10, а цветными указывает 5-20: цветными станут только 5-10."""
        mine = set(self.to_list(total_pages))
        theirs = set(other.to_list(total_pages))
        common = sorted(mine & theirs)
        if not common:
            return PageSelection(ranges=[])
        return PageSelection(ranges=self._merge([(p, p) for p in common]))

    def subtract(self, other: "PageSelection", total_pages: int) -> "PageSelection":
        """Разность — 'какие страницы остаются ЧБ, если эти цветные'."""
        mine = set(self.to_list(total_pages))
        theirs = set(other.to_list(total_pages))
        rest = sorted(mine - theirs)
        if not rest:
            return PageSelection(ranges=[])
        return PageSelection(ranges=self._merge([(p, p) for p in rest]))

    def render(self, all_label: str = "все", empty_label: str = "—") -> str:
        """'1-3,5,7-9' — то, что видит админ."""
        if self.ranges is None:
            return all_label
        if not self.ranges:
            return empty_label
        return ",".join(
            str(start) if start == end else f"{start}-{end}"
            for start, end in self.ranges
        )


# ==========================================================================
# Файл
# ==========================================================================
@dataclass(slots=True)
class PrintFile:
    path: str
    name: str
    total_pages: int

    # что печатаем
    pages: PageSelection = field(default_factory=PageSelection.all_pages)
    # какие из печатаемых страниц цветные (остальные ЧБ)
    color: PageSelection = field(default_factory=lambda: PageSelection(ranges=[]))

    format: Optional[str] = None      # 'A4' / 'A3' / 'A2' / 'A1' / 'A0'
    sided: Optional[str] = None       # 's' | 'd' (двусторонняя — только A4)
    copies: int = 1
    needs_folding: bool = False       # выбрано пользователем (для файлов ВНЕ брошюры)

    @property
    def pages_to_print(self) -> int:
        return self.pages.count(self.total_pages)

    @property
    def color_pages(self) -> int:
        return self.color.count(self.total_pages)

    @property
    def bw_pages(self) -> int:
        return self.pages_to_print - self.color_pages

    @property
    def bw_selection(self) -> PageSelection:
        return self.pages.subtract(self.color, self.total_pages)

    def is_big_format(self) -> bool:
        return self.format in BIG_FORMATS


# ==========================================================================
# Брошюра
# ==========================================================================
@dataclass(slots=True)
class BrochureProject:
    file_indices: list           # индексы файлов в Order.files, в порядке сборки
    binding: str                 # 'spring' | 'string' — это КЛЮЧ ТЕКСТА, не готовая строка
    copies: int = 1


# ==========================================================================
# Заказ
# ==========================================================================
@dataclass(slots=True)
class Order:
    user_info: str = ""
    files: list = field(default_factory=list)       # list[PrintFile]
    brochures: list = field(default_factory=list)   # list[BrochureProject]
    ready_time: Optional[str] = None                # ключ текста: 'time_1h' и т.п.
    is_express: bool = False

    # ---- выборки ----
    @property
    def current_file(self) -> PrintFile:
        """Файл, который пользователь настраивает прямо сейчас."""
        return self.files[-1]

    def brochure_file_indices(self) -> set:
        used = set()
        for project in self.brochures:
            used.update(project.file_indices)
        return used

    def standalone_files(self) -> list:
        """[(индекс, файл)] — файлы, не попавшие ни в одну брошюру."""
        used = self.brochure_file_indices()
        return [(i, f) for i, f in enumerate(self.files) if i not in used]

    def standalone_big_format_files(self) -> list:
        """Отдельные чертежи большого формата — только для них спрашиваем
        про складывание (LOGIC.md §2.6)."""
        return [(i, f) for i, f in self.standalone_files() if f.is_big_format()]

    def free_file_indices(self) -> list:
        """Индексы файлов, ещё не отданных ни в одну брошюру."""
        used = self.brochure_file_indices()
        return [i for i in range(len(self.files)) if i not in used]

    def folded_files(self) -> list:
        """Что физически будет сложено — для инструкции админу.

        Это отдельные чертежи, выбранные пользователем, ПЛЮС все чертежи
        внутри брошюр (они складываются автоматически как часть переплёта).
        """
        result = [f for _, f in self.standalone_big_format_files() if f.needs_folding]
        for i in sorted(self.brochure_file_indices()):
            if self.files[i].is_big_format():
                result.append(self.files[i])
        return result

    # ---- уборка ----
    def cleanup_files(self) -> None:
        """Удаляет скачанные PDF и опустевшую временную папку.

        Единственное место в проекте, которое трогает временные файлы на
        диске. Вызывается только из SessionStore.drop() — поэтому «забыть
        подчистить на каком-то из путей» стало невозможно.
        """
        directories = set()
        for f in self.files:
            if not f.path:
                continue
            directories.add(os.path.dirname(f.path))
            try:
                if os.path.exists(f.path):
                    os.remove(f.path)
            except OSError as e:
                logger.warning("Не удалось удалить файл %s: %s", f.path, e)

        for directory in directories:
            try:
                if directory and os.path.isdir(directory) and not os.listdir(directory):
                    os.rmdir(directory)
            except OSError as e:
                logger.warning("Не удалось удалить папку %s: %s", directory, e)
