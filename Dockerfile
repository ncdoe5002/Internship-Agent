# 1. Use a slim Debian image for pre-compiled wheel compatibility
FROM python:3.11-slim

WORKDIR /app
    
# Install OS-level dependencies often required by Docling, PyMuPDF, OpenCV, and psycopg2
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 2. Upgrade pip to handle large wheels efficiently
RUN pip install --upgrade pip

# 3. Use Docker Cache Mount AND force CPU-only PyTorch
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install -r requirements.txt

# 4. Copy the rest of your app code LAST (so code changes don't trigger pip installs)
COPY . .

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]
