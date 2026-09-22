# ==========================================================================
# Сквозной прогон диалога на заглушках — без Telegram и без сети.
#
# Это главный инструмент отладки сценария: за долю секунды проходится весь
# путь клиента, и видно, на каком шаге что-то пошло не так. В старой версии
# такое было невозможно — там логика была намертво сшита с апдейтами PTB.
#
# Запуск:  cd printbot && python -m pytest tests -q
# ==========================================================================

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

config.FORCE_BUSINESS_HOURS = True   # чтобы тест не зависел от времени суток

from core import router  # noqa: E402
from core.store import store  # noqa: E402

CLIENT_ID = 555
ADMIN_ID = config.ADMIN_ID


# --------------------------------------------------------------------------
# Заглушки Telegram
# --------------------------------------------------------------------------
class FakeFile:
    """«Скачивает» настоящий пустой PDF на 10 страниц — иначе бот
    справедливо отклонит файл как нечитаемый."""

    async def download_to_drive(self, path):
        import fitz

        doc = fitz.open()
        for _ in range(10):
            doc.new_page()
        doc.save(path)
        doc.close()


class FakeBot:
    def __init__(self):
        self.sent = []          # (chat_id, text)
        self.keyboards = []     # (chat_id, [подписи кнопок])
        self.documents = []
        self.alerts = []        # всплывашки поверх кнопки
        self.edits = []         # сообщения, заменённые на месте
        self.deleted = []       # удалённые сообщения
        self.hidden_keyboards = 0

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((chat_id, text))
        if reply_markup is not None:
            labels = [b.text for row in reply_markup.inline_keyboard for b in row]
            self.keyboards.append((chat_id, labels))
        return FakeMessage(text)

    async def send_document(self, chat_id, document, caption=None, filename=None, **kw):
        self.documents.append((chat_id, caption, filename))

    async def get_file(self, file_id):
        return FakeFile()

    async def delete_message(self, chat_id, message_id, **kw):
        self.deleted.append((chat_id, message_id))

    async def edit_message_reply_markup(self, chat_id=None, message_id=None, **kw):
        self.hidden_keyboards += 1


class FakeMessage:
    def __init__(self, text="", document=None, bot=None, chat_id=CLIENT_ID):
        self.text = text
        self.document = document
        self.message_id = 1
        self._bot = bot
        self._chat_id = chat_id

    async def reply_text(self, text, reply_markup=None, **kw):
        # Отвечаем именно тому, кто написал: раньше здесь стоял CLIENT_ID
        # жёстко, и ответы админу выглядели как сообщения клиенту.
        if self._bot:
            self._bot.sent.append((self._chat_id, text))
        return FakeMessage(text, chat_id=self._chat_id)


class FakeQuery:
    def __init__(self, data, bot, chat_id=CLIENT_ID):
        self.data = data
        self.message = FakeMessage("", bot=bot, chat_id=chat_id)
        self._bot = bot
        self._chat_id = chat_id

    async def answer(self, text=None, show_alert=False):
        if text:
            self._bot.alerts.append(text)

    async def edit_message_text(self, text, reply_markup=None, **kw):
        self._bot.sent.append((self._chat_id, text))
        self._bot.edits.append(text)      # заменено, а не прислано новым
        return FakeMessage(text, chat_id=self._chat_id)

    async def edit_message_reply_markup(self, reply_markup=None, **kw):
        self._bot.hidden_keyboards += 1


class FakeUser:
    def __init__(self, user_id):
        self.id = user_id


class FakeChat:
    def __init__(self, chat_id):
        self.id = chat_id


class FakeUpdate:
    def __init__(self, user_id, bot, text=None, data=None, document=None):
        self.effective_user = FakeUser(user_id)
        self.effective_chat = FakeChat(user_id)
        self.callback_query = FakeQuery(data, bot, user_id) if data else None
        self.message = (
            FakeMessage(text, document, bot, user_id)
            if (text is not None or document) else None
        )
        self.effective_message = self.message or (
            self.callback_query.message if self.callback_query else None
        )


class FakeContext:
    def __init__(self, bot):
        self.bot = bot
        self.args = []


