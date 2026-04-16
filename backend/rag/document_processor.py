import fitz  # PyMuPDF
import pandas as pd
from typing import List, Dict


def _clean_extracted_text(text: str) -> str:
    return text.strip()

def extract_text_from_pdf(file_path: str) -> str:
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text() + "\n"
    return text

def extract_text_from_csv(file_path: str) -> str:
    csv_error = None
    for encoding in ("utf-8", "latin1"):
        try:
            df = pd.read_csv(file_path, encoding=encoding)
            return df.to_string(index=False)
        except UnicodeDecodeError as exc:
            csv_error = exc
        except Exception as exc:
            raise ValueError(f"Failed to parse CSV file: {exc}") from exc
    raise ValueError(f"Failed to parse CSV file: {csv_error}")

def extract_text_from_excel(file_path: str) -> str:
    try:
        df = pd.read_excel(file_path)
        return df.to_string(index=False)
    except Exception as exc:
        raise ValueError(f"Failed to parse Excel file: {exc}") from exc

def parse_document(file_path: str, filename: str) -> str:
    """Routes the document parsing based on file extension."""
    normalized_filename = filename.lower()

    if normalized_filename.endswith(".pdf"):
        text = extract_text_from_pdf(file_path)
    elif normalized_filename.endswith(".csv"):
        text = extract_text_from_csv(file_path)
    elif normalized_filename.endswith((".xls", ".xlsx")):
        text = extract_text_from_excel(file_path)
    else:
        raise ValueError("Unsupported file format. Use PDF, CSV, or Excel.")

    cleaned_text = _clean_extracted_text(text)
    if not cleaned_text:
        raise ValueError("No readable text found in document.")

    return cleaned_text

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Splits text into chunks with specified size and overlap."""
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += (chunk_size - overlap)
        
    return chunks

def process_file(file_path: str, filename: str) -> List[Dict]:
    """Extracts text, chunks it, and attaches metadata."""
    full_text = parse_document(file_path, filename)
    text_chunks = chunk_text(full_text)
    if not text_chunks:
        raise ValueError("No text chunks could be created from document.")
    
    documents = []
    for i, chunk in enumerate(text_chunks):
        documents.append({
            "chunk_id": f"{filename}_chunk_{i}",
            "filename": filename,
            "text": chunk
        })
        
    return documents
