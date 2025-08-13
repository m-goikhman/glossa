# Interactive Narrative Detective Game

## 🕵️ Project Overview
This project is an experimental tool designed to increase learning engagement for English language learners. It combines an interactive detective story with a multi-role AI chatbot, allowing users to practice their language skills in an immersive and motivating narrative experience.

## 🎭 Features
- **Multi-Role AI**: A single bot seamlessly switches between multiple personalities: suspects, a narrator, and a language tutor.

- **Dynamic Scenes**: An AI "Game Director" creates unique, cinematic scenes with character reactions and interactions, going beyond simple Q&A.

- **Contextual Memory**: Characters remember the topic of conversation to avoid repeating themselves, creating a more natural dialogue flow.

- **Interactive Explanations**: An integrated language tutor helps players learn English by explaining difficult words and phrases on demand.

- **Personalized Learning**: The bot silently analyzes the player's messages and generates a personal progress report on their language skills.

- **Public & Private Modes**: Players can question suspects in a group setting or take them aside for a private interrogation.

- **Persistent Game State**: Game progress is automatically saved and can be resumed after breaks without losing progress.

- **Seamless Continuation**: Players can continue playing immediately after breaks without needing to use commands.

- **Enhanced Commands**: 
  - `/start` - Start or resume the game
  - `/restart` - Clear current game and start fresh (for testing)
  - `/menu` - Show game menu
  - `/progress` - View language learning progress

## 🔧 Technical Setup

### Prerequisites
- Python 3.13+
- Google Cloud Platform account with Secret Manager enabled
- Telegram Bot Token
- Groq API Key

### Dependencies
```bash
pip install -r requirements.txt
```

### Configuration

#### Google Secret Manager (Recommended for Production)
The project uses Google Secret Manager for secure storage of sensitive configuration:

1. **Enable Secret Manager API** in your Google Cloud project
2. **Create secrets**:
   ```bash
   gcloud secrets create telegram-bot-token --data-file=<(echo -n "YOUR_BOT_TOKEN")
   gcloud secrets create groq-api-key --data-file=<(echo -n "YOUR_GROQ_API_KEY")
   gcloud secrets create gcs-bucket-name --data-file=<(echo -n "YOUR_BUCKET_NAME")
   ```
3. **Set IAM permissions** for your App Engine service account:
   ```bash
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:YOUR_PROJECT_ID@appspot.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor"
   ```

#### Environment Variables (Local Development)
For local development, you can use environment variables as fallback:
```bash
export TELEGRAM_TOKEN="your-telegram-bot-token"
export GROQ_API_KEY="your-groq-api-key"
export GCS_BUCKET_NAME="your-bucket-name"
export GOOGLE_CLOUD_PROJECT="your-project-id"
```

### Running the Bot

#### Local Development
```bash
python3 main.py
```

#### Google App Engine Deployment
```bash
gcloud app deploy --project=YOUR_PROJECT_ID
```

## 🏗️ Architecture

### Core Components
- **`main.py`**: Webhook handler and bot initialization
- **`bot_handlers.py`**: Core game logic and message handling
- **`ai_services.py`**: AI model interactions (Groq API)
- **`game_state_manager.py`**: Persistent game state management
- **`progress_manager.py`**: Learning progress tracking
- **`config.py`**: Configuration and secret management
- **`utils.py`**: Utility functions and logging

### Data Storage
- **Google Cloud Storage**: Game states, user progress, and logs
- **Google Secret Manager**: API keys and sensitive configuration
- **In-Memory Cache**: System prompts and active game states

### Security Features
- **No PII Logging**: User messages are sanitized and truncated in logs
- **Secure Secret Management**: API keys stored in Google Secret Manager
- **Environment Variable Fallback**: Secure local development support

## 🔍 Current Scenario
**"The Chicago Formula"** - A mystery set in an academic environment. A brilliant PhD student is found attacked and unconscious in his apartment after a party, and a detective (the player) must interrogate the remaining guests—a nervous colleague, a secret business partner, a distraught girlfriend, and a dangerous creditor—to uncover the truth.

## 📚 Game Flow
1. **Onboarding**: Consent and instructions
2. **Investigation**: Examine clues and interrogate suspects
3. **Accusation**: Make final accusation after gathering evidence
4. **Progress Report**: View detailed language learning analysis

## 🚀 Recent Updates & Fixes

### v2.0 - Major Improvements
- ✅ **Persistent Game State**: Automatic save/resume functionality
- ✅ **Secret Manager Integration**: Secure API key management
- ✅ **Enhanced Commands**: Added `/restart` command for testing
- ✅ **Performance Optimizations**: Lazy initialization and prompt caching
- ✅ **Privacy Enhancements**: Sanitized logging and PII protection
- ✅ **Bug Fixes**: Resolved bucket initialization and startup issues

### Technical Improvements
- **Lazy Initialization**: GCS buckets created only when needed
- **Error Handling**: Robust error handling for network and storage issues
- **Logging**: Comprehensive logging with privacy protection
- **Code Quality**: Improved error handling and code organization

## 📁 Project Structure
```
gcloud_webhook/
├── main.py                 # Main application entry point
├── bot_handlers.py         # Core game logic and handlers
├── ai_services.py          # AI model interactions
├── game_state_manager.py   # Persistent state management
├── progress_manager.py     # Learning progress tracking
├── config.py              # Configuration and secrets
├── utils.py               # Utility functions
├── privacy_config.py      # Privacy and logging configuration
├── app.yaml               # App Engine configuration
├── requirements.txt       # Python dependencies
├── game_texts/            # Game narrative content
├── prompts/               # AI system prompts
├── images/                # Game visual assets
└── README.md              # This file
```

## 🧪 Testing
```bash
# Test Secret Manager integration
python3 test_secrets.py

# Test game state management
python3 test_game_state.py

# Test progress tracking
python3 test_progress.py
```

## 📝 Development Notes
This project was developed in close collaboration with an AI assistant. The core Python code, project architecture, and prompt engineering were iteratively designed and generated with the help of **Google's Gemini Pro 2.5**.

## 🔒 Privacy & Security
- **No PII Collection**: Personal information is not collected or stored
- **Sanitized Logging**: User messages are truncated and sanitized
- **Secure Storage**: All data stored in Google Cloud with proper access controls
- **Environment Isolation**: Development and production configurations are separate

## 📜 Source & Attribution
- Original Murder Mystery Game: "The Business of Murder" by John H. Kim
- Original Source: https://www.darkshire.net/jhkim/rpg/murder/business.html
- Used with permission from the author for chatbot experimentation

## 📄 License
MIT License - See LICENSE file for details
Original game content © John H. Kim - Used with permission