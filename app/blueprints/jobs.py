from flask import Blueprint, render_template_string
from flask_login import login_required

from ..extensions import db
from ..models.document import Document

jobs_bp = Blueprint("jobs", __name__, url_prefix="/jobs")

STATUS_SNIPPET = """
{% if status == 'PENDING' or status == 'PROCESSING' %}
  <span class="badge badge-processing">⏳ Processing…</span>
{% elif status == 'READY' %}
  <span class="badge badge-ready">✅ Ready for review</span>
{% elif status == 'APPROVED' %}
  <span class="badge badge-approved">✔ Approved</span>
{% elif status == 'FAILED' %}
  <span class="badge badge-failed">❌ Failed — contact admin</span>
{% endif %}
"""


@jobs_bp.route("/<int:doc_id>/status")
@login_required
def status(doc_id):
    # FIX: Document.query.get_or_404() is deprecated in SQLAlchemy 2.x.
    # The modern replacement is db.get_or_404(Model, id).
    # Both do the same: fetch by primary key, return 404 if not found.
    doc = db.get_or_404(Document, doc_id)
    return render_template_string(STATUS_SNIPPET, status=doc.status)
