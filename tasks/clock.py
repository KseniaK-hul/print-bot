# ==========================================================================
# tasks/clock.py — рабочие часы.
# ==========================================================================

import datetime

from config import (
    FORCE_BUSINESS_HOURS,
    MSK_UTC_OFFSET_HOURS,
    WORK_DAYS,
    WORK_HOUR_FROM,
    WORK_HOUR_TO,
)


def is_business_hours() -> bool:
    if FORCE_BUSINESS_HOURS:
        # Локальная отладка: позволяет пройти сценарий вечером или в выходной.
        # В проде переменную FORCE_BUSINESS_HOURS не задавать.
        return True

    now_msk = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        hours=MSK_UTC_OFFSET_HOURS
    )
    return now_msk.weekday() in WORK_DAYS and WORK_HOUR_FROM <= now_msk.hour < WORK_HOUR_TO
