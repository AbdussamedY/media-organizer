import subprocess
import sys


def select_folder(title, initial_dir=None):
    """
    Ouvre un sélecteur de dossier natif dans un processus séparé.

    Le processus séparé évite de lancer Tkinter depuis un thread de requête
    Flask, ce qui est fragile sur plusieurs systèmes.
    """
    script = r"""
import sys
import tkinter as tk
from tkinter import filedialog

title = sys.argv[1]
initial_dir = sys.argv[2] or None

root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)

try:
    selected = filedialog.askdirectory(
        parent=root,
        title=title,
        initialdir=initial_dir,
        mustexist=True,
    )
    print(selected or "")
finally:
    root.destroy()
"""

    try:
        result = subprocess.run(
            [sys.executable, "-c", script, title, str(initial_dir or "")],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            "Le sélecteur de dossiers a dépassé le délai autorisé."
        ) from error

    if result.returncode != 0:
        details = result.stderr.strip()
        raise RuntimeError(
            "Impossible d'ouvrir le sélecteur de dossiers. "
            "Vérifie que Tkinter est installé et qu'une session graphique "
            "est disponible."
            + (f" Détail : {details}" if details else "")
        )

    selected = result.stdout.strip()
    return selected or None
