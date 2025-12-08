import streamlit as st
import fitz  # PyMuPDF
from io import BytesIO

st.set_page_config(page_title="Label Cropper (3-across)", page_icon="✂️")

st.title("✂️ PDF Label Cropper – 3 labels across, 1 row")
st.markdown(
    """
This app assumes your PDF has **3 labels across and 1 row** per page.

It will crop the page so the output PDF has **only one label per sheet**.
By default, it uses the **first (leftmost) label**.
"""
)

uploaded_file = st.file_uploader("Upload your label sheet PDF", type=["pdf"])

if uploaded_file is not None:
    pdf_bytes = uploaded_file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    page_count = len(doc)
    st.write(f"Pages detected: **{page_count}**")

    page_number = st.number_input(
        "Page to use (1 = first page)",
        min_value=1,
        max_value=page_count,
        value=1,
        step=1,
    )

    label_choice = st.radio(
        "Which label do you want?",
        options=[1, 2, 3],
        index=0,  # default = 1 (first)
        format_func=lambda x: f"Label {x} (col {x})",
        horizontal=True,
    )

    if st.button("Crop to selected label"):
        page_index = page_number - 1
        page = doc[page_index]
        full_rect = page.rect

        cols = 3  # fixed: 3 labels across
        label_width = full_rect.width / cols
        label_height = full_rect.height  # 1 row

        label_index = label_choice - 1  # 0,1,2
        x0 = label_index * label_width
        y0 = 0
        x1 = x0 + label_width
        y1 = y0 + label_height

        clip_rect = fitz.Rect(x0, y0, x1, y1)

        # Build new 1-label PDF
        new_doc = fitz.open()
        new_page = new_doc.new_page(width=clip_rect.width, height=clip_rect.height)
        new_page.show_pdf_page(new_page.rect, doc, page_index, clip=clip_rect)

        pdf_out = BytesIO()
        new_doc.save(pdf_out)
        new_doc.close()
        doc.close()

        pdf_out.seek(0)

        st.download_button(
            "⬇️ Download cropped label PDF",
            data=pdf_out,
            file_name=f"cropped_label_{label_choice}.pdf",
            mime="application/pdf",
        )

        # Simple preview
        preview_doc = fitz.open(stream=pdf_out.getvalue(), filetype="pdf")
        preview_page = preview_doc[0]
        pix = preview_page.get_pixmap()
        img_bytes = pix.tobytes("png")
        st.image(img_bytes, caption=f"Cropped Label {label_choice} Preview")
        preview_doc.close()
