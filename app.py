import streamlit as st
import pdfplumber
import json
import requests
from openai import OpenAI

# ---------------------------------
# STREAMLIT PAGE CONFIG
# ---------------------------------
st.set_page_config(page_title="BAYONA SPA", layout="centered")
st.title("BAYONA SPA")
st.write("Upload one or multiple PDFs to generate ZPL hangtags with automatic LabelZoom rendering.")

# ---------------------------------
# INIT OPENAI
# ---------------------------------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Load Chile Hangtag system prompt
SYSTEM_PROMPT = open("system_prompt.txt").read()


# ---------------------------------
# HELPER FUNCTIONS
# ---------------------------------

def dedupe_text(raw_text):
    """Remove duplicate lines while keeping original order."""
    seen = set()
    unique = []
    for line in raw_text.split("\n"):
        clean = line.strip()
        if clean and clean not in seen:
            seen.add(clean)
            unique.append(clean)
    return "\n".join(unique)


def base_name(filename):
    """Return filename without .pdf/.PDF extension."""
    if filename.lower().endswith(".pdf"):
        return filename[:-4]
    return filename


def convert_zpl(zpl_code, target="pdf"):
    """Use LabelZoom API to convert ZPL → PDF or PNG."""
    url = f"https://api.labelzoom.net/convert/zpl/to/{target}"

    headers = {
        "Authorization": f"Bearer {st.secrets['LABELZOOM_API_KEY']}",
        "Content-Type": "text/plain"
    }

    params = {"dpi": 203}

    response = requests.post(
        url,
        headers=headers,
        params={"params": json.dumps(params)},
        data=zpl_code
    )

    if response.status_code == 200:
        return response.content
    else:
        st.error(f"LabelZoom Error ({target.upper()}): {response.text}")
        return None


def process_pdf(uploaded_file):
    """Extract text, dedupe, send to ChatGPT, return structured data."""
    with pdfplumber.open(uploaded_file) as pdf:
        text = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    cleaned = dedupe_text(text)

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": cleaned}
        ]
    )

    result_json = json.loads(response.choices[0].message.content)
    return cleaned, result_json


# ---------------------------------
# FILE UPLOAD
# ---------------------------------

uploaded_pdfs = st.file_uploader(
    "Upload PDFs",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_pdfs:

    for pdf_file in uploaded_pdfs:

        st.markdown("---")
        st.subheader(f"Processing: **{pdf_file.name}**")

        with st.spinner("Generating label…"):
            extracted_text, data = process_pdf(pdf_file)

        zpl_code = data["zpl"]
        name_base = base_name(pdf_file.name)

        # ---------------------------------
        # ALWAYS SHOW DOWNLOAD BUTTONS FIRST
        # ---------------------------------
        st.markdown("### Download Files")

        # ZPL
        st.download_button(
            label=f"⬇️ Download ZPL",
            data=zpl_code,
            file_name=f"{name_base}.zpl",
            mime="text/plain"
        )

        # PDF preview (LabelZoom)
        pdf_preview = convert_zpl(zpl_code, target="pdf")
        if pdf_preview:
            st.download_button(
                label=f"⬇️ Download PDF Preview",
                data=pdf_preview,
                file_name=f"{name_base}_preview.pdf",
                mime="application/pdf"
            )

        # PNG preview (LabelZoom)
        png_preview = convert_zpl(zpl_code, target="png")
        if png_preview:
            st.download_button(
                label=f"⬇️ Download PNG Preview",
                data=png_preview,
                file_name=f"{name_base}_preview.png",
                mime="image/png"
            )

        # ---------------------------------
        # COLLAPSIBLE FIELDS (HIDDEN BY DEFAULT)
        # ---------------------------------

        with st.expander("Extracted Fields (click to expand)", expanded=False):
            st.json(data)

        with st.expander("Cleaned Extracted Text (click to expand)", expanded=False):
            st.code(extracted_text)

        with st.expander("ZPL Output (click to expand)", expanded=False):
            st.code(zpl_code, language="plaintext")

        # ---------------------------------
        # PREVIEWS (PDF + PNG)
        # ---------------------------------

        if pdf_preview:
            st.markdown("### PDF Preview")
            st.pdf(pdf_preview)

        if png_preview:
            st.markdown("### PNG Preview")
            st.image(png_preview)


# ---------------------------------
# FOOTER
# ---------------------------------
st.markdown("---")
st.caption("Automated Hangtag System — BAYONA SPA")
