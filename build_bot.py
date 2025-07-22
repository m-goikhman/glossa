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
    "tim": {"prompt_file": "prompts/prompt_tim.mdown", "full_name": "Tim Kane", "emoji": "📚"},
    "pauline": {"prompt_file": "prompts/prompt_pauline.mdown", "full_name": "Pauline Thompson", "emoji": "💼"},
    "fiona": {"prompt_file": "prompts/raw/fiona.invite.txt", "full_name": "Fiona McAllister", "emoji": "💔"},
    "ronnie": {"prompt_file": "prompts/prompt_ronnie.mdown", "full_name": "Ronie Snapper", "emoji": "🔥"},
    "tutor": {"prompt_file": "prompts/prompt_tutor.mdown", "full_name": "English Tutor", "emoji": "🧑‍🏫"},
    "narrator": {"prompt_file": "prompts/prompt_narrator.mdown", "full_name": "Narrator", "emoji": "🎙️"},
}
GAME_STATE = {}
user_histories = {}
# A simple cache to store original message texts by message_id
message_cache = {}
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
    """Sends a request to the Groq API for an actor and returns the response."""
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
    """Asks the Director LLM for the next scene and returns it as a dictionary."""
    director_prompt = load_system_prompt("prompts/prompt_director.mdown")
    full_context_for_director = f"Context: \"{context_text}\"\nMessage: \"{message}\""
    director_messages = [{"role": "system", "content": director_prompt}, {"role": "user", "content": full_context_for_director}]
    try:
        chat_completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=director_messages, temperature=0.5)
        response_text = chat_completion.choices[0].message.content
        log_message(user_id, "director", response_text)
        # The expected response is a JSON object with a "scene" key
        return json.loads(response_text)
    except Exception as e:
        print(f"Error calling director or parsing JSON: {e}")
        return {"scene": []}

async def send_tutor_explanation(update: Update, context: ContextTypes.DEFAULT_TYPE, text_to_explain: str):
    """Generic function to get and send an explanation from the tutor."""
    user_id = update.effective_user.id
    tutor_data = CHARACTER_DATA["tutor"]
    system_prompt = load_system_prompt(tutor_data["prompt_file"])
    trigger_message = f"Please explain the meaning of: '{text_to_explain}'"
    reply_text = await ask_groq(user_id, trigger_message, system_prompt)
    formatted_reply = f"{tutor_data['emoji']} *{tutor_data['full_name']}:* {reply_text}"
    await context.bot.send_message(chat_id=user_id, text=formatted_reply, parse_mode='Markdown')

# -----------------------------------------------------------------
# Telegram Handlers
# -----------------------------------------------------------------

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command with a fixed, detailed welcome message."""
    user_id = update.message.from_user.id
    GAME_STATE[user_id] = {"mode": "public", "current_character": None, "waiting_for_word": False}
    welcome_text = (
        "🎙️ _The call came in as a possible assault, so you arrived with the paramedics. You step into "
        "the apartment just as they are wheeling Alex out on a gurney. He's alive, but unconscious.\n\n"
        "The door clicks shut behind you. Now, it's just you and the remaining guests, trapped in a heavy silence. "
        "You are the detective in charge. It's your job to find out what happened here._\n\n"
        "--- \n"
        "*HOW TO PLAY*\n"
        "• To start a private interrogation, use `/menu`.\n"
        "• To get an explanation for a difficult word, press the _💡 Explain..._ button that appears under character messages."
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def show_character_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a menu to choose a conversation mode."""
    keyboard = [[InlineKeyboardButton("💬 Talk to Everyone (Public)", callback_data="mode__public")]]
    for key, data in CHARACTER_DATA.items():
        if key not in ["tutor", "narrator"]:
            keyboard.append([InlineKeyboardButton(f"{data['emoji']} Talk to {data['full_name']}", callback_data=f"talk__{key}")])
    await update.message.reply_text("Choose your conversation mode:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button presses."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split("__")
    action_type = parts[0]
    
    if user_id not in GAME_STATE:
        GAME_STATE[user_id] = {}

    if action_type == "explain":
        sub_action = parts[1]
        
        if sub_action == "init":
            original_message_id = int(parts[2])
            original_text = message_cache.get(original_message_id, "I couldn't find the original message.")
            words_to_explain = await ask_word_spotter(original_text)
            keyboard = []
            for word in words_to_explain:
                keyboard.append([InlineKeyboardButton(f"'{word}'", callback_data=f"explain__word__{word}")])
            keyboard.append([InlineKeyboardButton("💬 The whole sentence", callback_data=f"explain__all__{original_message_id}")])
            keyboard.append([InlineKeyboardButton("✍️ A different word...", callback_data=f"explain__other")])
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif sub_action == "word":
            word_to_explain = parts[2]
            await send_tutor_explanation(update, context, word_to_explain)

        elif sub_action == "all":
            original_message_id = int(parts[2])
            original_text = message_cache.get(original_message_id, "I couldn't find the original message.")
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
            GAME_STATE[user_id]["mode"] = "private"
            GAME_STATE[user_id]["current_character"] = character_key
            char_name = CHARACTER_DATA[character_key]["full_name"]
            
            await query.edit_message_text(text=f"You decided to talk to {char_name}.")
            
            narrator_prompt = load_system_prompt(CHARACTER_DATA["narrator"]["prompt_file"])
            trigger_message = f"Describe the detective taking {char_name} aside for a private talk."
            description_text = await ask_groq(user_id, trigger_message, narrator_prompt)
            await context.bot.send_message(chat_id=user_id, text=f"🎙️ _{description_text}_")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The main handler for text messages, orchestrating the scene."""
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
    if current_mode == "public":
        context_for_director = "Player asks everyone"
        message_for_director = user_text
    else:
        char_key = GAME_STATE[user_id]['current_character']
        context_for_director = f"Player asks {char_key}"
        message_for_director = user_text

    director_decision = await ask_director(user_id, context_for_director, message_for_director)
    scene = director_decision.get("scene", [])

    if not scene:
        log_message(user_id, "director_info", "Director returned an empty scene.")
        return

    for i, scene_action in enumerate(scene):
        action = scene_action.get("action")
        data = scene_action.get("data", {})
        
        if i > 0: await asyncio.sleep(4)

        if action == "narrate_action":
            trigger_msg = data.get("trigger_message")
            if trigger_msg:
                narrator_prompt = load_system_prompt(CHARACTER_DATA["narrator"]["prompt_file"])
                description_text = await ask_groq(user_id, trigger_msg, narrator_prompt)
                await update.message.reply_text(f"🎙️ _{description_text}_")

        elif action in ["character_reply", "character_reaction"]:
            char_key = data.get("character_key")
            trigger_msg = data.get("trigger_message")
            if char_key in CHARACTER_DATA and trigger_msg:
                char_data = CHARACTER_DATA[char_key]
                system_prompt = load_system_prompt(char_data["prompt_file"])
                reply_text = await ask_groq(user_id, trigger_msg, system_prompt)
                formatted_reply = f"{char_data['emoji']} *{char_data['full_name']}:* {reply_text}"
                
                reply_message = await update.message.reply_text(formatted_reply, parse_mode='Markdown')
                
                if action == "character_reply":
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
    app.add_handler(CommandHandler("start", start_command_handler))
    app.add_handler(CommandHandler("menu", show_character_menu))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.post_init = set_bot_username
    print("Bot is ready and polling for messages.")
    app.run_polling()

if __name__ == "__main__":
    main()