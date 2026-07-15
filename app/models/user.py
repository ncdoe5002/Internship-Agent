from flask_login import UserMixin

from ..extensions import db, login_manager

from flask_login import UserMixin
from .. import db # Ensure you are importing your SQLAlchemy db instance

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)

    documents = db.relationship("Document", backref="uploader", lazy=True)
    audit_logs = db.relationship("AuditLog", backref="reviewer", lazy=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
