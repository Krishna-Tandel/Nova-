import os
import time
import subprocess
import webbrowser
from datetime import datetime
from urllib.parse import quote_plus

import keyboard

from core import winfocus
from core.brain import ask_brain
from core.safety import log_action, is_allowed, needs_confirmation

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HOME = os.path.expanduser("~")
MAX_TYPE = 300  # longest text Nova will type in one go

# App name you type -> what Windows should launch.
# To add your own app, add a line with its full path, for example:
# "discord": r"C:\Users\Krish\AppData\Local\Discord\Update.exe",
APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "task manager": "taskmgr.exe",
    "chrome": "chrome",
    "edge": "msedge",
    "settings": "ms-settings:",
    "spotify": "spotify:",
}

WEBSITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
}

FOLDERS = {
    "downloads": "Downloads",
    "documents": "Documents",
    "desktop": "Desktop",
    "pictures": "Pictures",
    "music": "Music",
    "videos": "Videos",
}

# Apps Nova is allowed to close: name -> process names.
# "explorer" is NOT here on purpose: closing it removes your taskbar.
CLOSABLE = {
    "notepad": ["notepad.exe"],
    "calculator": ["CalculatorApp.exe", "Calculator.exe", "win32calc.exe"],
    "paint": ["mspaint.exe"],
    "chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "spotify": ["Spotify.exe"],
}

# Closing these closes ALL their windows, so Nova warns you
WARN_ALL_WINDOWS = {"chrome", "edge"}


# ---------- Open / search ----------
def open_target(name):
    """Open an app or website by name."""
    name = name.strip().lower()
    for filler in ("the ", "my "):
        if name.startswith(filler):
            name = name[len(filler):]

    if name in APPS:
        try:
            os.startfile(APPS[name])
            log_action("open", name, "done")
            return f"Opening {name}..."
        except OSError:
            log_action("open", name, "failed")
            return f"I couldn't open {name}. Check its path in actions.py."

    if name in WEBSITES:
        webbrowser.open(WEBSITES[name])
        log_action("open", name, "done")
        return f"Opening {name}..."

    # Looks like a web address, e.g. "github.com"
    if "." in name and " " not in name:
        webbrowser.open(name if name.startswith("http") else "https://" + name)
        log_action("open", name, "done")
        return f"Opening {name}..."

    log_action("open", name, "unknown")
    return f"I don't know '{name}' yet. Add it to APPS in core/actions.py."


def web_search(query):
    query = query.strip()
    if not query:
        return "What should I search for?"
    webbrowser.open("https://www.google.com/search?q=" + quote_plus(query))
    log_action("search", query, "done")
    return f"Searching for: {query}"


def open_folder(name):
    sub = FOLDERS.get(name)
    if not sub:
        return "I don't know that folder."
    path = os.path.join(HOME, sub)
    if os.path.isdir(path):
        os.startfile(path)
        return f"Opening your {name} folder..."
    return f"I couldn't find your {name} folder."


# ---------- Close an app ----------
def close_app(name):
    exes = CLOSABLE.get(name)
    if not exes:
        return f"I can't close {name}."
    closed = False
    for exe in exes:
        # No /F: the app is asked to close politely, so it can ask to save your work
        result = subprocess.run(["taskkill", "/IM", exe], capture_output=True,
                                creationflags=NO_WINDOW)
        if result.returncode == 0:
            closed = True
    if closed:
        return f"Closed {name}. If it asks to save, answer it in that window."
    return f"{name} doesn't seem to be running."


# ---------- Type text ----------
def type_text(payload):
    if not winfocus.focus_last():
        return "Windows wouldn't let me switch to that window. Click it first, then try again."
    time.sleep(0.3)
    keyboard.write(payload, delay=0.01)
    return f"Typed {len(payload)} characters."


# ---------- Volume (uses the keyboard's volume keys; each press is about 2%) ----------
def _press(key, times):
    for _ in range(times):
        keyboard.send(key)
        time.sleep(0.01)


def volume_up():
    _press("volume up", 5)
    return "Volume up."


def volume_down():
    _press("volume down", 5)
    return "Volume down."


def volume_mute():
    keyboard.send("volume mute")
    return "Toggled mute."


def set_volume(level):
    try:
        n = max(0, min(100, int(level)))
    except ValueError:
        return "Tell me a number from 0 to 100."
    _press("volume down", 50)          # go to zero first
    _press("volume up", round(n / 2))  # then climb up
    return f"Volume set to about {n}%."


# ---------- Screenshot ----------
def take_screenshot():
    try:
        from PIL import ImageGrab
    except ImportError:
        return "Screenshots need Pillow. Run: pip install pillow"
    folder = os.path.join(HOME, "Pictures", "Nova Screenshots")
    os.makedirs(folder, exist_ok=True)
    name = datetime.now().strftime("screenshot_%Y-%m-%d_%H-%M-%S.png")
    path = os.path.join(folder, name)
    ImageGrab.grab().save(path)
    return f"Screenshot saved: {name} (in Pictures\\Nova Screenshots)"


