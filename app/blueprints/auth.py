from flask import Blueprint, redirect, url_for, request, flash, render_template
from flask_login import login_required, login_user, logout_user
from flask_login import current_user
import os
from typing import Any

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = Any

from ..models.user import User
from .. import db

auth_bp = Blueprint("auth", __name__)


def _create_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY")

    if not create_client or not supabase_url or not supabase_key:
        return None

    return create_client(supabase_url, supabase_key)


supabase = _create_supabase_client()


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # If they submit the form, process the Supabase login
    if request.method == "POST":
        email = request.form.get(
            "username", ""
        ).strip()  # matching your form input name
        password = request.form.get("password", "")

        if supabase is None:
            flash("Authentication is not configured.", "danger")
            return render_template("login.html")

        try:
            # Authenticate directly against Supabase
            auth_response = supabase.auth.sign_in_with_password(
                {"email": email, "password": password}
            )

            if auth_response.user:
                user_email = auth_response.user.email

                if user_email:
                    # Check if user exists in local DB, if not, create them
                    user = User.query.filter_by(email=user_email).first()
                    if not user:
                        username = user_email.split("@")[0]
                        user = User()
                        user.username = username
                        user.email = user_email
                        db.session.add(user)
                        db.session.commit()

                # Start the Flask-Login session
                login_user(user)
                return redirect(url_for("auth.dashboard"))

        except Exception as e:
            print(f"SUPABASE AUTH ERROR: {e}")

            flash("Invalid email or password. Please try again.", "danger")

    # If it's a GET request, just show the page
    return render_template("login.html")


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    # current_user is provided by Flask-Login.
    # It holds the User database model of whoever is currently logged in!
    return render_template("dashboard.html", username=current_user.username)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
