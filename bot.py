import logging
import os
import asyncio
import threading
import datetime
import pymupdf
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# !!! ВСТАВЬТЕ ВАШ НОВЫЙ ТОКЕН (после Revoke) !!!
TOKEN = os.getenv("BOT_TOKEN", "ВАШ_НОВЫЙ_ТОКЕН_СЮДА")
ADMIN_ID = 6592882382

MAX_FILE_SIZE_MB = 50
MIN_FILE_SIZE_KB = 10

# ==========================================
# ПЕРЕВОДЫ (Русский / English)
# ==========================================
LANG_RU = 'ru'
LANG_EN = 'en'
user_language = {} # user_id -> 'ru' / 'en'

TEXTS_RU = {
    'greeting': "👋 Привет! Сделай онлайн-заказ на печать.\n\n⚠️ Заказы на ненастоящие имена не выполняются!\n📝 Напишите ФИО и ИКГ (например: Иванов Иван Иванович, ИКГ-01-20)",
    'auth_success': "✅ Авторизация успешна!\n📄 Отправьте файл для печати (PDF):",
    'bad_file': "❌ Формат файла не поддерживается! Отправьте файл в формате PDF.",
    'file_too_big': "❌ Файл слишком большой! Максимум 50 МБ.",
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
    'admin_reply': "👨‍💻 Оператор: {text}",
    'working_hours': "⏰ Мы закрыты! Пн-Пт с 9:00 до 20:00."
}

TEXTS_EN = {
    'greeting': "👋 Hi! Make an online printing order.\n\n⚠️ Orders with fake names won't be accepted!\n📝 Write your Name and ID (e.g.: Ivanov Ivan Ivanovich, ICG-01-20)",
    'auth_success': "✅ Authorization successful!\n📄 Send the file to print (PDF):",
    'bad_file': "❌ File format not supported! Please send a PDF file.",
    'file_too_big': "❌ File too large! Maximum 50 MB.",
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
    'admin_reply': "👨‍💻 Operator: {text}",
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
        doc = pymupdf.open(file_path)
        total = len(doc)
        color = 0
        bw = 0
        for p in doc:
            has_color = False
            for img in p.get_images(full=True):
                try:
                    if pymupdf.Pixmap(doc, img[0]).n > 1: has_color = True; break
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

async def print_mode_choice(update, context):
    try:
        q = update.callback_query
        await q.answer()
        uid = q.from_user.id
        f = user_orders[uid][0]['files'][-1]
        if q.data == "print_all":
            f['selected_pages'] = None
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, 'color_all'), callback_data="color_all")], [InlineKeyboardButton(t(uid, 'bw_all'), callback_data="bw_all")], [InlineKeyboardButton(t(uid, 'color_specific'), callback_data="color_spec")]])
            await q.edit_message_text(t(uid, 'color_choice'), reply_markup=kb)
            return COLOR_MODE
        else:
            await q.edit_message_text(t(uid, 'choose_pages', total=f['total_pages']))
            return INPUT_PAGES
    except: return CONFIRM

async def input_pages_handler(update, context):
    try:
        uid = update.effective_user.id
        text = update.message.text.strip()
        f = user_orders[uid][0]['files'][-1]
        total = f['total_pages']
        pages = []
        try:
            for part in text.split(','):
                part = part.strip()
                if '-' in part:
                    s, e = map(int, part.split('-'))
                    if s > e or s < 1 or e > total:
                        await update.message.reply_text(t(uid, 'choose_pages', total=total))
                        return INPUT_PAGES
                    pages.extend(range(s, e+1))
                else:
                    p = int(part)
                    if p < 1 or p > total:
                        await update.message.reply_text(t(uid, 'choose_pages', total=total))
                        return INPUT_PAGES
                    pages.append(p)
        except:
            await update.message.reply_text(t(uid, 'choose_pages', total=total))
            return INPUT_PAGES
        
        f['selected_pages'] = sorted(list(set(pages)))
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, 'color_all'), callback_data="color_all")], [InlineKeyboardButton(t(uid, 'bw_all'), callback_data="bw_all")], [InlineKeyboardButton(t(uid, 'color_specific'), callback_data="color_spec")]])
        await update.message.reply_text(t(uid, 'color_choice'), reply_markup=kb)
        return COLOR_MODE
    except: return INPUT_PAGES

