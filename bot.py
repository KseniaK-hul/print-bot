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

# Состояния (ИСПРАВЛЕНО: Ровно 19, соответствует range(19))
(AUTH, WAIT_FILE, FORMAT, SIDED, ADD_FILE, FOLDING, FOLDING_SELECT, 
 READY_TIME, CONFIRM, WAIT_OPERATOR, PRINT_COPIES, STRING_COPIES, 
 PRINT_MODE, INPUT_PAGES, COLOR_MODE, INPUT_COLOR_PAGES, 
 SET_BROCHURE_COUNT, SETUP_BROCHURE, SETUP_BROCHURE_TYPE) = range(19)

# Цены
PRICES_COLOR = {'A4': 60, 'A3': 140, 'A2': 300, 'A1': 500, 'A0': 1000}
PRICES_BW = {'A4': 18, 'A3': 60, 'A2': 200, 'A1': 300, 'A0': 600}
FOLDING_PRICES = {'A0': 100, 'A1': 50, 'A2': 30, 'A3': 10}
FOLDABLE_FORMATS = ['A0', 'A1', 'A2', 'A3']

user_orders = {}
admin_cancel_states = {}
client_feedback_states = {}

# --- ПРОВЕРКА РАБОЧЕГО ВРЕМЕНИ (Пн-Пт, 9:00-20:00 МСК) ---
def is_business_hours():
    try:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_msk = now_utc + datetime.timedelta(hours=3)
        if now_msk.weekday() >= 5:  # Суббота/Воскресенье
            return False
        if now_msk.hour < 9 or now_msk.hour >= 20:
            return False
        return True
    except Exception:
        return True  # В случае ошибки разрешаем работу

# --- АНАЛИЗ ЦВЕТОВ ---
def analyze_pdf_colors(file_path):
    try:
        doc = pymupdf.open(file_path)
        total_pages = len(doc)
        color_pages = 0
        bw_pages = 0
        for page_num in range(total_pages):
            page = doc[page_num]
            images = page.get_images(full=True)
            has_color = False
            for img in images:
                try:
                    xref = img[0]
                    pix = pymupdf.Pixmap(doc, xref)
                    if pix.n > 1:
                        has_color = True
                        break
                except: continue
            if not has_color:
                text_instances = page.get_text("dict")
                for block in text_instances.get("blocks", []):
                    if "lines" in block:
                        for line in block["lines"]:
                            for span in line.get("spans", []):
                                if span.get("color") not in [0, 0x000000, 0xFFFFFF, 0xFF000000]:
                                    has_color = True
                                    break
                            if has_color: break
                    if has_color: break
            if has_color: color_pages += 1
            else: bw_pages += 1
        doc.close()
        return total_pages, color_pages, bw_pages
    except Exception as e:
        logger.error(f"Ошибка анализа цветов: {e}")
        return 0, 0, 0

def calculate_brochure_price(format_type, total_pages):
    try:
        if format_type == 'A4':
            if total_pages <= 20: return 150
            elif total_pages <= 40: return 200
            elif total_pages <= 60: return 250
            elif total_pages <= 80: return 300
            elif total_pages <= 100: return 350
            else: return 350 + (((total_pages - 80) + 19) // 20 * 50)
        elif format_type == 'A3':
            if total_pages <= 20: return 300
            else: return 300 + ((total_pages - 20) * 10)
        elif format_type in ['A0', 'A1', 'A2']:
            return 250
        return 0
    except Exception:
        return 0

# --- ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка при обработке: {context.error}", exc_info=True)
    try:
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ **Произошла ошибка в боте:**\n{context.error}\n\nБот продолжает работать.")
    except Exception:
        pass
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте еще раз или напишите /start.")
    except Exception:
        pass

# --- СТАРТ И АВТОРИЗАЦИЯ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        if not is_business_hours():
            await update.message.reply_text(
                "⏰ Мы закрыты!\n"
                "Наш график работы:\n"
                "Понедельник - Пятница с 9:00 до 20:00\n"
                "В выходные мы не работаем."
            )
            return ConversationHandler.END
        
        user_orders[user_id] = [{'user_info': 'Unknown', 'files': [], 'projects': [], 'folding': False, 'folding_files': [], 'folding_price': 0, 'string': False, 'string_price': 0, 'string_copies': 0, 'ready_time': None, 'total_price': 0, 'is_express': False, 'express_fee': 0}]
        context.user_data['selected_folding'] = []
        context.user_data['copy_index'] = 0
        
        await update.message.reply_text(
            "👋 Привет! Сделай онлайн-заказ на печать.\n\n"
            "⚠️ Важно: Заказы на ненастоящие имена не выполняются!\n"
            "Укажите реальные ФИО и ИКГ.\n\n"
            f"📦 Максимальный объем файла: {MAX_FILE_SIZE_MB} МБ.\n"
            f"📄 Минимальный размер файла: {MIN_FILE_SIZE_KB} КБ.\n\n"
            "🔧 **Бот не вносит правки в файлы.**\n"
            "Если нужны правки, сделайте их самостоятельно по ссылке:\n"
            "https://smallpdf.com/ru/edit-pdf\n\n"
            "📄 **Если у вас нет PDF-файла**, его можно сконвертировать здесь:\n"
            "https://smallpdf.com/ru/pdf-converter\n\n"
            "🎮 **Управление:**\n"
            "• Отменить заказ: /cancel\n"
            "• Начать заново: /start\n\n"
            "📝 Для начала авторизуйся:\n"
            "Напишите ФИО и ИКГ (например: Иванов Иван Иванович, ИКГ-01-20)"
        )
        return AUTH
    except Exception as e:
        logger.error(f"Ошибка в start: {e}")
        return ConversationHandler.END

async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        # Сохраняем текст на любом языке (кириллица или латиница)
        user_orders[user_id][0]['user_info'] = update.message.text
        await update.message.reply_text("✅ Авторизация успешна!\nТеперь отправьте файл для печати (PDF):")
        return WAIT_FILE
    except Exception as e:
        logger.error(f"Ошибка в auth: {e}")
        await update.message.reply_text("❌ Ошибка при авторизации. Нажмите /start заново.")
        return ConversationHandler.END

# --- ОБРАБОТКА ФАЙЛА (ЛЮБОЙ ДОКУМЕНТ) ---
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        document = update.message.document
        # Проверка на PDF
        if not document or not document.file_name.lower().endswith('.pdf'):
            await update.message.reply_text("❌ Формат файла не поддерживается! Отправьте файл в формате PDF.")
            return WAIT_FILE

        max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
        if document.file_size and document.file_size > max_bytes:
            await update.message.reply_text(f"❌ Файл слишком большой! Максимум {MAX_FILE_SIZE_MB} МБ.")
            return WAIT_FILE
            
        min_bytes = MIN_FILE_SIZE_KB * 1024
        if document.file_size and document.file_size < min_bytes:
            await update.message.reply_text(f"❌ Файл слишком маленький! Минимум {MIN_FILE_SIZE_KB} КБ.")
            return WAIT_FILE

        file = await context.bot.get_file(document.file_id)
        os.makedirs(f"temp_{user_id}", exist_ok=True)
        safe_filename = f"{user_id}_{document.file_id}.pdf"
        file_path = os.path.join(f"temp_{user_id}", safe_filename)
        
        try:
            await file.download_to_drive(file_path)
        except Exception:
            await update.message.reply_text("❌ Не удалось скачать файл. Попробуйте отправить его еще раз.")
            return WAIT_FILE

        total_pages, actual_color_pages, actual_bw_pages = await asyncio.to_thread(analyze_pdf_colors, file_path)
        
        if total_pages == 0:
            await update.message.reply_text("❌ Не удалось прочитать PDF. Попробуйте другой.")
            if os.path.exists(file_path): os.remove(file_path)
            return WAIT_FILE
        
        current_order = user_orders[user_id][0]
        current_order['files'].append({
            'path': file_path, 'name': document.file_name, 'total_pages': total_pages,
            'actual_color_pages': actual_color_pages, 
            'actual_bw_pages': actual_bw_pages,
            'format': None, 'sided': None, 'print_price': 0, 
            'copies': 1, 'folding_copies': 1,
            'selected_pages': None, 'color_pages': 0, 'bw_pages': 0
        })
        
        await update.message.reply_text(
            f"✅ Файл принят! Всего страниц: {total_pages}\n"
            f"🎨 Реально цветных: {actual_color_pages} | ⚫ ЧБ: {actual_bw_pages}\n\n"
            "Как напечатать этот файл?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 Все страницы", callback_data="print_all")],
                [InlineKeyboardButton("✂️ Конкретные страницы", callback_data="print_specific")]
            ])
        )
        return PRINT_MODE
    except Exception as e:
        logger.error(f"Ошибка в handle_file: {e}")
        await update.message.reply_text("❌ Произошла ошибка при обработке файла. Попробуйте отправить другой файл или нажмите /start.")
        return ConversationHandler.END

