"""
Game ending callback handlers for the Telegram bot.

This module handles all game conclusion actions including:
- Full case revelation sequence
- Custom reveal sequence for successful players
- Game restart functionality
- Final report generation and cleanup
"""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import GAME_STATE
from utils import load_system_prompt
from game_state_manager import game_state_manager
from progress_manager import progress_manager
from ..game_utils import save_user_game_state
from ..commands import restart_command_handler
from ..reports import generate_final_english_report

logger = logging.getLogger(__name__)


async def handle_reveal_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle full case revelation sequence actions."""
    query = update.callback_query
    state = GAME_STATE[user_id]
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


async def handle_reveal_custom_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle custom reveal sequence for successful players."""
    query = update.callback_query
    state = GAME_STATE[user_id]
    sub_action = parts[1]
    
    # Define custom reveal steps with only reveal_1_truth.txt and reveal_5_motive.txt
    custom_reveal_steps = [
        {"file": "game_texts/reveal_1_truth.txt", "next": True},
        {"file": "game_texts/reveal_5_motive.txt", "next": False}  # Final step
    ]
    
    if sub_action == "start":
        # Show first reveal message (reveal_1_truth.txt)
        state["custom_reveal_step"] = 0
        
    elif sub_action == "next":
        # Move to next reveal message (reveal_5_motive.txt)
        current_step = state.get("custom_reveal_step", 0) + 1
        state["custom_reveal_step"] = current_step
    else:
        # Invalid sub_action, default to first step
        state["custom_reveal_step"] = 0
    
    # Get current step
    current_step = state.get("custom_reveal_step", 0)
    
    if current_step < len(custom_reveal_steps):
        step_data = custom_reveal_steps[current_step]
        try:
            text = load_system_prompt(step_data["file"])
            
            if step_data["next"]:
                # Show next button (for reveal_1_truth.txt)
                await query.edit_message_text(text, parse_mode='Markdown')
                await asyncio.sleep(2)  # Pause before next message
                
                # Automatically show next message
                next_step = current_step + 1
                state["custom_reveal_step"] = next_step
                if next_step < len(custom_reveal_steps):
                    next_step_data = custom_reveal_steps[next_step]
                    next_text = load_system_prompt(next_step_data["file"])
                    
                    # Final message - show English report button after reveal_5_motive
                    keyboard = [[InlineKeyboardButton("📊 See Your Final English Report", callback_data="final__report")]]
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=next_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
            else:
                # This shouldn't be reached with current logic, but safety fallback
                keyboard = [[InlineKeyboardButton("📊 See Your Final English Report", callback_data="final__report")]]
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Failed to load custom reveal file {step_data['file']}: {e}")
            await query.edit_message_text("🎭 The case is now closed. Thank you for playing!", parse_mode='Markdown')
    else:
        # All messages shown - shouldn't happen with new logic, but safety fallback
        keyboard = [[InlineKeyboardButton("📊 See Your Final English Report", callback_data="final__report")]]
        await query.edit_message_text(
            "🎭 The case is now closed. Thank you for playing!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    await save_user_game_state(user_id)


async def handle_restart_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle game restart actions."""
    sub_action = parts[1]
    
    if sub_action == "game":
        # Restart the game
        await restart_command_handler(update, context)
        return True


async def handle_final_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle final game actions and cleanup."""
    query = update.callback_query
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
