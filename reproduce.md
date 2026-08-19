# Installer Bavard sur votre Mac 🗣️

Bavard est une app de dictée vocale **100 % hors-ligne** pour **macOS sur Apple Silicon** (M1 à M4).
Appuyez sur `ctrl+shift` n'importe où → parlez → appuyez à nouveau → un texte propre, ponctué et structuré en paragraphes apparaît à votre curseur. Aucun cloud, aucun abonnement : tout tourne sur votre machine.

Comptez ~15 minutes, téléchargements compris (~3 Go).

Trois façons d'installer : **avec Claude Code** (recommandé, aucune connaissance technique requise), **le script automatique**, ou **à la main** (sections 1 à 7).

---

## 🚀 Installation par script (pour les utilisateurs du Terminal)

Il vous faut juste [Homebrew](https://brew.sh) (si vous ne l'avez pas :
`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`).

```bash
git clone https://github.com/pacaudmatthieu-ui/bavard.git
cd bavard
./install.sh
```

Le script installe tout (Python, Ollama + modèle, Whisper, démarrage automatique) et vous guide pour la seule étape que macOS réserve à l'humain : deux glisser-déposer dans les Réglages Système. À la fin, testez directement dans Notes avec `ctrl+shift`.

---

## ⚡ Installation automatique avec Claude Code

