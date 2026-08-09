import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from ..services.dashboard_service import get_all_mnos, create_mno_operator
from flask import render_template
from flask_login import login_required
from ..models.mno import Mno
from ..models.document import Document
from ..models.agreement_prod import ProdAgmtHeader, ProdAgmtModels, ProdAgmtMdlNormal, ProdAgmtCommitment

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/", methods=["GET"])
@dashboard_bp.route("/dashboard", methods=["GET"])
@login_required
def index():
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_ANON_KEY")
    
    # Fetch dynamic MNO list from the database
    operators = get_all_mnos() 
    
    return render_template(
        "dashboard.html", 
        operators=operators, # Pass to Jinja2
        supabase_url=supabase_url, 
        supabase_key=supabase_key
    )

@dashboard_bp.route("/dashboard/add_mno", methods=["POST"])
@login_required
def add_mno():
    # Extract form data submitted via the Modal
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
        
    # Redirect back to the dashboard to see the updated list
    return redirect(url_for("dashboard.index"))


# -------------------------------------------------------------------
# NEW ROUTE: VIEW CONTRACT (SPLIT SCREEN)
# -------------------------------------------------------------------
@dashboard_bp.route("/view_contract/<int:contract_id>")
@login_required
def view_contract(contract_id):
    # The contract_id coming from the dashboard is actually the MNO ID
    mno = Mno.query.get_or_404(contract_id)
    
    # Query the new relational production tables
    prod_header = ProdAgmtHeader.query.filter_by(mno_id=mno.id).first()
    
    header_dict = {}
    models = []
    rates = []
    commitments = []
    pdf_doc_id = contract_id  # Fallback
    
    if prod_header:
        # Convert SQLAlchemy header row to a dictionary for easy Jinja rendering
        header_dict = {c.name: getattr(prod_header, c.name) for c in prod_header.__table__.columns if c.name not in ['id', 'mno_id']}
        
        # Fetch relational child rows
        models = ProdAgmtModels.query.filter_by(header_id=prod_header.id).all()
        rates = ProdAgmtMdlNormal.query.join(ProdAgmtModels).filter(ProdAgmtModels.header_id == prod_header.id).all()
        commitments = ProdAgmtCommitment.query.filter_by(header_id=prod_header.id).all()

        # Find the most recently PUBLISHED document for this operator to display the correct PDF
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
        pdf_doc_id=pdf_doc_id  # Pass the correct Document ID to the PDF viewer
    )

