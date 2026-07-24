import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, send_from_directory
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from ..extensions import db
from ..models.document import Document

from ..tasks.process_pdf import process_pdf
from ..models.agreement import AgmtHeaderStg, AgmtModelsStg, AgmtMdlNormalStg, AgmtCommitment
from datetime import date
from sqlalchemy import text

update_bp = Blueprint("update", __name__)


def allowed_file(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config.get("ALLOWED_EXTENSIONS", {"pdf", "docx", "png", "jpg"})


def _get_agmt_id_for_doc(doc: Document) -> str | None:
    """Return the AGMT_ID stored on the document, or None if not yet extracted."""
    return getattr(doc, "agmt_id", None) or None


# -------------------------------------------------------------------
# 1. THE UPLOAD UI (Clicked from the Dashboard)
# -------------------------------------------------------------------
@update_bp.route("/update/<int:operator_id>", methods=["GET", "POST"])
@login_required
def update_operator(operator_id):
    operator_name = request.args.get("operator_name", "Mobile Operator")

    if request.method == "GET":
        return render_template("update.html", operator_name=operator_name)

    file = request.files.get("pdf_file")

    if not file or not file.filename:
        flash("No file selected.", "warning")
        return redirect(url_for("update.update_operator", operator_id=operator_id))

    raw_filename: str = file.filename

    if not allowed_file(raw_filename):
        flash("Invalid file type.", "warning")
        return redirect(url_for("update.update_operator", operator_id=operator_id))

    filename = secure_filename(raw_filename)

    # Save to app/static/pdfs/ so the iframe can serve it directly
    upload_folder = os.path.join(current_app.root_path, "static", "pdfs")
    os.makedirs(upload_folder, exist_ok=True)

    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)

    # Create the Document record
    doc = Document()
    doc.filename = filename
    # file_key is relative to static/, e.g. "pdfs/filename.pdf"
    doc.file_key = f"pdfs/{filename}"
    doc.status = "PENDING"
    doc.partner_name = operator_name  # carry operator name for baseline lookup
    doc.uploaded_by = current_user.id

    db.session.add(doc)
    db.session.commit()

    # Kick off the Celery background task
    process_task = getattr(process_pdf, "delay", None)
    if callable(process_task):
        process_task(doc.id)

    return redirect(url_for("update.view_processing", doc_id=doc.id))


# -------------------------------------------------------------------
# 2. THE PROCESSING UI (Redirected to after upload)
# -------------------------------------------------------------------
@update_bp.route("/update/processing/<int:doc_id>", methods=["GET"])
@login_required
def view_processing(doc_id):
    doc = Document.query.get_or_404(doc_id)
    return render_template("processing.html", document=doc)


# -------------------------------------------------------------------
# 3. THE STATUS API (Polled by the Processing UI every 2 s)
# -------------------------------------------------------------------
@update_bp.route("/api/update/<int:doc_id>/status", methods=["GET"])
@login_required
def get_status(doc_id):
    doc = Document.query.get_or_404(doc_id)
    return jsonify({
        "document_id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "current_step": doc.current_step or 0,
        "error_message": doc.error_message or None,
    })


# -------------------------------------------------------------------
# 4. EXTRACTED DATA VIEW
# -------------------------------------------------------------------
@update_bp.route("/update/extracted/<int:doc_id>", methods=["GET"])
@login_required
def view_extracted(doc_id):
    doc = Document.query.get_or_404(doc_id)
    agmt_id = _get_agmt_id_for_doc(doc)

    # Fetch staged records extracted from this document
    header = AgmtHeaderStg.query.filter_by(AGMT_ID=agmt_id).first() if agmt_id else None
    models = AgmtModelsStg.query.filter_by(AGMT_ID=agmt_id).all() if agmt_id else []
    rates = AgmtMdlNormalStg.query.filter_by(AGMT_ID=agmt_id).all() if agmt_id else []
    commitments = AgmtCommitment.query.filter_by(AGMT_ID=agmt_id).all() if agmt_id else []

    # Count displayable fields
    total_fields = 0
    if header:
        total_fields += 6  # header table shows 6 columns
    total_fields += len(models) * 3
    total_fields += len(rates) * 4
    total_fields += len(commitments) * 4

    confidence_score = doc.confidence_score if doc.confidence_score is not None else 0

    return render_template(
        "extracted.html",
        document=doc,
        current_doc=None,   # No baseline document pane yet
        header=header,
        models=models,
        rates=rates,
        commitments=commitments,
        total_fields=total_fields,
        confidence_score=confidence_score,
    )


