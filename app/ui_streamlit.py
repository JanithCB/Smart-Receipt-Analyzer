# app/ui_streamlit.py
import os
import sys
import pandas as pd
import streamlit as st

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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
        background-color: #f5f7fa;
        color: #1a2a3a;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1280px;
    }

    h1, h2, h3 {
        color: #1a2a3a;
        font-weight: 600;
        letter-spacing: -0.01em;
        margin-bottom: 0.5rem;
    }

    h1 {
        font-size: 2rem;
    }

    h2 {
        font-size: 1.5rem;
    }

    h3 {
        font-size: 1.25rem;
    }

    .hero-box {
        background: linear-gradient(135deg, #1a2a3a 0%, #1e3a4a 100%);
        border-radius: 20px;
        padding: 2rem 2rem 1.8rem 2rem;
        margin-bottom: 1.75rem;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    }

    .hero-box h1 {
        color: #ffffff;
        margin-bottom: 0.5rem;
    }

    .hero-box p {
        color: #cbd5e0;
        font-size: 1rem;
        line-height: 1.5;
    }

    .section-box {
        background: #ffffff;
        border-radius: 16px;
        padding: 1.5rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        border: 1px solid #e2e8f0;
        transition: box-shadow 0.2s ease;
    }

    .section-box:hover {
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    }

    .small-note {
        color: #64748b;
        font-size: 0.9rem;
        line-height: 1.6;
        margin-top: 0.25rem;
    }

    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        padding: 1.25rem;
        border-radius: 12px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
    }

    div[data-testid="stMetric"] label {
        color: #475569;
        font-weight: 500;
    }

    div[data-testid="stMetric"] .stMetricValue {
        color: #1a2a3a;
        font-weight: 700;
    }

    div[data-testid="stFileUploader"] {
        background-color: #fafbfc;
        border-radius: 12px;
        padding: 0.75rem;
        border: 1px dashed #cbd5e0;
    }

    div[data-testid="stFileUploader"]:hover {
        border-color: #2d6a6a;
        background-color: #f8fafc;
    }

    .stButton > button {
        background-color: #2d6a6a;
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.6rem 1.2rem;
        font-weight: 500;
        transition: all 0.2s ease;
    }

    .stButton > button:hover {
        background-color: #1e4e4e;
        color: white;
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(45, 106, 106, 0.2);
    }

    .stButton > button:active {
        transform: translateY(0px);
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
        background-color: transparent;
        border-bottom: 2px solid #e2e8f0;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 8px 8px 0 0;
        padding: 0.6rem 1.2rem;
        font-weight: 500;
        color: #64748b;
        transition: all 0.2s ease;
    }

    .stTabs [aria-selected="true"] {
        background-color: #2d6a6a;
        color: white;
        border-radius: 8px 8px 0 0;
    }

    .stTabs [data-baseweb="tab"]:hover {
        background-color: #e2e8f0;
        color: #1a2a3a;
    }

    .stAlert {
        border-radius: 12px;
        border-left-width: 4px;
    }

    div[data-testid="stDataFrame"] {
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        overflow: hidden;
    }

    .stSpinner > div {
        border-color: #2d6a6a;
    }

    hr {
        margin: 1rem 0;
        border-color: #e2e8f0;
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
    ["Upload and Process", "Processed Receipts", "Analytics"]
)

csv_path = os.path.join(ANALYTICS_OUTPUT_DIR, "ocr_batch_results.csv")

with tab_upload:
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Upload Receipts")
    st.caption("Supported formats: JPG, JPEG, PNG")

    uploaded_files = st.file_uploader(
        "Select receipt images for processing",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        help="Upload one or more receipt images to extract structured data"
    )

    if uploaded_files:
        rows = []

        for uploaded_file in uploaded_files:
            save_path = os.path.join(UPLOAD_DIR, uploaded_file.name)

            with open(save_path, "wb") as file_obj:
                file_obj.write(uploaded_file.read())

            with st.spinner(f"Processing {uploaded_file.name}..."):
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

        st.success("Processing completed successfully")

        preview_cols = [col for col in ["file", "merchant", "date", "category", "total_usd", "payment_method", "error"] if col in df_new.columns]
        st.markdown("#### Newly Processed Receipts")
        st.dataframe(df_new[preview_cols], use_container_width=True)

    else:
        st.info("Upload receipt images to begin extraction")
    st.markdown("</div>", unsafe_allow_html=True)

with tab_table:
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Processed Receipts")

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
                hide_index=True,
            )
        except Exception as exc:
            st.error(f"Unable to load processed receipts: {exc}")
    else:
        st.info("No processed receipts available")
    st.markdown("</div>", unsafe_allow_html=True)

with tab_analytics:
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Analytics Overview")

    if not os.path.exists(csv_path):
        st.info("Analytics data not yet available")
    else:
        try:
            df = load_and_clean_analytics(csv_path)
            stats = compute_basic_stats(df)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Receipts", stats["total_receipts"])
            with col2:
                st.metric("Total Spend (USD)", f"${stats['total_spend_usd']:.2f}")
            with col3:
                st.metric("Average Receipt (USD)", f"${stats['avg_receipt_usd']:.2f}")

            st.markdown("#### Spending by Category")
            category_spend = (
                df.groupby("category")["total_usd"]
                .sum()
                .sort_values(ascending=False)
            )
            if not category_spend.empty:
                st.bar_chart(category_spend)
            else:
                st.caption("No category data available")

            st.markdown("#### Top Merchants")
            top_merchants = (
                df.groupby("merchant_clean")["total_usd"]
                .sum()
                .sort_values(ascending=False)
                .head(10)
            )
            if not top_merchants.empty:
                st.bar_chart(top_merchants)
            else:
                st.caption("No merchant data available")

            st.markdown("#### Monthly Spending Trend")
            monthly = (
                df.dropna(subset=["month_label"])
                .groupby("month_label")["total_usd"]
                .sum()
                .sort_index()
            )
            if not monthly.empty:
                st.line_chart(monthly)
            else:
                st.caption("No monthly data available")

        except Exception as exc:
            st.error(f"Unable to generate analytics: {exc}")
    st.markdown("</div>", unsafe_allow_html=True)