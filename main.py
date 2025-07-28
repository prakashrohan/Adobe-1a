#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF Outline Extractor with Language‑Adaptive Heading Inclusion

– Uses PyMuPDF to extract font‑size–based headings.
– If a line is in English, it must also match numbering/colon cues.
– If it's detected as another language, size alone suffices.
"""
import os
import json
import argparse
import fitz  # PyMuPDF
import regex as re      # pip install regex
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0

# Unicode punctuation stripper
PUNCT_STRIP = re.compile(r"^\p{P}+|\p{P}+$", re.UNICODE)
# English semantic cues
NUMERIC_RE = re.compile(r"^[0-9IVX]+[\.|\)]+")
COLON_RE   = re.compile(r":$")

def _jsonable(o):
    if isinstance(o, (str, int, float, bool)) or o is None:
        return o
    if isinstance(o, (list, tuple)):
        return [_jsonable(x) for x in o]
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    return str(o)

def extract_with_fallback(doc, fname):
    # 1) Gather all lines with their max font size
    lines, size_counts = [], {}
    for p in range(doc.page_count):
        page = doc.load_page(p)
        for blk in page.get_text("dict")["blocks"]:
            if blk.get("type") != 0:
                continue
            for ln in blk["lines"]:
                spans = ln.get("spans", [])
                txt = "".join(sp["text"] for sp in spans).strip()
                if not txt:
                    continue
                sz = round(max(sp.get("size", 0) for sp in spans), 1)
                lines.append((p+1, txt, sz))
                size_counts[sz] = size_counts.get(sz, 0) + len(txt.split())

    if not size_counts:
        return fname, []

    # 2) Identify heading‑sizes by dropping the most frequent (body text)
    body_sz = max(size_counts, key=size_counts.get)
    size_counts.pop(body_sz, None)
    if not size_counts:
        return fname, []

    header_sizes = sorted(size_counts.keys(), reverse=True)[:3]
    h1_sz = header_sizes[0]

    # 3) Build title from H1 lines on page 1
    title_lines = [txt for pg, txt, sz in lines if pg==1 and sz==h1_sz]
    if title_lines:
        seen = set()
        title = " ".join(x for x in title_lines if not (x in seen or seen.add(x)))
    else:
        meta = doc.metadata or {}
        title = (meta.get("title") or fname).strip()

    # 4) Assemble outline
    outline = []
    for pg, txt, sz in lines:
        if sz not in header_sizes:
            continue
        lvl = header_sizes.index(sz) + 1
        if lvl > 3:
            continue
        # skip title lines
        if lvl==1 and pg==1 and txt in title_lines:
            continue

        # detect language
        try:
            lang = detect(txt)
        except:
            lang = "en"

        # for English, enforce semantic cue
        if lang.startswith("en"):
            if not (NUMERIC_RE.match(txt) or COLON_RE.search(txt)):
                continue
        # for other languages, size alone suffices

        clean = PUNCT_STRIP.sub("", txt)
        outline.append({"level": f"H{lvl}", "text": clean, "page": pg})

    return title, outline

def process_pdf(path, out_dir):
    fname = os.path.splitext(os.path.basename(path))[0]
    doc = fitz.open(path)
    # we skip TOC-based extraction for brevity
    title, outline = extract_with_fallback(doc, fname)
    doc.close()

    out = {"title": title or fname, "outline": outline}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"{fname}.json"), "w", encoding="utf-8") as f:
        json.dump(_jsonable(out), f, ensure_ascii=False, indent=2)
    print(f"Processed {fname}")

def main():
    p = argparse.ArgumentParser(description="Unicode‑aware PDF outline extractor")
    p.add_argument("--in_dir",  default="data/input_pdfs")
    p.add_argument("--out_dir", default="data/processed")
    args = p.parse_args()

    for fn in sorted(os.listdir(args.in_dir)):
        if fn.lower().endswith(".pdf"):
            process_pdf(os.path.join(args.in_dir, fn), args.out_dir)
    print("Done.")

if __name__ == "__main__":
    main()