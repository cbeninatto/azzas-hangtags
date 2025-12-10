import io
import re
from pathlib import Path
from typing import Optional, List, Dict

import fitz  # PyMuPDF
import streamlit as st
import zipfile


# ---------- Config ----------

# Target single-label size taken from your reference PDF (C50039 0007 0001)
REF_LABEL_WIDTH = 82.68998718261719
REF_LABEL_HEIGHT = 78.56026458740234


# ---------- Core PDF helpers ----------

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
    Extracts a SKU like 'C50039 0007 0001' or 'C40008 0003 0002' from the label text.

    Handles both:
      - 'C50039 0007 0001'
      - 'C 50039 0007 0001'
    """
    normalized = " ".join(label_text.split())
    pattern = r"([A-Z])\s?(\d{5})\s+(\d{4})\s+(\d{4})"
    m = re.search(pattern, normalized)
    if not m:
        return None
    return f"{m.group(1)}{m.group(2)} {m.group(3)} {m.group(4)}"


def find_barcode_word_bbox(page, clip_rect):
    """
    Inside the label clip, find the 'word' that most likely corresponds
    to the barcode digits (longest mostly-numeric word).
    """
    words = page.get_text("words", clip=clip_rect) or []
    best = None
    best_len = 0

    for w in words:
        x0, y0, x1, y1, text, *rest = w
        digits = re.sub(r"\D", "", text)
        if len(digits) > best_len:
            best_len = len(digits)
            best = (x0, y0, x1, y1, text, digits)

    if best is None or best_len < 8:
        return None  # no convincing barcode text found

    return best


def process_pdf_bytes(
    file_bytes: bytes,
    original_name: str,
    cols: int = 3,
    padding_x: int = 5,
    padding_y: int = 8,
) -> List[Dict]:
    """
    Process a single PDF (in-memory bytes).

    Returns a list of dicts for each UNIQUE SKU found in the leftmost label across all pages.
    Each dict contains a SINGLE-PAGE cropped PDF bytes and metadata.

    Cropping is *horizontally centered on the barcode digits* and scaled to the
    fixed reference size REF_LABEL_WIDTH × REF_LABEL_HEIGHT, so the margin
    from barcode to left/right edges is the same for all SKUs.
    """
    results: List[Dict] = []

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Error opening {original_name}: {e}")
        return results

    if len(doc) == 0:
        st.warning(f"{original_name}: no pages.")
        doc.close()
        return results

    seen_skus = set()

    for page_index in range(len(doc)):
        page = doc[page_index]

        # 1) Rough label area from text clustering (leftmost column)
        label_rect = compute_first_label_clip(
            page, cols=cols, padding_x=padding_x, padding_y=padding_y
        )

        # 2) Read SKU from that area
        label_text = page.get_text("text", clip=label_rect) or ""
        sku = extract_sku(label_text)
        if not sku:
            continue

        if sku in seen_skus:
            continue  # already processed this SKU from this file
        seen_skus.add(sku)

        # 3) Find barcode digits bounding box inside the label
        barcode_info = find_barcode_word_bbox(page, label_rect)
        if barcode_info is None:
            # Fallback: use label_rect as-is (will still be standardized later)
            final_clip = label_rect
        else:
            bx0, by0, bx1, by1, text, digits = barcode_info
            center_x = (bx0 + bx1) / 2.0

            # Horizontally, we want a fixed width centered on the barcode digits
            target_w = REF_LABEL_WIDTH
            page_rect = page.rect

            min_x = center_x - target_w / 2.0
            max_x = center_x + target_w / 2.0

            # Keep it inside the page
            if min_x < 0:
                shift = -min_x
                min_x = 0
                max_x += shift
            if max_x > page_rect.width:
                shift = max_x - page_rect.width
                max_x = page_rect.width
                min_x -= shift

            # Vertically, align with the label_rect but match the reference height
            target_h = REF_LABEL_HEIGHT
            min_y = label_rect.y0
            max_y = min_y + target_h
            if max_y > page_rect.height:
                max_y = page_rect.height
                min_y = max_y - target_h

            final_clip = fitz.Rect(min_x, min_y, max_x, max_y)

        # 4) Build filename: CHILE BARCODE HANGTAG <SKU>.pdf
        out_name = f"CHILE BARCODE HANGTAG {sku}.pdf"

        # 5) Create a 1-page PDF with the cropped label, scaled to reference size
        new_doc = fitz.open()
        new_page = new_doc.new_page(
            width=REF_LABEL_WIDTH,
            height=REF_LABEL_HEIGHT,
        )
        new_page.show_pdf_page(
            new_page.rect,
            doc,
            page_index,
            clip=final_clip,
        )
        pdf_bytes = new_doc.tobytes()
        new_doc.close()

        results.append(
            {
                "output_name": out_name,
                "original_name": original_name,
                "sku": sku,
                "pdf_bytes": pdf_bytes,  # single-page PDF at reference size
            }
        )

    doc.close()
    return results


# ---------- Streamlit UI ----------

st.set_page_config(page_title="Chile Label Extractor", page_icon="🏷️")

st.title("🏷️ Chile Label Extractor – One PDF per SKU")

st.markdown(
    """
