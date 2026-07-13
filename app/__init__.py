import os

from flask import Flask

from .extensions import db, login_manager, migrate


def create_app():
    app = Flask(__name__)

    # ── Configuration ────────────────────────────────────────────
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.environ.get("UPLOAD_FOLDER", "uploads")

    # FIX: upload.py calls current_app.config["ALLOWED_EXTENSIONS"]
    # but it was never defined anywhere — would crash with KeyError on every upload.
    app.config["ALLOWED_EXTENSIONS"] = {"pdf"}

    # ── Connect extensions to this app ───────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # ── Import models so Flask-Migrate can see them ───────────────
    # Must happen AFTER db.init_app(app)
    from .models import audit_log, document, production_record, user  # noqa: F401

    # ── Register blueprints ───────────────────────────────────────
    from .blueprints.auth import auth_bp
    from .blueprints.jobs import jobs_bp
    from .blueprints.review import review_bp
    from .blueprints.upload import upload_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(review_bp)

    return app