import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from config import CHARACTER_DATA, GAME_STATE, message_cache, TOTAL_CLUES, SUSPECT_KEYS
from ai_services import ask_for_dialogue, ask_tutor_for_analysis, ask_tutor_for_explanation, ask_word_spotter, ask_director
from utils import load_system_prompt, get_log_filepath, write_log_entry, log_message, split_long_message

async def analyze_and_log_text(user_id: int, text_to_analyze: str):
    """Silently analyzes user text and logs it if improvements are needed."""
    analysis_result = await ask_tutor_for_analysis(user_id, text_to_analyze)
    if analysis_result.get("improvement_needed"):
        feedback = analysis_result.get("feedback", "")
        log_message(user_id, "tutor_log", f"Logged feedback for: '{text_to_analyze}'")
        write_log_entry(user_id, "feedback", text_to_analyze, feedback)

async def send_tutor_explanation(update: Update, context: ContextTypes.DEFAULT_TYPE, text_to_explain: str, original_message: str = ""):
    """Gets and sends a structured explanation, and logs the learned word."""
    user_id = update.effective_user.id
    tutor_data = CHARACTER_DATA["tutor"]

    explanation_data = await ask_tutor_for_explanation(user_id, text_to_explain, original_message)
    
    definition = explanation_data.get("definition")
    examples = explanation_data.get("examples", [])
    contextual_explanation = explanation_data.get("contextual_explanation")

    if not definition:
        await context.bot.send_message(chat_id=user_id, text="Sorry, I couldn't get a definition for that.")
        return
    reply_text = f"*{text_to_explain}:* {definition}\n"
    if examples:
        reply_text += "\n*Examples:*\n"
        for ex in examples:
            reply_text += f"- _{ex}_\n"
    if contextual_explanation:
        reply_text += f"\n*In Context:*\n_{contextual_explanation}_"

    formatted_reply = f"{tutor_data['emoji']} *{tutor_data['full_name']}:*\n{reply_text}"

    message_chunks = split_long_message(formatted_reply)
    for i, chunk in enumerate(message_chunks):
        if i > 0:
            await asyncio.sleep(1)
        await context.bot.send_message(chat_id=user_id, text=chunk, parse_mode='Markdown')
    
    write_log_entry(user_id, "word", text_to_explain, definition)

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command with a fixed, detailed welcome message."""
    user_id = update.message.from_user.id
    GAME_STATE[user_id] = {
        "mode": "public",
        "current_character": None,
        "waiting_for_word": False,
        "waiting_for_accusation": False,
        "accused_character": None,
        "clues_examined": set(),
        "suspects_interrogated": set(),
        "accuse_unlocked": False,
        "topic_memory": {"topic": "Initial greeting", "spoken": []}
    }
    consent_text = load_system_prompt("game_texts/onboarding_1_consent.txt")
    keyboard = [[InlineKeyboardButton("Continue", callback_data="onboarding__step2")]]
    await update.message.reply_text(consent_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def check_and_unlock_accuse(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Silently checks if conditions are met to unlock the accusation button."""
    state = GAME_STATE.get(user_id, {})
    # Do nothing if already unlocked
    if not state or state.get("accuse_unlocked"):
        return

    all_clues_examined = len(state.get("clues_examined", set())) == TOTAL_CLUES
    all_suspects_interrogated = len(state.get("suspects_interrogated", set())) >= len(SUSPECT_KEYS)

    if all_clues_examined and all_suspects_interrogated:
        state["accuse_unlocked"] = True

