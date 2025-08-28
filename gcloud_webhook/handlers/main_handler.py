"""
Main message handler for the Telegram bot.

This module contains the primary message processing function that orchestrates
all bot responses and delegates to appropriate specialized handlers.
"""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from config import GAME_STATE
from utils import load_system_prompt, log_message, get_character_from_message_id
from game_state_manager import game_state_manager

# Import handlers from other modules
from .commands import start_command_handler
from .conversations import handle_private_character_conversation, process_director_decision, handle_character_reply_response
from .tutoring import send_tutor_explanation, analyze_and_log_text
from .game_utils import (
    save_user_game_state,
    check_and_unlock_accuse
)

logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Orchestrates responses by calling helper functions."""
    # Этот логгер теперь должен сработать в любом случае
    logger.info(f"--- handle_message START for user {update.effective_user.id} ---")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    user_id = update.message.from_user.id
    user_text = update.message.text
    
    # Check if this message is a reply to another message
    reply_info = None
    if update.message.reply_to_message:
        reply_info = {
            "replied_to_message_id": update.message.reply_to_message.message_id,
            "replied_to_text": update.message.reply_to_message.text,
            "replied_to_user_id": update.message.reply_to_message.from_user.id if update.message.reply_to_message.from_user else None,
            "replied_to_date": update.message.reply_to_message.date
        }
        logger.info(f"User {user_id}: Replying to message {reply_info['replied_to_message_id']} with text: '{reply_info['replied_to_text'][:50]}...'")
    
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
            keyboard = [[InlineKeyboardButton("🎯 Find Your Language Level", callback_data="onboarding__step5")]]
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
    
    # Check if user is replying to a character message (highest priority)
    if reply_info:
        character_key = get_character_from_message_id(reply_info['replied_to_message_id'])
        if character_key:
            logger.info(f"User {user_id}: Detected reply to character '{character_key}' message")
            # Handle reply to character directly, bypassing normal flow
            if await handle_character_reply_response(update, context, user_id, user_text, character_key, reply_info):
                logger.info(f"--- handle_message END for user {user_id} (character reply handled) ---")
                # Save state after character reply
                await save_user_game_state(user_id)
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
        if await handle_private_character_conversation(update, context, user_id, user_text, reply_info):
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
