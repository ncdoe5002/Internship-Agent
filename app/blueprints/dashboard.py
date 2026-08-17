"""
Dashboard Blueprint
-------------------
Serves the primary application entry points, including the operator list 
(MNOs), operator creation logic, and the split-screen view for inspecting 
active production contracts currently residing in the database.
"""

import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

# Local Services & Models
from ..services.dashboard_service import get_all_mnos, create_mno_operator
from ..models.mno import Mno
from ..models.document import Document
from ..models.agreement_prod import (
    ProdAgmtHeader, 
    ProdAgmtModels, 
    ProdAgmtMdlNormal, 
    ProdAgmtCommitment
)

dashboard_bp = Blueprint("dashboard", __name__)

# =====================================================================
# ROUTE DEFINITIONS
# =====================================================================

@dashboard_bp.route("/", methods=["GET"])
@dashboard_bp.route("/dashboard", methods=["GET"])
@login_required
def index():
    """
    Renders the main dashboard UI.
    Fetches the dynamic list of Mobile Network Operators (MNOs) from the database
    and exposes Supabase credentials for client-side functionality if required.
    """
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_ANON_KEY")
    
    # Fetch dynamic MNO list from the database service layer
    operators = get_all_mnos() 
    
    return render_template(
        "dashboard.html", 
        operators=operators, # Expose iterable operator data to Jinja2
        supabase_url=supabase_url, 
        supabase_key=supabase_key
    )

@dashboard_bp.route("/dashboard/add_mno", methods=["POST"])
@login_required
def add_mno():
    """
    Handles form submissions from the "Add MNO" modal on the dashboard.
    Normalizes the input data and delegates database insertion to the service layer.
    """
    # Extract and normalize form data
    mno_data = {
        "name": request.form.get("name", "").strip(),
        "country": request.form.get("country", "").strip(),
        "currency": request.form.get("currency", "").strip().upper(),
        "categories": request.form.get("categories", "").strip()
    }
    
    if create_mno_operator(mno_data):
        flash(f"Successfully added {mno_data['name']}.", "success")
    else:
        flash("Failed to add MNO operator. Please try again.", "danger")
        
    # Redirect back to the dashboard to refresh the operator listing
    return redirect(url_for("dashboard.index"))


# -------------------------------------------------------------------
# VIEW CONTRACT (SPLIT SCREEN DISPLAY)
# -------------------------------------------------------------------
@dashboard_bp.route("/view_contract/<int:contract_id>")
@login_required
def view_contract(contract_id):
    """
    Retrieves and displays the active, published production contract for a specific MNO.
    Pulls heavily structured relational data (Headers, Models, Rates, Commitments) 
    and associates it with the most recent signed PDF document.
    """
    # Note: contract_id from the UI refers to the MNO primary key
    mno = Mno.query.get_or_404(contract_id)
    
    # Query the relational production schema
    prod_header = ProdAgmtHeader.query.filter_by(mno_id=mno.id).first()
    
    header_dict = {}
    models = []
    rates = []
    commitments = []
    pdf_doc_id = contract_id  # Fallback ID
    
    if prod_header:
        # Convert the SQLAlchemy header object into a flat dictionary for Jinja rendering
        header_dict = {
            c.name: getattr(prod_header, c.name) 
            for c in prod_header.__table__.columns 
            if c.name not in ['id', 'mno_id']
        }
        
        # Resolve cascading one-to-many relationships
        models = ProdAgmtModels.query.filter_by(header_id=prod_header.id).all()
        rates = ProdAgmtMdlNormal.query.join(ProdAgmtModels).filter(ProdAgmtModels.header_id == prod_header.id).all()
        commitments = ProdAgmtCommitment.query.filter_by(header_id=prod_header.id).all()

        # Locate the most recently PUBLISHED document to display in the PDF viewer iframe
        latest_doc = Document.query.filter_by(partner_name=mno.name, status="PUBLISHED").order_by(Document.id.desc()).first()
        if latest_doc:
            pdf_doc_id = latest_doc.id

    return render_template(
        "view_contract.html", 
        contract_id=mno.id,
        header=header_dict,
        models=models,
        rates=rates,
        commitments=commitments,
        pdf_doc_id=pdf_doc_id  # Injects correct Document ID for the PDF serving route
    )

