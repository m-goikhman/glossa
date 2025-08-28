"""
Game utility functions for the Telegram bot.

This module contains utility functions for game state management
and other game-related helper functions.
"""

import logging
from typing import Tuple
from telegram.ext import ContextTypes

from config import GAME_STATE, TOTAL_CLUES, SUSPECT_KEYS
from utils import load_system_prompt, log_message
from game_state_manager import game_state_manager

logger = logging.getLogger(__name__)


def get_participant_code(user_id: int) -> str:
    """Gets participant code from game state if available."""
    state = GAME_STATE.get(user_id, {})
    return state.get("participant_code")



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



