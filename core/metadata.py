import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image, ExifTags


def _display_value(value):
    """Convertit une valeur EXIF/FFprobe en texte lisible."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace").strip("\x00")
        except Exception:
            return repr(value)

    if isinstance(value, (tuple, list)):
        return ", ".join(_display_value(item) for item in value)

    if isinstance(value, dict):
        return "; ".join(
            f"{key}: {_display_value(item)}"
            for key, item in value.items()
        )

    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        denominator = value.denominator
        if denominator:
            number = value.numerator / denominator
            return f"{number:g}"

    return str(value)


def _add_section(sections, title, values):
    cleaned = [
        {"label": str(label), "value": _display_value(value)}
        for label, value in values
        if value is not None and str(value).strip() != ""
    ]
    if cleaned:
        sections.append({"title": title, "items": cleaned})


def _image_metadata(path, sections):
    try:
        with Image.open(path) as image:
            _add_section(sections, "Image", [
                ("Dimensions", f"{image.width} × {image.height} px"),
                ("Mode colorimétrique", image.mode),
                ("Format Pillow", image.format),
                ("Animation", getattr(image, "n_frames", 1) > 1),
            ])

            exif = image.getexif()
            if not exif:
                return

            decoded = []
            gps_values = []

            for tag_id, value in exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, f"Tag {tag_id}")
                if tag_name == "GPSInfo":
                    try:
                        gps = value
                        gps_decoded = []
                        for gps_id, gps_value in gps.items():
                            gps_name = ExifTags.GPSTAGS.get(
                                gps_id, f"GPS {gps_id}"
                            )
                            gps_decoded.append(
                                (gps_name, _display_value(gps_value))
                            )
                        gps_values.extend(gps_decoded)
                    except Exception:
                        gps_values.append(("GPSInfo", _display_value(value)))
                else:
                    decoded.append((tag_name, value))

            _add_section(sections, "Métadonnées EXIF", decoded)
            _add_section(sections, "GPS", gps_values)

    except Exception as error:
        _add_section(sections, "Métadonnées image", [
            ("Lecture EXIF", f"Impossible de lire les métadonnées : {error}")
        ])


def _video_metadata(path, sections):
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        _add_section(sections, "Vidéo", [
            ("Analyse détaillée", "FFprobe/FFmpeg n'est pas installé.")
        ])
        return

    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_format",
                "-show_streams",
                "-of", "json",
                str(path)
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True
        )
        metadata = json.loads(result.stdout)
        format_info = metadata.get("format", {})
        streams = metadata.get("streams", [])

        duration = format_info.get("duration")
        if duration is not None:
            seconds = float(duration)
            minutes, remaining_seconds = divmod(seconds, 60)
            duration_text = f"{int(minutes)} min {remaining_seconds:.2f} s"
        else:
            duration_text = None

        size = format_info.get("size")
        bitrate = format_info.get("bit_rate")

        _add_section(sections, "Vidéo", [
            ("Durée", duration_text),
            ("Conteneur", format_info.get("format_long_name")),
            ("Nom du format", format_info.get("format_name")),
            ("Débit global", f"{int(bitrate):,} bit/s" if bitrate else None),
            ("Taille déclarée", f"{int(size):,} octets" if size else None),
            ("Nombre de flux", len(streams)),
        ])

        for index, stream in enumerate(streams, start=1):
            codec_type = stream.get("codec_type", "Flux")
            values = [
                ("Codec", stream.get("codec_long_name") or stream.get("codec_name")),
                ("Profil", stream.get("profile")),
                ("Codec tag", stream.get("codec_tag_string")),
                ("Langue", stream.get("tags", {}).get("language")),
                ("Débit", (
                    f"{int(stream['bit_rate']):,} bit/s"
                    if stream.get("bit_rate") else None
                )),
                ("Durée", stream.get("duration")),
                ("Échantillonnage audio", (
                    f"{stream.get('sample_rate')} Hz"
                    if stream.get("sample_rate") else None
                )),
                ("Canaux audio", stream.get("channels")),
                ("Disposition audio", stream.get("channel_layout")),
                ("Format pixel", stream.get("pix_fmt")),
                ("Images par seconde", (
                    stream.get("avg_frame_rate")
                    or stream.get("r_frame_rate")
                )),
                ("Nombre d'images", stream.get("nb_frames")),
                ("Largeur", (
                    f"{stream.get('width')} px"
                    if stream.get("width") else None
                )),
                ("Hauteur", (
                    f"{stream.get('height')} px"
                    if stream.get("height") else None
                )),
                ("Rotation", stream.get("tags", {}).get("rotate")),
            ]
            _add_section(sections, f"Flux {index} — {codec_type}", values)

            tags = stream.get("tags", {})
            _add_section(
                sections,
                f"Métadonnées du flux {index}",
                list(tags.items())
            )

        _add_section(
            sections,
            "Métadonnées du conteneur",
            list(format_info.get("tags", {}).items())
        )

    except Exception as error:
        _add_section(sections, "Vidéo", [
            ("Analyse détaillée", f"Impossible de lire les métadonnées : {error}")
        ])


def get_media_metadata(path, media_type):
    """Construit les informations système et les métadonnées d'un média."""
    path = Path(path)
    stat = path.stat()

    sections = []

    size_bytes = stat.st_size
    size_mib = size_bytes / (1024 ** 2)

    _add_section(sections, "Fichier", [
        ("Nom", path.name),
        ("Extension", path.suffix.lower() or "Aucune"),
        ("Type détecté", media_type),
        ("Chemin actuel", str(path.resolve())),
        ("Taille", f"{size_bytes:,} octets ({size_mib:.2f} Mio)"),
        ("Création (système)", datetime.fromtimestamp(stat.st_ctime).astimezone().isoformat(timespec="seconds")),
        ("Modification (système)", datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")),
    ])

    if media_type == "image":
        _image_metadata(path, sections)
    elif media_type == "video":
        _video_metadata(path, sections)

    return sections
