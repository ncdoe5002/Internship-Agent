import os

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from ..extensions import db
from ..models.document import Document
from ..services.storage import save_upload
from ..tasks.process_pdf import process_pdf

upload_bp = Blueprint("upload", __name__)


def allowed_file(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


@upload_bp.route("/", methods=["GET"])
@login_required
def index():
    docs = Document.query.order_by(Document.created_at.desc()).limit(20).all()
    return render_template("upload.html", docs=docs)


@upload_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    partner_name = request.form.get("partner_name", "").strip() or None
    file = request.files.get("pdf_file")
    if not file or file.filename == "":
        flash("No file selected.", "warning")
        return redirect(url_for("upload.index"))
    if not allowed_file(file.filename):
        flash("Only PDF files are allowed.", "warning")
        return redirect(url_for("upload.index"))

    file_key = save_upload(file, current_app.config["UPLOAD_FOLDER"])
    doc = Document(
        filename=file.filename,
        file_key=file_key,
        status="PENDING",
        partner_name=partner_name,
        uploaded_by=current_user.id,
    )
    db.session.add(doc)
    db.session.commit()

    process_pdf.delay(doc.id)
    flash(f"'{file.filename}' uploaded — processing in background.", "success")
    return redirect(url_for("upload.index"))