class FakeDocument:
    def __init__(self, name="draw.pdf", size=500_000):
        self.file_name = name
        self.file_size = size
        self.file_id = "fileid1"


# --------------------------------------------------------------------------
# Помощники
# --------------------------------------------------------------------------
class Dialog:
    """Обёртка, чтобы шаги читались как сценарий."""

    def __init__(self, user_id=CLIENT_ID):
        self.bot = FakeBot()
        self.tg = FakeContext(self.bot)
        self.user_id = user_id

    async def start(self):
        update = FakeUpdate(self.user_id, self.bot, text="/start")
        await router.cmd_start(update, self.tg)

    async def text(self, value):
        await router.dispatch(FakeUpdate(self.user_id, self.bot, text=value), self.tg)

    async def click(self, data):
        await router.dispatch(FakeUpdate(self.user_id, self.bot, data=data), self.tg)

    async def send_pdf(self, name="draw.pdf"):
        update = FakeUpdate(self.user_id, self.bot, document=FakeDocument(name))
        await router.dispatch(update, self.tg)

    @property
    def step(self):
        session = store.get(self.user_id)
        return session.step if session else None

    @property
    def last(self):
        return self.bot.sent[-1][1] if self.bot.sent else ""

    def to_admin(self):
        return [text for chat, text in self.bot.sent if chat == ADMIN_ID]


def run(coro):
    return asyncio.run(coro)


def teardown_function(_):
    """Сброс глобального состояния между тестами: статусы заказов и
    незаконченный ввод админа живут в модуле и иначе протекают дальше."""
    from admin import panel

    store.drop(CLIENT_ID)
    panel.order_status.clear()
    panel.pending.clear()


# --------------------------------------------------------------------------
# Тесты
# --------------------------------------------------------------------------
def test_simple_a4_order_reaches_admin():
    async def scenario():
        d = Dialog()
        await d.start()
        assert d.step == "language"

        await d.click("set_lang_ru")
        assert d.step == "auth"

        await d.text("Иванов Иван Иванович, ИКГ-01-20")
        assert d.step == "wait_file"

        await d.send_pdf("report.pdf")
        assert d.step == "print_mode"

        await d.click("print_all")
        assert d.step == "color_mode"

        await d.click("color_bw")
        assert d.step == "format"

        await d.click("fmt_A4")
        assert d.step == "sided"      # A4 обязан спросить про сторонность

        await d.click("sided_s")
        assert d.step == "add_file"

        await d.click("add_no")
        assert d.step == "brochure_count"

        await d.text("0")
        # чертежей нет — вопрос про складывание пропущен
        assert d.step == "copies"

        await d.text("2")
        assert d.step == "ready_time"

        await d.click("rt_time_1h")
        assert d.step == "confirm"

        await d.click("confirm_yes")

        # сессия и временные файлы убраны сразу после отправки заказа
        assert store.get(CLIENT_ID) is None

        admin_messages = d.to_admin()
        assert any("НОВЫЙ ЗАКАЗ" in m for m in admin_messages)
        assert any("Иванов Иван Иванович" in m for m in admin_messages)
        assert d.bot.documents, "PDF должен уйти админу"

    run(scenario())


def test_admin_gets_original_file_name():
    """Админу должен приходить файл под своим именем, а не под техническим
    «<user_id>_<file_id>.pdf», под которым он лежит на диске."""
    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")
        await d.text("Иванов Иван Иванович, ИКГ-01-20")
        await d.send_pdf("Чертёж узла А-12.pdf")

        await d.click("print_all")
        await d.click("color_bw")
        await d.click("fmt_A4")
        await d.click("sided_s")
        await d.click("add_no")
        await d.text("0")
        await d.text("1")
        await d.click("rt_time_day")
        await d.click("confirm_yes")

        assert d.bot.documents, "файл не ушёл админу"
        _, caption, filename = d.bot.documents[0]
        assert filename == "Чертёж узла А-12.pdf", f"имя файла подменилось: {filename}"
        assert "Чертёж узла А-12.pdf" in caption

    run(scenario())


