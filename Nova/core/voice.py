import os
import re
import time
import queue
import threading
import traceback

# Silences a harmless Windows warning from the model downloader
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

# ---------------- Settings you can change ----------------
MODEL_NAME = "base.en"          # "tiny.en" = faster, "small.en" = more accurate but slower
SAMPLE_RATE = 16000
BLOCK_SECONDS = 0.1
CALIBRATION_BLOCKS = 3          # first 0.3 s is used to measure the background noise

WAIT_FOR_SPEECH_SECONDS = 6     # give up if you say nothing for this long
MAX_RECORD_SECONDS = 12         # never record longer than this
END_SILENCE_SECONDS = 0.9       # a pause this long means "I'm finished" (commands)
CONFIRM_SILENCE_SECONDS = 0.7   # same, for yes / no answers

MIN_THRESHOLD = 0.015           # quietest level counted as speech
MAX_THRESHOLD = 0.05            # raise this if a loud fan keeps Nova listening forever
USE_PROMPT = True               # hints Whisper toward Nova's words (set False if it repeats odd phrases)

# The panel passes this to mean "listen for yes / no". The list itself is not used.
CONFIRM_PHRASES = ["yes", "yes confirm", "no", "cancel"]

PROMPT = ("Open Notepad. Close Chrome. Search Python tutorials in Chrome. "
          "Volume up. Set volume to 40. Take a screenshot. Type hello world.")
CONFIRM_PROMPT = "Yes. No. Yes, confirm."


# ---------------- Turning what Whisper heard into a Nova command ----------------
UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}

# Words Whisper often splits or spells differently
REPLACEMENTS = [
    (r"\bnote pad\b", "notepad"),
    (r"\bscreen shot\b", "screenshot"),
    (r"\bgee mail\b|\bg mail\b", "gmail"),
    (r"\byou tube\b", "youtube"),
    (r"\bgit hub\b", "github"),
    (r"\bgoogle chrome\b", "chrome"),
    (r"\bmicrosoft edge\b", "edge"),
]

# Polite or filler words at the start, like "Hey Nova, can you ..."
LEADING = re.compile(
    r"^(?:(?:hey|hi|hello|okay|ok|yo|nova|please|can you|could you|would you|will you)\b[\s,.:;!?-]*)+",
    re.I)

YES_WORDS = {"yes", "yeah", "yep", "yup", "sure", "okay", "ok", "correct"}
NO_WORDS = {"no", "nope", "nah", "cancel", "stop", "dont", "never"}


def _strip_brackets(text):
    """Removes things like [BLANK_AUDIO] or (silence) that Whisper sometimes adds."""
    return re.sub(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*", " ", text)


def _convert_numbers(words):
    """['forty', 'five'] -> ['45']"""
    out = []
    i = 0
    while i < len(words):
        w = words[i]
        if w in TENS:
            value = TENS[w]
            if i + 1 < len(words) and words[i + 1] in UNITS and 1 <= UNITS[words[i + 1]] <= 9:
                value += UNITS[words[i + 1]]
                i += 1
            out.append(str(value))
        elif w in UNITS:
            out.append(str(UNITS[w]))
        elif w == "hundred":
            if out and out[-1] == "1":
                out[-1] = "100"
            else:
                out.append("100")
        else:
            out.append(w)
        i += 1
    return out


def normalize(text):
    """Lowercase, no punctuation, common mishearings fixed."""
    text = _strip_brackets(text).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", "", text)       # "don't" -> "dont"
    text = re.sub(r"\s+", " ", text).strip()
    for pattern, replacement in REPLACEMENTS:
        text = re.sub(pattern, replacement, text)
    words = text.split()
    if "volume" in words or "sound" in words:
        words = _convert_numbers(words)
    return " ".join(words)


def to_command(raw):
    """Turns what Whisper heard into a typed-style command for Nova's brain."""
    raw = _strip_brackets(raw).strip()

    stripped = LEADING.sub("", raw).strip()
    if stripped:                      # "hello" on its own stays a greeting
        raw = stripped

    # "type ..." keeps your capital letters and punctuation
    m = re.match(r"^\W*type\b[\s,:;.\-]*(.*)$", raw, re.I | re.S)
    if m and m.group(1).strip():
        payload = m.group(1).strip().rstrip(".").strip()
        if payload:
            return "type " + payload

    return normalize(raw)


def to_answer(raw):
    """Turns what Whisper heard into 'yes', 'yes confirm', 'no', or '' if unclear."""
    words = normalize(raw).split()
    if not words:
        return ""
    if any(w in NO_WORDS for w in words):       # "no" always wins: the safe direction
        return "no"
    if "confirm" in words or "confirmed" in words:
        return "yes confirm"
    if any(w in YES_WORDS for w in words):
        return "yes"
    return ""


# ---------------- The speech model (loaded once) ----------------
_model = None
_model_lock = threading.Lock()


def get_model():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel
            try:
                # Offline: use the copy already on your PC
                _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8",
                                      local_files_only=True)
            except Exception:
                # First time only: needs internet to download the model once
                _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
        return _model


