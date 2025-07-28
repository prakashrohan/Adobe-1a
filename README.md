
# 📘 PDF Outline Extractor

**Language-Adaptive PDF Heading Detection with PyMuPDF**

This tool extracts structured document outlines (headings like H1, H2, H3) from PDF files using a combination of font-size analysis and semantic cues. It works fully offline, supports multilingual documents, and outputs clean JSON for downstream processing.

---

## 🚀 Features

- ✅ Font-size–based heading detection using **PyMuPDF**
- 🌍 **Language-aware** logic:
  - English: requires numbering (e.g., `1.`) or a colon (`:`)
  - Other languages: font size alone is enough
- 🧠 Auto-infers document **title** from the first page
- 🧼 Cleans Unicode punctuation and stray characters
- 💾 Outputs per-file `outline.json` with heading levels and page numbers
- 🐳 Dockerized for easy deployment

---

## 📂 Output Format

Each PDF results in a `.json` file:
```json
{
  "title": "Research Paper",
  "outline": [
    { "level": "H1", "text": "1. Introduction", "page": 1 },
    { "level": "H2", "text": "2. Background", "page": 2 },
    { "level": "H3", "text": "2.1 Related Work", "page": 3 }
  ]
}
```

---

## 🧱 How It Works

1. **Line Collection:** Gathers all text lines from all pages, along with their max font size.
2. **Body Text Filtering:** The most frequent font size is assumed to be body text and is ignored for headings.
3. **Heading Detection:**
   - Retains the top 2–3 largest remaining sizes.
   - For English text, the line must start with a number or end with a colon.
   - Other languages rely on size alone.
4. **Output:** Produces structured headings per document with levels (H1, H2, H3) and page numbers.

---

## 📦 Installation

### ✅ Requirements

- Python 3.8+
- [PyMuPDF (fitz)](https://pymupdf.readthedocs.io)
- `langdetect`
- `regex` (Unicode-aware)

### Install dependencies:
```bash
pip install -r requirements.txt
```

### `requirements.txt`:
```
PyMuPDF==1.24.1
regex==2023.12.25
langdetect==1.0.9
```

---

## 🐳 Docker Setup

### 🔧 Build the image

```bash
docker build -t pdf-outline .
```

### ▶️ Run the container

```bash
docker run --rm \
  -v $(pwd)/input:/app/input \
  -v $(pwd)/output:/app/output \
  pdf-outline
```

---

## 🖥️ Local Usage

### Command-line Interface:
```bash
python main.py --in_dir data/input_pdfs --out_dir data/processed
```

### Arguments:
| Flag        | Description                        | Default             |
|-------------|------------------------------------|---------------------|
| `--in_dir`  | Folder with PDF files              | `data/input_pdfs`   |
| `--out_dir` | Folder where JSON results go       | `data/processed`    |

---

## 🧪 Example

Put a sample PDF inside `data/input_pdfs/`, then run:

```bash
python main.py
```

You will get JSON files in `data/processed/` named after each input PDF.

---

## 🧹 Punctuation Cleanup

- Strips leading/trailing Unicode punctuation (e.g., `■`, `–`, `:`)
- Converts Roman numerals (I, II, III, etc.)
- Ensures clean `text` fields in output



