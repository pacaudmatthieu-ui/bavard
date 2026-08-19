"""Personal context: who you are, your links, your vocabulary.

Lives OUTSIDE the repository — `~/Documents/Bavard/contexte.md` on the user's
own machine, next to the history and the meeting folders. It is never
committed, never sent anywhere; it only ever reaches the local Whisper model
and the local Ollama model.

The file is plain Markdown with four optional sections, created from a
template on first run:

    ## Qui je suis     free text, given to the cleanup model as context
    ## Raccourcis      « phrase = valeur » — literal replacements, no LLM
    ## Vocabulaire     one term per line — biases Whisper *and* the cleanup
    ## Signature       free text, appended in e-mail mode when enabled

Edits apply on the next dictation: the file's mtime is checked before each
use, so the user never has to restart the app.
"""
import os
import re
import unicodedata

DEFAULT_PATH = "~/Documents/Bavard/contexte.md"

# Whisper drifts and starts hallucinating when its initial_prompt gets long;
# the cleanup prompt costs latency. Both are capped.
_MAX_VOCAB_CHARS = 240
_MAX_ABOUT_CHARS = 500

TEMPLATE = """# Mon contexte Bavard

Ce fichier reste sur votre Mac. Il n'est jamais envoyé nulle part : il sert
uniquement à Bavard, en local, pour mieux vous comprendre et mieux écrire.
Modifiez-le quand vous voulez, c'est pris en compte à la dictée suivante.

Deux conventions dans les sections ci-dessous :

- les lignes _en italique_ sont des explications, Bavard les ignore
- les [crochets] marquent ce qui est à remplacer par vos vraies informations ;
  tant qu'une ligne contient des crochets, Bavard l'ignore aussi

Supprimez ce dont vous n'avez pas besoin, les sections vides ne gênent pas.

## Qui je suis

_Quelques phrases : prénom et nom, métier, activités. Bavard s'en sert pour
orthographier correctement ce qui vous concerne._

[Je m'appelle Prénom Nom, je suis ... ]

## Raccourcis

_Une ligne par raccourci : ce que je dis = ce qui s'écrit. Dites la phrase de
gauche pendant votre dictée, Bavard écrit celle de droite. Choisissez des
phrases bien distinctes, qui ne reviennent pas par hasard dans une phrase
normale._

mon lien youtube = [https://youtube.com/@votre-chaine]
mon adresse mail = [prenom.nom@exemple.fr]

## Vocabulaire

_Un terme par ligne : noms propres, marques, jargon métier, sigles. Ce sont
les mots que la reconnaissance vocale écorche le plus. Les lister ici suffit à
ce qu'ils soient reconnus et bien orthographiés._

[Nom de votre société]
[Votre marque]

## Signature

_Votre signature d'e-mail. Elle n'est ajoutée qu'en mode E-mail, et seulement
si vous activez modes.email_signature dans config.yaml._

[Bien à vous,]
[Prénom Nom]
"""


def _flatten(text):
    """Strip accents WITHOUT changing the string length, so offsets found in
    the flattened text still index into the original."""
    return "".join(unicodedata.normalize("NFD", ch)[0] for ch in text)


def _fold(text):
    """Lowercase, accent-free, single-spaced: for tolerant matching."""
    return re.sub(r"\s+", " ", _flatten(text)).strip().lower()


