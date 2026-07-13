import os
import uuid

from werkzeug.datastructures import FileStorage

# Global extraction limits used by deterministic parsers.
MAX_TABLE_COUNT = 10
MAX_ROW_COUNT = 25


def save_upload(file: FileStorage, upload_folder: str) -> str:
    """Save an uploaded file to disk and return its relative file key."""
    ext = file.filename.rsplit(".", 1)[-1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    dest = os.path.join(upload_folder, unique_name)
    file.save(dest)
    return unique_name


def read_pdf(file_key: str, upload_folder: str = "uploads") -> bytes:
    """Read a PDF from disk by its file key and return raw bytes."""
    path = os.path.join(upload_folder, file_key)
    with open(path, "rb") as f:
        return f.read()
