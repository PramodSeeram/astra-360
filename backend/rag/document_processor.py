"""
Universal Document Processor — Astra 360
Supports: TXT, Markdown, DOCX, CSV, Excel, PDF (pdfplumber + PyMuPDF fallback), Images (OCR).
Returns both raw text AND extracted tables for downstream parsing.
"""

import os
import logging
import fitz  # PyMuPDF
import pandas as pd
from typing import List, Dict, Optional, Tuple
from zipfile import ZipFile

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# PDF — pdfplumber (better table extraction)
# ─────────────────────────────────────────────
def _extract_pdf_pdfplumber(file_path: str) -> Tuple[str, List[pd.DataFrame]]:
    """Primary PDF handler using pdfplumber — excels at table extraction."""
    try:
        import pdfplumber
        text_parts = []
        tables: List[pd.DataFrame] = []

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                # Extract text
                page_text = page.extract_text() or ""
                text_parts.append(page_text)

                # Extract tables
                raw_tables = page.extract_tables()
                for raw in raw_tables:
                    if not raw or len(raw) < 2:
                        continue
                    try:
                        df = pd.DataFrame(raw[1:], columns=raw[0])
                        # Drop fully-empty rows/cols
                        df = df.dropna(how="all").dropna(axis=1, how="all")
                        if not df.empty:
                            tables.append(df)
                    except Exception:
                        pass

        text = "\n".join(text_parts)
        logger.info(f"[DOC] pdfplumber: {len(text)} chars, {len(tables)} tables")
        return text, tables

    except ImportError:
        logger.warning("[DOC] pdfplumber not installed — falling back to PyMuPDF")
        return "", []
    except Exception as e:
        logger.warning(f"[DOC] pdfplumber failed ({e}) — falling back to PyMuPDF")
        return "", []


def _extract_pdf_pymupdf(file_path: str) -> str:
    """Fallback PDF handler using PyMuPDF (plain text only)."""
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text() + "\n"
    logger.info(f"[DOC] PyMuPDF fallback: {len(text)} chars")
    return text


def _pdf_to_images(file_path: str) -> List:
    """Render a scanned/image-based PDF to PIL images for OCR."""
    try:
        from PIL import Image
        import io
        images = []
        with fitz.open(file_path) as doc:
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                images.append(img)
        return images
    except Exception as e:
        logger.warning(f"[DOC] PDF→image render failed: {e}")
        return []


