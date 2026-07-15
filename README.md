# ContractExtract

<p align="center">
  <img src="Images/ContractExtract.png" width="900" alt="ContractExtract Banner">
</p>
ContractExtract is a document processing system for contract and PDF extraction workflows. It uses Flask for the web application, Celery for background processing, PostgreSQL for persistence, Redis as the message broker and cache layer, and Google Gemini for AI-powered extraction. Human review is built into the flow so extracted data can be validated before it is permanently saved.

The project is designed for a practical enterprise-style workflow:

A user uploads a PDF.
The file is queued for background processing.
Gemini extracts structured data.
A reviewer checks the extracted output.
Approved records are stored permanently.

<p align="center">
  <a href="https://skillicons.dev">
    <img src="https://skillicons.dev/icons?i=python,flask,html,css,javascript" />
  </a>
</p>

<p align="center">
  <b>PDF upload → AI extraction → human review → permanent save</b>
</p>

---

## How It Works
 
```text
User uploads PDF
      ↓
Flask receives file
      ↓
File stored locally or in mounted volume
      ↓
Celery task starts
      ↓
Gemini extracts structured data
      ↓
Reviewer verifies output
      ↓
Approved record saved to PostgreSQL
      ↓
Document marked as APPROVED
```

## Quick start

### Prerequisites
- Docker Desktop installed and running
- A Google Gemini API key from [Google AI Studio](https://aistudio.google.com/)


## Features

<details>
<summary><strong>Click to expand the feature set</strong></summary>

- Upload PDF documents through a web interface.
- Process documents asynchronously with Celery workers.
- Extract structured data using Google Gemini.
- Present AI output for human verification.
- Track document lifecycle states such as pending, processing, ready, approved, and failed.
- Store metadata and final approved results in PostgreSQL.
- Use Redis for task brokering and queue management.
- Support a modular Flask project structure.
- Containerized development with Docker.
- Database migrations with Flask-Migrate.

</details>

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

```text
app/
├── blueprints/
│   ├── auth.py
│   ├── upload.py
│   ├── review.py
│   └── jobs.py
├── models/
│   ├── user.py
│   ├── document.py
|   ├── agreement.py
│   ├── audit_log.py
│   └── production_record.py
|   ├── agreement.py
├── services/
│   ├── storage.py
│   ├── gemini.py
│   └── baseline.py
├── tasks/
│   └── process_pdf.py
├── schemas/
│   └── extraction.py
└── templates/
    ├── base.html
    ├── upload.html
    ├── review.html
    └── dashboard.html
```
---

## Tech Stack

<p align="center">
  <img src="https://skillicons.dev/icons?i=python,flask,postgres,redis,docker,html,css" alt="Tech Stack" />
</p>

| Layer | Tools |
|---|---|
| Frontend | Jinja2, HTMX, HTML, CSS |
| Backend | Flask |
| Background Jobs | Celery |
| Queue / Cache | Redis |
| Database | PostgreSQL |
| AI | Google Gemini |
| Deployment | Docker, Docker Compose |
| Validation | Pydantic |

## Document status flow

```
PENDING → PROCESSING → READY → APPROVED
                    ↘ FAILED (after 3 retries)
```
## Architecture

```text
┌──────────────────────────────┐
│          Browser UI          │
│      Upload / Review Pages   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│         Flask App            │
│ Routes, validation, auth     │
└──────────────┬───────────────┘
               │
               ├──────────────► PostgreSQL
               │
               ├──────────────► Redis
               │
               ▼
┌──────────────────────────────┐
│        Celery Worker         │
│  Background PDF processing   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       Google Gemini          │
│ Structured extraction logic  │
└──────────────────────────────┘
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
