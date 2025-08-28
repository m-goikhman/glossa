"""
Onboarding callback handlers for the Telegram bot.

This module handles all onboarding-related actions including:
- Initial setup and participant code entry
- Language level selection and adjustment  
- Case introduction sequence
"""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from config import GAME_STATE
from utils import load_system_prompt
from ..game_utils import save_user_game_state

logger = logging.getLogger(__name__)


async def handle_onboarding_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle onboarding-related callback actions."""
    query = update.callback_query
    sub_action = parts[1]
    await query.edit_message_reply_markup(reply_markup=None)

    if sub_action == "step2":
        # Show links and questionnaire information
        links_text = load_system_prompt("game_texts/onboarding_2_links.txt")
        keyboard = [[InlineKeyboardButton("📝 First questionnaire done, let's go!", callback_data="onboarding__step4")]]
        
        sent_message = await context.bot.send_message(
            chat_id=user_id, 
            text=links_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Pin the message with links
        try:
            await context.bot.pin_chat_message(
                chat_id=user_id,
                message_id=sent_message.message_id,
                disable_notification=True
            )
            logger.info(f"User {user_id}: Links message pinned successfully")
        except Exception as e:
            logger.warning(f"User {user_id}: Could not pin links message: {e}")
        
        GAME_STATE[user_id]["onboarding_step"] = "links_shown"
    
    elif sub_action == "step4":
        # Request participant code
        code_text = load_system_prompt("game_texts/onboarding_2_code.txt")
        await context.bot.send_message(
            chat_id=user_id, 
            text=code_text,
            parse_mode='Markdown'
        )
        # Set state to wait for participant code
        GAME_STATE[user_id]["waiting_for_participant_code"] = True
        GAME_STATE[user_id]["onboarding_step"] = "waiting_for_code"
    
    elif sub_action == "step5":
        # Check if participant code was entered
        if not GAME_STATE[user_id].get("participant_code"):
            await query.answer("❌ Please enter your participant code first!")
            return
        
        # Show language level selection
        intro_b1_text = load_system_prompt("game_texts/intro-B1.txt")
        
        # Send intro-B1 with language level buttons
        sent_message = await context.bot.send_message(
            chat_id=user_id, 
            text=intro_b1_text,
            parse_mode='Markdown'
        )
        
        # Add language level selection buttons
        keyboard = [
            [InlineKeyboardButton("Easier", callback_data="language__easier")],
            [InlineKeyboardButton("Perfect!", callback_data="language__perfect")],
            [InlineKeyboardButton("More Advanced", callback_data="language__more_advanced")]
        ]
        
        await context.bot.edit_message_reply_markup(
            chat_id=sent_message.chat_id, 
            message_id=sent_message.message_id, 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Store current intro message ID for language level changes
        GAME_STATE[user_id]["current_intro_message_id"] = sent_message.message_id
        GAME_STATE[user_id]["current_language_level"] = "B1"
        GAME_STATE[user_id]["onboarding_step"] = "language_selection"
        
        logger.info(f"User {user_id}: Reached language selection step, showing intro-B1 with level buttons")


async def handle_language_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle language level selection and adjustment actions."""
    query = update.callback_query
    state = GAME_STATE[user_id]
    sub_action = parts[1]
    
    # Handle "perfect" first, as it's a terminal action in this flow
    if sub_action == "perfect":
        logger.info(f"User {user_id}: Language 'perfect' button clicked")
        # User is satisfied with current level, show confirmation and atmospheric start
        current_level = GAME_STATE[user_id].get("current_language_level", "B1")
        logger.info(f"User {user_id}: Current language level is {current_level}")
        
        current_message_id = GAME_STATE[user_id].get("current_intro_message_id")
        if current_message_id:
            # Just remove buttons from the intro message, don't change text
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=user_id,
                    message_id=current_message_id,
                    reply_markup=None
                )
                logger.info(f"User {user_id}: Removed buttons from intro message")
            except Exception as e:
                logger.warning(f"User {user_id}: Could not remove buttons from intro message: {e}")
        
        # Show level confirmation
        try:
            confirmation_text = load_system_prompt("game_texts/level_confirmed.txt").replace("[LEVEL]", current_level)
            logger.info(f"User {user_id}: Loaded confirmation text: {confirmation_text}")
            await context.bot.send_message(
                chat_id=user_id,
                text=confirmation_text,
                parse_mode='Markdown'
            )
            logger.info(f"User {user_id}: Level confirmation sent successfully")
        except Exception as e:
            logger.error(f"User {user_id}: Error sending level confirmation: {e}")
        
        # Send atmospheric photo with text and "Start Investigation" button
        try:
            atmospheric_text = load_system_prompt("game_texts/atmospheric_start.txt")
            logger.info(f"User {user_id}: Loaded atmospheric text: {atmospheric_text}")
            keyboard = [[InlineKeyboardButton("🕵️ Start Investigation!", callback_data="case_intro__begin")]]
            
            photo_path = "images/aric-cheng-7Bv9MrBan9s-unsplash.jpg"
            logger.info(f"User {user_id}: Attempting to send photo from {photo_path}")
            
            with open(photo_path, "rb") as photo:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption=atmospheric_text,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            logger.info(f"User {user_id}: Atmospheric photo sent successfully")
        except FileNotFoundError:
            logger.error(f"User {user_id}: Photo file not found at {photo_path}")
            # Fallback: send just the text without photo
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🌃 {atmospheric_text}",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                logger.info(f"User {user_id}: Atmospheric text sent successfully (no photo)")
            except Exception as fallback_e:
                logger.error(f"User {user_id}: Error sending fallback atmospheric message: {fallback_e}")
        except Exception as e:
            logger.error(f"User {user_id}: Error sending atmospheric photo: {e}")
            # Fallback: send just the text without photo
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🌃 {atmospheric_text}",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                logger.info(f"User {user_id}: Atmospheric text sent successfully (fallback)")
            except Exception as fallback_e:
                logger.error(f"User {user_id}: Error sending fallback atmospheric message: {fallback_e}")
        
        # Log the language level confirmation
        logger.info(f"User {user_id}: Confirmed language level {current_level}, showing atmospheric start with start button")
        return

    # Handle level changes ("easier" or "more_advanced")
    current_level = state.get("current_language_level", "B1")
    new_level = current_level

    if sub_action == "easier":
        if current_level == "B2":
            new_level = "B1"
        elif current_level == "B1":
            new_level = "A2"
    elif sub_action == "more_advanced":
        if current_level == "A2":
            new_level = "B1"
        elif current_level == "B1":
            new_level = "B2"

    if new_level != current_level:
        current_message_id = GAME_STATE[user_id].get("current_intro_message_id")
        if not current_message_id:
            logger.error(f"User {user_id}: No current intro message ID found for language change")
            return

        # Show loading animation
        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=current_message_id,
            text="🔄 Adjusting text difficulty...",
            parse_mode='Markdown'
        )
        await asyncio.sleep(1.5)

        # Determine text and keyboard for the new level
        if new_level == "A2":
            intro_text = load_system_prompt("game_texts/intro-A2.txt")
            keyboard_layout = [
                [InlineKeyboardButton("Perfect!", callback_data="language__perfect")],
                [InlineKeyboardButton("More Advanced", callback_data="language__more_advanced")]
            ]
        elif new_level == "B2":
            intro_text = load_system_prompt("game_texts/intro-B2.txt")
            keyboard_layout = [
                [InlineKeyboardButton("Easier", callback_data="language__easier")],
                [InlineKeyboardButton("Perfect!", callback_data="language__perfect")]
            ]
        else:  # B1
            intro_text = load_system_prompt("game_texts/intro-B1.txt")
            keyboard_layout = [
                [InlineKeyboardButton("Easier", callback_data="language__easier")],
                [InlineKeyboardButton("Perfect!", callback_data="language__perfect")],
                [InlineKeyboardButton("More Advanced", callback_data="language__more_advanced")]
            ]

        # Update message text and keyboard
        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=current_message_id,
            text=intro_text,
            parse_mode='Markdown'
        )
        await context.bot.edit_message_reply_markup(
            chat_id=user_id,
            message_id=current_message_id,
            reply_markup=InlineKeyboardMarkup(keyboard_layout)
        )

        # Update state and log the change
        GAME_STATE[user_id]["current_language_level"] = new_level
        logger.info(f"User {user_id}: Changed language level from {current_level} to {new_level}")


