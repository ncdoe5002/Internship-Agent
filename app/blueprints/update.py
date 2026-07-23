import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, send_from_directory
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from ..extensions import db
from ..models.document import Document
from ..services.storage import save_upload
from ..tasks.process_pdf import process_pdf 
from ..models.agreement import AgmtHeaderStg, AgmtModelsStg, AgmtMdlNormalStg, AgmtCommitment
from datetime import date
from sqlalchemy import text

update_bp = Blueprint("update", __name__)

def allowed_file(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config.get("ALLOWED_EXTENSIONS", ["pdf", "docx", "png", "jpg"])

# -------------------------------------------------------------------
# 1. THE UPLOAD UI (Clicked from the Dashboard)
# -------------------------------------------------------------------
@update_bp.route("/update/<int:operator_id>", methods=["GET", "POST"])
@login_required
def update_operator(operator_id):
    # Grab the operator_name from the URL query string
    operator_name = request.args.get('operator_name', 'Mobile Operator')

    # 1. Handle GET Request (Show the form)
    if request.method == "GET":
        return render_template('update.html', operator_name=operator_name)
        
    # 2. Handle POST Request (Process the upload)
    file = request.files.get("pdf_file") 
    
    # Strictly check for None to satisfy modern type checkers
    if not file or not file.filename:
        flash("No file selected.", "warning")
        return redirect(url_for("update.update_operator", operator_id=operator_id))
        
    # Now the linter knows this is strictly a string
    raw_filename: str = file.filename
        
    if not allowed_file(raw_filename):
        flash("Invalid file type.", "warning")
        return redirect(url_for("update.update_operator", operator_id=operator_id))

    # Secure the filename to prevent path traversal attacks
    filename = secure_filename(raw_filename)
    
    # Force the destination to be exactly where your HTML expects it: app/static/pdfs/
    upload_folder = os.path.join(current_app.root_path, 'static', 'pdfs')
    os.makedirs(upload_folder, exist_ok=True) # Creates the folder if it doesn't exist
    
    # Save the physical file to the hard drive
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)
    
    # Create the Document record
    doc = Document()
    doc.filename = filename
    # Prepend 'pdfs/' so url_for('static', filename=doc.file_key) generates the correct URL!
    doc.file_key = f"pdfs/{filename}" 
    doc.status = "PENDING"
    doc.uploaded_by = current_user.id
    
    db.session.add(doc)
    db.session.commit()

    # Start the Celery background task
    process_task = getattr(process_pdf, "delay", None)
    if callable(process_task):
        process_task(doc.id)

    # Success! Redirect to the dynamic processing UI
    return redirect(url_for("update.view_processing", doc_id=doc.id))

# -------------------------------------------------------------------
# 2. THE PROCESSING UI (Redirected to after upload)
# -------------------------------------------------------------------
@update_bp.route("/update/processing/<int:doc_id>", methods=["GET"])
@login_required
def view_processing(doc_id):
    # Now we look up the document, because it has been created!
    doc = Document.query.get_or_404(doc_id)
    
    # Render the dynamic loading bar UI (make sure you save it as processing.html)
    return render_template("processing.html", document=doc)

# -------------------------------------------------------------------
# 3. THE STATUS API (Polled by the Processing UI)
# -------------------------------------------------------------------
@update_bp.route("/api/update/<int:doc_id>/status", methods=["GET"])
@login_required
def get_status(doc_id):
    doc = Document.query.get_or_404(doc_id)
    return jsonify({
        "document_id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "current_step": getattr(doc, 'current_step', 0),
        "error_message": getattr(doc, 'error_message', None)
    })

# -------------------------------------------------------------------
# THE EXTRACTED DATA UI ROUTE
# -------------------------------------------------------------------
@update_bp.route("/update/extracted/<int:doc_id>", methods=["GET"])
@login_required
def view_extracted(doc_id):
    doc = Document.query.get_or_404(doc_id)

    
    
    # Dummy doc for the iframe
    class DummyDoc:
        file_key = "pdfs/dummy.pdf" 
    existing_doc = DummyDoc()

    # Fetch all the connected data from the database
    agmt_id = "AGMT_EXTRACT_001"
    header = AgmtHeaderStg.query.filter_by(AGMT_ID=agmt_id).first()
    models = AgmtModelsStg.query.filter_by(AGMT_ID=agmt_id).all()
    rates = AgmtMdlNormalStg.query.filter_by(AGMT_ID=agmt_id).all()
    commitments = AgmtCommitment.query.filter_by(AGMT_ID=agmt_id).all()

    # Calculate total fields dynamically based on the records found
    total_fields = 0
    if header:
        total_fields += 6 # 6 columns in the header table
    total_fields += len(models) * 3 # 3 columns in the models table
    total_fields += len(rates) * 4 # 4 columns in the rates table
    total_fields += len(commitments) * 4 # 4 columns in the commitments table

    confidence_score = 94 # Placeholder for actual confidence score logic

    return render_template(
        "extracted.html", 
        document=doc, 
        current_doc=existing_doc,
        header=header,
        models=models,
        rates=rates,
        commitments=commitments,
        total_fields=total_fields,          # Pass the new total
        confidence_score=confidence_score
    )

