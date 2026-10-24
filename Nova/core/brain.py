import re
import difflib
from datetime import datetime

# Words in a sentence -> which app or website to open.
# The names on the left must match the keys in APPS / WEBSITES (actions.py).
# Add your own words here any time.
KEYWORDS = {
    "notepad": ["write", "writing", "note", "notes", "text editor", "jot", "type something"],
    "calculator": ["calculate", "calculation", "math", "maths", "add numbers"],
    "paint": ["draw", "drawing", "sketch", "paint"],
    "file explorer": ["files", "folder", "folders", "documents", "explorer"],
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

# Words ignored when working out which app you mean
FILLER = {"the", "my", "a", "an", "please", "app", "application", "program",
          "for", "me", "to", "can", "you", "could", "up"}

# Questions that become a web search (the whole sentence is searched)
SEARCH_KEEP = ("what is", "what are", "who is", "who was", "how to", "how do",
               "how does", "why is", "why do", "where is", "when is")
# Phrases that are removed first, and the rest is searched
SEARCH_STRIP = ("look up ", "lookup ", "find out ", "find ", "tell me about ")


def _clean(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s\.]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _known_names():
    # Imported here (not at the top) so the two files don't import each other in a loop
    from core import actions
    return list(actions.APPS.keys()) + list(actions.WEBSITES.keys())


def _open(name):
    return {"action": "open", "target": name, "reply": f"Opening {name}..."}


def _search(query):
    return {"action": "search", "target": query, "reply": f"Searching for: {query}"}


def _chat(reply):
    return {"action": "chat", "reply": reply}


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
        return _chat("Try: open notepad, search python, or say what you want, like 'I want to write something'.")

    # ---------- Web search ----------
    for prefix in SEARCH_STRIP:
        if t.startswith(prefix):
            return _search(t[len(prefix):])
    if t.startswith(SEARCH_KEEP):
        return _search(t)

    # ---------- Open an app ----------
    names = _known_names()
    is_open = bool(difflib.get_close_matches(words[0], OPEN_WORDS, n=1, cutoff=0.7))

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

    # Typos in a single word, like "open notepd" (only when the user said open)
    if is_open:
        for w in words[1:]:
            if len(w) >= 5:
                close = difflib.get_close_matches(w, names, n=1, cutoff=0.8)
                if close:
                    return _open(close[0])

    return _chat("I'm not sure what you mean. Try: open notepad, or type help.")