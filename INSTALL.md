# Installation de JARVIS sur votre PC (Windows)

JARVIS est une application Python. Pour le faire tourner sur votre PC,
suivez ces étapes.

## 1. Prérequis

### Python 3.10 ou plus récent

Téléchargez et installez Python depuis <https://www.python.org/downloads/>.

**IMPORTANT** : pendant l'installation, cochez la case
**« Add Python to PATH »** (Ajouter Python au PATH).

Vérifiez que Python est bien installé en ouvrant l'Invite de commandes
(touche Windows, tapez `cmd`, Entrée) puis :

```cmd
python --version
```

Vous devez voir quelque chose comme `Python 3.11.x` ou `3.12.x`.

### MetaTrader 5 (optionnel — uniquement pour le trading réel)

Si vous souhaitez que JARVIS se connecte à votre compte MT5 pour trader
en réel, installez MetaTrader 5 depuis votre broker. Sinon, JARVIS
tourne en mode démo (simulation) — aucun MT5 requis pour démarrer.

---

## 2. Installer JARVIS

1. **Décompressez le zip** : copiez le fichier `jarvis.zip` sur votre
   bureau, faites un clic droit → « Extraire tout… ». Vous obtenez un
   dossier `jarvis`.

2. Ouvrez l'Invite de commandes (`cmd`) et allez dans le dossier :

   ```cmd
   cd %USERPROFILE%\Desktop\jarvis
   ```

   (adaptez le chemin selon l'endroit où vous avez extrait le zip)

3. **Installez les dépendances** :

   ```cmd
   pip install -e .
   ```

   Cela installe Streamlit, pandas, numpy, plotly, etc. Ça prend 1 à 2
   minutes la première fois. Le `[dev]` ci-dessous inclut aussi les
   outils de test :

   ```cmd
   pip install -e ".[dev]"
   ```

4. **Configurez vos paramètres** :

   ```cmd
   copy .env.example .env
   ```

   Puis éditez le fichier `.env` avec le Bloc-notes pour mettre vos
   identifiants MT5 (si vous tradez en réel) et choisir le mode.

---

## 3. Lancer l'interface web

Dans l'Invite de commandes, depuis le dossier `jarvis` :

```cmd
streamlit run app.py
```

Streamlit démarre et **ouvre automatiquement votre navigateur** sur
<http://localhost:8501>.

Vous voyez le dashboard complet de JARVIS :
- Portfolio (balance, equity, P&L, positions)
- Les 9 agents et leur décision
- Calendrier macro
- Graphique de prix en chandeliers japonais
- Trades récents
- Le chat en bas de page pour commander JARVIS

### Pour arrêter

Dans l'Invite de commandes, appuyez sur `Ctrl + C`.

---

## 4. Configurer le mode de trading

Éditez le fichier `.env` avec le Bloc-notes :

### Mode ANALYSIS (analyse uniquement, aucun ordre)

```env
TRADING_MODE=ANALYSIS
LIVE_TRADING_ENABLED=false
```

JARVIS analyse, mais ne peut envoyer **aucun ordre**.

### Mode PAPER (simulation, argent fictif) — recommandé pour démarrer

```env
TRADING_MODE=PAPER
LIVE_TRADING_ENABLED=false
PAPER_CAPITAL_XOF=500000
```

JARVIS simule les trades avec de l'argent fictif. Idéal pour tester.

### Mode LIVE (argent réel — nécessite MetaTrader 5)

```env
TRADING_MODE=LIVE
LIVE_TRADING_ENABLED=true
MT5_LOGIN=VOTRE_LOGIN
MT5_PASSWORD=MOT_DE_PASSE
MT5_SERVER=SERVEUR_DU_BROKER
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
```

**ATTENTION** : en mode LIVE, JARVIS peut exécuter de vrais ordres.
Mais il ne le fait **JAMAIS sans votre instruction explicite** + votre
confirmation. Les ordres d'analyse (« Analyse EUR/USD ») ne déclenchent
jamais d'ordre.

---

## 5. Utiliser le chat

Dans le chat en bas de la page web :

| Vous tapez | JARVIS fait |
|---|---|
| `Analyse EUR/USD` | Lance les 9 agents, montre la décision |
| `Que penses-tu de GBP/USD ?` | Analyse GBP/USD |
| `Cherche les meilleures opportunités` | Scanne plusieurs paires |
| `Exécute le trade proposé` | Prépare l'ordre, attend votre confirmation |
| `oui` | Confirme et envoie l'ordre |
| `non` | Annule |
| `Ferme cette position` | Ferme une position ouverte |
| `kill-switch` | Active le bouton d'arrêt d'urgence |

**Règle fondamentale** : JARVIS n'exécute JAMAIS un ordre sans votre
instruction explicite. Les commandes d'analyse ne déclenchent jamais
de trade.

---

## 6. En ligne de commande (alternative)

Si vous préférez le terminal :

```cmd
jarvis                        :: chat conversationnel interactif
jarvis --once "Analyse EUR/USD"   :: une seule commande
jarvis --dashboard            :: dashboard texte
```

---

## 7. Tester l'installation

Vérifiez que tout fonctionne :

```cmd
pytest -q
```

Vous devez voir `84 passed` — JARVIS est prêt.

---

## 8. Problèmes fréquents

### `streamlit` n'est pas reconnu

Vous avez oublié d'installer les dépendances. Refaites :

```cmd
pip install -e .
```

### `python` n'est pas reconnu

Python n'est pas dans le PATH. Réinstallez Python en cochant
« Add Python to PATH ».

### Le port 8501 est déjà utilisé

Lancez sur un autre port :

```cmd
streamlit run app.py --server.port 8502
```

Puis ouvrez <http://localhost:8502> dans votre navigateur.

### MetaTrader 5 ne se connecte pas (mode LIVE)

- Vérifiez vos identifiants dans `.env`
- Vérifiez le chemin de `terminal64.exe`
- MT5 doit être installé et avoir été lancé au moins une fois
- Votre broker doit autoriser le trading automatisé

### Je veux réinitialiser la mémoire

Supprimez le fichier `jarvis/data/memory.db` (il sera recréé
automatiquement au prochain démarrage).

---

## Structure du projet

```
jarvis/
├── app.py              ← interface web (Streamlit) — lancez celle-ci
├── jarvis/
│   ├── agents/         ← les 9 sous-agents
│   ├── boss.py         ← l'orchestrateur JARVIS BOSS
│   ├── brokers/        ← MT5 + broker démo
│   ├── chat/           ← classification des commandes + handler
│   ├── core/           ← config, modèles, mémoire, indicateurs
│   ├── engine/         ← backtest, paper trading, monitor
│   ├── execution/      ← LE SEUL module qui peut envoyer un ordre
│   ├── learning/       ← self-critic + versioning
│   └── web/            ← session state pour l'app web
├── tests/              ← 84 tests
├── .env.example        ← modèle de configuration
└── INSTALL.md          ← ce fichier
```

---

## Sécurité

- ❌ **JARVIS n'exécute jamais un ordre sans votre commande explicite**
- 🔒 Vos identifiants MT5 sont dans `.env` (jamais dans le code)
- 🛑 Kill-switch disponible : tapez `kill-switch` dans le chat
- 🟢 LIVE désactivé par défaut

Pour toute question, relisez ce fichier ou le `README.md`.
