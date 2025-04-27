# Import libraries
import os
import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# Load environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize the Groq client
client = Groq(
    api_key=GROQ_API_KEY,
)

# Dictionary to store message history for each user
user_histories = {}

# Function to log interactions to a text file
def log_message(user_id, role, content):
    with open('chat_logs.txt', 'a', encoding='utf-8') as log_file:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_file.write(f"[{timestamp}] User {user_id} ({role}): {content}\n")

# Load system prompt from a file
def load_system_prompt(filepath="system_prompt.txt"):
    with open(filepath, 'r', encoding='utf-8') as file:
        return file.read().strip()

SYSTEM_PROMPT = load_system_prompt()

# Function to interact with Groq
async def ask_groq(user_id, user_message):
    # Initialize history if the user is not yet in the dictionary
    if user_id not in user_histories:
        user_histories[user_id] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    # Add the user's message to the history
    user_histories[user_id].append({"role": "user", "content": user_message})
    log_message(user_id, "user", user_message)  # Log user's message

    # Limit the history to the last 10 exchanges + system prompt
    max_messages = 21  # 1 system + 10 pairs (user + assistant) = 1 + 20 = 21 messages
    if len(user_histories[user_id]) > max_messages:
        user_histories[user_id] = [user_histories[user_id][0]] + user_histories[user_id][-20:]

    try:
        chat_completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=user_histories[user_id],
            temperature=0.7,
        )

        assistant_reply = chat_completion.choices[0].message.content

        # Add the assistant's reply to the history
        user_histories[user_id].append({"role": "assistant", "content": assistant_reply})
        log_message(user_id, "assistant", assistant_reply)  # Log assistant's reply

        return assistant_reply

    except Exception as e:
        print(f"Error communicating with Groq API: {e}")
        return "Sorry, there was an error communicating with the server."

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Write to me and we will practice English through a role-playing game! 🌟")

# Handler for normal messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.message.from_user.id  # Unique user ID
    reply_text = await ask_groq(user_id, user_text)
    await update.message.reply_text(reply_text)

# Main function
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == '__main__':
    main()