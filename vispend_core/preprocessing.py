# vispend_core/preprocessing.py
import cv2
import numpy as np


def get_skew_angle(img: np.ndarray) -> float:
    edges = cv2.Canny(img, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=100,
        minLineLength=100,
        maxLineGap=10,
    )

    if lines is None:
        return 0.0

    angles = [
        np.degrees(np.arctan2(line[0][3] - line[0][1], line[0][2] - line[0][0]))
        for line in lines
    ]

    return float(np.median(angles)) if angles else 0.0


def deskew(img: np.ndarray) -> np.ndarray:
    angle = get_skew_angle(img)

    if abs(angle) < 1.0:
        return img

    h, w = img.shape
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)

    return cv2.warpAffine(
        img,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def preprocess_receipt(img_path: str, target_width: int = 800) -> np.ndarray:
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {img_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    h, w = gray.shape
    resized_height = int(h * target_width / w)
    gray = cv2.resize(gray, (target_width, resized_height))

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    denoised = cv2.GaussianBlur(enhanced, (3, 3), 0)

    thresh = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2,
    )

    return deskew(thresh)