# -------------------------------------------------------------------
# 5. PREVIEW SUBMISSION (Manager Queue Preview)
# -------------------------------------------------------------------
@update_bp.route("/update/preview-submission/<int:doc_id>", methods=["GET"])
@login_required
def preview_submission(doc_id):
    doc = Document.query.get_or_404(doc_id)
    agmt_id = _get_agmt_id_for_doc(doc)

    header = AgmtHeaderStg.query.filter_by(AGMT_ID=agmt_id).first() if agmt_id else None
    models = AgmtModelsStg.query.filter_by(AGMT_ID=agmt_id).all() if agmt_id else []
    rates = AgmtMdlNormalStg.query.filter_by(AGMT_ID=agmt_id).all() if agmt_id else []
    commitments = AgmtCommitment.query.filter_by(AGMT_ID=agmt_id).all() if agmt_id else []

    return render_template(
        "preview_submission.html",
        document=doc,
        header=header,
        models=models,
        rates=rates,
        commitments=commitments,
        date_today=date.today().strftime("%d %b %Y"),
    )


# -------------------------------------------------------------------
# 6. SAVE TO DATABASE (STAGING → PROD HOOK)
# -------------------------------------------------------------------
@update_bp.route("/update/submit-to-db", methods=["POST"])
@login_required
def submit_to_db_route_name():
    doc_id = request.form.get("document_id")
    return redirect(url_for("update.upload_signed_report_form", doc_id=doc_id))


# -------------------------------------------------------------------
# 7. UPLOAD SIGNED REPORT
# -------------------------------------------------------------------
@update_bp.route("/update/upload-signed-report/<int:doc_id>", methods=["GET"])
@login_required
def upload_signed_report_form(doc_id):
    doc = Document.query.get_or_404(doc_id)
    agmt_id = _get_agmt_id_for_doc(doc)
    header = AgmtHeaderStg.query.filter_by(AGMT_ID=agmt_id).first() if agmt_id else None
    dynamic_operator_name = header.SENDER if header else "Unknown Operator"

    return render_template(
        "upload_signed_report.html",
        operator_name=dynamic_operator_name,
        document_id=doc_id,
    )


@update_bp.route("/update/upload-signed-report/<int:doc_id>", methods=["POST"])
@login_required
def upload_signed_report(doc_id):
    file = request.files.get("signed_pdf")

    if not file or not file.filename:
        flash("No file selected.", "warning")
        return redirect(request.url)

    filename = secure_filename(file.filename)
    unique_filename = f"signed_{doc_id}_{filename}"

    upload_folder = os.path.join(current_app.root_path, "static", "pdfs")
    os.makedirs(upload_folder, exist_ok=True)

    file.save(os.path.join(upload_folder, unique_filename))
    return redirect(url_for("update.final_review", doc_id=doc_id, signed_filename=unique_filename))


# -------------------------------------------------------------------
# 8. FINAL SPLIT-PANE PUBLISH VIEW
# -------------------------------------------------------------------
@update_bp.route("/update/final-review/<int:doc_id>/<signed_filename>", methods=["GET"])
@login_required
def final_review(doc_id, signed_filename):
    doc = Document.query.get_or_404(doc_id)
    agmt_id = _get_agmt_id_for_doc(doc)

    header = AgmtHeaderStg.query.filter_by(AGMT_ID=agmt_id).first() if agmt_id else None
    models = AgmtModelsStg.query.filter_by(AGMT_ID=agmt_id).all() if agmt_id else []
    rates = AgmtMdlNormalStg.query.filter_by(AGMT_ID=agmt_id).all() if agmt_id else []

    return render_template(
        "submission.html",
        document=doc,
        header=header,
        models=models,
        rates=rates,
        signed_filename=signed_filename,
    )


