from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for
)

from config import (
    SOURCE_ROOT,
    ensure_directories
)

from core.database import (
    initialize_database,
    get_statistics,
    get_latest_scan_report,
    get_next_pending_media,
    mark_media_moved
)

from core.scanner import scan_directory

from core.organizer import (
    get_destination_folders,
    create_destination_folder,
    move_media
)


app = Flask(__name__)

app.secret_key = "change-this-local-secret-key"


# Initialisation
ensure_directories()
initialize_database()


@app.route("/")
def dashboard():

    statistics = get_statistics()
    scan_report = get_latest_scan_report()
    destination_folders = get_destination_folders()

    return render_template(
        "dashboard.html",
        statistics=statistics,
        scan_report=scan_report,
        destination_folders=destination_folders
    )


@app.route("/scan", methods=["POST"])
def scan():

    try:
        report = scan_directory(SOURCE_ROOT)

        flash(
            f"Scan terminé : {report['image_files']} images, "
            f"{report['video_files']} vidéos et "
            f"{report['ignored_files']} fichiers ignorés.",
            "success"
        )

    except Exception as error:
        flash(f"Erreur pendant le scan : {error}", "error")

    return redirect(url_for("dashboard"))


@app.route("/classify")
def classify():

    media = get_next_pending_media()

    if media is None:
        return render_template(
            "classify.html",
            media=None,
            destination_folders=get_destination_folders()
        )

    return render_template(
        "classify.html",
        media=media,
        destination_folders=get_destination_folders()
    )


@app.route("/media/<int:media_id>")
def serve_media(media_id):

    media = get_next_pending_media()

    if media is None or media["id"] != media_id:
        abort(404)

    path = Path(media["current_path"])

    if not path.is_file():
        abort(404)

    return send_file(path)


@app.route("/move/<int:media_id>", methods=["POST"])
def move(media_id):

    media = get_next_pending_media()

    if media is None or media["id"] != media_id:
        abort(404)

    folder_name = request.form.get("folder_name", "").strip()

    if not folder_name:
        flash("Choisis un dossier de destination.", "error")
        return redirect(url_for("classify"))

    try:
        destination_folder = create_destination_folder(folder_name)

        new_path = move_media(
            source_path=media["current_path"],
            destination_folder=destination_folder
        )

        mark_media_moved(
            media_id=media_id,
            new_path=new_path
        )

        flash(
            f"{media['filename']} déplacé dans {folder_name}.",
            "success"
        )

    except Exception as error:
        flash(f"Impossible de déplacer le média : {error}", "error")

    return redirect(url_for("classify"))


@app.route("/create-destination", methods=["POST"])
def create_destination():

    folder_name = request.form.get("folder_name", "")

    try:
        folder = create_destination_folder(folder_name)

        flash(
            f"Le dossier {folder.name} a été créé.",
            "success"
        )

    except Exception as error:
        flash(f"Impossible de créer le dossier : {error}", "error")

    return redirect(url_for("classify"))


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )