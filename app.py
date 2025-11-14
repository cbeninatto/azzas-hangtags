import streamlit as st
import pdfplumber
import json
import time
import base64
import requests
from openai import OpenAI

# ---------------------------------
# STREAMLIT PAGE CONFIG
# ---------------------------------
st.set_page_config(page_title="BAYONA SPA", layout="centered")
st.title("BAYONA SPA")
st.write("Upload PDFs to extract metadata, generate ZPL hangtags, and preview PNG renders via LabelZoom.")

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
    # STEP 1 — Extract PDF text
    progress.progress(10, text="Extracting PDF text...")
    with pdfplumber.open(uploaded_file) as pdf:
        text = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    cleaned = dedupe_text(text)
    time.sleep(0.1)

    # STEP 2 — GPT extraction
    progress.progress(50, text="Processing with GPT...")
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": cleaned}
        ]
    )

    result_json = json.loads(response.choices[0].message.content)

    progress.progress(100, text="Completed!")
    time.sleep(0.3)

    return cleaned, result_json


# ---------------------------------
# LABELZOOM PRIVATE API (PNG ONLY)
# ---------------------------------
def convert_zpl_private(zpl_code):
    """Use LabelZoom PRIVATE API to convert ZPL → PNG."""
    url = "https://prod-api.labelzoom.net/api/v2/convert/zpl/to/png"

    headers = {
        "Authorization": f"Bearer {st.secrets['LABELZOOM_PRIVATE_KEY']}",
        "Content-Type": "text/plain",
        "User-Agent": "BAYONA-SPA-Automation"
    }

    params = {
        "dpi": 203,
        "label": {"width": 4, "height": 6}
    }

    response = requests.post(
        url,
        headers=headers,
        params={"params": json.dumps(params)},
        data=zpl_code
    )

    if response.status_code == 200:
        return response.content
    else:
        st.error(f"LabelZoom Error (PNG): {response.text}")
        return None


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

        progress = st.progress(0, text="Starting...")
        extracted_text, data = process_pdf(pdf_file, progress)

        zpl_code = data["zpl"]
        name_base = base_name(pdf_file.name)

        # ---------------------------------
        # FILE HEADER (NO BUTTONS)
        # ---------------------------------
        st.markdown(f"### 📄 {pdf_file.name}")

        # ---------------------------------
        # ZPL OUTPUT FIRST (per request)
        # ---------------------------------
        with st.expander("ZPL Output (first and most important)", expanded=False):
            st.code(zpl_code, language="plaintext")

        # ---------------------------------
        # PNG PREVIEW (LabelZoom Rendering)
        # ---------------------------------
        with st.expander("Label Preview (PNG)", expanded=False):
            st.write("Rendering PNG preview via LabelZoom...")
            png_render = convert_zpl_private(zpl_code)
            if png_render:
                st.image(png_render, caption="PNG Preview")
                st.download_button(
                    "⬇️ Download PNG",
                    data=png_render,
                    file_name=f"{name_base}.png",
                    mime="image/png",
                    key=f"download_png_{pdf_file.name}"
                )

        # ---------------------------------
        # Extracted Fields + Extracted Text
        # ---------------------------------
        with st.expander("Extracted Fields"):
            st.json(data)

        with st.expander("Extracted Text"):
            st.code(extracted_text)


# ---------------------------------
# FOOTER
# ---------------------------------
st.markdown("---")
st.caption("Automated Hangtag System — BAYONA SPA")
