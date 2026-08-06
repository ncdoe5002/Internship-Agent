import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, send_from_directory
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from app.blueprints.jobs import process_contract_task 
from ..utils import extract_text_from_file
from ..extensions import db
from ..models.document import Document
from ..models.agreement import AgmtHeaderStg, AgmtModelsStg, AgmtMdlNormalStg, AgmtCommitment
from datetime import date, datetime, timezone
from sqlalchemy import text

update_bp = Blueprint("update", __name__)

from ..models.mno import Mno
from ..models.agreement_prod import (
    ProdAgmtHeader, 
    ProdAgmtModels, 
    ProdAgmtMdlNormal, 
    ProdAgmtCommitment
)
from ..models.agreement_archive import (
    ArchiveAgmtHeader, 
    ArchiveAgmtModels, 
    ArchiveAgmtMdlNormal, 
    ArchiveAgmtCommitment
)

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

    # 1. Extract text from the saved file
    document_text = extract_text_from_file(file_path)

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

    # TRIGGER THE BACKGROUND TASK!
    process_contract_task.delay(doc.id, document_text) # type: ignore

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
def get_status(doc_id):
    doc = Document.query.get_or_404(doc_id)
    return jsonify({
        "status": doc.status,
        "current_step": doc.current_step,
        "error_message": doc.error_message
    })


# -------------------------------------------------------------------
# 4. EXTRACTED DATA VIEW
# -------------------------------------------------------------------
@update_bp.route("/update/extracted/<int:doc_id>", methods=["GET"])
@login_required
def view_extracted(doc_id):
    doc = Document.query.get_or_404(doc_id)
    
    raw_data = doc.extracted_data or {}
    
    header_dict = raw_data.get("header", {})
    models = [raw_data.get("model")] if raw_data.get("model") else []
    rates = [raw_data.get("normal_model")] if raw_data.get("normal_model") else []
    commitments = [raw_data.get("commitment")] if raw_data.get("commitment") else []

    current_contract_data = None
    if doc.partner_name: 
        mno = Mno.query.filter_by(name=doc.partner_name).first()
        if mno:
            prod_header = ProdAgmtHeader.query.filter_by(mno_id=mno.id).first()
            if prod_header:
                current_contract_data = {
                    "header": {c.name: getattr(prod_header, c.name) for c in prod_header.__table__.columns},
                    "models": ProdAgmtModels.query.filter_by(header_id=prod_header.id).all(),
                    "rates": ProdAgmtMdlNormal.query.join(ProdAgmtModels).filter(ProdAgmtModels.header_id == prod_header.id).all(),
                    "commitments": ProdAgmtCommitment.query.filter_by(header_id=prod_header.id).all()
                }

    total_fields = sum([len(header_dict), len(models) * 3, len(rates) * 4, len(commitments) * 4])

    return render_template(
        "extracted.html",
        document=doc,
        current_doc=current_contract_data,
        header=header_dict,
        models=models,
        rates=rates,
        commitments=commitments,
        total_fields=total_fields,
        confidence_score=doc.confidence_score or 0,
    )


