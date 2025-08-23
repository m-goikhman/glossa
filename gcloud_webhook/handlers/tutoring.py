"""
Tutoring and AI-related handlers for the Telegram bot.

This module contains functions related to language learning assistance,
text analysis, and tutoring functionality.
"""

import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes

from config import CHARACTER_DATA, GAME_STATE
from ai_services import ask_tutor_for_analysis, ask_tutor_for_explanation
from utils import log_message, split_long_message
from progress_manager import progress_manager

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
        progress_manager.add_writing_feedback(user_id, text_to_analyze, feedback, get_participant_code(user_id))


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
    progress_manager.add_word_learned(user_id, text_to_explain, definition, get_participant_code(user_id))
