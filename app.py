import io
import re
from pathlib import Path
from typing import Optional, List, Tuple

import fitz  # PyMuPDF
import streamlit as st
import zipfile


def compute_first_label_clip(page, cols=3, padding_x=5, padding_y=8):
    """
    Finds the FIRST (leftmost) label on a page that has `cols` labels across (3).

    - Uses the x-centers of text blocks to cluster into `cols` columns.
    - Only keeps the leftmost cluster (column 1).
    - Builds a tight bounding box around that column's text.
    - Adds the same padding on left and right (padding_x) and on top/bottom (padding_y).
    """
    page_rect = page.rect
    blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, ...)

    xs = []
    block_data = []
    for b in blocks:
        if len(b) < 5:
            continue
        x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
        if not str(text).strip():
            continue

        cx = (x0 + x1) / 2.0  # center x of this block
        xs.append(cx)
        block_data.append((cx, x0, y0, x1, y1))

    # Fallback: if we somehow find no text
    if not xs:
        label_width = page_rect.width / cols
        return fitz.Rect(0, 0, label_width, page_rect.height)

    # --- 1D k-means on x-centers, initialized from the data range (not page width) ---
    k = cols
    minx, maxx = min(xs), max(xs)

    if k == 1 or maxx == minx:
        centers = [(minx + maxx) / 2.0]
        assignments = [0] * len(xs)
    else:
        spacing = (maxx - minx) / (k - 1)
        centers = [minx + i * spacing for i in range(k)]
        assignments = [0] * len(xs)

        for _ in range(10):
            # assign
            for i, x in enumerate(xs):
                assignments[i] = min(range(k), key=lambda j: abs(x - centers[j]))
            # recompute centers
            new_centers = centers[:]
            for j in range(k):
                members = [xs[i] for i, a in enumerate(assignments) if a == j]
                if members:
                    new_centers[j] = sum(members) / len(members)
            centers = new_centers

    # Group blocks per column
    col_blocks = {j: [] for j in range(len(centers))}
    for i, (cx, x0, y0, x1, y1) in enumerate(block_data):
        j = assignments[i]
        col_blocks[j].append((x0, y0, x1, y1))

    # Leftmost column = smallest center value
    sorted_indices = sorted(range(len(centers)), key=lambda j: centers[j])
    first_idx = sorted_indices[0]
    first_blocks = col_blocks.get(first_idx, [])

    # Fallback in weird cases
    if not first_blocks:
        label_width = page_rect.width / cols
        return fitz.Rect(0, 0, label_width, page_rect.height)

    # Tight bounding box of the first column's text
    xs0 = [b[0] for b in first_blocks]
    ys0 = [b[1] for b in first_blocks]
    xs1 = [b[2] for b in first_blocks]
    ys1 = [b[3] for b in first_blocks]

    min_x = max(0, min(xs0) - padding_x)
    max_x = min(page_rect.width, max(xs1) + padding_x)
    min_y = max(0, min(ys0) - padding_y)
    max_y = min(page_rect.height, max(ys1) + padding_y)

    return fitz.Rect(min_x, min_y, max_x, max_y)


def extract_sku(label_text: str) -> Optional[str]:
    """
    Extracts a SKU like 'C40008 0003 0002' from the label text.

    Handles both:
      - 'C40008 0003 0002'
      - 'C 40008 0003 0002'
    """
    normalized = " ".join(label_text.split())
    pattern = r"([A-Z])\s?(\d{5})\s+(\d{4})\s+(\d{4})"
    m = re.search(pattern, normalized)
    if not m:
        return None
    return f"{m.group(1)}{m.group(2)} {m.group(3)} {m.group(4)}"


def process_pdf_bytes(
    file_bytes: bytes,
    original_name: str,
    cols: int = 3,
    padding_x: int = 5,
    padding_y: int = 8,
) -> List[Tuple[str, bytes]]:
    """
    Process a single PDF (in-memory bytes).

    Returns a list of (output_filename, pdf_bytes) for each UNIQUE SKU
    found in the leftmost label across all pages.
    """
    outputs: List[Tuple[str, bytes]] = []

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Error opening {original_name}: {e}")
        return outputs

    if len(doc) == 0:
        st.warning(f"{original_name}: no pages.")
        doc.close()
        return outputs

    base_name = Path(original_name).stem
    seen_skus = set()

    for page_index in range(len(doc)):
        page = doc[page_index]

        clip_rect = compute_first_label_clip(
            page, cols=cols, padding_x=padding_x, padding_y=padding_y
        )

        label_text = page.get_text("text", clip=clip_rect) or ""
        sku = extract_sku(label_text)

        if not sku:
            continue

        if sku in seen_skus:
            continue  # already processed this SKU

        seen_skus.add(sku)

        out_name = f"{base_name} - {sku}.pdf"

        new_doc = fitz.open()
        new_page = new_doc.new_page(
            width=clip_rect.width,
            height=clip_rect.height,
        )
        new_page.show_pdf_page(
            new_page.rect,
            doc,
            page_index,
            clip=clip_rect,
        )
        pdf_bytes = new_doc.tobytes()
        new_doc.close()

        outputs.append((out_name, pdf_bytes))

    doc.close()
    return outputs


# -------- Streamlit UI --------

st.set_page_config(page_title="Chile Label Extractor", page_icon="🏷️")

st.title("🏷️ Chile Label Extractor – One PDF per SKU")

st.markdown(
    """
Upload one or more **multi-page PDFs** with label sheets.

For each PDF, this app will:

- Scan all pages
- Look at the **leftmost label** on each page
- Extract the SKU in the format `C40008 0003 0002`
- Keep **only one label per SKU**
- Output cropped PDFs named like:

`HANGTAG BARCODE CHILE - C40008 0003 0002.pdf`
"""
)

uploaded_files = st.file_uploader(
    "Upload your PDF files",
    type=["pdf"],
    accept_multiple_files=True,
)

cols = st.number_input("Labels across per page (columns)", min_value=1, value=3, step=1)
padding_x = st.number_input("Horizontal padding (px)", min_value=0, value=5, step=1)
padding_y = st.number_input("Vertical padding (px)", min_value=0, value=8, step=1)

if uploaded_files and st.button("Process PDFs"):
    all_outputs: List[Tuple[str, bytes]] = []
    sku_log = []

    for f in uploaded_files:
        st.write(f"**Processing:** {f.name}")
        file_bytes = f.read()
        outputs = process_pdf_bytes(
            file_bytes,
            f.name,
            cols=int(cols),
            padding_x=int(padding_x),
            padding_y=int(padding_y),
        )
        all_outputs.extend(outputs)
        for name, _ in outputs:
            sku_part = name.split(" - ", 1)[-1].replace(".pdf", "")
            sku_log.append((f.name, sku_part))

    if not all_outputs:
        st.warning("No labels with recognizable SKUs were found.")
    else:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, pdf_bytes in all_outputs:
                zf.writestr(filename, pdf_bytes)
        zip_buffer.seek(0)

        st.success(f"Done! Generated {len(all_outputs)} label PDFs.")

        st.download_button(
            label="⬇️ Download all labels as ZIP",
            data=zip_buffer.getvalue(),
            file_name="labels_by_sku.zip",
            mime="application/zip",
        )

        if sku_log:
            st.subheader("SKUs found")
            for original, sku in sku_log:
                st.write(f"- **{original}** → `{sku}`")
