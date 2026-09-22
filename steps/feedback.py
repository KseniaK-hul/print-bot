# ==========================================================================
# Шаги отзыва после выдачи заказа (LOGIC.md §3.5).
#
# Баг-репорт п.7: в английской версии диалог намертво вставал после «Rate
# the service from 1 to 10». Причина была не в языке, а в том, что оценка и
# комментарий висели двумя отдельными MessageHandler'ами на одном и том же
# фильтре TEXT — PTB выполнял только первый, второй не срабатывал никогда.
#
# Здесь это просто два обычных шага в общем роутере, поэтому подобная
# коллизия невозможна в принципе.
# ==========================================================================

from admin import panel
from core.ctx import Ctx
from core.step import TEXT, Again, Answer, Finish, Next, Outcome, Step


class FeedbackRatingStep(Step):
    id = "feedback_rating"
    accepts = (TEXT,)

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say("feedback_ask")

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        text = (answer.text or "").strip()
        if not text.isdigit() or not (1 <= int(text) <= 10):
            return Again("feedback_bad_rating")

        ctx.scratch["rating"] = int(text)
        return Next()


class FeedbackCommentStep(Step):
    id = "feedback_comment"
    accepts = (TEXT,)

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say("feedback_comment")

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        comment = (answer.text or "").strip() or "-"
        rating = ctx.scratch.get("rating", "?")

        await panel.notify_feedback(ctx.tg, ctx.user_id, rating, comment)
        # Подсказываем, как оформить следующий заказ — иначе клиент остаётся
        # в тупике и должен сам догадаться про /start (баг-репорт п.2).
        await ctx.say_raw(ctx.t("feedback_thanks") + ctx.t("order_again"))
        return Finish("feedback_done")


RATING_STEP = FeedbackRatingStep()
COMMENT_STEP = FeedbackCommentStep()
