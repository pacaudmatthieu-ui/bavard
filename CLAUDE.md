# Bavard — notes pour Claude Code

Dictée vocale 100 % locale pour macOS (Apple Silicon). Chaîne complète :

```
hotkey → audio.py → transcribe.py → cleanup.py → inject.py
                          ↓             ↓            ↓
                        history.py (sauvegarde à chaque étape)
```

Tout tourne sur la machine : faster-whisper pour la reconnaissance vocale,
Ollama pour le nettoyage. **Rien ne doit jamais partir sur le réseau** en
dehors de `localhost:11434` (Ollama). Aucune télémétrie, aucun appel cloud —
c'est la promesse du produit, pas un détail d'implémentation.

## Langue

Le produit est **français** : interface, menus, notifications, messages
d'erreur destinés à l'utilisateur, README et reproduce.md. Le code, les
docstrings et les commentaires sont en **anglais**. Les messages de commit
sont en français.

## Les modules

| Fichier | Rôle |
|---|---|
| `main.py` | point d'entrée : câble tout ensemble, lance la run loop AppKit |
| `hotkey.py` | raccourci global (pynput), modes `hold` et `toggle` |
| `audio.py` | capture micro, ring buffer de pre-roll, `keep_open` |
| `devices.py` | découverte des micros + choix utilisateur |
| `state.py` | préférences persistantes (`state.json`) : micro, mode |
| `modes.py` | modes de dictée + détection depuis l'app active |
| `context.py` | contexte personnel de l'utilisateur (hors dépôt) |
| `transcribe.py` | faster-whisper (ou mlx-whisper), dictée et fichier long |
| `cleanup.py` | nettoyage LLM via Ollama + commandes vocales de ponctuation |
| `inject.py` | collage au curseur (presse-papiers + Cmd+V synthétique) |
| `history.py` | journal des dictées, filet anti-perte |
| `notify.py` | notifications macOS (osascript) |
| `overlay.py` | pastille flottante (AppKit pur) + pastilles de mode |
| `menubar.py` | icône de la barre de menu, sous-menus, mode réunion |
| `meeting.py` | enregistrement long + compte rendu LLM |
| `prove.py` | preuve bout en bout depuis un WAV (pas un test unitaire) |

## Règles qui ne se devinent pas

**Le modèle LLM vient uniquement de `config.yaml`.** Jamais de nom de modèle
en dur dans le code, jamais de fallback silencieux vers un autre modèle. Si le
modèle configuré est absent, on le dit et on désactive le nettoyage.

