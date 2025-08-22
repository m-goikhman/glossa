"""
Bot handlers for the Telegram bot (Compatibility layer).

This file serves as a compatibility layer for any remaining imports from bot_handlers.
All functionality has been refactored into the handlers/ package for better organization.

This file imports all handlers from the new modular structure to maintain
backward compatibility.
"""

# Import all handlers from the new modular structure
from handlers import (
    # Command handlers
    start_command_handler,
    restart_command_handler,
    update_keyboard_handler,
    show_main_menu_handler,
    show_language_learning_menu_handler,
    
    # Callback handlers
    button_callback_handler,
    
    # Conversation handlers
    handle_private_character_conversation,
    handle_accusation_direct,
    execute_scene_action,
    process_director_decision,
    
    # Progress and reporting
    progress_report_handler,
    generate_final_english_report,
    
    # Tutoring and AI services
    analyze_and_log_text,
    send_tutor_explanation,
    
    # Game utilities
    get_participant_code,
    cancel_post_test_task,
    save_user_game_state,
    check_and_unlock_accuse,
    is_player_ready_to_accuse,
    get_random_common_space_phrase,
    check_and_schedule_post_test_message,
    schedule_post_test_message,
    
    # Main message handler
    handle_message
)

# Backward compatibility exports
__all__ = [
    'start_command_handler',
    'restart_command_handler', 
    'update_keyboard_handler',
    'show_main_menu_handler',
    'show_language_learning_menu_handler',
    'button_callback_handler',
    'handle_private_character_conversation',
    'handle_accusation_direct',
    'execute_scene_action',
    'process_director_decision',
    'progress_report_handler',
    'generate_final_english_report',
    'analyze_and_log_text',
    'send_tutor_explanation',
    'get_participant_code',
    'cancel_post_test_task',
    'save_user_game_state',
    'check_and_unlock_accuse',
    'is_player_ready_to_accuse',
    'get_random_common_space_phrase',
    'check_and_schedule_post_test_message',
    'schedule_post_test_message',
    'handle_message'
]
