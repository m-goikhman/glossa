# Interactive Narrative Detective Game

## 🕵️ Project Overview
This project is an experimental tool designed to increase learning engagement for English language learners. It combines an interactive detective story with a multi-role AI chatbot, allowing users to practice their language skills in an immersive and motivating narrative experience.

## 🎭 Features
- Multi-Role AI: A single bot seamlessly switches between multiple personalities: suspects, a narrator, and a language tutor.

- Dynamic Scenes: An AI "Game Director" creates unique, cinematic scenes with character reactions and interactions, going beyond simple Q&A.

- Contextual Memory: Characters remember the topic of conversation to avoid repeating themselves, creating a more natural dialogue flow.

- Interactive Explanations: An integrated language tutor helps players learn English by explaining difficult words and phrases on demand.

- Personalized Learning: The bot silently analyzes the player's messages and generates a personal progress report on their language skills.

- Public & Private Modes: Players can question suspects in a group setting or take them aside for a private interrogation.

## 🔧 Technical Setup

### Dependencies
```bash
pip install -r requirements.txt
```

### Configuration
The project uses a single `.env` file for configuration. Create it in the root directory of the project.

Example: `.env`
```
TELEGRAM_TOKEN="your-telegram-bot-token"
GROQ_API_KEY="your-groq-api-key"
```
All other configurations, such as character data and prompt file paths, are managed in the `config.py` file.

### Running the Bots

3. Running the Bot
To start the bot, simply run the `main.py` script from your terminal:

```bash
python3 main.py
```


## 🔍 Current Scenario
**"The Chicago Formula"** - A mystery set in an academic environment. A brilliant PhD student is found attacked and unconscious in his apartment after a party, and a detective (the player) must interrogate the remaining guests—a nervous colleague, a secret business partner, a distraught girlfriend, and a dangerous creditor—to uncover the truth.


## 📜 Source & Attribution
- Original Murder Mystery Game: "The Business of Murder" by John H. Kim
- Original Source: https://www.darkshire.net/jhkim/rpg/murder/business.html
- Used with permission from the author for chatbot experimentation


## ✨ Development Note
This project was developed in close collaboration with an AI assistant. The core Python code, project architecture, and prompt engineering were iteratively designed and generated with the help of **Google's Gemini Pro 2.5**.


## 📝 License
MIT License - See LICENSE file for details
Original game content © John H. Kim - Used with permission