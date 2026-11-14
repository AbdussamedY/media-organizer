# Media Organizer

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 app.py
```

Sous Linux, le sélecteur natif de dossiers utilise Tkinter. Si Tkinter n'est pas disponible dans ton environnement Python, installe-le avec le gestionnaire de paquets de cet environnement (par exemple `conda install tk` pour Anaconda, ou `sudo apt install python3-tk` pour le Python système).

## Premier lancement

1. Lance l'application avec `python3 app.py`.
2. Ouvre l'adresse locale affichée dans le terminal (par défaut `http://127.0.0.1:5000`).
3. Sélectionne le dossier source contenant les médias à classer.
4. Sélectionne le dossier de destination pour les médias classés.
5. Enregistre la configuration.

Les chemins sont enregistrés localement dans `data/settings.json` et ce fichier est ignoré par Git. Tu peux modifier les dossiers à tout moment depuis le lien **Paramètres**.

La base de données `data/photo_organizer.db` est conservée indépendamment de cette configuration.
