# ==========================================================================
# Шаг 19 — итоговая сводка и подтверждение (LOGIC.md §2.9).
#
# После любого исхода добавляем подсказку про /start (баг-репорт п.2) —
# раньше клиент оставался в тупике и должен был сам догадаться.
#
# Само сообщение админу собирается в admin/panel.py: клиентский шаг не
# должен знать, как выглядит админская панель.
# ==========================================================================

from admin import panel
from core.ctx import Ctx
from core.step import CALLBACK, Answer, Finish, Outcome, Step
from core.summary import client_summary
from pricing.calculator import order_total


class ConfirmStep(Step):
    id = "confirm"
    accepts = (CALLBACK,)
    buttons = ("confirm_",)

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say_raw(
            client_summary(ctx.order, ctx.session.lang),
            ctx.kb(("final_confirm", "confirm_yes"), ("final_cancel", "confirm_no")),
        )

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        if answer.data != "confirm_yes":
            await ctx.replace_raw(ctx.t("order_cancelled") + ctx.t("order_again"))
            return Finish("cancelled_by_client")

        total = order_total(ctx.order)
        await panel.notify_new_order(ctx.tg, ctx.user_id, ctx.order)
        await ctx.replace_raw(
            ctx.t("order_confirmed", total=total) + ctx.t("order_again")
        )
        # Finish -> store.drop(): сессия и временные файлы удаляются сразу,
        # заказ в памяти после отправки админу не нужен.
        return Finish("confirmed")


STEP = ConfirmStep()
