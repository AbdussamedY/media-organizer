import subprocess
import sys


def select_folder(title, initial_dir=None):
    """
    Ouvre un sélecteur de dossier Tkinter personnalisable dans un processus
    séparé, afin de ne pas lancer l'interface graphique dans un thread Flask.
    """
    script = r"""
import os
import sys
import tkinter as tk
from tkinter import ttk

title = sys.argv[1]
initial_dir = sys.argv[2] or os.path.expanduser("~")

if not os.path.isdir(initial_dir):
    initial_dir = os.path.expanduser("~")

current_dir = os.path.abspath(initial_dir)
selected_dir = None

root = tk.Tk()
root.title(title)
root.geometry("1150x800")
root.minsize(900, 650)
root.configure(padx=24, pady=22)

# Augmente l’échelle globale de Tkinter (notamment utile sur les écrans HiDPI).
root.tk.call("tk", "scaling", 1.6)

# Police et espacements plus confortables que ceux du sélecteur standard.
root.option_add("*Font", ("TkDefaultFont", 17))
style = ttk.Style(root)
style.configure("Treeview", font=("TkDefaultFont", 17), rowheight=42)
style.configure("Treeview.Heading", font=("TkDefaultFont", 22, "bold"))
style.configure("TButton", font=("TkDefaultFont", 16), padding=(16, 11))
style.configure("Path.TEntry", font=("TkDefaultFont", 16), padding=10)

heading = ttk.Label(root, text="Choisir un dossier", font=("TkDefaultFont", 17, "bold"))
heading.pack(anchor="w", pady=(0, 12))

path_frame = ttk.Frame(root)
path_frame.pack(fill="x", pady=(0, 12))

path_var = tk.StringVar(value=current_dir)
path_entry = ttk.Entry(path_frame, textvariable=path_var, style="Path.TEntry")
path_entry.pack(side="left", fill="x", expand=True)

tree_frame = ttk.Frame(root)
tree_frame.pack(fill="both", expand=True)

tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse")
scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
tree.configure(yscrollcommand=scrollbar.set)
tree.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

status_var = tk.StringVar()
status = ttk.Label(root, textvariable=status_var, anchor="w")
status.pack(fill="x", pady=(9, 12))

def show_directory(path):
    global current_dir
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        status_var.set("Ce chemin n'est pas un dossier accessible.")
        return

    current_dir = path
    path_var.set(path)
    tree.delete(*tree.get_children())

    try:
        entries = [
            entry for entry in os.scandir(path)
            if entry.is_dir(follow_symlinks=False)
        ]
        entries.sort(key=lambda entry: entry.name.casefold())
        for entry in entries:
            tree.insert("", "end", text=entry.name, values=(entry.path,))
        status_var.set(
            f"{len(entries)} dossier(s) — Double-cliquez sur un dossier pour l'ouvrir."
        )
    except OSError as error:
        status_var.set(f"Impossible de lire ce dossier : {error}")

def go_to_path(event=None):
    show_directory(path_var.get())

def open_selected(event=None):
    selection = tree.selection()
    if not selection:
        return
    item = tree.item(selection[0])
    name = item["text"]
    show_directory(os.path.join(current_dir, name))

def go_up():
    parent = os.path.dirname(current_dir)
    if parent != current_dir:
        show_directory(parent)

def choose_current():
    global selected_dir
    selected_dir = current_dir
    root.destroy()

def cancel():
    root.destroy()

path_entry.bind("<Return>", go_to_path)
tree.bind("<Double-1>", open_selected)

navigation = ttk.Frame(root)
navigation.pack(fill="x", pady=(12, 0))

ttk.Button(navigation, text="← Remonter", command=go_up).pack(side="left")
ttk.Button(navigation, text="Actualiser", command=lambda: show_directory(current_dir)).pack(
    side="left", padx=(8, 0)
)
ttk.Button(navigation, text="Annuler", command=cancel).pack(side="right")
ttk.Button(
    navigation,
    text="Choisir ce dossier",
    command=choose_current,
).pack(side="right", padx=(0, 8))

root.protocol("WM_DELETE_WINDOW", cancel)

# Centrer la fenêtre à l'écran.
root.update_idletasks()
x = max(0, (root.winfo_screenwidth() - root.winfo_width()) // 2)
y = max(0, (root.winfo_screenheight() - root.winfo_height()) // 2)
root.geometry(f"+{x}+{y}")
root.attributes("-topmost", True)
root.after(400, lambda: root.attributes("-topmost", False))

show_directory(current_dir)
path_entry.focus_set()
root.mainloop()

if selected_dir:
    print(selected_dir)
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
