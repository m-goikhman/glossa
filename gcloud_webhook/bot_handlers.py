import asyncio
import json
import os
import logging
import time
from datetime import datetime, timedelta
from typing import Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from config import CHARACTER_DATA, GAME_STATE, message_cache, TOTAL_CLUES, SUSPECT_KEYS
from ai_services import ask_for_dialogue, ask_tutor_for_analysis, ask_tutor_for_explanation, ask_tutor_for_final_summary, ask_word_spotter, ask_director
from utils import load_system_prompt, log_message, split_long_message, combine_character_prompt, create_explain_button
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

                "accused_character": None,
                "accusation_attempts": 0,  # Track number of accusation attempts (max 2)
                "reveal_step": 0,  # Track progress through reveal sequence
                "clues_examined": set(),
                "suspects_interrogated": set(),
                "accuse_unlocked": False,
                "topic_memory": {"topic": "Initial greeting", "spoken": []},
                "game_completed": False,
                "participant_code": None,
                "waiting_for_participant_code": False,
                "onboarding_step": "consent",
                "game_start_time": None
            }
            
            # Start with consent message (onboarding step 1)
            consent_text = load_system_prompt("game_texts/onboarding_1_consent.txt")
            keyboard = [[InlineKeyboardButton("📝 Questionnaire done, let's get started!", callback_data="onboarding__step2")]]
            
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
            [KeyboardButton("🔍 Game Menu"), KeyboardButton("� Learning Menu")]
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

            "accused_character": None,
            "accusation_attempts": 0,  # Track number of accusation attempts (max 2)
            "clues_examined": set(),
            "suspects_interrogated": set(),
            "accuse_unlocked": False,
            "topic_memory": {"topic": "Initial greeting", "spoken": []},
            "game_completed": False,
            "participant_code": None,
            "waiting_for_participant_code": False,
            "onboarding_step": "consent",
            "current_intro_message_id": None,
            "current_language_level": "B1",
            "game_start_time": None
        }
        
        consent_text = load_system_prompt("game_texts/onboarding_1_consent.txt")
        keyboard = [[InlineKeyboardButton("📝 Questionnaire done, let's get started!", callback_data="onboarding__step2")]]
        
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

        "accused_character": None,
        "accusation_attempts": 0,  # Track number of accusation attempts (max 2)
        "clues_examined": set(),
        "suspects_interrogated": set(),
        "accuse_unlocked": False,
        "topic_memory": {"topic": "Initial greeting", "spoken": []},
        "game_completed": False,
        "participant_code": None,
        "waiting_for_participant_code": False,
        "onboarding_step": "consent",
        "current_intro_message_id": None,
        "current_language_level": "B1",
        "game_start_time": None
    }
    
    # Start with consent message (onboarding step 1)
    consent_text = load_system_prompt("game_texts/onboarding_1_consent.txt")
    keyboard = [[InlineKeyboardButton("📝 Questionnaire done, let's get started!", callback_data="onboarding__step2")]]
    
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


