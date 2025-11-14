import streamlit as st
import pdfplumber
import json
from openai import OpenAI
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import os

# -----------------------------------------------------
# Load OpenAI client using Streamlit Cloud secret
# -----------------------------------------------------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# -----------------------------------------------------
# Load system prompt (Chile Hangtag Template Agent)
# -----------------------------------------------------
SYSTEM_PROMPT = open("system_prompt.txt").read()


# -----------------------------------------------------
# SMART DEDUPLICATION FUNCTION
# Removes repeated lines but keeps original order
# -----------------------------------------------------
def dedupe_text(raw_text):
    seen = set()
    unique_lines = []
    for line in raw_text.split("\n"):
        clean = line.strip()
        if clean and clean not in seen:
            seen.add(clean)
            unique_lines.append(clean)
    return "\n".join(unique_lines)


# -----------------------------------------------------
# Streamlit UI
# -----------------------------------------------------
st.title("🇨🇱 Chile Hangtag Generator")
st.write("Upload a PDF and automatically generate a ZPL hangtag label.")

uploaded_pdf = st.file_uploader("Upload PDF", type=["pdf"])

if uploaded_pdf:

    # -------------------------------------------------
    # Extract text from PDF
    # -------------------------------------------------
    with pdfplumber.open(uploaded_pdf) as pdf:
        pdf_text = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                pdf_text += page_text + "\n"

    # Apply deduplication BEFORE sending to ChatGPT
    cleaned_text = dedupe_text(pdf_text)

    st.subheader("Extracted Text (Cleaned)")
    st.code(cleaned_text, language="plaintext")

    # -------------------------------------------------
    # Generate ZPL using ChatGPT
    # -------------------------------------------------
    if st.button("Generate ZPL Label"):

        with st.spinner("Generating label..."):

            try:
                response = client.chat.completions.create(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": cleaned_text}
                    ]
                )

                output_json = response.choices[0].message.content
                data = json.loads(output_json)

            except Exception as e:
                st.error(f"OpenAI Error: {str(e)}")
                st.stop()

        st.success("ZPL generated successfully!")

        # -------------------------------------------------
        # Display extracted fields
        # -------------------------------------------------
        st.subheader("Extracted Fields")
        st.json(data)

        # -------------------------------------------------
        # Display ZPL Code
        # -------------------------------------------------
        zpl_code = data["zpl"]

        st.subheader("ZPL Output")
        st.code(zpl_code, language="plaintext")

        # -------------------------------------------------
        # Provide ZPL file download
        # -------------------------------------------------
        st.download_button(
            label="⬇️ Download ZPL File",
            data=zpl_code,
            file_name="hangtag.zpl",
            mime="text/plain"
        )

        # -------------------------------------------------
        # Create a preview PDF (raw ZPL text only)
        # -------------------------------------------------
        pdf_output_path = "/tmp/zpl_output.pdf"
        c = canvas.Canvas(pdf_output_path, pagesize=letter)
        c.setFont("Helvetica", 12)
        c.drawString(30, 750, "ZPL Output (Raw Preview):")

        y = 720
        for line in zpl_code.split("\n"):
            c.drawString(30, y, line)
            y -= 15
            if y < 40:  # New page if needed
                c.showPage()
                c.setFont("Helvetica", 12)
                y = 750

        c.save()

        with open(pdf_output_path, "rb") as f:
            st.download_button(
                label="⬇️ Download PDF Preview",
                data=f,
                file_name="hangtag_preview.pdf",
                mime="application/pdf"
            )

        st.info("PDF preview is ONLY the ZPL text, not a visual render.")


# -----------------------------------------------------
# Footer
# -----------------------------------------------------
st.markdown("---")
st.caption("Developed by Cesar Beninatto — Automated Chile Hangtag Generator")
