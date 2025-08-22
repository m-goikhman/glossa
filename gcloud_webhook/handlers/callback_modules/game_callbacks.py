"""
Core game action callback handlers for the Telegram bot.

This module handles all main game interaction actions including:
- Detective guide display
- Clue examination and evidence gathering
- Character conversation initiation
- Game mode switching (private/public)
- Accusation system
"""

import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import GAME_STATE, CHARACTER_DATA, SUSPECT_KEYS, message_cache
from ai_services import ask_for_dialogue
from utils import load_system_prompt, log_message, create_explain_button, combine_character_prompt
from ..game_utils import (
    get_participant_code, 
    save_user_game_state, 
    check_and_unlock_accuse, 
    is_player_ready_to_accuse, 
    get_random_common_space_phrase
)

logger = logging.getLogger(__name__)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def handle_guide_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle detective guide display actions."""
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


async def handle_clue_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle clue examination actions."""
    state = GAME_STATE[user_id]
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


async def handle_talk_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle character conversation initiation actions."""
    query = update.callback_query
    state = GAME_STATE[user_id]
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


async def handle_mode_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle game mode switching actions."""
    query = update.callback_query
    state = GAME_STATE[user_id]
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


async def handle_accuse_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle accusation system actions."""
    # Import here to avoid circular imports
    from ..conversations import handle_accusation_direct
    
    query = update.callback_query
    state = GAME_STATE[user_id]
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
        
        await query.edit_message_text(f"🎙️ All eyes turn to them {char_name}, the person you've just accused of attacking Alex. {attempts_text}_", parse_mode='Markdown')
        
        # Process accusation immediately without asking for explanation
        await handle_accusation_direct(update, context, user_id, accused_key)
