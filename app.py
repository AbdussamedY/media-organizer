from pathlib import Path
from threading import Lock, Thread

from flask import (
    Flask, abort, flash, jsonify, redirect, render_template,
    request, send_file, url_for
)

from config import (
    ensure_directories, load_settings, get_source_root, save_settings
)
from core.folder_picker import select_folder
from core.database import (
    initialize_database, get_statistics, get_latest_scan_report,
    get_next_pending_media, get_pending_media_by_id,
    get_pending_media_navigation, mark_media_moved,
    get_last_active_move, mark_move_undone
)
from core.scanner import scan_directory
from core.metadata import get_media_metadata
from core.organizer import (
    get_destination_folders, create_destination_folder,
    move_media, undo_move
)


app = Flask(__name__)
app.secret_key = "change-this-local-secret-key"

# La base est initialisée indépendamment des chemins des médias.
# Une configuration manquante ne doit jamais empêcher l'application de démarrer.
ensure_directories()
initialize_database()

scan_lock = Lock()
scan_status = {
    "phase": "idle", "current": 0, "total": 0, "current_file": None,
    "image_files": 0, "video_files": 0, "ignored_files": 0, "error": None,
}


def is_configured():
    return load_settings() is not None


def update_scan_status(progress):
    with scan_lock:
        scan_status.update(progress)


def run_scan():
    try:
        report = scan_directory(
            get_source_root(),
            progress_callback=update_scan_status
        )
        with scan_lock:
            scan_status.update({
                "phase": "completed",
                "current": report["total_files"],
                "total": report["total_files"],
                "current_file": None,
                "image_files": report["image_files"],
                "video_files": report["video_files"],
                "ignored_files": report["ignored_files"],
                "error": None,
            })
    except Exception as error:
        with scan_lock:
            scan_status.update({"phase": "error", "error": str(error)})


@app.route("/settings", methods=["GET"])
def settings():
    current = load_settings()
    return render_template(
        "setup.html",
        configured=current is not None,
        source_path=str(current["source_root"]) if current else "",
        destination_path=str(current["destination_root"]) if current else "",
    )


@app.route("/select-folder", methods=["POST"])
def select_folder_route():
    data = request.get_json(silent=True) or {}
    target = data.get("target")
    if target not in {"source_root", "destination_root"}:
        return jsonify({"error": "Champ de sélection invalide."}), 400

    current_path = data.get("current_path", "")
    initial_dir = current_path if current_path and Path(current_path).is_dir() else None
    title = (
        "Sélectionner le dossier source"
        if target == "source_root"
        else "Sélectionner le dossier de destination"
    )
    try:
        selected = select_folder(title, initial_dir)
        return jsonify({"path": selected})
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@app.route("/settings", methods=["POST"])
def save_settings_route():
    try:
        save_settings(
            request.form.get("source_root", ""),
            request.form.get("destination_root", ""),
        )
        flash("Configuration enregistrée.", "success")
        return redirect(url_for("dashboard"))
    except Exception as error:
        flash(f"Configuration impossible : {error}", "error")
        return redirect(url_for("settings"))


@app.route("/")
def dashboard():
    if not is_configured():
        return redirect(url_for("settings"))

    statistics = get_statistics()
    scan_report = get_latest_scan_report()
    destination_folders = get_destination_folders()
    current = load_settings()

    return render_template(
        "dashboard.html",
        statistics=statistics,
        scan_report=scan_report,
        destination_folders=destination_folders,
        source_path=str(current["source_root"]),
        destination_path=str(current["destination_root"]),
    )


@app.route("/scan", methods=["POST"])
def scan():
    if not is_configured():
        return jsonify({"started": False, "message": "Configure d'abord les dossiers."}), 400

    with scan_lock:
        if scan_status["phase"] in {"running", "starting"}:
            return jsonify({"started": False, "message": "Un scan est déjà en cours."}), 409
        scan_status.update({
            "phase": "starting", "current": 0, "total": 0,
            "current_file": None, "image_files": 0, "video_files": 0,
            "ignored_files": 0, "error": None,
        })

    Thread(target=run_scan, daemon=True).start()
    return jsonify({"started": True, "message": "Scan démarré."})