def test_admin_sees_exact_page_numbers():
    """Баг-репорт п.1: админу нужны конкретные номера страниц."""
    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")
        await d.text("Петров Пётр Петрович, ИКГ-02-21")
        await d.send_pdf("plan.pdf")

        await d.click("print_specific")
        await d.text("1-3,5,7-9")          # печатаем не всё
        await d.click("color_spec")
        await d.text("2,8")                # часть цветом

        await d.click("fmt_A3")            # не A4 — вопроса о сторонности нет
        assert d.step == "add_file"

        await d.click("add_no")
        await d.text("0")                  # брошюр нет
        assert d.step == "folding_ask"     # A3 — есть что складывать

        await d.click("fold_no")
        await d.text("1")                  # копии
        await d.click("rt_time_day")
        await d.click("confirm_yes")

        report = "\n".join(d.to_admin())
        assert "1-3,5,7-9" in report, "нет списка печатаемых страниц"
        assert "2,8" in report, "нет списка цветных страниц"
        assert "1,3,5,7,9" in report, "нет списка ЧБ страниц"

    run(scenario())


def test_brochure_binding_type_is_translated():
    """Баг-репорт п.4: должно быть «Пружинка», а не 'spring'."""
    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")
        await d.text("Сидоров Сидор Сидорович, ИКГ-03-22")

        await d.send_pdf("a.pdf")
        await d.click("print_all")
        await d.click("color_bw")
        await d.click("fmt_A4")
        await d.click("sided_s")
        await d.click("add_no")

        await d.text("1")                  # одна брошюра
        assert d.step == "brochure_assemble"

        await d.click("proj_0")            # выбрали файл
        await d.click("proj_done")
        assert d.step == "brochure_type"

        await d.click("btype_spring")
        assert d.step == "copies"

        await d.text("1")                  # копии файла
        await d.text("3")                  # копии брошюры
        assert d.step == "ready_time"

        await d.click("rt_time_1h")

        summary = d.last
        assert "Пружинка" in summary
        assert "spring" not in summary.lower()

    run(scenario())


def test_express_markup_is_announced_before_and_after_the_choice():
    """Про наценку за срочность человек должен узнать ДО выбора, а в сводке
    видеть, откуда в итоге взялась разница."""
    async def scenario():
        from pricing.calculator import file_price

        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")
        await d.text("Иванов Иван Иванович, ИКГ-01-20")
        await d.send_pdf("a.pdf")
        await d.click("print_all")
        await d.click("color_bw")
        await d.click("fmt_A4")
        await d.click("sided_s")
        await d.click("add_no")
        await d.text("0")
        await d.text("1")
        assert d.step == "ready_time"

        question = d.last
        assert "30%" in question, "наценка не названа в вопросе о сроках"
        assert "1 минуты" in question and "1 час" in question

        base = file_price(store.get(CLIENT_ID).order.files[0])
        await d.click("rt_time_express")

        summary = d.last
        assert "30%" in summary, "в сводке не сказано, откуда наценка"
        assert str(int(base * 1.3)) in summary

    run(scenario())


def test_error_does_not_eat_the_file_list():
    """«Вы не выбрали ни одного файла» не должно затирать сам список файлов —
    иначе нажимать больше не на что и диалог встаёт."""
    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")
        await d.text("Сидоров Сидор Сидорович, ИКГ-03-22")

        await d.send_pdf("a.pdf")
        await d.click("print_all")
        await d.click("color_bw")
        await d.click("fmt_A4")
        await d.click("sided_s")
        await d.click("add_no")
        await d.text("1")
        assert d.step == "brochure_assemble"

        before = len(d.bot.edits)
        await d.click("proj_done")            # ничего не выбрано

        assert d.step == "brochure_assemble"
        assert len(d.bot.edits) == before, "ошибка заменила собой вопрос с файлами"

        # список файлов остался на месте — выбор всё ещё возможен
        await d.click("proj_0")
        await d.click("proj_done")
        assert d.step == "brochure_type"

    run(scenario())


