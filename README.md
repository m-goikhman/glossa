# Interactive Narrative Bots for Language Learning

This project contains the backend code for two Telegram bots used in an experimental study on reducing Foreign Language Anxiety (FLA) through interactive, AI-mediated narrative dialogue.  
Each bot has a distinct communicative style, driven by a custom system prompt, and helps users practice English in role-playing situations.

The code supports running multiple bots from a single codebase using `.env` configuration files.
 @lingo_n_bot is a Telegram bot that helps users practice English through role-playing dialogues.  
It uses the Groq API (LLaMA 3.3 model) to generate responses and maintains a short memory of past messages for more natural conversations.

## Features
- Connects to Telegram via Bot API.
- Sends messages to Groq API (LLaMA 3.3 model).
- Remembers the last 10 user-assistant exchanges per user.
- Saves all chat logs to `chat_logs.txt`.
- Responds only in private chats or when mentioned in group chats.
- Easily configurable via `.env` files.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create `.env` files for each bot

Example: `.env_lingo_t`
```
TELEGRAM_TOKEN=your-lingo-t-bot-token
GROQ_API_KEY=your-groq-api-key
PROMPT_FILE=prompt_lingo_t.txt
```

Example: `.env_lingo_n`
```
TELEGRAM_TOKEN=your-lingo-n-bot-token
GROQ_API_KEY=your-groq-api-key
PROMPT_FILE=prompt_lingo_n.txt
```

### 3. Create prompt files

Each prompt file should contain a single-line system prompt for the bot.

Example: `prompt_lingo_t.txt`
```
You are a patient teacher who guides users through role-play situations in English.
```
---
## Running the bots

### Run a single bot:
```bash
CONFIG_FILE=.env_lingo_t python3 build_bot.py
```

### Or use provided scripts:
```bash
bash run_lingo_t.sh
bash run_lingo_n.sh
```

### Run both bots at once:
```bash
bash run_all.sh
```