async def update_keyboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /update_keyboard command - updates the persistent keyboard for existing users."""
    user_id = update.message.from_user.id
    logger.info(f"User {user_id}: Update keyboard command received")
    
    # Check if user has game state, if not try to restore from saved state
    if user_id not in GAME_STATE:
        saved_state_data = await game_state_manager.load_game_state(user_id)
        
        if saved_state_data and saved_state_data.get("state"):
            saved_state = saved_state_data["state"]
            if "game_completed" not in saved_state:
                saved_state["game_completed"] = False
            GAME_STATE[user_id] = saved_state
            logger.info(f"User {user_id}: Restored game state for keyboard update")
            
            # Check if post-test message should be scheduled for restored game
            asyncio.create_task(check_and_schedule_post_test_message(user_id, context))
        else:
            await update.message.reply_text("You don't have an active game. Use /start to begin!")
            return
    
    state = GAME_STATE.get(user_id, {})
    
    # Check if game is already completed
    if state.get("game_completed"):
        await update.message.reply_text("🎭 Your game has already ended. Use /start to begin a new adventure!")
        return
    
    # Update the persistent keyboard
    persistent_keyboard = [
        [KeyboardButton("🔍 Game Menu"), KeyboardButton("� Learning Menu")]
    ]
    reply_markup = ReplyKeyboardMarkup(persistent_keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "✅ **Keyboard Updated!**\n\nYour keyboard now shows the new menu structure.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    logger.info(f"User {user_id}: Keyboard updated successfully")

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
    # Get current language level from user's game state
    current_language_level = state.get("current_language_level", "B1")
    system_prompt = combine_character_prompt(char_key, current_language_level)
    
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
            keyboard = create_explain_button(reply_message.message_id)
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

def is_player_ready_to_accuse(user_id: int) -> Tuple[bool, str]:
    """
    Checks if player is ready to make an accusation.
    Returns: (is_ready, message_describing_what_is_missing)
    """
    state = GAME_STATE.get(user_id, {})
    if not state:
        return False, "Game state not found"
    
    clues_examined = len(state.get("clues_examined", set()))
    suspects_interrogated = len(state.get("suspects_interrogated", set()))
    
    all_clues_examined = clues_examined == TOTAL_CLUES
    all_suspects_interrogated = suspects_interrogated >= len(SUSPECT_KEYS)
    
    if all_clues_examined and all_suspects_interrogated:
        return True, ""
    
    missing_parts = []
    if not all_clues_examined:
        missing_clues = TOTAL_CLUES - clues_examined
        missing_parts.append(f"{missing_clues} more clue{'s' if missing_clues > 1 else ''}")
    
    if not all_suspects_interrogated:
        missing_suspects = len(SUSPECT_KEYS) - suspects_interrogated
        missing_parts.append(f"{missing_suspects} more suspect{'s' if missing_suspects > 1 else ''}")
    
    missing_text = " and ".join(missing_parts)
    return False, f"You still need to examine {missing_text} before making an accusation."

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
            
            # Check if post-test message should be scheduled for restored game
            asyncio.create_task(check_and_schedule_post_test_message(user_id, context))
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
        [InlineKeyboardButton("🗂️ Case Materials", callback_data="menu__evidence")],
        [InlineKeyboardButton("☝️ Make an Accusation", callback_data="accuse__init")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text("What would you like to do?", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("What would you like to do?", reply_markup=InlineKeyboardMarkup(keyboard))


async def show_language_learning_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the language learning menu with options for progress and difficulty settings."""
    user_id = update.effective_user.id
    
    # Log the language learning menu request
    log_message(user_id, "user_action", "Clicked 'Language Learning Menu' button", get_participant_code(user_id))
    
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
            
            logger.info(f"User {user_id}: Automatically restored game state from saved data in language learning menu")
            
            # Check if post-test message should be scheduled for restored game
            asyncio.create_task(check_and_schedule_post_test_message(user_id, context))
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
    
    # Check if game is already completed
    if state.get("game_completed"):
        await update.message.reply_text("🎭 Your game has already ended. Use /start to begin a new adventure!")
        return
    
    # Get current language level
    current_level = state.get("current_language_level", "B1")
    
    # Create inline keyboard for language learning menu
    keyboard = [
        [InlineKeyboardButton("📊 Language Progress", callback_data="language_menu__progress")],
        [InlineKeyboardButton(f"⚙️ Text Difficulty: {current_level}", callback_data="language_menu__difficulty")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"📚 **Language Learning Menu**\n\nCurrent difficulty level: **{current_level}**\n\n• **Language Progress** - View your learning statistics and feedback\n• **Text Difficulty** - Adjust how complex the game text should be (Light/Balanced/Advanced)",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        # If called from a message (e.g., old "Language Progress" button), update the keyboard
        persistent_keyboard = [
            [KeyboardButton("🔍 Game Menu"), KeyboardButton("� Learning Menu")]
        ]
        reply_markup = ReplyKeyboardMarkup(persistent_keyboard, resize_keyboard=True)
        
        # Send the menu and update keyboard in one message
        await update.message.reply_text(
            f"📚 **Language Learning Menu**\n\nCurrent difficulty level: **{current_level}**\n\n• **Language Progress** - View your learning statistics and feedback\n• **Text Difficulty** - Adjust how complex the game text should be (Light/Balanced/Advanced)",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        # Silently update the persistent keyboard
        await context.bot.send_message(
            chat_id=user_id,
            text="",
            reply_markup=reply_markup
        )


async def progress_report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, is_final_report: bool = False):
    """Sends the user a formatted report of their progress using HTML."""
    user_id = update.effective_user.id
    
    # Log the progress report request
    if is_final_report:
        log_message(user_id, "user_action", "Requested final progress report", get_participant_code(user_id))
    else:
        log_message(user_id, "user_action", "Clicked 'Language Progress' button in Language Learning Menu", get_participant_code(user_id))
    
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
            
            # Check if post-test message should be scheduled for restored game
            asyncio.create_task(check_and_schedule_post_test_message(user_id, context))
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
    
    # Log what we received for debugging
    logger.info(f"User {user_id}: Progress data received: {logs}")
    
    # Check if there's any progress data
    if not logs.get("words_learned") and not logs.get("writing_feedback"):
        logger.info(f"User {user_id}: No progress data found. Logs structure: {logs}")
        if not is_final_report:
            await update.message.reply_text("You don't have any saved progress yet!")
        return
    
    logger.info(f"User {user_id}: Found progress data - words_learned: {len(logs.get('words_learned', []))}, writing_feedback: {len(logs.get('writing_feedback', []))}")
    
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
    
    # Add back button to Language Learning Menu if this is not a final report
    if not is_final_report and update.callback_query:
        keyboard = [[InlineKeyboardButton("⬅️ Back to Language Menu", callback_data="language_menu__back")]]
        await context.bot.send_message(
            chat_id=user_id,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def generate_final_english_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates a comprehensive final English report with tutor summary + detailed progress."""
    user_id = update.effective_user.id
    
    # Log the final report request
    log_message(user_id, "user_action", "Requested final English report", get_participant_code(user_id))
    
    # Get progress data from progress manager
    logs = progress_manager.get_user_progress(user_id)
    
    # Note: We always generate a report, even if user had no errors or new words
    # This allows the tutor to congratulate them and suggest higher difficulty
    
    # Send typing indicator
    await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
    
    # Get tutor's final summary
    try:
        tutor_response = await ask_tutor_for_final_summary(user_id, logs)
        tutor_summary = tutor_response.get("summary", "Great job completing the game! You showed curiosity and engagement with English.")
    except Exception as e:
        logger.error(f"Failed to get tutor summary for user {user_id}: {e}")
        tutor_summary = "Great job completing the game! You showed curiosity and engagement with English."
    
    # Build the final report
    report = f"--- \n<b>🎓 Your Final English Report</b>\n---\n\n"
    
    # Add tutor's general summary
    report += f"<b>📝 Your Teacher's Summary:</b>\n"
    report += f"<i>{tutor_summary}</i>\n\n"
    
    # Add detailed progress section
    report += f"<b>📊 Detailed Progress:</b>\n\n"
    
    # Handle case where user had no errors or new words
    if not logs.get("words_learned") and not logs.get("writing_feedback"):
        report += f"🎯 <b>Excellent Performance!</b>\n"
        report += f"• No grammar errors that needed correction\n"
        report += f"• No unfamiliar words encountered\n"
        report += f"• Demonstrated strong English comprehension\n\n"
    else:
        if logs.get("words_learned"):
            report += f"<b>🔤 Words You've Learned ({len(logs['words_learned'])}):</b>\n"
            for entry in logs["words_learned"]:
                word = entry['query']
                definition = entry['feedback']
                report += f"• <code>{word}</code>: <tg-spoiler>{definition}</tg-spoiler>\n"
            report += "\n"
            
        if logs.get("writing_feedback"):
            report += f"<b>✍️ My Feedback on Your Phrases ({len(logs['writing_feedback'])}):</b>\n"
            for entry in logs["writing_feedback"]:
                query = entry['query']
                feedback = entry['feedback']
                report += f"📖 <i>You wrote:</i> {query}\n"
                report += f"✅ <b>My suggestion:</b> {feedback}\n\n"

    # Split and send the report
    message_chunks = split_long_message(report)
    for i, chunk in enumerate(message_chunks):
        if i > 0:
            await asyncio.sleep(1)
        await context.bot.send_message(chat_id=user_id, text=chunk, parse_mode='HTML')

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button presses."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split("__")
    action_type = parts[0]
    
    logger.info(f"User {user_id}: Button callback received - action: {action_type}, data: {query.data}")
    
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
            
            # Check if post-test message should be scheduled for restored game
            asyncio.create_task(check_and_schedule_post_test_message(user_id, context))
            
            # Continue processing the button press with restored state
        else:
            await query.edit_message_text(text="This button has expired. Please start over with /start.")
            return

    state = GAME_STATE[user_id]
    
    # Check if game is already completed (but allow final report and reveal)
    if state.get("game_completed") and action_type not in ["final", "reveal"]:
        await query.edit_message_text("🎭 Your game has already ended. Use /start to begin a new adventure!")
        return
    
    if action_type == "onboarding":
        sub_action = parts[1]
        await query.edit_message_reply_markup(reply_markup=None)

        if sub_action == "step2":
            # Request participant code
            code_text = load_system_prompt("game_texts/onboarding_2_code.txt")
            await context.bot.send_message(
                chat_id=user_id, 
                text=code_text,
                parse_mode='Markdown'
            )
            # Set state to wait for participant code
            GAME_STATE[user_id]["waiting_for_participant_code"] = True
            GAME_STATE[user_id]["onboarding_step"] = "waiting_for_code"
        
        # step3 removed - how to play will be shown after photo
        
        elif sub_action == "step4":
            # Check if participant code was entered
            if not GAME_STATE[user_id].get("participant_code"):
                await query.answer("❌ Please enter your participant code first!")
                return
            
            # Show language level selection
            intro_b1_text = load_system_prompt("game_texts/intro-B1.txt")
            
            # Send intro-B1 with language level buttons (language level text already shown in previous step)
            sent_message = await context.bot.send_message(
                chat_id=user_id, 
                text=intro_b1_text,
                parse_mode='Markdown'
            )
            
            # Add language level selection buttons
            # For B1 level (default), show all three options
            keyboard = [
                [InlineKeyboardButton("Easier", callback_data="language__easier")],
                [InlineKeyboardButton("Perfect!", callback_data="language__perfect")],
                [InlineKeyboardButton("More Advanced", callback_data="language__more_advanced")]
            ]
            
            await context.bot.edit_message_reply_markup(
                chat_id=sent_message.chat_id, 
                message_id=sent_message.message_id, 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Store current intro message ID for language level changes
            GAME_STATE[user_id]["current_intro_message_id"] = sent_message.message_id
            GAME_STATE[user_id]["current_language_level"] = "B1"
            GAME_STATE[user_id]["onboarding_step"] = "language_selection"
            
            # Log the language selection step
            logger.info(f"User {user_id}: Reached language selection step, showing intro-B1 with level buttons")
        
        

    elif action_type == "language":
        sub_action = parts[1]
        
        # Handle "perfect" first, as it's a terminal action in this flow
        if sub_action == "perfect":
            logger.info(f"User {user_id}: Language 'perfect' button clicked")
            # User is satisfied with current level, show confirmation and atmospheric start
            current_level = GAME_STATE[user_id].get("current_language_level", "B1")
            logger.info(f"User {user_id}: Current language level is {current_level}")
            
            current_message_id = GAME_STATE[user_id].get("current_intro_message_id")
            if current_message_id:
                # Just remove buttons from the intro message, don't change text
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=user_id,
                        message_id=current_message_id,
                        reply_markup=None
                    )
                    logger.info(f"User {user_id}: Removed buttons from intro message")
                except Exception as e:
                    logger.warning(f"User {user_id}: Could not remove buttons from intro message: {e}")
            
            # Show level confirmation
            try:
                confirmation_text = load_system_prompt("game_texts/level_confirmed.txt").replace("[LEVEL]", current_level)
                logger.info(f"User {user_id}: Loaded confirmation text: {confirmation_text}")
                await context.bot.send_message(
                    chat_id=user_id,
                    text=confirmation_text,
                    parse_mode='Markdown'
                )
                logger.info(f"User {user_id}: Level confirmation sent successfully")
            except Exception as e:
                logger.error(f"User {user_id}: Error sending level confirmation: {e}")
            
            # Send atmospheric photo with text and "Start Investigation" button
            try:
                atmospheric_text = load_system_prompt("game_texts/atmospheric_start.txt")
                logger.info(f"User {user_id}: Loaded atmospheric text: {atmospheric_text}")
                keyboard = [[InlineKeyboardButton("🕵️ Start Investigation!", callback_data="case_intro__begin")]]
                
                photo_path = "images/aric-cheng-7Bv9MrBan9s-unsplash.jpg"
                logger.info(f"User {user_id}: Attempting to send photo from {photo_path}")
                
                with open(photo_path, "rb") as photo:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=photo,
                        caption=atmospheric_text,
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                logger.info(f"User {user_id}: Atmospheric photo sent successfully")
            except FileNotFoundError:
                logger.error(f"User {user_id}: Photo file not found at {photo_path}")
                # Fallback: send just the text without photo
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🌃 {atmospheric_text}",
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    logger.info(f"User {user_id}: Atmospheric text sent successfully (no photo)")
                except Exception as fallback_e:
                    logger.error(f"User {user_id}: Error sending fallback atmospheric message: {fallback_e}")
            except Exception as e:
                logger.error(f"User {user_id}: Error sending atmospheric photo: {e}")
                # Fallback: send just the text without photo
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🌃 {atmospheric_text}",
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    logger.info(f"User {user_id}: Atmospheric text sent successfully (fallback)")
                except Exception as fallback_e:
                    logger.error(f"User {user_id}: Error sending fallback atmospheric message: {fallback_e}")
            
            # Log the language level confirmation
            logger.info(f"User {user_id}: Confirmed language level {current_level}, showing atmospheric start with start button")
            return

        # Handle level changes ("easier" or "more_advanced")
        current_level = state.get("current_language_level", "B1")
        new_level = current_level

        if sub_action == "easier":
            if current_level == "B2":
                new_level = "B1"
            elif current_level == "B1":
                new_level = "A2"
        elif sub_action == "more_advanced":
            if current_level == "A2":
                new_level = "B1"
            elif current_level == "B1":
                new_level = "B2"

        if new_level != current_level:
            current_message_id = GAME_STATE[user_id].get("current_intro_message_id")
            if not current_message_id:
                logger.error(f"User {user_id}: No current intro message ID found for language change")
                return

            # Show loading animation
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=current_message_id,
                text="🔄 Adjusting text difficulty...",
                parse_mode='Markdown'
            )
            await asyncio.sleep(1.5)

            # Determine text and keyboard for the new level
            if new_level == "A2":
                intro_text = load_system_prompt("game_texts/intro-A2.txt")
                keyboard_layout = [
                    [InlineKeyboardButton("Perfect!", callback_data="language__perfect")],
                    [InlineKeyboardButton("More Advanced", callback_data="language__more_advanced")]
                ]
            elif new_level == "B2":
                intro_text = load_system_prompt("game_texts/intro-B2.txt")
                keyboard_layout = [
                    [InlineKeyboardButton("Easier", callback_data="language__easier")],
                    [InlineKeyboardButton("Perfect!", callback_data="language__perfect")]
                ]
            else:  # B1
                intro_text = load_system_prompt("game_texts/intro-B1.txt")
                keyboard_layout = [
                    [InlineKeyboardButton("Easier", callback_data="language__easier")],
                    [InlineKeyboardButton("Perfect!", callback_data="language__perfect")],
                    [InlineKeyboardButton("More Advanced", callback_data="language__more_advanced")]
                ]

            # Update message text and keyboard
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=current_message_id,
                text=intro_text,
                parse_mode='Markdown'
            )
            await context.bot.edit_message_reply_markup(
                chat_id=user_id,
                message_id=current_message_id,
                reply_markup=InlineKeyboardMarkup(keyboard_layout)
            )

            # Update state and log the change
            GAME_STATE[user_id]["current_language_level"] = new_level
            logger.info(f"User {user_id}: Changed language level from {current_level} to {new_level}")

    elif action_type == "language_menu":
        sub_action = parts[1]
        
        if sub_action == "progress":
            # Show language progress report
            await progress_report_handler(update, context, is_final_report=False)
            
        elif sub_action == "difficulty":
            # Show difficulty selection menu
            current_level = state.get("current_language_level", "B1")
            
            # Create difficulty selection keyboard
            keyboard = []
            
            if current_level != "A2":
                keyboard.append([InlineKeyboardButton("🌱 Light", callback_data="difficulty__set__A2")])
            
            keyboard.append([InlineKeyboardButton("⚖️ Balanced", callback_data="difficulty__set__B1")])
            
            if current_level != "B2":
                keyboard.append([InlineKeyboardButton("🚀 Advanced", callback_data="difficulty__set__B2")])
            
            keyboard.append([InlineKeyboardButton("⬅️ Back to Language Menu", callback_data="language_menu__back")])
            
            await query.edit_message_text(
                f"⚙️ **Text Difficulty Settings**\n\nCurrent level: **{current_level}**\n\nChoose your preferred difficulty level:\n\n🌱 **Light (A2)** - Simple vocabulary and grammar\n⚖️ **Balanced (B1)** - Intermediate level, balanced complexity\n🚀 **Advanced (B2)** - More complex structures and vocabulary",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        elif sub_action == "back":
            # Return to language learning menu
            await show_language_learning_menu_handler(update, context)

    elif action_type == "difficulty":
        sub_action = parts[1]
        
        if sub_action == "set":
            new_level = parts[2]
            old_level = state.get("current_language_level", "B1")
            
            # Update the language level
            state["current_language_level"] = new_level
            
            # Save the updated state
            await save_user_game_state(user_id)
            
            # Log the difficulty change
            log_message(user_id, "user_action", f"Changed text difficulty from {old_level} to {new_level}", get_participant_code(user_id))
            logger.info(f"User {user_id}: Changed text difficulty from {old_level} to {new_level}")
            
            # Show confirmation and return to language learning menu
            await query.edit_message_text(
                f"✅ **Difficulty Updated!**\n\nYour text difficulty has been changed from **{old_level}** to **{new_level}**.\n\nThis setting will apply to all new conversations and character interactions. You can change it anytime from the Language Learning Menu.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Back to Language Menu", callback_data="language_menu__back")
                ]]),
                parse_mode='Markdown'
            )

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
                [InlineKeyboardButton("💡 Detective Guide", callback_data="guide__detective")],
                [InlineKeyboardButton("Initial Report", callback_data="clue__1")],
                [InlineKeyboardButton("The Weapon", callback_data="clue__2")],
                [InlineKeyboardButton("The Note", callback_data="clue__3")],
                [InlineKeyboardButton("The Apartment", callback_data="clue__4")],
                [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="menu__main")]
            ]
            await query.edit_message_text("What would you like to examine?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif action_type == "guide":
        sub_action = parts[1]
        if sub_action == "detective":
            # Log the guide viewing
            log_message(user_id, "user_action", "Viewed Detective Guide", get_participant_code(user_id))
            
            # Send the detective guide image
            try:
                guide_path = "images/detective_guide.png"
                with open(guide_path, "rb") as photo:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=photo,
                        caption="💡 **Detective Guide**\n\nHere are some ideas to get your investigation started!\n\n💬 **Pro tip**: People reveal more in private conversations than in group settings!",
                        parse_mode='Markdown'
                    )
            except FileNotFoundError:
                # Fallback if image not found
                await context.bot.send_message(
                    chat_id=user_id,
                    text="💡 **Detective Guide**\n\n🔹 Ask suspects where they were when Alex was found\n🔹 Find out what each person's relationship with Alex was\n🔹 Ask about the party - who came, what happened?\n🔹 Look for inconsistencies in their stories\n🔹 Ask about Alex's recent behavior or problems\n🔹 Find out who had access to Alex's apartment\n\n💬 **Pro tip**: People reveal more in private conversations than in group settings!",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error sending detective guide: {e}")
                # Fallback text
                await context.bot.send_message(
                    chat_id=user_id,
                    text="💡 **Detective Guide**\n\nSorry, there was an issue loading the guide image. Here are some starter questions:\n\n🔹 Ask suspects where they were when Alex was found\n🔹 Find out what each person's relationship with Alex was\n🔹 Ask about the party - who came, what happened?\n\n💬 **Pro tip**: People reveal more in private conversations than in group settings!",
                    parse_mode='Markdown'
                )

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
            keyboard = create_explain_button(reply_message.message_id)
            message_cache[reply_message.message_id] = clue_text
            await context.bot.edit_message_reply_markup(chat_id=reply_message.chat_id, message_id=reply_message.message_id, reply_markup=InlineKeyboardMarkup(keyboard))

    elif action_type == "talk":
        character_key = parts[1]
        if character_key in CHARACTER_DATA:
            state.update({"mode": "private", "current_character": character_key})
            
            char_name = CHARACTER_DATA[character_key]["full_name"]
            # Get current language level from user's game state
            current_language_level = state.get("current_language_level", "B1")
            narrator_prompt = combine_character_prompt("narrator", current_language_level)
            description_text = await ask_for_dialogue(user_id, f"Describe taking {char_name} aside for a private talk.", narrator_prompt)
            
            await query.delete_message()
            reply_message = await context.bot.send_message(chat_id=user_id, text=f"🎙️ _{description_text}_", parse_mode='Markdown')
            keyboard = create_explain_button(reply_message.message_id)
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
            keyboard = create_explain_button(reply_message.message_id)
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
    
    elif action_type == "reveal":
        sub_action = parts[1]
        
        # Define reveal steps with their files and button texts
        reveal_steps = [
            {"file": "game_texts/reveal_1_truth.txt", "button": "So was it Pauline?"},
            {"file": "game_texts/reveal_2_killer.txt", "button": "Show me the evidence"},
            {"file": "game_texts/reveal_3_evidence.txt", "button": "How it happened?"},
            {"file": "game_texts/reveal_4_timeline.txt", "button": "Ok, but why?"},
            {"file": "game_texts/reveal_5_motive.txt", "button": None}  # Final step with no button
        ]
        
        if sub_action == "start":
            # Show first reveal message
            state["reveal_step"] = 0
            
        elif sub_action == "next":
            # Move to next reveal message
            current_step = state.get("reveal_step", 0) + 1
            state["reveal_step"] = current_step
        else:
            # Invalid sub_action, default to first step
            state["reveal_step"] = 0
        
        # Get current step
        current_step = state.get("reveal_step", 0)
        
        if current_step < len(reveal_steps):
            step_data = reveal_steps[current_step]
            try:
                text = load_system_prompt(step_data["file"])
                
                if step_data["button"]:
                    keyboard = [[InlineKeyboardButton(step_data["button"], callback_data="reveal__next")]]
                    await query.edit_message_text(
                        text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
                else:
                    # Final message - show questionnaire after
                    await query.edit_message_text(text, parse_mode='Markdown')
                    
                    # Show questionnaire after final reveal
                    questionnaire_text = load_system_prompt("game_texts/outro_questionnaire.txt")
                    keyboard = [[InlineKeyboardButton("📊 See Your Final English Report", callback_data="final__report")]]
                    
                    await query.message.reply_text(
                        questionnaire_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"Failed to load reveal file {step_data['file']}: {e}")
                await query.edit_message_text("🎭 The case is now closed. Thank you for playing!", parse_mode='Markdown')
        else:
            # All messages shown - shouldn't happen with new logic, but safety fallback
            await query.edit_message_text("🎭 The case is now closed. Thank you for playing!", parse_mode='Markdown')
            
            await save_user_game_state(user_id)
    
    elif action_type == "restart":
        sub_action = parts[1]
        if sub_action == "game":
            # Restart the game
            await restart_command_handler(update, context)
            return True
    
    elif action_type == "final":
        sub_action = parts[1]
        if sub_action == "report":
            # Show final progress report with tutor summary
            await generate_final_english_report(update, context)
            
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
            
            # Check if player is ready to make an accusation
            is_ready, missing_info = is_player_ready_to_accuse(user_id)
            
            if is_ready:
                # Player is ready - show normal accusation menu
                info_text = load_system_prompt("game_texts/accuse_unlocked.txt")
                keyboard = []
                for key, data in CHARACTER_DATA.items():
                    if key in SUSPECT_KEYS:
                        keyboard.append([InlineKeyboardButton(f"{data['emoji']} Accuse {data['full_name']}", callback_data=f"accuse__confirm__{key}")])
                keyboard.append([InlineKeyboardButton("⬅️ Nevermind, go back", callback_data="menu__main")])
                await query.edit_message_text(info_text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                # Player is not ready - show warning
                warning_text = load_system_prompt("game_texts/accuse_warning.txt")
                # Replace placeholder with specific missing info
                warning_text = warning_text.replace("{missing_info}", missing_info)
                
                keyboard = [
                    [InlineKeyboardButton("Yes, I'm sure - Make Accusation", callback_data="accuse__force")],
                    [InlineKeyboardButton("You're right, let me investigate more", callback_data="menu__main")]
                ]
                await query.edit_message_text(warning_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        elif sub_action == "force":
            # Player insists on making accusation despite warning
            log_message(user_id, "user_action", "Insisted on making accusation despite warning", get_participant_code(user_id))
            
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
            
            # Show attempt number (max 2 attempts)
            attempt_number = state.get("accusation_attempts", 0) + 1
            attempts_text = f" (Attempt {attempt_number}/2)" if attempt_number > 1 else ""
            
            await query.edit_message_text(f"🎙️ _You point at {char_name}. All eyes turn to them.{attempts_text}_", parse_mode='Markdown')
            
            # Process accusation immediately without asking for explanation
            await handle_accusation_direct(update, context, user_id, accused_key)

    elif action_type == "case_intro":
        logger.info(f"User {user_id}: case_intro action triggered with sub_action: {parts[1]}")
        sub_action = parts[1]
        
        if sub_action == "situation":
            # Show the situation details as a new message
            try:
                situation_text = load_system_prompt("game_texts/case_intro_2_situation.txt")
                logger.info(f"User {user_id}: Successfully loaded situation_text: {situation_text[:100]}...")
            except Exception as e:
                logger.error(f"User {user_id}: Failed to load case_intro_2_situation.txt: {e}")
                # Fallback to default text
                situation_text = "📍 THE SITUATION\n\nAlex was found unconscious in his bathroom after a Christmas party."
            
            # Send new message with situation text and next button
            sent_message = await context.bot.send_message(
                chat_id=user_id,
                text=situation_text,
                parse_mode='Markdown'
            )
            
            # Add next button
            keyboard = [
                [InlineKeyboardButton("Who was there?", callback_data="case_intro__suspects")]
            ]
            
            await context.bot.edit_message_reply_markup(
                chat_id=sent_message.chat_id,
                message_id=sent_message.message_id,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Remove button from previous message
            await query.edit_message_reply_markup(reply_markup=None)
            
        elif sub_action == "suspects":
            # Show the suspects information as a new message
            try:
                suspects_text = load_system_prompt("game_texts/case_intro_3_suspects.txt")
                logger.info(f"User {user_id}: Successfully loaded suspects_text: {suspects_text[:100]}...")
            except Exception as e:
                logger.error(f"User {user_id}: Failed to load case_intro_3_suspects.txt: {e}")
                # Fallback to default text
                suspects_text = "👥 FOUR PEOPLE ARE IN THE APARTMENT\n\nNobody can leave until you complete your investigation."
            
            # Send photo with suspects text as caption
            try:
                photo_path = "images/suspects.png"
                logger.info(f"User {user_id}: Attempting to send photo from {photo_path}")
                
                with open(photo_path, "rb") as photo:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=photo,
                        caption=suspects_text,
                        parse_mode='Markdown'
                    )
                logger.info(f"User {user_id}: Suspects photo sent successfully")
            
            except FileNotFoundError:
                logger.error(f"User {user_id}: Photo file not found at {photo_path}")
                # Fallback: send just the text without photo
                await context.bot.send_message(
                    chat_id=user_id,
                    text=suspects_text,
                    parse_mode='Markdown'
                )
            
            except Exception as e:
                logger.error(f"User {user_id}: Error sending suspects photo: {e}")
                # Fallback: send just the text without photo
                await context.bot.send_message(
                    chat_id=user_id,
                    text=suspects_text,
                    parse_mode='Markdown'
                )
            
            # Remove button from previous message
            await query.edit_message_reply_markup(reply_markup=None)
            
            # Add "How to play?" button
            keyboard = [[InlineKeyboardButton("🎮 How to play?", callback_data="case_intro__how_to_play")]]
            await context.bot.send_message(
                chat_id=user_id,
                text="🧩 Ready to start the game?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        elif sub_action == "how_to_play":
            # Remove the "How to play?" button
            await query.edit_message_reply_markup(reply_markup=None)

            # Show how to play instructions
            how_to_play_text = load_system_prompt("game_texts/onboarding_3_howtoplay.txt")
            await context.bot.send_message(
                chat_id=user_id,
                text=how_to_play_text,
                parse_mode='Markdown'
            )
            
            # Add persistent keyboard for game menu and language learning
            persistent_keyboard = [
                [KeyboardButton("🔍 Game Menu"), KeyboardButton("� Learning Menu")]
            ]
            reply_markup = ReplyKeyboardMarkup(persistent_keyboard, resize_keyboard=True)
            
            await context.bot.send_message(
                chat_id=user_id,
                text="Game menu and language learning options are now available on the panel below 👇",
                reply_markup=reply_markup
            )

        elif sub_action == "begin":
            # Show the first case introduction (this is called from the Start Investigation button)
            logger.info(f"User {user_id}: Starting case introduction sequence")
            
            # Record game start time
            GAME_STATE[user_id]["game_start_time"] = time.time()
            logger.info(f"User {user_id}: Game start time recorded")
            
            # Save state with game start time
            await save_user_game_state(user_id)
            
            # Schedule post-test message after 1 hour
            post_test_delay = 3600  # 1 hour in seconds
            asyncio.create_task(schedule_post_test_message(user_id, context, post_test_delay))
            logger.info(f"User {user_id}: Post-test message scheduled for {post_test_delay} seconds later")
            
            try:
                case_intro_1_text = load_system_prompt("game_texts/case_intro_1_call.txt")
                logger.info(f"User {user_id}: Successfully loaded case_intro_1_text: {case_intro_1_text[:100]}...")
            except Exception as e:
                logger.error(f"User {user_id}: Failed to load case_intro_1_call.txt: {e}")
                # Fallback to default text
                case_intro_1_text = "📞 THE EMERGENCY CALL\n\nFiona called 911 a panic about Alex being unconscious."
            
            # Send the first case introduction with button
            sent_message = await context.bot.send_message(
                chat_id=user_id,
                text=case_intro_1_text,
                parse_mode='Markdown'
            )
            
            # Add first navigation button - sequential flow
            keyboard = [
                [InlineKeyboardButton("What happened?", callback_data="case_intro__situation")]
            ]
            
            await context.bot.edit_message_reply_markup(
                chat_id=sent_message.chat_id,
                message_id=sent_message.message_id,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

# --- Вспомогательные функции для обработчиков ---



async def handle_accusation_direct(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, accused_key: str):
    """Handles accusation directly without asking for explanation."""
    state = GAME_STATE[user_id]
    
    # Increment attempt counter
    state["accusation_attempts"] += 1

    # Note: We don't analyze button clicks as these are not user-written text

    # Check if the accusation is correct (Tim is the killer)
    if accused_key == 'tim':
        # Correct accusation - player wins
        outro_text = load_system_prompt("game_texts/outro_win.txt")
        
        await asyncio.sleep(1)  # Brief pause for drama
        await update.callback_query.message.reply_text(outro_text, parse_mode='Markdown')
        await asyncio.sleep(2)
        
        # Send the questionnaire text
        questionnaire_text = load_system_prompt("game_texts/outro_questionnaire.txt")
        
        # Create inline keyboard with final report button
        keyboard = [[InlineKeyboardButton("📊 See Your Final English Report", callback_data="final__report")]]
        
        await update.callback_query.message.reply_text(
            questionnaire_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        # Mark game as completed but keep state for final report
        state["game_completed"] = True
        await save_user_game_state(user_id)
        
    else:
        # Wrong accusation - always show defense first
        defense_text = load_system_prompt(f"game_texts/defense_{accused_key}.txt")
        
        await asyncio.sleep(1)  # Brief pause for drama
        await update.callback_query.message.reply_text(defense_text, parse_mode='Markdown')
        
        if state["accusation_attempts"] >= 2:
            # Second wrong attempt - show game over after defense
            await asyncio.sleep(3)  # Longer pause to let player read the defense
            
            outro_text = load_system_prompt("game_texts/outro_lose.txt")
            
            # Create keyboard based on outro_lose.txt instructions
            keyboard = [
                [InlineKeyboardButton("📖 Yes, show me", callback_data="reveal__start")],
                [InlineKeyboardButton("🔄 Start again", callback_data="restart__game")]
            ]
            
            await update.callback_query.message.reply_text(
                outro_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            
            # Mark game as completed but keep state for final report
            state["game_completed"] = True
            await save_user_game_state(user_id)
            
        else:
            # First wrong attempt - show options for second chance
            await asyncio.sleep(2)  # Pause to let player read the defense
            
            # Create keyboard with options for second attempt
            keyboard = [
                [InlineKeyboardButton("🔄 Make Another Accusation", callback_data="accuse__init")],
                [InlineKeyboardButton("🔍 Continue Investigation", callback_data="menu__main")]
            ]
            
            await update.callback_query.message.reply_text(
                "What would you like to do next?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Reset accusation state but keep attempt counter
            state["accused_character"] = None
            await save_user_game_state(user_id)



async def execute_scene_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, scene_action: dict):
    """Executes a single action from a scene (e.g., character reply, character reaction)."""
    action = scene_action.get("action")
    data = scene_action.get("data", {})
    state = GAME_STATE[user_id]

    if action == "director_note":
        # Handle director narrative/guidance message
        message = data.get("message", "The investigation continues...")
        logger.info(f"User {user_id}: Sending director note: '{message[:50]}...'")
        
        # Format as a narrative message
        formatted_message = f"🎬 *Narrator:* _{message}_"
        
        try:
            await update.message.reply_text(formatted_message, parse_mode='Markdown')
            logger.info(f"User {user_id}: Successfully sent director note.")
        except Exception as e:
            logger.error(f"User {user_id}: Failed to send director note: {e}")
            # Fallback without formatting
            await update.message.reply_text(message)
        
    elif action in ["character_reply", "character_reaction"]:
        char_key = data.get("character_key")
        trigger_msg = data.get("trigger_message")
        if char_key in CHARACTER_DATA and trigger_msg:
            logger.info(f"User {user_id}: Generating reply for character '{char_key}'.")
            char_data = CHARACTER_DATA[char_key]
            # Get current language level from user's game state
            current_language_level = state.get("current_language_level", "B1")
            system_prompt = combine_character_prompt(char_key, current_language_level)
            reply_text = await ask_for_dialogue(user_id, trigger_msg, system_prompt)
            
            if reply_text:
                logger.info(f"User {user_id}: Character '{char_key}' generated reply: '{reply_text[:100]}...'")
                # Use regular Markdown instead of MarkdownV2 for character replies
                formatted_reply = f"{char_data['emoji']} *{char_data['full_name']}:* {reply_text}"
                
                try:
                    logger.info(f"User {user_id}: Sending formatted reply to user.")
                    reply_message = await update.message.reply_text(formatted_reply, parse_mode='Markdown')
                    logger.info(f"User {user_id}: Successfully sent character reply.")
                    
                    # Add explain button for both character_reply and character_reaction
                    keyboard = create_explain_button(reply_message.message_id)
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

            # Character response already logged above in the try block
            
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


async def check_and_schedule_post_test_message(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Check if post-test message should be scheduled for restored game state."""
    if user_id not in GAME_STATE:
        return
        
    state = GAME_STATE[user_id]
    game_start_time = state.get("game_start_time")
    
    if not game_start_time or state.get("game_completed", False):
        return
    
    # Calculate how much time has passed since game start
    current_time = time.time()
    elapsed_time = current_time - game_start_time
    
    post_test_delay = 3600
    
    if elapsed_time >= post_test_delay:
        # Post-test should have been sent already, send immediately
        logger.info(f"User {user_id}: Post-test message overdue, sending immediately")
        asyncio.create_task(schedule_post_test_message(user_id, context, 0))
    else:
        # Calculate remaining time until post-test should be sent
        remaining_time = post_test_delay - elapsed_time
        logger.info(f"User {user_id}: Post-test message scheduled for {remaining_time:.0f} seconds from now")
        asyncio.create_task(schedule_post_test_message(user_id, context, remaining_time))


async def schedule_post_test_message(user_id: int, context: ContextTypes.DEFAULT_TYPE, delay_seconds: float = 3600):
    """Schedules the post-test message to be sent after the specified delay."""
    try:
        # Wait for the specified delay
        await asyncio.sleep(delay_seconds)
        
        # Check if user still has active game state
        if user_id not in GAME_STATE:
            logger.info(f"User {user_id}: Post-test message cancelled - no active game state")
            return
            
        # Check if game was completed (if so, don't send post-test)
        if GAME_STATE[user_id].get("game_completed", False):
            logger.info(f"User {user_id}: Post-test message cancelled - game already completed")
            return
        
        # Load post-test message
        try:
            post_test_text = load_system_prompt("game_texts/post-test.txt")
        except Exception as e:
            logger.error(f"User {user_id}: Failed to load post-test.txt: {e}")
            post_test_text = "📋 Second questionnaire is now available.\n\nComplete it now or continue playing and fill it out later. Thank you!\n\nLink: https://forms.gle/zd6dsxFDgGHp5TxK9\n\n(This message stays pinned so you won't lose the link)"
        
        # Send the message
        message = await context.bot.send_message(
            chat_id=user_id,
            text=post_test_text,
            parse_mode='Markdown'
        )
        
        # Pin the message
        try:
            await context.bot.pin_chat_message(
                chat_id=user_id,
                message_id=message.message_id
            )
            logger.info(f"User {user_id}: Post-test message sent and pinned successfully")
        except Exception as e:
            logger.error(f"User {user_id}: Failed to pin post-test message: {e}")
            logger.info(f"User {user_id}: Post-test message sent but not pinned")
            
        # Log the message send
        log_message(user_id, "system", "Post-test questionnaire message sent", get_participant_code(user_id))
        
    except asyncio.CancelledError:
        logger.info(f"User {user_id}: Post-test message task was cancelled")
    except Exception as e:
        logger.error(f"User {user_id}: Error in post-test message scheduling: {e}")


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
            
            # Check if post-test message should be scheduled for restored game
            asyncio.create_task(check_and_schedule_post_test_message(user_id, context))
            
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
        # Validate participant code format (e.g., AN0842) or TEST for testers
        is_valid_regular_code = (len(user_text) == 6 and user_text[:2].isalpha() and 
                                user_text[2:4].isdigit() and user_text[4:6].isdigit())
        is_test_code = user_text.upper() == "TEST"
        
        if is_valid_regular_code or is_test_code:
            # Store participant code
            state["participant_code"] = user_text.upper()
            state["waiting_for_participant_code"] = False
            
            # Continue with language level selection
            keyboard = [[InlineKeyboardButton("🎯 Find Your Language Level", callback_data="onboarding__step4")]]
            language_level_text = load_system_prompt("game_texts/onboarding_4_language_level.txt")
            await update.message.reply_text(
                language_level_text, 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Set onboarding state to continue with language selection
            state["onboarding_step"] = "waiting_for_language_selection"
            
            # Log the transition
            logger.info(f"User {user_id}: Participant code saved, moving to language selection step")
            
            # Save state with participant code
            await save_user_game_state(user_id)
            logger.info(f"User {user_id}: Participant code '{user_text.upper()}' saved")
            return
        else:
            await update.message.reply_text(
                "❌ Invalid participant code format. Please use the format: First 2 letters + Day (01-31) + Last 2 digits of phone (e.g., AN0842)"
            )
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