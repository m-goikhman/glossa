# main.py
import asyncio
import json # Добавляем импорт json для логгирования
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
import logging
import uvicorn
import traceback # Добавляем импорт traceback

from config import TELEGRAM_TOKEN
from privacy_config import sanitize_log_data
from bot_handlers import (
    start_command_handler,
    restart_command_handler,
    update_keyboard_handler,
    show_main_menu_handler,
    show_language_learning_menu_handler,
    progress_report_handler,
    button_callback_handler,
    handle_message,
)

# Настраиваем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Глобальные переменные ---
ptb_app = None
app = Starlette()

@app.on_event("startup")
async def startup_event():
    """
    Инициализирует приложение бота один раз при старте сервера.
    """
    global ptb_app
    if ptb_app is None:
        logger.info("Server startup: Initializing Telegram Bot Application...")
        
        ptb_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

        ptb_app.add_handler(CommandHandler("start", start_command_handler))
        ptb_app.add_handler(CommandHandler("restart", restart_command_handler))
        ptb_app.add_handler(CommandHandler("update_keyboard", update_keyboard_handler))
        ptb_app.add_handler(CommandHandler("menu", show_main_menu_handler))
        ptb_app.add_handler(CommandHandler("progress", progress_report_handler))
        ptb_app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^🔍 Game Menu$'), show_main_menu_handler))
        ptb_app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^📖 Learning Menu$'), show_language_learning_menu_handler))
        ptb_app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^📊 Language Progress$'), show_language_learning_menu_handler))
        # Move CallbackQueryHandler before the general MessageHandler to ensure button clicks are processed first
        ptb_app.add_handler(CallbackQueryHandler(button_callback_handler))
        ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        await ptb_app.initialize()
        
        logger.info("Bot application initialized successfully on startup.")

@app.route('/_ah/start')
async def health_check(request: Request):
    """Отвечает на проверку готовности от Google App Engine."""
    return PlainTextResponse('OK')

@app.route(f"/{TELEGRAM_TOKEN}", methods=['POST'])
async def webhook(request: Request):
    """Принимает обновления от Telegram и обрабатывает их."""
    if ptb_app is None:
        logger.error("FATAL: Bot application is not initialized. Webhook cannot process update.")
        return PlainTextResponse('error: bot not initialized', status_code=500)

    try:
        update_data = await request.json()
        
        # Log only essential info without personal data
        sanitized_data = sanitize_log_data(update_data)
        
        if 'message' in sanitized_data:
            user_id = sanitized_data.get('user_id', 'unknown')
            message_type = 'text' if 'text' in sanitized_data['message'] else 'other'
            logger.info(f"Received {message_type} message from user {user_id}")
        elif 'callback_query' in sanitized_data:
            user_id = sanitized_data.get('user_id', 'unknown')
            logger.info(f"Received callback query from user {user_id}")
        else:
            logger.info("Received update (type not recognized)")
        
        update = Update.de_json(update_data, ptb_app.bot)
        
        # --- ГЛАВНОЕ ИЗМЕНЕНИЕ: ЛОВИМ ОШИБКУ ЗДЕСЬ ---
        try:
            await ptb_app.process_update(update)
        except Exception:
            # Выводим в лог полную, детальную трассировку ошибки
            logger.error("!!! CAUGHT EXCEPTION in process_update !!!")
            logger.error(traceback.format_exc())
            
    except Exception as e:
        logger.error(f"Error in webhook BEFORE processing update: {e}", exc_info=True)
    
    return PlainTextResponse('ok')

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)