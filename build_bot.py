# Import libraries
import os
import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# Load environment variables from configurable .env file
config_file = os.environ.get("CONFIG_FILE", ".env")
load_dotenv(dotenv_path=config_file)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PROMPT_FILE = os.getenv("PROMPT_FILE")

# Initialize the Groq client
client = Groq(api_key=GROQ_API_KEY)

# Store chat histories per user
user_histories = {}
BOT_USERNAME = None  # Will be set after bot connects

# Load system prompt from file
def load_system_prompt(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            return file.read().strip()
    except FileNotFoundError:
        return "You are a helpful assistant."

# Log only to file
def log_message(user_id, role, content):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] User {user_id} ({role}): {content}"
    with open('chat_logs.txt', 'a', encoding='utf-8') as log_file:
        log_file.write(log_entry + '\n')

# Handle bot replies with context and memory
async def ask_groq(user_id, user_message):
    if user_id not in user_histories:
        user_histories[user_id] = [
            {"role": "system", "content": load_system_prompt(PROMPT_FILE)}
        ]

    user_histories[user_id].append({"role": "user", "content": user_message})

    if len(user_histories[user_id]) > 21:
        user_histories[user_id] = [user_histories[user_id][0]] + user_histories[user_id][-20:]

    try:
        chat_completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=user_histories[user_id],
            temperature=0.7,
        )

        assistant_reply = chat_completion.choices[0].message.content
        user_histories[user_id].append({"role": "assistant", "content": assistant_reply})
        log_message(user_id, "assistant", assistant_reply)
        return assistant_reply

    except Exception as e:
        print(f"Error communicating with Groq API: {e}")
        return "Sorry, there was an error communicating with the server."

# Handle /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Write to me and we'll practice English through a role-playing game! 🌟")

# Handle all user messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.message.from_user.id
    chat_type = update.message.chat.type
    username = update.message.from_user.username or update.message.from_user.first_name

    # In groups: reply only if bot is mentioned
    if chat_type != "private":
        if f"@{BOT_USERNAME}" not in user_text:
            return
        user_text = user_text.replace(f"@{BOT_USERNAME}", "").strip()

    log_message(user_id, "user", user_text)
    reply_text = await ask_groq(user_id, user_text)

    # Mention user in group replies
    if chat_type != "private":
        reply_text = f"@{username} {reply_text}"

    await update.message.reply_text(reply_text)

# Set bot username after connecting
async def set_bot_username(app):
    global BOT_USERNAME
    me = await app.bot.get_me()
    BOT_USERNAME = me.username

# Main function to launch the bot
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.post_init = set_bot_username
    app.run_polling()

if __name__ == '__main__':
    main()
