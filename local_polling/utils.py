import os
import datetime
import json
import tempfile
import re

def load_system_prompt(filepath: str) -> str:
    """Loads the system prompt text from a file."""
    try:
        with open(filepath, "r", encoding="utf-8-sig") as file:
            return file.read().strip()
    except FileNotFoundError:
        print(f"ERROR: Prompt file not found: {filepath}")
        return "You are a helpful assistant."

def get_log_filepath(user_id: int, log_type: str) -> str:
    """Creates a directory for user logs and returns the path to a user's log file."""
    log_dir = "user_logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    if log_type == 'progress':
        return os.path.join(log_dir, f"log_{user_id}.json")
    elif log_type == 'chat':
        return os.path.join(log_dir, f"chat_history_{user_id}.txt")
    else:
        return os.path.join(log_dir, f"{log_type}_{user_id}.log")

def log_message(user_id: int, role: str, content: str):
    """Writes a message to the user's personal chat history log."""
    filepath = get_log_filepath(user_id, 'chat')
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] ({role}): {content}\n"
    with open(filepath, "a", encoding="utf-8") as log_file:
        log_file.write(log_entry)

def write_log_entry(user_id: int, entry_type: str, query: str, feedback: str = ""):
    """Safely reads, updates, and writes a log entry to a user's JSON progress file."""
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
    except Exception as e:
        print(f"[ERROR] Failed to write to progress log file: {e}")

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