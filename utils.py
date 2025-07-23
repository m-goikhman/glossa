import os
import datetime
import json

def load_system_prompt(filepath: str) -> str:
    """Loads the system prompt text from a file."""
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        print(f"ERROR: Prompt file not found: {filepath}")
        return "You are a helpful assistant."

def log_message(user_id: int, role: str, content: str):
    """Writes a message to the log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] User {user_id} ({role}): {content}\n"
    with open("chat_logs.txt", "a", encoding="utf-8") as log_file:
        log_file.write(log_entry)

def get_user_log_path(user_id: int) -> str:
    """Creates a directory for user logs and returns the path to a user's log file."""
    log_dir = "user_logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    return os.path.join(log_dir, f"log_{user_id}.json")

def write_log_entry(user_id: int, entry_type: str, query: str, feedback: str = ""):
    """Reads, updates, and writes a log entry to a user's JSON file."""
    filepath = get_user_log_path(user_id)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logs = {"words_learned": [], "writing_feedback": []}
    
    new_entry = {"timestamp": datetime.datetime.now().isoformat(), "query": query, "feedback": feedback}
    
    if entry_type == "word" and new_entry not in logs["words_learned"]:
        logs["words_learned"].append(new_entry)
    elif entry_type == "feedback" and new_entry not in logs["writing_feedback"]:
        logs["writing_feedback"].append(new_entry)
        
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)