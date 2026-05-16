# vispend_core/analytics_core.py
import os
from difflib import SequenceMatcher

import pandas as pd

from .config import ANALYTICS_OUTPUT_DIR

VALID_CATEGORIES = [
    "Food & Beverage",
    "Grocery",
    "Transport",
    "Retail",
    "Hardware & Tools",
    "Electronics",
    "Fuel",
    "Parking",
    "Healthcare",
    "Other",
]

PAYMENT_MAP = {
    "MASTER": "MASTERCARD",
    "MASTERCARD": "MASTERCARD",
    "VISA": "VISA",
    "CASH": "CASH",
    "DEBIT": "DEBIT",
    "CREDIT": "CREDIT",
    "UNKNOWN": "Unknown",
}


def fuzzy_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def standardize_merchants(merchants, threshold: float = 0.75):
    cleaned = [m for m in merchants if isinstance(m, str) and m.strip()]
    unique = sorted(set(cleaned))
    mapping = {}

    canonical_names = []
    for name in unique:
        matched_name = None

        for canonical in canonical_names:
            if fuzzy_similarity(name, canonical) >= threshold:
                matched_name = canonical
                break

        if matched_name is None:
            matched_name = name
            canonical_names.append(name)

        mapping[name] = matched_name

    return mapping


def load_and_clean_analytics(csv_path: str | None = None) -> pd.DataFrame:
    if csv_path is None:
        csv_path = os.path.join(ANALYTICS_OUTPUT_DIR, "ocr_batch_results.csv")

    df = pd.read_csv(csv_path).copy()

    if "total_usd" not in df.columns and "total_usd" not in df.rename(columns=str.lower).columns:
        raise ValueError("Expected total_usd column not found in analytics input.")

    df["total_usd"] = pd.to_numeric(df["total_usd"], errors="coerce")
    if "subtotal_usd" in df.columns:
        df["subtotal_usd"] = pd.to_numeric(df["subtotal_usd"], errors="coerce")
    if "tax_usd" in df.columns:
        df["tax_usd"] = pd.to_numeric(df["tax_usd"], errors="coerce")

    df = df[df["total_usd"].notna()]
    df = df[df["total_usd"] > 0]

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["month_label"] = df["date"].dt.strftime("%Y-%m")
    df["weekday"] = df["date"].dt.day_name()

    df["category"] = df["category"].fillna("Other").astype(str).str.strip()
    df.loc[~df["category"].isin(VALID_CATEGORIES), "category"] = "Other"

    df["payment_method"] = (
        df["payment_method"]
        .fillna("Unknown")
        .astype(str)
        .str.upper()
        .str.strip()
        .map(lambda x: PAYMENT_MAP.get(x, "Unknown"))
    )

    df["merchant"] = (
        df["merchant"]
        .fillna("Unknown Merchant")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    merchant_map = standardize_merchants(df["merchant"].tolist())
    df["merchant_clean"] = df["merchant"].map(lambda x: merchant_map.get(x, x))

    return df


def compute_basic_stats(df: pd.DataFrame) -> dict:
    return {
        "total_receipts": int(len(df)),
        "total_spend_usd": float(df["total_usd"].sum()),
        "avg_receipt_usd": float(df["total_usd"].mean()),
        "median_receipt_usd": float(df["total_usd"].median()),
        "min_receipt_usd": float(df["total_usd"].min()),
        "max_receipt_usd": float(df["total_usd"].max()),
    }


def detect_anomalies_iqr(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    q1 = df["total_usd"].quantile(0.25)
    q3 = df["total_usd"].quantile(0.75)
    iqr = q3 - q1

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    anomalies = df[(df["total_usd"] < lower) | (df["total_usd"] > upper)].copy()

    bounds = {
        "q1": float(q1),
        "q3": float(q3),
        "iqr": float(iqr),
        "lower_bound": float(lower),
        "upper_bound": float(upper),
        "anomaly_count": int(len(anomalies)),
    }

    return anomalies, bounds


def build_summaries(df: pd.DataFrame) -> dict:
    category_summary = (
        df.groupby("category", dropna=False)["total_usd"]
        .agg(["count", "sum", "mean"])
        .reset_index()
        .sort_values("sum", ascending=False)
    )

    merchant_summary = (
        df.groupby("merchant_clean", dropna=False)["total_usd"]
        .agg(["count", "sum", "mean"])
        .reset_index()
        .sort_values("sum", ascending=False)
    )

    monthly_summary = (
        df.dropna(subset=["month_label"])
        .groupby("month_label")["total_usd"]
        .agg(["count", "sum", "mean"])
        .reset_index()
        .sort_values("month_label")
    )

    weekday_order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    weekday_summary = (
        df.dropna(subset=["weekday"])
        .groupby("weekday")["total_usd"]
        .agg(["count", "sum", "mean"])
        .reset_index()
    )
    weekday_summary["weekday"] = pd.Categorical(
        weekday_summary["weekday"],
        categories=weekday_order,
        ordered=True,
    )
    weekday_summary = weekday_summary.sort_values("weekday")

    payment_summary = (
        df.groupby("payment_method", dropna=False)["total_usd"]
        .agg(["count", "sum", "mean"])
        .reset_index()
        .sort_values("sum", ascending=False)
    )

    return {
        "category_summary": category_summary,
        "merchant_summary": merchant_summary,
        "monthly_summary": monthly_summary,
        "weekday_summary": weekday_summary,
        "payment_summary": payment_summary,
    }


def save_analytics_outputs(df: pd.DataFrame) -> dict:
    os.makedirs(ANALYTICS_OUTPUT_DIR, exist_ok=True)

    cleaned_path = os.path.join(ANALYTICS_OUTPUT_DIR, "final_analytics.csv")
    df.to_csv(cleaned_path, index=False)

    stats = compute_basic_stats(df)
    stats_df = pd.DataFrame([stats])
    stats_path = os.path.join(ANALYTICS_OUTPUT_DIR, "basic_stats.csv")
    stats_df.to_csv(stats_path, index=False)

    summaries = build_summaries(df)
    summary_paths = {}

    for name, summary_df in summaries.items():
        path = os.path.join(ANALYTICS_OUTPUT_DIR, f"{name}.csv")
        summary_df.to_csv(path, index=False)
        summary_paths[name] = path

    anomalies_df, bounds = detect_anomalies_iqr(df)
    anomalies_path = os.path.join(ANALYTICS_OUTPUT_DIR, "anomalies.csv")
    anomalies_df.to_csv(anomalies_path, index=False)

    bounds_df = pd.DataFrame([bounds])
    bounds_path = os.path.join(ANALYTICS_OUTPUT_DIR, "anomaly_bounds.csv")
    bounds_df.to_csv(bounds_path, index=False)

    return {
        "cleaned_path": cleaned_path,
        "stats_path": stats_path,
        "anomalies_path": anomalies_path,
        "bounds_path": bounds_path,
        **summary_paths,
    }