**Latence avant élégance.** La dictée doit se coller quasi instantanément.
D'où : les énoncés courts (`min_words_for_cleanup`) sautent complètement
l'appel au LLM ; `"think": False` dans les requêtes Ollama (les variantes
« réflexion » comme `qwen3:4b` tout court sont inutilisables ici) ; les
commandes vocales de ponctuation (« à la ligne », « point d'interrogation »…)
sont traitées par regex dans `cleanup.py`, pas par le LLM — c'est
déterministe et ça marche aussi sur les énoncés courts.

**Le LLM nettoie, il ne répond pas.** Les petits modèles prennent le texte
brut pour une question à laquelle répondre. D'où le prompt système + le
préambule explicite + l'exemple dans `config.yaml`. Toute modification de ces
prompts doit être testée sur des énoncés courts ET longs.

**Tout AppKit sur le thread principal.** Les threads de travail passent par
`AppHelper.callAfter(...)`. Un appel AppKit depuis un thread secondaire ne
lève pas d'erreur — il corrompt l'affichage plus tard, c'est pire.

**PyObjC réserve les noms de sélecteurs courts** sur les sous-classes de
`NSObject` (`create`, `init`, `copy`…). D'où la fonction module-level
`menubar.create(...)` au lieu d'une méthode de classe, et les
`@objc.python_method` sur toutes les méthodes qui ne sont pas des actions de
menu. Les actions de menu (`selectMic_`, `toggleMeeting_`…) doivent, elles,
rester des sélecteurs ObjC — donc **pas** de `@objc.python_method` dessus.

**La pastille ne doit jamais prendre le focus clavier.** Elle est cliquable
(les pastilles de mode), donc : `NSWindowStyleMaskNonactivatingPanel`,
`setBecomesKeyOnlyIfNeeded_(True)` et `acceptsFirstMouse_` qui renvoie `True`
— sans quoi le premier clic serait avalé, et pire, l'app cible perdrait le
focus et le collage n'aurait plus de destination. `chip_rects()` est l'unique
source de vérité de la géométrie : dessin et détection du clic la partagent.

**Le presse-papiers est restauré en différé (1 s).** Les apps lentes
(Electron, navigateurs) traitent le Cmd+V bien après l'envoi de l'événement ;
restaurer trop tôt leur fait coller l'ancien contenu. Ne pas « optimiser » ce
délai.

**PortAudio ne redécouvre le matériel qu'à la ré-initialisation**, ce qui tue
les streams ouverts. D'où `devices.refresh(safe=...)` : on ne rescanne que
quand plus rien n'enregistre.

**Le modèle Whisper n'est pas thread-safe.** Dictée et transcription de
réunion peuvent se chevaucher : `Transcriber` sérialise avec un lock.

**Le mode se décide à l'appui sur le raccourci**, pas au collage : entre les
deux, l'utilisateur a pu changer de fenêtre. `main.py` capture l'app active
dans `on_press` et la transporte jusqu'au nettoyage.

**Ce qui peut être déterministe ne doit pas passer par le LLM.** Les
raccourcis du contexte, les commandes vocales de ponctuation, l'écrasement des
lignes vides en mode court : tout ça est fait en code. Un modèle 4B oublie une
consigne de format environ une fois sur trois — et ces traitements doivent
marcher aussi sur les énoncés courts, qui sautent le LLM.

**Rien ne doit pouvoir perdre une dictée.** `history.record()` est appelé dès
que la transcription existe, avant le nettoyage et avant le collage. Le
journal est un JSONL append-only (une entrée puis ses amendements, `fsync` à
chaque ligne, jamais de réécriture en place). Toute nouvelle étape ajoutée au
pipeline doit rester *après* ce point de sauvegarde.

**La détection de champ de texte est un indice, pas une autorisation.**
`inject._has_text_target()` peut se tromper : on colle toujours. Quand elle
dit « pas de cible », on garde en plus le texte dans le presse-papiers au lieu
de le restaurer. Et sans permission Accessibilité elle s'abstient (renvoie
`True`) plutôt que d'alerter à chaque dictée.

## Permissions macOS

L'app a besoin de trois permissions, accordées au **vrai binaire**
(`readlink -f .venv/bin/python`), pas au terminal :

- **Surveillance de l'entrée** — le raccourci global
- **Accessibilité** — le collage et la détection de champ de texte
- **Micro** — demandé automatiquement à la première dictée

Sans Accessibilité, le collage échoue silencieusement : c'est la panne n° 1.

## Tester

Il n'y a pas de suite de tests. Ce qui existe :

- `python prove.py fichier.wav` — la chaîne complète depuis un WAV, sur Mac
- les modules sans dépendance macOS (`history.py`, la logique de `cleanup.py`)
  se testent en isolation, y compris sur Linux
- `inject.py` se teste en stubbant `Quartz`, `AppKit` et `ApplicationServices`

**Sur une machine non-macOS** (conteneur, CI), rien qui importe `Quartz` ou
`AppKit` ne peut être importé : ni `main.py`, ni `menubar.py`, ni `inject.py`.
Se limiter à `python -m py_compile` pour ceux-là, et tester la logique pure
avec des doublures.

## Ce qui ne va PAS dans le dépôt

Le dépôt est public. Restent en local, jamais commités :

- `state.json` — choix du micro, mode courant (déjà dans `.gitignore`)
- `~/Documents/Bavard/` — historique des dictées, réunions, **contexte
  personnel** de l'utilisateur

Le contexte personnel (nom, liens, vocabulaire métier) vit uniquement sur la
machine de l'utilisateur. Ne jamais l'inclure dans un fichier versionné, ni
dans un exemple de `config.yaml`.
