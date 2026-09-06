#!/bin/zsh
# Draft night: keeps the Mac awake, runs the bot against your real league room, logs to data/draft_night.out.
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"
exec caffeinate -dims .venv/bin/python live.py league "$@" 2>&1 | tee -a data/draft_night.out
