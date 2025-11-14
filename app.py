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
    """Use LabelZoom v2 API to convert ZPL → PDF or PNG."""
    url = f"https://api.labelzoom.net/api/v2/convert/zpl/to/{target}"

    headers = {
        "Authorization": f"Bearer {st.secrets['LABELZOOM_API_KEY']}",
        "Content-Type": "text/plain",
        "User-Agent": "Mozilla/5.0"  # Prevent Cloudflare WAF blocking
    }

    params = {
        "dpi": 203,
        "pdf": {"conversionMode": "IMAGE"},
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
# CLIPBOARD HELPER
# ---------------------------------

def copy_to_clipboard(text):
    st.session_state["clipboard"] = text
    st.toast("ZPL copied to clipboard!")


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

            # Extract data first
            extracted_text, data = process_pdf(pdf_file)
            zpl_code = data["zpl"]
            name_base = base_name(pdf_file.name)

            # ------------------------------
            # TOP ROW: File name + buttons
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

            # COPY ZPL BUTTON
            cols[2].button(
                "📋 Copy",
                on_click=copy_to_clipboard,
                args=(zpl_code,),
                key=f"copy_zpl_{pdf_file.name}"
            )

            # Invisible input to support clipboard storage
            st.text_input(
                "clipboard",
                st.session_state.get("clipboard", ""),
                type="password",
                label_visibility="collapsed",
                key=f"clipboard_field_{pdf_file.name}"
            )

            # ------------------------------
            # PREVIEWS SECTION
            # ------------------------------
            st.markdown("### Preview")

            # PDF preview via LabelZoom
            pdf_preview = convert_zpl(zpl_code, target="pdf")
            if pdf_preview:
                st.pdf(pdf_preview)

            # PNG preview via LabelZoom
            png_preview = convert_zpl(zpl_code, target="png")
            if png_preview:
                st.image(png_preview)

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
