#!/usr/bin/env python3
import os
import json
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed

import fitz            # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0

INPUT_DIR  = os.environ.get("PDF_INPUT_DIR",  "./input")
OUTPUT_DIR = os.environ.get("PDF_OUTPUT_DIR", "./output")


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def extract_metadata(path):
    doc = fitz.open(path)
    m = doc.metadata or {}
    md = {
        "title":         m.get("title"),
        "author":        m.get("author"),
        "creation_date": m.get("creationDate"),
        "mod_date":      m.get("modDate"),
        "pages":         doc.page_count
    }
    doc.close()
    return md

def extract_outline(doc):
    font_counts = {}
    for page in doc:
        for blk in page.get_text("dict")["blocks"]:
            if blk.get("type") != 0: continue
            for ln in blk["lines"]:
                for sp in ln["spans"]:
                    f = sp.get("font", "")
                    font_counts[f] = font_counts.get(f, 0) + 1

    candidates = [f for f in font_counts if any(k in f.lower() for k in ("bold","black","heavy","medium"))]
    heads = sorted(candidates, key=lambda f: font_counts[f], reverse=True)[:3]

    outline = []
    title   = None
    page_w  = None

    for pnum, page in enumerate(doc, 1):
        if page_w is None:
            page_w = page.rect.width
        for blk in page.get_text("dict")["blocks"]:
            if blk.get("type") != 0: continue
            for ln in blk["lines"]:
                if len(ln["spans"]) != 1: 
                    continue
                sp  = ln["spans"][0]
                txt = sp.get("text","").strip()
                fnt = sp.get("font","")
                if not txt or fnt not in heads:
                    continue
                x0,y0,x1,y1 = sp["bbox"]
                if (x1-x0) < page_w * 0.5 or len(txt) > 100:
                    continue
                lvl = f"H{heads.index(fnt)+1}"
                outline.append({"level": lvl, "text": txt, "page": pnum})
                if pnum == 1 and title is None:
                    title = txt

    if not outline:
        all_spans = []
        for pnum, page in enumerate(doc, 1):
            for blk in page.get_text("dict")["blocks"]:
                if blk.get("type") != 0: continue
                for ln in blk["lines"]:
                    for sp in ln["spans"]:
                        size = round(sp.get("size", 0), 1)
                        txt  = sp.get("text","").strip()
                        if txt:
                            all_spans.append((size, pnum, txt))
        if all_spans:
            top_sizes = sorted({s for s,_,_ in all_spans}, reverse=True)[:3]
            for size, pnum, txt in all_spans:
                if size in top_sizes:
                    lvl = f"H{top_sizes.index(size)+1}"
                    outline.append({"level": lvl, "text": txt, "page": pnum})
            if title is None:
                for size, pnum, txt in all_spans:
                    if pnum == 1 and size == top_sizes[0]:
                        title = txt
                        break
    if title is None:
        title = os.path.splitext(os.path.basename(doc.name))[0]

    return title, outline

def extract_full_text(doc):
    pages = []
    for pnum, page in enumerate(doc,1):
        txt = page.get_text("text") or ""
        lang = None
        if txt.strip():
            try:
                lang = detect(txt)
            except:
                lang = None
        if not txt.strip():
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(2,2), alpha=False)
                mode = "RGB" if pix.n >= 3 else "L"
                img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
                txt = pytesseract.image_to_string(img)
                lang = None
            except Exception as e:
                logging.warning(f"OCR failed on page {pnum}: {e}")
        pages.append({"page":pnum, "text":txt, "language":lang})
    return pages

def extract_tables(path):
    tbls = []
    with pdfplumber.open(path) as pdf:
        for pnum, page in enumerate(pdf.pages,1):
            for idx, t in enumerate(page.extract_tables() or [],1):
                tbls.append({"page":pnum,"table_index":idx,"rows":t})
    return tbls

def extract_images(doc, out_dir, base):
    imgs = []
    folder = os.path.join(out_dir, f"{base}_images")
    os.makedirs(folder, exist_ok=True)
    for pnum, page in enumerate(doc,1):
        for idx, img in enumerate(page.get_images(full=True),1):
            xref = img[0]; pix = fitz.Pixmap(doc, xref)
            name = f"{base}_page{pnum}_img{idx}.png"
            path = os.path.join(folder, name)
            if pix.n < 5:
                pix.save(path)
            else:
                pix0 = fitz.Pixmap(fitz.csRGB, pix); pix0.save(path); pix0 = None
            pix = None
            imgs.append({"page":pnum,"file":os.path.join(os.path.basename(folder),name)})
    return imgs

def extract_links_and_annots(doc):
    links = []
    annots = []
    for pnum, page in enumerate(doc, start=1):
        for l in page.get_links():
            r = l.get("from")
            links.append({
                "page": pnum,
                "uri": l.get("uri"),
                "rect": {
                    "x0": r.x0, "y0": r.y0,
                    "x1": r.x1, "y1": r.y1
                }
            })
        a = page.first_annot
        while a:
            r = a.rect
            annots.append({
                "page": pnum,
                "type": a.type[0],
                "rect": {
                    "x0": r.x0, "y0": r.y0,
                    "x1": r.x1, "y1": r.y1
                }
            })
            a = a.next
    return {"links": links, "annotations": annots}

def process_file(path):
    base    = os.path.splitext(os.path.basename(path))[0]
    doc_dir = os.path.join(OUTPUT_DIR, base)
    os.makedirs(doc_dir, exist_ok=True)
    try:
        logging.info(f"▶️ Start {base}")
        md          = extract_metadata(path)
        doc         = fitz.open(path)
        title, outl = extract_outline(doc)
        pages       = extract_full_text(doc)
        tables      = extract_tables(path)
        images      = extract_images(doc, doc_dir, base)
        links_ann   = extract_links_and_annots(doc)
        doc.close()

        result = {
            "metadata":   md,
            "title":      title,
            "outline":    outl,
            "pages":      pages,
            "tables":     tables,
            "images":     images,
            **links_ann
        }
        with open(os.path.join(doc_dir, f"{base}.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logging.info(f"✅ Done  {base}")
    except Exception as e:
        logging.error(f"❌ Failed {base}: {e}", exc_info=True)

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pdfs = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".pdf")]
    with ProcessPoolExecutor() as pool:
        futures = {pool.submit(process_file, os.path.join(INPUT_DIR, f)): f for f in pdfs}
        for _ in as_completed(futures):
            pass

if __name__ == "__main__":
    main()
