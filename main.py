from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
from config import TELEGRAM_TOKEN
from bot_handlers import (
    start_command_handler,
    show_character_menu,
    progress_report_handler,
    button_callback_handler,
    handle_message,
)

async def post_init(app):
    """Gets and prints the bot's username after launch."""
    me = await app.bot.get_me()
    print(f"Bot started as @{me.username}")

def main():
    """The main function to create and run the bot application."""
    print("Starting bot...")
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Add all handlers from bot_handlers.py
    app.add_handler(CommandHandler("start", start_command_handler))
    app.add_handler(CommandHandler("menu", show_character_menu))
    app.add_handler(CommandHandler("progress", progress_report_handler))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.post_init = post_init
    
    print("Bot is ready and polling for messages.")
    app.run_polling()

if __name__ == "__main__":
    main()