# -------------------------------------------------------------------
# DATABASE SEEDING ROUTE (Run this once to populate all tables)
# -------------------------------------------------------------------
@update_bp.route("/update/seed", methods=["GET"])
def seed_dummy_data():
    # 1. Fix the precision issue on CHARGE_FIELD just in case
    db.session.execute(text('ALTER TABLE "AGMT_MDL_NORMAL_STG" ALTER COLUMN "CHARGE_FIELD" TYPE NUMERIC(18,4);'))
    db.session.commit()

    # 2. Wipe existing data to avoid conflicts
    AgmtCommitment.query.delete()
    AgmtMdlNormalStg.query.delete()
    AgmtModelsStg.query.delete()
    AgmtHeaderStg.query.delete()
    db.session.commit()

    # 3. Seed AGMT_HEADER_STG
    header = AgmtHeaderStg()
    header.AGMT_ID = "AGMT_EXTRACT_001"
    header.SENDER = "Operator A"
    header.RP = "Operator B"
    header.AGMT_STATUS = "PENDING"
    header.START_DATE = date(2026, 1, 1)
    header.END_DATE = date(2026, 12, 31)
    header.CURRENCY_CODE = "EUR"
    header.REMARKS = "Extracted by AI. Pending review."
    db.session.add(header)

    # 4. Seed AGMT_MODELS_STG
    model = AgmtModelsStg()
    model.MODEL_SEQ = 1
    model.AGMT_ID = "AGMT_EXTRACT_001"
    model.MODEL_TYPE = "STANDARD"
    model.MODEL_NAME = "Standard Data & Voice"
    db.session.add(model)

    # 5. Seed AGMT_MDL_NORMAL_STG (The Rates)
    rates = []
    for rec_type, charge_field in [
        ("SMS-MT Rate", 0.0205),
        ("GPRS Data Rate", 0.0140),
        ("Voice MOC Rate", 0.0068),
    ]:
        rate = AgmtMdlNormalStg()
        rate.AGMT_ID = "AGMT_EXTRACT_001"
        rate.MODEL_SEQ = 1
        rate.REC_TYPE = rec_type
        rate.RATE_CURRENCY = "EUR"
        rate.CHARGE_FIELD = charge_field
        rates.append(rate)
    db.session.add_all(rates)

    # 6. Seed AGMT_COMMITMENT (The Commitments)
    commitments = [
        AgmtCommitment(),
        AgmtCommitment()
    ]
    commitments[0].AGMT_ID = "AGMT_EXTRACT_001"
    commitments[0].COMMITMENT_NAME = "Inbound Data Vol"
    commitments[0].COMMITMENT_TYPE = "Volume"
    commitments[0].DIRECTION = "Inbound"
    commitments[0].AMOUNT = 500000.00
    commitments[1].AGMT_ID = "AGMT_EXTRACT_001"
    commitments[1].COMMITMENT_NAME = "Outbound Spend"
    commitments[1].COMMITMENT_TYPE = "Financial"
    commitments[1].DIRECTION = "Outbound"
    commitments[1].AMOUNT = 15000.00
    db.session.add_all(commitments)

    db.session.commit()
    return "Successfully seeded Header, Models, Rates, and Commitments! You can now view the extracted data."

# -------------------------------------------------------------------
# 5. PREVIEW SUBMISSION (Manager Queue Preview)
# -------------------------------------------------------------------
@update_bp.route("/update/preview-submission/<int:doc_id>", methods=["GET"])
@login_required
def preview_submission(doc_id):
    doc = Document.query.get_or_404(doc_id)
    
    # Fetch all the connected data from the database using your dummy ID
    agmt_id = "AGMT_EXTRACT_001"
    header = AgmtHeaderStg.query.filter_by(AGMT_ID=agmt_id).first()
    models = AgmtModelsStg.query.filter_by(AGMT_ID=agmt_id).all()
    rates = AgmtMdlNormalStg.query.filter_by(AGMT_ID=agmt_id).all()
    commitments = AgmtCommitment.query.filter_by(AGMT_ID=agmt_id).all()

    return render_template(
        "preview_submission.html",
        document=doc,
        header=header,
        models=models,
        rates=rates,
        commitments=commitments,
        date_today=date.today().strftime('%d %b %Y')
    )

