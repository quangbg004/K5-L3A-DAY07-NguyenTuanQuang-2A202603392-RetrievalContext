"""Build a page-level text and visual index from the supplied WDR PDF."""
import argparse
from collections import Counter
from contextlib import closing
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
import re
from time import perf_counter

import pypdfium2 as pdfium
from pypdf import PdfReader

from day7 import write

SOURCE = "https://doi.org/10.1596/978-1-4648-2078-6"
REFERENCE = r"(Figure|Table|Map)\s+([A-Z0-9]+(?:\s*\.\s*\d+)+)"
CAPTION = re.compile(r"\b" + REFERENCE + r"(?=[\s:]|$)")


def ref_key(kind, label):
    compact = "".join(label.split()).casefold()
    return f"{kind.casefold()} {compact}"


def build(path, cache):
    start = perf_counter()
    labels = PdfReader(path).page_labels
    pages = []
    with pdfium.PdfDocument(path) as pdf:
        for index, label in enumerate(labels):
            with closing(pdf[index]) as page, closing(page.get_textpage()) as textpage:
                raw = textpage.get_text_range().replace("\r", "").replace("\u00ad", "")
                text = re.sub(r"(?<=\w)-\n(?=[a-z])", "", raw)
                text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
                refs = sorted({ref_key(*m.groups()) for m in CAPTION.finditer(text)}
                              if label.isdecimal() else set())
                pages.append({"page": index + 1, "label": label, "text": text,
                              "references": refs, "pdf_points": list(page.get_size())})
    manifest = {
        "title": "World Development Report 2024: The Middle-Income Trap",
        "source": SOURCE, "license": "CC BY 3.0 IGO; see rights page for third-party content",
        "pdf_sha256": sha256(path.read_bytes()).hexdigest(), "physical_pages": len(pages),
        "indexed_page_records": len(pages),
        "searchable_text_pages": sum(bool(p["text"]) for p in pages),
        "pages_without_text_layer": [p["page"] for p in pages if not p["text"]],
        "caption_pages": sum(bool(p["references"]) for p in pages),
        "references_by_kind": dict(Counter(r.split()[0] for p in pages for r in p["references"])),
        "image_region": [0, 0, 1, 1],
        "image_mode": "PDFium full-page raster, rendered on retrieval at 2x scale",
        "versions": {name: version(name) for name in ("pypdfium2", "pypdf", "pillow")},
        "index_seconds": perf_counter() - start, "index_api_cost_usd": 0,
    }
    write(cache, {"manifest": manifest, "pages": pages})
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    args = parser.parse_args()
    print(build(args.pdf, args.index))