@app.route("/scan-status")
def scan_status_endpoint():
    with scan_lock:
        return jsonify(dict(scan_status))


@app.route("/classify")
def classify():
    if not is_configured():
        return redirect(url_for("settings"))

    requested_media_id = request.args.get("media_id", type=int)
    media = (
        get_pending_media_by_id(requested_media_id)
        if requested_media_id is not None else None
    )
    if media is None:
        media = get_next_pending_media()

    navigation = (
        get_pending_media_navigation(media["id"])
        if media is not None else {
            "position": 0, "total": 0,
            "previous_id": None, "next_id": None
        }
    )
    last_move = get_last_active_move()

    media_metadata = []
    if media is not None:
        media_path = Path(media["current_path"])
        if media_path.is_file():
            try:
                media_metadata = get_media_metadata(media_path, media["media_type"])
            except Exception as error:
                media_metadata = [{
                    "title": "Métadonnées",
                    "items": [{"label": "Erreur", "value": str(error)}]
                }]

    return render_template(
        "classify.html",
        media=media,
        destination_folders=get_destination_folders(),
        previous_media_id=navigation["previous_id"],
        next_media_id=navigation["next_id"],
        media_position=navigation["position"],
        pending_total=navigation["total"],
        last_move=last_move,
        media_metadata=media_metadata,
    )


@app.route("/media/<int:media_id>")
def serve_media(media_id):
    media = get_pending_media_by_id(media_id)
    if media is None:
        abort(404)
    path = Path(media["current_path"])
    if not path.is_file():
        abort(404)
    return send_file(path)


@app.route("/move/<int:media_id>", methods=["POST"])
def move(media_id):
    media = get_pending_media_by_id(media_id)
    if media is None:
        abort(404)

    folder_name = request.form.get("folder_name", "").strip()
    if not folder_name:
        flash("Choisis un dossier de destination.", "error")
        return redirect(url_for("classify", media_id=media_id))

    try:
        destination_folder = create_destination_folder(folder_name)
        new_path = move_media(
            source_path=media["current_path"],
            destination_folder=destination_folder
        )
        mark_media_moved(media_id=media_id, new_path=new_path)
        flash(f"{media['filename']} déplacé dans {folder_name}.", "success")

        next_media = get_next_pending_media(after_id=media_id)
        if next_media is not None:
            return redirect(url_for("classify", media_id=next_media["id"]))
    except Exception as error:
        flash(f"Impossible de déplacer le média : {error}", "error")
        return redirect(url_for("classify", media_id=media_id))

    return redirect(url_for("classify"))


@app.route("/undo-last-move", methods=["POST"])
def undo_last_move():
    last_move = get_last_active_move()
    if last_move is None:
        flash("Aucun déplacement à annuler.", "error")
        return redirect(url_for("classify"))

    try:
        undo_move(
            source_path=last_move["source_path"],
            destination_path=last_move["destination_path"]
        )
        mark_move_undone(last_move["id"])
        flash(
            f"{last_move['filename']} a été remis à son emplacement précédent.",
            "success"
        )
        return redirect(url_for("classify", media_id=last_move["media_id"]))
    except Exception as error:
        flash(f"Impossible d'annuler le déplacement : {error}", "error")
        return redirect(url_for("classify"))


@app.route("/create-destination", methods=["POST"])
def create_destination():
    folder_name = request.form.get("folder_name", "")
    current_media_id = request.form.get("current_media_id", type=int)
    try:
        folder = create_destination_folder(folder_name)
        flash(f"Le dossier {folder.name} a été créé.", "success")
    except Exception as error:
        flash(f"Impossible de créer le dossier : {error}", "error")

    if current_media_id is not None:
        return redirect(url_for("classify", media_id=current_media_id))
    return redirect(url_for("classify"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
