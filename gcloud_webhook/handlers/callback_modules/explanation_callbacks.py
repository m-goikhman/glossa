"""
Word explanation callback handlers for the Telegram bot.

This module handles all word and phrase explanation actions including:
- Explanation initialization and word spotting
- Individual word explanations
- Full sentence explanations
- Custom word/phrase explanation requests
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import GAME_STATE, message_cache
from ai_services import ask_word_spotter
from utils import log_message
from ..game_utils import get_participant_code
from ..tutoring import send_tutor_explanation

logger = logging.getLogger(__name__)


async def handle_explain_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle word and phrase explanation actions."""
    query = update.callback_query
    state = GAME_STATE[user_id]
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
