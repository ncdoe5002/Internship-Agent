from flask_login import UserMixin
from ..extensions import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)

    documents = db.relationship("Document", backref="uploader", lazy=True)
    audit_logs = db.relationship("AuditLog", backref="reviewer", lazy=True)


@login_manager.user_loader
def load_user(user_id):
    # db.session.get() is the SQLAlchemy 2.x replacement for the deprecated Query.get()
    return db.session.get(User, int(user_id))
