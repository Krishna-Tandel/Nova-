import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_PATH = os.path.join(DATA_DIR, "log.txt")

# Nova refuses any action that is not in this list
ALLOWED_ACTIONS = {
    "open", "search", "chat",
    "lock", "shutdown", "restart", "cancel_shutdown",
    "volume_up", "volume_down", "volume_mute", "volume_set",
    "screenshot", "folder",
    "close", "type",
}

# These wait for you to type "yes" before they run
NEEDS_CONFIRM = {"shutdown", "restart", "close", "type"}


def is_allowed(action):
    return action in ALLOWED_ACTIONS


def needs_confirmation(action):
    return action in NEEDS_CONFIRM


def log_action(kind, detail="", status="done"):
    """Adds one line to data/log.txt. Never crashes Nova if the file can't be written."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{now} | {status} | {kind} | {detail}\n")
    except OSError:
        pass