async def show_main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the main game menu, conditionally showing the accuse button."""
    user_id = update.effective_user.id
    state = GAME_STATE.get(user_id, {})
    
    keyboard = [
        [InlineKeyboardButton("💬 Talk to Suspects", callback_data="menu__talk")],
        [InlineKeyboardButton("🔍 Examine Evidence", callback_data="menu__evidence")]
    ]

    if state.get("accuse_unlocked"):
        keyboard.append([InlineKeyboardButton("☝️ Make an Accusation", callback_data="accuse__init")])
    
    if update.callback_query:
        await update.callback_query.edit_message_text("What would you like to do?", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("What would you like to do?", reply_markup=InlineKeyboardMarkup(keyboard))

async def progress_report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, is_final_report: bool = False):
    """Sends the user a formatted report of their progress using HTML."""
    user_id = update.effective_user.id
    filepath = get_log_filepath(user_id, 'progress')
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            logs = json.load(f)
        if not logs.get("words_learned") and not logs.get("writing_feedback"): raise FileNotFoundError
    except (FileNotFoundError, json.JSONDecodeError):
        # В финальном отчете, если логов нет, ничего не отправляем
        if not is_final_report:
            await update.message.reply_text("You don't have any saved progress yet!")
        return
    
    report_title = "Your Final Progress Report" if is_final_report else "Your Progress Report"
    report = f"--- \n<b>{report_title}</b>\n---\n\n"
    
    if logs.get("words_learned"):
        report += "<b>Words You've Learned:</b>\n"
        for entry in logs["words_learned"]:
            word = entry['query']
            definition = entry['feedback']
            report += f"• <code>{word}</code>: <tg-spoiler>{definition}</tg-spoiler>\n"
        report += "\n"
        
    if logs.get("writing_feedback"):
        report += "<b>My Feedback on Your Phrases:</b>\n"
        for entry in logs["writing_feedback"]:
            query = entry['query']
            feedback = entry['feedback']
            report += f"📖 <i>You wrote:</i> {query}\n"
            report += f"✅ <b>My suggestion:</b> {feedback}\n\n"

    message_chunks = split_long_message(report)
    for i, chunk in enumerate(message_chunks):
        if i > 0:
            await asyncio.sleep(1)
        
        # Определяем, как отправить сообщение
        if update.callback_query:
             await context.bot.send_message(chat_id=user_id, text=chunk, parse_mode='HTML')
        elif update.message:
            await update.message.reply_text(chunk, parse_mode='HTML')

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button presses."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split("__")
    action_type = parts[0]
    
    if user_id not in GAME_STATE:
        await query.edit_message_text(text="This button has expired. Please start over with /start.")
        return

    state = GAME_STATE[user_id]
    
    # ... (остальные блоки if/elif без изменений) ...
    if action_type == "onboarding":
        sub_action = parts[1]
        await query.edit_message_reply_markup(reply_markup=None)

        if sub_action == "step2":
            how_to_play_text = load_system_prompt("game_texts/onboarding_2_howtoplay.txt")
            keyboard = [[InlineKeyboardButton("Start Game", callback_data="onboarding__startgame")]]
            await context.bot.send_message(chat_id=user_id, text=how_to_play_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        elif sub_action == "startgame":
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
            intro_text = load_system_prompt("game_texts/intro.txt")
            sent_message = await context.bot.send_message(chat_id=user_id, text=intro_text, parse_mode='Markdown')
            keyboard = [[InlineKeyboardButton("💡 Explain...", callback_data=f"explain__init__{sent_message.message_id}")]]
            message_cache[sent_message.message_id] = intro_text
            await context.bot.edit_message_reply_markup(chat_id=sent_message.chat_id, message_id=sent_message.message_id, reply_markup=InlineKeyboardMarkup(keyboard))

            persistent_keyboard = [
                [KeyboardButton("🔍 Game Menu"), KeyboardButton("📊 Language Progress")]
            ]
            reply_markup = ReplyKeyboardMarkup(persistent_keyboard, resize_keyboard=True)
            
            await context.bot.send_message(
                chat_id=user_id,
                text="Game menu and your language progress report are now available on the panel below 👇",
                reply_markup=reply_markup
            )

    elif action_type == "explain":
        sub_action = parts[1]
        if sub_action == "init":
            original_message_id = int(parts[2])
            original_text = message_cache.get(original_message_id, "I couldn't find the original message.")
            words_to_explain = await ask_word_spotter(original_text)
            keyboard = []
            for word in words_to_explain:
                keyboard.append([InlineKeyboardButton(f"'{word}'", callback_data=f"explain__word__{original_message_id}__{word}")])
            keyboard.append([InlineKeyboardButton("💬 The whole sentence", callback_data=f"explain__all__{original_message_id}")])
            keyboard.append([InlineKeyboardButton("✍️ A different word...", callback_data=f"explain__other")])
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

        elif sub_action == "word":
            original_message_id = int(parts[2])
            word_to_explain = parts[3]
            original_message = message_cache.get(original_message_id, "")
            await send_tutor_explanation(update, context, word_to_explain, original_message)

        elif sub_action == "all":
            original_message_id = int(parts[2])
            original_text = message_cache.get(original_message_id, "I couldn't find the original message.")
            await send_tutor_explanation(update, context, original_text, original_text)

        elif sub_action == "other":
            state["waiting_for_word"] = True
            await context.bot.send_message(chat_id=user_id, text="Okay, please type the word or phrase you want me to explain.")

    elif action_type == "menu":
        sub_action = parts[1]
        if sub_action == "main":
            await show_main_menu_handler(update, context)
        elif sub_action == "talk":
            keyboard = [[InlineKeyboardButton("💬 Talk to Everyone (Public)", callback_data="mode__public")]]
            for key, data in CHARACTER_DATA.items():
                if key in SUSPECT_KEYS:
                    keyboard.append([InlineKeyboardButton(f"{data['emoji']} Talk to {data['full_name']}", callback_data=f"talk__{key}")])
            keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="menu__main")])
            await query.edit_message_text("Choose your conversation partner:", reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif sub_action == "evidence":
            keyboard = [
                [InlineKeyboardButton("Initial Report", callback_data="clue__1")],
                [InlineKeyboardButton("The Weapon", callback_data="clue__2")],
                [InlineKeyboardButton("The Note", callback_data="clue__3")],
                [InlineKeyboardButton("The Apartment", callback_data="clue__4")],
                [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="menu__main")]
            ]
            await query.edit_message_text("Which piece of evidence do you want to examine?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif action_type == "clue":
        clue_id = parts[1]
        state["clues_examined"].add(clue_id)
        await check_and_unlock_accuse(user_id, context)

        image_filepath = f"images/clue{clue_id}.png"
        with open(image_filepath, 'rb') as photo:
            await context.bot.send_photo(chat_id=user_id, photo=photo)
        
        clue_filepath = f"game_texts/Clue{clue_id}.txt"
        clue_text = load_system_prompt(clue_filepath)

        reply_message = await context.bot.send_message(chat_id=user_id, text=clue_text, parse_mode='HTML')
        if reply_message:
            keyboard = [[InlineKeyboardButton("💡 Explain...", callback_data=f"explain__init__{reply_message.message_id}")]]
            message_cache[reply_message.message_id] = clue_text
            await context.bot.edit_message_reply_markup(chat_id=reply_message.chat_id, message_id=reply_message.message_id, reply_markup=InlineKeyboardMarkup(keyboard))

    elif action_type == "talk":
        character_key = parts[1]
        if character_key in CHARACTER_DATA:
            state.update({"mode": "private", "current_character": character_key})
            
            char_name = CHARACTER_DATA[character_key]["full_name"]
            narrator_prompt = load_system_prompt(CHARACTER_DATA["narrator"]["prompt_file"])
            description_text = await ask_for_dialogue(user_id, f"Describe taking {char_name} aside for a private talk.", narrator_prompt)
            
            await query.delete_message()
            reply_message = await context.bot.send_message(chat_id=user_id, text=f"🎙️ _{description_text}_", parse_mode='Markdown')
            keyboard = [[InlineKeyboardButton("💡 Explain...", callback_data=f"explain__init__{reply_message.message_id}")]]
            message_cache[reply_message.message_id] = description_text
            await context.bot.edit_message_reply_markup(chat_id=reply_message.chat_id, message_id=reply_message.message_id, reply_markup=InlineKeyboardMarkup(keyboard))

    elif action_type == "accuse":
        sub_action = parts[1]
        if sub_action == "init":
            info_text = load_system_prompt("game_texts/accuse_unlocked.txt")
            keyboard = []
            for key, data in CHARACTER_DATA.items():
                if key in SUSPECT_KEYS:
                    keyboard.append([InlineKeyboardButton(f"{data['emoji']} Accuse {data['full_name']}", callback_data=f"accuse__confirm__{key}")])
            keyboard.append([InlineKeyboardButton("⬅️ Nevermind, go back", callback_data="menu__main")])
            await query.edit_message_text(info_text, reply_markup=InlineKeyboardMarkup(keyboard))

        elif sub_action == "confirm":
            accused_key = parts[2]
            state["waiting_for_accusation_reason"] = True
            state["accused_character"] = accused_key
            
            char_name = CHARACTER_DATA[accused_key]['full_name']
            await query.edit_message_text(f"You chose to accuse {char_name}. Please write your final report and explain why you think they are guilty.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The main handler for text messages, orchestrating the scene."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    user_id = update.message.from_user.id
    user_text = update.message.text
    log_message(user_id, "user", user_text)

    if user_id not in GAME_STATE:
        await start_command_handler(update, context)
        return

    state = GAME_STATE[user_id]
    
    # Засчитываем допрос при первом сообщении в приватном чате
    current_mode = state.get("mode", "public")
    if current_mode == "private":
        char_key = state.get("current_character")
        if char_key and char_key not in state["suspects_interrogated"]:
            state["suspects_interrogated"].add(char_key)
            # Проверяем, не пора ли разблокировать финал
            await check_and_unlock_accuse(user_id, context)

    if state.get("waiting_for_accusation_reason"):
        state["waiting_for_accusation_reason"] = False
        accused_key = state.get("accused_character")
        
        asyncio.create_task(analyze_and_log_text(user_id, user_text))
        
        if accused_key == 'tim':
            outro_text = load_system_prompt("game_texts/outro_win.txt")
        else:
            outro_text = load_system_prompt("game_texts/outro_lose.txt")
        
        await update.message.reply_text(outro_text, parse_mode='Markdown')
        await asyncio.sleep(2)
        
        await progress_report_handler(update, context, is_final_report=True)
        GAME_STATE.pop(user_id, None)
        await context.bot.send_message(
            chat_id=user_id,
            text="Game over. To start a new game, use the /start command."
        )
        return

    if state.get("waiting_for_word"):
        await send_tutor_explanation(update, context, user_text)
        state["waiting_for_word"] = False
        return

    asyncio.create_task(analyze_and_log_text(user_id, user_text))

    topic_memory = state.get("topic_memory", {"topic": "None", "spoken": []})
    
    if current_mode == "public":
        context_for_director = f"Player asks everyone. Topic Memory: {json.dumps(topic_memory)}"
        message_for_director = user_text
    else:
        char_key = state['current_character']
        context_for_director = f"Player asks {char_key}. Topic Memory: {json.dumps(topic_memory)}"
        message_for_director = user_text

    director_decision = await ask_director(user_id, context_for_director, message_for_director)
    scene = director_decision.get("scene", [])
    new_topic = director_decision.get("new_topic", topic_memory["topic"])
    
    if new_topic != topic_memory["topic"]: state["topic_memory"] = {"topic": new_topic, "spoken": []}
    else: state["topic_memory"]["topic"] = new_topic

    if not scene:
        log_message(user_id, "director_info", "Director returned an empty scene."); return

    for i, scene_action in enumerate(scene):
        action = scene_action.get("action")
        data = scene_action.get("data", {})
        if i > 0: await asyncio.sleep(4)

        if action == "narrate_action":
            trigger_msg = data.get("trigger_message")
            if trigger_msg:
                narrator_prompt = load_system_prompt(CHARACTER_DATA["narrator"]["prompt_file"])
                description_text = await ask_for_dialogue(user_id, trigger_msg, narrator_prompt)
                reply_message = await update.message.reply_text(f"🎙️ _{description_text}_", parse_mode='Markdown')
                
                keyboard = [[InlineKeyboardButton("💡 Explain...", callback_data=f"explain__init__{reply_message.message_id}")]]
                message_cache[reply_message.message_id] = description_text
                await context.bot.edit_message_reply_markup(chat_id=reply_message.chat_id, message_id=reply_message.message_id, reply_markup=InlineKeyboardMarkup(keyboard))

        elif action in ["character_reply", "character_reaction"]:
            char_key = data.get("character_key")
            trigger_msg = data.get("trigger_message")
            if char_key in CHARACTER_DATA and trigger_msg:
                char_data = CHARACTER_DATA[char_key]
                system_prompt = load_system_prompt(char_data["prompt_file"])
                reply_text = await ask_for_dialogue(user_id, trigger_msg, system_prompt)
                
                if reply_text:
                    formatted_reply = f"{char_data['emoji']} *{char_data['full_name']}:* {reply_text}"
                    reply_message = await update.message.reply_text(formatted_reply, parse_mode='Markdown')
                    
                    if action == "character_reply":
                        keyboard = [[InlineKeyboardButton("💡 Explain...", callback_data=f"explain__init__{reply_message.message_id}")]]
                        message_cache[reply_message.message_id] = reply_text
                        await context.bot.edit_message_reply_markup(chat_id=reply_message.chat_id, message_id=reply_message.message_id, reply_markup=InlineKeyboardMarkup(keyboard))
                
                if char_key not in state["topic_memory"]["spoken"]:
                    state["topic_memory"]["spoken"].append(char_key)