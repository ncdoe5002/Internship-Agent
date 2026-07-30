import os

from flask import Flask
from .extensions import celery_app
from .extensions import db, login_manager, migrate

def create_app():
    app = Flask(__name__)

    app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-local-key")

    # --- GUARANTEED CELERY CONFIGURATION ---
    # This ensures Gunicorn and the Celery worker both read the Redis URL
    celery_app.conf.update(
        broker_url=app.config.get("CELERY_BROKER_URL", "redis://redis:6379/0"),
        result_backend=app.config.get("CELERY_RESULT_BACKEND", "redis://redis:6379/0"),
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
    )

    class ContextTask(celery_app.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app.Task = ContextTask
    # ---------------------------------------

    # ── Configuration ────────────────────────────────────────────
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.environ.get("UPLOAD_FOLDER", "uploads")

    # FIX: upload.py calls current_app.config["ALLOWED_EXTENSIONS"]
    # but it was never defined anywhere — would crash with KeyError on every upload.
    app.config["ALLOWED_EXTENSIONS"] = {"pdf", "xlsx", "xls", "docx"}

    # ── Connect extensions to this app ───────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # ── Import models so Flask-Migrate can see them ───────────────
    # Must happen AFTER db.init_app(app)
    from .models import agreement, audit_log, document, production_record, user  # noqa: F401

    # ── Register blueprints ───────────────────────────────────────
    from .blueprints.auth import auth_bp
    from .blueprints.update import update_bp
    from .blueprints.dashboard import dashboard_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(update_bp)

    return app
