import fitz  # pip install PyMuPDF

def extract_text_from_file(file_path: str) -> str:
    """
    Extracts raw text from an uploaded PDF file.
    """
    ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else ''
    
    if ext == 'pdf':
        text = ""
        with fitz.open(file_path) as doc:
            for page in doc:
                text += str(page.get_text()) + "\n"
        return text
    else:
        # Simple fallback for standard text files
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()