import asyncio
import json
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from config import CHARACTER_DATA, GAME_STATE, message_cache, TOTAL_CLUES, SUSPECT_KEYS
from ai_services import ask_for_dialogue, ask_tutor_for_analysis, ask_tutor_for_explanation, ask_word_spotter, ask_director
from utils import load_system_prompt, log_message, split_long_message, combine_character_prompt
from game_state_manager import game_state_manager
from progress_manager import progress_manager

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logger = logging.getLogger(__name__)

def get_participant_code(user_id: int) -> str:
    """Gets participant code from game state if available."""
    state = GAME_STATE.get(user_id, {})
    return state.get("participant_code")

async def analyze_and_log_text(user_id: int, text_to_analyze: str):
    """Silently analyzes user text and logs it if improvements are needed."""
    analysis_result = await ask_tutor_for_analysis(user_id, text_to_analyze)
    if analysis_result.get("improvement_needed"):
        feedback = analysis_result.get("feedback", "")
        log_message(user_id, "tutor_log", f"Logged feedback for: '{text_to_analyze}'", get_participant_code(user_id))
        # Use progress manager instead of local file system
        progress_manager.add_writing_feedback(user_id, text_to_analyze, feedback)

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
    
    # Use progress manager instead of local file system
    progress_manager.add_word_learned(user_id, text_to_explain, definition)

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command, checking for existing game state first."""
    user_id = update.message.from_user.id
    
    # Check if user has an existing game state
    saved_state_data = await game_state_manager.load_game_state(user_id)
    
    if saved_state_data and saved_state_data.get("state"):
        saved_state = saved_state_data["state"]
        
        # Check if the saved game was already completed
        if saved_state.get("game_completed"):
            # Game was completed - start fresh instead of resuming
            logger.info(f"User {user_id}: Previous game was completed, starting fresh")
            
            # Clear the completed game state from storage
            await game_state_manager.delete_game_state(user_id)
            
            # Clear progress data for fresh start
            progress_manager.clear_user_progress(user_id)
            
            # Start new game with onboarding
            GAME_STATE[user_id] = {
                "mode": "public",
                "current_character": None,
                "waiting_for_word": False,
                "waiting_for_accusation": False,
                "accused_character": None,
                "clues_examined": set(),
                "suspects_interrogated": set(),
                "accuse_unlocked": False,
                "topic_memory": {"topic": "Initial greeting", "spoken": []},
                "game_completed": False,
                "participant_code": None,
                "waiting_for_participant_code": False,
                "onboarding_step": "consent"
            }
            
            # Start with consent message (onboarding step 1)
            consent_text = load_system_prompt("game_texts/onboarding_1_consent.txt")
            keyboard = [[InlineKeyboardButton("Continue", callback_data="onboarding__step2")]]
            
            await update.message.reply_text(
                "🎮 Starting fresh detective game!",
                reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True)  # Clear keyboard
            )
            
            # Send consent message with inline keyboard
            await update.message.reply_text(
                consent_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return
        
        # Game was not completed - resume from where they left off
        # Ensure game_completed flag is set if it doesn't exist
        if "game_completed" not in saved_state:
            saved_state["game_completed"] = False
        GAME_STATE[user_id] = saved_state
        
        # Set up persistent keyboard
        persistent_keyboard = [
            [KeyboardButton("🔍 Game Menu"), KeyboardButton("📊 Language Progress")]
        ]
        reply_markup = ReplyKeyboardMarkup(persistent_keyboard, resize_keyboard=True)
        
        # Send game resumed message with keyboard
        await update.message.reply_text(
            "🎮 Game resumed! You can continue from where you left off.",
            reply_markup=reply_markup
        )
        
    else:
        # New user or no saved state - start fresh game
        # Clear any existing progress data and completed game state
        progress_manager.clear_user_progress(user_id)
        
        GAME_STATE[user_id] = {
            "mode": "public",
            "current_character": None,
            "waiting_for_word": False,
            "waiting_for_accusation": False,
            "accused_character": None,
            "clues_examined": set(),
            "suspects_interrogated": set(),
            "accuse_unlocked": False,
            "topic_memory": {"topic": "Initial greeting", "spoken": []},
            "game_completed": False,
            "participant_code": None,
            "waiting_for_participant_code": False,
            "onboarding_step": "consent"
        }
        
        consent_text = load_system_prompt("game_texts/onboarding_1_consent.txt")
        keyboard = [[InlineKeyboardButton("Continue", callback_data="onboarding__step2")]]
        
        # Send consent message with inline keyboard
        await update.message.reply_text(
            consent_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def restart_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /restart command - clears current game and starts fresh (for testing)."""
    user_id = update.message.from_user.id
    logger.info(f"User {user_id}: Restart command received")
    
    # Clear current game state from memory
    GAME_STATE.pop(user_id, None)
    
    # Delete saved game state from persistent storage
    await game_state_manager.delete_game_state(user_id)
    
    # Clear progress data
    progress_manager.clear_user_progress(user_id)
    
    # Start fresh game with onboarding process
    GAME_STATE[user_id] = {
        "mode": "public",
        "current_character": None,
        "waiting_for_word": False,
        "waiting_for_accusation": False,
        "accused_character": None,
        "clues_examined": set(),
        "suspects_interrogated": set(),
        "accuse_unlocked": False,
        "topic_memory": {"topic": "Initial greeting", "spoken": []},
        "game_completed": False,
        "participant_code": None,
        "waiting_for_participant_code": False,
        "onboarding_step": "consent"
    }
    
    # Start with consent message (onboarding step 1)
    consent_text = load_system_prompt("game_texts/onboarding_1_consent.txt")
    keyboard = [[InlineKeyboardButton("Continue", callback_data="onboarding__step2")]]
    
    await update.message.reply_text(
        "🎮 Game restarted! Starting from the beginning...",
        reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True)  # Clear keyboard
    )
    
    # Send consent message with inline keyboard
    await update.message.reply_text(
        consent_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

def get_random_common_space_phrase():
    """Returns a random phrase from the common_space.txt file."""
    try:
        phrases = load_system_prompt("game_texts/common_space.txt").strip().split('\n')
        # Filter out empty lines
        phrases = [phrase.strip() for phrase in phrases if phrase.strip()]
        if phrases:
            import random
            return random.choice(phrases)
        else:
            return "You are in the main room. Everyone is present."
    except Exception as e:
        logger.error(f"Failed to load common space phrases: {e}")
        return "You are in the main room. Everyone is present."

async def handle_private_character_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, user_text: str):
    """Handles private conversations directly with a specific character, bypassing the Director AI."""
    state = GAME_STATE[user_id]
    char_key = state.get("current_character")
    
    if not char_key or char_key not in CHARACTER_DATA:
        logger.error(f"User {user_id}: Invalid character key '{char_key}' for private conversation")
        return False
    
    char_data = CHARACTER_DATA[char_key]
    system_prompt = combine_character_prompt(char_key)
    
    # Create a context-aware trigger for the character
    topic_memory = state.get("topic_memory", {"topic": "None", "spoken": []})
    context_trigger = f"The detective is asking you a question: '{user_text}'. Current topic: {topic_memory.get('topic', 'None')}. Respond as your character."
    
    logger.info(f"User {user_id}: Direct character conversation with '{char_key}'")
    
    try:
        reply_text = await ask_for_dialogue(user_id, context_trigger, system_prompt)
        
        if reply_text:
            formatted_reply = f"{char_data['emoji']} *{char_data['full_name']}:* {reply_text}"
            reply_message = await update.message.reply_text(formatted_reply, parse_mode='Markdown')
            
            # Add explain button
            keyboard = [[InlineKeyboardButton("📒 Explain difficult words", callback_data=f"explain__init__{reply_message.message_id}")]]
            message_cache[reply_message.message_id] = reply_text
            await context.bot.edit_message_reply_markup(
                chat_id=reply_message.chat_id, 
                message_id=reply_message.message_id, 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Log the character's response
            log_message(user_id, f"character_{char_key}", reply_text, get_participant_code(user_id))
            
            logger.info(f"User {user_id}: Character '{char_key}' replied successfully")
            return True
        else:
            logger.error(f"User {user_id}: Character '{char_key}' generated empty reply")
            # Send fallback message
            fallback_message = f"{char_data['full_name']} is thinking..."
            await update.message.reply_text(f"{char_data['emoji']} *{char_data['full_name']}:* *[Character is thinking...]*", parse_mode='Markdown')
            
            # Log the fallback response
            log_message(user_id, f"character_{char_key}", fallback_message, get_participant_code(user_id))
            return True
            
    except Exception as e:
        logger.error(f"User {user_id}: Failed to get character reply from '{char_key}': {e}")
        # Send fallback message
        fallback_message = f"{char_data['full_name']} is thinking..."
        await update.message.reply_text(f"{char_data['emoji']} *{char_data['full_name']}:* *[Character is thinking...]*", parse_mode='Markdown')
        
        # Log the fallback response
        log_message(user_id, f"character_{char_key}", fallback_message)
        return True

async def save_user_game_state(user_id: int):
    """Save the current game state for a user to persistent storage."""
    if user_id in GAME_STATE:
        await game_state_manager.save_game_state(user_id, GAME_STATE[user_id])

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
        # Save state when accusation is unlocked
        await save_user_game_state(user_id)

async def show_main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the main game menu, conditionally showing the accuse button."""
    user_id = update.effective_user.id
    
    # Log the game menu request
    log_message(user_id, "user_action", "Clicked 'Game Menu' button", get_participant_code(user_id))
    
    # Check if user has game state, if not try to restore from saved state
    if user_id not in GAME_STATE:
        # Send immediate response to prevent user from leaving
        typing_message = await update.message.reply_text("🔄 Restoring your game...")
        
        saved_state_data = await game_state_manager.load_game_state(user_id)
        
        if saved_state_data and saved_state_data.get("state"):
            # User has an existing game - restore it silently
            saved_state = saved_state_data["state"]
            # Ensure game_completed flag is set if it doesn't exist
            if "game_completed" not in saved_state:
                saved_state["game_completed"] = False
            GAME_STATE[user_id] = saved_state
            
            # Delete the typing message
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=typing_message.message_id)
            except:
                pass
            
            logger.info(f"User {user_id}: Automatically restored game state from saved data in main menu")
        else:
            # Delete the typing message
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=typing_message.message_id)
            except:
                pass
            
            # No saved state - redirect to start
            await update.message.reply_text("You don't have an active game. Use /start to begin!")
            return
    
    state = GAME_STATE.get(user_id, {})
    
    # Check if game is already completed (but allow final reports)
    if state.get("game_completed"):
        await update.message.reply_text("🎭 Your game has already ended. Use /start to begin a new adventure!")
        return
    
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
    
    # Log the progress report request
    if is_final_report:
        log_message(user_id, "user_action", "Requested final progress report", get_participant_code(user_id))
    else:
        log_message(user_id, "user_action", "Clicked 'Language Progress' button", get_participant_code(user_id))
    
    # Check if user has game_state, if not try to restore from saved state
    if user_id not in GAME_STATE:
        # Send immediate response to prevent user from leaving
        typing_message = await update.message.reply_text("🔄 Restoring your game...")
        
        saved_state_data = await game_state_manager.load_game_state(user_id)
        
        if saved_state_data and saved_state_data.get("state"):
            # User has an existing game - restore it silently
            saved_state = saved_state_data["state"]
            # Ensure game_completed flag is set if it doesn't exist
            if "game_completed" not in saved_state:
                saved_state["game_completed"] = False
            GAME_STATE[user_id] = saved_state
            
            # Delete the typing message
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=typing_message.message_id)
            except:
                pass
            
            logger.info(f"User {user_id}: Automatically restored game state from saved data in progress report")
        else:
            # Delete the typing message
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=typing_message.message_id)
            except:
                pass
            
            # No saved state - redirect to start
            await update.message.reply_text("You don't have an active game. Use /start to begin!")
            return
    
    # Check if game is already completed (but allow final reports)
    if GAME_STATE.get(user_id, {}).get("game_completed") and not is_final_report:
        await update.message.reply_text("🎭 Your game has already ended. Use /start to begin a new adventure!")
        return
    
    # Get progress data from progress manager (Google Cloud Storage)
    logs = progress_manager.get_user_progress(user_id)
    
    # Check if there's any progress data
    if not logs.get("words_learned") and not logs.get("writing_feedback"):
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
        # Show immediate response to prevent user from leaving
        await query.answer("🔄 Restoring your game...")
        
        # Check if user has saved game state and restore it automatically
        saved_state_data = await game_state_manager.load_game_state(user_id)
        
        if saved_state_data and saved_state_data.get("state"):
            # User has an existing game - restore it silently and continue
            saved_state = saved_state_data["state"]
            # Ensure game_completed flag is set if it doesn't exist
            if "game_completed" not in saved_state:
                saved_state["game_completed"] = False
            GAME_STATE[user_id] = saved_state
            
            logger.info(f"User {user_id}: Automatically restored game state from saved data in button callback")
            # Continue processing the button press with restored state
        else:
            await query.edit_message_text(text="This button has expired. Please start over with /start.")
            return

    state = GAME_STATE[user_id]
    
    # Check if game is already completed (but allow final report)
    if state.get("game_completed") and action_type != "final":
        await query.edit_message_text("🎭 Your game has already ended. Use /start to begin a new adventure!")
        return
    
    # ... (остальные блоки if/elif без изменений) ...
    if action_type == "onboarding":
        sub_action = parts[1]
        await query.edit_message_reply_markup(reply_markup=None)

        if sub_action == "step2":
            # Request participant code
            await context.bot.send_message(
                chat_id=user_id, 
                text="Please enter your participant code below (e.g., AN0842):",
                reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True)  # Clear keyboard
            )
            # Set state to wait for participant code
            GAME_STATE[user_id]["waiting_for_participant_code"] = True
            GAME_STATE[user_id]["onboarding_step"] = "waiting_for_code"
        
        elif sub_action == "startgame":
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
            
            # Mark onboarding as complete
            GAME_STATE[user_id]["onboarding_step"] = "completed"
            
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
            
            # Save the completed onboarding state
            await save_user_game_state(user_id)

    elif action_type == "explain":
        sub_action = parts[1]
        if sub_action == "init":
            original_message_id = int(parts[2])
            original_text = message_cache.get(original_message_id, "I couldn't find the original message.")
            
            # Log the explain action initiation
            log_message(user_id, "user_action", f"Clicked 'Explain' button for message: {original_text[:100]}...", get_participant_code(user_id))
            
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
            
            # Log the word explanation request
            log_message(user_id, "user_action", f"Requested explanation for word: '{word_to_explain}' from message: {original_message[:100]}...", get_participant_code(user_id))
            
            await send_tutor_explanation(update, context, word_to_explain, original_message)

        elif sub_action == "all":
            original_message_id = int(parts[2])
            original_text = message_cache.get(original_message_id, "I couldn't find the original message.")
            
            # Log the sentence explanation request
            log_message(user_id, "user_action", f"Requested explanation for entire sentence: {original_text[:100]}...", get_participant_code(user_id))
            
            await send_tutor_explanation(update, context, original_text, original_text)

        elif sub_action == "other":
            state["waiting_for_word"] = True
            
            # Log the custom word explanation request
            log_message(user_id, "user_action", "Requested to explain a custom word/phrase", get_participant_code(user_id))
            
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
        
                    # Log the clue examination
        log_message(user_id, "user_action", f"Examined clue {clue_id}", get_participant_code(user_id))
        
        state["clues_examined"].add(clue_id)
        await check_and_unlock_accuse(user_id, context)
        # Save state when clue is examined
        await save_user_game_state(user_id)

        image_filepath = os.path.join(_BASE_DIR, f"images/clue{clue_id}.png")
        try:
            with open(image_filepath, 'rb') as photo:
                await context.bot.send_photo(chat_id=user_id, photo=photo)
        except (OSError, IOError, FileNotFoundError) as e:
            print(f"[WARNING] Could not load clue image {image_filepath}: {e}")
            # Continue without the image if it can't be loaded
        
        clue_filepath = f"game_texts/Clue{clue_id}.txt"
        clue_text = load_system_prompt(clue_filepath)

        reply_message = await context.bot.send_message(chat_id=user_id, text=clue_text, parse_mode='Markdown')
        if reply_message:
            keyboard = [[InlineKeyboardButton("💡 Explain...", callback_data=f"explain__init__{reply_message.message_id}")]]
            message_cache[reply_message.message_id] = clue_text
            await context.bot.edit_message_reply_markup(chat_id=reply_message.chat_id, message_id=reply_message.message_id, reply_markup=InlineKeyboardMarkup(keyboard))

    elif action_type == "talk":
        character_key = parts[1]
        if character_key in CHARACTER_DATA:
            state.update({"mode": "private", "current_character": character_key})
            
            char_name = CHARACTER_DATA[character_key]["full_name"]
            narrator_prompt = combine_character_prompt("narrator")
            description_text = await ask_for_dialogue(user_id, f"Describe taking {char_name} aside for a private talk.", narrator_prompt)
            
            await query.delete_message()
            reply_message = await context.bot.send_message(chat_id=user_id, text=f"🎙️ _{description_text}_", parse_mode='Markdown')
            keyboard = [[InlineKeyboardButton("💡 Explain...", callback_data=f"explain__init__{reply_message.message_id}")]]
            message_cache[reply_message.message_id] = description_text
            await context.bot.edit_message_reply_markup(chat_id=reply_message.chat_id, message_id=reply_message.message_id, reply_markup=InlineKeyboardMarkup(keyboard))
            
            # Log the narrator's transition description
            log_message(user_id, "narrator", description_text, get_participant_code(user_id))

    elif action_type == "mode":
        sub_action = parts[1]
        if sub_action == "public":
            # Set mode to public and send random common space phrase from narrator
            state.update({"mode": "public", "current_character": None})
            
            # Get random phrase from common_space.txt
            random_phrase = get_random_common_space_phrase()
            
            # Send the phrase from narrator
            reply_message = await context.bot.send_message(
                chat_id=user_id, 
                text=f"🎙️ _{random_phrase}_", 
                parse_mode='Markdown'
            )
            
            # Add explain button
            keyboard = [[InlineKeyboardButton("💡 Explain...", callback_data=f"explain__init__{reply_message.message_id}")]]
            message_cache[reply_message.message_id] = random_phrase
            await context.bot.edit_message_reply_markup(
                chat_id=reply_message.chat_id, 
                message_id=reply_message.message_id, 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Log the narrator's phrase
            log_message(user_id, "narrator", random_phrase, get_participant_code(user_id))
            
            # Delete the menu message
            await query.delete_message()
    
    elif action_type == "final":
        sub_action = parts[1]
        if sub_action == "report":
            # Show final progress report
            await progress_report_handler(update, context, is_final_report=True)
            
            # After showing the report, clean up everything
            await game_state_manager.delete_game_state(user_id)
            GAME_STATE.pop(user_id, None)
            
            # Clear progress data
            progress_manager.clear_user_progress(user_id)
            
            # Send final message and remove inline keyboard
            await query.edit_message_text(
                "🎭 Thank you for playing! Your game data has been cleared. Use /start to begin a new adventure!",
                reply_markup=None
            )
            return True
    
    elif action_type == "accuse":
        sub_action = parts[1]
        if sub_action == "init":
            # Log the accusation initiation
            log_message(user_id, "user_action", "Clicked 'Make an Accusation' button", get_participant_code(user_id))
            
            info_text = load_system_prompt("game_texts/accuse_unlocked.txt")
            keyboard = []
            for key, data in CHARACTER_DATA.items():
                if key in SUSPECT_KEYS:
                    keyboard.append([InlineKeyboardButton(f"{data['emoji']} Accuse {data['full_name']}", callback_data=f"accuse__confirm__{key}")])
            keyboard.append([InlineKeyboardButton("⬅️ Nevermind, go back", callback_data="menu__main")])
            await query.edit_message_text(info_text, reply_markup=InlineKeyboardMarkup(keyboard))

        elif sub_action == "confirm":
            accused_key = parts[2]
            
            # Log the accusation confirmation
            char_name = CHARACTER_DATA[accused_key]['full_name']
            log_message(user_id, "user_action", f"Confirmed accusation against {char_name}", get_participant_code(user_id))
            
            state["waiting_for_accusation_reason"] = True
            state["accused_character"] = accused_key
            
            await query.edit_message_text(f"🎙️ _All eyes turn to {char_name}. You take a deep breath. Now, explain to everyone why you believe this person is guilty. This is your moment to prove you are right._", parse_mode='Markdown')
# --- Вспомогательные функции для обработчиков ---

async def handle_accusation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, user_text: str):
    """Handles the final accusation and ends the game."""
    state = GAME_STATE[user_id]
    state["waiting_for_accusation_reason"] = False
    accused_key = state.get("accused_character")

    # Безопасно запускаем фоновую задачу
    try:
        asyncio.create_task(analyze_and_log_text(user_id, user_text))
    except Exception as e:
        logger.error(f"Failed to create asyncio task for analyze_and_log_text: {e}")

    outro_text = load_system_prompt("game_texts/outro_win.txt") if accused_key == 'tim' else load_system_prompt("game_texts/outro_lose.txt")
    
    await update.message.reply_text(outro_text, parse_mode='Markdown')
    await asyncio.sleep(2)
    
    # Send the questionnaire text
    questionnaire_text = load_system_prompt("game_texts/outro_questionnaire.txt")
    
    # Create inline keyboard with final report button
    keyboard = [[InlineKeyboardButton("📊 See Your Final English Report", callback_data="final__report")]]
    
    await update.message.reply_text(
        questionnaire_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    # Mark game as completed but keep state for final report
    state["game_completed"] = True
    await save_user_game_state(user_id)
    
    return True

async def execute_scene_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, scene_action: dict):
    """Executes a single action from a scene (e.g., character reply, character reaction)."""
    action = scene_action.get("action")
    data = scene_action.get("data", {})
    state = GAME_STATE[user_id]

    if action in ["character_reply", "character_reaction"]:
        char_key = data.get("character_key")
        trigger_msg = data.get("trigger_message")
        if char_key in CHARACTER_DATA and trigger_msg:
            logger.info(f"User {user_id}: Generating reply for character '{char_key}'.")
            char_data = CHARACTER_DATA[char_key]
            system_prompt = combine_character_prompt(char_key)
            reply_text = await ask_for_dialogue(user_id, trigger_msg, system_prompt)
            
            if reply_text:
                logger.info(f"User {user_id}: Character '{char_key}' generated reply: '{reply_text[:100]}...'")
                # Use regular Markdown instead of MarkdownV2 for character replies
                formatted_reply = f"{char_data['emoji']} *{char_data['full_name']}:* {reply_text}"
                
                try:
                    logger.info(f"User {user_id}: Sending formatted reply to user.")
                    reply_message = await update.message.reply_text(formatted_reply, parse_mode='Markdown')
                    logger.info(f"User {user_id}: Successfully sent character reply.")
                    
                    if action == "character_reply":
                        keyboard = [[InlineKeyboardButton("💡 Explain...", callback_data=f"explain__init__{reply_message.message_id}")]]
                        message_cache[reply_message.message_id] = reply_text
                        await context.bot.edit_message_reply_markup(chat_id=reply_message.chat_id, message_id=reply_message.message_id, reply_markup=InlineKeyboardMarkup(keyboard))
                        
                        # Log the character's response
                        log_message(user_id, f"character_{char_key}", reply_text, get_participant_code(user_id))
                except Exception as e:
                    logger.error(f"User {user_id}: FAILED to send message to Telegram. Error: {e}. Original text: '{reply_text}'")
                    # Try sending without markdown as fallback
                    try:
                        fallback_reply = f"{char_data['emoji']} {char_data['full_name']}: {reply_text}"
                        await update.message.reply_text(fallback_reply, parse_mode=None)
                        logger.info(f"User {user_id}: Sent fallback message without markdown.")
                    except Exception as fallback_error:
                        logger.error(f"User {user_id}: Even fallback message failed: {fallback_error}")
                        # Last resort - try to send just the text without any formatting
                        try:
                            await update.message.reply_text(reply_text, parse_mode=None)
                            logger.info(f"User {user_id}: Sent plain text message as last resort.")
                        except Exception as final_error:
                            logger.error(f"User {user_id}: All attempts to send character reply failed: {final_error}")
            else:
                logger.error(f"User {user_id}: Character '{char_key}' generated empty reply.")
                # Send a fallback message when character generates empty reply
                try:
                    fallback_message = f"{char_data['full_name']} is thinking..."
                    await update.message.reply_text(f"{char_data['emoji']} *{char_data['full_name']}:* *[Character is thinking...]*", parse_mode='Markdown')
                    
                    # Log the fallback response
                    log_message(user_id, f"character_{char_key}", fallback_message, get_participant_code(user_id))
                except Exception as fallback_error:
                    logger.error(f"User {user_id}: Failed to send fallback message for empty reply: {fallback_error}")

            # Log the character's response (for both reply and reaction)
            log_message(user_id, f"character_{char_key}", reply_text, get_participant_code(user_id))
            
            if char_key not in state["topic_memory"]["spoken"]:
                state["topic_memory"]["spoken"].append(char_key)

async def process_director_decision(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, user_text: str):
    """Gets a decision from the director and executes the resulting scene for PUBLIC conversations only."""
    state = GAME_STATE[user_id]
    current_mode = state.get("mode", "public")
    topic_memory = state.get("topic_memory", {"topic": "None", "spoken": []})

    # This function now only handles public mode
    if current_mode != "public":
        logger.warning(f"User {user_id}: process_director_decision called for non-public mode: {current_mode}")
        return

    context_for_director = f"Player asks everyone. Topic Memory: {json.dumps(topic_memory)}"

    logger.info(f"User {user_id}: Getting director decision for mode '{current_mode}'.")
    logger.info(f"User {user_id}: Context for director: {context_for_director}")
    logger.info(f"User {user_id}: User text: {user_text}")
    
    director_decision = await ask_director(user_id, context_for_director, user_text)
    logger.info(f"User {user_id}: Director decision received: {director_decision}")

    scene = director_decision.get("scene", [])
    new_topic = director_decision.get("new_topic", topic_memory["topic"])

    state["topic_memory"]["topic"] = new_topic
    if new_topic != topic_memory.get("topic"):
        state["topic_memory"]["spoken"] = []
        # Save state when topic changes
        await save_user_game_state(user_id)

    if not scene:
        logger.warning(f"User {user_id}: Director returned an empty scene for public conversation.")
        log_message(user_id, "director_info", "Director returned an empty scene for public conversation.", get_participant_code(user_id))
        
        # For public mode, we could add a fallback response here if needed
        # For now, just log the issue
        return

    logger.info(f"User {user_id}: Executing scene with {len(scene)} actions: {[action.get('action') for action in scene]}")
    for i, scene_action in enumerate(scene):
        if i > 0:
            await asyncio.sleep(4)
        logger.info(f"User {user_id}: Executing scene action {i+1}/{len(scene)}: {scene_action.get('action')}")
        logger.info(f"User {user_id}: Scene action data: {scene_action.get('data', {})}")
        await execute_scene_action(update, context, user_id, scene_action)


# --- Основной обработчик сообщений ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Orchestrates responses by calling helper functions."""
    # Этот логгер теперь должен сработать в любом случае
    logger.info(f"--- handle_message START for user {update.effective_user.id} ---")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    user_id = update.message.from_user.id
    user_text = update.message.text
    
    # Get participant code for logging (if state exists)
    participant_code = None
    if user_id in GAME_STATE:
        participant_code = GAME_STATE[user_id].get("participant_code")
    log_message(user_id, "user", user_text, participant_code)

    if user_id not in GAME_STATE:
        # Send immediate response to prevent user from leaving
        typing_message = await update.message.reply_text("🔄 Restoring your game...")
        
        # Check if user has saved game state and restore it automatically
        saved_state_data = await game_state_manager.load_game_state(user_id)
        
        if saved_state_data and saved_state_data.get("state"):
            # User has an existing game - restore it silently and continue
            saved_state = saved_state_data["state"]
            # Ensure game_completed flag is set if it doesn't exist
            if "game_completed" not in saved_state:
                saved_state["game_completed"] = False
            GAME_STATE[user_id] = saved_state
            
            # Delete the typing message
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=typing_message.message_id)
            except:
                pass
            
            logger.info(f"User {user_id}: Automatically restored game state from saved data")
            # Continue processing the message with restored state
        else:
            # Delete the typing message
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=typing_message.message_id)
            except:
                pass
            
            # No saved state - start new game
            await start_command_handler(update, context)
            return

    # Check if game is already completed (but allow final reports)
    if GAME_STATE.get(user_id, {}).get("game_completed"):
        await update.message.reply_text("🎭 Your game has already ended. Use /start to begin a new adventure!")
        return

    state = GAME_STATE[user_id]

    # Check if waiting for participant code
    if state.get("waiting_for_participant_code"):
        # Validate participant code format (e.g., AN0842)
        if len(user_text) == 6 and user_text[:2].isalpha() and user_text[2:4].isdigit() and user_text[4:6].isdigit():
            # Store participant code
            state["participant_code"] = user_text.upper()
            state["waiting_for_participant_code"] = False
            
            # Continue with how-to-play instructions
            how_to_play_text = load_system_prompt("game_texts/onboarding_2_howtoplay.txt")
            keyboard = [[InlineKeyboardButton("Start Game", callback_data="onboarding__startgame")]]
            await update.message.reply_text(
                how_to_play_text, 
                reply_markup=InlineKeyboardMarkup(keyboard), 
                parse_mode='Markdown'
            )
            
            # Set onboarding state to continue with game start
            state["onboarding_step"] = "how_to_play"
            
            # Save state with participant code
            await save_user_game_state(user_id)
            logger.info(f"User {user_id}: Participant code '{user_text.upper()}' saved")
            return
        else:
            await update.message.reply_text(
                "❌ Invalid participant code format. Please use the format: First 2 letters + Day (01-31) + Last 2 digits of phone (e.g., AN0842)"
            )
            return

    if state.get("waiting_for_accusation_reason"):
        if await handle_accusation(update, context, user_id, user_text):
            logger.info(f"--- handle_message END for user {user_id} (accusation handled) ---")
            return

    if state.get("waiting_for_word"):
        await send_tutor_explanation(update, context, user_text)
        state["waiting_for_word"] = False
        logger.info(f"--- handle_message END for user {user_id} (word explained) ---")
        return
    
    # Безопасно создаем фоновую задачу
    try:
        asyncio.create_task(analyze_and_log_text(user_id, user_text))
    except Exception as e:
        logger.error(f"Failed to create asyncio task for analyze_and_log_text: {e}")

    if state.get("mode") == "private":
        char_key = state.get("current_character")
        if char_key and char_key not in state.get("suspects_interrogated", set()):
            state["suspects_interrogated"].add(char_key)
            await check_and_unlock_accuse(user_id, context)
            # Save state when suspect is interrogated
            await save_user_game_state(user_id)
        
        # Handle private conversation directly with character (bypass Director AI)
        logger.info(f"User {user_id}: Processing private conversation with character '{char_key}'")
        if await handle_private_character_conversation(update, context, user_id, user_text):
            logger.info(f"--- handle_message END for user {user_id} (private conversation handled) ---")
            # Save state after private conversation
            await save_user_game_state(user_id)
            return
    else:
        # Public mode - use Director AI for scene orchestration
        logger.info(f"User {user_id}: Processing public conversation via Director AI")
        await process_director_decision(update, context, user_id, user_text)
    
    # Save state after processing the message (periodic save)
    await save_user_game_state(user_id)
    
    logger.info(f"--- handle_message END for user {user_id} ---")