async def print_mode_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        current_order = user_orders[user_id][0]
        file_data = current_order['files'][-1]
        
        if query.data == "print_all":
            file_data['selected_pages'] = None
            await query.edit_message_text("🎨 Как напечатать эти страницы?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎨 Все цветом", callback_data="color_mode_all_color")],
                    [InlineKeyboardButton("⚫ Все ЧБ", callback_data="color_mode_all_bw")],
                    [InlineKeyboardButton("📝 Указать страницы цветом", callback_data="color_mode_specific")]
                ])
            )
            return COLOR_MODE
        else:
            await query.edit_message_text(
                f"📝 Введите номера страниц через запятую (например: 1,3,5-7).\nВсего страниц в файле: {file_data['total_pages']}"
            )
            return INPUT_PAGES
    except Exception as e:
        logger.error(f"Ошибка в print_mode_choice: {e}")
        return CONFIRM

async def input_pages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        text = update.message.text.strip()
        current_order = user_orders[user_id][0]
        file_data = current_order['files'][-1]
        total = file_data['total_pages']
        
        pages = []
        try:
            for part in text.split(','):
                part = part.strip()
                if '-' in part:
                    start, end = part.split('-')
                    s, e = int(start), int(end)
                    if s > e or s < 1 or e > total:
                        await update.message.reply_text(f"❌ Неверный диапазон. Страниц в файле всего: {total}.")
                        return INPUT_PAGES
                    pages.extend(range(s, e + 1))
                else:
                    p = int(part)
                    if p < 1 or p > total:
                        await update.message.reply_text(f"❌ Страница {p} не существует. Всего страниц: {total}.")
                        return INPUT_PAGES
                    pages.append(p)
        except:
            await update.message.reply_text("❌ Пожалуйста, введите корректные номера страниц (например: 1,3,5-7).")
            return INPUT_PAGES
        
        file_data['selected_pages'] = sorted(list(set(pages)))
        
        await update.message.reply_text(
            f"✅ Выбрано страниц: {len(file_data['selected_pages'])}.\n\n🎨 Как напечатать эти страницы?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎨 Все цветом", callback_data="color_mode_all_color")],
                [InlineKeyboardButton("⚫ Все ЧБ", callback_data="color_mode_all_bw")],
                [InlineKeyboardButton("📝 Указать страницы цветом", callback_data="color_mode_specific")]
            ])
        )
        return COLOR_MODE
    except Exception as e:
        logger.error(f"Ошибка в input_pages_handler: {e}")
        await update.message.reply_text("❌ Ошибка. Попробуйте ещё раз.")
        return INPUT_PAGES

