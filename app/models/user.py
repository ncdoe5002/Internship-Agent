from flask_login import UserMixin

from ..extensions import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    documents = db.relationship("Document", backref="uploader", lazy=True)
    audit_logs = db.relationship("AuditLog", backref="reviewer", lazy=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