Si vous avez [Claude Code](https://claude.com/claude-code), copiez-collez tel quel le bloc ci-dessous dans une session, et laissez-vous guider. Claude fera tout sauf trois clics de permissions que macOS réserve à l'humain.

```text
Installe l'application de dictée vocale « Bavard » sur ce Mac, depuis
https://github.com/pacaudmatthieu-ui/bavard. C'est une app 100 % locale
(Whisper + Ollama), rien ne part dans le cloud. Suis ces étapes dans l'ordre :

1. Vérifie les prérequis : Mac Apple Silicon (uname -m doit donner arm64).
   Si Homebrew est absent, installe-le en expliquant d'abord à l'utilisateur
   que c'est le gestionnaire de logiciels standard du Mac et que son mot de
   passe de session sera demandé ; ajoute ensuite /opt/homebrew/bin au PATH
   si nécessaire. Puis installe Python 3.12 (brew install python@3.12) s'il
   est absent.
2. Installe Ollama s'il est absent (brew install ollama), démarre-le en
   service (brew services start ollama), puis télécharge le modèle de
   nettoyage : ollama pull qwen3:4b-instruct (~2,5 Go).
3. Clone le repo dans un dossier pérenne (pas un dossier temporaire),
   crée un venv Python 3.12 dedans (.venv), installe requirements.txt.
4. Pré-télécharge le modèle Whisper pour que le premier lancement soit
   instantané : dans le venv, WhisperModel('small', compute_type='int8').
5. Installe le démarrage automatique : adapte les deux chemins absolus de
   com.riadanas.whisperflow.plist au dossier d'installation et au HOME de
   l'utilisateur, copie-le dans ~/Library/LaunchAgents/ et charge-le avec
   launchctl load. Les logs vont dans ~/Library/Logs/whisperflow.log.
6. Permissions macOS (l'humain doit cliquer, tu ne peux pas le faire) :
   - Résous le vrai binaire : readlink -f .venv/bin/python
   - Ouvre le panneau : open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
     et révèle le binaire : open -R "$(readlink -f .venv/bin/python)"
   - Demande à l'utilisateur de glisser-déposer le fichier python3.12 dans
     DEUX listes de Réglages Système → Confidentialité et sécurité :
     « Surveillance de l'entrée » ET « Accessibilité » (attention : le bon
     panneau Accessibilité est DANS Confidentialité et sécurité, pas celui
     de la barre latérale), puis d'activer les deux interrupteurs.
   - Le micro sera demandé automatiquement à la première dictée.
7. Redémarre l'app (launchctl kickstart -k gui/$(id -u)/com.riadanas.whisperflow)
   et vérifie dans le log qu'il n'y a plus ni « SETUP NEEDED » ni
   « This process is not trusted ».
8. Vérifie que le micro d'entrée par défaut du système n'est PAS un casque
   Bluetooth (sinon sa musique perdrait ses basses) : propose de basculer
   sur le micro intégré si besoin.
9. Fais faire un test à l'utilisateur : curseur dans Notes, ctrl+shift,
   parler, ctrl+shift à nouveau → le texte doit se coller. En cas de souci,
   diagnostique avec tail ~/Library/Logs/whisperflow.log et la section
   « Dépannage express » du reproduce.md du repo.
```

## 💡 C'est quoi Ollama, au fait ?

**Ollama n'est pas un site ni un service en ligne** : c'est un logiciel gratuit et open source qui s'installe sur votre Mac (`brew install ollama`, ou le téléchargement sur [ollama.com](https://ollama.com)) et qui fait tourner des modèles d'IA **directement sur votre machine**.

- Une fois lancé, il tourne discrètement en arrière-plan et écoute en local sur `http://localhost:11434` — une adresse qui n'existe que sur votre ordinateur, inaccessible depuis Internet.
- `ollama pull qwen3:4b-instruct` télécharge **une seule fois** le modèle (~2,5 Go, comme un gros fichier) ; ensuite tout fonctionne sans connexion.
- Quand vous dictez, Bavard envoie le texte brut transcrit par Whisper à Ollama, qui le renvoie nettoyé (sans les « euh », avec ponctuation et paragraphes). L'aller-retour se fait en local, en une seconde environ.
- Pas de compte, pas d'abonnement, aucune donnée transmise à qui que ce soit. Si vous coupez le Wi-Fi, la dictée fonctionne toujours.

En résumé : **Whisper** (dans l'app) transforme votre voix en texte, **Ollama** (le second cerveau local) rend ce texte propre. Les deux vivent entièrement sur votre Mac.

---

## 1. Prérequis

```bash
# Homebrew, le gestionnaire de paquets macOS (sautez si déjà installé)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python 3.12 (la version utilisée par le projet)
brew install python@3.12

# Ollama : fait tourner le petit LLM local qui nettoie vos transcriptions
brew install ollama

# Démarrer Ollama en service (se relance automatiquement à chaque démarrage du Mac)
brew services start ollama

# Télécharger le LLM de nettoyage (~2,5 Go, une seule fois)
ollama pull qwen3:4b-instruct
```

## 2. Installer le projet

```bash
# Cloner le dépôt et entrer dedans
git clone https://github.com/pacaudmatthieu-ui/bavard.git
cd bavard

# Créer un environnement Python isolé dans le projet
python3.12 -m venv .venv

# L'activer
source .venv/bin/activate

# Installer les bibliothèques nécessaires
pip install -r requirements.txt
```

## 3. Premier lancement

```bash
# Le premier lancement télécharge le modèle vocal Whisper « small » (~460 Mo)
python main.py
```

L'app affiche `Bavard ready` mais **ne fonctionnera pas encore** : macOS bloque tout tant que les permissions ne sont pas accordées.

## 4. Accorder les permissions (une seule fois — lisez bien, c'est LE passage délicat)

Il faut autoriser le binaire Python du projet dans **Réglages Système → Confidentialité et sécurité**, dans **deux** listes : **Surveillance de l'entrée** (pour voir le raccourci clavier) et **Accessibilité** (pour coller le texte).

> ⚠️ **Piège n° 1** : il existe DEUX panneaux « Accessibilité » dans les Réglages Système. Le bon est **à l'intérieur de « Confidentialité et sécurité »**. Celui de la barre latérale principale (fonctions pour malvoyants) n'a rien à voir.

> ⚠️ **Piège n° 2** : le fichier à autoriser est caché dans des dossiers invisibles. Deux méthodes qui marchent :

**Méthode A — glisser-déposer (recommandée)** : dans le Terminal, tapez

```bash
open -R "$(readlink -f .venv/bin/python)"
```

Une fenêtre Finder s'ouvre avec le fichier `python3.12` sélectionné. Glissez-déposez-le directement dans chacune des deux listes des Réglages Système.

**Méthode B — le sélecteur de fichiers** : cliquez **+** dans la liste, puis dans le sélecteur appuyez sur `⌘⇧G`, collez le chemin affiché par `readlink -f .venv/bin/python`, validez par Entrée.

Dans les deux cas, vérifiez que **l'interrupteur à côté de `python3.12` est activé**, puis **relancez l'app** (`Ctrl+C` puis `python main.py`).

**Micro** : macOS demandera l'autorisation tout seul à votre première dictée — cliquez « Autoriser ».

## 5. Utilisation

Cliquez dans n'importe quel champ de texte (Notes, navigateur, mail, Slack…) :

1. Appuyez sur `ctrl+shift` → une pastille noire avec des ondes violettes apparaît (enregistrement)
2. Parlez naturellement — les « euh », « ben », « bah » seront supprimés
3. Appuyez à nouveau sur `ctrl+shift` → la pastille passe en mode « Traitement… » (roue qui tourne), puis le texte propre est collé à votre curseur

Tant que la roue tourne, ça travaille. Les textes longs sont automatiquement ponctués et découpés en paragraphes.

**La mise en forme s'adapte à l'app.** Au moment où vous appuyez sur le raccourci, Bavard regarde quelle application est devant et choisit un mode : **E-mail** (Mail, Gmail, Spark, Outlook), **Message court** (Slack, Messages, WhatsApp), **Technique** (terminal, VS Code, Cursor), **Notes** (Notes, Notion, Obsidian), **Texte standard** ailleurs. Menu 🎙️ → **Mode de dictée** montre celui qui s'appliquerait ici et permet d'en épingler un autre. Pour créer vos propres modes, un fichier `~/Documents/Bavard/modes.yaml` ; chaque mode y accepte `label`, `prompt`, `apps`, `titles`, `min_words`, `one_block`.

**Bavard peut vous connaître.** Menu 🎙️ → **Mon contexte…** ouvre `~/Documents/Bavard/contexte.md`, un fichier qui ne quitte jamais votre Mac. Quatre sections : *Qui je suis* (Bavard sait de qui vous parlez), *Raccourcis* (`mon lien youtube = https://…` — dites la phrase, l'URL s'écrit), *Vocabulaire* (vos noms propres, marques et sigles, pour que la reconnaissance vocale cesse de les écorcher), *Signature*. Les lignes _en italique_ sont des explications et les valeurs entre [crochets] sont à remplacer : tant que les crochets sont là, la ligne est ignorée. Vos modifications s'appliquent à la dictée suivante, sans redémarrer.

**Rien ne se perd.** Chaque dictée est écrite sur le disque dès que la transcription existe — avant le nettoyage, avant le collage. Si vous aviez oublié de cliquer dans un champ de texte, Bavard vous prévient par une notification, garde le texte dans le presse-papiers (un simple ⌘V le récupère) et l'archive quand même. Menu 🎙️ → **Historique des dictées** : les dernières dictées, un clic pour recoller celle qu'il vous faut, et « Ouvrir le dossier de l'historique » pour l'archive complète (`~/Documents/Bavard/historique/AAAA-MM.md`, un fichier par mois). Les dictées marquées ⚠️ sont celles qui n'ont pas atterri où vous pensiez.

> ⚠️ **Casque Bluetooth** : ne choisissez JAMAIS votre casque Bluetooth comme micro d'entrée (Réglages Système → Son → Entrée). macOS le basculerait en mode « appel » et votre musique perdrait ses basses. Utilisez le micro intégré du Mac ou un micro USB — la qualité de dictée y est d'ailleurs meilleure.

## 6. Démarrage automatique à l'ouverture de session (recommandé)

```bash
# Adapter les chemins du fichier plist à votre machine, l'installer et le charger :
sed -e "s|/Users/riadanas/Desktop/Fable 5/VoiceBud-Local-Riad|$(pwd)|g" \
    -e "s|/Users/riadanas|$HOME|g" \
    com.riadanas.whisperflow.plist > ~/Library/LaunchAgents/com.riadanas.whisperflow.plist
launchctl load ~/Library/LaunchAgents/com.riadanas.whisperflow.plist
```

Bavard démarre maintenant à chaque ouverture de session, sans terminal.

```bash
# Redémarrer l'app après un changement de config :
launchctl kickstart -k gui/$(id -u)/com.riadanas.whisperflow

# Les logs, si quelque chose cloche :
tail -f ~/Library/Logs/whisperflow.log
```

## 7. Personnaliser (`config.yaml`, puis redémarrer l'app)

| Réglage | Valeur par défaut | Options |
|---|---|---|
| `hotkey.key` | `ctrl+shift` | `alt_r`, `ctrl+alt`… (`fn` impossible sur macOS) |
| `hotkey.mode` | `toggle` (appui pour démarrer/arrêter) | `hold` (maintenir enfoncé) |
| `stt.language` | `fr` (fiabilité maximale en français) | `null` = auto-détection, `en`… |
| `stt.model` | `small` | `base` (plus rapide), `medium` (plus précis) |
| `audio.keep_open` | `false` (micro fermé au repos, pas d'icône orange) | `true` (toujours ouvert + pre-roll 500 ms) |
| `llm.model` | `qwen3:4b-instruct` | tout modèle Ollama (évitez `qwen3:4b` tout court : variante « réflexion », lente) |
| `history.enabled` | `true` (chaque dictée archivée) | `false` = aucune trace sur le disque |
| `history.keep_days` | `90` | ancienneté max du journal et des audios (`0` = illimité) ; les archives Markdown ne sont jamais purgées |
| `history.keep_audio` | `false` | `true` = garder aussi le WAV de chaque dictée, pour retranscrire un passage si le micro a coupé |
| `modes.default` | `auto` (d'après l'app active) | `standard`, `email`, `chat`, `code`, `notes`, ou une de vos clés |
| `modes.email_signature` | `false` | `true` = ajouter votre signature en mode E-mail (n'activez pas si vous dictez déjà votre formule de politesse) |
| `context.enabled` | `true` | `false` = ignorer le contexte personnel |

## Dépannage express

- **Rien ne se colle mais la transcription apparaît dans le log** → permission Accessibilité manquante ou désactivée (section 4)
- **Le raccourci ne réagit pas** → permission Surveillance de l'entrée manquante, ou l'app n'a pas été relancée après l'octroi
- **Le texte sort en anglais alors que vous parlez français** → vérifiez `stt.language: fr` dans `config.yaml`
- **Votre musique Bluetooth devient métallique** → votre casque est passé micro d'entrée ; remettez le micro du Mac (Réglages → Son → Entrée)
- **Première syllabe coupée** → commencez à parler juste après l'apparition de la pastille, ou passez `audio.keep_open: true`
- **Une dictée s'est perdue** → elle est dans l'historique : menu 🎙️ → « Historique des dictées » (clic = recollage), ou `~/Documents/Bavard/historique/`. Même un plantage en pleine dictée n'efface rien : l'entrée est récupérée au redémarrage suivant
- **Le mauvais mode s'applique** → menu 🎙️ → Mode de dictée : le premier élément indique ce que l'automatique choisirait pour l'app devant vous. Pour une app non reconnue, ajoutez son nom dans `~/Documents/Bavard/modes.yaml` (`email: {apps: [nom de l'app]}`)
- **Un raccourci du contexte ne se déclenche pas** → vérifiez que la ligne ne contient plus de [crochets], et choisissez une phrase distincte (« mon lien youtube » plutôt que « mon lien »)
- **Le micro a coupé au milieu / il manque un bout** → passez `history.keep_audio: true` dans `config.yaml` : le WAV de chaque dictée est conservé dans `historique/audio/` et peut être retranscrit

---

Basé sur [VoiceBud](https://github.com/anesriad/VoiceBud-Local-Riad) d'Anas Riad (MIT).