### Step 1 – Upload & process

Upload one or more **multi-page PDFs** with label sheets.

For each PDF, this app will:

- Scan all pages  
- Look at the **leftmost label** on each page  
- Extract the SKU in the format `C50039 0007 0001`  
- Keep **only one label per SKU**  
- Create a single-page PDF named:

`CHILE BARCODE HANGTAG C50039 0007 0001.pdf`

The output page size is fixed to match your reference label,
and the barcode is centered horizontally so the margins to the sides are identical
for all SKUs.
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

# Initialize session state store for processed labels
if "processed_labels" not in st.session_state:
    st.session_state["processed_labels"] = []


# ---- Step 1: Process PDFs ----

if st.button("✅ Process PDFs (step 1)"):
    if not uploaded_files:
        st.warning("Please upload at least one PDF first.")
    else:
        all_labels: List[Dict] = []
        for f in uploaded_files:
            st.write(f"**Processing:** {f.name}")
            file_bytes = f.read()
            labels = process_pdf_bytes(
                file_bytes,
                f.name,
                cols=int(cols),
                padding_x=int(padding_x),
                padding_y=int(padding_y),
            )
            all_labels.extend(labels)

        st.session_state["processed_labels"] = all_labels

        if not all_labels:
            st.warning("No labels with recognizable SKUs were found.")
        else:
            st.success(f"Found {len(all_labels)} unique labels (by SKU). See Step 2 below.")


processed_labels = st.session_state.get("processed_labels", [])

# ---- Step 2: Per-label duplication & ZIP download ----

if processed_labels:
    st.markdown("---")
    st.subheader("Step 2 – Choose pages per label and download")

    st.markdown(
        "For each label SKU below, set how many **pages** you want in the final PDF."
    )

    # Show per-label controls
    for i, item in enumerate(processed_labels):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(
                f"- **{item['output_name']}**  "
                f"(source: `{item['original_name']}`, SKU: `{item['sku']}`)"
            )
        with col2:
            key = f"copies_{i}"
            default_value = st.session_state.get(key, 1)
            st.number_input(
                "Pages",
                min_value=1,
                max_value=999,
                value=default_value,
                step=1,
                key=key,
            )

    # Build ZIP using current page settings
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, item in enumerate(processed_labels):
            copies = int(st.session_state.get(f"copies_{i}", 1))

            # Open the standardized single-page PDF
            base_pdf = fitz.open(stream=item["pdf_bytes"], filetype="pdf")
            src_page = base_pdf[0]
            rect = src_page.rect

            # Build a new PDF with `copies` identical pages
            new_doc = fitz.open()
            for _ in range(max(1, copies)):
                new_page = new_doc.new_page(width=rect.width, height=rect.height)
                new_page.show_pdf_page(new_page.rect, base_pdf, 0)

            pdf_bytes_multi = new_doc.tobytes()
            new_doc.close()
            base_pdf.close()

            zf.writestr(item["output_name"], pdf_bytes_multi)

    zip_buffer.seek(0)

    st.download_button(
        label="⬇️ Download labels as ZIP (step 2)",
        data=zip_buffer.getvalue(),
        file_name="labels_by_sku.zip",
        mime="application/zip",
    )
else:
    st.info("Upload PDFs and click **Process PDFs (step 1)** to start.")
