import os
import sys
from google.cloud import secretmanager

def get_secret(secret_name: str, default_env: str = None) -> str:
    """Safely retrieves secrets from Google Secret Manager or environment variables."""
    try:
        # Try Google Secret Manager first
        client = secretmanager.SecretManagerServiceClient()
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT', 'the-chicago-formula')
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("UTF-8").strip()
        return secret_value
    except Exception as e:
        # Fallback to environment variables for local development
        if default_env:
            value = os.getenv(default_env)
            if value:
                print(f"WARNING: Using environment variable for {secret_name}. Secret Manager failed: {e}", file=sys.stderr)
                return value.strip() if value else None
        return None

# --- API Configuration ---
TELEGRAM_TOKEN = get_secret("telegram-bot-token", "TELEGRAM_TOKEN")
GROQ_API_KEY = get_secret("groq-api-key", "GROQ_API_KEY")
GCS_BUCKET_NAME = get_secret("gcs-bucket-name", "GCS_BUCKET_NAME")

# Remove debug prints for security
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found in Secret Manager or environment variables")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in Secret Manager or environment variables")

if not GCS_BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME not found in Secret Manager or environment variables")


# --- Game Constants ---
# Total number of clues to be examined to unlock the final accusation
TOTAL_CLUES = 4
# Character keys for all suspects in the game
SUSPECT_KEYS = ["tim", "pauline", "fiona", "ronnie"]

# --- Character & Actor Data ---
CHARACTER_DATA = {
    "tim": {"prompt_file": "prompts/prompt_tim.md", "full_name": "Tim Kane", "emoji": "📚"},
    "pauline": {"prompt_file": "prompts/prompt_pauline.md", "full_name": "Pauline Thompson", "emoji": "💼"},
    "fiona": {"prompt_file": "prompts/prompt_fiona.md", "full_name": "Fiona McAllister", "emoji": "💔"},
    "ronnie": {"prompt_file": "prompts/prompt_ronnie.md", "full_name": "Ronnie Snapper", "emoji": "😎"},
    "tutor": {"prompt_file": "prompts/prompt_tutor.md", "full_name": "English Tutor", "emoji": "🧑‍🏫"},
    "narrator": {"prompt_file": "prompts/prompt_narrator.md", "full_name": "Narrator", "emoji": "🎙️"},
    "director": {"prompt_file": "prompts/prompt_director.md", "full_name": "Game Director", "emoji": "🎬"},
    "lexicographer": {"prompt_file": "prompts/prompt_lexicographer.md", "full_name": "Lexicographer", "emoji": "📖"},
}

# --- Global State Variables ---
GAME_STATE = {}
user_histories = {}
message_cache = {}
POST_TEST_TASKS = {}  # stores user_id -> asyncio.Task for post-test scheduling
