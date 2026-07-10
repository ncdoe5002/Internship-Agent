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
    # FIX: .query.get_or_404() deprecated → db.get_or_404()
    doc = db.get_or_404(Document, doc_id)
    if doc.status != "READY":
        abort(400, "Document is not ready for approval.")
    corrected = request.form.to_dict()
    try:
        record = ProductionRecord(document_id=doc.id, data=corrected)
        log = AuditLog(
            document_id=doc.id,
            user_id=current_user.id,
            action="APPROVED",
            detail=str(corrected),
        )
        doc.status = "APPROVED"
        db.session.add(record)
        db.session.add(log)
        db.session.commit()
        flash("Document approved and saved.", "success")
    except Exception:
        db.session.rollback()
        abort(500, "Approval failed — please try again.")
    return redirect(url_for("review.list_docs"))
