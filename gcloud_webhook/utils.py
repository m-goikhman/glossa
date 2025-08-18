import os
import datetime
import json
import tempfile
import re
from google.cloud import storage
from config import GCS_BUCKET_NAME
storage_client = None
bucket = None

def _get_bucket():
    """Lazy initialization of storage client and bucket."""
    global storage_client, bucket
    if storage_client is None:
        storage_client = storage.Client()
    if bucket is None and GCS_BUCKET_NAME:
        try:
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
        except Exception as e:
            print(f"WARNING: Failed to initialize GCS bucket '{GCS_BUCKET_NAME}': {e}")
            bucket = None
    return bucket
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def log_message(user_id: int, role: str, content: str, participant_code: str = None):
    """Writes a message to the user's chat history log in Google Cloud Storage."""
    bucket = _get_bucket()
    if not bucket:
        print("WARNING: GCS_BUCKET_NAME is not set or invalid. Cloud logging is disabled.")
        return

    try:
        # Sanitize content to remove any potential personal information
        if role == "user" and len(content) > 100:
            # Truncate long user messages to prevent logging personal info
            sanitized_content = content[:100] + "... [truncated]"
        else:
            sanitized_content = content

        # Use participant code if available, otherwise fall back to user_id
        if participant_code:
            blob_name = f"participant_logs/{participant_code}_chat_history.txt"
        else:
            blob_name = f"user_logs/chat_history_{user_id}.txt"
        blob = bucket.blob(blob_name)

        try:
            existing_content = blob.download_as_text(encoding="utf-8")
        except Exception: 
            existing_content = ""

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] ({role}): {sanitized_content}\n"
        new_content = existing_content + log_entry

        blob.upload_from_string(new_content, content_type="text/plain; charset=utf-8")

    except Exception as e:
        print(f"[ERROR] Failed to write log to Cloud Storage for user {user_id}: {e}")

# Cache for system prompts to avoid repeated file I/O
_prompt_cache = {}

def combine_character_prompt(character_name: str, language_level: str = "B1") -> str:
    """
    Combines a character's specific prompt with language learning requirements for the specified level.
    Only applies to game characters and narrator, not to tutor.
    
    Args:
        character_name (str): Name of the character (e.g., 'narrator', 'tim', 'fiona', etc.)
        language_level (str): Language level to use (A2, B1, or B2). Defaults to B1.
    
    Returns:
        str: Combined prompt with character-specific instructions and language requirements
    """
    # List of characters that should include language requirements
    game_characters = ["narrator", "tim", "fiona", "pauline", "ronnie"]
    
    try:
        # Load character-specific prompt
        character_prompt_path = f"prompts/prompt_{character_name}.md"
        character_prompt = load_system_prompt(character_prompt_path)
        
        # Only combine with language requirements for game characters and narrator
        if character_name in game_characters:
            # Load language requirements for the specified level
            language_file = f"prompts/language_learning/{language_level.lower()}.md"
            language_requirements = load_system_prompt(language_file)
            
            # Combine them with clear separation
            combined_prompt = f"{character_prompt}\n\n---\n\n## Language Requirements\n{language_requirements}"
            
            return combined_prompt
        else:
            # For non-game characters (like tutor), return just the character prompt
            return character_prompt
        
    except Exception as e:
        print(f"ERROR: Failed to combine prompt for character {character_name} with level {language_level}: {e}")
        # Fallback to just the character prompt if language requirements can't be loaded
        return load_system_prompt(f"prompts/prompt_{character_name}.md")

def create_explain_button(message_id: int) -> list:
    """
    Creates a standardized "Explain difficult words" button for inline keyboards.
    
    Args:
        message_id (int): The message ID to associate with the explain action
    
    Returns:
        list: A list containing the button row for use in InlineKeyboardMarkup
    """
    from telegram import InlineKeyboardButton
    return [[InlineKeyboardButton("📒 Explain difficult words", callback_data=f"explain__init__{message_id}")]]

def get_participant_code_from_state(user_id: int) -> str:
    """Gets participant code from game state if available."""
    try:
        from bot_handlers import GAME_STATE
        state = GAME_STATE.get(user_id, {})
        return state.get("participant_code")
    except ImportError:
        return None

def load_system_prompt(filepath: str) -> str:
    """Loads the system prompt text from a file using an absolute path with caching."""
    # Check cache first
    if filepath in _prompt_cache:
        return _prompt_cache[filepath]
    
    absolute_path = os.path.join(_BASE_DIR, filepath)
    try:
        with open(absolute_path, "r", encoding="utf-8-sig") as file:
            content = file.read().strip()
            # Cache the content
            _prompt_cache[filepath] = content
            return content
    except (FileNotFoundError, OSError, IOError) as e:
        print(f"ERROR: Could not load prompt file {absolute_path}: {e}")
        return "You are a helpful assistant."





def write_log_entry(user_id: int, entry_type: str, query: str, feedback: str = ""):
    """Safely reads, updates, and writes a log entry to a user's JSON progress file."""
    try:
        filepath = get_log_filepath(user_id, 'progress')
        
        logs = {"words_learned": [], "writing_feedback": []}
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8-sig") as f:
                    logs = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logs = {"words_learned": [], "writing_feedback": []}

        new_entry = {"timestamp": datetime.datetime.now().isoformat(), "query": query, "feedback": feedback}
        
        target_list_name = ""
        if entry_type == "word":
            target_list_name = "words_learned"
        elif entry_type == "feedback":
            target_list_name = "writing_feedback"
        
        if target_list_name and logs.get(target_list_name) is not None:
            target_list = logs[target_list_name]
            is_duplicate = any(entry['query'] == query for entry in target_list)
            if not is_duplicate:
                target_list.append(new_entry)
        
        try:
            with tempfile.NamedTemporaryFile('w', delete=False, dir=os.path.dirname(filepath), encoding='utf-8') as temp_f:
                json.dump(logs, temp_f, indent=2, ensure_ascii=False)
                temp_path = temp_f.name
            os.replace(temp_path, filepath)
        except (OSError, IOError) as e:
            print(f"[WARNING] Could not write to progress log file for user {user_id}: {e}")
        except Exception as e:
            print(f"[ERROR] Failed to write to progress log file for user {user_id}: {e}")
    except (OSError, IOError) as e:
        print(f"[WARNING] Could not access progress log file for user {user_id}: {e}")
    except Exception as e:
        print(f"[ERROR] Unexpected error in write_log_entry for user {user_id}: {e}")

def escape_markdown_v2(text: str) -> str:
    """Escapes special characters for Telegram's MarkdownV2 parse mode."""
    if not isinstance(text, str):
        return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def split_long_message(text: str, max_length: int = 4000) -> list[str]:
    """
    Splits a long text into multiple smaller chunks, respecting paragraphs and newlines.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""
    paragraphs = text.split('\n\n')

    for paragraph in paragraphs:
        if len(paragraph) > max_length:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            
            lines = paragraph.split('\n')
            for line in lines:
                if len(current_chunk) + len(line) + 1 > max_length:
                    chunks.append(current_chunk)
                    current_chunk = ""
                current_chunk += line + "\n"
            if current_chunk: # Add the last part of the long paragraph
                 chunks.append(current_chunk)
                 current_chunk = ""
            continue

        if len(current_chunk) + len(paragraph) + 2 > max_length:
            chunks.append(current_chunk)
            current_chunk = paragraph
        else:
            if current_chunk:
                current_chunk += "\n\n"
            current_chunk += paragraph

    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks