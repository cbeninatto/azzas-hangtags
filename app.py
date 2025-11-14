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
st.write("Upload one or multiple PDFs to extract metadata, generate ZPL hangtags and render PDF previews using LabelZoom.")

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
            {"role": "user", "content": cleaned}
        ]
    )

    result_json = json.loads(response.choices[0].message.content)

    progress.progress(100, text="Completed!")
    time.sleep(0.3)

    return cleaned, result_json


# ---------------------------------
# LABELZOOM PRIVATE API
# ---------------------------------
def convert_zpl_private(zpl_code, target="pdf"):
    """Use LabelZoom PRIVATE API to convert ZPL → PDF or PNG."""

    url = f"https://prod-api.labelzoom.net/api/v2/convert/zpl/to/{target}"

    headers = {
        "Authorization": f"Bearer {st.secrets['LABELZOOM_PRIVATE_KEY']}",
        "Content-Type": "text/plain",
        "User-Agent": "BAYONA-SPA-Automation"
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


# ---------------------------------
# PDF IFRAME PREVIEW (safe)
# ---------------------------------
def show_pdf_in_iframe(pdf_bytes):
    base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    html = f"""
        <iframe src="data:application/pdf;base64,{base64_pdf}"
        width="100%" height="700" type="application/pdf"></iframe>
    """
    st.markdown(html, unsafe_allow_html=True)


# ---------------------------------
# COPY BUTTON HANDLER
# ---------------------------------
def copy_zpl(zpl_text, key):
    st.session_state[f"copy_buffer_{key}"] = zpl_text
    st.session_state[f"copy_trigger_{key}"] = True


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
        # HEADER ROW (Filename + Buttons)
        # ---------------------------------
        cols = st.columns([4, 1, 1])
        cols[0].markdown(f"### 📄 {pdf_file.name}")

        # Download ZPL
        cols[1].download_button(
            label="⬇️ ZPL",
            data=zpl_code,
            file_name=f"{name_base}.zpl",
            mime="text/plain",
            key=f"download_zpl_{pdf_file.name}"
        )

        # Copy ZPL
        cols[2].button(
            "📋 Copy",
            on_click=copy_zpl,
            args=(zpl_code, pdf_file.name),
            key=f"copy_btn_{pdf_file.name}"
        )

        # Streamlit clipboard handler
        if st.session_state.get(f"copy_trigger_{pdf_file.name}", False):
            st.text_input(
                "hidden_copy_target",
                st.session_state[f"copy_buffer_{pdf_file.name}"],
                key=f"hidden_copy_box_{pdf_file.name}"
            )
            st.success("Copied to clipboard!")
            st.session_state[f"copy_trigger_{pdf_file.name}"] = False

        # ---------------------------------
        # LABELZOOM PDF + PNG RENDERING
        # ---------------------------------

        with st.expander("Label Preview (PDF/PNG)"):
            st.write("Rendering via LabelZoom...")

            # Generate PDF preview
            pdf_render = convert_zpl_private(zpl_code, "pdf")
            if pdf_render:
                st.download_button(
                    "⬇️ Download PDF Preview",
                    data=pdf_render,
                    file_name=f"{name_base}_preview.pdf",
                    mime="application/pdf",
                    key=f"download_pdf_{pdf_file.name}"
                )

                # Show inline preview
                show_pdf_in_iframe(pdf_render)

            # Generate PNG preview
            png_render = convert_zpl_private(zpl_code, "png")
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
        # COLLAPSIBLE EXTRACTION DATA
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