async def color_mode_choice(update, context):
    try:
        q = update.callback_query
        await q.answer()
        uid = q.from_user.id
        f = user_orders[uid][0]['files'][-1]
        total = len(f['selected_pages']) if f['selected_pages'] else f['total_pages']

        if q.data == "color_all":
            f['color_pages'] = f.get('actual_color_pages', total)
            f['bw_pages'] = f.get('actual_bw_pages', 0)
            await q.edit_message_text(t(uid, 'format_choice'), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("A4", callback_data="fmt_A4")], [InlineKeyboardButton("A3", callback_data="fmt_A3")], [InlineKeyboardButton("A2", callback_data="fmt_A2")], [InlineKeyboardButton("A1", callback_data="fmt_A1")], [InlineKeyboardButton("A0", callback_data="fmt_A0")]]))
            return FORMAT
        elif q.data == "bw_all":
            f['color_pages'] = 0
            f['bw_pages'] = total
            await q.edit_message_text(t(uid, 'format_choice'), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("A4", callback_data="fmt_A4")], [InlineKeyboardButton("A3", callback_data="fmt_A3")], [InlineKeyboardButton("A2", callback_data="fmt_A2")], [InlineKeyboardButton("A1", callback_data="fmt_A1")], [InlineKeyboardButton("A0", callback_data="fmt_A0")]]))
            return FORMAT
        else:
            await q.edit_message_text(t(uid, 'choose_color_pages'))
            return INPUT_COLOR_PAGES
    except: return CONFIRM

async def input_color_pages_handler(update, context):
    try:
        uid = update.effective_user.id
        text = update.message.text.strip()
        f = user_orders[uid][0]['files'][-1]
        pages_to_print = f['selected_pages'] if f['selected_pages'] else list(range(1, f['total_pages']+1))
        color_pages = []
        try:
            for part in text.split(','):
                part = part.strip()
                if '-' in part:
                    s, e = map(int, part.split('-'))
                    if s > e or s < 1 or e > f['total_pages']:
                        await update.message.reply_text(t(uid, 'choose_color_pages'))
                        return INPUT_COLOR_PAGES
                    color_pages.extend(range(s, e+1))
                else:
                    p = int(part)
                    if p < 1 or p > f['total_pages']:
                        await update.message.reply_text(t(uid, 'choose_color_pages'))
                        return INPUT_COLOR_PAGES
                    color_pages.append(p)
        except:
            await update.message.reply_text(t(uid, 'choose_color_pages'))
            return INPUT_COLOR_PAGES

        final_color = [p for p in color_pages if p in pages_to_print]
        f['color_pages'] = len(final_color)
        f['bw_pages'] = len(pages_to_print) - len(final_color)
        
        await update.message.reply_text(t(uid, 'format_choice'), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("A4", callback_data="fmt_A4")], [InlineKeyboardButton("A3", callback_data="fmt_A3")], [InlineKeyboardButton("A2", callback_data="fmt_A2")], [InlineKeyboardButton("A1", callback_data="fmt_A1")], [InlineKeyboardButton("A0", callback_data="fmt_A0")]]))
        return FORMAT
    except: return INPUT_COLOR_PAGES

