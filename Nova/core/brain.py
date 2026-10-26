import re
import difflib
from datetime import datetime

# Words in a sentence -> which app or website to open.
# The names on the left must match the keys in APPS / WEBSITES (actions.py).
KEYWORDS = {
    "notepad": ["write", "writing", "note", "notes", "text editor", "jot"],
    "calculator": ["calculate", "calculation", "math", "maths", "add numbers"],
    "paint": ["draw", "drawing", "sketch", "paint"],
    "file explorer": ["files", "explorer"],
    "task manager": ["task manager", "processes", "running programs"],
    "settings": ["settings", "wifi settings", "display settings"],
    "chrome": ["browser", "browse", "internet", "web browser"],
    "youtube": ["video", "videos", "watch", "youtube"],
    "gmail": ["email", "mail", "inbox", "gmail"],
    "github": ["github", "repository", "repo", "my code"],
    "cmd": ["terminal", "command line", "cmd"],
    "spotify": ["music", "song", "songs", "spotify"],
}

OPEN_WORDS = ["open", "launch", "start", "run"]

FILLER = {"the", "my", "a", "an", "please", "app", "application", "program",
          "for", "me", "to", "can", "you", "could", "up"}

SEARCH_KEEP = ("what is", "what are", "who is", "who was", "how to", "how do",
               "how does", "why is", "why do", "where is", "when is")
SEARCH_STRIP = ("look up ", "lookup ", "find out ", "find ", "tell me about ")

PC_WORDS = {"pc", "computer", "laptop", "system"}

FOLDER_WORDS = ("downloads", "documents", "desktop", "pictures", "music", "videos")
UP_WORDS = {"up", "increase", "raise", "louder", "higher"}
DOWN_WORDS = {"down", "decrease", "lower", "reduce", "quieter", "softer"}


def _clean(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s\.]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _known_names():
    # Imported here so the two files don't import each other in a loop
    from core import actions
    return list(actions.APPS.keys()) + list(actions.WEBSITES.keys())


def _open(name):
    return {"action": "open", "target": name, "reply": f"Opening {name}..."}


def _search(query):
    return {"action": "search", "target": query, "reply": f"Searching for: {query}"}


def _chat(reply):
    return {"action": "chat", "reply": reply}


def _system(action, target=""):
    return {"action": action, "target": target, "reply": ""}


def ask_brain(text):
    """Works out what you mean, on your PC. Free, no internet or API needed."""
    t = _clean(text)
    words = t.split()
    if not words:
        return _chat("Type a command.")

    # ---------- Small talk ----------
    if words[0] in ("hi", "hello", "hey", "yo"):
        return _chat("Hello! Try: open notepad")
    if "thanks" in words or "thank" in words:
        return _chat("You're welcome!")
    if "who are you" in t or "your name" in t:
        return _chat("I'm Nova, your personal PC agent.")
    if "time" in words and ("what" in words or "tell" in words or len(words) == 1):
        return _chat("It's " + datetime.now().strftime("%I:%M %p"))
    if ("date" in words or "today" in words) and ("what" in words or "tell" in words or len(words) == 1):
        return _chat("Today is " + datetime.now().strftime("%A, %d %B %Y"))
    if t == "help" or "what can you do" in t:
        return _chat("Try: open notepad, close notepad, type hello world, search python, "
                     "volume up, set volume 40, mute, screenshot, open downloads folder, "
                     "lock pc, shutdown.")

    # ---------- Close an app ----------
    m = re.match(r"^(close|quit|exit)\s+(.+)$", t)
    if m:
        from core import actions
        names = list(actions.CLOSABLE)
        rest = [w for w in m.group(2).split() if w not in FILLER]
        target = " ".join(rest)
        if target in names:
            return _system("close", target)
        close = difflib.get_close_matches(target, names, n=1, cutoff=0.7)
        if close:
            return _system("close", close[0])
        return _chat("I can only close: " + ", ".join(names) + ".")

    # ---------- Web search ----------
    for prefix in SEARCH_STRIP:
        if t.startswith(prefix):
            return _search(t[len(prefix):])
    if t.startswith(SEARCH_KEEP):
        return _search(t)

    # ---------- Screenshot ----------
    if re.search(r"screen\s?shot|capture (the )?screen|screen capture", t):
        return _system("screenshot")

    # ---------- Volume ----------
    if re.search(r"\b(mute|unmute)\b", t):
        return _system("volume_mute")
    vol = re.search(r"\b(volume|sound)\b\D*(\d{1,3})\b", t)
    if vol:
        return _system("volume_set", vol.group(2))
    wordset = set(words)
    if ({"volume", "sound"} & wordset) or ({"louder", "quieter"} & wordset):
        if UP_WORDS & wordset:
            return _system("volume_up")
        if DOWN_WORDS & wordset:
            return _system("volume_down")

    # ---------- System commands ----------
    has_pc = bool(PC_WORDS & wordset)
    if re.search(r"\b(cancel|abort)\b", t) and re.search(r"\b(shutdown|shut down|restart|reboot)\b", t):
        return _system("cancel_shutdown")
    if re.search(r"\b(shutdown|shut down)\b", t) or (has_pc and re.search(r"\b(turn off|power off)\b", t)):
        return _system("shutdown")
    if re.search(r"\b(restart|reboot)\b", t):
        return _system("restart")
    if "lock" in words and (has_pc or "screen" in words or len(words) == 1):
        return _system("lock")

    names = _known_names()
    is_open = bool(difflib.get_close_matches(words[0], OPEN_WORDS, n=1, cutoff=0.7))

    # ---------- Open a folder ----------
    for folder in FOLDER_WORDS:
        if folder in words:
            said_folder = "folder" in words or "folders" in words
            simple = is_open and folder in ("downloads", "documents", "desktop")
            if said_folder or simple:
                return _system("folder", folder)

    # ---------- Open an app ----------
    if is_open:
        rest = [w for w in words[1:] if w not in FILLER]
        target = " ".join(rest)
        if target in names:
            return _open(target)
        close = difflib.get_close_matches(target, names, n=1, cutoff=0.75)
        if close:
            return _open(close[0])

    # Keywords anywhere in the sentence, like "I want to write something"
    for name, kws in KEYWORDS.items():
        for kw in kws:
            if re.search(r"\b" + re.escape(kw) + r"\b", t):
                return _open(name)

    # Typos in a single word, like "open notepd"
    if is_open:
        for w in words[1:]:
            if len(w) >= 5:
                close = difflib.get_close_matches(w, names, n=1, cutoff=0.8)
                if close:
                    return _open(close[0])

    return _chat("I'm not sure what you mean. Try: open notepad, or type help.")