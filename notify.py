"""macOS notifications via osascript.

NSUserNotification silently fails from an unbundled LaunchAgent python (no real
bundle identifier), so every notification goes through osascript instead."""
import subprocess


def _escape(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def notify(message, title="Bavard", sound="Glass"):
    """Best-effort banner; never raises (a failed notification must not break
    the dictation flow)."""
    try:
        subprocess.run([
            "osascript", "-e",
            f'display notification "{_escape(message)}" '
            f'with title "{_escape(title)}" sound name "{sound}"',
        ], capture_output=True)
    except Exception:
        pass
