# ==========================================================================
# tasks/monitor.py — сколько ресурсов сервера занимает бот.
#
# Пишет в лог строку вида:
#   НАГРУЗКА [drop uid=123 confirmed] | память 98.4 МБ | CPU 0.5% |
#   сессий 1 (≈4.1 КБ) | временные PDF: 1 шт., 2.30 МБ
#
# Как читать:
#   - «память» — сколько процесс реально занимает на сервере (RSS). От числа
#     пользователей почти не зависит: сессия весит килобайты, а сам Python с
#     библиотеками ~100 МБ. После очистки RSS обычно НЕ падает назад —
#     Python не спешит отдавать освобождённую память системе. Это не утечка.
#   - «сессий (≈N КБ)» — точный вес самих заказов в памяти. Здесь очистка
#     видна сразу: после удаления сессии число уменьшается.
#   - «временные PDF» — скачанные файлы на диске. Здесь очистка видна лучше
#     всего: файлы исчезают после заказа, отмены или таймаута.
# ==========================================================================

from __future__ import annotations

import os
import sys

from config import TEMP_DIR_PREFIX, logger

try:
    import psutil

    _process = psutil.Process()
    _process.cpu_percent(None)   # первый вызов всегда 0 — «заряжаем» замер
except ImportError:              # бот не должен падать из-за мониторинга
    _process = None
    logger.warning("psutil не установлен — память и CPU в логах показаны не будут")


def _deep_size(obj, seen: set) -> int:
    """Примерный вес объекта со всем, что внутри (списки, словари, поля
    dataclass'ов). sys.getsizeof считает только «оболочку», без содержимого."""
    if id(obj) in seen:
        return 0
    seen.add(id(obj))

    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        size += sum(_deep_size(k, seen) + _deep_size(v, seen) for k, v in obj.items())
    elif isinstance(obj, (list, tuple, set, frozenset)):
        size += sum(_deep_size(item, seen) for item in obj)
    elif hasattr(obj, "__slots__"):
        size += sum(
            _deep_size(getattr(obj, name), seen)
            for name in obj.__slots__
            if hasattr(obj, name)
        )
    elif hasattr(obj, "__dict__"):
        size += _deep_size(vars(obj), seen)
    return size


def _temp_files() -> tuple[int, int]:
    """(количество, байты) скачанных PDF во временных папках."""
    count = size = 0
    try:
        names = os.listdir(".")
    except OSError:
        return 0, 0
    for name in names:
        if not name.startswith(TEMP_DIR_PREFIX) or not os.path.isdir(name):
            continue
        for root, _, files in os.walk(name):
            for file_name in files:
                try:
                    size += os.path.getsize(os.path.join(root, file_name))
                    count += 1
                except OSError:
                    pass
    return count, size


def snapshot(sessions: dict) -> str:
    parts = []
    if _process is not None:
        rss_mb = _process.memory_info().rss / 1024 / 1024
        parts.append(f"память {rss_mb:.1f} МБ")
        parts.append(f"CPU {_process.cpu_percent(None):.1f}%")

    sessions_kb = _deep_size(list(sessions.values()), set()) / 1024 if sessions else 0
    parts.append(f"сессий {len(sessions)} (≈{sessions_kb:.1f} КБ)")

    files, disk = _temp_files()
    parts.append(f"временные PDF: {files} шт., {disk / 1024 / 1024:.2f} МБ")
    return " | ".join(parts)


def log_snapshot(sessions: dict, event: str = "") -> None:
    label = f"[{event}] " if event else ""
    logger.info("НАГРУЗКА %s| %s", label, snapshot(sessions))


async def periodic(context) -> None:
    """Фоновая запись в лог раз в MONITOR_INTERVAL_SEC секунд."""
    from core.store import store   # здесь, а не наверху: store сам импортирует monitor

    log_snapshot(store.sessions(), "плановый замер")
