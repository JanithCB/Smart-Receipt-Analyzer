# kyc-robustness
KYC Document Robustness Analyzer that runs before OCR and face match. It uses image processing to score blur, contrast, cropping, and texture anomalies, then a small CV engine to classify scans as Good, Poor, or Suspicious, and highlight potentially tampered regions.