def test_english_dialog_stays_english():
    """Баг-репорт п.6: русские фразы не должны просачиваться в EN-диалог."""
    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_en")
        await d.text("Ivanov Ivan Ivanovich, ICG-01-20")

        await d.send_pdf("a.pdf")
        await d.click("print_all")
        await d.click("color_bw")
        await d.click("fmt_A4")
        await d.click("sided_s")
        await d.click("add_no")

        # заявляем 2 брошюры при одном файле — раньше здесь приходила
        # русская фраза «Свободных файлов больше нет...»
        await d.text("2")
        await d.click("proj_0")
        await d.click("proj_done")
        await d.click("btype_spring")

        client_messages = [t for chat, t in d.bot.sent if chat == CLIENT_ID]
        # Первое сообщение — выбор языка, оно намеренно двуязычное.
        client_messages = [m for m in client_messages if "Choose language" not in m]

        russian = [m for m in client_messages if any("а" <= c.lower() <= "я" for c in m)]
        assert not russian, f"русский текст в английском диалоге: {russian}"

    run(scenario())


def test_extra_file_gets_explanation_not_error():
    """Баг-репорт п.10: второй файл в том же сообщении — понятное объяснение."""
    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")
        await d.text("Иванов Иван Иванович, ИКГ-01-20")
        await d.send_pdf("first.pdf")
        assert d.step == "print_mode"

        await d.send_pdf("second.pdf")     # прилетел, пока настраиваем первый
        assert d.step == "print_mode"      # шаг не сбился
        assert "по одному" in d.last
        assert "не поддерживается" not in d.last

    run(scenario())


def test_garbage_name_is_rejected():
    """Баг-репорт п.9: 'sda' не должно проходить авторизацию."""
    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")

        await d.text("sda")
        assert d.step == "auth", "мусор не должен проходить авторизацию"

        await d.text("Иванов Иван Иванович, ИКГ-01-20")
        assert d.step == "wait_file"

    run(scenario())


def test_stray_text_offers_operator_without_losing_order():
    """ТЗ §4: на непонятный текст предлагаем оператора, но заказ не теряем."""
    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")
        await d.text("Иванов Иван Иванович, ИКГ-01-20")
        await d.send_pdf("a.pdf")
        assert d.step == "print_mode"

        await d.text("а сколько это стоит?")   # текст там, где ждали кнопку
        assert "оператора" in d.last
        assert d.step == "print_mode", "заказ не должен потеряться"

        await d.click("op_no")                 # передумал звать оператора
        assert d.step == "print_mode"
        await d.click("print_all")
        assert d.step == "color_mode"          # сценарий продолжается

    run(scenario())


def test_ready_button_leaves_only_issue_and_cancel():
    """После «Готов» повторно отмечать заказ готовым уже незачем —
    остаются только «Выдан» и «Отмена»."""
    async def scenario():
        d = Dialog(user_id=ADMIN_ID)
        await d.click(f"adm_ready_{CLIENT_ID}")

        admin_keyboards = [labels for chat, labels in d.bot.keyboards if chat == ADMIN_ID]
        assert admin_keyboards, "админу не пришла клавиатура"
        labels = admin_keyboards[-1]
        assert "📦 Выдан" in labels
        assert "❌ Отмена" in labels
        assert not any("Готов" in label for label in labels), f"кнопка «Готов» осталась: {labels}"

    run(scenario())


def test_feedback_ends_with_start_hint():
    """После отзыва клиент должен знать, как оформить новый заказ."""
    async def scenario():
        d = Dialog()
        store.set_lang(CLIENT_ID, "ru")
        # админ нажал «Выдан» — клиенту заводится сессия отзыва
        admin = Dialog(user_id=ADMIN_ID)
        admin.bot = d.bot
        admin.tg = d.tg
        await admin.click(f"adm_issue_{CLIENT_ID}")

        assert d.step == "feedback_rating"
        await d.text("9")
        assert d.step == "feedback_comment"

        await d.text("всё понравилось")
        assert "/start" in d.last, f"нет подсказки про новый заказ: {d.last!r}"
        assert store.get(CLIENT_ID) is None, "сессия отзыва должна закрыться"

        assert any("ОТЗЫВ" in m for m in d.to_admin())

    run(scenario())


