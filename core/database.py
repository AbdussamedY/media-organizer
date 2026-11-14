import json
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DATABASE_PATH, DATA_DIR


def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _columns(connection, table):
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})")
    }


def _add_column_if_missing(connection, table, definition):
    column_name = definition.split()[0]
    if column_name not in _columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def initialize_database():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_path TEXT NOT NULL UNIQUE,
                current_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                media_type TEXT NOT NULL,
                detected_format TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                destination_path TEXT,
                created_at TEXT NOT NULL,
                moved_at TEXT
            )
        """)

        # Migration transparente des anciennes bases.
        _add_column_if_missing(connection, "media", "fingerprint TEXT")
        _add_column_if_missing(connection, "media", "file_size INTEGER")
        _add_column_if_missing(connection, "media", "last_seen_scan TEXT")
        _add_column_if_missing(connection, "media", "missing_since TEXT")

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_media_fingerprint
            ON media(fingerprint)
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS move_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_id INTEGER NOT NULL,
                source_path TEXT NOT NULL,
                destination_path TEXT NOT NULL,
                moved_at TEXT NOT NULL,
                undone_at TEXT,
                FOREIGN KEY (media_id) REFERENCES media(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS scan_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_time TEXT NOT NULL,
                total_files INTEGER NOT NULL,
                image_files INTEGER NOT NULL,
                video_files INTEGER NOT NULL,
                ignored_files INTEGER NOT NULL,
                detected_formats TEXT NOT NULL,
                ignored_extensions TEXT NOT NULL
            )
        """)


def begin_scan():
    return datetime.now().isoformat(timespec="seconds")


def add_or_update_media(
    path,
    media_type,
    detected_format,
    fingerprint,
    file_size,
    scan_time
):
    """Ajoute un média ou réconcilie une entrée existante après changement de PC."""
    path = Path(path).resolve()
    path_string = str(path)

    with get_connection() as connection:
        # 1. Même chemin actuel.
        media = connection.execute("""
            SELECT *
            FROM media
            WHERE original_path = ?
        """, (path_string,)).fetchone()

        # 2. Même contenu : le chemin peut avoir changé (Mac -> Linux).
        if media is None and fingerprint:
            media = connection.execute("""
                SELECT *
                FROM media
                WHERE fingerprint = ?
                ORDER BY
                    CASE status
                        WHEN 'pending' THEN 0
                        WHEN 'moved' THEN 1
                        ELSE 2
                    END,
                    id
                LIMIT 1
            """, (fingerprint,)).fetchone()

        # 3. Migration des anciennes lignes sans fingerprint.
        # On ne réutilise qu'une entrée pending dont l'ancien fichier n'existe plus,
        # et uniquement si le nom/type/format correspondent exactement.
        if media is None:
            candidates = connection.execute("""
                SELECT *
                FROM media
                WHERE
                    fingerprint IS NULL
                    AND status = 'pending'
                    AND filename = ?
                    AND media_type = ?
                    AND detected_format = ?
            """, (
                path.name,
                media_type,
                detected_format
            )).fetchall()

            missing_candidates = [
                candidate
                for candidate in candidates
                if not Path(candidate["current_path"]).is_file()
            ]

            if len(missing_candidates) == 1:
                media = missing_candidates[0]

        if media is None:
            connection.execute("""
                INSERT INTO media (
                    original_path,
                    current_path,
                    filename,
                    media_type,
                    detected_format,
                    fingerprint,
                    file_size,
                    status,
                    created_at,
                    last_seen_scan,
                    missing_since
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, NULL)
            """, (
                path_string,
                path_string,
                path.name,
                media_type,
                detected_format,
                fingerprint,
                file_size,
                datetime.now().isoformat(timespec="seconds"),
                scan_time
            ))
            return "inserted"

        # Un média déjà moved garde son emplacement courant : scanner le dossier
        # source ne doit pas écraser une destination de classement.
        if media["status"] == "moved":
            connection.execute("""
                UPDATE media
                SET
                    fingerprint = COALESCE(fingerprint, ?),
                    file_size = COALESCE(file_size, ?),
                    last_seen_scan = ?,
                    missing_since = NULL
                WHERE id = ?
            """, (
                fingerprint,
                file_size,
                scan_time,
                media["id"]
            ))
            return "matched"

        # pending / missing : le chemin réel est maintenant celui trouvé par le scan.
        connection.execute("""
            UPDATE media
            SET
                original_path = ?,
                current_path = ?,
                filename = ?,
                media_type = ?,
                detected_format = ?,
                fingerprint = ?,
                file_size = ?,
                status = 'pending',
                last_seen_scan = ?,
                missing_since = NULL
            WHERE id = ?
        """, (
            path_string,
            path_string,
            path.name,
            media_type,
            detected_format,
            fingerprint,
            file_size,
            scan_time,
            media["id"]
        ))
        return "matched"


def finalize_scan(scan_time):
    """Marque les anciennes entrées pending absentes du dernier scan comme missing."""
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT id, current_path
            FROM media
            WHERE status = 'pending'
              AND (last_seen_scan IS NULL OR last_seen_scan != ?)
        """, (scan_time,)).fetchall()

        missing_ids = [
            row["id"]
            for row in rows
            if not Path(row["current_path"]).is_file()
        ]

        if missing_ids:
            connection.executemany("""
                UPDATE media
                SET
                    status = 'missing',
                    missing_since = ?
                WHERE id = ?
            """, [
                (
                    datetime.now().isoformat(timespec="seconds"),
                    media_id
                )
                for media_id in missing_ids
            ])

    return len(missing_ids)


def save_scan_report(
    total_files,
    image_files,
    video_files,
    ignored_files,
    detected_formats,
    ignored_extensions
):
    with get_connection() as connection:
        connection.execute("""
            INSERT INTO scan_reports (
                scan_time,
                total_files,
                image_files,
                video_files,
                ignored_files,
                detected_formats,
                ignored_extensions
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(timespec="seconds"),
            total_files,
            image_files,
            video_files,
            ignored_files,
            json.dumps(dict(detected_formats), ensure_ascii=False),
            json.dumps(dict(ignored_extensions), ensure_ascii=False)
        ))


