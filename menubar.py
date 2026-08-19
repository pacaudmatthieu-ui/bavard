"""Menu bar: status icon, mic picker submenu, dictation history, and the
meeting recorder flow.

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

import context as context_mod
import devices
import history
import inject
import meeting
import modes as modes_mod
from notify import notify


def create(cfg, rec, stt, hist=None, ctx=None, all_modes=None):
    """Build the menu bar controller (plain function: PyObjC reserves short
    selector names like `create` on NSObject subclasses)."""
    self = MenuBar.alloc().init()
    self.cfg = cfg
    self.rec = rec          # dictation Recorder (for stream_open / restart)
    self.stt = stt
    self.history = hist if hist is not None else history.History(cfg.get("history"))
    self.context = ctx if ctx is not None else context_mod.Context(cfg.get("context"))
    self.modes = all_modes if all_modes is not None else modes_mod.Modes(cfg.get("modes"))
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

        mode_root = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Mode de dictée", None, "")
        self.mode_menu = NSMenu.alloc().init()
        self.mode_menu.setAutoenablesItems_(False)
        self.mode_menu.setDelegate_(self)
        mode_root.setSubmenu_(self.mode_menu)
        menu.addItem_(mode_root)

        ctx_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Mon contexte…", "openContext:", "")
        ctx_item.setTarget_(self)
        ctx_item.setToolTip_(
            "Votre prénom, vos liens, votre vocabulaire — reste sur ce Mac")
        menu.addItem_(ctx_item)

        hist_root = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Historique des dictées", None, "")
        self.hist_menu = NSMenu.alloc().init()
        self.hist_menu.setAutoenablesItems_(False)
        self.hist_menu.setDelegate_(self)
        hist_root.setSubmenu_(self.hist_menu)
        menu.addItem_(hist_root)

        self.meet_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "🔴 Enregistrer une réunion", "toggleMeeting:", "")
        self.meet_item.setTarget_(self)
        menu.addItem_(self.meet_item)

        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quitter Bavard", "terminate:", "q")
        menu.addItem_(quit_item)
        self.status.setMenu_(menu)

    # ── submenus (rebuilt each time they open) ───────────────────────────────
    def menuNeedsUpdate_(self, menu):
        # == (isEqual:), not `is`: PyObjC may hand out a fresh proxy object
        # for the same underlying NSMenu
        if menu == self.hist_menu:
            self._build_history_menu(menu)
        elif menu == self.mode_menu:
            self._build_mode_menu(menu)
        else:
            self._build_mic_menu(menu)

    @objc.python_method
    def _build_mic_menu(self, menu):
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

    # ── dictation mode ───────────────────────────────────────────────────────
    @objc.python_method
    def _build_mode_menu(self, menu):
        menu.removeAllItems()
        if not self.modes.enabled:
            self._disabled_item(menu, "Modes désactivés (config.yaml)")
            return
        override = modes_mod.current_override()
        # show what automatic mode would pick right now, for the app in front
        app, title = inject.frontmost_context()
        detected = self.modes.detect(app, title)

        auto = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Automatique (ici : {self.modes.label(detected)})", "selectMode:", "")
        auto.setTarget_(self)
        auto.setRepresentedObject_(modes_mod.AUTO)
        auto.setState_(1 if override == modes_mod.AUTO else 0)
        menu.addItem_(auto)
        menu.addItem_(NSMenuItem.separatorItem())
        for key in self.modes.keys():
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                self.modes.label(key), "selectMode:", "")
            item.setTarget_(self)
            item.setRepresentedObject_(key)
            item.setState_(1 if override == key else 0)
            menu.addItem_(item)

    def selectMode_(self, sender):
        key = sender.representedObject()
        modes_mod.save_override(key)
        name = "automatique" if key == modes_mod.AUTO else self.modes.label(key)
        print(f"Mode : {name}")

    def openContext_(self, sender):
        """Open contexte.md in TextEdit (-t forces a plain text editor rather
        than whatever happens to own .md on this Mac)."""
        self.context.ensure_file()
        if os.path.exists(self.context.path):
            subprocess.run(["open", "-t", self.context.path])
        else:
            notify("Le fichier de contexte n'a pas pu être créé.")

    # ── dictation history ────────────────────────────────────────────────────
    @objc.python_method
    def _build_history_menu(self, menu):
        menu.removeAllItems()
        entries = self.history.recent() if self.history.enabled else []
        if not self.history.enabled:
            self._disabled_item(menu, "Historique désactivé (config.yaml)")
            return
        if not entries:
            self._disabled_item(menu, "Aucune dictée enregistrée")
        for e in entries:
            mark = "" if e.get("state") == "ok" else "⚠️ "
            when = datetime.datetime.fromtimestamp(e["at"]).strftime("%H:%M")
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                f"{mark}{when}  {history.preview(e['text'])}", "replayEntry:", "")
            item.setTarget_(self)
            item.setRepresentedObject_(e["id"])
            item.setToolTip_(e["text"])
            menu.addItem_(item)
        menu.addItem_(NSMenuItem.separatorItem())
        open_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Ouvrir le dossier de l'historique", "openHistory:", "")
        open_item.setTarget_(self)
        menu.addItem_(open_item)

    @objc.python_method
    def _disabled_item(self, menu, title):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
        item.setEnabled_(False)
        menu.addItem_(item)

    def replayEntry_(self, sender):
        """Re-paste a past dictation at the cursor (and leave it on the
        clipboard if there is nowhere to paste it)."""
        entry = self.history.get(sender.representedObject())
        if not entry or not entry.get("text"):
            return
        threading.Thread(
            target=self._replay, args=(entry["text"],), daemon=True).start()

    @objc.python_method
    def _replay(self, text):
        # the menu is still closing and focus has not returned to the app yet,
        # so give the pasteboard a longer settle than a normal dictation
        state, app = inject.inject(text, self.cfg["inject"], settle=0.35)
        if state == "not-pasted":
            notify("Aucun champ de texte : la dictée est dans le "
                   "presse-papiers (⌘V).")
        else:
            print(f"Dictée recollée dans {app or 'app active'}")

    def openHistory_(self, sender):
        """Reveal this month's archive in the Finder (or the folder itself)."""
        path = self.history.month_file()
        args = ["open", "-R", path] if path else ["open", self.history.dir]
        subprocess.run(args)

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
    def _notify(self, message):
        notify(message)

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
            self._notify(
                f"Réunion de {meeting.fmt_duration(duration)} — "
                "transcription et compte rendu prêts")
            print(f"Réunion prête : {folder}")
        except Exception as e:
            print(f"Traitement de la réunion échoué : {e}")
            self._notify("Le traitement de la réunion a échoué — voir les logs")
        finally:
            AppHelper.callAfter(self._reset_idle)

    @objc.python_method
    def _reset_idle(self):
        self.busy = False
        self.status.button().setTitle_("🎙️")
        self.meet_item.setEnabled_(True)
        self.meet_item.setTitle_("🔴 Enregistrer une réunion")