class Context:
    def __init__(self, cfg=None):
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.path = os.path.expanduser(cfg.get("path", DEFAULT_PATH))
        self.about = ""
        self.signature = ""
        self.shortcuts = {}     # folded phrase -> replacement
        self.vocabulary = []
        self._mtime = None
        if self.enabled:
            self.ensure_file()
            self.reload_if_changed()

    # ── file ─────────────────────────────────────────────────────────────────

    def ensure_file(self):
        """Create the annotated template the first time, never overwrite it."""
        if os.path.exists(self.path):
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w") as f:
                f.write(TEMPLATE)
            print(f"Contexte personnel créé : {self.path}")
        except OSError as e:
            print(f"Contexte personnel indisponible ({e}).")
            self.enabled = False

    def reload_if_changed(self):
        """Cheap mtime check before every use — edits apply without a restart."""
        if not self.enabled:
            return
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return
        if mtime != self._mtime:
            self._mtime = mtime
            try:
                with open(self.path) as f:
                    self._parse(f.read())
            except OSError as e:
                print(f"Contexte personnel illisible ({e}).")

    # ── parsing ──────────────────────────────────────────────────────────────

    def _parse(self, text):
        sections = {}
        current = None
        for line in text.splitlines():
            head = re.match(r"^#{1,3}\s+(.*)$", line)
            if head:
                current = _fold(head.group(1))
                sections[current] = []
            elif current:
                sections[current].append(line)
        self.about = " ".join(
            self._content(sections.get("qui je suis", [])))[:_MAX_ABOUT_CHARS]
        self.signature = "\n".join(
            self._content(sections.get("signature", []))).strip()
        self.shortcuts = self._parse_shortcuts(sections.get("raccourcis", []))
        self.vocabulary = self._parse_vocabulary(sections.get("vocabulaire", []))

    @staticmethod
    def _content(lines):
        """The user's own lines. Two things are not content: a hint the
        template ships (_in italics_) and a value still to be filled in
        ([in brackets])."""
        out = []
        for line in lines:
            s = line.strip()
            if not s:
                if out and out[-1]:
                    out.append("")
                continue
            if s.startswith("_") or s.endswith("_") or ("[" in s and "]" in s):
                continue
            out.append(s)
        while out and not out[-1]:
            out.pop()
        return out

    def _parse_shortcuts(self, lines):
        out = {}
        for line in self._content(lines):
            phrase, sep, value = line.partition("=")
            phrase, value = phrase.strip(), value.strip()
            if not sep or not phrase or not value or len(phrase) > 60:
                continue
            out[_fold(phrase)] = value
        return out

    def _parse_vocabulary(self, lines):
        out = []
        for line in self._content(lines):
            term = line.strip(" -•\t")
            if term and len(term) <= 60 and term not in out:
                out.append(term)
        return out

    # ── use ──────────────────────────────────────────────────────────────────

    def apply_shortcuts(self, text):
        """Literal, deterministic replacements — no LLM involved, so they work
        on short utterances too (which skip the cleanup model entirely)."""
        if not text or not self.shortcuts:
            return text
        # longest first: « mon lien youtube » must win over « mon lien »
        for phrase in sorted(self.shortcuts, key=len, reverse=True):
            value = self.shortcuts[phrase]
            # accent- and case-insensitive, tolerant of the spacing and the
            # stray commas Whisper sprinkles between words
            body = r"[\s,]+".join(re.escape(w) for w in phrase.split())
            pattern = re.compile(
                (r"\b" if phrase[:1].isalnum() else "") + body +
                (r"\b" if phrase[-1:].isalnum() else ""), re.IGNORECASE)
            pos = 0
            while True:
                # search the accent-stripped twin, splice into the original
                match = pattern.search(_flatten(text), pos)
                if not match:
                    break
                text = text[:match.start()] + value + text[match.end():]
                pos = match.start() + len(value)  # never rescan our own output
        return text

    def whisper_prompt(self):
        """Vocabulary as Whisper's initial_prompt, so proper nouns come back
        spelled right instead of phonetically mangled."""
        if not self.vocabulary:
            return None
        prompt, out = "", []
        for term in self.vocabulary:
            if len(prompt) + len(term) + 2 > _MAX_VOCAB_CHARS:
                break
            out.append(term)
            prompt = ", ".join(out)
        return prompt or None

    def llm_block(self):
        """Short context block for the cleanup prompt. Kept tight: every
        character here costs latency on every single dictation."""
        parts = []
        if self.about:
            parts.append(f"About the speaker: {self.about}")
        if self.vocabulary:
            terms = ", ".join(self.vocabulary[:20])
            parts.append(
                "Proper nouns and terms the speaker uses, to be spelled "
                f"exactly like this: {terms}")
        return "\n".join(parts)