async def format_choice(update, context):
    try:
        q = update.callback_query
        await q.answer()
        uid = q.from_user.id
        f = user_orders[uid][0]['files'][-1]
        f['format'] = q.data.split('_')[1]

        if f['format'] == 'A4':
            await q.edit_message_text(t(uid, 'sided_choice'), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, 'one_side'), callback_data="sided_s")], [InlineKeyboardButton(t(uid, 'two_side'), callback_data="sided_d")]]))
            return SIDED
        else:
            f['sided'] = 's'
            total = 0
            if f['color_pages'] > 0: total += f['color_pages'] * PRICES_COLOR[f['format']]
            if f['bw_pages'] > 0: total += f['bw_pages'] * PRICES_BW[f['format']]
            f['print_price'] = total
            await q.edit_message_text(t(uid, 'total_price', price=total), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes", callback_data="add_y")], [InlineKeyboardButton("❌ No", callback_data="add_n")]]))
            return ADD_FILE
    except: return CONFIRM

async def sided_choice(update, context):
    try:
        q = update.callback_query
        await q.answer()
        uid = q.from_user.id
        f = user_orders[uid][0]['files'][-1]
        f['sided'] = 's' if q.data == 'sided_s' else 'd'
        
        total = 0
        if f['color_pages'] > 0: total += f['color_pages'] * PRICES_COLOR[f['format']]
        if f['bw_pages'] > 0: total += f['bw_pages'] * PRICES_BW[f['format']]
        f['print_price'] = total

        await q.edit_message_text(t(uid, 'total_price', price=total), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes", callback_data="add_y")], [InlineKeyboardButton("❌ No", callback_data="add_n")]]))
        return ADD_FILE
    except: return CONFIRM

async def add_file_choice(update, context):
    try:
        q = update.callback_query
        await q.answer()
        uid = q.from_user.id
        if q.data == "add_y":
            await q.edit_message_text(t(uid, 'add_file'))
            return WAIT_FILE
        else:
            await q.edit_message_text(t(uid, 'fold_choice'), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes", callback_data="fold_y")], [InlineKeyboardButton("❌ No", callback_data="fold_n")]]))
            return FOLDING
    except: return CONFIRM

# ==========================================
# СКЛАДЫВАНИЕ
# ==========================================
async def folding_choice(update, context):
    try:
        q = update.callback_query
        await q.answer()
        uid = q.from_user.id
        order = user_orders[uid][0]
        if q.data == "fold_y":
            order['folding'] = True
            context.user_data['selected_folding'] = []
            
            broshure_files_idx = []
            for project in order.get('projects', []): broshure_files_idx.extend(project['files'])
            
            kb = []
            for i, f in enumerate(order['files']):
                if f['name'] is not None and f['format'] in ['A0', 'A1', 'A2', 'A3'] and i not in broshure_files_idx:
                    kb.append([InlineKeyboardButton(f"📄 {f['name']}", callback_data=f"fold_{i}")])
            
            if not kb:
                await q.edit_message_text("❌ Нет отдельных чертежей. Переходим дальше!")
                return await show_final_order(update, context)
            
            kb.append([InlineKeyboardButton("✅ Готово", callback_data="fold_done")])
            await q.edit_message_text(t(uid, 'fold_select'), reply_markup=InlineKeyboardMarkup(kb))
            return FOLDING_SELECT
        else:
            order['folding'] = False
            return await show_final_order(update, context)
    except: return CONFIRM

async def folding_select(update, context):
    try:
        q = update.callback_query
        await q.answer()
        uid = q.from_user.id
        order = user_orders[uid][0]
        if q.data == "fold_done":
            total = 0
            for idx in context.user_data['selected_folding']:
                order['files'][idx]['folding_copies'] = 1
                total += FOLDING_PRICES.get(order['files'][idx]['format'], 0)
            order['folding_files'] = context.user_data['selected_folding']
            order['folding_price'] = total
            return await show_final_order(update, context)
        else:
            idx = int(q.data.split('_')[1])
            if idx in context.user_data['selected_folding']: context.user_data['selected_folding'].remove(idx)
            else: context.user_data['selected_folding'].append(idx)
            kb = []
            for i, f in enumerate(order['files']):
                if f['name'] is not None and f['format'] in ['A0', 'A1', 'A2', 'A3']:
                    check = "✅ " if i in context.user_data['selected_folding'] else ""
                    kb.append([InlineKeyboardButton(f"{check}{f['name']}", callback_data=f"fold_{i}")])
            kb.append([InlineKeyboardButton("✅ Готово", callback_data="fold_done")])
            await q.edit_message_text(t(uid, 'fold_select'), reply_markup=InlineKeyboardMarkup(kb))
            return FOLDING_SELECT
    except: return CONFIRM

# ==========================================
# КОПИИ И БРОШЮРОВКА
# ==========================================
async def show_final_order(update, context):
    try:
        uid = update.effective_user.id
        order = user_orders[uid][0]
        response = "📊 ИТОГОВЫЙ ЗАКАЗ:\n"
        for i, f in enumerate(order['files']):
            if f['name'] is not None:
                side = 'Односторонняя' if f['sided'] == 's' else 'Двусторонняя'
                response += f"📄 Файл #{i+1}: {f['name']}\n"
                response += f"  📐 {f['format']} | {side}\n"
                response += f"  🎨 Цветных: {f['color_pages']} | ЧБ: {f['bw_pages']}\n"
                response += f"  💰 {f['print_price']} руб.\n"
        
        if order.get('folding', False) and order.get('folding_files'):
            response += f"\n📐 Складывание: {order['folding_price']} руб.\n"
        
        context.user_data['copy_index'] = 0
        first_name = order['files'][0]['name']
        msg = f"{response}\n\n" + t(uid, 'copies_header', name=first_name)

        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return PRINT_COPIES
    except: return CONFIRM

async def print_copies_handler(update, context):
    try:
        uid = update.effective_user.id
        txt = update.message.text.strip()
        if not txt.isdigit() or int(txt) <= 0:
            await update.message.reply_text("❌ Enter a number > 0.")
            return PRINT_COPIES
        copies = int(txt)
        order = user_orders[uid][0]
        idx = context.user_data['copy_index']
        order['files'][idx]['copies'] = copies
        idx += 1
        if idx < len(order['files']):
            context.user_data['copy_index'] = idx
            await update.message.reply_text(t(uid, 'copies_next', copies=copies, num=idx+1, name=order['files'][idx]['name']))
            return PRINT_COPIES
        else:
            await update.message.reply_text("✅ Copies set!")
            await update.message.reply_text(t(uid, 'brochure_count'))
            return SET_BROCHURE_COUNT
    except: return CONFIRM

async def set_brochure_count_handler(update, context):
    try:
        uid = update.effective_user.id
        txt = update.message.text.strip()
        if not txt.isdigit():
            await update.message.reply_text("❌ Enter 0, 1, 2...")
            return SET_BROCHURE_COUNT
        count = int(txt)
        order = user_orders[uid][0]
        order['projects'] = []
        if count == 0:
            await update.message.reply_text(t(uid, 'no_brochure'))
            await update.message.reply_text(t(uid, 'time_choice'), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚡ Экспресс", callback_data="time_express")], [InlineKeyboardButton("⏱ 1 час", callback_data="time_1h")], [InlineKeyboardButton("⏰ 3 часа", callback_data="time_3h")], [InlineKeyboardButton("📅 День", callback_data="time_day")]]))
            return READY_TIME
        context.user_data['total_projects'] = count
        context.user_data['current_project_index'] = 1
        await show_project_setup(update, context)
        return SETUP_BROCHURE
    except: return CONFIRM

async def show_project_setup(update, context):
    try:
        uid = update.effective_user.id
        order = user_orders[uid][0]
        num = context.user_data['current_project_index']
        used = []
        for p in order['projects']: used.extend(p['files'])
        
        avail = []
        for i, f in enumerate(order['files']):
            if i not in used and f['name'] is not None: avail.append(i)
        if not avail:
            context.user_data['current_project_index'] = context.user_data['total_projects'] + 1
            await context.bot.send_message(chat_id=update.effective_chat.id, text=t(uid, 'fold_choice'), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes", callback_data="fold_y")], [InlineKeyboardButton("❌ No", callback_data="fold_n")]]))
            return FOLDING
        
        kb = []
        for i in avail:
            if i in context.user_data['temp_project_files']:
                kb.append([InlineKeyboardButton(f"✅ {context.user_data['temp_project_files'].index(i)+1}. {order['files'][i]['name']}", callback_data=f"proj_{i}")])
            else:
                kb.append([InlineKeyboardButton(f"⬜ {order['files'][i]['name']}", callback_data=f"proj_{i}")])
        kb.append([InlineKeyboardButton("✅ Done", callback_data="proj_done")])
        await context.bot.send_message(chat_id=update.effective_chat.id, text=t(uid, 'choose_brochure', num=num), reply_markup=InlineKeyboardMarkup(kb))
    except: return CONFIRM

async def brochure_setup_handler(update, context):
    try:
        q = update.callback_query
        await q.answer()
        uid = q.from_user.id
        if q.data == "proj_done":
            if not context.user_data['temp_project_files']:
                await q.edit_message_text("❌ No files chosen!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="proj_back")]]))
                return SETUP_BROCHURE
            await q.edit_message_text(t(uid, 'brochure_type'), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, 'spring'), callback_data="btype_spring")], [InlineKeyboardButton(t(uid, 'string'), callback_data="btype_string")]]))
            return SETUP_BROCHURE_TYPE
        elif q.data == "proj_back":
            await q.edit_message_text(t(uid, 'brochure_count'))
            return SET_BROCHURE_COUNT
        elif q.data.startswith("proj_"):
            idx = int(q.data.split('_')[1])
            if idx in context.user_data['temp_project_files']: context.user_data['temp_project_files'].remove(idx)
            else: context.user_data['temp_project_files'].append(idx)
            order = user_orders[uid][0]
            used = []
            for p in order['projects']: used.extend(p['files'])
            kb = []
            for i, f in enumerate(order['files']):
                if i not in used and f['name'] is not None:
                    if i in context.user_data['temp_project_files']:
                        kb.append([InlineKeyboardButton(f"✅ {context.user_data['temp_project_files'].index(i)+1}. {f['name']}", callback_data=f"proj_{i}")])
                    else:
                        kb.append([InlineKeyboardButton(f"⬜ {f['name']}", callback_data=f"proj_{i}")])
            kb.append([InlineKeyboardButton("✅ Done", callback_data="proj_done")])
            await q.edit_message_text(t(uid, 'choose_brochure', num=context.user_data['current_project_index']), reply_markup=InlineKeyboardMarkup(kb))
            return SETUP_BROCHURE
    except: return CONFIRM

async def brochure_type_handler(update, context):
    try:
        q = update.callback_query
        await q.answer()
        uid = q.from_user.id
        btype = 'Spring' if q.data == 'btype_spring' else 'String'
        order = user_orders[uid][0]
        order['projects'].append({'files': context.user_data['temp_project_files'], 'type': btype, 'copies': 1})
        context.user_data['temp_project_files'] = []
        
        if context.user_data['current_project_index'] < context.user_data['total_projects']:
            context.user_data['current_project_index'] += 1
            await q.edit_message_text("✅ Brochure done!")
            await show_project_setup(update, context)
            return SETUP_BROCHURE
        else:
            await q.edit_message_text("✅ All brochures done!")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=t(uid, 'fold_choice'), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes", callback_data="fold_y")], [InlineKeyboardButton("❌ No", callback_data="fold_n")]]))
            return FOLDING
    except: return CONFIRM

# ==========================================
# ВРЕМЯ, БЕЧЕВКА, ПОДТВЕРЖДЕНИЕ
# ==========================================
async def time_choice(update, context):
    try:
        q = update.callback_query
        await q.answer()
        uid = q.from_user.id
        order = user_orders[uid][0]
        time_map = {'time_1h': '1h', 'time_3h': '3h', 'time_day': 'Day', 'time_express': 'Express'}
        order['ready_time'] = time_map[q.data]
        total = 0
        for f in order['files']:
            if f['name'] is not None: total += f['print_price'] * f['copies']
        if q.data == 'time_express': total = int(total * 1.3)
        order['total_price'] = total
        await q.edit_message_text(f"💰 Итог: {total} руб.")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🧵 Сколько штук бечевки? (0 если не нужно):")
        return STRING_COPIES
    except: return CONFIRM

async def string_copies_handler(update, context):
    try:
        uid = update.effective_user.id
        txt = update.message.text.strip()
        if not txt.isdigit():
            await update.message.reply_text("❌ Enter 0, 1, 2...")
            return STRING_COPIES
        strings = int(txt)
        order = user_orders[uid][0]
        order['string_copies'] = strings
        order['string'] = strings > 0
        order['string_price'] = 0

        response = "📊 ОКОНЧАТЕЛЬНЫЙ РАСЧЕТ:\n"
        for f in order['files']:
            if f['name'] is not None:
                response += f"📄 {f['name']} — {f['copies']} копий.\n"
        response += f"💰 ИТОГО: {order['total_price']} руб.\n"
        response += f"⏱ Готовность: {order['ready_time']}\n"
        response += "\nГотовы заказать?"
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, 'final_confirm'), callback_data="confirm_y")], [InlineKeyboardButton(t(uid, 'final_cancel'), callback_data="confirm_n")]])
        await update.message.reply_text(response, reply_markup=kb)
        return CONFIRM
    except: return CONFIRM

