import os
import json
import time
import queue
import traceback
from PyQt6.QtCore import QThread, pyqtSignal

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTER = os.path.join(BASE_DIR, "models", "vosk-model-small-en-us-0.15")
INNER = os.path.join(OUTER, "vosk-model-small-en-us-0.15")

LISTEN_SECONDS = 8
SAMPLE_RATE = 16000

NUMBERS = {
    "zero": 0, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90, "hundred": 100,
}

# Fixed phrases. App, website, folder and close commands are added automatically.
BASE_COMMANDS = [
    "volume up", "volume down", "mute", "unmute", "louder", "quieter",
    "take a screenshot", "screenshot",
    "lock pc", "lock computer",
    "shutdown", "restart", "cancel shutdown",
    "no", "cancel", "help", "hello",
]

# The only phrases Nova listens for while it is waiting for your answer
CONFIRM_PHRASES = ["yes", "yes confirm", "no", "cancel"]


def find_model():
    """Returns the folder that really contains the model (it has 'am' and 'conf')."""
    for path in (OUTER, INNER):
        if os.path.isdir(os.path.join(path, "am")) and os.path.isdir(os.path.join(path, "conf")):
            return path
    return None


def build_commands():
    # Imported here so the files don't import each other in a loop
    from core import actions
    cmds = list(BASE_COMMANDS)
    for name in list(actions.APPS) + list(actions.WEBSITES) + list(actions.FOLDERS):
        cmds.append("open " + name)
    for name in actions.CLOSABLE:
        cmds.append("close " + name)
    for word in NUMBERS:
        cmds.append("set volume " + word)
    return list(dict.fromkeys(cmds))  # remove duplicates, keep order


def to_command(text):
    """Turns 'set volume forty' into 'set volume 40' so the brain understands it."""
    words = text.split()
    if len(words) >= 3 and words[0] == "set" and words[1] == "volume" and words[-1] in NUMBERS:
        return f"set volume {NUMBERS[words[-1]]}"
    return text


def _clean(result_json):
    text = json.loads(result_json).get("text", "").strip()
    if not text or "[unk]" in text:
        return ""
    return text


_model = None  # loaded once, then reused


class VoiceWorker(QThread):
    """Listens for ONE command in the background, fully offline.
    Pass phrases=CONFIRM_PHRASES to listen only for yes / no."""
    status = pyqtSignal(str)
    heard = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, phrases=None):
        super().__init__()
        self.phrases = phrases

    def run(self):
        global _model
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer, SetLogLevel
        except ImportError:
            self.failed.emit("Voice needs: pip install vosk sounddevice")
            return

        try:
            SetLogLevel(-1)
            if _model is None:
                path = find_model()
                if path is None:
                    self.failed.emit("Voice model not found in the models folder.")
                    return
                self.status.emit("Loading voice...")
                print("[voice] loading model:", path)
                _model = Model(path)
                print("[voice] model loaded")

            phrases = self.phrases if self.phrases else build_commands()
            grammar = json.dumps(list(phrases) + ["[unk]"])
            rec = KaldiRecognizer(_model, SAMPLE_RATE, grammar)
            audio = queue.Queue()

            def callback(indata, frames, time_info, status):
                audio.put(bytes(indata))

            self.status.emit("Listening...")
            print("[voice] listening for:", "yes / no" if self.phrases else "commands")
            deadline = time.time() + LISTEN_SECONDS

            with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=4000, dtype="int16",
                                   channels=1, callback=callback):
                while time.time() < deadline and not self.isInterruptionRequested():
                    try:
                        data = audio.get(timeout=0.3)
                    except queue.Empty:
                        continue
                    if rec.AcceptWaveform(data):
                        text = _clean(rec.Result())
                        if text:
                            print("[voice] heard:", text)
                            self.heard.emit(to_command(text))
                            return
                final = _clean(rec.FinalResult())
                if final:
                    print("[voice] heard:", final)
                    self.heard.emit(to_command(final))
                    return

            print("[voice] nothing recognised")
            self.failed.emit("I didn't catch that. Try again.")
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(f"Voice error: {type(e).__name__}: {e}")