def test_operator_flow_reaches_admin():
    """Баг-репорт п.8: сообщение клиента должно дойти до админа."""
    async def scenario():
        d = Dialog()
        await d.text("здравствуйте, у меня вопрос")   # вне сценария
        assert "оператора" in d.last

        await d.click("op_yes")
        assert d.step == "operator_chat"

        await d.text("когда вы работаете?")
        admin_messages = d.to_admin()
        assert any("когда вы работаете?" in m for m in admin_messages)

    run(scenario())


def test_client_can_leave_operator_chat():
    """Из режима оператора должен быть выход — иначе человек заперт в нём
    навсегда: шаг operator_chat сам себя не завершает."""
    async def scenario():
        d = Dialog()
        await d.text("вопрос")
        await d.click("op_yes")
        await d.text("а есть ли скидки?")
        assert d.step == "operator_chat"

        await d.click("op_end")
        assert store.get(CLIENT_ID) is None, "сессия оператора должна закрыться"
        assert any("завершён" in m for m in d.to_admin())

    run(scenario())


def test_admin_can_end_operator_chat():
    """Оператор тоже должен уметь закрыть разговор со своей стороны."""
    async def scenario():
        d = Dialog()
        await d.text("вопрос")
        await d.click("op_yes")
        assert d.step == "operator_chat"

        admin = Dialog(user_id=ADMIN_ID)
        admin.bot, admin.tg = d.bot, d.tg
        await admin.click(f"adm_end_{CLIENT_ID}")

        assert store.get(CLIENT_ID) is None
        client_messages = [t for chat, t in d.bot.sent if chat == CLIENT_ID]
        assert any("завершён" in m for m in client_messages), "клиента не уведомили"

    run(scenario())


def test_timeout_removes_the_continue_button():
    """После закрытия диалога сообщение «Продолжить» с живой кнопкой не
    должно остаться висеть в чате."""
    import time as _time

    from config import IDLE_GRACE_SEC, IDLE_WARN_SEC
    from tasks.janitor import sweep

    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")
        session = store.get(CLIENT_ID)

        # молчит достаточно долго -> предупреждение с кнопкой
        session.last_seen = _time.monotonic() - IDLE_WARN_SEC - 1
        await sweep(d.tg)
        assert session.warned
        warn_id = session.warn_message_id
        assert warn_id is not None, "предупреждение не отправлено"

        # молчит ещё дольше -> диалог закрывается
        session.last_seen = _time.monotonic() - IDLE_WARN_SEC - IDLE_GRACE_SEC - 1
        await sweep(d.tg)

        assert store.get(CLIENT_ID) is None, "сессия не закрылась"
        assert (CLIENT_ID, warn_id) in d.bot.deleted, "кнопка «Продолжить» осталась"

    run(scenario())


def test_answer_after_warning_removes_the_warning():
    """Человек ответил после предупреждения — оно перестало быть правдой и
    должно исчезнуть вместе с кнопкой."""
    import time as _time

    from config import IDLE_WARN_SEC
    from tasks.janitor import sweep

    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")
        session = store.get(CLIENT_ID)

        session.last_seen = _time.monotonic() - IDLE_WARN_SEC - 1
        await sweep(d.tg)
        warn_id = session.warn_message_id
        assert warn_id is not None

        await d.text("Иванов Иван Иванович, ИКГ-01-20")   # ответил

        assert (CLIENT_ID, warn_id) in d.bot.deleted, "предупреждение осталось"
        assert store.get(CLIENT_ID).warn_message_id is None
        assert store.get(CLIENT_ID).step == "wait_file", "ответ не обработан"

    run(scenario())


