import hashlib
import json
import shutil
import subprocess

from collections import Counter
from pathlib import Path

from PIL import Image
from pillow_heif import register_heif_opener

from core.database import (
    add_or_update_media,
    begin_scan,
    finalize_scan,
    save_scan_report,
)


register_heif_opener()


# Ces extensions ne servent PAS à identifier automatiquement tous les médias.
# Elles constituent uniquement un filet de sécurité pour conserver dans la file
# les formats vidéo lorsque FFprobe n'est pas installé ou ne peut pas décoder
# un fichier sur la machine actuelle.
VIDEO_EXTENSIONS = {
    ".mov", ".mp4", ".m4v", ".avi", ".mkv", ".mpeg", ".mpg",
    ".3gp", ".3g2", ".wmv", ".webm", ".mts", ".m2ts", ".ts",
    ".flv", ".vob", ".ogv",
}

# Même principe pour les images : fallback après une vraie tentative de lecture.
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".jpe", ".jfif",
    ".heic", ".heif", ".hif",
    ".png", ".gif", ".webp", ".tif", ".tiff",
    ".bmp", ".dib", ".avif", ".mpo",
}


def file_fingerprint(path, chunk_size=65536):
    """Empreinte rapide, indépendante du chemin, pour réconcilier deux machines."""
    path = Path(path)
    size = path.stat().st_size

    digest = hashlib.blake2b(digest_size=20)
    digest.update(str(size).encode())

    with path.open("rb") as file:
        digest.update(file.read(chunk_size))

        if size > chunk_size:
            file.seek(max(0, size - chunk_size))
            digest.update(file.read(chunk_size))

    return digest.hexdigest(), size


def detect_image_format(path):
    try:
        with Image.open(path) as image:
            image.verify()
            return image.format
    except Exception:
        return None


def detect_video_format(path):
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
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )

        metadata = json.loads(result.stdout)
        streams = metadata.get("streams", [])

        if not any(
            stream.get("codec_type") == "video"
            for stream in streams
        ):
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
        json.JSONDecodeError,
    ):
        return None


def detect_media(path):
    image_format = detect_image_format(path)
    if image_format is not None:
        return "image", image_format.upper()

    video_format = detect_video_format(path)
    if video_format is not None:
        return "video", video_format

    extension = path.suffix.lower()

    # Fallback explicite : le fichier reste classable même si la pile locale
    # (Pillow/libheif/FFmpeg) ne sait pas le décoder sur Linux.
    if extension in IMAGE_EXTENSIONS:
        return (
            "image",
            f"{extension.lstrip('.').upper()} (non vérifié)",
        )

    if extension in VIDEO_EXTENSIONS:
        return (
            "video",
            f"{extension.lstrip('.').upper()} (non vérifié)",
        )

    return None, None


def scan_directory(root, progress_callback=None):
    """Scanne et synchronise la base avec les médias réellement présents."""
    root = Path(root).resolve()

    paths = [
        path
        for path in root.rglob("*")
        if path.is_file()
    ]

    scan_time = begin_scan()
    total_to_process = len(paths)

    detected_formats = Counter()
    ignored_extensions = Counter()

    total_files = 0
    image_files = 0
    video_files = 0
    ignored_files = 0

    if progress_callback is not None:
        progress_callback({
            "phase": "running",
            "current": 0,
            "total": total_to_process,
            "current_file": None,
            "image_files": 0,
            "video_files": 0,
            "ignored_files": 0,
        })

    for index, path in enumerate(paths, start=1):
        total_files += 1

        media_type, detected_format = detect_media(path)

        if media_type is None:
            extension = path.suffix.lower() or "[sans extension]"
            ignored_extensions[extension] += 1
            ignored_files += 1
        else:
            try:
                fingerprint, file_size = file_fingerprint(path)

                add_or_update_media(
                    path=path,
                    media_type=media_type,
                    detected_format=detected_format,
                    fingerprint=fingerprint,
                    file_size=file_size,
                    scan_time=scan_time,
                )

                detected_formats[
                    f"{media_type.upper()} - {detected_format}"
                ] += 1

                if media_type == "image":
                    image_files += 1
                else:
                    video_files += 1

            except (OSError, PermissionError):
                extension = path.suffix.lower() or "[sans extension]"
                ignored_extensions[extension] += 1
                ignored_files += 1

        if progress_callback is not None:
            progress_callback({
                "phase": "running",
                "current": index,
                "total": total_to_process,
                "current_file": path.name,
                "image_files": image_files,
                "video_files": video_files,
                "ignored_files": ignored_files,
            })

    finalize_scan(scan_time)

    save_scan_report(
        total_files=total_files,
        image_files=image_files,
        video_files=video_files,
        ignored_files=ignored_files,
        detected_formats=detected_formats,
        ignored_extensions=ignored_extensions,
    )

    return {
        "total_files": total_files,
        "image_files": image_files,
        "video_files": video_files,
        "ignored_files": ignored_files,
        "detected_formats": detected_formats,
        "ignored_extensions": ignored_extensions,
    }
