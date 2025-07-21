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
        return "Tell the user the prompt file is not found"


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


async def ask_director(user_id: int, context_text: str, message: str) -> dict:
    director_prompt = load_system_prompt("prompts/prompt_director.mdown")
    
    # Format the context for the director
    full_context_for_director = f"Context: \"{context_text}\"\nMessage: \"{message}\""
    
    director_messages = [
        {"role": "system", "content": director_prompt},
        {"role": "user", "content": full_context_for_director}
    ]
    
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=director_messages, temperature=0.5)
        response_text = chat_completion.choices[0].message.content
        log_message(user_id, "director", response_text)
        return json.loads(response_text)
    except Exception as e:
        print(f"Error calling director or parsing JSON: {e}")
        return {"action": "do_nothing", "data": {}}

# --- Telegram Handlers ---

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    # Set default state for new users
    GAME_STATE[user_id] = {"mode": "public", "current_character": None}
    await update.message.reply_text(
        "Welcome to the detective game! You are now in 'public chat'. Everyone can hear you.\n\n"
        "To switch to a private conversation with a character, use /menu."
    )

# ### UPDATED ###
async def show_character_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a menu to choose a private conversation or return to public."""
    keyboard = [
        [InlineKeyboardButton("💬 Talk to Everyone (Public)", callback_data="mode_public")]
    ]
    for key, data in CHARACTER_DATA.items():
        keyboard.append([
            InlineKeyboardButton(f"{data['emoji']} Talk to {data['full_name']}", callback_data=f"talk_{key}")
        ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose your conversation mode:", reply_markup=reply_markup)

# ### UPDATED ###
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all button presses for mode switching."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in GAME_STATE:
        GAME_STATE[user_id] = {"mode": "public", "current_character": None}

    if query.data == "mode_public":
        GAME_STATE[user_id] = {"mode": "public", "current_character": None}
        await query.edit_message_text(text="You are now in 'public chat'. Your messages are visible to everyone.")
        return

    action, character_key = query.data.split("_", 1)
    if action == "talk" and character_key in CHARACTER_DATA:
        GAME_STATE[user_id] = {"mode": "private", "current_character": character_key}
        char_name = CHARACTER_DATA[character_key]["full_name"]
        await query.edit_message_text(text=f"You are now in a private conversation with {char_name}.")

# ### HEAVILY REFACTORED ###
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler with logic for public and private modes."""
    user_id = update.message.from_user.id
    user_text = update.message.text
    log_message(user_id, "user", user_text)

    # Ensure user has a state
    if user_id not in GAME_STATE:
        GAME_STATE[user_id] = {"mode": "public", "current_character": None}

    current_mode = GAME_STATE[user_id].get("mode", "public")

    # --- PUBLIC MODE LOGIC ---
    if current_mode == "public":
        director_decision = await ask_director(user_id, "Player asks everyone", user_text)
        action = director_decision.get("action")
        data = director_decision.get("data", {})

        if action == "character_reply":
            char_key = data.get("character_key")
            trigger_msg = data.get("trigger_message")
            if char_key in CHARACTER_DATA and trigger_msg:
                char_data = CHARACTER_DATA[char_key]
                system_prompt = load_system_prompt(char_data["prompt_file"])
                reply_text = await ask_groq(user_id, trigger_msg, system_prompt)
                formatted_reply = f"{char_data['emoji']} **{char_data['full_name']}:** {reply_text}"
                await update.message.reply_text(formatted_reply, parse_mode='Markdown')

    # --- PRIVATE MODE LOGIC ---
    elif current_mode == "private":
        char_key = GAME_STATE[user_id].get("current_character")
        if not char_key or char_key not in CHARACTER_DATA:
            await update.message.reply_text("Error: Character not selected. Please use /menu.")
            return

        # Direct reply from the selected character
        char_data = CHARACTER_DATA[char_key]
        system_prompt = load_system_prompt(char_data["prompt_file"])
        reply_text = await ask_groq(user_id, user_text, system_prompt)
        formatted_reply = f"{char_data['emoji']} **{char_data['full_name']}:** {reply_text}"
        await update.message.reply_text(formatted_reply, parse_mode='Markdown')

        # After reply, check for reactions
        director_decision = await ask_director(user_id, "Character just spoke", reply_text)
        action = director_decision.get("action")
        data = director_decision.get("data", {})

        if action == "character_reaction":
            react_char_key = data.get("character_key")
            trigger_msg = data.get("trigger_message")
            if react_char_key in CHARACTER_DATA and trigger_msg:
                await asyncio.sleep(4)
                react_char_data = CHARACTER_DATA[react_char_key]
                react_prompt = load_system_prompt(react_char_data["prompt_file"])
                reaction_reply = await ask_groq(user_id, trigger_msg, react_prompt)
                formatted_reaction = f"{react_char_data['emoji']} **{react_char_data['full_name']}:** {reaction_reply}"
                await update.message.reply_text(formatted_reaction, parse_mode='Markdown')

# --- Bot launch sequence ---
async def set_bot_username(app):
    global BOT_USERNAME; me = await app.bot.get_me(); BOT_USERNAME = me.username; print(f"Bot started as @{BOT_USERNAME}")

def main():
    print("Starting bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command_handler))
    app.add_handler(CommandHandler("menu", show_character_menu))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.post_init = set_bot_username
    print("Bot is ready and polling for messages.")
    app.run_polling()

if __name__ == "__main__":
    main()




