import json
import shutil
import subprocess

from collections import Counter
from pathlib import Path

from PIL import Image
from pillow_heif import register_heif_opener

from core.database import add_media, save_scan_report


# Enregistrement du support HEIC / HEIF pour Pillow
register_heif_opener()


VIDEO_EXTENSIONS = {
    ".mov",
    ".mp4",
    ".m4v",
    ".avi",
    ".mkv",
    ".mpeg",
    ".mpg",
    ".3gp",
    ".3g2",
    ".wmv",
    ".webm",
    ".mts",
    ".m2ts",
    ".ts",
    ".flv",
    ".vob",
    ".ogv",
}


def detect_image_format(path):
    """
    Détecte une image à partir de son contenu.
    Retourne le format Pillow ou None.
    """
    try:
        with Image.open(path) as image:
            image.verify()

            return image.format

    except Exception:
        return None


def detect_video_format(path):
    """
    Détecte une vidéo avec FFprobe.
    Retourne son format ou None.
    """

    ffprobe = shutil.which("ffprobe")

    if ffprobe is None:
        return None

    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-show_entries",
                "format=format_name:stream=codec_type",
                "-of", "json",
                str(path)
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True
        )

        metadata = json.loads(result.stdout)

        streams = metadata.get("streams", [])

        has_video = any(
            stream.get("codec_type") == "video"
            for stream in streams
        )

        if not has_video:
            return None

        format_name = (
            metadata.get("format", {}).get("format_name")
            or path.suffix.lstrip(".")
        )

        return format_name.upper()

    except (
        subprocess.SubprocessError,
        OSError,
        ValueError,
        json.JSONDecodeError
    ):
        return None


def detect_media(path):
    """
    Identifie le type et le format d'un média.

    Retourne :
        ("image", format)
        ("video", format)
        (None, None)
    """

    image_format = detect_image_format(path)

    if image_format is not None:
        return "image", image_format.upper()

    video_format = detect_video_format(path)

    if video_format is not None:
        return "video", video_format

    # Secours si FFprobe n'est pas disponible ou ne reconnaît pas le fichier
    if path.suffix.lower() in VIDEO_EXTENSIONS:
        return (
            "video",
            f"{path.suffix.lstrip('.').upper()} (non vérifié)"
        )

    return None, None


def scan_directory(root):
    """
    Parcourt récursivement le dossier source
    et enregistre les images et vidéos reconnues.
    """

    root = Path(root).resolve()

    detected_formats = Counter()
    ignored_extensions = Counter()

    total_files = 0
    image_files = 0
    video_files = 0
    ignored_files = 0

    for path in root.rglob("*"):

        if not path.is_file():
            continue

        total_files += 1

        media_type, detected_format = detect_media(path)

        if media_type is None:
            extension = path.suffix.lower() or "[sans extension]"

            ignored_extensions[extension] += 1
            ignored_files += 1

            continue

        add_media(
            path=path,
            media_type=media_type,
            detected_format=detected_format
        )

        detected_formats[
            f"{media_type.upper()} - {detected_format}"
        ] += 1

        if media_type == "image":
            image_files += 1

        elif media_type == "video":
            video_files += 1

    save_scan_report(
        total_files=total_files,
        image_files=image_files,
        video_files=video_files,
        ignored_files=ignored_files,
        detected_formats=detected_formats,
        ignored_extensions=ignored_extensions
    )

    return {
        "total_files": total_files,
        "image_files": image_files,
        "video_files": video_files,
        "ignored_files": ignored_files,
        "detected_formats": detected_formats,
        "ignored_extensions": ignored_extensions
    }