def test_idle_closes_operator_and_feedback_sessions():
    """Сторож обязан закрывать не только заказы: раньше он пропускал
    оператора и отзыв, и такие сессии висели вечно."""
    import time as _time

    from config import IDLE_SIDE_SEC
    from core.session import KIND_FEEDBACK, KIND_OPERATOR
    from tasks.janitor import sweep

    async def scenario():
        bot = FakeBot()
        tg = FakeContext(bot)

        operator = store.start(CLIENT_ID, kind=KIND_OPERATOR, step="operator_chat")
        reviewer = store.start(777, kind=KIND_FEEDBACK, step="feedback_rating")
        stale = _time.monotonic() - IDLE_SIDE_SEC - 1
        operator.last_seen = stale
        reviewer.last_seen = stale

        await sweep(tg)

        assert store.get(CLIENT_ID) is None, "чат с оператором не закрылся"
        assert store.get(777) is None, "брошенный отзыв не закрылся"
        # про оператора сказать надо, про брошенный отзыв — не надо
        assert any(chat == CLIENT_ID for chat, _ in bot.sent)
        assert not any(chat == 777 for chat, _ in bot.sent)

    run(scenario())
    store.drop(777)


def test_stale_admin_input_is_not_sent_to_client():
    """Админ нажал «Отмена», отвлёкся на час и написал что-то своё — этот
    текст не должен уйти клиенту как причина отмены."""
    import time as _time

    from admin import panel
    from config import ADMIN_PENDING_TTL_SEC

    async def scenario():
        d = Dialog(user_id=ADMIN_ID)
        await d.click(f"adm_cancel_{CLIENT_ID}")
        assert ADMIN_ID in panel.pending

        # отматываем время назад: как будто прошло больше срока
        panel.pending[ADMIN_ID]["at"] -= ADMIN_PENDING_TTL_SEC + 1

        await d.text("напоминание себе купить бумагу")

        assert ADMIN_ID not in panel.pending, "просроченный ввод должен сбрасываться"
        assert not any(chat == CLIENT_ID for chat, _ in d.bot.sent), "текст ушёл клиенту"
        assert "НЕ отправлен" in d.last

    run(scenario())
    panel.pending.pop(ADMIN_ID, None)


def test_double_click_does_not_skip_a_step():
    """Быстрый двойной клик по кнопке цвета не должен проскочить выбор
    формата: раньше второе нажатие принимал шаг «формат», формат оставался
    пустым, и заказ выходил на 0 рублей."""
    async def scenario():
        from pricing.calculator import file_price

        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")
        await d.text("Иванов Иван Иванович, ИКГ-01-20")
        await d.send_pdf("plan.pdf")
        await d.click("print_all")
        assert d.step == "color_mode"

        await d.click("color_bw")
        await d.click("color_bw")      # то же нажатие ещё раз, со старой клавиатуры
        await d.click("color_bw")
        assert d.step == "format", "лишние нажатия увели диалог со своего шага"

        await d.click("fmt_A4")
        await d.click("sided_s")

        f = store.get(CLIENT_ID).order.files[0]
        assert f.format == "A4", "формат потерялся"
        assert file_price(f) == 10 * 18, f"цена посчиталась неверно: {file_price(f)}"

    run(scenario())


def test_stale_button_cannot_cancel_a_finished_order():
    """Самый дорогой случай того же бага: нажатие со старой клавиатуры не
    должно попасть в шаг подтверждения и отменить готовый заказ."""
    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")
        await d.text("Иванов Иван Иванович, ИКГ-01-20")
        await d.send_pdf("a.pdf")
        await d.click("print_all")
        await d.click("color_bw")
        await d.click("fmt_A4")
        await d.click("sided_s")
        await d.click("add_no")
        await d.text("0")
        await d.text("1")
        await d.click("rt_time_1h")
        assert d.step == "confirm"

        await d.click("sided_s")       # чужая кнопка на шаге подтверждения
        assert d.step == "confirm", "заказ сорвался из-за старой кнопки"

        await d.click("confirm_yes")
        assert any("НОВЫЙ ЗАКАЗ" in m for m in d.to_admin())

    run(scenario())


