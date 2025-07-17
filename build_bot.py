# -----------------------------------------------------------------
# Import necessary libraries
# -----------------------------------------------------------------
import os
import datetime
import asyncio
import json
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
from groq import Groq

# -----------------------------------------------------------------
# Load and set up configuration
# -----------------------------------------------------------------
# Load environment variables from the .env file
load_dotenv()

# Get tokens and keys from environment variables
# Ensure you have a .env file with these variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize the Groq API client
client = Groq(api_key=GROQ_API_KEY)


# -----------------------------------------------------------------
# Global variables and data structures
# -----------------------------------------------------------------

# A dictionary containing data for all characters. Easily expandable.
CHARACTER_DATA = {
    "tim": {
        "prompt_file": "prompts/prompt_tim.mdown",
        "full_name": "Tim Kane",
        "emoji": "📚",
    },
    "pauline": {
        "prompt_file": "prompts/prompt_pauline.mdown",
        "full_name": "Pauline Thompson",
        "emoji": "💼",
    },
    "fiona": {
        "prompt_file": "prompts/raw/fiona.invite.txt",
        "full_name": "Fiona McAllister",
        "emoji": "💔",
    },
    "ronnie": {
        "prompt_file": "prompts/prompt_ronnie.mdown",
        "full_name": "Ronie Snapper",
        "emoji": "🚬",
    },
}

# Storage for each player's game state. The key is the user_id.
# Each player will have their own isolated session.
GAME_STATE = {}

# Storage for each player's chat history
user_histories = {}

# Global variable for the bot's username
BOT_USERNAME = None


# -----------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------

def load_system_prompt(filepath: str) -> str:
    """Loads the system prompt text from a file."""
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        print(f"ERROR: Prompt file not found: {filepath}")
        return "You are a helpful assistant."


def log_message(user_id: int, role: str, content: str):
    """Writes a message to the log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] User {user_id} ({role}): {content}\n"
    with open("chat_logs.txt", "a", encoding="utf-8") as log_file:
        log_file.write(log_entry)


async def ask_groq(user_id: int, user_message: str, system_prompt: str) -> str:
    """Sends a request to the Groq API for a character actor and returns the response."""
    # Each player has their own history
    if user_id not in user_histories:
        user_histories[user_id] = []

    # Assemble messages for the request: system prompt + last 10 messages + new query
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(user_histories[user_id][-10:])
    messages.append({"role": "user", "content": user_message})

    try:
        chat_completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile", messages=messages, temperature=0.8
        )
        assistant_reply = chat_completion.choices[0].message.content

        # Add both the user's message and the assistant's reply to the history for context
        # Note: 'user_message' here is the trigger message from the director
        user_histories[user_id].append({"role": "user", "content": user_message})
        user_histories[user_id].append({"role": "assistant", "content": assistant_reply})
        
        # Trim the history to prevent it from growing indefinitely
        if len(user_histories[user_id]) > 20:
            user_histories[user_id] = user_histories[user_id][-20:]
            
        return assistant_reply

    except Exception as e:
        print(f"Error communicating with Groq API: {e}")
        return "Sorry, a server error occurred. I can't respond right now."


async def ask_director(user_id: int, last_message: str) -> dict:
    """Asks the Director LLM for the next action and returns it as a dictionary."""
    director_prompt = load_system_prompt("prompts/prompt_director.mdown")
    
    # Format the context for the director
    context_for_director = f"The last message in the conversation was: '{last_message}'"
    
    # We use a temporary, short context for the director to keep it objective
    director_messages = [
        {"role": "system", "content": director_prompt},
        {"role": "user", "content": context_for_director}
    ]
    
    try:
        # Direct API call without saving to the main history
        chat_completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile", messages=director_messages, temperature=0.5
        )
        response_text = chat_completion.choices[0].message.content
        log_message(user_id, "director", response_text)
        return json.loads(response_text) # Parse the JSON response
    except Exception as e:
        print(f"Error calling director or parsing JSON: {e}")
        return {"action": "do_nothing", "data": {}}


# -----------------------------------------------------------------
# Telegram Command and Button Handlers
# -----------------------------------------------------------------

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /start command."""
    await update.message.reply_text(
        "Welcome to the detective game! To choose a character to talk to, use the /menu command."
    )


async def show_character_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a character selection menu with inline buttons."""
    keyboard = [
        [
            InlineKeyboardButton(
                f"{data['emoji']} {data['full_name']}",
                callback_data=f"talk_{key}",
            )
        ]
        for key, data in CHARACTER_DATA.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Who do you want to talk to?", reply_markup=reply_markup)


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline button presses."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    action, character_key = query.data.split("_", 1)

    if action == "talk" and character_key in CHARACTER_DATA:
        if user_id not in GAME_STATE:
            GAME_STATE[user_id] = {}
        
        GAME_STATE[user_id]["current_character"] = character_key
        
        char_name = CHARACTER_DATA[character_key]["full_name"]
        await query.edit_message_text(text=f"Character selected: {char_name}. You can now ask your question.")
    else:
        await query.edit_message_text(text="An error occurred. Please try again.")


# -----------------------------------------------------------------
# Main Message Handler (The "Game Director" Logic)
# -----------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The main handler for text messages, orchestrating the two-step LLM call."""
    user_id = update.message.from_user.id
    user_text = update.message.text

    log_message(user_id, "user", user_text)

    # Step 1: Ask the Director what to do
    director_decision = await ask_director(user_id, user_text)
    
    action = director_decision.get("action")
    data = director_decision.get("data", {})

    if action in ["character_reply", "character_reaction"]:
        character_key = data.get("character_key")
        trigger_message = data.get("trigger_message")

        if not character_key or not trigger_message:
            print("Director's instructions were incomplete.")
            return

        char_data = CHARACTER_DATA[character_key]
        system_prompt = load_system_prompt(char_data["prompt_file"])
        
        # Step 2: Execute the director's command by calling the "Actor"
        reply_text = await ask_groq(user_id, trigger_message, system_prompt)
        
        formatted_reply = f"{char_data['emoji']} **{char_data['full_name']}:** {reply_text}"
        await update.message.reply_text(formatted_reply, parse_mode='Markdown')

    elif action == "do_nothing":
        # As per the director's instructions, do nothing.
        pass


# -----------------------------------------------------------------
# Bot launch sequence
# -----------------------------------------------------------------

async def set_bot_username(app):
    """Gets and saves the bot's username after launch."""
    global BOT_USERNAME
    me = await app.bot.get_me()
    BOT_USERNAME = me.username
    print(f"Bot started as @{BOT_USERNAME}")


def main():
    """The main function to create and run the bot application."""
    print("Starting bot...")
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start_command_handler))
    app.add_handler(CommandHandler("menu", show_character_menu))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.post_init = set_bot_username
    
    print("Bot is ready and polling for messages.")
    app.run_polling()


if __name__ == "__main__":
    main()