# ==========================================================================
# Шаг 2 — авторизация: ФИО + ИКГ (LOGIC.md §2.2).
#
# ВНИМАНИЕ, ОТКРЫТЫЙ ВОПРОС К ЗАКАЗЧИКУ: точного критерия «настоящего имени»
# нам не дали. Баг-репорт п.9 жалуется, что строка "sda" проходила проверку,
# поэтому здесь стоит минимальная защита от очевидного мусора — не меньше
# двух слов и не короче AUTH_MIN_LENGTH символов.
#
# Когда заказчик скажет точное правило (регулярка на «Фамилия Имя Отчество,
# ИКГ-XX-XX»? сверка со списком групп?) — менять надо ТОЛЬКО функцию
# looks_like_real_name ниже, остальной сценарий не трогается.
# ==========================================================================

from config import AUTH_MIN_LENGTH, AUTH_MIN_WORDS
from core.ctx import Ctx
from core.step import TEXT, Again, Answer, Next, Outcome, Step


def looks_like_real_name(text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) < AUTH_MIN_LENGTH:
        return False
    if len(cleaned.split()) < AUTH_MIN_WORDS:
        return False
    # хотя бы одна буква — чтобы не проходили строки вида "123 456"
    return any(ch.isalpha() for ch in cleaned)


class AuthStep(Step):
    id = "auth"
    accepts = (TEXT,)

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say("greeting")

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        text = (answer.text or "").strip()
        if not looks_like_real_name(text):
            return Again("auth_invalid")

        ctx.order.user_info = text
        return Next()


STEP = AuthStep()
