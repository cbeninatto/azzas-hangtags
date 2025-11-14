import streamlit as st
import pdfplumber
import json
from openai import OpenAI

import streamlit as st
from openai import OpenAI

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

SYSTEM_PROMPT = open("system_prompt.txt").read()  # saves the agent prompt in a file

st.title("Chile Hangtag Generator")

uploaded_pdf = st.file_uploader("Upload PDF", type=["pdf"])

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        pdf_text = ""
        for page in pdf.pages:
            pdf_text += page.extract_text() + "\n"

    st.subheader("Extracted Text")
    st.code(pdf_text, language="plaintext")

    if st.button("Generate ZPL"):
        with st.spinner("Generating..."):

            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": pdf_text}
                ]
            )

            json_output = json.loads(response.choices[0].message.content)

        st.success("ZPL Generated!")

        st.subheader("Extracted Fields")
        st.json(json_output)

        zpl_code = json_output["zpl"]

        st.subheader("ZPL Output")
        st.code(zpl_code, language="plaintext")

        st.download_button(
            label="Download ZPL",
            data=zpl_code,
            file_name="label.zpl",
            mime="text/plain"
        )

        # OPTIONAL PDF GENERATION
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter

        pdf_path = "/tmp/output.pdf"
        c = canvas.Canvas(pdf_path, pagesize=letter)
        c.setFont("Helvetica", 12)
        c.drawString(30, 750, "ZPL Hangtag Preview (raw text):")
        y = 720
        for line in zpl_code.split("\n"):
            c.drawString(30, y, line)
            y -= 15
        c.save()

        with open(pdf_path, "rb") as f:
            st.download_button(
                label="Download PDF (raw ZPL text)",
                data=f,
                file_name="zpl_output.pdf",
                mime="application/pdf"
            )
