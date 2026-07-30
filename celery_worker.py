from app import create_app
from app.extensions import celery_app

# Calling create_app() now automatically configures celery_app with Redis
flask_app = create_app()

# Expose the configured instance for the Celery CLI to find
celery = celery_app
