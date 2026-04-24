# vispend_core/analytics_core.py
import os
import pandas as pd
from difflib import SequenceMatcher
from .config import ANALYTICS_OUTPUT_DIR

VALID_CATEGORIES = [
    "Food & Beverage", "Grocery", "Transport", "Retail",
    "Hardware & Tools", "Electronics", "Fuel",
    "Parking", "Healthcare", "Other",
]

PAYMENT_MAP = {
    "MASTER": "MASTERCARD",
    "MASTERCARD": "MASTERCARD",
    "VISA": "VISA",
    "CASH": "CASH",
    "DEBIT": "DEBIT",
    "UNKNOWN": "Unknown",
}

def fuzzy_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def standardize_merchants(merchants, threshold=0.75):
    unique = list(set(merchants))
    mapping = {}
    for name in unique:
        matched = False
        for canonical in mapping.values():
            if fuzzy_similarity(name, canonical) >= threshold:
                mapping[name] = canonical
                matched = True
                break
        if not matched:
            mapping[name] = name
    return mapping

def load_and_clean_analytics(csv_path: str | None = None) -> pd.DataFrame:
    if csv_path is None:
        csv_path = os.path.join(ANALYTICS_OUTPUT_DIR, "ocr_batch_results.csv")

    df_raw = pd.read_csv(csv_path)
    df = df_raw.copy()

    df = df[df["total_usd"].notna()]
    df = df[df["total_usd"] > 0]

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["month_label"] = df["date"].dt.strftime("%Y-%m")
    df["weekday"] = df["date"].dt.day_name()

    df["category"] = df["category"].fillna("Other").str.strip()
    df.loc[~df["category"].isin(VALID_CATEGORIES), "category"] = "Other"

    df["payment_method"] = (
        df["payment_method"]
        .fillna("Unknown")
        .str.upper()
        .str.strip()
        .map(lambda x: PAYMENT_MAP.get(x, "Unknown"))
    )

    df["merchant"] = (
        df["merchant"]
        .fillna("Unknown Merchant")
        .str.strip()
        .str.upper()
    )

    merchant_map = standardize_merchants(df["merchant"].tolist())
    df["merchant_clean"] = df["merchant"].map(merchant_map)

    return df

def compute_basic_stats(df: pd.DataFrame) -> dict:
    total_raw = len(df)
    total_spend = df["total_usd"].sum()
    avg = df["total_usd"].mean()
    median = df["total_usd"].median()
    return {
        "total_receipts": int(total_raw),
        "total_spend_usd": float(total_spend),
        "avg_receipt_usd": float(avg),
        "median_receipt_usd": float(median),
    }