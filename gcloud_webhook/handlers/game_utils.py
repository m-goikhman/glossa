"""
Game utility functions for the Telegram bot.

This module contains utility functions for game state management,
post-test scheduling, and other game-related helper functions.
"""

import asyncio
import logging
import time
from typing import Tuple
from telegram.ext import ContextTypes

from config import GAME_STATE, TOTAL_CLUES, SUSPECT_KEYS, POST_TEST_TASKS
from utils import load_system_prompt, log_message
from game_state_manager import game_state_manager

logger = logging.getLogger(__name__)


def get_participant_code(user_id: int) -> str:
    """Gets participant code from game state if available."""
    state = GAME_STATE.get(user_id, {})
    return state.get("participant_code")


def cancel_post_test_task(user_id: int):
    """Cancels any existing post-test task for the user."""
    if user_id in POST_TEST_TASKS:
        task = POST_TEST_TASKS[user_id]
        if not task.done():
            task.cancel()
            logger.info(f"User {user_id}: Cancelled existing post-test task")
        del POST_TEST_TASKS[user_id]


def get_random_common_space_phrase():
    """Returns a random phrase from the common_space.txt file."""
    try:
        phrases = load_system_prompt("game_texts/common_space.txt").strip().split('\n')
        # Filter out empty lines
        phrases = [phrase.strip() for phrase in phrases if phrase.strip()]
        if phrases:
            import random
            return random.choice(phrases)
        else:
            return "You are in the main room. Everyone is present."
    except Exception as e:
        logger.error(f"Failed to load common space phrases: {e}")
        return "You are in the main room. Everyone is present."


async def save_user_game_state(user_id: int):
    """Save the current game state for a user to persistent storage."""
    if user_id in GAME_STATE:
        await game_state_manager.save_game_state(user_id, GAME_STATE[user_id])


async def check_and_unlock_accuse(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Silently checks if conditions are met to unlock the accusation button."""
    state = GAME_STATE.get(user_id, {})
    # Do nothing if already unlocked
    if not state or state.get("accuse_unlocked"):
        return

    all_clues_examined = len(state.get("clues_examined", set())) == TOTAL_CLUES
    all_suspects_interrogated = len(state.get("suspects_interrogated", set())) >= len(SUSPECT_KEYS)

    if all_clues_examined and all_suspects_interrogated:
        state["accuse_unlocked"] = True
        # Save state when accusation is unlocked
        await save_user_game_state(user_id)


def is_player_ready_to_accuse(user_id: int) -> Tuple[bool, str]:
    """
    Checks if player is ready to make an accusation.
    Returns: (is_ready, message_describing_what_is_missing)
    """
    state = GAME_STATE.get(user_id, {})
    if not state:
        return False, "Game state not found"
    
    clues_examined = len(state.get("clues_examined", set()))
    suspects_interrogated = len(state.get("suspects_interrogated", set()))
    
    all_clues_examined = clues_examined == TOTAL_CLUES
    all_suspects_interrogated = suspects_interrogated >= len(SUSPECT_KEYS)
    
    if all_clues_examined and all_suspects_interrogated:
        return True, ""
    
    missing_parts = []
    if not all_clues_examined:
        missing_clues = TOTAL_CLUES - clues_examined
        missing_parts.append(f"{missing_clues} more clue{'s' if missing_clues > 1 else ''}")
    
    if not all_suspects_interrogated:
        missing_suspects = len(SUSPECT_KEYS) - suspects_interrogated
        missing_parts.append(f"{missing_suspects} more suspect{'s' if missing_suspects > 1 else ''}")
    
    missing_text = " and ".join(missing_parts)
    return False, f"You still need to examine {missing_text} before making an accusation."


async def check_and_schedule_post_test_message(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Check if post-test message should be scheduled for restored game state."""
    if user_id not in GAME_STATE:
        return
        
    state = GAME_STATE[user_id]
    game_start_time = state.get("game_start_time")
    
    if not game_start_time or state.get("game_completed", False):
        return
    
    # Calculate how much time has passed since game start
    current_time = time.time()
    elapsed_time = current_time - game_start_time
    
    post_test_delay = 1200
    
    # Cancel any existing post-test task for this user
    cancel_post_test_task(user_id)
    
    if elapsed_time >= post_test_delay:
        # Post-test should have been sent already, send immediately
        logger.info(f"User {user_id}: Post-test message overdue, sending immediately")
        task = asyncio.create_task(schedule_post_test_message(user_id, context, 0))
        POST_TEST_TASKS[user_id] = task
    else:
        # Calculate remaining time until post-test should be sent
        remaining_time = post_test_delay - elapsed_time
        logger.info(f"User {user_id}: Post-test message scheduled for {remaining_time:.0f} seconds from now")
        task = asyncio.create_task(schedule_post_test_message(user_id, context, remaining_time))
        POST_TEST_TASKS[user_id] = task


async def schedule_post_test_message(user_id: int, context: ContextTypes.DEFAULT_TYPE, delay_seconds: float = 1200):
    """Schedules the post-test message to be sent after the specified delay, but only if 5+ messages have been sent."""
    try:
        # Wait for the specified delay
        await asyncio.sleep(delay_seconds)
        
        # Check if user still has active game state
        if user_id not in GAME_STATE:
            logger.info(f"User {user_id}: Post-test message cancelled - no active game state")
            return
            
        # Check if game was completed (if so, don't send post-test)
        if GAME_STATE[user_id].get("game_completed", False):
            logger.info(f"User {user_id}: Post-test message cancelled - game already completed")
            return
            
        # Additional validation: check if game_start_time exists and is valid
        game_start_time = GAME_STATE[user_id].get("game_start_time")
        if not game_start_time:
            logger.info(f"User {user_id}: Post-test message cancelled - no valid game start time")
            return
        
        # Check message count requirement
        message_count = GAME_STATE[user_id].get("message_count", 0)
        if message_count < 5:
            logger.info(f"User {user_id}: Post-test message delayed - only {message_count} messages sent, waiting for 5th message")
            # Don't send post-test yet, wait for 5th message (handled in handle_message)
            return
        
        # Load post-test message
        try:
            post_test_text = load_system_prompt("game_texts/post-test.txt")
        except Exception as e:
            logger.error(f"User {user_id}: Failed to load post-test.txt: {e}")
            post_test_text = "📋 Second questionnaire is now available.\n\nComplete it now or continue playing and fill it out later. Thank you!\n\nLink: https://forms.gle/zd6dsxFDgGHp5TxK9\n\n(This message stays pinned so you won't lose the link)"
        
        # Send the message
        message = await context.bot.send_message(
            chat_id=user_id,
            text=post_test_text,
            parse_mode='Markdown'
        )
        
        # Pin the message
        try:
            await context.bot.pin_chat_message(
                chat_id=user_id,
                message_id=message.message_id
            )
            logger.info(f"User {user_id}: Post-test message sent and pinned successfully")
        except Exception as e:
            logger.error(f"User {user_id}: Failed to pin post-test message: {e}")
            logger.info(f"User {user_id}: Post-test message sent but not pinned")
            
        # Log the message send
        log_message(user_id, "system", "Post-test questionnaire message sent", get_participant_code(user_id))
        
    except asyncio.CancelledError:
        logger.info(f"User {user_id}: Post-test message task was cancelled")
    except Exception as e:
        logger.error(f"User {user_id}: Error in post-test message scheduling: {e}")
    finally:
        # Clean up the task from tracking dictionary
        POST_TEST_TASKS.pop(user_id, None)
