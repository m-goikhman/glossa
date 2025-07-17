#!/bin/bash

echo "Starting Tim..."
CONFIG_FILE=.env_tim python3 build_bot.py &

echo "Starting Pauline..."
CONFIG_FILE=.env_pauline python3 build_bot.py &

echo "Both bots are now running in the background 🎉"
echo "Use 'ps' or 'htop' to monitor them, or 'pkill -f build_bot.py' to stop them."