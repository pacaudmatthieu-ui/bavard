"""Menu bar: status icon, mic picker submenu, and the meeting recorder flow.

Icon states: 🎙️ idle · 🔴 recording a meeting · ⏳ transcribing / writing the
compte rendu. All AppKit calls happen on the main thread (AppHelper.callAfter
from worker threads)."""
import datetime
import os
import subprocess
import threading

from AppKit import NSMenu, NSMenuItem, NSStatusBar, NSTimer
import objc
from Foundation import NSObject
from PyObjCTools import AppHelper

import devices
import meeting


def create(cfg, rec, stt):
    """Build the menu bar controller (plain function: PyObjC reserves short
    selector names like `create` on NSObject subclasses)."""
    self = MenuBar.alloc().init()
    self.cfg = cfg
    self.rec = rec          # dictation Recorder (for stream_open / restart)
    self.stt = stt
    self.meeting = meeting.MeetingRecorder(cfg["audio"]["sample_rate"])
    self.busy = False       # transcription / summary in progress
    self.folder = None
    self._timer = None
    self._build()
    return self


class MenuBar(NSObject):
    # ── menu construction ────────────────────────────────────────────────────
    @objc.python_method
    def _build(self):
        self.status = NSStatusBar.systemStatusBar().statusItemWithLength_(-1)
        self.status.button().setTitle_("🎙️")
        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)

        hint = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Bavard — {self.cfg['hotkey']['key']} pour dicter", None, "")
        hint.setEnabled_(False)
        menu.addItem_(hint)
        menu.addItem_(NSMenuItem.separatorItem())

        mic_root = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Micro", None, "")
        self.mic_menu = NSMenu.alloc().init()
        self.mic_menu.setAutoenablesItems_(False)
        self.mic_menu.setDelegate_(self)
        mic_root.setSubmenu_(self.mic_menu)
        menu.addItem_(mic_root)

        self.meet_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "🔴 Enregistrer une réunion", "toggleMeeting:", "")
        self.meet_item.setTarget_(self)
        menu.addItem_(self.meet_item)

        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quitter Bavard", "terminate:", "q")
        menu.addItem_(quit_item)
        self.status.setMenu_(menu)

    # ── mic picker (rebuilt each time the submenu opens) ─────────────────────
    def menuNeedsUpdate_(self, menu):
        # rescanning hardware kills open streams, so only when everything is idle
        devices.refresh(safe=not (self.rec.stream_open or self.meeting.active))
        menu.removeAllItems()
        choice = devices.current_choice()
        _, active_name, _ = devices.resolve_input_device()

        auto = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Automatique (micro du Mac)", "selectMic:", "")
        auto.setTarget_(self)
        auto.setState_(1 if choice is None else 0)
        menu.addItem_(auto)
        menu.addItem_(NSMenuItem.separatorItem())
        for d in devices.list_input_devices():
            title = d["name"] + ("  ← actif" if d["name"] == active_name else "")
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, "selectMic:", "")
            item.setTarget_(self)
            item.setRepresentedObject_(d["name"])
            item.setState_(1 if d["name"] == choice else 0)
            menu.addItem_(item)

    def selectMic_(self, sender):
        name = sender.representedObject()  # None for "Automatique"
        devices.save_choice(name)
        self.rec.restart_stream()  # applies immediately in keep_open mode
        print(f"Micro : {name or 'automatique (micro du Mac)'}")

    # ── meeting flow ─────────────────────────────────────────────────────────
    def toggleMeeting_(self, sender):
        if self.meeting.active:
            self._stop_meeting()
        elif not self.busy:
            self._start_meeting()

    @objc.python_method
    def _start_meeting(self):
        root = os.path.expanduser(
            self.cfg.get("meeting", {}).get("output_dir", "~/Documents/Bavard"))
        now = datetime.datetime.now()
        self.folder = os.path.join(root, f"Réunion {now:%Y-%m-%d %Hh%M}")
        os.makedirs(self.folder, exist_ok=True)
        try:
            self.meeting.start(os.path.join(self.folder, "audio.wav"))
        except Exception as e:
            print(f"Impossible de démarrer l'enregistrement : {e}")
            return
        self.status.button().setTitle_("🔴")
        self._timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            1.0, True, self._tick)
        self._tick(None)

    @objc.python_method
    def _tick(self, _timer):
        s = int(self.meeting.elapsed())
        clock = (f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600
                 else f"{s // 60:02d}:{s % 60:02d}")
        self.meet_item.setTitle_(
            f"⏹ Terminer l'enregistrement — {clock} ({self.meeting.mic_name})")

    @objc.python_method
    def _stop_meeting(self):
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        duration = self.meeting.stop()
        self.busy = True
        self.status.button().setTitle_("⏳")
        self.meet_item.setEnabled_(False)
        self.meet_item.setTitle_("Transcription en cours…")
        threading.Thread(
            target=self._process, args=(self.folder, duration), daemon=True,
        ).start()

    @objc.python_method
    def _set_step(self, text):
        AppHelper.callAfter(self.meet_item.setTitle_, text)

    @objc.python_method
    def _process(self, folder, duration):
        now = datetime.datetime.now()
        date_str = f"{now:%d/%m/%Y}"
        try:
            wav = os.path.join(folder, "audio.wav")
            timestamped, plain = self.stt.transcribe_file(
                wav,
                on_progress=lambda f: self._set_step(
                    f"Transcription en cours… {int(f * 100)} %"),
            )
            header = (f"# Réunion du {date_str}\n\n"
                      f"Durée : {meeting.fmt_duration(duration)} — "
                      f"micro : {self.meeting.mic_name}\n\n")
            with open(os.path.join(folder, "transcription.md"), "w") as f:
                f.write(header + (timestamped or "_(aucune parole détectée)_") + "\n")
            if plain:
                self._set_step("Rédaction du compte rendu…")
                try:
                    report = meeting.write_summary(
                        self.cfg["llm"], plain, date_str, duration,
                        on_progress=lambda i, n: self._set_step(
                            f"Rédaction du compte rendu… partie {i}/{n}"),
                    )
                    with open(os.path.join(folder, "compte-rendu.md"), "w") as f:
                        f.write(report + "\n")
                except Exception as e:
                    print(f"Compte rendu impossible ({e}) — transcription conservée.")
            if not self.cfg.get("meeting", {}).get("keep_audio", True):
                os.remove(wav)
            subprocess.run(["open", folder])
            print(f"Réunion prête : {folder}")
        except Exception as e:
            print(f"Traitement de la réunion échoué : {e}")
        finally:
            AppHelper.callAfter(self._reset_idle)

    @objc.python_method
    def _reset_idle(self):
        self.busy = False
        self.status.button().setTitle_("🎙️")
        self.meet_item.setEnabled_(True)
        self.meet_item.setTitle_("🔴 Enregistrer une réunion")
