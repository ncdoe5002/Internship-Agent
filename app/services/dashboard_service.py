from ..extensions import db
from ..models.mno import Mno
from datetime import datetime, timezone

def get_all_mnos():
    """Fetches all MNOs to display on the dashboard."""
    try:
        # Sort by ID descending so the newest ones appear at the top
        return Mno.query.order_by(Mno.id.desc()).all()
    except Exception as e:
        print(f"Error fetching MNOs: {e}")
        return []

def create_mno_operator(data: dict) -> bool:
    """Inserts a new MNO operator into the database."""
    try:
        new_mno = Mno()
        new_mno.name = data.get('name')
        new_mno.country = data.get('country')
        new_mno.currency = data.get('currency')
        new_mno.categories = int(data.get('categories', 0))
        new_mno.last_updated = datetime.utcnow().strftime('%d %b %Y') # e.g. 14 Feb 2026
        
        db.session.add(new_mno)
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error creating MNO: {e}")
        db.session.rollback()
        return False