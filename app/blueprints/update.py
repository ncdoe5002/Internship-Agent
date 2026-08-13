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
import json
import subprocess

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
    return getattr(doc, "agmt_id", None) or None

# === ADD THE CONVERSION FUNCTION HERE ===
def convert_docx_to_pdf(docx_path):
    """
    Converts a .docx file to .pdf using LibreOffice in headless mode.
    Returns the path to the newly created PDF.
    """
    if not docx_path.endswith('.docx'):
        return docx_path
        
    output_dir = os.path.dirname(docx_path)
    
    try:
        subprocess.run([
            'libreoffice', 
            '--headless', 
            '--convert-to', 
            'pdf', 
            docx_path, 
            '--outdir', 
            output_dir
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        pdf_path = docx_path.replace('.docx', '.pdf')
        print(f"Successfully created viewable PDF: {pdf_path}")
        return pdf_path
        
    except subprocess.CalledProcessError as e:
        print(f"Failed to convert DOCX to PDF: {e}")
        return None

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

    # === NEW DOCX TO PDF CONVERSION CALL ===
    if filename.endswith('.docx'):
        convert_docx_to_pdf(file_path)

    # 1. Extract text from the saved file (Docling will handle the original .docx)
    document_text = extract_text_from_file(file_path)

    # Create the Document record
    doc = Document()
    doc.filename = filename
    # file_key is relative to static/, e.g. "pdfs/filename.pdf" or "pdfs/filename.docx"
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
    models = raw_data.get("model", [])
    rates = raw_data.get("normal_model", [])
    commitments = raw_data.get("commitment", [])

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
    models = raw_data.get("model", [])
    rates = raw_data.get("normal_model", [])
    commitments = raw_data.get("commitment", [])    

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
    
    # === DOCX TO PDF FIX ===
    # If the database record is a .docx, intercept it and serve the converted .pdf instead
    if filename.endswith('.docx'):
        filename = filename.replace('.docx', '.pdf')
        
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

    # === DEBUG LOG: THE RAW JSON PAYLOAD ===
    print("\n" + "="*50, flush=True)
    print(f"🚀 INITIATING DB PUBLISH FOR DOC ID: {doc_id}", flush=True)
    print("📦 RAW EXTRACTED DATA RECEIVED:", flush=True)
    print(json.dumps(raw_data, indent=2), flush=True)
    print("="*50 + "\n", flush=True)

    mno = Mno.query.filter_by(name=doc.partner_name).first()
    if not mno:
        flash(f"Operator '{doc.partner_name}' not found. Please add them in the MNO dashboard.", "warning")
        return redirect(url_for("dashboard.index"))

    # Helper to safely extract values, prevent AttributeError, and sanitize empty strings
    def get_val(section_dict, key):
        if not isinstance(section_dict, dict):
            return None
            
        val = section_dict.get(key)
        if val is None: # Fallback to uppercase keys
            val = section_dict.get(key.upper())
        if val is None: # Safe exit if field doesn't exist
            return None
            
        # Extract the actual value whether it's nested in a dict or flat
        extracted = val.get("value") if isinstance(val, dict) else val
        
        # THE FIX: If the value is an empty string, convert it to a true SQL NULL
        if isinstance(extracted, str) and extracted.strip() == "":
            return None
            
        return extracted

    header_json = raw_data.get("header", {})
    incoming_rp = get_val(header_json, "rp")
    if incoming_rp:
        incoming_rp = str(incoming_rp).strip()

    print(f"🎯 EVACUATION TARGET RP: {incoming_rp}", flush=True)

    # =========================================================
    # 1. BULLETPROOF EVACUATION 
    # =========================================================
    clashing_headers = []
    clashing_headers.extend(ProdAgmtHeader.query.filter_by(mno_id=mno.id).all())
    
    if incoming_rp:
        # 1. Exact match (bypasses ilike wildcard issues)
        clashing_headers.extend(ProdAgmtHeader.query.filter(ProdAgmtHeader.RP == incoming_rp).all())
        # 2. Trim match (catches old DB records with sneaky trailing spaces)
        clashing_headers.extend(ProdAgmtHeader.query.filter(db.func.trim(ProdAgmtHeader.RP) == incoming_rp).all())

    unique_clashing = {h.id: h for h in clashing_headers}.values()

    for prod_header in unique_clashing:
        print(f"🧹 ARCHIVING PREVIOUS AGREEMENT ID: {prod_header.id}", flush=True)
        archive_header_data = {c.name: getattr(prod_header, c.name) for c in prod_header.__table__.columns if c.name not in ['id', 'mno_id']}
        archive_header_data['mno_id'] = prod_header.mno_id
        archive_header = ArchiveAgmtHeader(**archive_header_data)
        db.session.add(archive_header)
        db.session.flush()

        for p_model in ProdAgmtModels.query.filter_by(header_id=prod_header.id).all():
            model_data = {c.name: getattr(p_model, c.name) for c in p_model.__table__.columns if c.name not in ['id', 'header_id']}
            model_data['header_id'] = archive_header.id
            a_model = ArchiveAgmtModels(**model_data)
            db.session.add(a_model)
            db.session.flush()

            for p_rate in ProdAgmtMdlNormal.query.filter_by(model_id=p_model.id).all():
                rate_data = {c.name: getattr(p_rate, c.name) for c in p_rate.__table__.columns if c.name not in ['id', 'model_id']}
                rate_data['model_id'] = a_model.id
                a_rate = ArchiveAgmtMdlNormal(**rate_data)
                db.session.add(a_rate)
                db.session.delete(p_rate)
            
            db.session.delete(p_model)

        for p_comm in ProdAgmtCommitment.query.filter_by(header_id=prod_header.id).all():
            comm_data = {c.name: getattr(p_comm, c.name) for c in p_comm.__table__.columns if c.name not in ['id', 'header_id']}
            comm_data['header_id'] = archive_header.id
            a_comm = ArchiveAgmtCommitment(**comm_data)
            db.session.add(a_comm)
            db.session.delete(p_comm)

        db.session.delete(prod_header)

    db.session.commit()

    # =========================================================
    # 2. INSERT NEW PROD DATA
    # =========================================================
    print("📝 INSERTING NEW HEADER...", flush=True)
    new_prod_header = ProdAgmtHeader(**{
        "mno_id": mno.id,
        "AGMT_ID": get_val(header_json, "agmt_id"),
        "SENDER": get_val(header_json, "sender"),
        "RP": incoming_rp,
        "CURRENCY_CODE": get_val(header_json, "currency_code"),
        "START_DATE": get_val(header_json, "start_date"),
        "END_DATE": get_val(header_json, "end_date"),
        "REMARKS": get_val(header_json, "remarks")
    })
    db.session.add(new_prod_header)
    db.session.flush()

    models_list = raw_data.get("model", [])
    if isinstance(models_list, dict):
        models_list = [models_list]
        
    rates_list = raw_data.get("normal_model", [])
    if isinstance(rates_list, dict):
        rates_list = [rates_list]

    for model_json in models_list:
        m_name = get_val(model_json, "model_name")
        m_type = get_val(model_json, "model_type")
        m_seq = get_val(model_json, "model_seq") or 1
        
        print(f"📊 INSERTING MODEL: Seq={m_seq}, Name={m_name}, Type={m_type}", flush=True)
        
        if m_name or m_type:
            p_model = ProdAgmtModels(**{
                "header_id": new_prod_header.id,
                "MODEL_SEQ": m_seq,
                "MODEL_TYPE": m_type,
                "MODEL_NAME": m_name,
                "AGMT_ID": get_val(model_json, "agmt_id") or get_val(header_json, "agmt_id")
            })
            db.session.add(p_model)
            db.session.flush()

            for rate_json in rates_list:
                r_seq = get_val(rate_json, "model_seq")
                
                if (str(r_seq) == str(m_seq)) or (r_seq is None and str(m_seq) == "1"):
                    r_type = get_val(rate_json, "rec_type")
                    r_charge = get_val(rate_json, "charge_field")
                    
                    # === DEBUG LOG: RATE INSERTION ===
                    print(f"  👉 RATE FOUND: Type={r_type} | Extracted Charge={r_charge}", flush=True)
                    print(f"🔥 SQLALCHEMY THINKS CHARGE_FIELD IS: {ProdAgmtMdlNormal.CHARGE_FIELD.type}", flush=True)

                    if r_type or (r_charge is not None):
                        p_rate = ProdAgmtMdlNormal(**{
                            "model_id": p_model.id,
                            "REC_TYPE": r_type,
                            "ZONE_CODE": get_val(rate_json, "zone_code"),
                            "RATE_CURRENCY": get_val(rate_json, "rate_currency"),
                            "PRA_RATE_TYPE": get_val(rate_json, "pra_rate_type"),
                            "DISC_RATE_PERC": get_val(rate_json, "disc_rate_perc"),
                            "CHARGE_FIELD": r_charge
                        })
                        db.session.add(p_rate)

    comms_list = raw_data.get("commitment", [])
    if isinstance(comms_list, dict):
        comms_list = [comms_list]

    for comm_json in comms_list:
        c_name = get_val(comm_json, "commitment_name")
        c_amt = get_val(comm_json, "amount")
        
        print(f"🤝 INSERTING COMMITMENT: Name={c_name}, Amount={c_amt}", flush=True)

        if c_name or c_amt:
            p_comm = ProdAgmtCommitment(**{
                "header_id": new_prod_header.id,
                "COMMITMENT_NAME": c_name,
                "COMMITMENT_TYPE": get_val(comm_json, "commitment_type"),
                "DIRECTION": get_val(comm_json, "direction"),
                "AMOUNT": c_amt,
                "PARTY_FROM": get_val(comm_json, "party_from"),
                "PARTY_TO": get_val(comm_json, "party_to")
            })
            db.session.add(p_comm)

    # =========================================================
    # 3. FINALIZE TRANSACTION
    # =========================================================
    doc.status = "PUBLISHED"
    mno.last_updated = datetime.now(timezone.utc).strftime('%d %b %Y')
    db.session.commit()
    print("✅ DATABASE COMMIT SUCCESSFUL!", flush=True)

    return render_template("final_publish.html", document=doc)


# -------------------------------------------------------------------
# DEV UTILITY: SEED BASELINE PROD DATA FOR "ETISALAT MISR"
# -------------------------------------------------------------------
@update_bp.route("/update/seed-baseline", methods=["GET"])
def seed_baseline_data():
    try:
        mno_name = "Etisalat Misr"
        
        # 1. Create or get the MNO[cite: 11]
        mno = Mno.query.filter_by(name=mno_name).first()
        if not mno:
            mno = Mno()
            mno.name = mno_name
            mno.country = "Egypt"
            mno.currency = "EUR"
            db.session.add(mno)
            db.session.flush() # Get the mno.id immediately

        # 2. Clear any existing Prod Header to avoid the unique "RP" constraint error[cite: 7]
        existing_header = ProdAgmtHeader.query.filter_by(mno_id=mno.id).first()
        if existing_header:
            db.session.delete(existing_header)
            db.session.flush()

        # 3. Create the Production Header[cite: 7, 10]
        header = ProdAgmtHeader()
        header.mno_id = mno.id
        header.AGMT_ID = "BASE-ETISALAT-2024"
        header.SENDER = "Orange EU Affiliates"
        header.RP = "Etisalat Misr"
        header.START_DATE = date(2024, 1, 1)
        header.END_DATE = date(2024, 12, 31)
        header.CURRENCY_CODE = "EUR"
        db.session.add(header)
        db.session.flush()

        # 4. Create the Rate Model[cite: 7, 10]
        model = ProdAgmtModels()
        model.header_id = header.id
        model.MODEL_SEQ = 1
        model.MODEL_TYPE = "Incremental Rates"
        model.MODEL_NAME = "Baseline Incremental Rates"
        model.AGMT_ID = "BASE-ETISALAT-2024"
        db.session.add(model)
        db.session.flush()

        # 5. Insert the Rates to trigger your UI logic[cite: 7, 10]
        rates = []

        sms_rate = ProdAgmtMdlNormal()
        sms_rate.model_id = model.id
        sms_rate.REC_TYPE = "SMS"
        sms_rate.RATE_CURRENCY = "EUR"
        sms_rate.CHARGE_FIELD = 0.035
        rates.append(sms_rate)

        moc_rate = ProdAgmtMdlNormal()
        moc_rate.model_id = model.id
        moc_rate.REC_TYPE = "MOC"
        moc_rate.RATE_CURRENCY = "EUR"
        moc_rate.CHARGE_FIELD = 0.10
        rates.append(moc_rate)

        data_rate = ProdAgmtMdlNormal()
        data_rate.model_id = model.id
        data_rate.REC_TYPE = "DATA"
        data_rate.RATE_CURRENCY = "EUR"
        data_rate.CHARGE_FIELD = 0.020
        rates.append(data_rate)
        
        db.session.bulk_save_objects(rates)
        db.session.commit()

        return f"Successfully seeded baseline data for {mno_name}! You can now test the UI."

    except Exception as e:
        db.session.rollback()
        return f"Error seeding data: {str(e)}"


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