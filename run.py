import sys
from pathlib import Path


# Add the current directory to Python path
current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir))

from runtime_env import load_env_file

load_env_file(current_dir / ".env")

from bot.main import run_bot

if __name__ == "__main__":
    run_bot()
