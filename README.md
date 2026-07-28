# Bavard 🗣️

Dictée vocale 100 % hors-ligne pour macOS (Apple Silicon) — parlez, il écrit.

Appuyez sur `ctrl+shift` dans n'importe quelle app → parlez → appuyez à nouveau → un texte propre, ponctué et structuré en paragraphes apparaît à votre curseur. La reconnaissance vocale tourne sur la machine (faster-whisper), le nettoyage (suppression des « euh », ponctuation, majuscules, sauts de ligne entre les idées) passe par un LLM local (Ollama). Aucun cloud, aucun abonnement, aucun audio ne quitte votre Mac.

## Fonctionnalités

- **Français d'abord** : Whisper `small` multilingue, langue forcée en français pour une fiabilité totale
- **Mise en forme automatique** : ponctuation, majuscules, et paragraphes aérés sur les textes longs
- **Suppression des tics de langage** : euh, ben, bah, hein… y compris en début de phrase
- **Commandes vocales** : dites « à la ligne », « nouveau paragraphe », « point d'interrogation », « point d'exclamation », « points de suspension », « point-virgule » ou « deux-points » pour insérer la ponctuation correspondante
- **Micro discret** : le micro ne s'ouvre que pendant la dictée (pas d'icône orange en permanence)
- **Pastille d'état** : ondes violettes pendant l'enregistrement, roue « Traitement… » pendant la transcription — vous savez toujours où ça en est
- **Collage fiable** : le presse-papiers est préservé et restauré en arrière-plan

## Installation

**Prérequis** : un Mac Apple Silicon (M1 ou plus récent). Comptez ~15 min et ~3 Go de téléchargements.

### Option A — avec Claude Code (le plus simple)

Si vous avez [Claude Code](https://claude.com/claude-code), copiez-collez tel quel le bloc ci-dessous dans une session, et laissez-vous guider. Claude fera tout sauf trois clics de permissions que macOS réserve à l'humain.

```text
Installe l'application de dictée vocale « Bavard » sur ce Mac, depuis
https://github.com/pacaudmatthieu-ui/bavard. C'est une app 100 % locale
(Whisper + Ollama), rien ne part dans le cloud. Suis ces étapes dans l'ordre :

1. Vérifie les prérequis : Mac Apple Silicon (uname -m doit donner arm64),
   Homebrew, Python 3.12 (brew install python@3.12 si absent).
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

### Option B — le script d'installation

Il vous faut [Homebrew](https://brew.sh), puis dans le Terminal :

```bash
git clone https://github.com/pacaudmatthieu-ui/bavard.git
cd bavard
./install.sh
```

Le script fait tout : Python, Ollama et son modèle, Whisper, démarrage automatique à l'ouverture de session. Il ne vous reste que deux glisser-déposer dans les Réglages Système (permissions macOS), guidés pas à pas par le script.

Installation manuelle détaillée et dépannage : voir [reproduce.md](reproduce.md).

## Personnalisation (`config.yaml`, puis redémarrer)

- `hotkey.key` : le raccourci (`ctrl+shift` par défaut)
- `stt.language` : `fr` (forcé) — remettre `null` pour l'auto-détection multilingue
- `stt.model` : `small` par défaut ; `medium` pour plus de précision, `base` pour plus de vitesse
- `audio.keep_open` : `false` = micro fermé au repos ; `true` = toujours ouvert + pre-roll
- `llm.model` : le modèle Ollama de nettoyage

## Crédits

Basé sur [VoiceBud](https://github.com/anesriad/VoiceBud-Local-Riad) d'Anas Riad (licence MIT), lui-même une alternative locale et gratuite à Wispr Flow. Adapté pour le français et enrichi avec Claude Code.
