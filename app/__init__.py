from flask import Flask
from .extensions import db, migrate, login_manager, celery_app
from .config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialise extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Register blueprints
    from .blueprints.auth import auth_bp
    from .blueprints.upload import upload_bp
    from .blueprints.review import review_bp
    from .blueprints.jobs import jobs_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(jobs_bp)

    # Ensure the uploads folder exists
    import os
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    return app
