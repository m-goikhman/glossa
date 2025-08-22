"""
Progress reporting handlers for the Telegram bot.

This module contains functions for generating and displaying user progress reports,
including language learning progress and final reports.
"""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from config import GAME_STATE, POST_TEST_TASKS
from ai_services import ask_tutor_for_final_summary
from utils import log_message, split_long_message
from game_state_manager import game_state_manager
from progress_manager import progress_manager

logger = logging.getLogger(__name__)


def get_participant_code(user_id: int) -> str:
    """Gets participant code from game state if available."""
    state = GAME_STATE.get(user_id, {})
    return state.get("participant_code")


async def check_and_schedule_post_test_message(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Check if post-test message should be scheduled for a restored game."""
    # Import here to avoid circular imports
    from .game_utils import schedule_post_test_message
    
    state = GAME_STATE.get(user_id, {})
    
    # Check if game is completed and post-test message should be sent
    if (state.get("game_completed") and 
        state.get("reveal_step", 0) >= 5 and 
        user_id not in POST_TEST_TASKS):
        
        # Schedule post-test message with a short delay
        await schedule_post_test_message(user_id, context, delay_seconds=5)
        logger.info(f"User {user_id}: Scheduled post-test message for restored completed game")


async def progress_report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, is_final_report: bool = False):
    """Sends the user a formatted report of their progress using HTML."""
    user_id = update.effective_user.id
    
    # Log the progress report request
    if is_final_report:
        log_message(user_id, "user_action", "Requested final progress report", get_participant_code(user_id))
    else:
        log_message(user_id, "user_action", "Clicked 'Language Progress' button in ✍️ Learning Menu", get_participant_code(user_id))
    
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
            # Ensure message_count field exists for backwards compatibility
            if "message_count" not in saved_state:
                saved_state["message_count"] = 0
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
    
    # Add back button to ✍️ Learning Menu if this is not a final report
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
