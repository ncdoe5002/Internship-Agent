from ..extensions import db
from datetime import datetime, timezone

class Mno(db.Model):
    __tablename__ = 'mnos'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(100), nullable=False)
    currency = db.Column(db.String(10), nullable=False)
    categories = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default='active')
    
    # Using String here to easily match your UI's format "14 Feb 2026"
    last_updated = db.Column(db.String(20), default=lambda: datetime.now(timezone.utc).strftime('%d %b %Y'))