import time
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

# Windows that belong to the desktop itself are never a typing target
SHELL_CLASSES = {
    "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW",
    "NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland",
}

last_external = None  # the last real window used before Nova


def _class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def title(hwnd):
    try:
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""


def is_valid(hwnd):
    return bool(hwnd) and bool(user32.IsWindow(hwnd))


def track(own_hwnd):
    """Called every moment by the panel. Remembers the active window if it isn't Nova."""
    global last_external
    hwnd = user32.GetForegroundWindow()
    if not hwnd or hwnd == own_hwnd:
        return
    if not user32.IsWindowVisible(hwnd):
        return
    if _class(hwnd) in SHELL_CLASSES:
        return
    if not title(hwnd):
        return
    last_external = hwnd


def focus_last():
    """Brings the remembered window to the front. Returns True if it worked."""
    hwnd = last_external
    if not is_valid(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # restore a minimised window

    user32.SetForegroundWindow(hwnd)
    for _ in range(6):
        time.sleep(0.05)
        if user32.GetForegroundWindow() == hwnd:
            return True

    # Windows sometimes refuses; borrow the active window's input thread and retry
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    my_thread = kernel32.GetCurrentThreadId()
    if fg_thread and fg_thread != my_thread:
        user32.AttachThreadInput(my_thread, fg_thread, True)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(my_thread, fg_thread, False)
    for _ in range(6):
        time.sleep(0.05)
        if user32.GetForegroundWindow() == hwnd:
            return True
    return False