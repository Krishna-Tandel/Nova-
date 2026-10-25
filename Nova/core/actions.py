import os
import subprocess
import webbrowser
from urllib.parse import quote_plus

from core.brain import ask_brain
from core.safety import log_action, is_allowed, needs_confirmation

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# App name you type -> what Windows should launch.
# To add your own app, add a line with its full path, for example:
# "spotify": r"C:\Users\Krish\AppData\Roaming\Spotify\Spotify.exe",
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
}

WEBSITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
}


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


def run_command(text):
    """Returns (reply, pending). pending is None unless Nova needs you to confirm."""
    text = text.strip()
    if not text:
        return "Type a command.", None

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

    if action in SYSTEM:
        func, question = SYSTEM[action]
        if needs_confirmation(action):
            pending = {"kind": action, "run": func}
            log_action(action, "waiting for confirmation", "pending")
            return f"Do you really want to {question}? Type yes to confirm or no to cancel.", pending
        result = func()
        log_action(action, "", "done")
        return result, None

    if action == "open":
        return open_target(target), None
    if action == "search":
        return web_search(target), None
    return message or "I'm not sure what you mean.", None