# TeachOrTell - Interactive Narrative Detective Game

## 🕵️ Project Overview

This is an experimental educational tool designed to increase learning engagement for English language learners. It combines an interactive detective story with a multi-role AI chatbot, allowing users to practice their language skills in an immersive and motivating narrative experience.

The project features a detective mystery game where players act as detectives, interrogating AI-powered suspects while receiving real-time language assistance and progress tracking.

## 🎭 Key Features

- **Multi-Role AI**: A single bot seamlessly switches between multiple personalities: suspects, a narrator, and a language tutor
- **Dynamic Scenes**: An AI "Game Director" creates unique, cinematic scenes with character reactions and interactions
- **Contextual Memory**: Characters remember conversation topics to avoid repetition, creating natural dialogue flow
- **Interactive Explanations**: Integrated language tutor explains difficult words and phrases on demand
- **Personalized Learning**: Silent analysis of player messages generates detailed language progress reports
- **Public & Private Modes**: Question suspects in group settings or take them aside for private interrogation
- **Persistent Game State**: Automatic save/resume functionality without losing progress

## 🔍 Current Scenario: "The Chicago Formula"

A mystery set in an academic environment where a brilliant PhD student is found attacked and unconscious in his apartment after a party. As a detective, you must interrogate the remaining guests:
- A nervous colleague
- A secret business partner  
- A distraught girlfriend
- A dangerous creditor

Uncover the truth through careful investigation and interrogation!

## 🏗️ Project Structure

This repository contains **two versions** of the same chatbot:

```
TeachOrTell/
├── gcloud_webhook/          # Google Cloud App Engine version
│   ├── main.py             # Webhook handler for production
│   ├── app.yaml            # App Engine configuration
│   ├── requirements.txt    # Production dependencies
│   └── README.md           # Detailed deployment guide
├── local_polling/          # Local development version
│   ├── main.py             # Polling-based bot for local use
│   ├── requirements.txt    # Development dependencies
│   └── README.md           # Local setup guide
├── game_texts/             # Game narrative content
├── prompts/                # AI system prompts and character definitions
├── images/                 # Game visual assets
└── README.md               # This file
```

## 🚀 Quick Start

### Option 1: Local Development (Recommended for testing)

```bash
cd local_polling
pip install -r requirements.txt

# Create .env file with your API keys
echo "TELEGRAM_TOKEN=your_bot_token" > .env
echo "GROQ_API_KEY=your_groq_key" >> .env

python3 main.py
```

### Option 2: Google Cloud Deployment (Production)

```bash
cd gcloud_webhook
pip install -r requirements.txt

# Set up Google Cloud credentials and secrets
# See gcloud_webhook/README.md for detailed instructions

gcloud app deploy
```

## 🔧 Technical Requirements

### Core Dependencies
- **Python 3.13+**
- **Telegram Bot Token** (from [@BotFather](https://t.me/botfather))
- **Groq API Key** (for AI interactions)

### Version-Specific Dependencies

| Feature | Local Polling | Google Cloud |
|---------|---------------|--------------|
| **Web Framework** | python-telegram-bot | Starlette + Uvicorn |
| **Deployment** | Local machine | Google App Engine |
| **Storage** | Local files | Google Cloud Storage |
| **Secrets** | .env file | Google Secret Manager |
| **Scaling** | Single instance | Auto-scaling |

## 📚 Game Flow

1. **Onboarding**: Consent and game instructions
2. **Investigation**: Examine clues and interrogate suspects
3. **Accusation**: Make final accusation after gathering evidence
4. **Progress Report**: View detailed language learning analysis

## 🎯 Use Cases

- **Language Learning**: Practice English through interactive storytelling
- **Educational Gaming**: Engage students with narrative-driven learning
- **AI Research**: Study multi-role chatbot interactions
- **Game Development**: Template for interactive narrative games

## 🔒 Privacy & Security

- **No PII Collection**: Personal information is not collected or stored
- **Sanitized Logging**: User messages are truncated and sanitized
- **Secure Storage**: Production version uses Google Cloud with proper access controls
- **Environment Isolation**: Development and production configurations are separate

## 🧪 Testing

```bash
# Test game state management
python3 gcloud_webhook/test_game_state.py

# Test progress tracking  
python3 gcloud_webhook/test_progress.py

# Test secret management
python3 gcloud_webhook/test_secrets.py
```

## 📝 Development Notes

This project was developed in close collaboration with an AI assistant. The core Python code, project architecture, and prompt engineering were iteratively designed and generated with the help of **Google's Gemini Pro 2.5**.

## 📜 Source & Attribution

- **Original Game**: "The Business of Murder" by John H. Kim
- **Source**: https://www.darkshire.net/jhkim/rpg/murder/business.html
- **License**: Used with permission from the author for chatbot experimentation

## 📄 License

- **Project**: MIT License
- **Original Game Content**: © John H. Kim - Used with permission

## 📞 Support

For detailed setup instructions, see the README files in each version directory:
- **Local Development**: `local_polling/README.md`
- **Cloud Deployment**: `gcloud_webhook/README.md`

---

**Happy detecting and learning! 🕵️📚**