# -------------------------------------------------------------------
# 5. PREVIEW SUBMISSION (Manager Queue Preview)
# -------------------------------------------------------------------
@update_bp.route("/update/preview-submission/<int:doc_id>", methods=["GET"])
@login_required
def preview_submission(doc_id):
    doc = Document.query.get_or_404(doc_id)
    
    raw_data = doc.extracted_data or {}
    header_dict = raw_data.get("header", {})
    models = [raw_data.get("model")] if raw_data.get("model") else []
    rates = [raw_data.get("normal_model")] if raw_data.get("normal_model") else []
    commitments = [raw_data.get("commitment")] if raw_data.get("commitment") else []

    return render_template(
        "preview_submission.html",
        document=doc,
        header=header_dict,
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
    
    raw_data = doc.extracted_data or {}
    header_dict = raw_data.get("header", {})
    
    # Check for Pydantic v2 lowercase keys or legacy uppercase
    sender_data = header_dict.get("sender") or header_dict.get("SENDER")
    
    # Handles nested dictionary structure if the orchestrator mapped flags
    if isinstance(sender_data, dict):
        sender = sender_data.get("value")
    else:
        sender = sender_data

    dynamic_operator_name = sender or doc.partner_name or "Unknown Operator"

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
    
    raw_data = doc.extracted_data or {}
    header_dict = raw_data.get("header", {})
    models = [raw_data.get("model")] if raw_data.get("model") else []
    rates = [raw_data.get("normal_model")] if raw_data.get("normal_model") else []

    return render_template(
        "submission.html",
        document=doc,
        header=header_dict,
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
# 9. PUBLISH TO PRODUCTION (Evacuate to Archive)
# -------------------------------------------------------------------
@update_bp.route("/update/publish-to-production", methods=["POST"])
@login_required
def publish_to_production():
    doc_id = request.form.get("document_id")
    doc = Document.query.get_or_404(doc_id)

    raw_data = doc.extracted_data
    if not raw_data:
        flash("No extracted data found to publish.", "danger")
        return redirect(url_for("dashboard.index"))

    mno = Mno.query.filter_by(name=doc.partner_name).first()
    if not mno:
        flash(f"Operator '{doc.partner_name}' not found. Please add them in the MNO dashboard.", "warning")
        return redirect(url_for("dashboard.index"))

    # 1. EVACUATE EXISTING PROD DATA TO ARCHIVE
    prod_header = ProdAgmtHeader.query.filter_by(mno_id=mno.id).first()
    if prod_header:
        archive_header_data = {c.name: getattr(prod_header, c.name) for c in prod_header.__table__.columns if c.name not in ['id', 'mno_id']}
        archive_header_data['mno_id'] = mno.id
        archive_header = ArchiveAgmtHeader(**archive_header_data)
        db.session.add(archive_header)
        db.session.flush()

        # Archive Models & Rates
        for p_model in ProdAgmtModels.query.filter_by(header_id=prod_header.id).all():
            model_data = {
                c.name: getattr(p_model, c.name) 
                for c in p_model.__table__.columns 
                if c.name not in ['id', 'header_id']
            }
            model_data['header_id'] = archive_header.id
            a_model = ArchiveAgmtModels(**model_data)
            
            db.session.add(a_model)
            db.session.flush()

            for p_rate in ProdAgmtMdlNormal.query.filter_by(model_id=p_model.id).all():
                rate_data = {
                    c.name: getattr(p_rate, c.name) 
                    for c in p_rate.__table__.columns 
                    if c.name not in ['id', 'model_id']
                }
                rate_data['model_id'] = a_model.id
                a_rate = ArchiveAgmtMdlNormal(**rate_data)
                
                db.session.add(a_rate)

        # Archive Commitments
        for p_comm in ProdAgmtCommitment.query.filter_by(header_id=prod_header.id).all():
            a_comm = ArchiveAgmtCommitment(**{
                "header_id": archive_header.id,
                "COMMITMENT_NAME": p_comm.COMMITMENT_NAME,
                "COMMITMENT_TYPE": p_comm.COMMITMENT_TYPE,
                "DIRECTION": p_comm.DIRECTION,
                "AMOUNT": p_comm.AMOUNT,
                "CAPTURE_RATE_PCT": p_comm.CAPTURE_RATE_PCT,
                "PARTY_FROM": p_comm.PARTY_FROM,
                "PARTY_TO": p_comm.PARTY_TO
            })
            db.session.add(a_comm)

        db.session.delete(prod_header)
        db.session.flush()

    # 2. Extract values cleanly if the dict is nested with 'value' properties from frontend editing
    def get_val(section_dict, key):
        val = section_dict.get(key)
        return val.get("value") if isinstance(val, dict) else val

    header_json = raw_data.get("header", {})
    new_prod_header = ProdAgmtHeader(**{
        "mno_id": mno.id,
        "AGMT_ID": get_val(header_json, "agmt_id"),
        "SENDER": get_val(header_json, "sender"),
        "RP": get_val(header_json, "rp"),
        "CURRENCY_CODE": get_val(header_json, "currency_code"),
        "START_DATE": get_val(header_json, "start_date"),
        "END_DATE": get_val(header_json, "end_date"),
        "REMARKS": get_val(header_json, "remarks")
    })
    db.session.add(new_prod_header)
    db.session.flush()

    model_json = raw_data.get("model", {})
    if model_json and get_val(model_json, "model_name"):
        p_model = ProdAgmtModels(**{
            "header_id": new_prod_header.id,
            "MODEL_SEQ": get_val(model_json, "model_seq") or 1,
            "MODEL_TYPE": get_val(model_json, "model_type"),
            "MODEL_NAME": get_val(model_json, "model_name"),
            "AGMT_ID": get_val(model_json, "agmt_id") or get_val(header_json, "agmt_id")
        })
        db.session.add(p_model)
        db.session.flush()

        rate_json = raw_data.get("normal_model", {})
        if rate_json:
            p_rate = ProdAgmtMdlNormal(**{
                "model_id": p_model.id,
                "REC_TYPE": get_val(rate_json, "rec_type"),
                "ZONE_CODE": get_val(rate_json, "zone_code"),
                "RATE_CURRENCY": get_val(rate_json, "rate_currency"),
                "PRA_RATE_TYPE": get_val(rate_json, "pra_rate_type"),
                "DISC_RATE_PERC": get_val(rate_json, "disc_rate_perc")
            })
            db.session.add(p_rate)

    comm_json = raw_data.get("commitment", {})
    if comm_json and get_val(comm_json, "commitment_name"):
        p_comm = ProdAgmtCommitment(**{
            "header_id": new_prod_header.id,
            "COMMITMENT_NAME": get_val(comm_json, "commitment_name"),
            "COMMITMENT_TYPE": get_val(comm_json, "commitment_type"),
            "DIRECTION": get_val(comm_json, "direction"),
            "AMOUNT": get_val(comm_json, "amount"),
            "PARTY_FROM": get_val(comm_json, "party_from"),
            "PARTY_TO": get_val(comm_json, "party_to")
        })
        db.session.add(p_comm)

    # 3. FINALIZE TRANSACTION
    doc.status = "PUBLISHED"
    mno.last_updated = datetime.now(timezone.utc).strftime('%d %b %Y')
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


@update_bp.route("/api/update/<int:doc_id>/save-draft", methods=["POST"])
@login_required
def save_draft(doc_id):
    doc = Document.query.get_or_404(doc_id)
    updated_json = request.get_json()
    
    if not updated_json:
        return jsonify({"success": False, "error": "No data provided"}), 400

    doc.extracted_data = updated_json
    db.session.commit()
    return jsonify({"success": True, "message": "Draft updated successfully"})