import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from config import CHARACTER_DATA, GAME_STATE, message_cache
from ai_services import ask_for_dialogue, ask_tutor_for_analysis, ask_word_spotter, ask_director
from utils import load_system_prompt, get_user_log_path, write_log_entry, log_message, split_long_message

async def analyze_and_log_text(user_id: int, text_to_analyze: str):
    """Silently analyzes user text and logs it if improvements are needed."""
    analysis_result = await ask_tutor_for_analysis(user_id, text_to_analyze)
    if analysis_result.get("improvement_needed"):
        feedback = analysis_result.get("feedback", "")
        log_message(user_id, "tutor_log", f"Logged feedback for: '{text_to_analyze}'")
        write_log_entry(user_id, "feedback", text_to_analyze, feedback)

async def send_tutor_explanation(update: Update, context: ContextTypes.DEFAULT_TYPE, text_to_explain: str):
    """Gets and sends an explanation, and logs the learned word."""
    user_id = update.effective_user.id
    tutor_data = CHARACTER_DATA["tutor"]
    system_prompt = load_system_prompt(tutor_data["prompt_file"])
    trigger_message = f"Explain the meaning of: '{text_to_explain}'"
    reply_text = await ask_for_dialogue(user_id, trigger_message, system_prompt)
    formatted_reply = f"{tutor_data['emoji']} *{tutor_data['full_name']}:* {reply_text}"
    await context.bot.send_message(chat_id=user_id, text=formatted_reply, parse_mode='Markdown')
    write_log_entry(user_id, "word", text_to_explain, reply_text)

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command with a fixed, detailed welcome message."""
    user_id = update.message.from_user.id
    GAME_STATE[user_id] = {"mode": "public", "current_character": None, "waiting_for_word": False, "topic_memory": {"topic": "Initial greeting", "spoken": []}}
    # Load and send the first onboarding message
    consent_text = load_system_prompt("game_texts/onboarding_1_consent.txt")
    keyboard = [[InlineKeyboardButton("Continue", callback_data="onboarding__step2")]]
    
    await update.message.reply_text(consent_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def show_character_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a menu to choose a conversation mode."""
    keyboard = [[InlineKeyboardButton("💬 Talk to Everyone (Public)", callback_data="mode__public")]]
    for key, data in CHARACTER_DATA.items():
        if key not in ["tutor", "narrator"]:
            keyboard.append([InlineKeyboardButton(f"{data['emoji']} Talk to {data['full_name']}", callback_data=f"talk__{key}")])
    await update.message.reply_text("Choose your conversation mode:", reply_markup=InlineKeyboardMarkup(keyboard))