async def color_mode_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        current_order = user_orders[user_id][0]
        file_data = current_order['files'][-1]
        
        total_to_print = len(file_data['selected_pages']) if file_data['selected_pages'] else file_data['total_pages']
        
        if query.data == "color_mode_all_color":
            file_data['color_pages'] = file_data.get('actual_color_pages', total_to_print)
            file_data['bw_pages'] = file_data.get('actual_bw_pages', 0)
            await query.edit_message_text("📐 Какой формат листа нужен?",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("A4", callback_data="format_A4")], [InlineKeyboardButton("A3", callback_data="format_A3")], [InlineKeyboardButton("A2", callback_data="format_A2")], [InlineKeyboardButton("A1", callback_data="format_A1")], [InlineKeyboardButton("A0", callback_data="format_A0")]]))
            return FORMAT
        elif query.data == "color_mode_all_bw":
            file_data['color_pages'] = 0
            file_data['bw_pages'] = total_to_print
            await query.edit_message_text("📐 Какой формат листа нужен?",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("A4", callback_data="format_A4")], [InlineKeyboardButton("A3", callback_data="format_A3")], [InlineKeyboardButton("A2", callback_data="format_A2")], [InlineKeyboardButton("A1", callback_data="format_A1")], [InlineKeyboardButton("A0", callback_data="format_A0")]]))
            return FORMAT
        else:
            await query.edit_message_text(
                f"📝 Введите номера страниц, которые будут ЦВЕТНЫМИ (остальные станут ЧБ).\nВсего страниц к печати: {total_to_print}"
            )
            return INPUT_COLOR_PAGES
    except Exception as e:
        logger.error(f"Ошибка в color_mode_choice: {e}")
        return CONFIRM

async def input_color_pages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        text = update.message.text.strip()
        current_order = user_orders[user_id][0]
        file_data = current_order['files'][-1]
        
        pages_to_print = file_data['selected_pages'] if file_data['selected_pages'] else list(range(1, file_data['total_pages'] + 1))
        
        color_page_list = []
        try:
            for part in text.split(','):
                part = part.strip()
                if '-' in part:
                    start, end = part.split('-')
                    s, e = int(start), int(end)
                    if s > e or s < 1 or e > file_data['total_pages']:
                        await update.message.reply_text(f"❌ Неверный диапазон страниц.")
                        return INPUT_COLOR_PAGES
                    color_page_list.extend(range(s, e + 1))
                else:
                    p = int(part)
                    if p < 1 or p > file_data['total_pages']:
                        await update.message.reply_text("❌ Неверный номер страницы.")
                        return INPUT_COLOR_PAGES
                    color_page_list.append(p)
        except:
            await update.message.reply_text("❌ Введите корректные номера страниц.")
            return INPUT_COLOR_PAGES
        
        final_color_pages = [p for p in color_page_list if p in pages_to_print]
        file_data['color_pages'] = len(final_color_pages)
        file_data['bw_pages'] = len(pages_to_print) - len(final_color_pages)
        
        await update.message.reply_text(
            f"✅ Цветных: {len(final_color_pages)} | ЧБ: {len(pages_to_print) - len(final_color_pages)}.\n\n📐 Какой формат листа нужен?",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("A4", callback_data="format_A4")], [InlineKeyboardButton("A3", callback_data="format_A3")], [InlineKeyboardButton("A2", callback_data="format_A2")], [InlineKeyboardButton("A1", callback_data="format_A1")], [InlineKeyboardButton("A0", callback_data="format_A0")]]))
        return FORMAT
    except Exception as e:
        logger.error(f"Ошибка в input_color_pages_handler: {e}")
        await update.message.reply_text("❌ Ошибка. Попробуйте ещё раз.")
        return INPUT_COLOR_PAGES

async def format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        format_type = query.data.split('_')[1]
        current_order = user_orders[user_id][0]
        file_data = current_order['files'][-1]
        file_data['format'] = format_type
        
        if format_type == 'A4':
            await query.edit_message_text(f"📐 Формат {format_type} выбран.\n📄 Печать будет односторонней или двусторонней?", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("1️⃣ Односторонняя", callback_data="sided_single")], [InlineKeyboardButton("2️⃣ Двусторонняя", callback_data="sided_double")]]))
            return SIDED
        else:
            file_data['sided'] = 'single'
            total_price = 0
            if file_data['color_pages'] > 0: total_price += file_data['color_pages'] * PRICES_COLOR[format_type]
            if file_data['bw_pages'] > 0: total_price += file_data['bw_pages'] * PRICES_BW[format_type]
            file_data['print_price'] = total_price
            
            await query.edit_message_text(f"✅ Итого за файл: {total_price} руб.\nХотите добавить ещё файл?", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Да", callback_data="add_yes")], [InlineKeyboardButton("❌ Нет", callback_data="add_no")]]))
            return ADD_FILE
    except Exception as e:
        logger.error(f"Ошибка в format_choice: {e}")
        return CONFIRM

async def sided_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        current_order = user_orders[user_id][0]
        file_data = current_order['files'][-1]
        file_data['sided'] = query.data.split('_')[1]
        
        format_type = file_data['format']
        total_price = 0
        if file_data['color_pages'] > 0: total_price += file_data['color_pages'] * PRICES_COLOR[format_type]
        if file_data['bw_pages'] > 0: total_price += file_data['bw_pages'] * PRICES_BW[format_type]
        file_data['print_price'] = total_price
        
        await query.edit_message_text(f"✅ Итого за файл: {total_price} руб.\nХотите добавить ещё файл?", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Да", callback_data="add_yes")], [InlineKeyboardButton("❌ Нет", callback_data="add_no")]]))
        return ADD_FILE
    except Exception as e:
        logger.error(f"Ошибка в sided_choice: {e}")
        return CONFIRM

async def add_file_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        
        if query.data == "add_yes":
            await query.edit_message_text("📄 Отправьте следующий файл:")
            return WAIT_FILE
        else:
            await query.edit_message_text("📐 Нужно ли сложить чертежи?", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Да", callback_data="folding_yes")], [InlineKeyboardButton("❌ Нет", callback_data="folding_no")]]))
            return FOLDING
    except Exception as e:
        logger.error(f"Ошибка в add_file_choice: {e}")
        return CONFIRM

# --- СКЛАДЫВАНИЕ ЧЕРТЕЖЕЙ (ТОЛЬКО ВНЕ БРОШЮР) ---
async def folding_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        current_order = user_orders[user_id][0]
        
        if query.data == "folding_yes":
            current_order['folding'] = True
            context.user_data['selected_folding'] = []
            
            broshure_files_idx = []
            for project in current_order.get('projects', []):
                broshure_files_idx.extend(project['files'])
                
            keyboard = []
            for i, file in enumerate(current_order['files']):
                if file['name'] is not None and file['format'] in FOLDABLE_FORMATS:
                    if i not in broshure_files_idx:
                        keyboard.append([InlineKeyboardButton(f"📄 {file['name']} ({file['format']})", callback_data=f"folding_{i}")])
            
            if not keyboard:
                await query.edit_message_text("❌ Нет отдельных чертежей для складывания (все в брошюре). Переходим дальше!")
                return await show_final_order(update, context)
                
            keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="folding_done")])
            await query.edit_message_text("📐 Выберите отдельные чертежи для складывания (доступны только те, что не в брошюре A0-A3):", reply_markup=InlineKeyboardMarkup(keyboard))
            return FOLDING_SELECT
        else:
            current_order['folding'] = False
            return await show_final_order(update, context)
    except Exception as e:
        logger.error(f"Ошибка в folding_choice: {e}")
        return CONFIRM

