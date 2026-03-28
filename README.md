# kyc-robustness
Given a photo or scan of a shopping receipt, the system cleans and normalizes the image (image processing), calls an OCR API to extract text (computer vision via API), parses totals and items, and then aggregates spending per month and per category.

# Vispend AI — Receipt Intelligence System

An end-to-end AI-powered receipt analytics pipeline built with Python, 
OpenCV, OCR, and LLM-based field extraction.

## Pipeline

Raw Receipt Image
      |
[OpenCV Pipeline]  — CLAHE, Denoising, Adaptive Threshold, Deskew
      |
[OCR.Space API]    — Text extraction from preprocessed image
      |
[Groq / Llama-4]   — Structured field parsing (merchant, date, total, category)
      |
[Analytics]        — USD conversion, categorization, anomaly detection, charts

## Notebooks

| Notebook | Purpose |
|---|---|
| 01_exploration.ipynb | CV preprocessing pipeline |
| 02_ocr_extraction.ipynb | OCR extraction + AI field parsing |
| 03_analytics.ipynb | Analytics, visualizations, insights |

## Results

- 101 receipts processed
- 85.1% successful extraction rate
- $1,463.52 USD total spend captured
- 8 spending categories classified
- Anomaly detection using IQR method
- AI-generated financial insights via Llama-4 Scout

## Tech Stack

Python, OpenCV, NumPy, Pandas, Matplotlib, OCR.Space API, Groq API
