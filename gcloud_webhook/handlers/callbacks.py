"""
Main callback dispatcher for the Telegram bot.

This module provides a clean, modular dispatch system for handling all inline button presses.
It routes callbacks to appropriate specialized handlers based on action type.
"""

import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes

from config import GAME_STATE
from game_state_manager import game_state_manager


# Import all specialized callback handlers
from .callback_modules import (
    handle_onboarding_action,
    handle_language_action, 
    handle_case_intro_action,
    handle_language_menu_action,
    handle_difficulty_action,
    handle_menu_action,
    handle_guide_action,
    handle_clue_action,
    handle_talk_action,
    handle_mode_action,
    handle_accuse_action,
    handle_explain_action,
    handle_reveal_action,
    handle_reveal_custom_action,
    handle_restart_action,
    handle_final_action
)

logger = logging.getLogger(__name__)

# Action type to handler mapping
ACTION_HANDLERS = {
    "onboarding": handle_onboarding_action,
    "language": handle_language_action,
    "case_intro": handle_case_intro_action,
    "language_menu": handle_language_menu_action,
    "difficulty": handle_difficulty_action,
    "menu": handle_menu_action,
    "guide": handle_guide_action,
    "clue": handle_clue_action,
    "talk": handle_talk_action,
    "mode": handle_mode_action,
    "accuse": handle_accuse_action,
    "explain": handle_explain_action,
    "reveal": handle_reveal_action,
    "reveal_custom": handle_reveal_custom_action,
    "restart": handle_restart_action,
    "final": handle_final_action,
}


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main callback dispatcher that routes button presses to appropriate handlers.
    
    This is a clean, modular replacement for the previous 875-line monolithic function.
    """
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split("__")
    action_type = parts[0]
    
    logger.info(f"User {user_id}: Button callback received - action: {action_type}, data: {query.data}")
    
    # Restore game state if needed
    if user_id not in GAME_STATE:
        await query.answer("🔄 Restoring your game...")
        
        saved_state_data = await game_state_manager.load_game_state(user_id)
        
        if saved_state_data and saved_state_data.get("state"):
            saved_state = saved_state_data["state"]
            # Ensure required fields exist
            if "game_completed" not in saved_state:
                saved_state["game_completed"] = False

            GAME_STATE[user_id] = saved_state
            
            logger.info(f"User {user_id}: Automatically restored game state from saved data in button callback")
            
            # Check if post-test message should be scheduled for restored game

        else:
            await query.edit_message_text(text="This button has expired. Please start over with /start.")
            return

    state = GAME_STATE[user_id]
    
    # Check if game is already completed (but allow final report and reveal)
    if state.get("game_completed") and action_type not in ["final", "reveal", "reveal_custom"]:
        await query.edit_message_text("🎭 Your game has already ended. Use /start to begin a new adventure!")
        return
    
    # Route to appropriate handler
    handler = ACTION_HANDLERS.get(action_type)
    if handler:
        try:
            result = await handler(update, context, user_id, parts)
            # Some handlers return True to indicate special handling (like restarts)
            if result is True:
                return
        except Exception as e:
            logger.error(f"Error in {action_type} handler for user {user_id}: {e}", exc_info=True)
            await query.edit_message_text("❌ An error occurred. Please try again or use /start to restart.")
    else:
        logger.warning(f"User {user_id}: Unknown action type '{action_type}'")
        await query.edit_message_text("❌ Unknown action. Please try again or use /start to restart.")
