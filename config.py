from pathlib import Path


# Dossier contenant les transferts de médias à organiser
SOURCE_ROOT = Path('/Users/abdussamed.yazici/Desktop/test_photo-organizer.nosync/Photos à trier')

# Dossier contenant les dossiers de destination
DESTINATION_ROOT = Path('/Users/abdussamed.yazici/Desktop/test_photo-organizer.nosync/Photos organisées')


# Chemins internes du projet
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "photo_organizer.db"


def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DESTINATION_ROOT.mkdir(parents=True, exist_ok=True)

    if not SOURCE_ROOT.exists():
        raise FileNotFoundError(
            f"Le dossier source n'existe pas : {SOURCE_ROOT}"
        )

    if not SOURCE_ROOT.is_dir():
        raise NotADirectoryError(
            f"Le chemin source n'est pas un dossier : {SOURCE_ROOT}"
        )

    if SOURCE_ROOT == DESTINATION_ROOT:
        raise ValueError(
            "Le dossier source et le dossier de destination doivent être différents."
        )

    if SOURCE_ROOT in DESTINATION_ROOT.parents:
        raise ValueError(
            "Le dossier de destination ne doit pas être situé dans le dossier source."
        )

    if DESTINATION_ROOT in SOURCE_ROOT.parents:
        raise ValueError(
            "Le dossier source ne doit pas être situé dans le dossier de destination."
        )