async def folding_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        current_order = user_orders[user_id][0]
        
        if query.data == "folding_done":
            if not context.user_data['selected_folding']:
                await query.edit_message_text("❌ Вы не выбрали ни одного файла.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="folding_back")]]))
                return FOLDING_SELECT
            
            total_fold_price = 0
            for idx in context.user_data['selected_folding']:
                current_order['files'][idx]['folding_copies'] = 1
                total_fold_price += FOLDING_PRICES.get(current_order['files'][idx]['format'], 0) * 1
            current_order['folding_files'] = context.user_data['selected_folding']
            current_order['folding_price'] = total_fold_price
            
            await query.edit_message_text(f"💰 Складывание: {total_fold_price} руб.")
            return await show_final_order(update, context)
        elif query.data == "folding_back":
            await query.edit_message_text("📐 Нужно ли сложить чертежи?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Да", callback_data="folding_yes")], [InlineKeyboardButton("❌ Нет", callback_data="folding_no")]]))
            return FOLDING
        else:
            file_idx = int(query.data.split('_')[1])
            if file_idx in context.user_data['selected_folding']: context.user_data['selected_folding'].remove(file_idx)
            else: context.user_data['selected_folding'].append(file_idx)
            keyboard = []
            for i, file in enumerate(current_order['files']):
                if file['name'] is not None and file['format'] in FOLDABLE_FORMATS:
                    check = "✅ " if i in context.user_data['selected_folding'] else ""
                    keyboard.append([InlineKeyboardButton(f"{check}{file['name']}", callback_data=f"folding_{i}")])
            keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="folding_done")])
            await query.edit_message_text("📐 Выберите файлы для складывания:", reply_markup=InlineKeyboardMarkup(keyboard))
            return FOLDING_SELECT
    except Exception as e:
        logger.error(f"Ошибка в folding_select: {e}")
        return CONFIRM

# --- ИТОГ И КОПИИ ПЕЧАТИ ---
async def show_final_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        current_order = user_orders[user_id][0]
        
        response = "📊 ИТОГОВЫЙ ЗАКАЗ:\n"
        file_num = 1
        for file_data in current_order['files']:
            if file_data['name'] is not None:
                side = 'Односторонняя' if file_data['sided'] == 'single' else 'Двусторонняя'
                response += f"📄 Файл #{file_num}: {file_data['name']}\n"
                if file_data['selected_pages']:
                    response += f"  📄 Страницы: {', '.join(map(str, file_data['selected_pages']))}\n"
                else:
                    response += f"  📄 Все страницы\n"
                response += f"  📐 {file_data['format']} | {side}\n"
                response += f"  🎨 Цветных: {file_data['color_pages']} | ЧБ: {file_data['bw_pages']}\n"
                response += f"  💰 {file_data['print_price']} руб.\n"
                file_num += 1
        
        if current_order.get('folding', False) and current_order.get('folding_files'):
            response += f"\n📐 СКЛАДЫВАНИЕ ЧЕРТЕЖЕЙ:\n"
            for idx in current_order['folding_files']:
                f = current_order['files'][idx]
                p = FOLDING_PRICES.get(f['format'], 0)
                response += f"  {f['name']} ({f['format']}) x {f['folding_copies']} шт. - {p * f['folding_copies']} руб.\n"
            response += f"  Итого: {current_order['folding_price']} руб.\n"
        
        context.user_data['copy_index'] = 0
        first_file_name = current_order['files'][0]['name']
        
        message = f"{response}\n💵 ПРЕДВАРИТЕЛЬНАЯ СУММА: {current_order['folding_price']} руб. (только складывание)\n\n" \
                  f"📄 Сколько копий напечатать для файла #1 ({first_file_name})?\n" \
                  "Пожалуйста, введите цифру:"

        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        
        return PRINT_COPIES
    except Exception as e:
        logger.error(f"Ошибка в show_final_order: {e}")
        return CONFIRM

async def print_copies_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        text = update.message.text.strip()
        if not text.isdigit() or int(text) <= 0:
            await update.message.reply_text("❌ Пожалуйста, введите целое число больше 0.")
            return PRINT_COPIES
        
        copies = int(text)
        current_order = user_orders[user_id][0]
        idx = context.user_data['copy_index']
        current_order['files'][idx]['copies'] = copies
        
        idx += 1
        if idx < len(current_order['files']):
            context.user_data['copy_index'] = idx
            await update.message.reply_text(f"✅ Копий для файла #{idx}: {copies} шт.\n\n📄 Сколько копий напечатать для файла #{idx+1} ({current_order['files'][idx]['name']})?")
            return PRINT_COPIES
        else:
            await update.message.reply_text("✅ Копии заданы!")
            
            # Спрашиваем количество брошюр
            await update.message.reply_text("📚 Сколько брошюр нужно сшить? (Введите цифру, если не нужно - 0)")
            return SET_BROCHURE_COUNT
    except Exception as e:
        logger.error(f"Ошибка в print_copies_handler: {e}")
        return CONFIRM

