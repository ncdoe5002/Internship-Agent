from flask import Blueprint, render_template
from flask_login import login_required

from ..models.document import Document

# Initialize the new blueprint
dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/", methods=["GET"])
@dashboard_bp.route("/dashboard", methods=["GET"]) # I added an explicit /dashboard route as well
@login_required
def index():
    # Fetch the latest 20 documents
    docs = Document.query.order_by(Document.created_at.desc()).limit(20).all()
    
    # Render the UI template
    return render_template("dashboard.html", docs=docs)