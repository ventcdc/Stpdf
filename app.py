import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO
from datetime import datetime

st.set_page_config(page_title="Invoice Extractor — Sciex", layout="wide", page_icon="📄")

# --------------------- PDF TEXT EXTRACTION ---------------------
def extract_text_from_pdf_bytes(file_bytes):
    """Extract all text from uploaded PDF file."""
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


# --------------------- CUSTOMER EXTRACTION FUNCTIONS ---------------------
def extract_mace_multi(text):
    """Extract multiple invoices from Mace PDF."""
    pattern = re.compile(
        r"P\.O\. NO\.\s*(\d+).*?"          # P.O. NO.
        r"(\d{2}\s[A-Za-z]+\s\d{4}).*?"    # Date
        r"DDU Singapore\s+(\d+).*?"        # Sciex PO
        r"TOTAL USD\s*:\s*([\d,\.]+)",     # Total USD
        re.DOTALL
    )

    matches = pattern.findall(text)
    data = []
    for m in matches:
        po_no, date, sciex_po, total_usd = m
        data.append({
            "Invoice Date": date.strip(),
            "P.O. NO.": po_no.strip(),
            "Sciex PO": sciex_po.strip(),
            "Total Invoice Value(USD)": total_usd.strip()
        })
    return data


def extract_novanta(text):
    """Extract single invoice from Novanta PDF."""
    invoice_date_pattern = re.compile(r"Date:\s*(\d{2}\/\d{2}\/\d{4})", re.IGNORECASE)
    invoice_no_pattern = re.compile(r"Invoice ID:\s*(\d+)", re.IGNORECASE)
    po_no_pattern = re.compile(r"ABSCIEX-S\s*(\d+)", re.IGNORECASE)
    amount_pattern = re.compile(r"TOTAL AMOUNT DUE:\s*\$?([\d,\.]+)", re.IGNORECASE)

    return [{
        "Invoice Date": invoice_date_pattern.search(text).group(1) if invoice_date_pattern.search(text) else None,
        "Invoice NO": invoice_no_pattern.search(text).group(1) if invoice_no_pattern.search(text) else None,
        "Sciex PO": po_no_pattern.search(text).group(1) if po_no_pattern.search(text) else None,
        "Total Invoice Value(USD)": amount_pattern.search(text).group(1) if amount_pattern.search(text) else None
    }]


def extract_cronologic(text):
    """Extract single invoice from Cronologic PDF."""
    date_pattern = re.compile(r"Date\s*[:\-]?\s*(\d{4}\-\d{2}\-\d{2})", re.IGNORECASE)
    invoice_no_pattern = re.compile(r"Invoice No\.?\s*[:\-]?\s*(\d+)", re.IGNORECASE)
    po_no_pattern = re.compile(r"PO-?(\d+)", re.IGNORECASE)
    amount_pattern = re.compile(r"Amount for Payment\s*[:\-]?\s*\$?([\d,\.]+)", re.IGNORECASE)

    return [{
        "Invoice Date": date_pattern.search(text).group(1) if date_pattern.search(text) else None,
        "Invoice NO": invoice_no_pattern.search(text).group(1) if invoice_no_pattern.search(text) else None,
        "Sciex PO": po_no_pattern.search(text).group(1) if po_no_pattern.search(text) else None,
        "Total Invoice Value(USD)": amount_pattern.search(text).group(1) if amount_pattern.search(text) else None
    }]


EXTRACTORS = {
    "Mace": extract_mace_multi,
    "Novanta": extract_novanta,
    "Cronologic": extract_cronologic
}

# --------------------- SIDEBAR ---------------------
st.sidebar.header("Controls")
st.sidebar.markdown("Upload invoice PDFs and select the customer type to extract data automatically.")

customer_type = st.sidebar.selectbox("Customer Type", ["Mace", "Novanta", "Cronologic"])
uploaded_files = st.sidebar.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True)
ex_rate = st.sidebar.number_input("Enter Exchange Rate (EX-RATE)", min_value=0.0, step=0.01, format="%.4f", value=0.0)
normalize_names = st.sidebar.checkbox("Normalize column names (lowercase + underscores)", value=False)
show_logs = st.sidebar.checkbox("Show extraction logs", value=True)

st.sidebar.markdown("---")
st.sidebar.markdown("Made for **Sciex** — Multi-customer invoice extractor.")


