from flask import Blueprint, redirect, url_for, request, flash, render_template
from flask_login import login_required, login_user, logout_user, current_user
from supabase import create_client, Client
import os
from ..models.user import User
from .. import db

auth_bp = Blueprint("auth", __name__)

# Initialize Supabase Client
supabase: Client = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_ANON_KEY", "")
)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = request.form.get("username", "").strip()  # field name is "username" in the form
        password = request.form.get("password", "")

        try:
            # Authenticate against Supabase
            auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})

            if auth_response.user:
                user_email = auth_response.user.email

                if not user_email:
                    flash("Authentication error: no email returned.", "danger")
                    return render_template("login.html")

                # Sync user into the local DB (creates on first login)
                user = User.query.filter_by(email=user_email).first()
                if not user:
                    username = user_email.split("@")[0]
                    user = User()
                    user.username = username
                    user.email = user_email
                    db.session.add(user)
                    db.session.commit()

                login_user(user)
                return redirect(url_for("dashboard.index"))

        except Exception as e:
            print(f"SUPABASE AUTH ERROR: {e}")
            flash("Invalid email or password. Please try again.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
