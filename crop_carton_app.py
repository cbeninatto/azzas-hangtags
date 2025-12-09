import re
from io import BytesIO

import numpy as np
from PIL import Image

import fitz  # PyMuPDF
import streamlit as st
import zipfile


TARGET_WIDTH = 680
TARGET_HEIGHT = 480
TARGET_RATIO = TARGET_WIDTH / TARGET_HEIGHT


def extract_reference(text: str) -> str:
    """Extract REFERENCIA code like C400080003XX from page text."""
    match = re.search(r"REFERENCIA:\s*([A-Z0-9]+)", text)
    if match:
        return match.group(1)
    return "UNKNOWN"


def extract_groups(doc):
    """Return dict mapping REFERENCIA -> list of page indices."""
    groups = {}
    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text()
        ref = extract_reference(text)
        groups.setdefault(ref, []).append(i)
    return groups


def detect_crop_rect(
    doc,
    target_ratio: float = TARGET_RATIO,
    zoom: float = 2.0,
    threshold: int = 250,
):
    """
    Detect a crop rectangle on the first page based on non-white content.

    Returns:
        crop_rect_pdf (fitz.Rect): rectangle in PDF coordinates
        preview (PIL.Image): 680x480 preview image of the cropped area
    """
    page = doc[0]
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)

    # Build PIL image from pixmap
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    gray = img.convert("L")
    arr = np.array(gray)

    # Find all non-white pixels
    mask = arr < threshold
    ys, xs = np.where(mask)
    if xs.size == 0 or ys.size == 0:
        # Fallback: no content detected, use the whole page
        preview = img.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)
        return page.rect, preview

    min_x, max_x = xs.min(), xs.max()
    min_y, max_y = ys.min(), ys.max()
    x0, y0, x1, y1 = float(min_x), float(min_y), float(max_x), float(max_y)
    width = x1 - x0
    height = y1 - y0

    # Adjust to desired aspect ratio by expanding the box
    current_ratio = width / height
    if current_ratio > target_ratio:
        # Too wide: increase height
        new_height = width / target_ratio
        center_y = (y0 + y1) / 2
        y0 = center_y - new_height / 2
        y1 = center_y + new_height / 2
    else:
        # Too tall: increase width
        new_width = height * target_ratio
        center_x = (x0 + x1) / 2
        x0 = center_x - new_width / 2
        x1 = center_x + new_width / 2

    # Clamp to image bounds
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(pix.width, x1)
    y1 = min(pix.height, y1)

    # Create preview image at 680x480
    crop_box_px = (int(round(x0)), int(round(y0)),
                   int(round(x1)), int(round(y1)))
    cropped = img.crop(crop_box_px)
    preview = cropped.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)

    # Convert pixel rect to PDF coordinates
    page_rect = page.rect
    scale_x = page_rect.width / pix.width
    scale_y = page_rect.height / pix.height
    crop_rect_pdf = fitz.Rect(
        x0 * scale_x,
        y0 * scale_y,
        x1 * scale_x,
        y1 * scale_y,
    )

    return crop_rect_pdf, preview


def build_group_pdfs(doc, groups, crop_rect):
    """Create one cropped PDF per REFERENCIA.

    Returns:
        dict[str, tuple[str, BytesIO]] mapping ref -> (filename, buffer)
    """
    outputs = {}
    for ref, page_indices in groups.items():
        out_doc = fitz.open()
        for idx in page_indices:
            out_doc.insert_pdf(doc, from_page=idx, to_page=idx)
            page = out_doc[-1]
            page.set_cropbox(crop_rect)

        buffer = BytesIO()
        out_doc.save(buffer)
        out_doc.close()
        buffer.seek(0)

        filename = f"CARTON BARCODE - {ref}.pdf"
        outputs[ref] = (filename, buffer)

    return outputs


def build_zip(outputs):
    """Pack all generated PDFs into a single ZIP buffer."""
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for filename, buf in outputs.values():
            zf.writestr(filename, buf.getvalue())
    zip_buffer.seek(0)
    return zip_buffer


def main():
    st.set_page_config(
        page_title="Carton Barcode Cropper",
        page_icon="📦",
        layout="centered",
    )
    st.title("📦 Carton Barcode Cropper")

    st.markdown(
        """\
Upload the consolidated **picking PDF** and this app will:

1. Detect the label area on the first page and crop every page to that region
   (output aspect ratio ≈ **680 × 480 px**).
2. Group pages by **REFERENCIA** (e.g. `C400080003XX`).
3. Generate one PDF per REFERENCIA with filenames like  
   `CARTON BARCODE - C400080003XX.pdf`.
        """
    )

    uploaded = st.file_uploader("Upload PDF", type=["pdf"])

    if not uploaded:
        return

    pdf_bytes = uploaded.read()

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Could not open PDF: {e}")
        return

    st.success(f"Loaded PDF with {len(doc)} page(s).")

    with st.spinner("Detecting crop area from first page..."):
        crop_rect, preview = detect_crop_rect(doc)

    st.subheader("Crop preview (680 × 480 px)")
    st.image(
        preview,
        caption="What each output page will look like",
        width=TARGET_WIDTH,
    )

    with st.spinner("Reading REFERENCIA codes..."):
        groups = extract_groups(doc)

    if not groups:
        st.error("No REFERENCIA codes were found in the document.")
        return

    st.subheader("Detected REFERENCIA groups")
    summary_rows = [
        {"REFERENCIA": ref, "Pages": len(pages)}
        for ref, pages in sorted(groups.items())
    ]
    st.dataframe(summary_rows, hide_index=True)

    if st.button("Generate cropped PDFs"):
        with st.spinner("Building grouped & cropped PDFs..."):
            outputs = build_group_pdfs(doc, groups, crop_rect)
            zip_buffer = build_zip(outputs)

        st.success("Done! Download your files below.")

        # Individual downloads
        for ref, (filename, buf) in outputs.items():
            st.download_button(
                label=f"Download {filename}",
                data=buf,
                file_name=filename,
                mime="application/pdf",
                key=f"download-{ref}",
            )

        # Zip download
        st.download_button(
            label="⬇️ Download all as ZIP",
            data=zip_buffer,
            file_name="carton_barcodes.zip",
            mime="application/zip",
        )


if __name__ == "__main__":
    main()
