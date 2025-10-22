import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO
from datetime import datetime

st.set_page_config(page_title="Invoice Extractor — Mace (Sciex)", layout="wide", page_icon="📄")

# --------------------- Helper Functions ---------------------
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


def extract_mace_multi(text):
    """
    Extract multiple invoices from a Mace PDF.
    Each invoice typically contains:
    - P.O. NO.
    - Sciex PO
    - Date
    - TOTAL USD
    """
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


# --------------------- Sidebar ---------------------
st.sidebar.header("Controls")
st.sidebar.markdown("Upload one or more Mace invoice PDFs and extract all invoices automatically.")

uploaded_files = st.sidebar.file_uploader("Upload Mace PDF files", type=["pdf"], accept_multiple_files=True)
ex_rate = st.sidebar.number_input("Enter Exchange Rate (EX-RATE)", min_value=0.0, step=0.01, format="%.4f", value=0.0)
normalize_names = st.sidebar.checkbox("Normalize column names (lowercase + underscores)", value=False)
show_logs = st.sidebar.checkbox("Show extraction logs", value=True)

st.sidebar.markdown("---")
st.sidebar.markdown("Made for **Sciex** — Mace multi-invoice extractor.")


# --------------------- Main Layout ---------------------
st.title("📄 Invoice Extractor — Mace (Sciex)")
st.write("Upload PDFs in the sidebar, enter a valid **EX-RATE**, and click **Process** to extract all invoices.")

if uploaded_files:
    st.write("### Uploaded files")
    cols = st.columns(3)
    for i, f in enumerate(uploaded_files):
        col = cols[i % 3]
        with col:
            st.markdown(f"**📕 {f.name}**")
            st.caption(f"Size: {len(f.getvalue())/1024:.1f} KB")
else:
    st.info("No PDF files uploaded yet. Use the sidebar to upload one or more Mace invoice PDFs.")

process_btn = st.button("Process Files", type="primary")

status_area = st.empty()
result_area = st.container()

if process_btn:
    if not uploaded_files:
        st.warning("Please upload one or more PDF files before processing.")
    elif ex_rate <= 0:
        st.error("❌ Please enter a valid EX-RATE (must be greater than 0) before processing.")
    else:
        status_area.info("Starting extraction...")
        total_files = len(uploaded_files)
        progress = st.progress(0)
        results = []
        logs = []

        for idx, uploaded_file in enumerate(uploaded_files, start=1):
            file_name = uploaded_file.name
            try:
                text = extract_text_from_pdf_bytes(uploaded_file.getvalue())
                extracted = extract_mace_multi(text)

                if not extracted:
                    logs.append(f"⚠️ {file_name}: No matches found.")
                else:
                    for row in extracted:
                        row["source_file"] = file_name
                        results.append(row)
                    logs.append(f"✅ {file_name}: {len(extracted)} invoices extracted.")

            except Exception as e:
                logs.append(f"❌ {file_name}: error - {e}")
            progress.progress(int((idx / total_files) * 100))

        status_area.success("Extraction complete.")

        if show_logs:
            st.subheader("Logs")
            for l in logs:
                st.write(l)

        if results:
            df = pd.DataFrame(results)

            # Clean numeric column
            df["Total Invoice Value(USD)"] = (
                df["Total Invoice Value(USD)"]
                .astype(str)
                .str.replace(",", "", regex=False)
                .astype(float)
            )

            # Add EX-RATE and compute SGD
            df["EX-RATE"] = ex_rate
            df["Total Invoice Value(SGD)"] = df["Total Invoice Value(USD)"] * ex_rate

            # Format values for display
            df["Total Invoice Value(USD)"] = df["Total Invoice Value(USD)"].map(lambda x: f"{x:,.2f}")
            df["Total Invoice Value(SGD)"] = df["Total Invoice Value(SGD)"].map(lambda x: f"{x:,.2f}")

            if normalize_names:
                df.columns = [c.strip().lower().replace(" ", "_").replace(".", "") for c in df.columns]

            with result_area:
                st.subheader("Extracted Invoice Data")
                st.dataframe(df, use_container_width=True)

                # Prepare files for download
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
                        file_name=f"mace_extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
                with col2:
                    st.download_button(
                        "📄 Download CSV",
                        data=csv_buffer.getvalue(),
                        file_name=f"mace_extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime='text/csv'
                    )

        else:
            st.info("No invoice data found in the uploaded files.")