def test_repeat_confirm_clicks_are_silent():
    """Лишние нажатия «Заказать» прилетают, когда заказ уже отправлен и
    сессии нет. Бот молчал бы правильно — раньше он на каждое отвечал
    «диалог закрыт из-за долгого молчания», хотя молчания не было."""
    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")
        await d.text("Иванов Иван Иванович, ИКГ-01-20")
        await d.send_pdf("a.pdf")
        await d.click("print_all")
        await d.click("color_bw")
        await d.click("fmt_A4")
        await d.click("sided_s")
        await d.click("add_no")
        await d.text("0")
        await d.text("1")
        await d.click("rt_time_1h")

        await d.click("confirm_yes")
        assert d.step is None, "сессия должна закрыться после заказа"

        to_client = len([1 for chat, _ in d.bot.sent if chat == CLIENT_ID])
        await d.click("confirm_yes")
        await d.click("confirm_yes")

        assert len([1 for chat, _ in d.bot.sent if chat == CLIENT_ID]) == to_client, \
            "лишние нажатия породили сообщения клиенту"
        assert len(d.to_admin()) == 1, "заказ ушёл админу дважды"

    run(scenario())


def test_stale_button_on_text_step_is_silent():
    """Случай из живого лога: после сборки брошюры бот спрашивает копии
    (ждёт текст), а следом прилетают лишние нажатия «proj_done» со старой
    клавиатуры. Бот не должен отвечать «я не умею читать текст»."""
    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")
        await d.text("Иванов Иван Иванович, ИКГ-01-20")
        await d.send_pdf("a.pdf")
        await d.click("print_all")
        await d.click("color_bw")
        await d.click("fmt_A4")
        await d.click("sided_s")
        await d.click("add_no")
        await d.text("1")             # одна брошюра
        await d.click("proj_0")
        await d.click("proj_done")
        await d.click("btype_spring")
        assert d.step == "copies"

        before = len(d.bot.sent)
        await d.click("proj_done")    # запоздалые нажатия по старым кнопкам
        await d.click("proj_done")
        await d.click("proj_0")

        new = [t for _, t in d.bot.sent[before:]]
        assert not new, f"на лишние нажатия бот наговорил лишнего: {new}"
        assert d.step == "copies", "лишние нажатия сбили шаг"

        # обычные ответы по-прежнему работают: копии файла, затем брошюры
        await d.text("2")
        assert d.step == "copies"
        await d.text("3")
        assert d.step == "ready_time"

    run(scenario())


def test_no_duplicate_when_telegram_rejects_identical_edit():
    """Если правка сообщения отклонена как «ничего не изменилось», копию
    новым сообщением слать нельзя — в чате появлялся дубль."""
    async def scenario():
        d = Dialog()
        await d.start()
        await d.click("set_lang_ru")

        async def refuse(text, reply_markup=None, **kw):
            raise RuntimeError(
                "Message is not modified: specified new message content and "
                "reply markup are exactly the same"
            )

        update = FakeUpdate(CLIENT_ID, d.bot, text=None, data="op_no")
        update.callback_query.edit_message_text = refuse

        before = len(d.bot.sent)
        await router.dispatch(update, d.tg)
        assert len(d.bot.sent) == before, "дубль ушёл новым сообщением"

    run(scenario())


def test_every_button_step_declares_its_buttons():
    """Шаг с кнопками обязан объявить buttons — иначе он снова начнёт
    принимать чужие нажатия."""
    from core.step import CALLBACK
    from steps import STEPS

    forgotten = [
        step.id for step in STEPS.values()
        if CALLBACK in step.accepts and not step.buttons
    ]
    assert not forgotten, f"шаги без buttons: {forgotten}"


def test_button_answer_replaces_the_question():
    """Ответ кнопкой должен заменять сам вопрос, а не оставлять его висеть
    со старой клавиатурой — так вёл себя первоначальный бот."""
    async def scenario():
        d = Dialog()
        await d.start()
        assert not d.bot.edits, "первый вопрос заменять нечего"

        await d.click("set_lang_ru")
        assert "ФИО" in d.bot.edits[-1], "выбор языка не заменился приветствием"

        await d.text("Иванов Иван Иванович, ИКГ-01-20")
        await d.send_pdf("a.pdf")
        edits_before = len(d.bot.edits)

        await d.click("print_all")     # вопрос про страницы -> вопрос про цвет
        await d.click("color_bw")      # вопрос про цвет -> вопрос про формат
        await d.click("fmt_A4")        # формат -> сторонность
        await d.click("sided_s")       # сторонность -> цена и «ещё файл?»

        assert len(d.bot.edits) - edits_before == 4, (
            f"каждое нажатие должно заменять вопрос, а заменилось "
            f"{len(d.bot.edits) - edits_before} из 4"
        )
        # ответ текстом заменить нечего — там приходит новое сообщение
        await d.click("add_no")
        edits_after_text_step = len(d.bot.edits)
        await d.text("0")
        assert len(d.bot.edits) == edits_after_text_step

    run(scenario())


