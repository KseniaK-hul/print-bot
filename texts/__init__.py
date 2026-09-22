# ==========================================================================
# texts/__init__.py — единственная точка получения текста.
#
# ГЛАВНОЕ ПРАВИЛО ПРОЕКТА: язык передаётся АРГУМЕНТОМ, а не берётся из
# глобального словаря по user_id. Благодаря этому любая функция — включая
# фоновую задачу, которая пишет пользователю через 15 минут, — физически
# не может ошибиться с языком: она берёт session.lang.
#
# Из шагов (steps/) эту функцию напрямую не зовут — там есть ctx.t(key),
# который сам подставляет язык текущей сессии.
# ==========================================================================

from config import logger
from .en import TEXTS_EN
from .ru import TEXTS_RU

LANG_RU = "ru"
LANG_EN = "en"
DEFAULT_LANG = LANG_RU

_TABLES = {LANG_RU: TEXTS_RU, LANG_EN: TEXTS_EN}


def translate(lang: str, key: str, **kwargs) -> str:
    """Возвращает текст по ключу на нужном языке.

    Если ключа нет в выбранном языке — падаем на русский, а не на сырой ключ,
    чтобы пользователь никогда не увидел строку вида 'brochure_saved'.
    """
    table = _TABLES.get(lang, TEXTS_RU)
    text = table.get(key)
    if text is None:
        text = TEXTS_RU.get(key)
        if text is None:
            logger.error("Нет текста для ключа %r (язык %r)", key, lang)
            return key
        logger.warning("Ключ %r отсутствует в языке %r — показан русский текст", key, lang)

    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError as e:
            logger.error("В тексте %r не хватает подстановки %s", key, e)
    return text


def all_keys() -> set:
    return set(TEXTS_RU) | set(TEXTS_EN)
