"""
Command handlers for the Telegram bot.

This module contains handlers for bot commands like /start, /restart, etc.
"""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from config import GAME_STATE, POST_TEST_TASKS
from utils import load_system_prompt, log_message
from game_state_manager import game_state_manager
from progress_manager import progress_manager

logger = logging.getLogger(__name__)


# Import utility functions from game_utils
from .game_utils import get_participant_code, cancel_post_test_task, check_and_schedule_post_test_message


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
            
            # Cancel any existing post-test task
            cancel_post_test_task(user_id)
            
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
                "custom_reveal_step": 0,  # Track progress through custom reveal sequence
                "clues_examined": set(),
                "suspects_interrogated": set(),
                "accuse_unlocked": False,
                "topic_memory": {"topic": "Initial greeting", "spoken": []},
                "game_completed": False,
                "participant_code": None,
                "waiting_for_participant_code": False,
                "onboarding_step": "consent",
                "game_start_time": None,
                "message_count": 0  # Track user messages since game start
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
        # Ensure message_count field exists for backwards compatibility
        if "message_count" not in saved_state:
            saved_state["message_count"] = 0
        GAME_STATE[user_id] = saved_state
        
        # Set up persistent keyboard
        persistent_keyboard = [
            [KeyboardButton("🔍 Game Menu"), KeyboardButton("✍️ Learning Menu")]
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
            "reveal_step": 0,  # Track progress through reveal sequence
            "custom_reveal_step": 0,  # Track progress through custom reveal sequence
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
            "game_start_time": None,
            "message_count": 0  # Track user messages since game start
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
    
    # Cancel any existing post-test task
    cancel_post_test_task(user_id)
    
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
        "reveal_step": 0,  # Track progress through reveal sequence
        "custom_reveal_step": 0,  # Track progress through custom reveal sequence
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
        "game_start_time": None,
        "message_count": 0  # Track user messages since game start
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
        [KeyboardButton("🔍 Game Menu"), KeyboardButton("✍️ Learning Menu")]
    ]
    reply_markup = ReplyKeyboardMarkup(persistent_keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "✅ **Keyboard Updated!**\n\nYour keyboard now shows the new menu structure.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    logger.info(f"User {user_id}: Keyboard updated successfully")


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
            # Ensure message_count field exists for backwards compatibility
            if "message_count" not in saved_state:
                saved_state["message_count"] = 0
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
    """Sends the ✍️ Learning Menu with options for progress and difficulty settings."""
    user_id = update.effective_user.id
    
    # Log the ✍️ Learning Menu request
    log_message(user_id, "user_action", "Clicked '✍️ Learning Menu' button", get_participant_code(user_id))
    
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
            # Ensure message_count field exists for backwards compatibility
            if "message_count" not in saved_state:
                saved_state["message_count"] = 0
            GAME_STATE[user_id] = saved_state
            
            # Delete the typing message
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=typing_message.message_id)
            except:
                pass
            
            logger.info(f"User {user_id}: Automatically restored game state from saved data in ✍️ Learning Menu")
            
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
    
    # Create inline keyboard for ✍️ Learning Menu
    keyboard = [
        [InlineKeyboardButton("📊 Language Progress", callback_data="language_menu__progress")],
        [InlineKeyboardButton(f"⚙️ Text Difficulty: {current_level}", callback_data="language_menu__difficulty")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"📚 **✍️ Learning Menu**\n\nCurrent difficulty level: **{current_level}**\n\n• **Language Progress** - View your learning statistics and feedback\n• **Text Difficulty** - Adjust how complex the game text should be (Light/Balanced/Advanced)",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        # If called from a message (e.g., old "Language Progress" button), update the keyboard
        persistent_keyboard = [
            [KeyboardButton("🔍 Game Menu"), KeyboardButton("✍️ Learning Menu")]
        ]
        reply_markup = ReplyKeyboardMarkup(persistent_keyboard, resize_keyboard=True)
        
        # Send the menu and update keyboard in one message
        await update.message.reply_text(
            f"📚 **✍️ Learning Menu**\n\nCurrent difficulty level: **{current_level}**\n\n• **Language Progress** - View your learning statistics and feedback\n• **Text Difficulty** - Adjust how complex the game text should be (Light/Balanced/Advanced)",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        # Silently update the persistent keyboard
        await context.bot.send_message(
            chat_id=user_id,
            text="",
            reply_markup=reply_markup
        )