def transcribe(audio, confirm_mode=False):
    model = get_model()
    prompt = None
    if USE_PROMPT:
        prompt = CONFIRM_PROMPT if confirm_mode else PROMPT
    segments, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=True,
                                   condition_on_previous_text=False,
                                   initial_prompt=prompt)
    parts = [s.text for s in segments if getattr(s, "no_speech_prob", 0.0) < 0.6]
    return " ".join(parts).strip()


# ---------------- Recording until you stop talking ----------------
def record_utterance(should_stop, confirm_mode=False):
    """Records from the microphone until you finish speaking.
    Returns a float32 numpy array, or None if nothing was said."""
    import sounddevice as sd

    block_size = int(SAMPLE_RATE * BLOCK_SECONDS)
    end_seconds = CONFIRM_SILENCE_SECONDS if confirm_mode else END_SILENCE_SECONDS
    end_blocks = max(1, int(round(end_seconds / BLOCK_SECONDS)))
    audio_q = queue.Queue()

    def callback(indata, frames, time_info, status):
        audio_q.put(indata[:, 0].copy())

    blocks = []
    calibration = []
    threshold = 0.03          # used only for the first fraction of a second
    started = False
    loud_run = 0
    silent_run = 0
    t0 = time.time()

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                        blocksize=block_size, callback=callback):
        while not should_stop():
            elapsed = time.time() - t0
            if elapsed > MAX_RECORD_SECONDS:
                break
            if not started and elapsed > WAIT_FOR_SPEECH_SECONDS:
                return None
            try:
                block = audio_q.get(timeout=0.3)
            except queue.Empty:
                continue

            blocks.append(block)
            level = float(np.sqrt(np.mean(block ** 2)))

            # Measure the background noise (fan etc.) from the quietest early block
            if len(calibration) < CALIBRATION_BLOCKS:
                calibration.append(level)
                if len(calibration) == CALIBRATION_BLOCKS:
                    threshold = min(MAX_THRESHOLD, max(MIN_THRESHOLD, min(calibration) * 3))
                    print(f"[voice] noise threshold: {threshold:.3f}")

            loud = level > threshold
            if not started:
                loud_run = loud_run + 1 if loud else 0
                if loud_run >= 2:
                    started = True
            else:
                silent_run = 0 if loud else silent_run + 1
                if silent_run >= end_blocks:
                    break

    if not started or not blocks:
        return None
    return np.concatenate(blocks)


# ---------------- The background thread the panel uses ----------------
class VoiceWorker(QThread):
    """Listens for ONE command in the background, fully offline (Whisper).
    Pass phrases=CONFIRM_PHRASES to listen only for a yes / no answer."""
    status = pyqtSignal(str)
    heard = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, phrases=None):
        super().__init__()
        self.phrases = phrases

    def run(self):
        confirm_mode = bool(self.phrases)
        try:
            try:
                import sounddevice  # noqa: F401
                import faster_whisper  # noqa: F401
            except ImportError:
                self.failed.emit("Voice needs: pip install faster-whisper sounddevice")
                return

            if _model is None:
                self.status.emit("Loading voice...")
                print("[voice] loading model:", MODEL_NAME)
            get_model()

            self.status.emit("Listening...")
            print("[voice] listening for:", "yes / no" if confirm_mode else "a command")
            audio = record_utterance(self.isInterruptionRequested, confirm_mode)
            if audio is None:
                print("[voice] heard nothing")
                self.failed.emit("I didn't hear anything. Click the mic and try again.")
                return

            self.status.emit("Thinking...")
            raw = transcribe(audio, confirm_mode)
            print("[voice] heard (raw):", repr(raw))
            if not raw:
                self.failed.emit("I didn't catch that. Try again.")
                return

            if confirm_mode:
                answer = to_answer(raw)
                if not answer:
                    self.failed.emit("I didn't hear yes or no. Try again.")
                    return
                print("[voice] answer:", answer)
                self.heard.emit(answer)
                return

            command = to_command(raw)
            if not command:
                self.failed.emit("I didn't catch that. Try again.")
                return
            print("[voice] command:", command)
            self.heard.emit(command)
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(f"Voice error: {type(e).__name__}: {e}")