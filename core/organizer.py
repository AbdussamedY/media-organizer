import os
from pathlib import Path

from config import DESTINATION_ROOT


def get_destination_folders():
    """
    Retourne les sous-dossiers immédiats du dossier de destination.
    """

    DESTINATION_ROOT.mkdir(parents=True, exist_ok=True)

    return sorted(
        [
            folder
            for folder in DESTINATION_ROOT.iterdir()
            if folder.is_dir()
        ],
        key=lambda folder: folder.name.lower()
    )


def create_destination_folder(folder_name):
    """
    Crée un dossier de destination.
    """

    folder_name = folder_name.strip()

    if not folder_name:
        raise ValueError("Le nom du dossier ne peut pas être vide.")

    if folder_name in {".", ".."}:
        raise ValueError("Nom de dossier invalide.")

    if Path(folder_name).name != folder_name:
        raise ValueError("Le nom ne doit pas contenir de chemin.")

    destination = DESTINATION_ROOT / folder_name

    destination.mkdir(exist_ok=True)

    if not destination.is_dir():
        raise ValueError("Un fichier portant ce nom existe déjà.")

    return destination


def move_media(source_path, destination_folder):
    """
    Déplace un média dans un dossier de destination.

    Le dossier de destination doit être un sous-dossier immédiat
    de DESTINATION_ROOT.
    """

    source_path = Path(source_path).resolve()
    destination_folder = Path(destination_folder).resolve()
    destination_root = DESTINATION_ROOT.resolve()

    if not source_path.is_file():
        raise FileNotFoundError(
            f"Le média source n'existe pas : {source_path}"
        )

    if destination_folder.parent != destination_root:
        raise ValueError(
            "Le dossier de destination n'est pas autorisé."
        )

    if not destination_folder.is_dir():
        raise NotADirectoryError(
            "Le dossier de destination n'existe pas."
        )

    destination_path = destination_folder / source_path.name

    if destination_path.exists():
        raise FileExistsError(
            f"Un fichier nommé {source_path.name} existe déjà "
            f"dans {destination_folder.name}."
        )

    source_device = os.stat(source_path).st_dev
    destination_device = os.stat(destination_folder).st_dev

    if source_device != destination_device:
        raise OSError(
            "Le fichier source et le dossier de destination "
            "sont sur des volumes différents. "
            "Le déplacement natif n'est pas possible."
        )

    os.rename(source_path, destination_path)

    return destination_path


def undo_move(source_path, destination_path):
    """Replace un média à son emplacement précédent."""

    source_path = Path(source_path).resolve()
    destination_path = Path(destination_path).resolve()

    if not destination_path.is_file():
        raise FileNotFoundError(
            f"Le média déplacé n'existe plus : {destination_path}"
        )

    if source_path.exists():
        raise FileExistsError(
            f"Un fichier existe déjà à l'emplacement d'origine : {source_path}"
        )

    source_path.parent.mkdir(parents=True, exist_ok=True)

    source_device = os.stat(destination_path).st_dev
    destination_device = os.stat(source_path.parent).st_dev

    if source_device != destination_device:
        raise OSError(
            "Le média et son emplacement d'origine sont sur "
            "des volumes différents. L'annulation native n'est pas possible."
        )

    os.rename(destination_path, source_path)

    return source_path