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

# Load prompt
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

def process_pdf(uploaded_file):
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
# COPY BUTTON (JS)
# ---------------------------------
def copy_button(label, text, key):
    safe_text = text.replace("`", "'")  # avoid breaking JS template literal
    button_html = f"""
        <script>
        function copyToClipboard_{key}() {{
            navigator.clipboard.writeText(`{safe_text}`);
        }}
        </script>
        <button onclick="copyToClipboard_{key}()" style="
            border-radius: 5px;
            padding: 6px 14px;
            background-color: #eee;
            border: 1px solid #ccc;
            cursor: pointer;
            font-size: 14px;
        ">{label}</button>
    """
    st.markdown(button_html, unsafe_allow_html=True)

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

        container = st.container()
        with container:

            st.markdown("---")

            extracted_text, data = process_pdf(pdf_file)
            zpl_code = data["zpl"]
            name_base = base_name(pdf_file.name)

            # TOP ROW
            cols = st.columns([4, 1, 1])
            cols[0].markdown(f"### 📄 {pdf_file.name}")

            # ZPL DOWNLOAD
            cols[1].download_button(
                label="⬇️ ZPL",
                data=zpl_code,
                file_name=f"{name_base}.zpl",
                mime="text/plain",
                key=f"dl_{pdf_file.name}"
            )

            # COPY BUTTON (JS)
            with cols[2]:
                copy_button("📋 Copy", zpl_code, f"copy_{pdf_file.name}")

            # COLLAPSIBLE SECTIONS
            with st.expander("Extracted Fields"):
                st.json(data)

            with st.expander("Extracted Text"):
                st.code(extracted_text)

            with st.expander("ZPL Output"):
                st.code(zpl_code, language="plaintext")

# FOOTER
st.markdown("---")
st.caption("Automated Hangtag System — BAYONA SPA")