async def handle_case_intro_action(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, parts: list):
    """Handle case introduction sequence actions."""
    query = update.callback_query
    sub_action = parts[1]
    
    logger.info(f"User {user_id}: case_intro action triggered with sub_action: {sub_action}")
    
    if sub_action == "situation":
        # Show the situation details as a new message
        try:
            situation_text = load_system_prompt("game_texts/case_intro_2_situation.txt")
            logger.info(f"User {user_id}: Successfully loaded situation_text: {situation_text[:100]}...")
        except Exception as e:
            logger.error(f"User {user_id}: Failed to load case_intro_2_situation.txt: {e}")
            # Fallback to default text
            situation_text = "📍 THE SITUATION\n\nAlex was found unconscious in his bathroom after a Christmas party."
        
        # Send new message with situation text and next button
        sent_message = await context.bot.send_message(
            chat_id=user_id,
            text=situation_text,
            parse_mode='Markdown'
        )
        
        # Add next button
        keyboard = [
            [InlineKeyboardButton("Who was there?", callback_data="case_intro__suspects")]
        ]
        
        await context.bot.edit_message_reply_markup(
            chat_id=sent_message.chat_id,
            message_id=sent_message.message_id,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Remove button from previous message
        await query.edit_message_reply_markup(reply_markup=None)
        
    elif sub_action == "suspects":
        # Show the suspects information as a new message
        try:
            suspects_text = load_system_prompt("game_texts/case_intro_3_suspects.txt")
            logger.info(f"User {user_id}: Successfully loaded suspects_text: {suspects_text[:100]}...")
        except Exception as e:
            logger.error(f"User {user_id}: Failed to load case_intro_3_suspects.txt: {e}")
            # Fallback to default text
            suspects_text = "👥 FOUR PEOPLE ARE IN THE APARTMENT\n\nNobody can leave until you complete your investigation."
        
        # Send photo with suspects text as caption
        try:
            photo_path = "images/suspects.png"
            logger.info(f"User {user_id}: Attempting to send photo from {photo_path}")
            
            with open(photo_path, "rb") as photo:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption=suspects_text,
                    parse_mode='Markdown'
                )
            logger.info(f"User {user_id}: Suspects photo sent successfully")
        
        except FileNotFoundError:
            logger.error(f"User {user_id}: Photo file not found at {photo_path}")
            # Fallback: send just the text without photo
            await context.bot.send_message(
                chat_id=user_id,
                text=suspects_text,
                parse_mode='Markdown'
            )
        
        except Exception as e:
            logger.error(f"User {user_id}: Error sending suspects photo: {e}")
            # Fallback: send just the text without photo
            await context.bot.send_message(
                chat_id=user_id,
                text=suspects_text,
                parse_mode='Markdown'
            )
        
        # Remove button from previous message
        await query.edit_message_reply_markup(reply_markup=None)
        
        # Add "How to play?" button
        keyboard = [[InlineKeyboardButton("🎮 How to play?", callback_data="case_intro__how_to_play")]]
        await context.bot.send_message(
            chat_id=user_id,
            text="🧩 Ready to start the game?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif sub_action == "how_to_play":
        # Remove the "How to play?" button
        await query.edit_message_reply_markup(reply_markup=None)

        # Show how to play instructions
        how_to_play_text = load_system_prompt("game_texts/onboarding_3_howtoplay.txt")
        await context.bot.send_message(
            chat_id=user_id,
            text=how_to_play_text,
            parse_mode='Markdown'
        )
        
        # Add persistent keyboard for game menu and language learning
        persistent_keyboard = [
            [KeyboardButton("🔍 Game Menu"), KeyboardButton("✍️ Learning Menu")]
        ]
        reply_markup = ReplyKeyboardMarkup(persistent_keyboard, resize_keyboard=True)
        
        await context.bot.send_message(
            chat_id=user_id,
            text="Game menu and language learning options are now available on the panel below 👇",
            reply_markup=reply_markup
        )

    elif sub_action == "begin":
        # Show the first case introduction (this is called from the Start Investigation button)
        logger.info(f"User {user_id}: Starting case introduction sequence")
        
        # Save game state
        await save_user_game_state(user_id)
        
        try:
            case_intro_1_text = load_system_prompt("game_texts/case_intro_1_call.txt")
            logger.info(f"User {user_id}: Successfully loaded case_intro_1_text: {case_intro_1_text[:100]}...")
        except Exception as e:
            logger.error(f"User {user_id}: Failed to load case_intro_1_call.txt: {e}")
            # Fallback to default text
            case_intro_1_text = "📞 THE EMERGENCY CALL\n\nFiona called 911 a panic about Alex being unconscious."
        
        # Send the first case introduction with button
        sent_message = await context.bot.send_message(
            chat_id=user_id,
            text=case_intro_1_text,
            parse_mode='Markdown'
        )
        
        # Add first navigation button - sequential flow
        keyboard = [
            [InlineKeyboardButton("What happened?", callback_data="case_intro__situation")]
        ]
        
        await context.bot.edit_message_reply_markup(
            chat_id=sent_message.chat_id,
            message_id=sent_message.message_id,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
