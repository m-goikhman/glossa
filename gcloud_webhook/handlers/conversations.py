"""
Character conversation and game logic handlers for the Telegram bot.

This module contains functions for handling character conversations, 
accusations, scene actions, and director decisions.
"""

import asyncio
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import GAME_STATE, CHARACTER_DATA, message_cache
from ai_services import ask_for_dialogue, ask_director
from utils import load_system_prompt, log_message, create_explain_button, combine_character_prompt
from progress_manager import progress_manager

# Import utility functions
from .game_utils import get_participant_code, save_user_game_state

logger = logging.getLogger(__name__)


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
    topic_memory = state.get("topic_memory", {"topic": "None", "spoken": [], "predefined_used": []})
    context_trigger = f"The detective is asking you a question: '{user_text}'. Current topic: {topic_memory.get('topic', 'None')}. Respond as your character."
    
    logger.info(f"User {user_id}: Direct character conversation with '{char_key}'")
    
    try:
        reply_text = await ask_for_dialogue(user_id, context_trigger, system_prompt, char_key)
        
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
        
        # Create inline keyboard with find out more and final report buttons
        keyboard = [
            [InlineKeyboardButton("🕵️ Find out more", callback_data="reveal_custom__start")],
            [InlineKeyboardButton("📊 See Your Final English Report", callback_data="final__report")]
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
            reply_text = await ask_for_dialogue(user_id, trigger_msg, system_prompt, char_key)
            
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
    topic_memory = state.get("topic_memory", {"topic": "None", "spoken": [], "predefined_used": []})

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
        # Reset spoken list but preserve predefined_used when topic changes
        state["topic_memory"]["spoken"] = []
        # Ensure predefined_used field exists
        if "predefined_used" not in state["topic_memory"]:
            state["topic_memory"]["predefined_used"] = []
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
