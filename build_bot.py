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
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

# -----------------------------------------------------------------
# Global variables and data structures
# -----------------------------------------------------------------
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
    "tutor": {
        "prompt_file": "prompts/prompt_tutor.mdown",
        "full_name": "English Tutor",
        "emoji": "🧑‍🏫",
    },
}
GAME_STATE = {}
user_histories = {}
# A simple cache to store original message texts by message_id
message_cache = {}

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
    if user_id not in user_histories:
        user_histories[user_id] = []
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(user_histories[user_id][-10:])
    messages.append({"role": "user", "content": user_message})
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages, temperature=0.8)
        assistant_reply = chat_completion.choices[0].message.content
        user_histories[user_id].extend([{"role": "user", "content": user_message}, {"role": "assistant", "content": assistant_reply}])
        if len(user_histories[user_id]) > 20:
            user_histories[user_id] = user_histories[user_id][-20:]
        return assistant_reply
    except Exception as e:
        print(f"Error communicating with Groq API: {e}")
        return "Sorry, a server error occurred."

async def ask_word_spotter(text_to_analyze: str) -> list:
    """Asks the Word Spotter AI to find difficult words in a text."""
    prompt = load_system_prompt("prompts/prompt_lexicographer.mdown")
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": text_to_analyze}]
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages, temperature=0.2)
        response_text = chat_completion.choices[0].message.content
        return json.loads(response_text)
    except Exception as e:
        print(f"Error calling Word Spotter or parsing JSON: {e}")
        return []
        
async def ask_director(user_id: int, context_text: str, message: str) -> dict:
    """Asks the Director LLM for the next action and returns it as a dictionary."""
    director_prompt = load_system_prompt("prompts/prompt_director.mdown")
    full_context_for_director = f"Context: \"{context_text}\"\nMessage: \"{message}\""
    director_messages = [{"role": "system", "content": director_prompt}, {"role": "user", "content": full_context_for_director}]
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=director_messages, temperature=0.5)
        response_text = chat_completion.choices[0].message.content
        log_message(user_id, "director", response_text)
        return json.loads(response_text)
    except Exception as e:
        print(f"Error calling director or parsing JSON: {e}")
        return {"action": "do_nothing", "data": {}}

async def send_tutor_explanation(update: Update, context: ContextTypes.DEFAULT_TYPE, text_to_explain: str):
    """Generic function to get and send an explanation from the tutor."""
    user_id = update.effective_user.id
    tutor_data = CHARACTER_DATA["tutor"]
    system_prompt = load_system_prompt(tutor_data["prompt_file"])
    trigger_message = f"Please explain the meaning of: '{text_to_explain}'"
    reply_text = await ask_groq(user_id, trigger_message, system_prompt)
    formatted_reply = f"{tutor_data['emoji']} **{tutor_data['full_name']}:** {reply_text}"
    await context.bot.send_message(chat_id=user_id, text=formatted_reply, parse_mode='Markdown')

# -----------------------------------------------------------------
# Telegram Handlers
# -----------------------------------------------------------------

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    GAME_STATE[user_id] = {"mode": "public", "current_character": None, "waiting_for_word": False}
    await update.message.reply_text(
        "Welcome to the detective game! You are now in 'public chat'. Everyone can hear you.\n\n"
        "💡 **Tip:** To get an explanation of any character's message, press the '💡 Explain...' button below it.\n\n"
        "To switch to a private conversation, use /menu."
    )

