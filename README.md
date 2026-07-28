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

**Prérequis** : un Mac Apple Silicon (M1 ou plus récent) et [Homebrew](https://brew.sh).

```bash
git clone https://github.com/pacaudmatthieu-ui/bavard.git
cd bavard
./install.sh
```

Le script fait tout (~15 min, ~3 Go de téléchargements) : Python, Ollama et son modèle, Whisper, démarrage automatique à l'ouverture de session. Il ne vous reste que deux glisser-déposer dans les Réglages Système (permissions macOS), guidés pas à pas par le script.

Installation manuelle détaillée, installation assistée par Claude Code et dépannage : voir [reproduce.md](reproduce.md).

## Personnalisation (`config.yaml`, puis redémarrer)

- `hotkey.key` : le raccourci (`ctrl+shift` par défaut)
- `stt.language` : `fr` (forcé) — remettre `null` pour l'auto-détection multilingue
- `stt.model` : `small` par défaut ; `medium` pour plus de précision, `base` pour plus de vitesse
- `audio.keep_open` : `false` = micro fermé au repos ; `true` = toujours ouvert + pre-roll
- `llm.model` : le modèle Ollama de nettoyage

## Crédits

Basé sur [VoiceBud](https://github.com/anesriad/VoiceBud-Local-Riad) d'Anas Riad (licence MIT), lui-même une alternative locale et gratuite à Wispr Flow. Adapté pour le français et enrichi avec Claude Code.