# -------------------------------------------------------------------
# SAVE TO DATABASE (STAGING TO PROD LOGIC GOES HERE LATER)
# -------------------------------------------------------------------
@update_bp.route("/update/submit-to-db", methods=["POST"])
@login_required
def submit_to_db_route_name():
    doc_id = request.form.get("document_id")
    # In the future, you can update the status of the staging records to 'PENDING_REVIEW' here
    
    # Send user to the upload signed report screen
    return redirect(url_for('update.upload_signed_report_form', doc_id=doc_id))

# -------------------------------------------------------------------
# 6. UPLOAD SIGNED REPORT
# -------------------------------------------------------------------
@update_bp.route("/update/upload-signed-report/<int:doc_id>", methods=["GET"])
@login_required
def upload_signed_report_form(doc_id):
    # Fetch the header data to get the dynamic operator name
    agmt_id = "AGMT_EXTRACT_001" # Using your current dummy ID logic
    header = AgmtHeaderStg.query.filter_by(AGMT_ID=agmt_id).first()
    
    # Extract the SENDER name, with a safe fallback just in case
    dynamic_operator_name = header.SENDER if header else "Unknown Operator"

    return render_template(
        "upload_signed_report.html", 
        operator_name=dynamic_operator_name, 
        document_id=doc_id
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
    
    # Save to the same static/pdfs directory used in step 1
    upload_folder = os.path.join(current_app.root_path, 'static', 'pdfs')
    os.makedirs(upload_folder, exist_ok=True)
    
    file_path = os.path.join(upload_folder, unique_filename)
    file.save(file_path)
    
    # Move to the final review
    return redirect(url_for("update.final_review", doc_id=doc_id, signed_filename=unique_filename))

# -------------------------------------------------------------------
# 7. FINAL SPLIT-PANE PUBLISH VIEW
# -------------------------------------------------------------------
@update_bp.route("/update/final-review/<int:doc_id>/<signed_filename>", methods=["GET"])
@login_required
def final_review(doc_id, signed_filename):
    doc = Document.query.get_or_404(doc_id)
    
    # Fetch staging data again for the left pane
    agmt_id = "AGMT_EXTRACT_001"
    header = AgmtHeaderStg.query.filter_by(AGMT_ID=agmt_id).first()
    models = AgmtModelsStg.query.filter_by(AGMT_ID=agmt_id).all()
    rates = AgmtMdlNormalStg.query.filter_by(AGMT_ID=agmt_id).all()

    return render_template(
        "submission.html",
        document=doc,
        header=header,
        models=models, 
        rates=rates,
        signed_filename=signed_filename
    )

@update_bp.route("/update/serve-signed-pdf/<filename>")
@login_required
def serve_signed_pdf(filename):
    """Serves the signed PDF from the static folder to the embed tag"""
    upload_folder = os.path.join(current_app.root_path, 'static', 'pdfs')
    return send_from_directory(upload_folder, filename)


@update_bp.route("/update/serve-pdf/<int:doc_id>")
@login_required
def serve_pdf(doc_id):
    """Serves a document's file stored in `Document.file_key` by document id."""
    doc = Document.query.get_or_404(doc_id)
    # file_key is stored as relative path under static, e.g. 'pdfs/filename.pdf'
    file_key = getattr(doc, 'file_key', None)
    if not file_key:
        flash("Document has no associated file.", "warning")
        return redirect(url_for('dashboard.index'))

    filename = os.path.basename(file_key)
    upload_folder = os.path.join(current_app.root_path, 'static', 'pdfs')
    return send_from_directory(upload_folder, filename)

@update_bp.route("/update/publish-to-production", methods=["POST"])
@login_required
def publish_to_production():
    """
    Final publishing endpoint. Reads `document_id` from the POST form,
    performs any DB publish logic, and renders the final status UI.
    """
    # Read document id from the submitted form
    doc_id = request.form.get("document_id")
    if not doc_id:
        flash("No document id provided.", "warning")
        return redirect(url_for("update.update_operator", operator_id=1))

    # Try to fetch the document and update status
    doc = Document.query.get(doc_id)
    if doc:
        doc.status = "PUBLISHED"
        db.session.commit()

    # Render the final publishing status UI with the document object
    return render_template("final_publish.html", document=doc)

# -------------------------------------------------------------------
