# ContractExtract

PDF upload → AI extraction → human review → permanent save.

Built with: Flask · Celery · PostgreSQL · Redis · Google Gemini · HTMX · Docker

## Quick start

### Prerequisites
- Docker Desktop installed and running
- A Google Gemini API key from [Google AI Studio](https://aistudio.google.com/)

### 1. Clone and configure

```bash
git clone <repo-url>
cd ContractExtract
cp .env.example .env
# Edit .env — add your GEMINI_API_KEY and change SECRET_KEY
```

### 2. Start everything

```bash
docker compose up --build
```

Open your browser to **http://localhost:8000**

### 3. Create the database tables (first time only)

```bash
docker compose exec web flask db init
docker compose exec web flask db migrate -m "Initial schema"
docker compose exec web flask db upgrade
```

### 4. Create your first user (dev helper)

```bash
docker compose exec web python -c "
from app import create_app
from app.extensions import db
from app.models.user import User
from werkzeug.security import generate_password_hash
app = create_app()
with app.app_context():
    u = User(username='admin', email='admin@example.com', password_hash=generate_password_hash('admin123'), is_admin=True)
    db.session.add(u)
    db.session.commit()
    print('User created: admin / admin123')
"
```

## Project structure

```
app/
├── blueprints/   # Route handlers (upload, review, auth, jobs)
├── models/       # SQLAlchemy database models
├── services/     # Business logic (file storage, Gemini AI calls)
├── tasks/        # Celery background tasks
├── schemas/      # Pydantic validation for AI output
└── templates/    # Jinja2 HTML pages
```

## Document status flow

```
PENDING → PROCESSING → READY → APPROVED
                    ↘ FAILED (after 3 retries)
```

## Development (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Start postgres and redis separately, then:
flask run --port 8000
celery -A celery_worker.celery worker --loglevel=info
```

## Environment variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `GEMINI_API_KEY` | Google AI Studio API key |
| `SECRET_KEY` | Flask session secret (make it long and random) |
| `DB_PASSWORD` | PostgreSQL password (used by docker-compose) |
| `UPLOAD_FOLDER` | Where PDFs are stored locally (default: `uploads`) |