# --- ЛОГИКА БРОШЮРОВКИ (ПОСЛЕ КОПИЙ) ---
async def set_brochure_count_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        text = update.message.text.strip()
        if not text.isdigit():
            await update.message.reply_text("❌ Введите целое число (например, 0, 1, 2).")
            return SET_BROCHURE_COUNT
        
        count = int(text)
        current_order = user_orders[user_id][0]
        current_order['projects'] = []
        
        if count == 0:
            await update.message.reply_text("✅ Брошюровка не нужна!")
            await update.message.reply_text("🕐 Когда готовы забрать?\n⚡ Доступна ЭКСПРЕСС печать (+30% к стоимости)!", 
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚡ Экспресс (от 3 мин до 1 часа)", callback_data="time_express")],
                    [InlineKeyboardButton("⏱ В течение часа", callback_data="time_1h")],
                    [InlineKeyboardButton("⏰ В течение 3 часов", callback_data="time_3h")],
                    [InlineKeyboardButton("📅 В течение дня", callback_data="time_day")]
                ]))
            return READY_TIME
        
        context.user_data['total_projects'] = count
        context.user_data['current_project_index'] = 1
        context.user_data['temp_project_files'] = []
        context.user_data['temp_project_type'] = None
        
        await show_project_setup(update, context)
        return SETUP_BROCHURE
    except Exception as e:
        logger.error(f"Ошибка в set_brochure_count_handler: {e}")
        return CONFIRM

async def show_project_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        current_order = user_orders[user_id][0]
        project_num = context.user_data['current_project_index']
        
        used_files = []
        for project in current_order['projects']:
            used_files.extend(project['files'])
        
        available_files = []
        for i, file in enumerate(current_order['files']):
            if i not in used_files and file['name'] is not None:
                available_files.append((i, file))
        
        if not available_files:
            context.user_data['current_project_index'] = context.user_data['total_projects'] + 1
            await context.bot.send_message(chat_id=update.effective_chat.id, text="📐 Нужно ли сложить чертежи?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Да", callback_data="folding_yes")], [InlineKeyboardButton("❌ Нет", callback_data="folding_no")]]))
            return FOLDING
        
        keyboard = []
        for i, file in available_files:
            if i in context.user_data['temp_project_files']:
                order_num = context.user_data['temp_project_files'].index(i) + 1
                label = f"✅ {order_num}. {file['name']} ({file['format']})"
            else:
                label = f"⬜ {file['name']} ({file['format']})"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"proj_sel_{i}")])
        
        keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="proj_done")])
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"📚 Соберите Брошюру #{project_num}:\n"
            "Нажимайте на файлы в том порядке, в котором они должны идти в брошюре.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Ошибка в show_project_setup: {e}")
        return CONFIRM

async def brochure_setup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        
        if query.data == "proj_done":
            if not context.user_data['temp_project_files']:
                await query.edit_message_text("❌ Вы не выбрали ни одного файла для этой брошюры.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="proj_back")]]))
                return SETUP_BROCHURE
            
            await query.edit_message_text("📚 Брошюра собрана! Какой тип брошюровки?", 
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Пружинка", callback_data="proj_type_spring")],
                    [InlineKeyboardButton("🧵 Бечевка", callback_data="proj_type_string")]
                ]))
            return SETUP_BROCHURE_TYPE
        elif query.data == "proj_back":
            await query.edit_message_text("📚 Сколько брошюр нужно сшить? Введите цифру:")
            return SET_BROCHURE_COUNT
        elif query.data.startswith("proj_sel_"):
            file_idx = int(query.data.split('_')[2])
            if file_idx in context.user_data['temp_project_files']:
                context.user_data['temp_project_files'].remove(file_idx)
            else:
                context.user_data['temp_project_files'].append(file_idx)
            current_order = user_orders[user_id][0]
            used_files = []
            for project in current_order['projects']:
                used_files.extend(project['files'])
            keyboard = []
            for i, file in enumerate(current_order['files']):
                if i not in used_files and file['name'] is not None:
                    if i in context.user_data['temp_project_files']:
                        order_num = context.user_data['temp_project_files'].index(i) + 1
                        label = f"✅ {order_num}. {file['name']} ({file['format']})"
                    else:
                        label = f"⬜ {file['name']} ({file['format']})"
                    keyboard.append([InlineKeyboardButton(label, callback_data=f"proj_sel_{i}")])
            keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="proj_done")])
            await query.edit_message_text(f"📚 Соберите Брошюру #{context.user_data['current_project_index']}:\nНажимайте на файлы в том порядке, в котором они должны идти в брошюре.", reply_markup=InlineKeyboardMarkup(keyboard))
            return SETUP_BROCHURE
    except Exception as e:
        logger.error(f"Ошибка в brochure_setup_handler: {e}")
        return CONFIRM

async def brochure_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        
        raw_type = query.data.split('_')[2]
        b_type = 'Пружинка' if raw_type == 'spring' else 'Бечевка'
        
        current_order = user_orders[user_id][0]
        project = {
            'files': context.user_data['temp_project_files'],
            'type': b_type,
            'copies': 1
        }
        current_order['projects'].append(project)
        
        # Убрано автодобавление чертежей в складывание
        context.user_data['temp_project_files'] = []
        context.user_data['temp_project_type'] = None
        
        if context.user_data['current_project_index'] < context.user_data['total_projects']:
            context.user_data['current_project_index'] += 1
            await query.edit_message_text(f"✅ Брошюра #{context.user_data['current_project_index'] - 1} готова! Переходим к следующей.")
            await show_project_setup(update, context)
            return SETUP_BROCHURE
        else:
            await query.edit_message_text("✅ Все брошюры собраны!")
            await context.bot.send_message(chat_id=update.effective_chat.id, text="📐 Нужно ли сложить чертежи?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Да", callback_data="folding_yes")], [InlineKeyboardButton("❌ Нет", callback_data="folding_no")]]))
            return FOLDING
    except Exception as e:
        logger.error(f"Ошибка в brochure_type_handler: {e}")
        return CONFIRM

