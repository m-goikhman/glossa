"""
Handlers package for the Telegram bot.

This package contains modular handlers for different aspects of the bot functionality:
- commands: Command handlers (/start, /restart, etc.)
- callbacks: Button callback handlers
- conversations: Character conversation and game logic
- reports: Progress and final reports  
- tutoring: AI/Tutor related functionality
- game_utils: Game state and utility functions
"""

from .commands import start_command_handler, restart_command_handler, update_keyboard_handler, show_main_menu_handler, show_language_learning_menu_handler
from .callbacks import button_callback_handler
from .conversations import handle_private_character_conversation, handle_accusation_direct, execute_scene_action, process_director_decision
from .reports import progress_report_handler, generate_final_english_report
from .tutoring import analyze_and_log_text, send_tutor_explanation
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

# Main message handler
from .main_handler import handle_message

__all__ = [
    # Commands
    'start_command_handler',
    'restart_command_handler', 
    'update_keyboard_handler',
    'show_main_menu_handler',
    'show_language_learning_menu_handler',
    
    # Callbacks
    'button_callback_handler',
    
    # Conversations
    'handle_private_character_conversation',
    'handle_accusation_direct',
    'execute_scene_action', 
    'process_director_decision',
    
    # Reports
    'progress_report_handler',
    'generate_final_english_report',
    
    # Tutoring
    'analyze_and_log_text',
    'send_tutor_explanation',
    
    # Game Utils
    'get_participant_code',
    'cancel_post_test_task',
    'save_user_game_state',
    'check_and_unlock_accuse',
    'is_player_ready_to_accuse',
    'get_random_common_space_phrase',
    'check_and_schedule_post_test_message',
    'schedule_post_test_message',
    
    # Main handler
    'handle_message'
]