def test_issue_notifies_client_exactly_once():
    """Клиент должен получить просьбу оценить ровно один раз, даже если
    админ нажал «Выдан» несколько раз подряд."""
    async def scenario():
        from admin import panel

        panel.order_status.clear()
        d = Dialog(user_id=ADMIN_ID)
        await d.click(f"adm_issue_{CLIENT_ID}")
        await d.click(f"adm_issue_{CLIENT_ID}")
        await d.click(f"adm_issue_{CLIENT_ID}")

        to_client = [t for chat, t in d.bot.sent if chat == CLIENT_ID]
        asks = [t for t in to_client if "Оцените сервис" in t]
        assert len(asks) == 1, f"клиенту ушло {len(asks)} просьб оценить: {to_client}"
        assert any("уже выдан" in a for a in d.bot.alerts)

    run(scenario())
    from admin import panel
    panel.order_status.clear()


def test_closed_order_ignores_ready_and_cancel():
    """После выдачи заказа кнопки «Готов» и «Отмена» не должны работать."""
    async def scenario():
        from admin import panel

        panel.order_status.clear()
        d = Dialog(user_id=ADMIN_ID)
        await d.click(f"adm_issue_{CLIENT_ID}")
        before = len(d.bot.sent)

        await d.click(f"adm_ready_{CLIENT_ID}")
        await d.click(f"adm_cancel_{CLIENT_ID}")

        assert ADMIN_ID not in panel.pending, "отмена не должна начинаться"
        new_texts = [t for _, t in d.bot.sent[before:]]
        assert not new_texts, f"после выдачи ничего слаться не должно: {new_texts}"
        assert len(d.bot.alerts) >= 2

    run(scenario())
    from admin import panel
    panel.order_status.clear()


def test_cancelled_order_cannot_be_issued():
    async def scenario():
        from admin import panel

        panel.order_status.clear()
        d = Dialog(user_id=ADMIN_ID)
        await d.click(f"adm_cancel_{CLIENT_ID}")
        await d.text("нет бумаги")          # причина — отмена состоялась
        assert panel.order_status[CLIENT_ID] == panel.CANCELLED

        before = len(d.bot.sent)
        await d.click(f"adm_issue_{CLIENT_ID}")
        assert len(d.bot.sent) == before, "отменённый заказ нельзя выдать"
        assert any("отменён" in a for a in d.bot.alerts)

    run(scenario())
    from admin import panel
    panel.order_status.clear()
    panel.pending.pop(ADMIN_ID, None)


def test_abandoned_cancel_keeps_order_usable():
    """Админ нажал «Отмена», но причину так и не написал — заказ должен
    остаться рабочим."""
    async def scenario():
        from admin import panel

        panel.order_status.clear()
        d = Dialog(user_id=ADMIN_ID)
        await d.click(f"adm_cancel_{CLIENT_ID}")
        assert panel.order_status.get(CLIENT_ID, panel.NEW) == panel.NEW

        await d.click(f"adm_ready_{CLIENT_ID}")   # передумал — отмечает готовым
        assert panel.order_status[CLIENT_ID] == panel.READY
        assert ADMIN_ID not in panel.pending

    run(scenario())
    from admin import panel
    panel.order_status.clear()


def test_other_admin_button_cancels_pending_input():
    """Нажатие другой кнопки отменяет незаконченный ввод."""
    async def scenario():
        from admin import panel

        d = Dialog(user_id=ADMIN_ID)
        await d.click(f"adm_cancel_{CLIENT_ID}")
        assert panel.pending[ADMIN_ID]["mode"] == "cancel"

        await d.click(f"adm_ready_{CLIENT_ID}")
        assert ADMIN_ID not in panel.pending

    run(scenario())
