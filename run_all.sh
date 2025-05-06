#!/bin/bash

echo "Starting Lingo T bot..."
CONFIG_FILE=.env_lingo_t python3 build_bot.py &

echo "Starting Lingo N bot..."
CONFIG_FILE=.env_lingo_n python3 build_bot.py &

echo "Both bots are now running in the background 🎉"
echo "Use 'ps' or 'htop' to monitor them, or 'kill' to stop them."