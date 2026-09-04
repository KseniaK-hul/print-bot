import logging
import os
import asyncio
import threading
import datetime
import fitz
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# !!! ВСТАВЬТЕ ВАШ НОВЫЙ ТОКЕН (после Revoke) !!!
TOKEN = os.getenv("BOT_TOKEN", "ВАШ_НОВЫЙ_ТОКЕН_СЮДА")
ADMIN_ID = 6592882382

MAX_FILE_SIZE_MB = 20
MIN_FILE_SIZE_KB = 10

# ==========================================
# ПЕРЕВОДЫ
# ==========================================
LANG_RU = 'ru'
LANG_EN = 'en'
user_language = {}

TEXTS_RU = {
    'greeting': "👋 Привет! Сделай онлайн-заказ на печать.\n\n⚠️ Заказы на ненастоящие имена не выполняются!\n📝 Напишите ФИО и ИКГ (например: Иванов Иван Иванович, ИКГ-01-20)",
    'auth_success': "✅ Авторизация успешна!\n📄 Отправьте файл для печати (PDF):",
    'bad_file': "❌ Формат файла не поддерживается! Отправьте файл в формате PDF.",
    'file_too_big': "❌ Файл слишком большой! Максимум 20 МБ.",
    'pdf_error': "❌ Не удалось прочитать PDF. Попробуйте другой.",
    'file_ok': "✅ Файл принят! Страниц: {total} (🎨{color} / ⚫{bw})\nКак напечатать?",
    'print_all': "📄 Все страницы",
    'print_specific': "✂️ Конкретные страницы",
    'choose_pages': "📝 Введите номера страниц через запятую (например: 1,3,5-7).\nВсего страниц: {total}",
    'color_choice': "🎨 Как напечатать эти страницы?",
    'color_all': "🎨 Все цветом",
    'bw_all': "⚫ Все ЧБ",
    'color_specific': "📝 Указать страницы цветом",
    'choose_color_pages': "📝 Введите номера страниц, которые будут ЦВЕТНЫМИ (остальные станут ЧБ).",
    'format_choice': "📐 Какой формат листа нужен?",
    'sided_choice': "📄 Печать будет односторонней или двусторонней?",
    'one_side': "1️⃣ Односторонняя",
    'two_side': "2️⃣ Двусторонняя",
    'total_price': "💰 Итого за файл: {price} руб.\nХотите добавить ещё файл?",
    'add_file': "📄 Отправьте следующий файл:",
    'no_brochure': "📚 Брошюровка не нужна!",
    'brochure_count': "📚 Сколько брошюр нужно сшить? (Введите цифру, если не нужно - 0)",
    'choose_brochure': "📚 Соберите Брошюру #{num}:\nНажимайте на файлы в том порядке, в котором они должны идти.",
    'brochure_type': "Какой тип брошюровки?",
    'spring': "🔄 Пружинка",
    'string': "🧵 Бечевка",
    'fold_choice': "📐 Нужно ли сложить чертежи?",
    'fold_select': "📐 Выберите отдельные чертежи для складывания (не в брошюре):",
    'copies_header': "📄 Сколько копий напечатать для файла #1 ({name})? Введите цифру:",
    'copies_next': "✅ Копий: {copies}. Сколько копий для файла #{num} ({name})?",
    'copies_set': "✅ Копии заданы!",
    'enter_number': "❌ Введите цифру (например, 0, 1, 2).",
    'time_choice': "🕐 Когда готовы забрать?",
    'bw_fold': "📐 Складывание: {price} руб.",
    'final_confirm': "✅ Заказать",
    'final_cancel': "❌ Отказаться",
    'feedback_ask': "📦 Ваш заказ выдан! Оцените сервис от 1 до 10:",
    'feedback_comment': "✅ Спасибо! 📝 Напишите, что улучшить (или поставьте -):",
    'feedback_thanks': "🙏 Спасибо за отзыв!",
    'operator_text': "🤖 Я не умею читать тексты! Перевести на оператора?",
    'operator_yes': "👨‍💻 Да",
    'operator_no': "❌ Нет",
    'working_hours': "⏰ Мы закрыты! Пн-Пт с 9:00 до 20:00."
}

