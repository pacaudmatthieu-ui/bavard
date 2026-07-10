"""Text injection at the cursor: clipboard + synthesized Cmd+V (Quartz CGEvent),
with a per-character Unicode keystroke fallback. Saves/restores the clipboard."""
import threading
import time

import Quartz
from AppKit import NSPasteboard, NSPasteboardTypeString

KEY_V = 9  # macOS virtual keycode for 'v'


def _set_clipboard(text):
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


def _get_clipboard():
    pb = NSPasteboard.generalPasteboard()
    return pb.stringForType_(NSPasteboardTypeString)


def _press_cmd_v():
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    down = Quartz.CGEventCreateKeyboardEvent(src, KEY_V, True)
    up = Quartz.CGEventCreateKeyboardEvent(src, KEY_V, False)
    Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def _type_unicode(text):
    """Fallback: per-character CGEvent Unicode keystrokes (no clipboard involved)."""
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    for ch in text:
        down = Quartz.CGEventCreateKeyboardEvent(src, 0, True)
        Quartz.CGEventKeyboardSetUnicodeString(down, len(ch), ch)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        up = Quartz.CGEventCreateKeyboardEvent(src, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(up, len(ch), ch)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        time.sleep(0.002)


def inject(text, cfg):
    if not text:
        return
    if cfg.get("method", "paste") == "type":
        _type_unicode(text)
        return
    old = _get_clipboard() if cfg.get("restore_clipboard", True) else None
    _set_clipboard(text)
    time.sleep(0.1)  # let the pasteboard settle
    _press_cmd_v()
    if old is not None:
        # Slow apps (Electron, browsers) may process Cmd+V well after the event
        # is posted; restoring too early makes them paste the OLD clipboard.
        # Restore in the background so the caller (and the overlay) don't wait.
        threading.Timer(1.0, _set_clipboard, args=(old,)).start()
