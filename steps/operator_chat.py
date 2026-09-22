# ==========================================================================
# Шаг — переписка с оператором (LOGIC.md §2.10, §3.6).
#
# Баг-репорт п.8: оператор не мог ответить клиенту. Причина — ответ был
# возможен только командой /reply <id> <текст>, о которой надо знать и в
# которой легко ошибиться. Теперь к каждому сообщению клиента админу
# приходит кнопка «Ответить», после нажатия он просто пишет текст.
#
# У режима оператора обязательно должен быть выход. Без него человек, один
# раз согласившийся на оператора, остаётся в этом режиме навсегда: шаг
# возвращает Stay(), то есть сам себя не завершает. Поэтому здесь есть
# кнопка «Завершить разговор» у клиента, такая же кнопка у админа
# (admin/panel.py) и закрытие по молчанию (tasks/janitor.py).
# ==========================================================================

from admin import panel
from core.ctx import Ctx
from core.step import CALLBACK, TEXT, Answer, Finish, Outcome, Stay, Step


class OperatorChatStep(Step):
    id = "operator_chat"
    accepts = (TEXT, CALLBACK)
    buttons = ("op_end",)

    async def ask(self, ctx: Ctx) -> None:
        await ctx.say(
            "operator_transferred",
            ctx.kb(("operator_end_button", "op_end")),
        )

    async def handle(self, ctx: Ctx, answer: Answer) -> Outcome:
        if answer.kind == CALLBACK:
            if answer.data != "op_end":
                return Stay()
            # replace убирает кнопку вместе с текстом — нажать её дважды нельзя
            await ctx.replace("operator_closed")
            await panel.notify_operator_closed(ctx.tg, ctx.user_id, by_admin=False)
            return Finish("operator_closed_by_client")

        await panel.notify_operator_message(ctx.tg, ctx.user_id, answer.text or "")
        await ctx.say("operator_sent")
        # Stay(), а не Repeat(): клиент может писать сколько угодно, но
        # повторять ему «переведено на оператора» на каждое сообщение не надо.
        return Stay()


STEP = OperatorChatStep()