# --- ВРЕМЯ, БЕЧЕВКА, ПОДТВЕРЖДЕНИЕ ---
async def time_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        current_order = user_orders[user_id][0]
        time_map = {'time_1h': 'в течение часа', 'time_3h': 'в течение 3 часов', 'time_day': 'в течение дня', 'time_express': 'Экспресс (от 3 мин до 1 часа)'}
        ready_time = time_map[query.data]
        current_order['ready_time'] = ready_time
        
        base_price = 0
        for f in current_order['files']:
            if f['name'] is not None:
                base_price += f['print_price'] * f['copies']
        
        for project in current_order.get('projects', []):
            for file_idx in project['files']:
                f = current_order['files'][file_idx]
                p = calculate_brochure_price(f['format'], f['total_pages'])
                base_price += p * project['copies']
                
        if current_order.get('folding', False) and current_order.get('folding_files'):
            base_price += current_order.get('folding_price', 0)
        
        if query.data == 'time_express':
            current_order['is_express'] = True
            current_order['express_fee'] = int(base_price * 0.3)
            current_order['total_price'] = base_price + current_order['express_fee']
        else:
            current_order['is_express'] = False
            current_order['express_fee'] = 0
            current_order['total_price'] = base_price
            
        await query.edit_message_text(f"⏱ Готовность: {ready_time}\n\n💰 Итоговая стоимость: {current_order['total_price']} руб.\n" + ("⚡ Надбавка за экспресс: +" + str(current_order['express_fee']) + " руб.\n" if current_order['is_express'] else "") + f"\n🧵 Сколько штук бечевки вам нужно?\nПожалуйста, введите цифру (если не нужна, напишите 0):")
        return STRING_COPIES
    except Exception as e:
        logger.error(f"Ошибка в time_choice: {e}")
        return CONFIRM

async def string_copies_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        text = update.message.text.strip()
        if not text.isdigit():
            await update.message.reply_text("❌ Введите целое число (например, 0, 1, 2).")
            return STRING_COPIES
        
        string_copies = int(text)
        current_order = user_orders[user_id][0]
        current_order['string_copies'] = string_copies
        if string_copies > 0:
            current_order['string'] = True
            current_order['string_price'] = 0
        else:
            current_order['string'] = False
        
        total_price = current_order.get('total_price', 0)
        current_order['total_price'] = total_price
        
        response = f"📊 ОКОНЧАТЕЛЬНЫЙ РАСЧЕТ:\n"
        for f in current_order['files']:
            if f['name'] is not None:
                response += f"📄 Файл: {f['name']} — {f['copies']} копий.\n"
                    
        if current_order.get('projects'):
            for p_idx, project in enumerate(current_order['projects'], 1):
                response += f"📚 Брошюра #{p_idx}: {project['type']}, {project['copies']} шт.\n"
        
        if current_order.get('string', False): response += f"🧵 Бечевка: {string_copies} шт.\n"
        else: response += f"🧵 Бечевка: не нужна\n"
        response += f"💰 ИТОГО: {total_price} руб.\n"
        response += f"⏱ Готовность: {current_order['ready_time']}\n"
        if current_order.get('is_express'): response += f"⚡ Экспресс (+{current_order['express_fee']} руб.)\n"
        response += "\nГотовы заказать?"
        
        await update.message.reply_text(response, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Заказать", callback_data="confirm_yes")], [InlineKeyboardButton("❌ Отказаться", callback_data="confirm_no")]
        ]))
        return CONFIRM
    except Exception as e:
        logger.error(f"Ошибка в string_copies_handler: {e}")
        return CONFIRM

async def confirm_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        if query.data == "confirm_yes":
            await send_order_to_admin(update, context, user_id, user_orders[user_id][0])
            return ConversationHandler.END
        else:
            if user_id in user_orders:
                for order in user_orders[user_id]:
                    for f in order['files']:
                        try:
                            if f.get('path'): os.remove(f['path'])
                        except: pass
                del user_orders[user_id]
            await query.edit_message_text("❌ Заказ отменен. Для создания нового заказа нажмите /start")
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в confirm_choice: {e}")
        return ConversationHandler.END

# --- ОТПРАВКА АДМИНУ ---
async def send_order_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, order: dict):
    try:
        total_sum = order['total_price']
        
        admin_message = f"🆕 НОВЫЙ ЗАКАЗ!\n👤 Клиент: {order['user_info']}\n🆔 ID: {user_id}\n⏱ Готовность: {order['ready_time']}\n\n"
        admin_message += "🖨 ПЕЧАТЬ:\n"
        
        for i, file_data in enumerate(order['files']):
            if file_data['name'] is not None:
                side = 'Односторонняя' if file_data['sided'] == 'single' else 'Двусторонняя'
                copies = file_data['copies']
                total_file_price = file_data['print_price'] * copies
                
                admin_message += f"Файл #{i+1}: {file_data['name']}\n"
                if file_data['selected_pages']:
                    admin_message += f"    Страницы: {', '.join(map(str, file_data['selected_pages']))}\n"
                else:
                    admin_message += f"    Страницы: Все\n"
                admin_message += f"    Формат: {file_data['format']} | {side}\n"
                admin_message += f"    Цветных: {file_data['color_pages']} | ЧБ: {file_data['bw_pages']}\n"
                admin_message += f"    Копии: {copies} шт. | Итого: {total_file_price} руб.\n"
        
        if order.get('projects'):
            admin_message += f"\n📚 БРОШЮРОВКА (БРОШЮРЫ):\n"
            for p_idx, project in enumerate(order['projects'], 1):
                b_type = 'Пружинка' if project['type'] == 'spring' else 'Бечевка'
                admin_message += f"Брошюра #{p_idx} ({b_type}, {project['copies']} шт.):\n"
                for order_idx, file_idx in enumerate(project['files'], 1):
                    f = order['files'][file_idx]
                    p = calculate_brochure_price(f['format'], f['total_pages'])
                    admin_message += f"  {order_idx}. {f['name']} ({f['format']}) - {p} руб.\n"
        
        if order.get('folding', False) and order.get('folding_files'):
            admin_message += f"\n📐 СКЛАДЫВАНИЕ ЧЕРТЕЖЕЙ:\n"
            for file_idx in order['folding_files']:
                f = order['files'][file_idx]
                p = FOLDING_PRICES.get(f['format'], 0)
                admin_message += f"  - {f['name']} ({f['format']}) x {f['folding_copies']} шт. - {p * f['folding_copies']} руб.\n"
            admin_message += f"  💰 Итого: {order['folding_price']} руб.\n"
            
        if order.get('string', False): admin_message += f"\n🧵 БЕЧЕВКА:\n  Требуется: {order['string_copies']} шт.\n"
        else: admin_message += f"\n🧵 БЕЧЕВКА:\n  Не требуется\n"
        if order.get('is_express'): admin_message += f"\n⚡ ЭКСПРЕСС ПЕЧАТЬ: ДА (+{order['express_fee']} руб.)\n"
        else: admin_message += f"\n⚡ ЭКСПРЕСС ПЕЧАТЬ: Нет\n"
        admin_message += f"\n💵 ИТОГО К ОПЛАТЕ: {total_sum} руб.\n\nДля уведомления: /ready_{user_id}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Отправить уведомление о готовности", callback_data=f"ready_{user_id}")],
            [InlineKeyboardButton("📦 Заказ выдан", callback_data=f"issue_{user_id}")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data=f"admin_cancel:{user_id}")]
        ])

        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message, reply_markup=keyboard)
        
        for i, file_data in enumerate(order['files']):
            if file_data.get('path') and os.path.exists(file_data['path']):
                try:
                    with open(file_data['path'], 'rb') as doc:
                        await context.bot.send_document(chat_id=ADMIN_ID, document=doc, caption=f"📎 Файл #{i+1}")
                except Exception as e:
                    logger.error(f"Не удалось отправить файл {file_data['name']}: {e}")
        
        await update.effective_message.reply_text(f"✅ ЗАКАЗ ПРИНЯТ! Сумма: {total_sum} руб.\n⏱ Готовность: {order['ready_time']}\n\n📩 Вам придет уведомление, когда заказ будет готов.\n📌 Ждем вас в печатке в УЛБ!")
    except Exception as e:
        logger.error(f"Критическая ошибка в send_order_to_admin: {e}")
        await update.effective_message.reply_text("❌ Ошибка оформления. Свяжитесь с администратором.")
    finally:
        for file_data in order['files']:
            try:
                if file_data.get('path') and os.path.exists(file_data['path']):
                    os.remove(file_data['path'])
            except Exception as e:
                logger.error(f"Не удалось удалить файл: {e}")

