# app/ui_streamlit.py
import os
import pandas as pd
import streamlit as st

from vispend_core.config import UPLOAD_DIR, ANALYTICS_OUTPUT_DIR
from vispend_core.pipeline import process_single_receipt
from vispend_core.analytics_core import load_and_clean_analytics, compute_basic_stats

st.set_page_config(
    page_title="Vispend AI",
    page_icon="",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp {
        background-color: #f7f6f3;
        color: #1f2933;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }

    h1, h2, h3 {
        color: #1f2933;
        font-weight: 600;
        letter-spacing: -0.02em;
    }

    .hero-box {
        background: #ffffff;
        border: 1px solid #e6e3dd;
        border-radius: 16px;
        padding: 1.5rem 1.5rem 1.2rem 1.5rem;
        margin-bottom: 1.25rem;
    }

    .section-box {
        background: #ffffff;
        border: 1px solid #e6e3dd;
        border-radius: 16px;
        padding: 1.25rem;
        margin-bottom: 1rem;
    }

    .small-note {
        color: #5b6570;
        font-size: 0.95rem;
        line-height: 1.6;
    }

    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e6e3dd;
        padding: 1rem;
        border-radius: 14px;
    }

    div[data-testid="stFileUploader"] {
        background-color: #fcfcfa;
        border-radius: 12px;
        padding: 0.5rem;
    }

    .stButton > button {
        background-color: #2d6a6a;
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.55rem 1.1rem;
        font-weight: 500;
    }

    .stButton > button:hover {
        background-color: #245757;
        color: white;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
    }

    .stTabs [data-baseweb="tab"] {
        background: #ece9e3;
        border-radius: 10px;
        padding: 0.5rem 1rem;
    }

    .stTabs [aria-selected="true"] {
        background: #dfeceb;
        color: #173c3c;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero-box">
        <h1>Vispend AI</h1>
        <p class="small-note">
            A receipt image-processing and OCR analysis system for extracting structured information
            from uploaded receipts and presenting clear spending summaries.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_upload, tab_table, tab_analytics = st.tabs(
    ["Upload and process", "Processed receipts", "Analytics"]
)

csv_path = os.path.join(ANALYTICS_OUTPUT_DIR, "ocr_batch_results.csv")

with tab_upload:
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Upload receipts")
    st.caption("Upload receipt images in JPG, JPEG, or PNG format.")

    uploaded_files = st.file_uploader(
        "Select receipt images",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        rows = []

        for uploaded_file in uploaded_files:
            save_path = os.path.join(UPLOAD_DIR, uploaded_file.name)

            with open(save_path, "wb") as file_obj:
                file_obj.write(uploaded_file.read())

            with st.spinner(f"Processing {uploaded_file.name}"):
                try:
                    result = process_single_receipt(save_path)
                    rows.append(result)
                except Exception as exc:
                    rows.append(
                        {
                            "file": uploaded_file.name,
                            "merchant": None,
                            "date": None,
                            "category": None,
                            "total_usd": None,
                            "payment_method": None,
                            "error": str(exc),
                        }
                    )

        df_new = pd.DataFrame(rows)

        if os.path.exists(csv_path):
            df_existing = pd.read_csv(csv_path)
            df_all = pd.concat([df_existing, df_new], ignore_index=True)
        else:
            df_all = df_new

        df_all.to_csv(csv_path, index=False)

        st.success("Processing completed and results were saved.")

        preview_cols = [col for col in ["file", "merchant", "date", "category", "total_usd", "payment_method", "error"] if col in df_new.columns]
        st.markdown("#### New results")
        st.dataframe(df_new[preview_cols], use_container_width=True)

    else:
        st.info("Upload one or more receipts to begin the extraction process.")
    st.markdown("</div>", unsafe_allow_html=True)

with tab_table:
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Processed receipts")

    if os.path.exists(csv_path):
        try:
            df = load_and_clean_analytics(csv_path)

            table_cols = [
                col for col in
                ["file", "date", "merchant_clean", "category", "total_usd", "payment_method"]
                if col in df.columns
            ]

            st.dataframe(
                df[table_cols].sort_values("date", ascending=False),
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"Could not load processed receipts: {exc}")
    else:
        st.info("No processed receipts are available yet.")
    st.markdown("</div>", unsafe_allow_html=True)

with tab_analytics:
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Analytics overview")

    if not os.path.exists(csv_path):
        st.info("No analytics data is available yet.")
    else:
        try:
            df = load_and_clean_analytics(csv_path)
            stats = compute_basic_stats(df)

            col1, col2, col3 = st.columns(3)
            col1.metric("Total receipts", stats["total_receipts"])
            col2.metric("Total spend (USD)", f"{stats['total_spend_usd']:.2f}")
            col3.metric("Average receipt (USD)", f"{stats['avg_receipt_usd']:.2f}")

            st.markdown("#### Spending by category")
            category_spend = (
                df.groupby("category")["total_usd"]
                .sum()
                .sort_values(ascending=False)
            )
            st.bar_chart(category_spend)

            st.markdown("#### Top merchants")
            top_merchants = (
                df.groupby("merchant_clean")["total_usd"]
                .sum()
                .sort_values(ascending=False)
                .head(10)
            )
            st.bar_chart(top_merchants)

            st.markdown("#### Monthly trend")
            monthly = (
                df.dropna(subset=["month_label"])
                .groupby("month_label")["total_usd"]
                .sum()
                .sort_index()
            )
            st.line_chart(monthly)

        except Exception as exc:
            st.error(f"Could not generate analytics: {exc}")
    st.markdown("</div>", unsafe_allow_html=True)