TEXTS_EN = {
    'greeting': "👋 Hi! Make an online printing order.\n\n⚠️ Orders with fake names won't be accepted!\n📝 Write your Name and ID (e.g.: Ivanov Ivan Ivanovich, ICG-01-20)",
    'auth_success': "✅ Authorization successful!\n📄 Send the file to print (PDF):",
    'bad_file': "❌ File format not supported! Please send a PDF file.",
    'file_too_big': "❌ File too large! Maximum 20 MB.",
    'pdf_error': "❌ Could not read PDF. Try another.",
    'file_ok': "✅ File accepted! Pages: {total} (🎨{color} / ⚫{bw})\nHow to print?",
    'print_all': "📄 All pages",
    'print_specific': "✂️ Specific pages",
    'choose_pages': "📝 Enter page numbers separated by commas (e.g., 1,3,5-7).\nTotal pages: {total}",
    'color_choice': "🎨 How to print these pages?",
    'color_all': "🎨 All color",
    'bw_all': "⚫ All B&W",
    'color_specific': "📝 Specify color pages",
    'choose_color_pages': "📝 Enter numbers of the pages that should be COLOR (others will be B&W).",
    'format_choice': "📐 What paper size?",
    'sided_choice': "📄 Single-sided or double-sided?",
    'one_side': "1️⃣ Single",
    'two_side': "2️⃣ Double",
    'total_price': "💰 Total for file: {price} RUB.\nAdd another file?",
    'add_file': "📄 Send the next file:",
    'no_brochure': "📚 No binding needed!",
    'brochure_count': "📚 How many brochures to bind? (Enter number, 0 if none)",
    'choose_brochure': "📚 Assemble Brochure #{num}:\nClick files in the correct order.",
    'brochure_type': "Binding type?",
    'spring': "🔄 Spiral",
    'string': "🧵 String",
    'fold_choice': "📐 Need to fold drawings?",
    'fold_select': "📐 Choose separate drawings to fold (not in brochure):",
    'copies_header': "📄 How many copies for file #1 ({name})? Enter number:",
    'copies_next': "✅ Copies: {copies}. How many for file #{num} ({name})?",
    'copies_set': "✅ Copies set!",
    'enter_number': "❌ Enter 0, 1, 2...",
    'time_choice': "🕐 When will you pick up?",
    'bw_fold': "📐 Folding: {price} RUB.",
    'final_confirm': "✅ Confirm order",
    'final_cancel': "❌ Cancel",
    'feedback_ask': "📦 Order handed out! Rate the service from 1 to 10:",
    'feedback_comment': "✅ Thanks! 📝 What can we improve? (or type '-'):",
    'feedback_thanks': "🙏 Thank you for your feedback!",
    'operator_text': "🤖 I can't read texts! Transfer to an operator?",
    'operator_yes': "👨‍💻 Yes",
    'operator_no': "❌ No",
    'working_hours': "⏰ We are closed! Mon-Fri 9:00 to 20:00."
}

def t(user_id, key, **kwargs):
    lang = user_language.get(user_id, LANG_RU)
    text = TEXTS_EN.get(key, TEXTS_RU.get(key, key)) if lang == LANG_EN else TEXTS_RU.get(key, key)
    if kwargs: text = text.format(**kwargs)
    return text

# ==========================================
# СОСТОЯНИЯ
# ==========================================
(AUTH, WAIT_FILE, FORMAT, SIDED, ADD_FILE, FOLDING, FOLDING_SELECT, 
 READY_TIME, CONFIRM, WAIT_OPERATOR, PRINT_COPIES, STRING_COPIES, 
 PRINT_MODE, INPUT_PAGES, COLOR_MODE, INPUT_COLOR_PAGES, 
 SET_BROCHURE_COUNT, SETUP_BROCHURE, SETUP_BROCHURE_TYPE) = range(19)

# ==========================================
# ЦЕНЫ
# ==========================================
PRICES_COLOR = {'A4': 60, 'A3': 140, 'A2': 300, 'A1': 500, 'A0': 1000}
PRICES_BW = {'A4': 18, 'A3': 60, 'A2': 200, 'A1': 300, 'A0': 600}
FOLDING_PRICES = {'A0': 100, 'A1': 50, 'A2': 30, 'A3': 10}

user_orders = {}
admin_cancel_states = {}
client_feedback_states = {}

# ==========================================
# СЛУЖЕБНЫЕ ФУНКЦИИ
# ==========================================
def is_business_hours():
    try:
        now_msk = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
        return now_msk.weekday() < 5 and 9 <= now_msk.hour < 20
    except:
        return True

