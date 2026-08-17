"""
Update Blueprint
----------------
Handles the end-to-end pipeline for updating roaming agreements.
This includes file upload, background extraction triggering, data review, 
signed report management, and final promotion of data from staging to production.
"""

import os
import json
import subprocess
from datetime import date, datetime, timezone

from flask import (
    Blueprint, render_template, request, redirect, 
    url_for, flash, jsonify, current_app, send_from_directory
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from sqlalchemy import text

# Local Application Imports
from ..extensions import db
from ..utils import extract_text_from_file
from app.blueprints.jobs import process_contract_task 
from ..models.document import Document
from ..models.mno import Mno
from ..models.agreement import AgmtHeaderStg, AgmtModelsStg, AgmtMdlNormalStg, AgmtCommitment
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

update_bp = Blueprint("update", __name__)


# =====================================================================
# HELPER FUNCTIONS
# =====================================================================

def allowed_file(filename: str) -> bool:
    """
    Validates if the uploaded file extension is permitted.
    
    Args:
        filename (str): The name of the file to check.
        
    Returns:
        bool: True if the file extension is in the allowed list, False otherwise.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config.get("ALLOWED_EXTENSIONS", {"pdf", "docx", "png", "jpg"})


def _get_agmt_id_for_doc(doc: Document) -> str | None:
    """
    Retrieves the parsed Agreement ID from a Document record.
    
    Args:
        doc (Document): The Document database instance.
        
    Returns:
        str | None: The Agreement ID if it exists, otherwise None.
    """
    return getattr(doc, "agmt_id", None) or None


def convert_docx_to_pdf(docx_path: str) -> str | None:
    """
    Converts a .docx file to .pdf utilizing LibreOffice in headless mode.
    This allows the application to render DOCX files natively in the browser via an iframe.
    
    Args:
        docx_path (str): Absolute path to the original .docx file.
        
    Returns:
        str | None: Path to the generated .pdf file, or None if conversion fails.
    """
    if not docx_path.endswith('.docx'):
        return docx_path
        
    output_dir = os.path.dirname(docx_path)
    
    try:
        # Execute LibreOffice headless conversion as a subprocess
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


# =====================================================================
# ROUTE DEFINITIONS
# =====================================================================

# -------------------------------------------------------------------
# 1. FILE UPLOAD UI & INGESTION
# -------------------------------------------------------------------
@update_bp.route("/update/<int:operator_id>", methods=["GET", "POST"])
@login_required
def update_operator(operator_id):
    """
    Renders the upload interface and handles incoming contract files.
    Initiates the background extraction pipeline (Celery) upon successful upload.
    """
    operator_name = request.args.get("operator_name", "Mobile Operator")

    # Render initial upload view
    if request.method == "GET":
        return render_template("update.html", operator_name=operator_name)

    file = request.files.get("pdf_file")

    # Validate file presence and type
    if not file or not file.filename:
        flash("No file selected.", "warning")
        return redirect(url_for("update.update_operator", operator_id=operator_id))

    raw_filename: str = file.filename

    if not allowed_file(raw_filename):
        flash("Invalid file type.", "warning")
        return redirect(url_for("update.update_operator", operator_id=operator_id))

    filename = secure_filename(raw_filename)

    # Prepare storage directory and save file
    upload_folder = os.path.join(current_app.root_path, "static", "pdfs")
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)

    # Intercept DOCX files to generate a web-viewable PDF
    if filename.endswith('.docx'):
        convert_docx_to_pdf(file_path)

    # Initial text extraction (Docling handles the original format)
    document_text = extract_text_from_file(file_path)

    # Initialize Document tracking record in the database
    doc = Document()
    doc.filename = filename
    doc.file_key = f"pdfs/{filename}"
    doc.status = "PENDING"
    doc.partner_name = operator_name
    doc.uploaded_by = current_user.id

    db.session.add(doc)
    db.session.commit()

    # Dispatch extraction job to asynchronous Celery worker
    process_contract_task.delay(doc.id, document_text) # type: ignore

    return redirect(url_for("update.view_processing", doc_id=doc.id))


# -------------------------------------------------------------------
# 2. PROCESSING UI (LOADING SCREEN)
# -------------------------------------------------------------------
@update_bp.route("/update/processing/<int:doc_id>", methods=["GET"])
@login_required
def view_processing(doc_id):
    """Renders the loading screen while the Celery worker parses the document."""
    doc = Document.query.get_or_404(doc_id)
    return render_template("processing.html", document=doc)


# -------------------------------------------------------------------
# 3. BACKGROUND TASK STATUS API
# -------------------------------------------------------------------
@update_bp.route("/api/update/<int:doc_id>/status", methods=["GET"])
def get_status(doc_id):
    """
    JSON API endpoint polled by the processing UI to track Celery task progress.
    """
    doc = Document.query.get_or_404(doc_id)
    return jsonify({
        "status": doc.status,
        "current_step": doc.current_step,
        "error_message": doc.error_message
    })


# -------------------------------------------------------------------
# 4. EXTRACTED DATA REVIEW UI
# -------------------------------------------------------------------
@update_bp.route("/update/extracted/<int:doc_id>", methods=["GET"])
@login_required
def view_extracted(doc_id):
    """
    Retrieves the AI-extracted data payload and displays it alongside 
    the baseline (current production) data for manual verification and edits.
    """
    doc = Document.query.get_or_404(doc_id)
    raw_data = doc.extracted_data or {}
    
    header_dict = raw_data.get("header", {})
    models = raw_data.get("model", [])
    rates = raw_data.get("normal_model", [])
    commitments = raw_data.get("commitment", [])

    current_contract_data = None
    
    # Query existing baseline data to populate the comparison view
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
# 5. DRAFT SAVING API
# -------------------------------------------------------------------
@update_bp.route("/api/update/<int:doc_id>/save-draft", methods=["POST"])
@login_required
def save_draft(doc_id):
    """
    API endpoint that accepts flattened JSON from the review UI and
    overwrites the Document's extracted_data with user-corrected values.
    """
    doc = Document.query.get_or_404(doc_id)
    updated_json = request.get_json()
    
    if not updated_json:
        return jsonify({"success": False, "error": "No data provided"}), 400

    doc.extracted_data = updated_json
    db.session.commit()
    return jsonify({"success": True, "message": "Draft updated successfully"})


# -------------------------------------------------------------------
# 6. MANAGER QUEUE PREVIEW
# -------------------------------------------------------------------
@update_bp.route("/update/preview-submission/<int:doc_id>", methods=["GET"])
@login_required
def preview_submission(doc_id):
    """
    Displays a final staging preview summarizing all corrected data 
    before transitioning to the formal report signing phase.
    """
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
# 7. WORKFLOW HOOK: STAGING TO SIGNATURE
# -------------------------------------------------------------------
@update_bp.route("/update/submit-to-db", methods=["POST"])
@login_required
def submit_to_db_route_name():
    """Redirect handler that routes the user to the signed report upload."""
    doc_id = request.form.get("document_id")
    return redirect(url_for("update.upload_signed_report_form", doc_id=doc_id))


# -------------------------------------------------------------------
# 8. UPLOAD SIGNED REPORT
# -------------------------------------------------------------------
@update_bp.route("/update/upload-signed-report/<int:doc_id>", methods=["GET"])
@login_required
def upload_signed_report_form(doc_id):
    """Renders the UI for uploading the manually signed management report."""
    doc = Document.query.get_or_404(doc_id)
    
    raw_data = doc.extracted_data or {}
    header_dict = raw_data.get("header", {})
    
    # Check for Pydantic v2 lowercase keys or legacy uppercase
    sender_data = header_dict.get("sender") or header_dict.get("SENDER")
    
    # Handle nested dictionary structures generated by the orchestrator mapping logic
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
    """Handles the physical upload and storage of the signed PDF report."""
    file = request.files.get("signed_pdf")

    if not file or not file.filename:
        flash("No file selected.", "warning")
        return redirect(request.url)

    filename = secure_filename(file.filename)
    unique_filename = f"signed_{doc_id}_{filename}"

    upload_folder = os.path.join(current_app.root_path, "static", "pdfs")
    os.makedirs(upload_folder, exist_ok=True)

    file.save(os.path.join(upload_folder, unique_filename))
    
    # Transition to the final publish review screen
    return redirect(url_for("update.final_review", doc_id=doc_id, signed_filename=unique_filename))


# -------------------------------------------------------------------
# 9. FINAL SPLIT-PANE PUBLISH VIEW
# -------------------------------------------------------------------
@update_bp.route("/update/final-review/<int:doc_id>/<signed_filename>", methods=["GET"])
@login_required
def final_review(doc_id, signed_filename):
    """
    Renders the final confirmation screen, comparing the staged JSON data
    side-by-side with the uploaded signed PDF before committing to Production.
    """
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
# 10. FILE SERVING HELPERS
# -------------------------------------------------------------------
@update_bp.route("/update/serve-signed-pdf/<filename>")
@login_required
def serve_signed_pdf(filename):
    """Securely serves the signed PDF reports from the static directory."""
    upload_folder = os.path.join(current_app.root_path, "static", "pdfs")
    return send_from_directory(upload_folder, filename)


@update_bp.route("/update/serve-pdf/<int:doc_id>")
@login_required
def serve_pdf(doc_id):
    """
    Securely serves the source contract document. Dynamically handles DOCX
    files by substituting the extension to serve the converted PDF instead.
    """
    doc = Document.query.get_or_404(doc_id)
    file_key = getattr(doc, "file_key", None)
    if not file_key:
        flash("Document has no associated file.", "warning")
        return redirect(url_for("dashboard.index"))

    filename = os.path.basename(file_key)
    
    # If the stored record is a .docx, intercept and serve the generated .pdf
    if filename.endswith('.docx'):
        filename = filename.replace('.docx', '.pdf')
        
    upload_folder = os.path.join(current_app.root_path, "static", "pdfs")
    return send_from_directory(upload_folder, filename)


# -------------------------------------------------------------------
# 11. PUBLISH TO PRODUCTION CORE LOGIC (STAGING -> PROD)
# -------------------------------------------------------------------
@update_bp.route("/update/publish-to-production", methods=["POST"])
@login_required
def publish_to_production():
    """
    Core Migration Routine:
    Promotes validated JSON data from the Document record directly into the
    highly-structured PostgreSQL Production schema. It automatically detects
    existing active contracts for the operator and evacuates them to the 
    Archive schema to preserve history and enforce unique constraints.
    """
    doc_id = request.form.get("document_id")
    doc = Document.query.get_or_404(doc_id)

    raw_data = doc.extracted_data
    if not raw_data:
        flash("No extracted data found to publish.", "danger")
        return redirect(url_for("dashboard.index"))

    print("\n" + "="*50, flush=True)
    print(f"🚀 INITIATING DB PUBLISH FOR DOC ID: {doc_id}", flush=True)
    print("📦 RAW EXTRACTED DATA RECEIVED:", flush=True)
    print(json.dumps(raw_data, indent=2), flush=True)
    print("="*50 + "\n", flush=True)

    # Verify MNO context
    mno = Mno.query.filter_by(name=doc.partner_name).first()
    if not mno:
        flash(f"Operator '{doc.partner_name}' not found. Please add them in the MNO dashboard.", "warning")
        return redirect(url_for("dashboard.index"))

    def get_val(section_dict: dict, key: str):
        """
        Internal data scrubber. Safely retrieves values from complex nested
        JSON objects, normalizes case sensitivity, and enforces SQL NULL rules.
        """
        if not isinstance(section_dict, dict):
            return None
            
        val = section_dict.get(key)
        if val is None: # Fallback for legacy uppercase schema matching
            val = section_dict.get(key.upper())
        if val is None: 
            return None
            
        # Extract underlying primitive if nested in a confidence/flag object
        extracted = val.get("value") if isinstance(val, dict) else val
        
        # Enforce strict SQL Null for empty strings to satisfy constraint checkers
        if isinstance(extracted, str) and extracted.strip() == "":
            return None
            
        return extracted

    header_json = raw_data.get("header", {})
    incoming_rp = get_val(header_json, "rp")
    if incoming_rp:
        incoming_rp = str(incoming_rp).strip()

    print(f"🎯 EVACUATION TARGET RP: {incoming_rp}", flush=True)

    # =========================================================
    # PHASE A: BULLETPROOF EVACUATION (PROD -> ARCHIVE)
    # =========================================================
    # Identify any existing active contracts that clash with this MNO
    clashing_headers = []
    clashing_headers.extend(ProdAgmtHeader.query.filter_by(mno_id=mno.id).all())
    
    if incoming_rp:
        # 1. Exact match
        clashing_headers.extend(ProdAgmtHeader.query.filter(ProdAgmtHeader.RP == incoming_rp).all())
        # 2. Trim match (catches trailing spaces)
        clashing_headers.extend(ProdAgmtHeader.query.filter(db.func.trim(ProdAgmtHeader.RP) == incoming_rp).all())
        # 3. Case-insensitive match (catches capitalization differences)
        clashing_headers.extend(ProdAgmtHeader.query.filter(ProdAgmtHeader.RP.ilike(incoming_rp)).all())
        # 4. Fallback: Catch any RP that simply starts with the same first 10 characters
        if len(incoming_rp) > 10:
            clashing_headers.extend(ProdAgmtHeader.query.filter(ProdAgmtHeader.RP.ilike(f"{incoming_rp[:10]}%")).all())

    # Deduplicate clashing records so we don't try to archive the same record twice
    unique_clashing = {h.id: h for h in clashing_headers}.values()

    # Deep cascade migration: Relocate headers, models, rates, and commitments to History
    for prod_header in unique_clashing:
        print(f"🧹 ARCHIVING PREVIOUS AGREEMENT ID: {prod_header.id}", flush=True)
        
        # Archive Header
        archive_header_data = {c.name: getattr(prod_header, c.name) for c in prod_header.__table__.columns if c.name not in ['id', 'mno_id']}
        archive_header_data['mno_id'] = prod_header.mno_id
        archive_header = ArchiveAgmtHeader(**archive_header_data)
        db.session.add(archive_header)
        db.session.flush() # Flush to generate surrogate PK for child records

        # Archive Models & cascading Rates
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
                db.session.delete(p_rate) # Remove from active table
            
            db.session.delete(p_model)

        # Archive Commitments
        for p_comm in ProdAgmtCommitment.query.filter_by(header_id=prod_header.id).all():
            comm_data = {c.name: getattr(p_comm, c.name) for c in p_comm.__table__.columns if c.name not in ['id', 'header_id']}
            comm_data['header_id'] = archive_header.id
            a_comm = ArchiveAgmtCommitment(**comm_data)
            db.session.add(a_comm)
            db.session.delete(p_comm)

        db.session.delete(prod_header)

    # Force write evacuation changes before inserting new unique constraints
    db.session.commit()

    # =========================================================
    # PHASE B: INSERT NEW PRODUCTION DATA (JSON -> SQL)
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

    # Normalize JSON arrays (safeguard against singleton dicts)
    models_list = raw_data.get("model", [])
    if isinstance(models_list, dict): models_list = [models_list]
        
    rates_list = raw_data.get("normal_model", [])
    if isinstance(rates_list, dict): rates_list = [rates_list]

    # Process and Map Models & Rates
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

            # Process subset of rates belonging to this specific model
            for rate_json in rates_list:
                r_seq = get_val(rate_json, "model_seq")
                
                # Logic map: Associate rate to model if sequences match, or if it's the default baseline (Seq 1)
                if (str(r_seq) == str(m_seq)) or (r_seq is None and str(m_seq) == "1"):
                    r_type = get_val(rate_json, "rec_type")
                    r_charge = get_val(rate_json, "charge_field")
                    
                    print(f"  👉 RATE FOUND: Type={r_type} | Extracted Charge={r_charge}", flush=True)

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

    # Normalize Commitments and Write
    comms_list = raw_data.get("commitment", [])
    if isinstance(comms_list, dict): comms_list = [comms_list]

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
    # PHASE C: FINALIZE TRANSACTION
    # =========================================================
    # Tag document as fully processed and update Dashboard timestamp
    doc.status = "PUBLISHED"
    mno.last_updated = datetime.now(timezone.utc).strftime('%d %b %Y')
    
    db.session.commit()
    print("✅ DATABASE COMMIT SUCCESSFUL!", flush=True)

    # Serve the success terminal UI
    return render_template("final_publish.html", document=doc)


# -------------------------------------------------------------------
# DEV UTILITY: DATABASE SEEDER (Testing Context)
# -------------------------------------------------------------------
@update_bp.route("/update/seed-baseline", methods=["GET"])
def seed_baseline_data():
    """
    Developer tool used to manually inject hardcoded mock production records 
    for UI testing purposes. Prevents unique constraint crashes by executing 
    an automatic teardown sequence before injecting the fresh payload.
    """
    try:
        mno_name = "Etisalat Misr"
        
        # 1. Resolve or Create the parent MNO entity
        mno = Mno.query.filter_by(name=mno_name).first()
        if not mno:
            mno = Mno()
            mno.name = mno_name
            mno.country = "Egypt"
            mno.currency = "EUR"
            db.session.add(mno)
            db.session.flush()

        # 2. Teardown existing records to respect Unique RP rule
        existing_header = ProdAgmtHeader.query.filter_by(mno_id=mno.id).first()
        if existing_header:
            db.session.delete(existing_header)
            db.session.flush()

        # 3. Seed Production Header Configuration
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

        # 4. Seed associated Rate Model logic
        model = ProdAgmtModels()
        model.header_id = header.id
        model.MODEL_SEQ = 1
        model.MODEL_TYPE = "Incremental Rates"
        model.MODEL_NAME = "Baseline Incremental Rates"
        model.AGMT_ID = "BASE-ETISALAT-2024"
        db.session.add(model)
        db.session.flush()

        # 5. Bulk ingest rate schedules mapped to the model
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