# ==========================================================================
# steps/__init__.py — реестр всех шагов.
#
# Добавил новый вопрос? Создай файл рядом, положи в него класс с STEP = ...,
# импортируй здесь и пропиши переход в core/flow.py. Больше нигде ничего
# регистрировать не надо.
# ==========================================================================

from steps import (
    add_file,
    auth,
    brochure_assemble,
    brochure_count,
    brochure_type,
    color_mode,
    confirm,
    copies,
    feedback,
    folding_ask,
    folding_select,
    format as format_step,
    input_color_pages,
    input_pages,
    language,
    operator_chat,
    print_mode,
    ready_time,
    sided,
    wait_file,
)

_ALL = (
    language.STEP,
    auth.STEP,
    wait_file.STEP,
    print_mode.STEP,
    input_pages.STEP,
    color_mode.STEP,
    input_color_pages.STEP,
    format_step.STEP,
    sided.STEP,
    add_file.STEP,
    brochure_count.STEP,
    brochure_assemble.STEP,
    brochure_type.STEP,
    folding_ask.STEP,
    folding_select.STEP,
    copies.STEP,
    ready_time.STEP,
    confirm.STEP,
    operator_chat.STEP,
    feedback.RATING_STEP,
    feedback.COMMENT_STEP,
)

STEPS = {step.id: step for step in _ALL}

assert len(STEPS) == len(_ALL), "Два шага с одинаковым id — проверь поле id"
