import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# Настройки
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL = os.getenv("API_URL", "http://localhost:8000")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Эмодзи для красоты
EMOJI = {
    'tool': '🔧',
    'available': '✅',
    'assigned': '👷',
    'repair': '🔨',
    'list': '📋',
    'user': '👤',
    'warning': '⚠️',
    'success': '✅',
    'error': '❌'
}

async def api_request(endpoint, method='GET', data=None):
    """Универсальная функция для запросов к API"""
    url = f"{API_URL}{endpoint}"
    try:
        async with aiohttp.ClientSession() as session:
            if method == 'GET':
                async with session.get(url) as response:
                    return await response.json()
            elif method == 'POST':
                async with session.post(url, json=data) as response:
                    return await response.json()
    except Exception as e:
        logger.error(f"API request error: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовое сообщение"""
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['list']} Статус инструментов", callback_data='status')],
        [InlineKeyboardButton(f"{EMOJI['tool']} Выдать инструмент", callback_data='assign')],
        [InlineKeyboardButton(f"{EMOJI['success']} Вернуть инструмент", callback_data='return')],
        [InlineKeyboardButton(f"{EMOJI['user']} Список работников", callback_data='members')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""
{EMOJI['tool']} *WheraTools - Учёт инструментов*

Выберите действие из меню ниже:
"""
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=reply_markup)

async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус всех инструментов"""
    query = update.callback_query
    await query.answer()
    
    tools = await api_request('/tools/status')
    
    if not tools:
        await query.edit_message_text(f"{EMOJI['error']} Ошибка получения данных")
        return
    
    # Подсчёт статистики
    available = sum(1 for t in tools if t['status'] == 'available')
    assigned = sum(1 for t in tools if t['status'] == 'assigned')
    repair = sum(1 for t in tools if t['status'] == 'in_repair')
    
    text = f"📊 *Статистика инструментов*\n\n"
    text += f"{EMOJI['available']} Доступно: *{available}*\n"
    text += f"{EMOJI['assigned']} В работе: *{assigned}*\n"
    text += f"{EMOJI['repair']} В ремонте: *{repair}*\n\n"
    text += "━━━━━━━━━━━━━━━━━\n\n"
    
    for tool in tools:
        status_emoji = {
            'available': EMOJI['available'],
            'assigned': EMOJI['assigned'],
            'in_repair': EMOJI['repair']
        }.get(tool['status'], '❓')
        
        text += f"{status_emoji} *{tool['tool_name']}*\n"
        
        if tool['status'] == 'assigned':
            text += f"   У: _{tool['current_holder']}_\n"
        elif tool['status'] == 'in_repair' and tool['repair_info']:
            text += f"   Проблема: _{tool['repair_info']['issue']}_\n"
        
        text += "\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data='menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def assign_tool_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор инструмента для выдачи"""
    query = update.callback_query
    await query.answer()
    
    tools = await api_request('/tools/status')
    available_tools = [t for t in tools if t['status'] == 'available']
    
    if not available_tools:
        await query.edit_message_text(
            f"{EMOJI['warning']} Все инструменты выданы или в ремонте",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='menu')]])
        )
        return
    
    keyboard = []
    for tool in available_tools:
        keyboard.append([InlineKeyboardButton(
            f"{EMOJI['tool']} {tool['tool_name']}", 
            callback_data=f"assign_tool_{tool['tool_id']}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='menu')])
    
    await query.edit_message_text(
        f"{EMOJI['tool']} *Выберите инструмент для выдачи:*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def assign_member_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор работника для выдачи инструмента"""
    query = update.callback_query
    await query.answer()
    
    tool_id = int(query.data.split('_')[2])
    context.user_data['assign_tool_id'] = tool_id
    
    members = await api_request('/members')
    
    keyboard = []
    for member in members:
        keyboard.append([InlineKeyboardButton(
            f"{EMOJI['user']} {member['name']}", 
            callback_data=f"assign_member_{member['id']}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='assign')])
    
    await query.edit_message_text(
        f"{EMOJI['user']} *Выберите работника:*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def confirm_assign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение выдачи инструмента"""
    query = update.callback_query
    await query.answer()
    
    member_id = int(query.data.split('_')[2])
    tool_id = context.user_data.get('assign_tool_id')
    
    result = await api_request('/tools/assign', method='POST', data={
        'tool_id': tool_id,
        'member_id': member_id
    })
    
    if result and 'message' in result:
        text = f"{EMOJI['success']} {result['message']}"
    else:
        text = f"{EMOJI['error']} Ошибка при выдаче инструмента"
    
    keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data='menu')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def return_tool_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор инструмента для возврата"""
    query = update.callback_query
    await query.answer()
    
    tools = await api_request('/tools/status')
    assigned_tools = [t for t in tools if t['status'] == 'assigned']
    
    if not assigned_tools:
        await query.edit_message_text(
            f"{EMOJI['warning']} Нет выданных инструментов",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='menu')]])
        )
        return
    
    keyboard = []
    for tool in assigned_tools:
        keyboard.append([InlineKeyboardButton(
            f"{EMOJI['tool']} {tool['tool_name']} (у {tool['current_holder']})", 
            callback_data=f"return_tool_{tool['tool_id']}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='menu')])
    
    await query.edit_message_text(
        f"{EMOJI['success']} *Выберите инструмент для возврата:*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def return_condition_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор состояния инструмента при возврате"""
    query = update.callback_query
    await query.answer()
    
    tool_id = int(query.data.split('_')[2])
    context.user_data['return_tool_id'] = tool_id
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJI['success']} Исправен", callback_data='return_working')],
        [InlineKeyboardButton(f"{EMOJI['error']} Неисправен", callback_data='return_broken')],
        [InlineKeyboardButton("🔙 Назад", callback_data='return')]
    ]
    
    await query.edit_message_text(
        f"{EMOJI['tool']} *Состояние инструмента:*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список работников"""
    query = update.callback_query
    await query.answer()
    
    members = await api_request('/members')
    
    text = f"{EMOJI['user']} *Список работников:*\n\n"
    for member in members:
        text += f"• {member['name']}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data='menu')]]
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех кнопок"""
    query = update.callback_query
    data = query.data
    
    if data == 'menu':
        await start(update, context)
        await query.message.delete()
    elif data == 'status':
        await show_status(update, context)
    elif data == 'assign':
        await assign_tool_select(update, context)
    elif data.startswith('assign_tool_'):
        await assign_member_select(update, context)
    elif data.startswith('assign_member_'):
        await confirm_assign(update, context)
    elif data == 'return':
        await return_tool_select(update, context)
    elif data.startswith('return_tool_'):
        await return_condition_select(update, context)
    elif data == 'members':
        await show_members(update, context)

def main():
    """Запуск бота"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
 
