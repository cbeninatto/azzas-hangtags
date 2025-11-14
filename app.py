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


def convert_zpl(zpl_code, filetype="pdf"):
    """Use LabelZoom API to convert ZPL → PDF or PNG."""
    url = f"https://api.labelzoom.net/api/convert/zpl/{filetype}"

    headers = {
        "Authorization": f"Bearer {st.secrets['LABELZOOM_API_KEY']}",
        "Content-Type": "application/json"
    }

    payload = {
        "zpl": zpl_code,
        "dpi": 203
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        return response.content
    else:
        st.error(f"LabelZoom Error ({filetype.upper()}): {response.text}")
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

        with st.spinner("Extracting and generating label…"):
            extracted_text, data = process_pdf(pdf_file)

        zpl_code = data["zpl"]
        name_base = base_name(pdf_file.name)

        # ---------------------------------
        # DISPLAY DATA
        # ---------------------------------

        st.markdown("### Extracted Fields")
        st.json(data)

        with st.expander("Show cleaned extracted PDF text"):
            st.code(extracted_text)

        st.markdown("### ZPL Output")
        st.code(zpl_code, language="plaintext")

        # ---------------------------------
        # DOWNLOAD RAW ZPL
        # ---------------------------------
        st.download_button(
            label=f"⬇️ Download ZPL ({pdf_file.name})",
            data=zpl_code,
            file_name=f"{name_base}.zpl",
            mime="text/plain"
        )

        # ---------------------------------
        # LABELZOOM PDF RENDER
        # ---------------------------------
        pdf_preview = convert_zpl(zpl_code, filetype="pdf")
        if pdf_preview:
            st.markdown("### LabelZoom PDF Preview")
            st.pdf(pdf_preview)
            st.download_button(
                label=f"⬇️ Download PDF Preview ({pdf_file.name})",
                data=pdf_preview,
                file_name=f"{name_base}_preview.pdf",
                mime="application/pdf"
            )

        # ---------------------------------
        # LABELZOOM PNG RENDER
        # ---------------------------------
        png_preview = convert_zpl(zpl_code, filetype="png")
        if png_preview:
            st.markdown("### LabelZoom PNG Preview")
            st.image(png_preview)

            st.download_button(
                label=f"⬇️ Download PNG Preview ({pdf_file.name})",
                data=png_preview,
                file_name=f"{name_base}_preview.png",
                mime="image/png"
            )

# ---------------------------------
# FOOTER
# ---------------------------------
st.markdown("---")
st.caption("Automated Hangtag System — BAYONA SPA")
