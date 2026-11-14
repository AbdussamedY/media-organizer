import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "photo_organizer.db"
SETTINGS_PATH = DATA_DIR / "settings.json"


def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_settings():
    if not SETTINGS_PATH.is_file():
        return None
    try:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Impossible de lire la configuration locale : {SETTINGS_PATH}") from error

    source = settings.get("source_root")
    destination = settings.get("destination_root")
    if not source or not destination:
        raise RuntimeError("Configuration incomplète. Sélectionne à nouveau les dossiers dans les paramètres.")
    return {"source_root": Path(source).expanduser(), "destination_root": Path(destination).expanduser()}


def get_source_root():
    settings = load_settings()
    if settings is None:
        raise RuntimeError("Le dossier source n'est pas encore configuré.")
    return settings["source_root"]


def get_destination_root():
    settings = load_settings()
    if settings is None:
        raise RuntimeError("Le dossier de destination n'est pas encore configuré.")
    return settings["destination_root"]


def validate_paths(source_root, destination_root):
    source = Path(source_root).expanduser().resolve(strict=True)
    destination = Path(destination_root).expanduser().resolve(strict=False)
    if not source.is_dir():
        raise NotADirectoryError(f"Le dossier source n'est pas un dossier : {source}")
    if source == destination:
        raise ValueError("Le dossier source et le dossier de destination doivent être différents.")
    if source in destination.parents:
        raise ValueError("Le dossier de destination ne doit pas être situé dans le dossier source.")
    if destination in source.parents:
        raise ValueError("Le dossier source ne doit pas être situé dans le dossier de destination.")
    return source, destination


def save_settings(source_root, destination_root):
    ensure_directories()
    source, destination = validate_paths(source_root, destination_root)
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        raise NotADirectoryError(f"Le chemin de destination n'est pas un dossier : {destination}")
    settings = {"source_root": str(source), "destination_root": str(destination)}
    temporary_path = SETTINGS_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(SETTINGS_PATH)
    return settings
