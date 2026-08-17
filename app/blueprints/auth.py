"""
Authentication Blueprint
----------------------
Handles user login, logout, and session management.
Integrates with Supabase for external authentication and automatically 
syncs user profiles to the local database upon their first successful login.
"""

from flask import Blueprint, redirect, url_for, request, flash, render_template
from flask_login import login_required, login_user, logout_user, current_user
from supabase import create_client, Client
import os

from ..models.user import User
from .. import db

auth_bp = Blueprint("auth", __name__)

# =====================================================================
# EXTERNAL CLIENT INITIALIZATION
# =====================================================================
# Initialize Supabase Client using environment variables
supabase: Client = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_ANON_KEY", "")
)

# =====================================================================
# ROUTE DEFINITIONS
# =====================================================================

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Renders the login form and processes authentication requests.
    Validates credentials against Supabase. If successful, checks if the user
    exists in the local database (creating a new local User record if not) 
    and establishes a local Flask-Login session.
    """
    # Bypass login screen if already authenticated
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = request.form.get("username", "").strip()  # Form field named "username" acts as email
        password = request.form.get("password", "")

        try:
            # 1. Authenticate against remote Supabase instance
            auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})

            if auth_response.user:
                user_email = auth_response.user.email

                if not user_email:
                    flash("Authentication error: no email returned.", "danger")
                    return render_template("login.html")

                # 2. Local Database Synchronization (Creates account on first login)
                user = User.query.filter_by(email=user_email).first()
                if not user:
                    username = user_email.split("@")[0]
                    user = User()
                    user.username = username
                    user.email = user_email
                    db.session.add(user)
                    db.session.commit()

                # 3. Establish local session tracking
                login_user(user)
                return redirect(url_for("dashboard.index"))

        except Exception as e:
            print(f"SUPABASE AUTH ERROR: {e}")
            flash("Invalid email or password. Please try again.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """
    Terminates the current user's local session and redirects to the login screen.
    """
    logout_user()
    return redirect(url_for("auth.login"))