# ─────────────────────────────────────────────
# OCR — pytesseract (images + scanned PDFs)
# ─────────────────────────────────────────────
def _ocr_available() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _extract_image_ocr(file_path: str) -> str:
    """OCR text from an image file."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang="eng")
        logger.info(f"[DOC] OCR (image): {len(text)} chars extracted")
        return text
    except Exception as e:
        logger.error(f"[DOC] OCR failed: {e}")
        return ""


def _extract_images_ocr(images) -> str:
    """OCR text from a list of PIL images (scanned PDF pages)."""
    try:
        import pytesseract
        parts = []
        for i, img in enumerate(images):
            text = pytesseract.image_to_string(img, lang="eng")
            parts.append(text)
            logger.debug(f"[DOC] OCR page {i+1}: {len(text)} chars")
        combined = "\n".join(parts)
        logger.info(f"[DOC] OCR (scanned PDF): {len(combined)} chars total")
        return combined
    except Exception as e:
        logger.error(f"[DOC] OCR (scanned PDF) failed: {e}")
        return ""


# ─────────────────────────────────────────────
# CSV / Excel — pandas (structured extraction)
# ─────────────────────────────────────────────
def _extract_csv(file_path: str) -> Tuple[str, List[pd.DataFrame]]:
    """Parse CSV with encoding fallback. Returns text + table."""
    last_err = None
    for enc in ("utf-8", "utf-8-sig", "latin1", "cp1252"):
        try:
            df = pd.read_csv(file_path, encoding=enc)
            df = df.dropna(how="all").dropna(axis=1, how="all")
            text = df.to_string(index=False)
            logger.info(f"[DOC] CSV ({enc}): {len(df)} rows, {len(df.columns)} cols")
            return text, [df]
        except UnicodeDecodeError as e:
            last_err = e
        except Exception as e:
            raise ValueError(f"CSV parse failed: {e}") from e
    raise ValueError(f"CSV encoding detection failed: {last_err}")


def _extract_excel(file_path: str) -> Tuple[str, List[pd.DataFrame]]:
    """Parse Excel file. Tries all sheets."""
    try:
        sheets = pd.read_excel(file_path, sheet_name=None)
        all_dfs = []
        all_texts = []
        for sheet_name, df in sheets.items():
            df = df.dropna(how="all").dropna(axis=1, how="all")
            if not df.empty:
                all_dfs.append(df)
                all_texts.append(df.to_string(index=False))
        combined_text = "\n\n".join(all_texts)
        logger.info(f"[DOC] Excel: {len(all_dfs)} sheets, combined {len(combined_text)} chars")
        return combined_text, all_dfs
    except Exception as e:
        raise ValueError(f"Excel parse failed: {e}") from e


def _extract_plain_text(file_path: str) -> Tuple[str, List[pd.DataFrame]]:
    with open(file_path, "r", encoding="utf-8") as handle:
        return handle.read(), []


def _extract_docx(file_path: str) -> Tuple[str, List[pd.DataFrame]]:
    try:
        with ZipFile(file_path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
        text = xml.replace("</w:p>", "\n")
        text = text.replace("</w:t>", " ")
        text = __import__("re").sub(r"<[^>]+>", "", text)
        return text, []
    except Exception as e:
        raise ValueError(f"DOCX parse failed: {e}") from e


# ─────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp")

def parse_document(file_path: str, filename: str) -> Dict:
    """
    Universal document parser.

    Returns:
        {
            "text": str,          # Raw extracted text
            "tables": [DataFrame],# Structured tables (may be empty list)
            "method": str,        # Which extraction path was used
            "filename": str
        }
    """
    fname = filename.lower()
    logger.info(f"[DOC] Processing '{filename}' — detecting type...")

    # ── CSV ──────────────────────────────────
    if fname.endswith((".txt", ".md")):
        text, tables = _extract_plain_text(file_path)
        return {"text": text, "tables": tables, "method": "plain_text", "filename": filename}

    if fname.endswith(".docx"):
        text, tables = _extract_docx(file_path)
        return {"text": text, "tables": tables, "method": "docx_zip", "filename": filename}

    # ── CSV ──────────────────────────────────
    if fname.endswith(".csv"):
        text, tables = _extract_csv(file_path)
        return {"text": text, "tables": tables, "method": "csv_pandas", "filename": filename}

    # ── Excel ────────────────────────────────
    if fname.endswith((".xls", ".xlsx")):
        text, tables = _extract_excel(file_path)
        return {"text": text, "tables": tables, "method": "excel_pandas", "filename": filename}

    # ── PDF ──────────────────────────────────
    if fname.endswith(".pdf"):
        # Attempt 1: pdfplumber (tables + text)
        text, tables = _extract_pdf_pdfplumber(file_path)

        if text.strip():
            return {"text": text, "tables": tables, "method": "pdf_pdfplumber", "filename": filename}

        # Attempt 2: PyMuPDF (text only)
        text = _extract_pdf_pymupdf(file_path)
        if text.strip():
            return {"text": text, "tables": [], "method": "pdf_pymupdf", "filename": filename}

        # Attempt 3: Scanned PDF → OCR
        logger.info("[DOC] PDF appears to be scanned — attempting OCR...")
        if _ocr_available():
            images = _pdf_to_images(file_path)
            if images:
                text = _extract_images_ocr(images)
                if text.strip():
                    return {"text": text, "tables": [], "method": "pdf_ocr", "filename": filename}
        else:
            logger.warning("[DOC] tesseract not available — cannot OCR scanned PDF")

        return {"text": "", "tables": [], "method": "pdf_no_content", "filename": filename}

    # ── Image ────────────────────────────────
    if fname.endswith(IMAGE_EXTS):
        if _ocr_available():
            text = _extract_image_ocr(file_path)
            return {"text": text, "tables": [], "method": "image_ocr", "filename": filename}
        else:
            logger.warning("[DOC] tesseract not available — cannot OCR image")
            return {"text": "", "tables": [], "method": "image_no_ocr", "filename": filename}

    # ── Unknown ──────────────────────────────
    raise ValueError(f"Unsupported file format: '{filename}'. Supported: PDF, CSV, Excel (.xls/.xlsx), Images (PNG/JPG/TIFF)")


# ─────────────────────────────────────────────
# Chunking (for RAG pipeline — unchanged API)
# ─────────────────────────────────────────────
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Splits text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += (chunk_size - overlap)
    return chunks


def process_file(file_path: str, filename: str) -> List[Dict]:
    """Extracts text, chunks it, and attaches metadata. (RAG pipeline compat)"""
    result = parse_document(file_path, filename)
    text = result["text"]
    if not text.strip():
        raise ValueError("No text could be extracted from document.")
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("No text chunks could be created from document.")
    return [
        {"chunk_id": f"{filename}_chunk_{i}", "filename": filename, "text": chunk}
        for i, chunk in enumerate(chunks)
    ]