# --- ОТЗЫВЫ И ОСТАЛЬНОЕ ---
async def issue_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        if update.effective_user.id != ADMIN_ID:
            await query.answer("У вас нет прав!", show_alert=True)
            return
        
        if not is_business_hours():
            await query.answer("❌ Выдача заказов возможна только с 9:00 до 20:00 (Пн-Пт)!", show_alert=True)
            return

        client_id = int(query.data.split('_')[1])
        try:
            await context.bot.send_message(chat_id=client_id, text="📦 Ваш заказ выдан!\n\nПросим вас оценить наш сервис от 1 до 10 (напишите цифру):")
            client_feedback_states[client_id] = {'state': 'waiting_rating', 'rating': None}
            await query.edit_message_text(text=query.message.text + "\n\n📦 Клиент уведомлен о выдаче заказа.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить заказ", callback_data=f"admin_cancel:{client_id}")]]))
        except Exception as e:
            logger.error(f"Ошибка уведомления клиента: {e}")
    except Exception as e:
        logger.error(f"Ошибка в issue_client: {e}")

async def feedback_rating_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        if user_id not in client_feedback_states or client_feedback_states[user_id]['state'] != 'waiting_rating':
            return
        text = update.message.text.strip()
        if not text.isdigit() or int(text) < 1 or int(text) > 10:
            await update.message.reply_text("❌ Пожалуйста, введите целое число от 1 до 10.")
            return
        rating = int(text)
        client_feedback_states[user_id] = {'state': 'waiting_comment', 'rating': rating}
        await update.message.reply_text(f"✅ Спасибо за оценку {rating}/10!\n\n📝 Напишите, что нам нужно улучшить?\nЕсли всё отлично, просто поставьте тире (-):")
    except Exception as e:
        logger.error(f"Ошибка в feedback_rating_handler: {e}")

async def feedback_comment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        if user_id not in client_feedback_states or client_feedback_states[user_id]['state'] != 'waiting_comment':
            return
        comment = update.message.text.strip()
        if not comment: comment = "-"
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"⭐ НОВЫЙ ОТЗЫВ ОТ КЛИЕНТА (ID: {user_id}):\n\nОценка: {client_feedback_states[user_id].get('rating', 'Не указана')}/10\nКомментарий: {comment}")
        except Exception:
            pass
        await update.message.reply_text("🙏 Спасибо за ваш отзыв! Мы обязательно учтем ваши пожелания.")
        del client_feedback_states[user_id]
    except Exception as e:
        logger.error(f"Ошибка в feedback_comment_handler: {e}")

async def admin_cancel_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        if update.effective_user.id != ADMIN_ID:
            await query.answer("У вас нет прав!", show_alert=True)
            return
        client_id = int(query.data.split(':')[1])
        admin_cancel_states[ADMIN_ID] = client_id
        await query.edit_message_text(text=query.message.text + "\n\n⚠️ Процесс отмены запущен.\n\nНапишите причину отмены текстовым сообщением для клиента.")
    except Exception as e:
        logger.error(f"Ошибка в admin_cancel_choice: {e}")

async def admin_cancel_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        admin_id = update.effective_user.id
        if admin_id != ADMIN_ID or admin_id not in admin_cancel_states: return
        client_id = admin_cancel_states[admin_id]
        reason = update.message.text
        try:
            await context.bot.send_message(chat_id=client_id, text=f"❌ Ваш заказ был отменен.\n\nПричина: {reason}\n\nЕсли это ошибка, свяжитесь с оператором. Для нового заказа нажмите /start")
            if client_id in user_orders:
                for order in user_orders[client_id]:
                    for f in order['files']:
                        try:
                            if f.get('path'): os.remove(f['path'])
                        except: pass
                del user_orders[client_id]
            await update.message.reply_text(f"✅ Клиент {client_id} уведомлен об отмене заказа.")
            del admin_cancel_states[admin_id]
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при отправке уведомления клиенту: {e}")
    except Exception as e:
        logger.error(f"Ошибка в admin_cancel_reason: {e}")

async def unsupported_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        if user_id in client_feedback_states:
            return ConversationHandler.END
        if update.message.text.startswith('/'): return ConversationHandler.END
        await update.message.reply_text("🤖 Я не умею читать текстовые сообщения! Я создан только для приема PDF-файлов и нажатия кнопок.\n\nХотите, чтобы вас перевели на оператора?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👨‍💻 Да, переведите", callback_data="operator_yes")], [InlineKeyboardButton("❌ Нет, продолжить заказ", callback_data="operator_no")]]))
        return WAIT_OPERATOR
    except Exception:
        return ConversationHandler.END

