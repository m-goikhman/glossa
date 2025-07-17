# Interactive Narrative Detective Game

## 🕵️ Project Overview
An experimental project combining interactive murder mystery party games with AI-powered chatbots. The project allows users to engage in immersive narrative experiences, solving mysteries through dynamic role-playing scenarios.

## 🎭 Features
- Character Chatbots: Unique backstories and motivations for each character
- Interactive Scenarios: Dynamic detective stories with multiple outcomes
- Clue System: Progressive information reveal to maintain suspense
- Multi-player Support: Group game functionality

## 🔧 Technical Setup

### Dependencies
```bash
pip install -r requirements.txt
```

### Configuration
Create `.env` files for each bot with the following structure:

Example: `.env_detective_bot`
```
TELEGRAM_TOKEN=your-telegram-bot-token
AI_API_KEY=your-ai-api-key
PROMPT_FILE=prompt_detective.txt
```

### Prompt Files
Create prompt files with system instructions for each bot. Example:
```
You are a detective character in an interactive murder mystery game. Respond in character and help advance the narrative.
```

### Running the Bots

#### Run a single bot:
```bash
CONFIG_FILE=.env_detective_bot python3 build_bot.py
```

#### Run multiple bots:
```bash
bash run_all.sh
```

## 📝 Game Mechanics
- Choose a scenario
- Initialize character chatbots
- Start the investigation
- Follow clues and solve the mystery

## 🔍 Current Scenario
"The Business of Murder" - A murder mystery set in an academic environment, featuring complex character interactions and hidden motivations.

## 📜 Source & Attribution
- Original Murder Mystery Game: "The Business of Murder" by John H. Kim
- Original Source: https://www.darkshire.net/jhkim/rpg/murder/business.html
- Used with permission from the author for chatbot experimentation

## 🛠 Technical Details
- Supports multiple AI models and API integrations
- Maintains short-term conversation memory
- Logs chat interactions
- Configurable through environment files

## 📊 Upcoming Features
- Separate log files per bot
- Optional Google Sheets logging
- Enhanced narrative complexity

## 📝 License
MIT License - See LICENSE file for details
Original game content © John H. Kim - Used with permission