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
st.write("Upload one or multiple PDFs to generate ZPL hangtags automatically.")

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

        file_container = st.container()

        with file_container:
            st.markdown("---")

            # Extract fields
            extracted_text, data = process_pdf(pdf_file)
            zpl_code = data["zpl"]
            name_base = base_name(pdf_file.name)

            # ------------------------------
            # TOP ROW: FILENAME + BUTTONS
            # ------------------------------
            cols = st.columns([4, 1, 1])
            cols[0].markdown(f"### 📄 {pdf_file.name}")

            # DOWNLOAD ZPL BUTTON
            cols[1].download_button(
                label="⬇️ ZPL",
                data=zpl_code,
                file_name=f"{name_base}.zpl",
                mime="text/plain",
                key=f"download_zpl_{pdf_file.name}"
            )

            # COPY ZPL BUTTON (new, clean version)
            cols[2].button(
                "📋 Copy",
                on_click=lambda z=zpl_code: st.clipboard(z),
                key=f"copy_zpl_{pdf_file.name}"
            )

            # ------------------------------
            # COLLAPSIBLE RAW DATA
            # ------------------------------

            with st.expander("Extracted Fields (click to expand)"):
                st.json(data)

            with st.expander("Extracted Text (click to expand)"):
                st.code(extracted_text)

            with st.expander("ZPL Output (click to expand)"):
                st.code(zpl_code, language="plaintext")


# ---------------------------------
# FOOTER
# ---------------------------------
st.markdown("---")
st.caption("Automated Hangtag System — BAYONA SPA")
