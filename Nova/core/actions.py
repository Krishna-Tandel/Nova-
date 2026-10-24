import os
import webbrowser
from urllib.parse import quote_plus

# App name you type -> what Windows should launch.
# To add your own app, add a new line with its full path, for example:
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


def open_target(name):
    """Open an app or website by name."""
    name = name.strip()
    for filler in ("the ", "my "):
        if name.startswith(filler):
            name = name[len(filler):]

    if name in APPS:
        try:
            os.startfile(APPS[name])
            return f"Opening {name}..."
        except OSError:
            return f"I couldn't open {name}. Check its path in actions.py."

    if name in WEBSITES:
        webbrowser.open(WEBSITES[name])
        return f"Opening {name}..."

    # Looks like a web address, e.g. "open github.com"
    if "." in name and " " not in name:
        webbrowser.open(name if name.startswith("http") else "https://" + name)
        return f"Opening {name}..."

    return f"I don't know '{name}' yet. Add it to APPS in core/actions.py."


def web_search(query):
    query = query.strip()
    if not query:
        return "What should I search for?"
    webbrowser.open("https://www.google.com/search?q=" + quote_plus(query))
    return f"Searching for: {query}"


def run_command(text):
    """Takes what you typed and decides what to do. Returns a reply."""
    text = text.strip().lower()
    if not text:
        return "Type a command."

    for prefix in ("open ", "launch ", "start ", "run "):
        if text.startswith(prefix):
            return open_target(text[len(prefix):])

    for prefix in ("search for ", "search ", "google "):
        if text.startswith(prefix):
            return web_search(text[len(prefix):])

    return "I don't know that command yet. Try: open notepad"