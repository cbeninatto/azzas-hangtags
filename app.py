import streamlit as st
import pdfplumber
import json
import time
from openai import OpenAI

# ---------------------------------
# STREAMLIT PAGE CONFIG
# ---------------------------------
st.set_page_config(page_title="BAYONA SPA", layout="centered")
st.title("BAYONA SPA")
st.write("Upload one or multiple PDFs to extract metadata and generate ZPL hangtags automatically.")

# ---------------------------------
# INIT OPENAI
# ---------------------------------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
SYSTEM_PROMPT = open("system_prompt.txt").read()

# ---------------------------------
# HELPERS
# ---------------------------------

def dedupe_text(raw_text):
    seen = set()
    unique = []
    for line in raw_text.split("\n"):
        clean = line.strip()
        if clean and clean not in seen:
            seen.add(clean)
            unique.append(clean)
    return "\n".join(unique)

def base_name(filename):
    if filename.lower().endswith(".pdf"):
        return filename[:-4]
    return filename

def process_pdf(uploaded_file, progress):
    progress.progress(10, text="Extracting PDF text...")
    with pdfplumber.open(uploaded_file) as pdf:
        text = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    cleaned = dedupe_text(text)
    time.sleep(0.1)

    progress.progress(50, text="Processing with GPT...")
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",  "content": cleaned}
        ]
    )

    result_json = json.loads(response.choices[0].message.content)

    progress.progress(100, text="Completed!")
    time.sleep(0.3)

    return cleaned, result_json

# ---------------------------------
# COPY BUTTON (JS)
# ---------------------------------
import streamlit.components.v1 as components

def copy_button_inline(label, text, key):
    safe_text = text.replace("`", "\\`")  # protect backticks
    html = f"""
        <button onclick="navigator.clipboard.writeText(`{safe_text}`)"
            style="
                border-radius: 6px;
                padding: 6px 14px;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                cursor: pointer;
                font-size: 14px;
                margin-top: 28px;
            ">
            {label}
        </button>
    """
    components.html(html, height=40)

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

        # Progress bar for this file
        progress = st.progress(0, text="Starting...")

        extracted_text, data = process_pdf(pdf_file, progress)
        zpl_code = data["zpl"]
        name_base = base_name(pdf_file.name)

        # ---------------------------------
        # FILE HEADER + BUTTONS (ALL IN ONE ROW)
        # ---------------------------------
        cols = st.columns([4, 1, 1])
        cols[0].markdown(f"### 📄 {pdf_file.name}")

        # DOWNLOAD ZPL BUTTON
        cols[1].download_button(
            label="⬇️ ZPL",
            data=zpl_code,
            file_name=f"{name_base}.zpl",
            mime="text/plain",
            key=f"dl_zpl_{pdf_file.name}"
        )

        # COPY ZPL BUTTON — NOW NEXT TO FILENAME
        with cols[2]:
            copy_button_inline("📋 Copy", zpl_code, key=f"copy_{pdf_file.name}")

        # ---------------------------------
        # COLLAPSIBLE SECTIONS
        # ---------------------------------

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