async def confirm_choice(update, context):
    try:
        q = update.callback_query
        await q.answer()
        uid = q.from_user.id
        if q.data == "confirm_y":
            await send_order_to_admin(update, context, uid, user_orders[uid][0])
            return ConversationHandler.END
        else:
            if uid in user_orders:
                for f in user_orders[uid][0]['files']:
                    try:
                        if f.get('path'): os.remove(f['path'])
                    except: pass
                del user_orders[uid]
            await q.edit_message_text("❌ Заказ отменен. Нажмите /start")
            return ConversationHandler.END
    except: return ConversationHandler.END

async def send_order_to_admin(update, context, uid, order):
    try:
        total = order['total_price']
        admin_msg = f"🆕 НОВЫЙ ЗАКАЗ!\n👤 Клиент: {order['user_info']}\n🆔 ID: {uid}\n⏱ Готовность: {order['ready_time']}\n\n"
        admin_msg += "🖨 ПЕЧАТЬ:\n"
        for i, f in enumerate(order['files']):
            if f['name'] is not None:
                side = 'Односторонняя' if f['sided'] == 's' else 'Двусторонняя'
                admin_msg += f"Файл #{i+1}: {f['name']} ({f['format']}, {side}, Цв:{f['color_pages']}, ЧБ:{f['bw_pages']}) - {f['copies']} копий.\n"
        
        if order.get('projects'):
            admin_msg += "\n📚 БРОШЮРЫ:\n"
            for idx, p in enumerate(order['projects'], 1):
                admin_msg += f"Брошюра #{idx} ({p['type']}):\n"
                for fi in p['files']:
                    f = order['files'][fi]
                    admin_msg += f"  - {f['name']} ({f['format']})\n"
        
        if order.get('folding', False) and order.get('folding_files'):
            admin_msg += "\n📐 СКЛАДЫВАНИЕ:\n"
            for fi in order['folding_files']:
                f = order['files'][fi]
                admin_msg += f"  - {f['name']} ({f['format']})\n"

        admin_msg += f"\n💵 ИТОГО: {total} руб."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Готов", callback_data=f"ready_{uid}")],
            [InlineKeyboardButton("📦 Выдан", callback_data=f"issue_{uid}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{uid}")]
        ])
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=kb)
        
        for f in order['files']:
            if f.get('path') and os.path.exists(f['path']):
                try:
                    with open(f['path'], 'rb') as doc:
                        await context.bot.send_document(chat_id=ADMIN_ID, document=doc, caption=f"📎 {f['name']}")
                except: pass
        await update.effective_message.reply_text(f"✅ ЗАКАЗ ПРИНЯТ! Сумма: {total} руб.")
    except Exception as e:
        logger.error(f"Ошибка отправки админу: {e}")
    finally:
        for f in order['files']:
            try:
                if f.get('path'): os.remove(f['path'])
            except: pass

