#!/usr/bin/env python3
import os
import json
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed

import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image
from langdetect import detect, DetectorFactory

# Ensure deterministic language detection
DetectorFactory.seed = 0

# Directories for input and output PDFs
INPUT_PATH = os.environ.get("PDF_INPUT_DIR", "./input")
OUTPUT_PATH = os.environ.get("PDF_OUTPUT_DIR", "./output")

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def get_document_metadata(file_path):
    """
    Extract basic metadata from a PDF file.
    """
    doc = fitz.open(file_path)
    meta = doc.metadata or {}
    info = {
        "title": meta.get("title"),
        "author": meta.get("author"),
        "creation_date": meta.get("creationDate"),
        "modification_date": meta.get("modDate"),
        "page_count": doc.page_count
    }
    doc.close()
    return info


def parse_outline(pdf_doc):
    """
    Identify document headings by analyzing font usage, falling back to font size if needed.
    Returns a tuple of (title, outline_entries).
    """
    # Count occurrences of each font
    font_usage = {}
    for page in pdf_doc:
        blocks = page.get_text("dict").get("blocks", [])
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    font = span.get("font", "")
                    font_usage[font] = font_usage.get(font, 0) + 1

    # Select top fonts that imply headings
    bold_fonts = [f for f in font_usage if any(tok in f.lower() for tok in ("bold", "black", "heavy", "medium"))]
    heading_fonts = sorted(bold_fonts, key=lambda f: font_usage[f], reverse=True)[:3]

    outline = []
    doc_title = None
    page_width = None

    # Primary pass: look for spans using heading fonts
    for page_idx, page in enumerate(pdf_doc, start=1):
        if page_width is None:
            page_width = page.rect.width
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                if len(line["spans"]) != 1:
                    continue
                span = line["spans"][0]
                text = span.get("text", "").strip()
                font = span.get("font", "")
                if not text or font not in heading_fonts:
                    continue
                x0, y0, x1, y1 = span["bbox"]
                # Filter out very short or excessively long lines
                if (x1 - x0) < page_width * 0.5 or len(text) > 100:
                    continue
                level = f"H{heading_fonts.index(font) + 1}"
                outline.append({"level": level, "text": text, "page": page_idx})
                if page_idx == 1 and doc_title is None:
                    doc_title = text

    # Fallback: use font sizes if no outline found
    if not outline:
        all_spans = []
        for page_idx, page in enumerate(pdf_doc, start=1):
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        size = round(span.get("size", 0), 1)
                        txt = span.get("text", "").strip()
                        if txt:
                            all_spans.append((size, page_idx, txt))
        if all_spans:
            top_sizes = sorted({s for s, _, _ in all_spans}, reverse=True)[:3]
            for size, page_idx, txt in all_spans:
                if size in top_sizes:
                    lvl = f"H{top_sizes.index(size) + 1}"
                    outline.append({"level": lvl, "text": txt, "page": page_idx})
                    if page_idx == 1 and doc_title is None and size == top_sizes[0]:
                        doc_title = txt

    # Default title if none discovered
    if doc_title is None:
        doc_title = os.path.splitext(os.path.basename(pdf_doc.name))[0]

    return doc_title, outline


def extract_text_content(pdf_doc):
    """
    Extract text per page, with OCR fallback on blank pages.
    """
    pages = []
    for page_idx, page in enumerate(pdf_doc, start=1):
        text = page.get_text("text") or ""
        language = None
        if text.strip():
            try:
                language = detect(text)
            except:
                language = None
        else:
            # OCR on image-only pages
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                mode = "RGB" if pix.n >= 3 else "L"
                img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
                text = pytesseract.image_to_string(img)
            except Exception as err:
                logging.warning(f"OCR failed on page {page_idx}: {err}")
        pages.append({"page": page_idx, "text": text, "language": language})
    return pages


def extract_tables(pdf_path):
    """
    Use pdfplumber to pull tables from each page.
    """
    tables = []
    with pdfplumber.open(pdf_path) as doc:
        for page_idx, page in enumerate(doc.pages, start=1):
            for tbl_idx, table in enumerate(page.extract_tables() or [], start=1):
                tables.append({"page": page_idx, "table_index": tbl_idx, "rows": table})
    return tables


def save_page_images(pdf_doc, output_dir, base_name):
    """
    Extract embedded images and save them as PNGs.
    """
    saved = []
    img_dir = os.path.join(output_dir, f"{base_name}_images")
    os.makedirs(img_dir, exist_ok=True)
    for page_idx, page in enumerate(pdf_doc, start=1):
        for img_idx, img_info in enumerate(page.get_images(full=True), start=1):
            xref = img_info[0]
            pix = fitz.Pixmap(pdf_doc, xref)
            filename = f"{base_name}_p{page_idx}_img{img_idx}.png"
            filepath = os.path.join(img_dir, filename)
            if pix.n < 5:
                pix.save(filepath)
            else:
                rgb_pix = fitz.Pixmap(fitz.csRGB, pix)
                rgb_pix.save(filepath)
                rgb_pix = None
            pix = None
            saved.append({"page": page_idx, "file": os.path.join(os.path.basename(img_dir), filename)})
    return saved


def extract_links_and_annotations(pdf_doc):
    """
    Gather hyperlink and annotation details.
    """
    links = []
    annotations = []
    for page_idx, page in enumerate(pdf_doc, start=1):
        for link in page.get_links():
            frm = link.get("from")
            links.append({
                "page": page_idx,
                "uri": link.get("uri"),
                "rect": {"x0": frm.x0, "y0": frm.y0, "x1": frm.x1, "y1": frm.y1}
            })
        annot = page.first_annot
        while annot:
            r = annot.rect
            annotations.append({
                "page": page_idx,
                "type": annot.type[0],
                "rect": {"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1}
            })
            annot = annot.next
    return {"links": links, "annotations": annotations}


def process_pdf(file_path):
    """
    Orchestrate extraction for a single PDF.
    """
    base = os.path.splitext(os.path.basename(file_path))[0]
    dest = os.path.join(OUTPUT_PATH, base)
    os.makedirs(dest, exist_ok=True)
    logging.info(f"▶️ Processing {base}")
    try:
        metadata = get_document_metadata(file_path)
        pdf_doc = fitz.open(file_path)
        title, outline = parse_outline(pdf_doc)
        pages = extract_text_content(pdf_doc)
        tables = extract_tables(file_path)
        images = save_page_images(pdf_doc, dest, base)
        extras = extract_links_and_annotations(pdf_doc)
        pdf_doc.close()

        output = {
            "metadata": metadata,
            "title": title,
            "outline": outline,
            "pages": pages,
            "tables": tables,
            "images": images,
            **extras
        }
        with open(os.path.join(dest, f"{base}.json"), "w", encoding="utf-8") as fp:
            json.dump(output, fp, ensure_ascii=False, indent=2)
        logging.info(f"✅ Completed {base}")
    except Exception as error:
        logging.error(f"❌ Error in {base}: {error}", exc_info=True)


def main():
    # Prepare output folder
    os.makedirs(OUTPUT_PATH, exist_ok=True)
    # Find all PDFs in input directory
    pdfs = [f for f in os.listdir(INPUT_PATH) if f.lower().endswith(".pdf")]
    # Process in parallel
    with ProcessPoolExecutor() as executor:
        futures = {executor.submit(process_pdf, os.path.join(INPUT_PATH, p)): p for p in pdfs}
        for _ in as_completed(futures):
            pass


if __name__ == "__main__":
    main()
