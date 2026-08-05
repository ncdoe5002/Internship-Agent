# 1. Use the official PyTorch CUDA Runtime image (already includes Python 3.11/3.10)
FROM pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime

WORKDIR /app
    
# 2. Install OS-level dependencies (Docling still needs these)
# Note: we use DEBIAN_FRONTEND to prevent interactive prompts
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 3. Use Docker Cache Mount for your other python packages
RUN pip install --upgrade pip
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# 4. Copy the rest of your app code LAST
COPY . .

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]
