"""VoiceBud: hold ctrl+alt to dictate anywhere. Fully offline.

Setup (5 lines):
  python3.12 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  Grant Terminal: Microphone, Accessibility, Input Monitoring (System Settings -> Privacy & Security)
  ollama serve   (in another terminal, if not already running)
  python main.py
"""
import threading
import time

import yaml

import context as context_mod
import history
import inject
import modes as modes_mod
from audio import Recorder
from cleanup import Cleaner
from hotkey import PushToTalk
from notify import notify
from transcribe import Transcriber

APP_NAME = "Bavard"


def check_permissions():
    """Best-effort permission probes; print one-time setup guidance if missing."""
    import Quartz
    msgs = []
    try:
        if not Quartz.CGPreflightListenEventAccess():
            msgs.append("Input Monitoring (for the global hotkey)")
    except AttributeError:
        pass
    try:
        from ApplicationServices import AXIsProcessTrusted
        if not AXIsProcessTrusted():
            msgs.append("Accessibility (to paste text into other apps)")
    except Exception:
        pass
    if msgs:
        print("SETUP NEEDED — grant your terminal these permissions in")
        print("System Settings -> Privacy & Security, then restart this app:")
        for m in msgs:
            print(f"  - {m}")
        print("  - Microphone (macOS will prompt on first recording)")


def rename_app():
    """Best-effort: show 'VoiceBud' instead of 'Python' where macOS reads the bundle name."""
    try:
        from Foundation import NSBundle, NSProcessInfo
        NSProcessInfo.processInfo().setProcessName_(APP_NAME)
        info = NSBundle.mainBundle().infoDictionary()
        if info is not None:
            info["CFBundleName"] = APP_NAME
    except Exception:
        pass


def main():
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    check_permissions()

    from AppKit import NSApplication
    from PyObjCTools import AppHelper
    from overlay import Overlay

    rename_app()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)  # accessory: no Dock icon

    print(f"Loading STT model ({cfg['stt']['model']})...")
    stt = Transcriber(cfg["stt"])
    cleaner = Cleaner(cfg["llm"])
    rec = Recorder(
        sample_rate=cfg["audio"]["sample_rate"],
        channels=cfg["audio"]["channels"],
        preroll_ms=cfg["audio"]["preroll_ms"],
        keep_open=cfg["audio"].get("keep_open", True),
    )
    rec.start_stream()
    overlay = Overlay(rec.bands)
    hist = history.History(cfg.get("history"))
    ctx = context_mod.Context(cfg.get("context"))
    all_modes = modes_mod.Modes(cfg.get("modes"))

    # menu bar: status icon, mic picker, mode picker, history, meeting recorder
    import menubar as menubar_mod
    menubar = menubar_mod.create(cfg, rec, stt, hist, ctx, all_modes)

    # the mode is decided when the hotkey goes down, while the target app still
    # has focus — by the time we paste, the user may have switched away
    pending = {}

    def on_press():
        app, title = inject.frontmost_context()
        key, detected = all_modes.resolve(
            app, title, override=modes_mod.current_override())
        pending.update(app=app, mode=key)
        ctx.reload_if_changed()  # edits to contexte.md apply without a restart
        rec.start()
        AppHelper.callAfter(overlay.show)
        print(f"[{all_modes.label(key)}{'' if detected else ' — épinglé'}] "
              f"{app or 'app inconnue'}")

    def process(audio):
        t0 = time.time()
        entry = None
        mode_key = pending.get("mode", modes_mod.DEFAULT)
        try:
            raw = stt.transcribe(audio, initial_prompt=ctx.whisper_prompt())
            if not raw:
                print("(no speech detected)")
                return
            # On disk before anything can go wrong: a failed cleanup, a missing
            # text field or a crashed paste can no longer lose the dictation.
            entry = hist.record(raw, audio=audio,
                                sample_rate=cfg["audio"]["sample_rate"])
            text = cleaner.clean(raw, mode=all_modes.spec(mode_key), context=ctx)
            state, app = inject.inject(text, cfg["inject"])
            hist.finish(entry, text=text, state=state, app=app,
                        mode=all_modes.label(mode_key))
            entry = None
            if state == "not-pasted":
                notify("Aucun champ de texte : la dictée est dans le "
                       "presse-papiers (⌘V) et dans l'historique.")
                print(f'→ "{text}"  (non collé — {app or "app inconnue"})')
            else:
                print(f'→ "{text}"  ({time.time() - t0:.2f}s, '
                      f'{all_modes.label(mode_key)})')
        except Exception as e:
            if entry is not None:
                hist.finish(entry, state="failed", error=e,
                            mode=all_modes.label(mode_key))
                entry = None
                notify("La dictée n'a pas pu être collée — elle est dans "
                       "l'historique (menu 🎙️).")
            print(f"Dictation failed: {e}")
        finally:
            if entry is not None:  # interrupted before finish()
                hist.finish(entry, state="failed",
                            mode=all_modes.label(mode_key))
            AppHelper.callAfter(overlay.hide)

    def on_release():
        audio = rec.stop()
        AppHelper.callAfter(overlay.processing)
        threading.Thread(target=process, args=(audio,), daemon=True).start()

    key = cfg["hotkey"]["key"]
    mode = cfg["hotkey"].get("mode", "hold")
    PushToTalk(key, on_press, on_release, mode=mode).start()
    action = "Press" if mode == "toggle" else "Hold"
    print(f"{APP_NAME} ready. {action} [{key}] to dictate ({mode} mode).")
    if ctx.enabled:
        print(f"Contexte personnel : {ctx.path}")
    try:
        AppHelper.runEventLoop()
    finally:
        rec.close()


if __name__ == "__main__":
    main()
