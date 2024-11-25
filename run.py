# run.py
import os
import sys
from bot.main import run_bot

# Add the current directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

if __name__ == "__main__":
    run_bot()