# ==========================================
# ОТЗЫВЫ, ОПЕРАТОР И АДМИН
# ==========================================
async def issue_client(update, context):
    try:
        q = update.callback_query
        await q.answer()
        if update.effective_user.id != ADMIN_ID:
            await q.answer("Нет прав!", show_alert=True)
            return
        if not is_business_hours():
            await q.answer("Выдача только с 9:00 до 20:00 (Пн-Пт)!", show_alert=True)
            return
        client_id = int(q.data.split('_')[1])
        await context.bot.send_message(chat_id=client_id, text=t(client_id, 'feedback_ask'))
        client_feedback_states[client_id] = {'state': 'waiting_rating', 'rating': None}
        await q.edit_message_text(text=q.message.text + "\n\n✅ Клиент уведомлен о выдаче.")
    except: pass

async def feedback_rating_handler(update, context):
    try:
        uid = update.effective_user.id
        if uid not in client_feedback_states or client_feedback_states[uid]['state'] != 'waiting_rating': return
        if not update.message.text.strip().isdigit() or int(update.message.text) < 1 or int(update.message.text) > 10:
            await update.message.reply_text("❌ Введите число от 1 до 10.")
            return
        client_feedback_states[uid] = {'state': 'waiting_comment', 'rating': int(update.message.text)}
        await update.message.reply_text(t(uid, 'feedback_comment'))
    except: pass

