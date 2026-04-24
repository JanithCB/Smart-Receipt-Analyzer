# app/ui_streamlit.py
import os
import io
import shutil
import pandas as pd
import streamlit as st

from vispend_core.config import UPLOAD_DIR, ANALYTICS_OUTPUT_DIR
from vispend_core.pipeline import process_single_receipt
from vispend_core.analytics_core import load_and_clean_analytics, compute_basic_stats

st.set_page_config(
    page_title="Vispend AI – Receipt Insights",
    layout="wide",
)

st.title("Vispend AI – Receipt Insights (Desktop Demo)")

tab_upload, tab_table, tab_analytics = st.tabs(
    [" Upload & Process", " Receipts Table", " Analytics Dashboard"]
)

with tab_upload:
    st.subheader("Upload new receipts")
    uploaded_files = st.file_uploader(
        "Drop receipt images here",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        rows = []
        for uf in uploaded_files:
            # Save to uploads directory
            save_path = os.path.join(UPLOAD_DIR, uf.name)
            with open(save_path, "wb") as f:
                f.write(uf.read())

            with st.spinner(f"Processing {uf.name}..."):
                result = process_single_receipt(save_path)
                rows.append(result)

            st.success(f"Processed {uf.name}")

        # Append to main CSV
        df_new = pd.DataFrame(rows)
        csv_path = os.path.join(ANALYTICS_OUTPUT_DIR, "ocr_batch_results.csv")
        if os.path.exists(csv_path):
            df_existing = pd.read_csv(csv_path)
            df_all = pd.concat([df_existing, df_new], ignore_index=True)
        else:
            df_all = df_new

        df_all.to_csv(csv_path, index=False)
        st.info("Saved results to ocr_batch_results.csv")

        st.write("Preview of newly processed receipts:")
        st.dataframe(df_new[["file", "merchant", "date", "category", "total_usd"]])

with tab_table:
    st.subheader("All processed receipts")
    csv_path = os.path.join(ANALYTICS_OUTPUT_DIR, "ocr_batch_results.csv")
    if os.path.exists(csv_path):
        df = load_and_clean_analytics(csv_path)
        st.dataframe(
            df[
                [
                    "file",
                    "date",
                    "merchant_clean",
                    "category",
                    "total_usd",
                    "payment_method",
                ]
            ].sort_values("date", ascending=False)
        )
    else:
        st.info("No receipts processed yet. Upload some in the previous tab.")

with tab_analytics:
    st.subheader("Spending analytics")
    csv_path = os.path.join(ANALYTICS_OUTPUT_DIR, "ocr_batch_results.csv")
    if not os.path.exists(csv_path):
        st.info("No data yet.")
    else:
        df = load_and_clean_analytics(csv_path)
        stats = compute_basic_stats(df)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total receipts", stats["total_receipts"])
        col2.metric("Total spend (USD)", f"{stats['total_spend_usd']:.2f}")
        col3.metric("Avg receipt (USD)", f"{stats['avg_receipt_usd']:.2f}")

        st.markdown("### Spend by category")
        cat_spend = df.groupby("category")["total_usd"].sum().sort_values(ascending=False)
        st.bar_chart(cat_spend)

        st.markdown("### Top merchants")
        top_merch = (
            df.groupby("merchant_clean")["total_usd"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
        )
        st.bar_chart(top_merch)

        st.markdown("### Monthly trend")
        monthly = (
            df.dropna(subset=["month_label"])
            .groupby("month_label")["total_usd"]
            .sum()
            .sort_index()
        )
        st.line_chart(monthly)