async def operator_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        if query.data == "operator_yes":
            await query.edit_message_text("✅ Вы переведены на оператора. Ожидайте ответа или напишите свой вопрос.")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"👤 Пользователь {user_id} (@{query.from_user.username or 'нет юзернейма'}) просит перевести на оператора.")
            return WAIT_OPERATOR
        else:
            await query.edit_message_text("Хорошо! Чтобы продолжить заказ, отправьте PDF-файл или нажмите /start для начала заново.")
            return ConversationHandler.END
    except Exception:
        return ConversationHandler.END

async def operator_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        text = update.message.text
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"📩 Сообщение от клиента {user_id}:\n{text}")
        await update.message.reply_text("✅ Ваше сообщение отправлено оператору.")
        return WAIT_OPERATOR
    except Exception:
        return WAIT_OPERATOR

async def reply_to_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ У вас нет прав для этой команды.")
            return
        try:
            args = context.args
            if len(args) < 2:
                await update.message.reply_text("❌ Неверный формат. Используйте: /reply <ID клиента> <ваш текст>")
                return
            client_id = int(args[0])
            reply_text = " ".join(args[1:])
            await context.bot.send_message(chat_id=client_id, text=f"👨‍💻 Оператор: {reply_text}")
            await update.message.reply_text(f"✅ Ответ отправлен клиенту {client_id}.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    except Exception:
        pass

async def notify_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            if query.from_user.id != ADMIN_ID:
                await query.answer("Нет прав!", show_alert=True)
                return
            client_id = int(query.data.split('_')[1])
            try:
                await context.bot.send_message(chat_id=client_id, text="🎉 ВАШ ЗАКАЗ ГОТОВ! Заберите его в печатке в УЛБ.\n💳 Оплата при получении.")
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"✅ Клиент {client_id} уведомлен о готовности заказа.\n\nТеперь вы можете выдать заказ.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📦 Заказ выдан", callback_data=f"issue_{client_id}")],
                        [InlineKeyboardButton("❌ Отменить заказ", callback_data=f"admin_cancel:{client_id}")]
                    ])
                )
            except Exception as e:
                await query.edit_message_text(text=query.message.text + f"\n\n❌ Ошибка: {e}")
        else:
            if update.effective_user.id != ADMIN_ID:
                await update.message.reply_text("❌ У вас нет прав.")
                return
            try:
                client_id = int(update.message.text.split('_')[1])
                await context.bot.send_message(chat_id=client_id, text="🎉 ВАШ ЗАКАЗ ГОТОВ! Заберите его в печатке в УЛБ.\n💳 Оплата при получении.")
                await update.message.reply_text(f"✅ Уведомление отправлено клиенту ID: {client_id}")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")
    except Exception as e:
        logger.error(f"Ошибка в notify_client: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        if user_id in user_orders:
            for order in user_orders[user_id]:
                for file_data in order['files']:
                    try:
                        if file_data.get('path'): os.remove(file_data['path'])
                    except: pass
            del user_orders[user_id]
        await update.message.reply_text("❌ Заказ отменен. Нажмите /start для нового заказа.")
        return ConversationHandler.END
    except Exception:
        return ConversationHandler.END

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id == ADMIN_ID:
            await update.message.reply_text("✅ Бот работает!")
        else:
            await update.message.reply_text("❌ Нет прав.")
    except Exception:
        pass

async def send_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id == ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text="🧪 Тест!")
            await update.message.reply_text("✅ Отправлено!")
        else:
            await update.message.reply_text("❌ Нет прав.")
    except Exception:
        pass

# --- ФУНКЦИЯ ЗАПУСКА БОТА ---
def run_bot():
    application = Application.builder().token(TOKEN).build()
    application.add_error_handler(error_handler)
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth)],
            WAIT_FILE: [MessageHandler(filters.Document.ALL, handle_file)],
            PRINT_MODE: [CallbackQueryHandler(print_mode_choice, pattern="^print_")],
            INPUT_PAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_pages_handler)],
            COLOR_MODE: [CallbackQueryHandler(color_mode_choice, pattern="^color_mode_")],
            INPUT_COLOR_PAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_color_pages_handler)],
            FORMAT: [CallbackQueryHandler(format_choice, pattern="^format_")],
            SIDED: [CallbackQueryHandler(sided_choice, pattern="^sided_")],
            ADD_FILE: [CallbackQueryHandler(add_file_choice, pattern="^add_")],
            FOLDING: [CallbackQueryHandler(folding_choice, pattern="^folding_")],
            FOLDING_SELECT: [CallbackQueryHandler(folding_select, pattern="^folding_")],
            PRINT_COPIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, print_copies_handler)],
            SET_BROCHURE_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_brochure_count_handler)],
            SETUP_BROCHURE: [CallbackQueryHandler(brochure_setup_handler, pattern="^(proj_sel_|proj_done|proj_back)")],
            SETUP_BROCHURE_TYPE: [CallbackQueryHandler(brochure_type_handler, pattern="^proj_type_")],
            READY_TIME: [CallbackQueryHandler(time_choice, pattern="^time_")],
            STRING_COPIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, string_copies_handler)],
            CONFIRM: [CallbackQueryHandler(confirm_choice, pattern="^confirm_")],
            WAIT_OPERATOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, operator_chat), CallbackQueryHandler(operator_choice, pattern="^operator_")],
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.TEXT & ~filters.COMMAND, unsupported_text)]
    )
    
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_rating_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_comment_handler))
    application.add_handler(CallbackQueryHandler(admin_cancel_choice, pattern="^admin_cancel:"))
    application.add_handler(CallbackQueryHandler(notify_client, pattern="^ready_"))
    application.add_handler(CallbackQueryHandler(issue_client, pattern="^issue_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_cancel_reason))
    application.add_handler(CommandHandler('reply', reply_to_client))
    application.add_handler(CommandHandler('test', test))
    application.add_handler(CommandHandler('sendtest', send_test))
    
    print("🤖 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# --- ЗАПУСК ДЛЯ RENDER ---
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