async def show_character_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("💬 Talk to Everyone (Public)", callback_data="mode__public")]]
    for key, data in CHARACTER_DATA.items():
        if key != "tutor":
            keyboard.append([InlineKeyboardButton(f"{data['emoji']} Talk to {data['full_name']}", callback_data=f"talk__{key}")])
    await update.message.reply_text("Choose your conversation mode:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    parts = query.data.split("__")
    action_type = parts[0]
    
    if user_id not in GAME_STATE:
        GAME_STATE[user_id] = {}

    if action_type == "explain":
        sub_action = parts[1]
        
        # --- NEW LOGIC: We parse data based on the sub_action ---
        
        if sub_action == "init":
            original_message_id = int(parts[2])
            original_text = message_cache.get(original_message_id, query.message.text)
            words_to_explain = await ask_word_spotter(original_text)
            
            keyboard = []
            # We use a more robust callback format for words to avoid errors
            for word in words_to_explain:
                keyboard.append([InlineKeyboardButton(f"'{word}'", callback_data=f"explain__word__{word}")])
            
            keyboard.append([InlineKeyboardButton("💬 The whole sentence", callback_data=f"explain__all__{original_message_id}")])
            keyboard.append([InlineKeyboardButton("✍️ A different word...", callback_data=f"explain__other")]) # No extra data needed
            
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif sub_action == "word":
            word_to_explain = parts[2] # Here, parts[2] is the word itself
            await send_tutor_explanation(update, context, word_to_explain)

        elif sub_action == "all":
            original_message_id = int(parts[2]) # Here, parts[2] is the message_id
            original_text = message_cache.get(original_message_id, query.message.text)
            await send_tutor_explanation(update, context, original_text)
            
        elif sub_action == "other":
            GAME_STATE[user_id]["waiting_for_word"] = True
            await context.bot.send_message(chat_id=user_id, text="Okay, please type the word or phrase you want me to explain.")

    elif action_type == "mode":
        GAME_STATE[user_id] = {"mode": "public", "current_character": None}
        await query.edit_message_text(text="You are now in 'public chat'. Your messages are visible to everyone.")

    elif action_type == "talk":
        character_key = parts[1]
        if character_key in CHARACTER_DATA:
            GAME_STATE[user_id] = {"mode": "private", "current_character": character_key}
            char_name = CHARACTER_DATA[character_key]["full_name"]
            await query.edit_message_text(text=f"You are now in a private conversation with {char_name}.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_text = update.message.text
    log_message(user_id, "user", user_text)

    if user_id not in GAME_STATE:
        GAME_STATE[user_id] = {"mode": "public", "current_character": None, "waiting_for_word": False}

    if GAME_STATE[user_id].get("waiting_for_word"):
        await send_tutor_explanation(update, context, user_text)
        GAME_STATE[user_id]["waiting_for_word"] = False
        return

    current_mode = GAME_STATE[user_id].get("mode", "public")
    reply_message = None
    
    # --- PUBLIC MODE ---
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
                reply_message = await update.message.reply_text(formatted_reply, parse_mode='Markdown')

    # --- PRIVATE MODE ---
    elif current_mode == "private":
        char_key = GAME_STATE[user_id].get("current_character")
        if char_key in CHARACTER_DATA:
            char_data = CHARACTER_DATA[char_key]
            system_prompt = load_system_prompt(char_data["prompt_file"])
            reply_text = await ask_groq(user_id, user_text, system_prompt)
            formatted_reply = f"{char_data['emoji']} **{char_data['full_name']}:** {reply_text}"
            reply_message = await update.message.reply_text(formatted_reply, parse_mode='Markdown')

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
                    # No need to add button here as it's a reaction, not a direct reply
                    await update.message.reply_text(formatted_reaction, parse_mode='Markdown')
        else:
            await update.message.reply_text("Error: Character not selected. Please use /menu.")
            return

    # Attach the explanation button to the main reply
    if reply_message:
        keyboard = [[InlineKeyboardButton("💡 Explain...", callback_data=f"explain__init__{reply_message.message_id}")]]
        message_cache[reply_message.message_id] = reply_message.text
        await context.bot.edit_message_reply_markup(
            chat_id=reply_message.chat_id,
            message_id=reply_message.message_id,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# -----------------------------------------------------------------
# Bot launch sequence
# -----------------------------------------------------------------
def main():
    print("Starting bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command_handler))
    app.add_handler(CommandHandler("menu", show_character_menu))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot is ready and polling for messages.")
    app.run_polling()

if __name__ == "__main__":
    main()