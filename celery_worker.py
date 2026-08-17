from app import create_app
from app.extensions import celery_app

flask_app = create_app()
    

def init_celery(app):
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
    return celery_app


celery = init_celery(flask_app)
