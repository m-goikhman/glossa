"""
Menu navigation callback handlers for the Telegram bot.

This module handles all menu-related navigation actions including:
- Language learning menu navigation
- Difficulty settings and adjustments
- Main game menu navigation
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import GAME_STATE, CHARACTER_DATA, SUSPECT_KEYS
from utils import log_message
from ..game_utils import get_participant_code, save_user_game_state
from ..commands import show_main_menu_handler, show_language_learning_menu_handler
from ..reports import progress_report_handler

logger = logging.getLogger(__name__)


async def handle_language_menu_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle language learning menu navigation actions."""
    query = update.callback_query
    state = GAME_STATE[user_id]
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
        # Return to ✍️ Learning Menu
        await show_language_learning_menu_handler(update, context)


async def handle_difficulty_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle difficulty setting changes."""
    query = update.callback_query
    state = GAME_STATE[user_id]
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
        
        # Show confirmation and return to ✍️ Learning Menu
        await query.edit_message_text(
            f"✅ **Difficulty Updated!**\n\nYour text difficulty has been changed from **{old_level}** to **{new_level}**.\n\nThis setting will apply to all new conversations and character interactions. You can change it anytime from the ✍️ Learning Menu.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Back to Language Menu", callback_data="language_menu__back")
            ]]),
            parse_mode='Markdown'
        )


async def handle_menu_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle main game menu navigation actions."""
    query = update.callback_query
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