async def feedback_comment_handler(update, context):
    try:
        uid = update.effective_user.id
        if uid not in client_feedback_states or client_feedback_states[uid]['state'] != 'waiting_comment': return
        comment = update.message.text.strip() if update.message.text.strip() else '-'
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"⭐ ОТЗЫВ ОТ {uid}:\nОценка: {client_feedback_states[uid]['rating']}/10\nКомментарий: {comment}")
        await update.message.reply_text(t(uid, 'feedback_thanks'))
        del client_feedback_states[uid]
    except: pass

async def unsupported_text(update, context):
    try:
        uid = update.effective_user.id
        if uid in client_feedback_states: return ConversationHandler.END
        if update.message.text.startswith('/'): return ConversationHandler.END
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, 'operator_yes'), callback_data="op_y")], [InlineKeyboardButton(t(uid, 'operator_no'), callback_data="op_n")]])
        await update.message.reply_text(t(uid, 'operator_text'), reply_markup=kb)
        return WAIT_OPERATOR
    except: return ConversationHandler.END

async def operator_choice(update, context):
    try:
        q = update.callback_query
        await q.answer()
        uid = q.from_user.id
        if q.data == "op_y":
            await q.edit_message_text("✅ Перевод на оператора.")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"👤 Пользователь {uid} просит оператора.")
            return WAIT_OPERATOR
        else:
            await q.edit_message_text("ОК! Отправьте PDF или /start")
            return ConversationHandler.END
    except: return ConversationHandler.END