# --------------------- MAIN LAYOUT ---------------------
st.title("📄 Invoice Extractor — Sciex")
st.write("Upload PDFs, choose **customer type**, and enter a valid **EX-RATE** before processing.")

if uploaded_files:
    st.write("### Uploaded files")
    cols = st.columns(3)
    for i, f in enumerate(uploaded_files):
        col = cols[i % 3]
        with col:
            st.markdown(f"**📕 {f.name}**")
            st.caption(f"Size: {len(f.getvalue())/1024:.1f} KB")
else:
    st.info("No PDF files uploaded yet. Use the sidebar to upload.")

process_btn = st.button("Process Files", type="primary")

status_area = st.empty()
result_area = st.container()

# --------------------- MAIN PROCESSING ---------------------
if process_btn:
    if not uploaded_files:
        st.warning("Please upload one or more PDF files before processing.")
    elif ex_rate <= 0:
        st.error("❌ Please enter a valid EX-RATE (must be greater than 0) before processing.")
    else:
        status_area.info(f"Extracting data for **{customer_type}** invoices...")
        total_files = len(uploaded_files)
        progress = st.progress(0)
        results = []
        logs = []
        extractor = EXTRACTORS.get(customer_type)

        for idx, uploaded_file in enumerate(uploaded_files, start=1):
            file_name = uploaded_file.name
            try:
                text = extract_text_from_pdf_bytes(uploaded_file.getvalue())
                extracted_rows = extractor(text)
                if not extracted_rows:
                    logs.append(f"⚠️ {file_name}: No data found.")
                else:
                    results.extend(extracted_rows)
                    logs.append(f"✅ {file_name}: {len(extracted_rows)} records extracted.")
            except Exception as e:
                logs.append(f"❌ {file_name}: error - {e}")
            progress.progress(int((idx / total_files) * 100))

        status_area.success("✅ Extraction complete.")

        if show_logs:
            st.subheader("Logs")
            for log in logs:
                st.write(log)

        if results:
            df = pd.DataFrame(results)

            # Clean numeric column
            usd_cols = [col for col in df.columns if "usd" in col.lower()]
            if usd_cols:
                usd_col = usd_cols[0]
                df[usd_col] = (
                    df[usd_col]
                    .astype(str)
                    .str.replace(",", "", regex=False)
                    .astype(float, errors="ignore")
                )

                # Add EX-RATE and SGD calculation
                df["EX-RATE"] = ex_rate
                df["Total Invoice Value(SGD)"] = df[usd_col] * ex_rate

                # Format display
                df[usd_col] = df[usd_col].map(lambda x: f"{x:,.2f}" if pd.notnull(x) else "")
                df["Total Invoice Value(SGD)"] = df["Total Invoice Value(SGD)"].map(lambda x: f"{x:,.2f}" if pd.notnull(x) else "")

            if normalize_names:
                df.columns = [c.strip().lower().replace(" ", "_").replace(".", "").replace(":", "") for c in df.columns]

            with result_area:
                st.subheader(f"Extracted Data — {customer_type}")
                st.dataframe(df, use_container_width=True)

                # Prepare export (keep numeric values)
                df_export = df.copy()
                for col in ["Total Invoice Value(USD)", "Total Invoice Value(SGD)"]:
                    if col in df_export.columns:
                        df_export[col] = (
                            df_export[col]
                            .astype(str)
                            .str.replace(",", "", regex=False)
                            .astype(float, errors="ignore")
                        )

                excel_buffer = BytesIO()
                with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                    df_export.to_excel(writer, index=False, sheet_name="extracted")
                excel_buffer.seek(0)

                csv_buffer = BytesIO()
                csv_buffer.write(df_export.to_csv(index=False).encode("utf-8"))
                csv_buffer.seek(0)

                col1, col2 = st.columns([1, 1])
                with col1:
                    st.download_button(
                        "📥 Download Excel",
                        data=excel_buffer.getvalue(),
                        file_name=f"{customer_type.lower()}_extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
                with col2:
                    st.download_button(
                        "📄 Download CSV",
                        data=csv_buffer.getvalue(),
                        file_name=f"{customer_type.lower()}_extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime='text/csv'
                    )
        else:
            st.info("No invoice data extracted from the uploaded files.")
