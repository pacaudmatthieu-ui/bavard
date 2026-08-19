"""Text injection at the cursor: clipboard + synthesized Cmd+V (Quartz CGEvent),
with a per-character Unicode keystroke fallback. Saves/restores the clipboard.

Before pasting, the Accessibility API is asked whether the frontmost app really
has a text field focused. When it does not (the classic « j'ai oublié de
cliquer dans le document »), the paste is still attempted — detection is only a
hint — but the text is *left on the clipboard* instead of being restored, so a
plain Cmd+V recovers it. The caller is told, and logs it in the history.
"""
import threading
import time

import Quartz
from AppKit import NSPasteboard, NSPasteboardTypeString, NSWorkspace

KEY_V = 9  # macOS virtual keycode for 'v'

# AX roles that accept typed text. Real apps are inconsistent (Word, Mail and
# Electron editors each report something different), so the role check is only
# the first of several signals — see _has_text_target.
_TEXT_ROLES = {
    "AXTextField", "AXTextArea", "AXComboBox", "AXSearchField", "AXWebArea",
}


def _set_clipboard(text):
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


def _get_clipboard():
    pb = NSPasteboard.generalPasteboard()
    return pb.stringForType_(NSPasteboardTypeString)


def frontmost_app():
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return app.localizedName() if app is not None else None
    except Exception:
        return None


def frontmost_context():
    """-> (app_name, focused_window_title).

    The window title is what tells Gmail or Outlook apart from any other tab
    when the frontmost app is just « Google Chrome ». Empty when the
    Accessibility permission is missing — detection then falls back to the app
    name alone."""
    app = frontmost_app()
    try:
        from ApplicationServices import (
            AXIsProcessTrusted,
            AXUIElementCopyAttributeValue,
            AXUIElementCreateApplication,
        )
        if not AXIsProcessTrusted():
            return app, ""
        running = NSWorkspace.sharedWorkspace().frontmostApplication()
        if running is None:
            return app, ""
        element = AXUIElementCreateApplication(running.processIdentifier())
        err, window = AXUIElementCopyAttributeValue(element, "AXFocusedWindow", None)
        if err != 0 or window is None:
            return app, ""
        err, title = AXUIElementCopyAttributeValue(window, "AXTitle", None)
        return app, str(title) if err == 0 and title else ""
    except Exception:
        return app, ""


def _has_text_target():
    """True if the focused element looks like it can receive text.

    Returns True when unsure: a false « no target » warning is worse than a
    missing one, since the paste is attempted either way."""
    try:
        from ApplicationServices import (
            AXIsProcessTrusted,
            AXUIElementCopyAttributeValue,
            AXUIElementCreateSystemWide,
            AXUIElementIsAttributeSettable,
        )
    except ImportError:
        return True
    if not AXIsProcessTrusted():
        # Without the Accessibility permission every AX query fails; that says
        # nothing about the focused app, so don't cry wolf on every dictation
        # (main.py already prints the SETUP NEEDED guidance at startup).
        return True
    try:
        system = AXUIElementCreateSystemWide()
        err, focused = AXUIElementCopyAttributeValue(
            system, "AXFocusedUIElement", None)
        if err != 0 or focused is None:
            return False  # nothing at all has keyboard focus
        err, role = AXUIElementCopyAttributeValue(focused, "AXRole", None)
        if err == 0 and role in _TEXT_ROLES:
            return True
        # role says no, but many editors expose an editable value or a
        # selection range instead — either one means text will land somewhere
        err, settable = AXUIElementIsAttributeSettable(focused, "AXValue", None)
        if err == 0 and settable:
            return True
        err, _ = AXUIElementCopyAttributeValue(focused, "AXSelectedTextRange", None)
        return err == 0
    except Exception:
        return True


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


def inject(text, cfg, settle=0.1):
    """-> (state, app_name) with state "ok" | "not-pasted".

    "not-pasted" means no text field was focused: the text stayed on the
    clipboard and the caller should tell the user."""
    if not text:
        return "ok", None
    app = frontmost_app()
    if cfg.get("method", "paste") == "type":
        if not _has_text_target():
            _set_clipboard(text)  # nowhere to type it — leave it recoverable
            return "not-pasted", app
        _type_unicode(text)
        return "ok", app
    targeted = _has_text_target()
    old = _get_clipboard() if cfg.get("restore_clipboard", True) else None
    _set_clipboard(text)
    time.sleep(settle)  # let the pasteboard settle
    _press_cmd_v()
    if not targeted:
        # Nothing focused to receive the paste: keep the dictation on the
        # clipboard so a manual Cmd+V still recovers it.
        return "not-pasted", app
    if old is not None:
        # Slow apps (Electron, browsers) may process Cmd+V well after the event
        # is posted; restoring too early makes them paste the OLD clipboard.
        # Restore in the background so the caller (and the overlay) don't wait.
        threading.Timer(1.0, _set_clipboard, args=(old,)).start()
    return "ok", app
