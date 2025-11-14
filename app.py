import streamlit as st
import pdfplumber
import json
import requests
from openai import OpenAI
from io import BytesIO
import zipfile

# -------------------------------
# INIT
# -------------------------------

st.set_page_config(page_title="BAYONA SPA", layout="centered")

st.title("BAYONA SPA")
st.write("Upload one or multiple PDFs to generate ZPL hangtags with automatic LabelZoom rendering.")

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
SYSTEM_PROMPT = open("system_prompt.txt").read()


# -------------------------------
# SMART DEDUPLICATION
# -------------------------------
def dedupe_text(raw_text):
    seen = set()
    unique_lines = []
    for line in raw_text.split("\n"):
        clean = line.strip()
        if clean and clean not in seen:
            seen.add(clean)
            unique_lines.append(clean)
    return "\n".join(unique_lines)


# -------------------------------
# LABELZOOM – ZPL → PDF, PNG
# -------------------------------
def convert_zpl(zpl_code, filetype="pdf"):
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


# -------------------------------
# PROCESS PDF → JSON + ZPL
# -------------------------------
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


# -------------------------------
# MULTI-PDF UPLOAD
# -------------------------------
uploaded_pdfs = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_pdfs:

    for pdf_file in uploaded_pdfs:

        st.markdown("---")
        st.subheader(f"Processing: **{pdf_file.name}**")

        with st.spinner("Extracting and generating label…"):
            extracted_text, data = process_pdf(pdf_file)

        zpl_code = data["zpl"]

        # SHOW FIELDS
        st.markdown("### Extracted Fields")
        st.json(data)

        # SHOW CLEANED TEXT
        with st.expander("Show cleaned extracted PDF text"):
            st.code(extracted_text)

        # ZPL OUTPUT
        st.markdown("### ZPL Output")
        st.code(zpl_code, language="plaintext")

        # DOWNLOAD ZPL
        st.download_button(
            label=f"⬇️ Download ZPL ({pdf_file.name.replace('.pdf', '')})",
            data=zpl_code,
            file_name=f"{pdf_file.name.replace('.pdf','')}.zpl",
            mime="text/plain"
        )

        # LABELZOOM RENDER – PDF
        pdf_preview = convert_zpl(zpl_code, filetype="pdf")
        if pdf_preview:
            st.markdown("### LabelZoom PDF Preview")
            st.download_button(
                label=f"⬇️ Download PDF Preview ({pdf_file.name.replace('.pdf','')})",
                data=pdf_preview,
                file_name=f"{pdf_file.name.replace('.pdf','')}_preview.pdf",
                mime="application/pdf"
            )
            st.pdf(pdf_preview)

        # LABELZOOM RENDER – PNG
        png_preview = convert_zpl(zpl_code, filetype="png")
        if png_preview:
            st.markdown("### LabelZoom PNG Preview")
            st.image(png_preview)

            st.download_button(
                label=f"⬇️ Download PNG Preview ({pdf_file.name.replace('.pdf','')})",
                data=png_preview,
                file_name=f"{pdf_file.name.replace('.pdf','')}_preview.png",
                mime="image/png"
            )


# FOOTER
st.markdown("---")
st.caption("Automated Hangtag System — BAYONA SPA")