async def progress_report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the user a formatted report of their progress."""
    user_id = update.message.from_user.id
    filepath = get_user_log_path(user_id)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            logs = json.load(f)
        if not logs.get("words_learned") and not logs.get("writing_feedback"): raise FileNotFoundError
    except (FileNotFoundError, json.JSONDecodeError):
        await update.message.reply_text("You don't have any saved progress yet!"); return
    report = "--- \n*Your Progress Report*\n---\n\n"
    if logs.get("words_learned"):
        report += "*Words You've Learned:*\n"
        for entry in logs["words_learned"]:
            report += f"• `{entry['query']}`\n"
        report += "\n"
    if logs.get("writing_feedback"):
        report += "*My Feedback on Your Phrases:*\n"
        for entry in logs["writing_feedback"]:
            report += f"📖 _You wrote:_ {entry['query']}\n"
            report += f"✅ *My suggestion:* {entry['feedback']}\n\n"

    message_chunks = split_long_message(report)
    for i, chunk in enumerate(message_chunks):
        if i > 0:
            await asyncio.sleep(1)
        await update.message.reply_text(chunk, parse_mode='Markdown')


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button presses."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split("__")
    action_type = parts[0]
    
    if user_id not in GAME_STATE:
        # A safeguard for users who might click old buttons after a bot restart
        await query.edit_message_text(text="This button has expired. Please start over with /start.")
        return

    # ### ONBOARDING LOGIC - REVISED TO KEEP MESSAGES ###
    if action_type == "onboarding":
        sub_action = parts[1]

        # Deactivate the button on the previous message, leaving the text intact
        await query.edit_message_reply_markup(reply_markup=None)

        if sub_action == "step2":
            # Send the "How to Play" text as a NEW message
            how_to_play_text = load_system_prompt("game_texts/onboarding_2_howtoplay.txt")
            keyboard = [[InlineKeyboardButton("Start Game", callback_data="onboarding__startgame")]]
            await context.bot.send_message(
                chat_id=user_id,
                text=how_to_play_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        elif sub_action == "startgame":
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
            intro_text = load_system_prompt("game_texts/intro.txt")
            sent_message = await context.bot.send_message(
                chat_id=user_id,
                text=intro_text,
                parse_mode='Markdown'
            )
            keyboard = [[InlineKeyboardButton("💡 Explain...", callback_data=f"explain__init__{sent_message.message_id}")]]
            message_cache[sent_message.message_id] = intro_text
            await context.bot.edit_message_reply_markup(
                chat_id=sent_message.chat_id,
                message_id=sent_message.message_id,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    elif action_type == "explain":
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
        elif sub_action == "word": await send_tutor_explanation(update, context, parts[2])
        elif sub_action == "all":
            original_message_id = int(parts[2])
            original_text = message_cache.get(original_message_id, "I couldn't find the original message.")
            await send_tutor_explanation(update, context, original_text)
        elif sub_action == "other":
            GAME_STATE[user_id]["waiting_for_word"] = True
            await context.bot.send_message(chat_id=user_id, text="Okay, please type the word or phrase you want me to explain.")

    elif action_type == "mode":
        GAME_STATE[user_id].update({"mode": "public", "current_character": None})
        await query.edit_message_text(text="You are now in 'public chat'. Your messages are visible to everyone.")

    elif action_type == "talk":
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
        character_key = parts[1]
        if character_key in CHARACTER_DATA:
            GAME_STATE[user_id].update({"mode": "private", "current_character": character_key})
            char_name = CHARACTER_DATA[character_key]["full_name"]
            narrator_prompt_text = load_system_prompt(CHARACTER_DATA["narrator"]["prompt_file"])
            b1 = load_system_prompt("prompts/language_learning/b1.mdown")
            narrator_prompt = f"{narrator_prompt_text}\n\n{b1}"
            description_text = await ask_for_dialogue(user_id, f"Describe taking {char_name} aside for a private talk.", narrator_prompt)
            
            # Delete the old menu and send a new message
            await query.delete_message()
            reply_message = await context.bot.send_message(
                chat_id=user_id,
                text=f"🎙️ _{description_text}_",
                parse_mode='Markdown'
            )
            
            # Add the explain button to the new message
            keyboard = [[InlineKeyboardButton("💡 Explain...", callback_data=f"explain__init__{reply_message.message_id}")]]
            message_cache[reply_message.message_id] = description_text
            await context.bot.edit_message_reply_markup(
                chat_id=reply_message.chat_id,
                message_id=reply_message.message_id,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The main handler for text messages, orchestrating the scene."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    user_id = update.message.from_user.id
    user_text = update.message.text
    log_message(user_id, "user", user_text)

    if user_id not in GAME_STATE:
        GAME_STATE[user_id] = {"mode": "public", "current_character": None, "waiting_for_word": False, "topic_memory": {"topic": "Initial greeting", "spoken": []}}

    if GAME_STATE[user_id].get("waiting_for_word"):
        await send_tutor_explanation(update, context, user_text)
        GAME_STATE[user_id]["waiting_for_word"] = False
        return

    asyncio.create_task(analyze_and_log_text(user_id, user_text))

    current_mode = GAME_STATE[user_id].get("mode", "public")
    topic_memory = GAME_STATE[user_id].get("topic_memory", {"topic": "None", "spoken": []})
    
    if current_mode == "public":
        context_for_director = f"Player asks everyone. Topic Memory: {json.dumps(topic_memory)}"
        message_for_director = user_text
    else:
        char_key = GAME_STATE[user_id]['current_character']
        context_for_director = f"Player asks {char_key}. Topic Memory: {json.dumps(topic_memory)}"
        message_for_director = user_text

    director_decision = await ask_director(user_id, context_for_director, message_for_director)
    scene = director_decision.get("scene", [])
    new_topic = director_decision.get("new_topic", topic_memory["topic"])
    
    if new_topic != topic_memory["topic"]: GAME_STATE[user_id]["topic_memory"] = {"topic": new_topic, "spoken": []}
    else: GAME_STATE[user_id]["topic_memory"]["topic"] = new_topic

    if not scene:
        log_message(user_id, "director_info", "Director returned an empty scene."); return

    for i, scene_action in enumerate(scene):
        action = scene_action.get("action")
        data = scene_action.get("data", {})
        if i > 0: await asyncio.sleep(4)

        elif action in ["character_reply", "character_reaction"]:
            char_key = data.get("character_key")
            trigger_msg = data.get("trigger_message")
            if char_key in CHARACTER_DATA and trigger_msg:
                char_data = CHARACTER_DATA[char_key]
                character_prompt_text = load_system_prompt(char_data["prompt_file"])
                b1 = load_system_prompt("prompts/language_learning/b1.mdown")
                system_prompt = f"{character_prompt_text}\n\n{b1}"
                reply_text = await ask_for_dialogue(user_id, trigger_msg, system_prompt)
                
                if reply_text:
                    formatted_reply = f"{char_data['emoji']} *{char_data['full_name']}:* {reply_text}"
                    reply_message = await update.message.reply_text(formatted_reply, parse_mode='Markdown')
                    
                    if (action == "character_reply"):
                        keyboard = [[InlineKeyboardButton("💡 Explain...", callback_data=f"explain__init__{reply_message.message_id}")]]
                        message_cache[reply_message.message_id] = reply_text
                        await context.bot.edit_message_reply_markup(
                            chat_id=reply_message.chat_id, message_id=reply_message.message_id,
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                
                if char_key not in GAME_STATE[user_id]["topic_memory"]["spoken"]:
                    GAME_STATE[user_id]["topic_memory"]["spoken"].append(char_key)