import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# --- API Configuration ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# --- Character & Actor Data ---
CHARACTER_DATA = {
    "tim": {"prompt_file": "prompts/prompt_tim.mdown", "full_name": "Tim Kane", "emoji": "📚"},
    "pauline": {"prompt_file": "prompts/prompt_pauline.mdown", "full_name": "Pauline Thompson", "emoji": "💼"},
    "fiona": {"prompt_file": "prompts/prompt_fiona.mdown", "full_name": "Fiona McAllister", "emoji": "💔"},
    "ronnie": {"prompt_file": "prompts/prompt_ronnie.mdown", "full_name": "Ronnie Snapper", "emoji": "🔥"},
    "tutor": {"prompt_file": "prompts/prompt_tutor.mdown", "full_name": "English Tutor", "emoji": "🧑‍🏫"},
    "narrator": {"prompt_file": "prompts/prompt_narrator.mdown", "full_name": "Narrator", "emoji": "🎙️"},
}

# --- Global State Variables ---
GAME_STATE = {}
user_histories = {}
message_cache = {}