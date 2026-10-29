# Nova: an offline voice and text assistant for Windows

Nova controls a Windows PC from a small panel that hides at the edge of the screen.
You type or speak a command, such as "open notepad", "volume up" or "close chrome",
and Nova does it. Everything runs **offline on your own PC**: no cloud AI, no API key, no cost.

Author: Krishna Tandel

## Features

- **Slide-out panel** that hides at the right screen edge and springs out when you hover over it
- **Voice commands**, fully offline, using OpenAI's Whisper model (through `faster-whisper`)
- **Plain sentences**: "I want to write something" opens Notepad; small typing mistakes are fixed automatically
- **Open and close** apps, websites and folders
- **Type text** into the window you were last using
- **Web search** in Chrome or Edge
- **Volume control**, **screenshots**, **lock**, **shutdown** and **restart**
- **Safety layer**: allowed-actions list, confirmation for risky actions, action log, emergency stop
- **Animated interface**: spring slide-in, pulsing mic, typing bubble, colour changes for each state

## How it works

```
You type or speak
      |  (speech is turned into text by Whisper, offline)
      v
Panel (ui/panel.py)  ->  Actions (core/actions.py)  ->  Brain (core/brain.py)
                                                          decides what you mean
      v
Safety layer (core/safety.py): is this action allowed? does it need confirmation? log it
      v
The action runs (open, close, type, search, volume, screenshot, lock ...)
      v
Reply appears in the chat panel
```

| File | Job |
|---|---|
| `main.py` | Starts Nova: tray icon, global hotkeys, panel |
| `ui/panel.py` | The panel: animations, chat, mic button, yes/no confirmation |
| `core/brain.py` | Understands sentences with keywords and fuzzy matching (rule-based, no AI model) |
| `core/actions.py` | Does the actual work: opens, closes, types, searches, volume, screenshots |
| `core/safety.py` | Allowed-actions list, which actions need confirmation, the log |
| `core/voice.py` | Offline speech recognition: records until you stop talking, then Whisper |
| `core/winfocus.py` | Remembers your last window so "type ..." knows where to type |

## Commands

| You say or type | What happens |
|---|---|
| `open notepad` / `open chrome` / `open spotify` | Opens the app |
| `open youtube` / `open github` / `open gmail` | Opens the website in Chrome |
| `open downloads` / `open documents folder` | Opens the folder |
| `I want to write something` | Opens Notepad (plain sentences work) |
| `close notepad` | Asks for confirmation, then closes it |
| `type hello world` | Asks for confirmation, then types it into your last window |
| `search python tutorials in chrome` | Google search in Chrome |
| `volume up` / `volume down` / `mute` / `set volume 40` | Changes the volume |
| `take a screenshot` | Saves a picture to `Pictures\Nova Screenshots` |
| `lock pc` | Locks the computer |
| `shutdown` / `restart` | Asks for confirmation, then a 10 second countdown. `cancel shutdown` stops it |
| `what is the time` / `hello` / `help` | Small talk and help |

## Hotkeys

| Keys | Action |
|---|---|
| `Ctrl + Space` | Show or hide the panel |
| `Ctrl + Alt + Space` | Start listening (voice) |
| `Ctrl + Alt + Q` | Emergency stop: closes Nova instantly |
| `Esc` | Hide the panel |

Left-click the tray icon to show or hide the panel. Right-click it for Show and Quit.

## Safety

- Nova only runs actions on an **allowed list**. Anything else is blocked and logged.
- `close`, `type`, `shutdown` and `restart` always **ask for confirmation**.
- By voice, `shutdown` and `restart` need the longer phrase **"yes confirm"**, so a misheard word cannot shut the PC down.
- Hiding the panel cancels a question that is waiting for an answer.
- Every action is written to `data/log.txt`. Text you ask Nova to type is **never** logged, only its length.
- Nova refuses to close `explorer.exe` (your taskbar) and Python itself.
- Apps are closed politely, so they can still ask you to save your work.

## Setup (Windows)

1. Install Python 3.12 (this project was developed and tested on 3.12).
2. Open a terminal in the project folder and create a virtual environment:
   ```
   py -3.12 -m venv venv
   venv\Scripts\activate
   ```
3. Install the libraries:
   ```
   pip install -r requirements.txt
   ```
4. Run Nova:
   ```
   python main.py
   ```
5. The first time you use voice, the Whisper model (about 145 MB) downloads once, so you need internet for that one step. After that, voice works with no internet.

If the hotkeys do nothing, run the terminal as Administrator.

## Folder structure

```
Nova/
├── main.py
├── requirements.txt
├── README.md
├── assets/
│   └── icon.png
├── core/
│   ├── __init__.py
│   ├── actions.py
│   ├── brain.py
│   ├── safety.py
│   ├── voice.py
│   └── winfocus.py
├── data/
│   └── log.txt          (created automatically)
└── ui/
    ├── __init__.py
    └── panel.py
```

## Demo script (about 5 minutes)

1. Run `python main.py`. Only a thin strip is visible at the right edge. *"Nova stays out of the way until it is needed."*
2. Hover the strip. The panel springs out.
3. Click the **Notepad** quick button. Notepad opens.
4. Type `I want to write something`. Nova understands a plain sentence.
5. Click inside Notepad, then use Nova to type `type hello everyone` and confirm. The text appears in Notepad.
6. Type `volume up`, `set volume 40`, then `take a screenshot`.
7. Type `search python tutorials in chrome`.
8. Click the mic and say "open calculator". Then say "close calculator" and answer "yes".
9. Safety: type `shutdown`, then answer `no`. Nova says "Cancelled. Nothing was changed."
10. Open `data/log.txt` to show that every action is recorded. Finish with `Ctrl + Alt + Q`.

If voice mishears in a noisy room, say "I'll type it instead" and use the keyboard. Every command works by typing.

## Limitations and future work

- Voice accuracy depends on the microphone and background noise. A headset helps a lot.
- The brain is rule-based (keywords and fuzzy matching), so it only understands phrases it was taught.
- Windows only.
- Future ideas: a local language model (for example through Ollama) for free-form understanding, multi-step commands, a settings screen, and packaging as a single `.exe`.

## Tech stack

Python 3.12, PyQt6 (interface and animations), faster-whisper / Whisper (offline speech to text),
sounddevice (microphone), keyboard (global hotkeys), Pillow (screenshots), and the Windows API through `ctypes`.
