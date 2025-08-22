"""
Callback handlers for the Telegram bot.

This module contains the main button callback handler that processes all inline button presses.
Note: This is a very large function that could be refactored further into smaller handlers.
"""

import asyncio
import logging
import os
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from config import GAME_STATE, CHARACTER_DATA, SUSPECT_KEYS, message_cache, POST_TEST_TASKS
from ai_services import ask_for_dialogue, ask_word_spotter
from utils import load_system_prompt, log_message, create_explain_button, combine_character_prompt
from game_state_manager import game_state_manager
from progress_manager import progress_manager

# Import functions from other handlers
from .game_utils import (
    get_participant_code, 
    cancel_post_test_task, 
    save_user_game_state, 
    check_and_unlock_accuse, 
    is_player_ready_to_accuse, 
    get_random_common_space_phrase,
    check_and_schedule_post_test_message,
    schedule_post_test_message
)
from .commands import show_main_menu_handler, show_language_learning_menu_handler, restart_command_handler
from .reports import progress_report_handler, generate_final_english_report
from .tutoring import send_tutor_explanation

logger = logging.getLogger(__name__)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button presses."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split("__")
    action_type = parts[0]
    
    logger.info(f"User {user_id}: Button callback received - action: {action_type}, data: {query.data}")
    
    if user_id not in GAME_STATE:
        # Show immediate response to prevent user from leaving
        await query.answer("🔄 Restoring your game...")
        
        # Check if user has saved game state and restore it automatically
        saved_state_data = await game_state_manager.load_game_state(user_id)
        
        if saved_state_data and saved_state_data.get("state"):
            # User has an existing game - restore it silently and continue
            saved_state = saved_state_data["state"]
            # Ensure game_completed flag is set if it doesn't exist
            if "game_completed" not in saved_state:
                saved_state["game_completed"] = False
            # Ensure message_count field exists for backwards compatibility
            if "message_count" not in saved_state:
                saved_state["message_count"] = 0
            GAME_STATE[user_id] = saved_state
            
            logger.info(f"User {user_id}: Automatically restored game state from saved data in button callback")
            
            # Check if post-test message should be scheduled for restored game
            asyncio.create_task(check_and_schedule_post_test_message(user_id, context))
            
            # Continue processing the button press with restored state
        else:
            await query.edit_message_text(text="This button has expired. Please start over with /start.")
            return

    state = GAME_STATE[user_id]
    
    # Check if game is already completed (but allow final report and reveal)
    if state.get("game_completed") and action_type not in ["final", "reveal"]:
        await query.edit_message_text("🎭 Your game has already ended. Use /start to begin a new adventure!")
        return
    
    if action_type == "onboarding":
        sub_action = parts[1]
        await query.edit_message_reply_markup(reply_markup=None)

        if sub_action == "step2":
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
        
        # step3 removed - how to play will be shown after photo
        
        elif sub_action == "step4":
            # Check if participant code was entered
            if not GAME_STATE[user_id].get("participant_code"):
                await query.answer("❌ Please enter your participant code first!")
                return
            
            # Show language level selection
            intro_b1_text = load_system_prompt("game_texts/intro-B1.txt")
            
            # Send intro-B1 with language level buttons (language level text already shown in previous step)
            sent_message = await context.bot.send_message(
                chat_id=user_id, 
                text=intro_b1_text,
                parse_mode='Markdown'
            )
            
            # Add language level selection buttons
            # For B1 level (default), show all three options
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
            
            # Log the language selection step
            logger.info(f"User {user_id}: Reached language selection step, showing intro-B1 with level buttons")
        

    elif action_type == "language":
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

    elif action_type == "language_menu":
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

    elif action_type == "difficulty":
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

    elif action_type == "explain":
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

    elif action_type == "menu":
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

    elif action_type == "guide":
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

    elif action_type == "clue":
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

    elif action_type == "talk":
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

    elif action_type == "mode":
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
    
    elif action_type == "reveal":
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
    
    elif action_type == "reveal_custom":
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
    
    elif action_type == "restart":
        sub_action = parts[1]
        if sub_action == "game":
            # Restart the game
            await restart_command_handler(update, context)
            return True
    
    elif action_type == "final":
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
    
    elif action_type == "accuse":
        # Import here to avoid circular imports
        from .conversations import handle_accusation_direct
        
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

    elif action_type == "case_intro":
        logger.info(f"User {user_id}: case_intro action triggered with sub_action: {parts[1]}")
        sub_action = parts[1]
        
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
            
            # Record game start time
            GAME_STATE[user_id]["game_start_time"] = time.time()
            logger.info(f"User {user_id}: Game start time recorded")
            
            # Save state with game start time
            await save_user_game_state(user_id)
            
            # Schedule post-test message after 20 minutes
            post_test_delay = 1200  # 20 minutes in seconds
            
            # Cancel any existing post-test task for this user
            cancel_post_test_task(user_id)
            
            # Create and track new post-test task
            task = asyncio.create_task(schedule_post_test_message(user_id, context, post_test_delay))
            POST_TEST_TASKS[user_id] = task
            logger.info(f"User {user_id}: Post-test message scheduled for {post_test_delay} seconds later")
            
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
