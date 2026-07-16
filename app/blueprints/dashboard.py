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

