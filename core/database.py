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


def add_media(path, media_type, detected_format):
    path = Path(path).resolve()

    with get_connection() as connection:
        connection.execute("""
            INSERT OR IGNORE INTO media (
                original_path,
                current_path,
                filename,
                media_type,
                detected_format,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """, (
            str(path),
            str(path),
            path.name,
            media_type,
            detected_format,
            datetime.now().isoformat(timespec="seconds")
        ))


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

    report["detected_formats"] = json.loads(
        report["detected_formats"]
    )

    report["ignored_extensions"] = json.loads(
        report["ignored_extensions"]
    )

    return report


def get_next_pending_media():
    with get_connection() as connection:
        media = connection.execute("""
            SELECT *
            FROM media
            WHERE status = 'pending'
            ORDER BY id
            LIMIT 1
        """).fetchone()

    return media


def mark_media_moved(media_id, new_path):
    new_path = Path(new_path).resolve()

    with get_connection() as connection:
        connection.execute("""
            UPDATE media
            SET
                current_path = ?,
                destination_path = ?,
                status = 'moved',
                moved_at = ?
            WHERE id = ?
        """, (
            str(new_path),
            str(new_path.parent),
            datetime.now().isoformat(timespec="seconds"),
            media_id
        ))


def get_statistics():
    with get_connection() as connection:
        row = connection.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'moved' THEN 1 ELSE 0 END) AS moved,
                SUM(CASE WHEN media_type = 'image' THEN 1 ELSE 0 END) AS images,
                SUM(CASE WHEN media_type = 'video' THEN 1 ELSE 0 END) AS videos,
                SUM(CASE WHEN status = 'pending' AND media_type = 'image'
                    THEN 1 ELSE 0 END) AS pending_images,
                SUM(CASE WHEN status = 'pending' AND media_type = 'video'
                    THEN 1 ELSE 0 END) AS pending_videos
            FROM media
        """).fetchone()

    return {
        key: row[key] or 0
        for key in row.keys()
    }