def analyze_pdf_colors(file_path):
    try:
        doc = fitz.open(file_path)
        total = len(doc)
        color = 0
        bw = 0
        for p in doc:
            has_color = False
            for img in p.get_images(full=True):
                try:
                    if fitz.Pixmap(doc, img[0]).n > 1: has_color = True; break
                except: continue
            if not has_color:
                for block in p.get_text("dict").get("blocks", []):
                    if "lines" in block:
                        for line in block["lines"]:
                            for span in line.get("spans", []):
                                if span.get("color") not in [0, 0x000000, 0xFFFFFF, 0xFF000000]:
                                    has_color = True; break
                            if has_color: break
                    if has_color: break
            if has_color: color += 1
            else: bw += 1
        doc.close()
        return total, color, bw
    except:
        return 0, 0, 0

def calc_brochure_price(fmt, pages):
    if fmt == 'A4': return 150 if pages <= 20 else 150 + ((pages - 20 + 19) // 20 * 50)
    if fmt == 'A3': return 300 + max(0, pages - 20) * 10
    if fmt in ['A0', 'A1', 'A2']: return 250
    return 0

async def error_handler(update, context):
    logger.error(f"Ошибка: {context.error}", exc_info=True)
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ Ошибка в боте: {context.error}")
    except: pass

# ==========================================
# СТАРТ И ЯЗЫК
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        if user_id in user_orders:
            for f in user_orders[user_id][0]['files']:
                try:
                    if f.get('path'): os.remove(f['path'])
                except: pass
            del user_orders[user_id]

        if not is_business_hours():
            await update.message.reply_text(t(user_id, 'working_hours'))
            return ConversationHandler.END

        user_orders[user_id] = [{'user_info': 'Unknown', 'files': [], 'projects': [], 'folding': False, 'folding_files': [], 'folding_price': 0, 'string': False, 'string_price': 0, 'string_copies': 0, 'ready_time': None, 'total_price': 0, 'is_express': False, 'express_fee': 0}]
        context.user_data['selected_folding'] = []
        context.user_data['copy_index'] = 0

        lang_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="set_lang_ru")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en")]
        ])
        await update.message.reply_text("🌍 Выберите язык / Choose language:", reply_markup=lang_kb)
        return AUTH
    except Exception as e:
        logger.error(f"Ошибка start: {e}")
        return ConversationHandler.END

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == "set_lang_en":
        user_language[user_id] = LANG_EN
    else:
        user_language[user_id] = LANG_RU

    await query.edit_message_text(t(user_id, 'greeting'))
    return AUTH

async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        user_orders[user_id][0]['user_info'] = update.message.text
        await update.message.reply_text(t(user_id, 'auth_success'))
        return WAIT_FILE
    except Exception as e:
        await update.message.reply_text("❌ Ошибка. Нажмите /start.")
        return ConversationHandler.END

# ==========================================
# ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ДОКУМЕНТОВ (ИСПРАВЛЕНИЕ КРАША)
# ==========================================
async def ignore_document(update, context):
    try:
        uid = update.effective_user.id
        await update.message.reply_text(t(uid, 'bad_file'))
    except:
        pass

# ==========================================
# ОБРАБОТКА ФАЙЛОВ
# ==========================================
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        doc = update.message.document
        if not doc or not doc.file_name.lower().endswith('.pdf'):
            await update.message.reply_text(t(user_id, 'bad_file'))
            return WAIT_FILE
        if doc.file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            await update.message.reply_text(t(user_id, 'file_too_big'))
            return WAIT_FILE

        file = await context.bot.get_file(doc.file_id)
        os.makedirs(f"temp_{user_id}", exist_ok=True)
        path = os.path.join(f"temp_{user_id}", f"{user_id}_{doc.file_id}.pdf")
        await file.download_to_drive(path)

        total, color, bw = await asyncio.to_thread(analyze_pdf_colors, path)
        if total == 0:
            await update.message.reply_text(t(user_id, 'pdf_error'))
            if os.path.exists(path): os.remove(path)
            return WAIT_FILE

        user_orders[user_id][0]['files'].append({'path': path, 'name': doc.file_name, 'total_pages': total, 'actual_color_pages': color, 'actual_bw_pages': bw, 'format': None, 'sided': None, 'print_price': 0, 'copies': 1, 'folding_copies': 1, 'selected_pages': None, 'color_pages': 0, 'bw_pages': 0})

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(user_id, 'print_all'), callback_data="print_all")],
            [InlineKeyboardButton(t(user_id, 'print_specific'), callback_data="print_specific")]
        ])
        await update.message.reply_text(t(user_id, 'file_ok', total=total, color=color, bw=bw), reply_markup=kb)
        return PRINT_MODE
    except Exception as e:
        logger.error(f"Ошибка file: {e}")
        return ConversationHandler.END

