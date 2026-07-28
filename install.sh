#!/bin/bash
# Installateur Bavard — dictée vocale 100 % locale pour macOS (Apple Silicon)
# Usage : ./install.sh   (depuis le dossier cloné du repo)
set -euo pipefail

BOLD=$(tput bold 2>/dev/null || true)
NORM=$(tput sgr0 2>/dev/null || true)
step() { echo; echo "${BOLD}==> $*${NORM}"; }
die()  { echo "❌ $*" >&2; exit 1; }

cd "$(dirname "$0")"
INSTALL_DIR=$(pwd)
PLIST_LABEL="com.riadanas.whisperflow"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

echo "${BOLD}🗣️  Installation de Bavard — parlez, il écrit${NORM}"
echo "    Dossier d'installation : $INSTALL_DIR"

# ── 1. Prérequis ─────────────────────────────────────────────────────────────
step "1/7 Vérification des prérequis"

[ "$(uname -m)" = "arm64" ] || die "Bavard nécessite un Mac Apple Silicon (M1 ou plus récent)."

if ! command -v brew >/dev/null 2>&1; then
  die "Homebrew est requis. Installez-le d'abord :
  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"
puis relancez ./install.sh"
fi
echo "✓ Mac Apple Silicon + Homebrew"

if ! command -v python3.12 >/dev/null 2>&1; then
  echo "Installation de Python 3.12…"
  brew install python@3.12
fi
echo "✓ Python 3.12"

# ── 2. Ollama + modèle de nettoyage ──────────────────────────────────────────
step "2/7 Ollama (le LLM local qui nettoie vos transcriptions)"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Installation d'Ollama…"
  brew install ollama
fi
brew services start ollama >/dev/null 2>&1 || true
echo "✓ Ollama installé et démarré en service"

# Attendre que le serveur Ollama réponde
for i in $(seq 1 30); do
  curl -s http://localhost:11434 >/dev/null 2>&1 && break
  sleep 1
done
curl -s http://localhost:11434 >/dev/null 2>&1 || die "Ollama ne répond pas sur localhost:11434. Lancez « brew services restart ollama » puis relancez ./install.sh"

if ollama list 2>/dev/null | grep -q "qwen3:4b-instruct"; then
  echo "✓ Modèle qwen3:4b-instruct déjà téléchargé"
else
  echo "Téléchargement du modèle de nettoyage (~2,5 Go, une seule fois)…"
  ollama pull qwen3:4b-instruct
fi

# ── 3. Environnement Python ──────────────────────────────────────────────────
step "3/7 Environnement Python du projet"

if [ ! -d .venv ]; then
  python3.12 -m venv .venv
fi
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt
echo "✓ Bibliothèques installées dans .venv"

# ── 4. Modèle Whisper ────────────────────────────────────────────────────────
step "4/7 Modèle vocal Whisper « small » (~460 Mo, une seule fois)"

./.venv/bin/python - <<'EOF'
from faster_whisper import WhisperModel
WhisperModel("small", compute_type="int8")
print("✓ Modèle Whisper prêt")
EOF

# ── 5. Démarrage automatique (LaunchAgent) ───────────────────────────────────
step "5/7 Démarrage automatique à l'ouverture de session"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
sed -e "s|/Users/riadanas/Desktop/Fable 5/VoiceBud-Local-Riad|$INSTALL_DIR|g" \
    -e "s|/Users/riadanas|$HOME|g" \
    "$PLIST_LABEL.plist" > "$PLIST_DEST"
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"
echo "✓ Bavard démarrera automatiquement à chaque ouverture de session"
echo "  (logs : ~/Library/Logs/whisperflow.log)"

# ── 6. Permissions macOS ─────────────────────────────────────────────────────
step "6/7 Permissions macOS — la seule étape manuelle (2 glisser-déposer)"

PYBIN=$(readlink -f .venv/bin/python)
cat <<EOF

macOS exige votre accord pour deux choses :
  • « Surveillance de l'entrée »  → détecter le raccourci ctrl+shift
  • « Accessibilité »             → coller le texte à votre curseur

Je vais ouvrir :
  1. une fenêtre Finder avec le fichier « python3.12 » sélectionné
  2. les Réglages Système, panneau « Confidentialité et sécurité »

À vous de jouer : glissez-déposez ce fichier python3.12 dans les DEUX listes
« Surveillance de l'entrée » ET « Accessibilité », et activez les interrupteurs.

⚠️  Le bon panneau « Accessibilité » est DANS « Confidentialité et sécurité »,
    pas celui de la barre latérale (fonctions pour malvoyants).

EOF
open -R "$PYBIN"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
read -r -p "Appuyez sur Entrée une fois les DEUX permissions accordées… "

# ── 7. Redémarrage et fin ────────────────────────────────────────────────────
step "7/7 Redémarrage de Bavard"

launchctl kickstart -k "gui/$(id -u)/$PLIST_LABEL"
sleep 2

cat <<EOF

${BOLD}🎉 Installation terminée !${NORM}

Pour tester : cliquez dans Notes (ou n'importe quel champ de texte), appuyez
sur ${BOLD}ctrl+shift${NORM}, parlez, appuyez à nouveau sur ${BOLD}ctrl+shift${NORM} → le texte
propre et ponctué se colle à votre curseur. Le micro sera demandé par macOS
à la première dictée : cliquez « Autoriser ».

⚠️  Micro : n'utilisez PAS un casque Bluetooth comme entrée (Réglages → Son),
    sinon votre musique perdra ses basses. Micro intégré ou USB.

En cas de souci :
  tail -20 ~/Library/Logs/whisperflow.log
  (et la section « Dépannage express » de reproduce.md)

Personnalisation (raccourci, langue, modèles) : config.yaml, puis
  launchctl kickstart -k gui/\$(id -u)/$PLIST_LABEL
EOF