async def operator_chat(update, context):
    try:
        uid = update.effective_user.id
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"📩 {uid}: {update.message.text}")
        await update.message.reply_text("✅ Отправлено оператору.")
        return WAIT_OPERATOR
    except: return WAIT_OPERATOR

async def reply_to_client(update, context):
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Нет прав.")
            return
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("❌ Формат: /reply <ID> <текст>")
            return
        client_id = int(args[0])
        reply_text = " ".join(args[1:])
        # Отправляем текст как есть (русский, английский, что угодно)
        await context.bot.send_message(chat_id=client_id, text=f"👨‍💻 {reply_text}")
        await update.message.reply_text(f"✅ Отправлено клиенту {client_id}.")
    except Exception as e:
        logger.error(f"Ошибка reply: {e}")
        await update.message.reply_text("❌ Ошибка!")

async def notify_client(update, context):
    try:
        q = update.callback_query
        await q.answer()
        if q.from_user.id != ADMIN_ID:
            await q.answer("Нет прав!", show_alert=True)
            return
        client_id = int(q.data.split('_')[1])
        await context.bot.send_message(chat_id=client_id, text="🎉 ВАШ ЗАКАЗ ГОТОВ! Заберите его в печатке в УЛБ.")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ Клиент {client_id} уведомлен.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📦 Выдать", callback_data=f"issue_{client_id}")], [InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{client_id}")]]))
    except: pass

async def cancel(update, context):
    try:
        uid = update.effective_user.id
        if uid in user_orders:
            for f in user_orders[uid][0]['files']:
                try:
                    if f.get('path'): os.remove(f['path'])
                except: pass
            del user_orders[uid]
        await update.message.reply_text("❌ Заказ отменен. Нажмите /start")
        return ConversationHandler.END
    except: return ConversationHandler.END

# ... (админ команды test, sendtest остаются для отладки, но не критичны) ...

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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_rating_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_comment_handler))
    application.add_handler(CallbackQueryHandler(issue_client, pattern="^issue_"))
    application.add_handler(CallbackQueryHandler(notify_client, pattern="^ready_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_to_client)) # Fallback for /reply
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