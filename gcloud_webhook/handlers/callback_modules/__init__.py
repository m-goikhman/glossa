"""
Callback handlers subpackage for the Telegram bot.

This package contains modular callback handlers organized by functionality:
- onboarding_callbacks: Setup and language selection
- menu_callbacks: Navigation and settings
- game_callbacks: Core game interactions
- explanation_callbacks: Word explanations
- ending_callbacks: Game conclusion sequences
"""

from .onboarding_callbacks import handle_onboarding_action, handle_language_action, handle_case_intro_action
from .menu_callbacks import handle_language_menu_action, handle_difficulty_action, handle_menu_action
from .game_callbacks import handle_guide_action, handle_clue_action, handle_talk_action, handle_mode_action, handle_accuse_action
from .explanation_callbacks import handle_explain_action
from .ending_callbacks import handle_reveal_action, handle_reveal_custom_action, handle_restart_action, handle_final_action

__all__ = [
    # Onboarding handlers
    'handle_onboarding_action',
    'handle_language_action', 
    'handle_case_intro_action',
    
    # Menu handlers
    'handle_language_menu_action',
    'handle_difficulty_action',
    'handle_menu_action',
    
    # Game handlers
    'handle_guide_action',
    'handle_clue_action',
    'handle_talk_action',
    'handle_mode_action',
    'handle_accuse_action',
    
    # Explanation handlers
    'handle_explain_action',
    
    # Ending handlers
    'handle_reveal_action',
    'handle_reveal_custom_action',
    'handle_restart_action',
    'handle_final_action'
]