# -------------------------------------------------------------------
# FILE SERVING HELPERS
# -------------------------------------------------------------------
@update_bp.route("/update/serve-signed-pdf/<filename>")
@login_required
def serve_signed_pdf(filename):
    upload_folder = os.path.join(current_app.root_path, "static", "pdfs")
    return send_from_directory(upload_folder, filename)


@update_bp.route("/update/serve-pdf/<int:doc_id>")
@login_required
def serve_pdf(doc_id):
    doc = Document.query.get_or_404(doc_id)
    file_key = getattr(doc, "file_key", None)
    if not file_key:
        flash("Document has no associated file.", "warning")
        return redirect(url_for("dashboard.index"))

    filename = os.path.basename(file_key)
    upload_folder = os.path.join(current_app.root_path, "static", "pdfs")
    return send_from_directory(upload_folder, filename)


# -------------------------------------------------------------------
# 9. PUBLISH TO PRODUCTION
# -------------------------------------------------------------------
@update_bp.route("/update/publish-to-production", methods=["POST"])
@login_required
def publish_to_production():
    doc_id = request.form.get("document_id")
    if not doc_id:
        flash("No document id provided.", "warning")
        return redirect(url_for("update.update_operator", operator_id=1))

    doc = Document.query.get(doc_id)
    if doc:
        doc.status = "PUBLISHED"
        db.session.commit()

    return render_template("final_publish.html", document=doc)


# -------------------------------------------------------------------
# DEV UTILITY: SEED DUMMY DATA (kept for local testing)
# -------------------------------------------------------------------
@update_bp.route("/update/seed", methods=["GET"])
def seed_dummy_data():
    try:
        db.session.execute(text('ALTER TABLE "AGMT_MDL_NORMAL_STG" ALTER COLUMN "CHARGE_FIELD" TYPE NUMERIC(18,4);'))
        db.session.commit()
    except Exception:
        db.session.rollback()

    AgmtCommitment.query.filter_by(AGMT_ID="SEED-001").delete()
    AgmtMdlNormalStg.query.filter_by(AGMT_ID="SEED-001").delete()
    AgmtModelsStg.query.filter_by(AGMT_ID="SEED-001").delete()
    AgmtHeaderStg.query.filter_by(AGMT_ID="SEED-001").delete()
    db.session.commit()

    header = AgmtHeaderStg()
    header.AGMT_ID = "SEED-001"
    header.SENDER = "Operator A"
    header.RP = "Operator B"
    header.AGMT_STATUS = "PENDING"
    header.START_DATE = date(2026, 1, 1)
    header.END_DATE = date(2026, 12, 31)
    header.CURRENCY_CODE = "EUR"
    header.REMARKS = "Seeded test record."
    db.session.add(header)

    model = AgmtModelsStg()
    model.AGMT_ID = "SEED-001"
    model.MODEL_SEQ = 1
    model.MODEL_TYPE = "STANDARD"
    model.MODEL_NAME = "Standard Data & Voice"
    db.session.add(model)

    for rec_type, charge_field in [
        ("SMS-MT Rate", 0.0205),
        ("GPRS Data Rate", 0.0140),
        ("Voice MOC Rate", 0.0068),
    ]:
        rate = AgmtMdlNormalStg()
        rate.AGMT_ID = "SEED-001"
        rate.MODEL_SEQ = 1
        rate.REC_TYPE = rec_type
        rate.RATE_CURRENCY = "EUR"
        rate.CHARGE_FIELD = charge_field
        db.session.add(rate)

    for name, ctype, direction, amount in [
        ("Inbound Data Vol", "Volume", "Inbound", 500000.00),
        ("Outbound Spend", "Financial", "Outbound", 15000.00),
    ]:
        c = AgmtCommitment()
        c.AGMT_ID = "SEED-001"
        c.COMMITMENT_NAME = name
        c.COMMITMENT_TYPE = ctype
        c.DIRECTION = direction
        c.AMOUNT = amount
        db.session.add(c)

    db.session.commit()
    return "Seeded SEED-001 records successfully."
