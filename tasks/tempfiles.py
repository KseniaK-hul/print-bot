# ==========================================================================
# tasks/tempfiles.py — уборка временных папок, оставшихся от прошлых запусков.
#
# Если процесс упал или был перезапущен посреди диалога, скачанные PDF
# остаются на диске навсегда. На маленьком сервере это медленно забивает
# место и выглядит как «бот со временем перестаёт работать».
# ==========================================================================

import os
import shutil
import time

from config import STALE_TEMP_HOURS, TEMP_DIR_PREFIX, logger


def sweep_stale_dirs() -> int:
    """Сносит папки TEMP_DIR_PREFIX*, которым больше STALE_TEMP_HOURS часов.
    Вызывается один раз при старте бота."""
    now = time.time()
    removed = 0

    try:
        entries = os.listdir(".")
    except OSError as e:
        logger.warning("не удалось прочитать рабочую папку: %s", e)
        return 0

    for name in entries:
        if not name.startswith(TEMP_DIR_PREFIX) or not os.path.isdir(name):
            continue
        try:
            age_hours = (now - os.path.getmtime(name)) / 3600
            if age_hours > STALE_TEMP_HOURS:
                shutil.rmtree(name, ignore_errors=True)
                removed += 1
        except OSError as e:
            logger.warning("не удалось убрать %s: %s", name, e)

    if removed:
        logger.info("при старте удалено устаревших временных папок: %d", removed)
    return removed
