"""
Privacy Configuration for the Detective Game Bot

This file ensures that no personal information (names, usernames, etc.) 
is collected, stored, or logged. Only anonymous user IDs are used.
"""

# Privacy settings
PRIVACY_CONFIG = {
    "log_user_id_only": True,  # Only log numeric user IDs, never names/usernames
    "no_personal_data": True,  # Never collect or store personal information
    "anonymous_logging": True,  # All logs use anonymous identifiers
    "data_retention": "game_session_only"  # Data only kept for active game sessions
}

# Allowed data to log (privacy-safe)
ALLOWED_LOG_DATA = {
    "user_id": True,  # Numeric Telegram user ID (anonymous)
    "message_type": True,  # Type of message (text, callback, etc.)
    "game_actions": True,  # Game-related actions (clues examined, etc.)
    "learning_progress": True,  # Language learning progress (anonymous)
    "error_logs": True,  # Error logs (without personal data)
}

# Data that should NEVER be logged
FORBIDDEN_LOG_DATA = {
    "first_name": False,
    "last_name": False,
    "username": False,
    "phone_number": False,
    "email": False,
    "location": False,
    "personal_messages": False,  # Content of personal messages
    "profile_photos": False,
    "contact_info": False
}

def is_privacy_compliant(data_dict: dict) -> bool:
    """
    Check if a data dictionary contains only privacy-compliant information.
    Returns True if safe, False if personal data is detected.
    """
    for forbidden_key in FORBIDDEN_LOG_DATA:
        if forbidden_key in data_dict:
            return False
    return True

def sanitize_log_data(data_dict: dict) -> dict:
    """
    Remove any personal information from data before logging.
    Returns a sanitized version with only safe data.
    """
    sanitized = {}
    for key, value in data_dict.items():
        if key in ALLOWED_LOG_DATA and ALLOWED_LOG_DATA[key]:
            sanitized[key] = value
        elif key == 'from' and isinstance(value, dict):
            # Only keep user_id from 'from' field
            if 'id' in value:
                sanitized['user_id'] = value['id']
    return sanitized
