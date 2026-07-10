# Plume Vocale 🪶

Dictée vocale 100 % hors-ligne pour macOS (Apple Silicon) — votre voix devient une plume.

Appuyez sur `ctrl+shift` dans n'importe quelle app → parlez → appuyez à nouveau → un texte propre, ponctué et structuré en paragraphes apparaît à votre curseur. La reconnaissance vocale tourne sur la machine (faster-whisper), le nettoyage (suppression des « euh », ponctuation, majuscules, sauts de ligne entre les idées) passe par un LLM local (Ollama). Aucun cloud, aucun abonnement, aucun audio ne quitte votre Mac.

## Fonctionnalités

- **Français d'abord** : Whisper `small` multilingue, langue forcée en français pour une fiabilité totale
- **Mise en forme automatique** : ponctuation, majuscules, et paragraphes aérés sur les textes longs
- **Suppression des tics de langage** : euh, ben, bah, hein… y compris en début de phrase
- **Micro discret** : le micro ne s'ouvre que pendant la dictée (pas d'icône orange en permanence)
- **Pastille d'état** : ondes violettes pendant l'enregistrement, roue « Traitement… » pendant la transcription — vous savez toujours où ça en est
- **Collage fiable** : le presse-papiers est préservé et restauré en arrière-plan

## Installation

Suivre [reproduce.md](reproduce.md) (~10 minutes). L'essentiel :

```bash
brew install python@3.12 ollama
brew services start ollama
ollama pull qwen3:4b-instruct
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Puis accorder les permissions macOS (Surveillance de l'entrée, Accessibilité, Micro) au binaire Python du venv — voir [reproduce.md](reproduce.md), et optionnellement installer le LaunchAgent pour un démarrage automatique à l'ouverture de session.

## Personnalisation (`config.yaml`, puis redémarrer)

- `hotkey.key` : le raccourci (`ctrl+shift` par défaut)
- `stt.language` : `fr` (forcé) — remettre `null` pour l'auto-détection multilingue
- `stt.model` : `small` par défaut ; `medium` pour plus de précision, `base` pour plus de vitesse
- `audio.keep_open` : `false` = micro fermé au repos ; `true` = toujours ouvert + pre-roll
- `llm.model` : le modèle Ollama de nettoyage

## Crédits

Basé sur [VoiceBud](https://github.com/anesriad/VoiceBud-Local-Riad) d'Anas Riad (licence MIT), lui-même une alternative locale et gratuite à Wispr Flow. Adapté pour le français et enrichi avec Claude Code.
