# ==========================================================================
# Шаг 1 — выбор языка (LOGIC.md §2.1).
#
# Единственный шаг, где текст написан прямо в коде: язык ещё не выбран, и
# показать надо оба варианта сразу. Дальше всё идёт только через ctx.t().
# ==========================================================================

from core.ctx import Ctx
from core.step import CALLBACK, Answer, Next, Outcome, Step
from core.store import store
from texts import LANG_EN, LANG_RU


class LanguageStep(Step):
    id = "language"
    accepts = (CALLBACK,)
    buttons = ("set_lang_",)

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say_raw(
            "🌍 Выберите язык / Choose language:",
            ctx.raw_kb(
                ("🇷🇺 Русский", "set_lang_ru"),
                ("🇬🇧 English", "set_lang_en"),
            ),
        )

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        lang = LANG_EN if answer.data == "set_lang_en" else LANG_RU
        # set_lang запоминает язык и в сессии, и в кэше — если человек вернётся
        # завтра, спрашивать снова не придётся.
        store.set_lang(ctx.user_id, lang)
        return Next()


STEP = LanguageStep()