# ==========================================
# ВСЕ ОСТАЛЬНЫЕ ФУНКЦИИ (print_mode_choice, input_pages_handler, color_mode_choice,
# input_color_pages_handler, format_choice, sided_choice, add_file_choice,
# folding_choice, folding_select, show_final_order, print_copies_handler,
# set_brochure_count_handler, show_project_setup, brochure_setup_handler,
# brochure_type_handler, time_choice, string_copies_handler, confirm_choice,
# send_order_to_admin, issue_client, feedback_rating_handler, feedback_comment_handler,
# unsupported_text, operator_choice, operator_chat, reply_to_client, notify_client,
# cancel, test, send_test)
# ... (Эти функции остаются точно такими же, как в предыдущем рабочем коде, 
# с защитой try/except и удалением текстовых ошибок)
# ==========================================

# ... (Вставьте сюда все остальные функции из предыдущего готового кода, 
# они полностью идентичны и уже защищены от ошибок)
# ==========================================
# ЗАПУСК БОТА
# ==========================================
def run_bot():
    application = Application.builder().token(TOKEN).build()
    application.add_error_handler(error_handler)
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AUTH: [CallbackQueryHandler(language_callback, pattern="^set_lang_"), MessageHandler(filters.TEXT & ~filters.COMMAND, auth)],
            WAIT_FILE: [MessageHandler(filters.Document.ALL, handle_file)],
            PRINT_MODE: [CallbackQueryHandler(print_mode_choice, pattern="^print_")],
            INPUT_PAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_pages_handler)],
            COLOR_MODE: [CallbackQueryHandler(color_mode_choice, pattern="^color_|^bw_|^color_spec")],
            INPUT_COLOR_PAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_color_pages_handler)],
            FORMAT: [CallbackQueryHandler(format_choice, pattern="^fmt_")],
            SIDED: [CallbackQueryHandler(sided_choice, pattern="^sided_")],
            ADD_FILE: [CallbackQueryHandler(add_file_choice, pattern="^add_")],
            FOLDING: [CallbackQueryHandler(folding_choice, pattern="^fold_")],
            FOLDING_SELECT: [CallbackQueryHandler(folding_select, pattern="^fold_")],
            PRINT_COPIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, print_copies_handler)],
            SET_BROCHURE_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_brochure_count_handler)],
            SETUP_BROCHURE: [CallbackQueryHandler(brochure_setup_handler, pattern="^proj_")],
            SETUP_BROCHURE_TYPE: [CallbackQueryHandler(brochure_type_handler, pattern="^btype_")],
            READY_TIME: [CallbackQueryHandler(time_choice, pattern="^time_")],
            STRING_COPIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, string_copies_handler)],
            CONFIRM: [CallbackQueryHandler(confirm_choice, pattern="^confirm_")],
            WAIT_OPERATOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, operator_chat), CallbackQueryHandler(operator_choice, pattern="^op_")],
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.TEXT & ~filters.COMMAND, unsupported_text)]
    )
    
    application.add_handler(conv_handler)
    
    # ИСПРАВЛЕНИЕ: Глобальный обработчик документов. Теперь .docx и др. не уронят бота на любом этапе
    application.add_handler(MessageHandler(filters.Document.ALL, ignore_document))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_rating_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_comment_handler))
    application.add_handler(CallbackQueryHandler(issue_client, pattern="^issue_"))
    application.add_handler(CallbackQueryHandler(notify_client, pattern="^ready_"))
    application.add_handler(CommandHandler('reply', reply_to_client))
    
    print("🤖 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# ==========================================
# НАСТРОЙКА FLASK ДЛЯ RENDER
# ==========================================
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return 'Bot is running!'

def run_flask():
    flask_app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    run_bot()
