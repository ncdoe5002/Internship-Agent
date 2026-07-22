import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from ..extensions import db
from ..models.document import Document
from ..services.storage import save_upload
from ..tasks.process_pdf import process_pdf 
from ..models.agreement import AgmtHeaderStg, AgmtModelsStg, AgmtMdlNormalStg

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

@update_bp.route("/update/extracted/<int:doc_id>", methods=["GET"])
@login_required
def view_extracted(doc_id):
    doc = Document.query.get_or_404(doc_id)
    
    class DummyDoc:
        file_key = "pdfs/dummy.pdf" 
    existing_doc = DummyDoc()

    # --- 1. Query the database ---
    # We retrieve the current active agreement and the new proposed one we seeded
    current_rates = AgmtMdlNormalStg.query.filter_by(AGMT_ID="AGMT_CURRENT_001").all()
    proposed_rates = AgmtMdlNormalStg.query.filter_by(AGMT_ID="AGMT_PROPOSED_001").all()
    
    # Map the proposed rates into a dictionary keyed by REC_TYPE (e.g., "SMS-MT Rate") 
    # so we can easily match them to the current rates.
    proposed_map = {r.REC_TYPE: r for r in proposed_rates}

    rate_comparisons = []
    colors = ["ul-blue", "ul-green", "ul-cyan", "ul-red", "ul-purple"]
    
    # Helper dictionary to format UI units nicely based on the REC_TYPE
    unit_map = {
        "SMS-MT Rate": "msg",
        "GPRS Data Rate": "MB",
        "Voice MOC Rate": "min",
        "Voice MTC Rate": "min",
        "LTE Data Rate": "MB"
    }

    # --- 2. Process and compare the data dynamically ---
    for idx, c_rate in enumerate(current_rates):
        p_rate = proposed_map.get(c_rate.REC_TYPE)
        if not p_rate:
            continue
            
        # Cast Decimal types from the DB to floats for math
        old_val = float(c_rate.CHARGE_FIELD) if c_rate.CHARGE_FIELD else 0.0
        new_val = float(p_rate.CHARGE_FIELD) if p_rate.CHARGE_FIELD else 0.0
        
        # Calculate Percentage Delta
        if old_val > 0 and old_val != new_val:
            delta_pct = abs((new_val - old_val) / old_val) * 100
            delta_text = f"↑ {delta_pct:.1f}%" if new_val > old_val else f"↓ {delta_pct:.1f}%"
            delta_class = "up" if new_val > old_val else "down"
        else:
            delta_text = "— 0.0%"
            delta_class = "neutral"
            
        # Dynamically generate AI notes based on math
        ai_note = "Unchanged"
        ai_note_class = ""
        
        if delta_class == "up":
            if delta_pct > 25.0:
                ai_note = "Increase — flagged for review"
                ai_note_class = "flagged"
            else:
                ai_note = "Increase within IOT ceiling"
        elif delta_class == "down":
            ai_note = "Decrease — promotional rate"

        # Determine the display unit (e.g., EUR/MB)
        base_unit = unit_map.get(c_rate.REC_TYPE, "unit")
        display_unit = f"{c_rate.RATE_CURRENCY}/{base_unit}"

        # Append to our final list for Jinja
        rate_comparisons.append({
            "field_name": c_rate.REC_TYPE,
            "color_class": colors[idx % len(colors)],
            "current_rate": f"{old_val:.4f}",
            "new_rate": f"{new_val:.4f}",
            "unit": display_unit,
            "delta_text": delta_text,
            "delta_class": delta_class,
            "ai_note": ai_note,
            "ai_note_class": ai_note_class
        })

    # --- 3. Calculate dynamic summary stats for the top bar ---
    changed_count = sum(1 for r in rate_comparisons if r["delta_class"] != "neutral")
    increased_count = sum(1 for r in rate_comparisons if r["delta_class"] == "up")
    decreased_count = sum(1 for r in rate_comparisons if r["delta_class"] == "down")

    return render_template(
        "extracted.html", 
        document=doc, 
        current_doc=existing_doc,
        rates=rate_comparisons,
        total_fields=len(rate_comparisons),
        changed_count=changed_count,
        increased_count=increased_count,
        decreased_count=decreased_count
    )

# -------------------------------------------------------------------
# TEMP: DATABASE SEEDING ROUTE (Run this once)
# -------------------------------------------------------------------
@update_bp.route("/update/seed", methods=["GET"])
def seed_dummy_data():
    # Check if data already exists to prevent duplicate entries
    if AgmtHeaderStg.query.filter_by(AGMT_ID="AGMT_CURRENT_001").first():
        return "Database already seeded! You can now visit the extracted view."

    # 1. Create the 'Current' and 'Proposed' Agreement Headers
    agmt_current = AgmtHeaderStg()
    agmt_current.AGMT_ID = "AGMT_CURRENT_001"
    agmt_current.SENDER = "Operator A"
    agmt_current.RP = "Operator B"
    agmt_current.AGMT_STATUS = "ACTIVE"

    agmt_proposed = AgmtHeaderStg()
    agmt_proposed.AGMT_ID = "AGMT_PROPOSED_001"
    agmt_proposed.SENDER = "Operator A"
    agmt_proposed.RP = "Operator B"
    agmt_proposed.AGMT_STATUS = "PENDING"
    
    # 2. Create the Rate Models for them
    model_current = AgmtModelsStg()
    model_current.MODEL_SEQ = 1
    model_current.AGMT_ID = "AGMT_CURRENT_001"
    model_current.MODEL_TYPE = "STANDARD"

    model_proposed = AgmtModelsStg()
    model_proposed.MODEL_SEQ = 2
    model_proposed.AGMT_ID = "AGMT_PROPOSED_001"
    model_proposed.MODEL_TYPE = "PROPOSED"

    db.session.add_all([agmt_current, agmt_proposed, model_current, model_proposed])

    # 3. Insert the normal rate data rows (REC_TYPE, Current Value, New Value)
    sample_rates = [
        ("SMS-MT Rate", 0.0182, 0.0205, "EUR"),
        ("GPRS Data Rate", 0.0140, 0.0140, "EUR"),
        ("Voice MOC Rate", 0.0075, 0.0068, "EUR"),
        ("Voice MTC Rate", 0.0032, 0.0041, "EUR"),
        ("LTE Data Rate", 0.0210, 0.0210, "EUR")
    ]

    for rec_type, cur_val, new_val, curr in sample_rates:
        # Link current rate to Current Agreement
        rate_cur = AgmtMdlNormalStg()
        rate_cur.AGMT_ID = "AGMT_CURRENT_001"
        rate_cur.MODEL_SEQ = 1
        rate_cur.REC_TYPE = rec_type
        rate_cur.CHARGE_FIELD = cur_val
        rate_cur.RATE_CURRENCY = curr
        # Link proposed rate to Proposed Agreement
        rate_prop = AgmtMdlNormalStg()
        rate_prop.AGMT_ID = "AGMT_PROPOSED_001"
        rate_prop.MODEL_SEQ = 2
        rate_prop.REC_TYPE = rec_type
        rate_prop.CHARGE_FIELD = new_val
        rate_prop.RATE_CURRENCY = curr
        
        db.session.add_all([rate_cur, rate_prop])

    db.session.commit()
    return "Successfully seeded the database! You can now view the extracted data."