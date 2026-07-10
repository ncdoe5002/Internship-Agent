from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models.audit_log import AuditLog
from ..models.document import Document
from ..models.production_record import ProductionRecord

review_bp = Blueprint("review", __name__, url_prefix="/review")


@review_bp.route("/")
@login_required
def list_docs():
    docs = (
        Document.query.filter_by(status="READY")
        .order_by(Document.created_at.desc())
        .all()
    )
    return render_template("review_list.html", docs=docs)


@review_bp.route("/<int:doc_id>")
@login_required
def detail(doc_id):
    # FIX: .query.get_or_404() deprecated → db.get_or_404()
    doc = db.get_or_404(Document, doc_id)
    return render_template("review_detail.html", doc=doc)


@review_bp.route("/<int:doc_id>/approve", methods=["POST"])
@login_required
def approve(doc_id):
    """
    Approve a document after human review.
    
    This endpoint:
    - Requires document status to be READY (after orchestrator completes)
    - Captures any corrections made by the reviewer
    - Logs the approval action with reviewer identity and timestamp
    - Stores corrections in ProductionRecord
    - Only allows APPROVED status to proceed to publish/notify
    """
    # FIX: .query.get_or_404() deprecated → db.get_or_404()
    doc = db.get_or_404(Document, doc_id)
    
    # Document must be in READY state (orchestrator completed, awaiting human review)
    if doc.status != "READY":
        abort(400, "Document is not ready for approval. Current status: " + doc.status)
    
    # Get corrections from form data
    corrected = request.form.to_dict()
    
    # Extract approval decision from form
    approval_decision = corrected.get("approval_decision", "APPROVED")
    
    # Validate approval decision
    valid_decisions = ["APPROVED", "REJECTED", "NEEDS_CHANGES"]
    if approval_decision not in valid_decisions:
        abort(400, f"Invalid approval decision. Must be one of: {', '.join(valid_decisions)}")
    
    # Only APPROVED status allows proceeding to publish/notify
    if approval_decision != "APPROVED":
        # For REJECTED or NEEDS_CHANGES, update document status but don't create ProductionRecord
        try:
            log = AuditLog(
                document_id=doc.id,
                user_id=current_user.id,
                action=approval_decision,
                detail=str(corrected),
            )
            doc.status = approval_decision
            db.session.add(log)
            db.session.commit()
            flash(f"Document marked as {approval_decision}.", "info")
        except Exception:
            db.session.rollback()
            abort(500, "Approval failed — please try again.")
        return redirect(url_for("review.list_docs"))
    
    # For APPROVED status, create ProductionRecord with corrections
    try:
        record = ProductionRecord(document_id=doc.id, data=corrected)
        log = AuditLog(
            document_id=doc.id,
            user_id=current_user.id,
            action="APPROVED",
            detail=f"Reviewer: {current_user.username}. Corrections: {str(corrected)}",
        )
        doc.status = "APPROVED"
        db.session.add(record)
        db.session.add(log)
        db.session.commit()
        flash("Document approved and saved. Changes will be published.", "success")
    except Exception:
        db.session.rollback()
        abort(500, "Approval failed — please try again.")
    return redirect(url_for("review.list_docs"))