def get_latest_scan_report():
    with get_connection() as connection:
        report = connection.execute("""
            SELECT *
            FROM scan_reports
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

    if report is None:
        return None

    report = dict(report)
    report["detected_formats"] = json.loads(report["detected_formats"])
    report["ignored_extensions"] = json.loads(report["ignored_extensions"])
    return report


def get_next_pending_media(after_id=None):
    with get_connection() as connection:
        if after_id is not None:
            media = connection.execute("""
                SELECT * FROM media
                WHERE status = 'pending' AND id > ?
                ORDER BY id LIMIT 1
            """, (after_id,)).fetchone()
            if media is not None:
                return media

        return connection.execute("""
            SELECT * FROM media
            WHERE status = 'pending'
            ORDER BY id LIMIT 1
        """).fetchone()


def get_pending_media_by_id(media_id):
    with get_connection() as connection:
        return connection.execute("""
            SELECT * FROM media
            WHERE id = ? AND status = 'pending'
        """, (media_id,)).fetchone()


def get_pending_media_navigation(media_id):
    with get_connection() as connection:
        total = connection.execute("""
            SELECT COUNT(*) FROM media
            WHERE status = 'pending'
        """).fetchone()[0]

        position = connection.execute("""
            SELECT COUNT(*) FROM media
            WHERE status = 'pending' AND id <= ?
        """, (media_id,)).fetchone()[0]

        previous_media = connection.execute("""
            SELECT id FROM media
            WHERE status = 'pending' AND id < ?
            ORDER BY id DESC LIMIT 1
        """, (media_id,)).fetchone()

        next_media = connection.execute("""
            SELECT id FROM media
            WHERE status = 'pending' AND id > ?
            ORDER BY id LIMIT 1
        """, (media_id,)).fetchone()

    return {
        "position": position,
        "total": total,
        "previous_id": previous_media["id"] if previous_media else None,
        "next_id": next_media["id"] if next_media else None
    }


def mark_media_moved(media_id, new_path):
    new_path = Path(new_path).resolve()

    with get_connection() as connection:
        media = connection.execute("""
            SELECT current_path FROM media WHERE id = ?
        """, (media_id,)).fetchone()

        if media is None:
            raise ValueError("Média introuvable.")

        moved_at = datetime.now().isoformat(timespec="seconds")
        source_path = media["current_path"]

        connection.execute("""
            INSERT INTO move_history (
                media_id, source_path, destination_path, moved_at
            )
            VALUES (?, ?, ?, ?)
        """, (media_id, source_path, str(new_path), moved_at))

        connection.execute("""
            UPDATE media
            SET current_path = ?, destination_path = ?,
                status = 'moved', moved_at = ?
            WHERE id = ?
        """, (
            str(new_path),
            str(new_path.parent),
            moved_at,
            media_id
        ))


def get_last_active_move():
    with get_connection() as connection:
        return connection.execute("""
            SELECT move_history.*, media.filename
            FROM move_history
            JOIN media ON media.id = move_history.media_id
            WHERE move_history.undone_at IS NULL
            ORDER BY move_history.id DESC
            LIMIT 1
        """).fetchone()


def mark_move_undone(move_id):
    with get_connection() as connection:
        move = connection.execute("""
            SELECT * FROM move_history
            WHERE id = ? AND undone_at IS NULL
        """, (move_id,)).fetchone()

        if move is None:
            raise ValueError("Ce déplacement ne peut plus être annulé.")

        connection.execute("""
            UPDATE move_history
            SET undone_at = ?
            WHERE id = ?
        """, (
            datetime.now().isoformat(timespec="seconds"),
            move_id
        ))

        connection.execute("""
            UPDATE media
            SET current_path = ?, destination_path = NULL,
                status = 'pending', moved_at = NULL,
                missing_since = NULL
            WHERE id = ?
        """, (
            move["source_path"],
            move["media_id"]
        ))


def get_statistics():
    with get_connection() as connection:
        row = connection.execute("""
            SELECT
                SUM(CASE WHEN status IN ('pending', 'moved') THEN 1 ELSE 0 END) AS total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'moved' THEN 1 ELSE 0 END) AS moved,
                SUM(CASE WHEN status IN ('pending', 'moved') AND media_type = 'image' THEN 1 ELSE 0 END) AS images,
                SUM(CASE WHEN status IN ('pending', 'moved') AND media_type = 'video' THEN 1 ELSE 0 END) AS videos,
                SUM(CASE WHEN status = 'pending' AND media_type = 'image' THEN 1 ELSE 0 END) AS pending_images,
                SUM(CASE WHEN status = 'pending' AND media_type = 'video' THEN 1 ELSE 0 END) AS pending_videos,
                SUM(CASE WHEN status = 'missing' THEN 1 ELSE 0 END) AS missing
            FROM media
        """).fetchone()

    return {key: row[key] or 0 for key in row.keys()}