# ---------- PC commands ----------
def lock_pc():
    subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], creationflags=NO_WINDOW)
    return "Locking your PC..."


def shutdown_pc():
    subprocess.run(["shutdown", "/s", "/t", "10"], creationflags=NO_WINDOW)
    return "Shutting down in 10 seconds. Type 'cancel shutdown' to stop it."


def restart_pc():
    subprocess.run(["shutdown", "/r", "/t", "10"], creationflags=NO_WINDOW)
    return "Restarting in 10 seconds. Type 'cancel shutdown' to stop it."


def cancel_shutdown():
    result = subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=NO_WINDOW)
    if result.returncode == 0:
        return "Shutdown cancelled."
    return "No shutdown or restart was scheduled."


# action name -> (function, question shown when confirmation is needed)
SYSTEM = {
    "lock": (lock_pc, "lock your PC"),
    "shutdown": (shutdown_pc, "shut down your PC"),
    "restart": (restart_pc, "restart your PC"),
    "cancel_shutdown": (cancel_shutdown, "cancel the shutdown"),
}

# Safe actions that run straight away
SIMPLE = {
    "volume_up": volume_up,
    "volume_down": volume_down,
    "volume_mute": volume_mute,
    "screenshot": take_screenshot,
}


# ---------- Confirmation ----------
def confirm_pending(pending):
    result = pending["run"]()
    log_action(pending["kind"], "confirmed by user", "done")
    return result


def cancel_pending(pending):
    log_action(pending["kind"], "cancelled by user", "cancelled")
    return "Cancelled. Nothing was changed."


# ---------- Command routing ----------
def run_local(text):
    """Fast commands that need no brain. Returns a reply, or None if not recognised."""
    text = text.strip().lower()

    for prefix in ("open ", "launch ", "start ", "run "):
        if text.startswith(prefix):
            name = text[len(prefix):].strip()
            known = name.replace("the ", "", 1).replace("my ", "", 1)
            if known in APPS or known in WEBSITES or ("." in known and " " not in known):
                return open_target(name)
            return None

    for prefix in ("search for ", "search ", "google "):
        if text.startswith(prefix):
            return web_search(text[len(prefix):])

    return None


def handle_type(text):
    """'type hello world' -> asks for confirmation, then types into your last window."""
    payload = text[4:].strip()
    if not payload:
        return "What should I type? Example: type hello world", None
    if not is_allowed("type"):
        return "That action isn't allowed.", None

    payload = payload[:MAX_TYPE]
    hwnd = winfocus.last_external
    if not winfocus.is_valid(hwnd):
        return "Click the window you want to type into first, then use Nova again.", None

    window_title = winfocus.title(hwnd)
    # Only the length is logged, never the text itself (it could be private)
    log_action("type", f"{len(payload)} characters into '{window_title}'", "pending")
    pending = {"kind": "type", "run": lambda: type_text(payload)}
    return (f'Type "{payload}" into "{window_title}"? '
            f"Type yes to confirm or no to cancel."), pending


def run_command(text):
    """Returns (reply, pending). pending is None unless Nova needs you to confirm."""
    text = text.strip()
    if not text:
        return "Type a command.", None

    # "type ..." is handled first, and its text is never logged
    low = text.lower()
    if low == "type" or low.startswith("type "):
        log_action("command", "type (text hidden)", "received")
        return handle_type(text)

    log_action("command", text, "received")

    reply = run_local(text)
    if reply is not None:
        return reply, None

    plan = ask_brain(text)
    action = plan.get("action")
    target = str(plan.get("target", ""))
    message = plan.get("reply", "")

    # Whitelist: refuse anything that is not on the allowed list
    if not is_allowed(action):
        log_action("blocked", f"{action} {target}", "blocked")
        return "That action isn't allowed.", None

    if action == "close":
        if target not in CLOSABLE:
            return f"I can't close {target}.", None
        extra = " This closes ALL of its windows and tabs." if target in WARN_ALL_WINDOWS else ""
        if needs_confirmation("close"):
            pending = {"kind": "close", "run": lambda: close_app(target)}
            log_action("close", f"{target} (waiting for confirmation)", "pending")
            return (f"Do you really want to close {target}?{extra} "
                    f"Type yes to confirm or no to cancel."), pending
        return close_app(target), None

    if action in SYSTEM:
        func, question = SYSTEM[action]
        if needs_confirmation(action):
            pending = {"kind": action, "run": func}
            log_action(action, "waiting for confirmation", "pending")
            return f"Do you really want to {question}? Type yes to confirm or no to cancel.", pending
        result = func()
        log_action(action, "", "done")
        return result, None

    if action in SIMPLE:
        result = SIMPLE[action]()
        log_action(action, "", "done")
        return result, None

    if action == "volume_set":
        result = set_volume(target)
        log_action(action, target, "done")
        return result, None

    if action == "folder":
        result = open_folder(target)
        log_action(action, target, "done")
        return result, None

    if action == "open":
        return open_target(target), None
    if action == "search":
        return web_search(target), None
    return message or "I'm not sure what you mean.", None