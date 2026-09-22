# ==========================================================================
# Проверки текстов. Именно они не дают вернуться багам «смешение языков»
# (баг-репорт п.4, п.6) и «английская версия молчит» (п.7).
#
# Запуск:  cd printbot && python -m pytest tests -q
# ==========================================================================

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from texts.en import TEXTS_EN  # noqa: E402
from texts.ru import TEXTS_RU  # noqa: E402

PLACEHOLDER = re.compile(r"\{(\w+)\}")


def test_same_keys():
    """Каждый ключ есть в обоих языках."""
    only_ru = set(TEXTS_RU) - set(TEXTS_EN)
    only_en = set(TEXTS_EN) - set(TEXTS_RU)
    assert not only_ru, f"нет английского перевода: {sorted(only_ru)}"
    assert not only_en, f"нет русского перевода: {sorted(only_en)}"


def test_same_placeholders():
    """Набор {подстановок} совпадает — иначе текст упадёт при форматировании
    ровно на одном языке, что крайне трудно заметить."""
    for key in TEXTS_RU:
        ru = set(PLACEHOLDER.findall(TEXTS_RU[key]))
        en = set(PLACEHOLDER.findall(TEXTS_EN[key]))
        assert ru == en, f"ключ {key!r}: подстановки RU={sorted(ru)} EN={sorted(en)}"


def test_no_russian_text_inside_steps():
    """В шагах не должно быть русских строк, которые увидит пользователь:
    любой такой текст обязан идти через ctx.t(ключ).

    Не считаются нарушением:
      - steps/language.py, где язык ещё не выбран и надпись двуязычная;
      - комментарии и docstring'и;
      - сообщения логов и assert'ов — их читаем только мы.
    """
    cyrillic = re.compile(r"[а-яА-ЯёЁ]")
    # Строки, которые уходят в лог или в исключение, пользователю не видны.
    internal = ("logger.", "assert ", "raise ", "logging.")
    offenders = []

    for path in sorted((ROOT / "steps").glob("*.py")):
        if path.name in ("language.py", "__init__.py"):
            continue

        inside_docstring = False
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()

            if stripped.count('"""') == 1 or stripped.count("'''") == 1:
                inside_docstring = not inside_docstring
                continue
            if inside_docstring or stripped.startswith("#"):
                continue
            if '"""' in stripped or "'''" in stripped:
                continue

            code = stripped.split("#", 1)[0]
            if not ('"' in code or "'" in code):
                continue
            if any(marker in code for marker in internal):
                continue
            if cyrillic.search(code):
                offenders.append(f"{path.name}:{number}: {stripped}")

    assert not offenders, (
        "Русский текст прямо в шаге — используйте ctx.t('ключ'):\n" + "\n".join(offenders)
    )
