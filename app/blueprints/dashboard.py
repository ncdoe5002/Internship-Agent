import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from ..services.dashboard_service import get_all_mnos, create_mno_operator

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
@dashboard_bp.route("/dashboard/view_contract/<int:contract_id>", methods=["GET"])
@login_required
def view_contract(contract_id):
    """
    Renders a split-screen view with tabular data on the left 
    and a PDF document viewer on the right.
    """
    
    # MOCK DATA: Replace this with your actual database query to fetch contract details
    # e.g., contract_data = AgmtMdlNormalStg.query.filter_by(document_id=contract_id).all()
    contract_data = [
        {"service": "Voice Call (MO)", "destination": "Zone 1", "rate": "0.15", "currency": "USD"},
        {"service": "Voice Call (MT)", "destination": "Zone 1", "rate": "0.05", "currency": "USD"},
        {"service": "SMS (MO)", "destination": "Global", "rate": "0.02", "currency": "USD"},
        {"service": "Data", "destination": "Local", "rate": "1.50", "currency": "USD/GB"}
    ]
    
    return render_template(
        "view_contract.html",
        contract_id=contract_id,
        contract_data=contract_data
    )

