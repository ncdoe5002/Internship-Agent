import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import current_user, login_required

from ..extensions import db
from ..models.document import Document
from ..services.storage import save_upload
from ..tasks.process_pdf import process_pdf 

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
    # If it's a GET request, just show the upload UI we built first
    if request.method == "GET":
        return render_template("update.html", operator_id=operator_id)
        
    # If it's a POST request, handle the file being uploaded from update.html
    # NOTE: Ensure your <input type="file"> in update.html has name="pdf_file"
    file = request.files.get("pdf_file") 
    filename = (file.filename if file else "") or ""
    
    if not file or filename == "":
        flash("No file selected.", "warning")
        return redirect(url_for("update.update_operator", operator_id=operator_id))
        
    if not allowed_file(filename):
        flash("Invalid file type.", "warning")
        return redirect(url_for("update.update_operator", operator_id=operator_id))

    # Save the file and create the Document record
    file_key = save_upload(file, current_app.config["UPLOAD_FOLDER"])
    
    doc = Document()
    doc.filename = file.filename
    doc.file_key = file_key
    doc.status = "PENDING"
    # Optional: If your Document model has an operator_id column, link it here!
    # doc.operator_id = operator_id 
    doc.uploaded_by = current_user.id
    
    db.session.add(doc)
    db.session.commit()

    # Start the Celery background task
    process_task = getattr(process_pdf, "delay", None)
    if callable(process_task):
        process_task(doc.id)

    # Success! Redirect to the dynamic processing UI we built second
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
    # Render the extracted data page (make sure you save it as extracted.html)
    return render_template("extracted.html", document=doc)