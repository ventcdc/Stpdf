import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO
from datetime import datetime
import os

st.set_page_config(page_title="Invoice Extractor — Sciex", layout="wide", page_icon="📄")

# --------------------- Helper functions (based on uploaded backend) ---------------------
def extract_text_from_pdf_bytes(file_bytes):
    text = ""
    try:
       
         with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                text += page_text + "\n"
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
    return text

# Extraction patterns per customer
def extract_novanta(text):
    invoice_date_pattern = re.compile(r"Date:\s*(\d{2}\/\d{2}\/\d{4})", re.IGNORECASE)
    invoice_no_pattern = re.compile(r"Invoice ID:\s*(\d+)", re.IGNORECASE)
    po_no_pattern = re.compile(r"ABSCIEX-S\s*(\d+)", re.IGNORECASE)
    amount_pattern = re.compile(r"TOTAL AMOUNT DUE:\s*\$?([\d,\.]+)", re.IGNORECASE)
    return {
        "Invoice Date": invoice_date_pattern.search(text).group(1) if invoice_date_pattern.search(text) else None,
        "Invoice NO": invoice_no_pattern.search(text).group(1) if invoice_no_pattern.search(text) else None,
        "Sciex PO": po_no_pattern.search(text).group(1) if po_no_pattern.search(text) else None,
        "Total Invoice Value(USD)": amount_pattern.search(text).group(1) if amount_pattern.search(text) else None
    }

def extract_cronologic(text):
    date_pattern = re.compile(r"Date\s*[:\-]?\s*(\d{4}\-\d{2}\-\d{2})", re.IGNORECASE)
    invoice_no_pattern = re.compile(r"Invoice No\.?\s*[:\-]?\s*(\d+)", re.IGNORECASE)
    po_no_pattern = re.compile(r"PO-?(\d+)", re.IGNORECASE)
    amount_pattern = re.compile(r"Amount for Payment\s*[:\-]?\s*\$?([\d,\.]+)", re.IGNORECASE)
    return {
        "Date": date_pattern.search(text).group(1) if date_pattern.search(text) else None,
        "Invoice No": invoice_no_pattern.search(text).group(1) if invoice_no_pattern.search(text) else None,
        "PO No": po_no_pattern.search(text).group(1) if po_no_pattern.search(text) else None,
        "Amount": amount_pattern.search(text).group(1) if amount_pattern.search(text) else None
    }

def extract_mace(text):
    date_pattern = re.compile(r"DATE\s*(\d{2}\s[A-Za-z]+\s\d{4})", re.IGNORECASE)
    invoice_no_pattern = re.compile(r"NO\.\s*(\d+)", re.IGNORECASE)
    po_no_pattern = re.compile(r"P\.O\. NO\.\s*(\d+)", re.IGNORECASE)
    amount_pattern = re.compile(r"TOTAL USD\s*:\s*\$?([\d,\.]+)", re.IGNORECASE)
    return {
        "DATE": date_pattern.search(text).group(1) if date_pattern.search(text) else None,
        "NO.": invoice_no_pattern.search(text).group(1) if invoice_no_pattern.search(text) else None,
        "P.O. NO.": po_no_pattern.search(text).group(1) if po_no_pattern.search(text) else None,
        "TOTAL USD": amount_pattern.search(text).group(1) if amount_pattern.search(text) else None
    }

EXTRACTORS = {
    "Novanta": extract_novanta,
    "Cronologic": extract_cronologic,
    "Mace": extract_mace
}

# --------------------- Sidebar ---------------------
st.sidebar.header("Controls")
st.sidebar.markdown("Choose customer type, upload PDFs, and process to get an Excel file.")

customer_type = st.sidebar.selectbox("Customer type", ["Novanta", "Cronologic", "Mace"])
uploaded_files = st.sidebar.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True)
normalize_names = st.sidebar.checkbox("Normalize column names to lowercase and underscores", value=False)
show_logs = st.sidebar.checkbox("Show extraction logs", value=True)

st.sidebar.markdown("---")
st.sidebar.markdown("Made for Sciex invoice extraction. Deploy on Streamlit Cloud.")

# --------------------- Main layout ---------------------
st.title("📄 Invoice Extractor — Sciex")
st.write("Upload PDFs in the sidebar. Choose the correct customer type and click **Process** below.")

# Preview uploaded files with icons
if uploaded_files:
    st.write("### Uploaded files")
    cols = st.columns(3)
    for i, f in enumerate(uploaded_files):
        col = cols[i % 3]
        with col:
            st.markdown(f"**📕 {f.name}**")
            st.caption(f"Size: {len(f.getvalue())/1024:.1f} KB")
else:
    st.info("No PDF files uploaded yet. Use the sidebar to upload files.")

process_btn = st.button("Process Files", type="primary")

# Container for status and results
status_area = st.empty()
result_area = st.container()

if process_btn:
    if not uploaded_files:
        st.warning("Please upload one or more PDF files in the sidebar before processing.")
    else:
        status_area.info("Starting processing...")
        total = len(uploaded_files)
        progress = st.progress(0)
        results = []
        logs = []
        extractor = EXTRACTORS.get(customer_type)

        for idx, uploaded_file in enumerate(uploaded_files, start=1):
            status_area.info(f"Processing {idx}/{total}: {uploaded_file.name}")
            try:
                file_bytes = uploaded_file.getvalue()
                text = extract_text_from_pdf_bytes(file_bytes)
                row = extractor(text)
                row["source_file"] = uploaded_file.name
                # capture simple normalization/cleanup
                # convert date formats if possible
                for k,v in row.items():
                    if isinstance(v, str):
                        row[k] = v.strip()
                results.append(row)
                logs.append(f"✅ {uploaded_file.name}: extracted {len([x for x in row.values() if x])} fields")
            except Exception as e:
                logs.append(f"❌ {uploaded_file.name}: error {e}")

            progress.progress(int((idx/total)*100))

        status_area.success("Processing complete.")
        if show_logs:
            st.subheader("Logs")
            for l in logs:
                st.write(l)

        if results:
            df = pd.DataFrame(results)
            if normalize_names:
                df.columns = [c.strip().lower().replace(" ", "_").replace(".", "").replace(":", "") for c in df.columns]

            with result_area:
                st.subheader("Extracted Data Preview")
                st.dataframe(df)

                # Let user download Excel or CSV
                excel_buffer = BytesIO()
                with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="extracted")
                excel_buffer.seek(0)

                csv_buffer = BytesIO()
                csv_buffer.write(df.to_csv(index=False).encode("utf-8"))
                csv_buffer.seek(0)

                col1, col2 = st.columns([1,1])
                with col1:
                    st.download_button("📥 Download Excel", data=excel_buffer.getvalue(),
                                       file_name=f"extracted_invoices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                with col2:
                    st.download_button("📄 Download CSV", data=csv_buffer.getvalue(),
                                       file_name=f"extracted_invoices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                       mime='text/csv')

        else:
            st.info("No fields were extracted from the uploaded files. Try a different customer type or check the PDFs.")
