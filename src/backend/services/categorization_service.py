import os, json, logging
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from ..models import CategoryFeedback

logger = logging.getLogger(__name__)

CATEGORY_RULES = {
    "Groceries": ["supermarket","grocery","market","tesco","aeon","giant","mydin",
        "cold storage","jaya grocer","village grocer","99 speedmart","kk mart",
        "walmart","kroger","whole foods","trader joe","aldi","lidl","carrefour",
        "hypermarket","minimarket","7-eleven","familymart","lawson","circle k"],
    "Dining": ["restaurant","cafe","coffee","bistro","food court","mamak","nasi",
        "mcdonald","kfc","pizza","burger","subway","starbucks","kopitiam","warung",
        "hawker","fast food","sushi","ramen","dim sum","bakery","dessert","bubble tea"],
    "Transport": ["grab","uber","lyft","taxi","petrol","fuel","gas station","shell",
        "petronas","caltex","esso","toll","parking","lrt","mrt","bus","train",
        "flight","airline","airasia","rapidkl","highway","ev charging"],
    "Shopping": ["h&m","zara","uniqlo","cotton on","zalora","shopee","lazada",
        "amazon","department store","boutique","fashion","clothing","apparel",
        "shoe","bag","watch","jewellery","nike","adidas","ikea","furniture"],
    "Health & Medical": ["pharmacy","clinic","hospital","doctor","dentist","optical",
        "watsons","guardian","caring pharmacy","alpro","laboratory","health",
        "medical","medicine","drug","supplement","vitamin"],
    "Entertainment": ["cinema","movie","gsc","tgv","mbo","netflix","spotify",
        "game","steam","concert","event","ticket","bowling","karaoke","arcade"],
    "Utilities & Bills": ["tnb","syabas","indah water","unifi","maxis","celcom",
        "digi","astro","electric","water bill","internet","telco","phone bill",
        "broadband","postpaid","prepaid","top up"],
    "Education": ["university","college","school","tuition","course","class",
        "book","stationery","popular bookstore","academy","training","udemy"],
    "Travel & Accommodation": ["hotel","resort","motel","airbnb","agoda",
        "booking.com","hostel","villa","lodge","inn","travel","holiday","tour"],
    "Financial Services": ["bank","atm","maybank","cimb","public bank","rhb",
        "hong leong","ambank","insurance","takaful","investment","service charge"],
}

CONFIDENCE_HIGH = 0.92
CONFIDENCE_MEDIUM = 0.70
CONFIDENCE_LOW = 0.45


def rule_based_categorize(merchant, ocr_text, translated_text) -> Tuple[Optional[str], float]:
    search = " ".join(filter(None, [
        (merchant or "").lower(),
        (ocr_text or "").lower()[:500],
        (translated_text or "").lower()[:500],
    ]))
    best_category, best_score = None, 0
    for category, keywords in CATEGORY_RULES.items():
        hits = sum(1 for kw in keywords if kw in search)
        score = hits / max(len(keywords) * 0.1, 1)
        if hits > 0 and score > best_score:
            best_score, best_category = score, category
    if best_category:
        return best_category, round(min(CONFIDENCE_HIGH, CONFIDENCE_MEDIUM + best_score * 0.1), 3)
    return None, 0.0


def check_user_history(db, user_id, merchant_normalized) -> Optional[str]:
    if not merchant_normalized:
        return None
    fb = (db.query(CategoryFeedback)
          .filter(CategoryFeedback.user_id == user_id,
                  CategoryFeedback.merchant_normalized == merchant_normalized)
          .order_by(CategoryFeedback.created_at.desc()).first())
    return fb.user_corrected_category if fb else None


def ai_categorize(merchant, ocr_text, translated_text) -> Tuple[Optional[str], float]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, 0.0
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        categories = list(CATEGORY_RULES.keys()) + ["Other"]
        context = f"Merchant: {merchant or 'Unknown'}\n"
        if translated_text:
            context += f"Receipt (translated): {translated_text[:600]}\n"
        elif ocr_text:
            context += f"Receipt: {ocr_text[:600]}\n"
        prompt = f"""Classify this receipt into ONE category.
Categories: {', '.join(categories)}
{context}
Reply ONLY with JSON: {{"category": "<cat>", "subcategory": "<optional>", "confidence": <0-1>}}"""
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100, temperature=0.1,
        )
        result = json.loads(resp.choices[0].message.content.strip())
        cat = result.get("category", "Other")
        conf = float(result.get("confidence", CONFIDENCE_MEDIUM))
        if cat not in categories:
            cat, conf = "Other", CONFIDENCE_LOW
        return cat, round(conf, 3)
    except Exception as e:
        logger.warning(f"AI categorization failed: {e}")
        return None, 0.0


def categorize_receipt(db, user_id, merchant, merchant_normalized, ocr_text, translated_text):
    """Returns (category, subcategory, confidence, source, needs_review)"""
    historical = check_user_history(db, user_id, merchant_normalized)
    if historical:
        return historical, None, CONFIDENCE_HIGH, "user_history", False

    category, confidence = rule_based_categorize(merchant, ocr_text, translated_text)
    if category and confidence >= CONFIDENCE_MEDIUM:
        return category, None, confidence, "rule", confidence < CONFIDENCE_HIGH

    ai_category, ai_confidence = ai_categorize(merchant, ocr_text, translated_text)
    if ai_category and ai_confidence >= CONFIDENCE_LOW:
        return ai_category, None, ai_confidence, "ai", ai_confidence < CONFIDENCE_HIGH

    if category:
        return category, None, confidence, "rule", True
    return "Other", None, CONFIDENCE_LOW, "fallback", True


def save_category_feedback(db, user_id, receipt_id, merchant_normalized, ai_predicted, user_corrected):
    fb = CategoryFeedback(
        user_id=user_id, receipt_id=receipt_id,
        merchant_normalized=merchant_normalized,
        ai_predicted_category=ai_predicted,
        user_corrected_category=user_corrected,
    )
    db.add(fb)
    db.commit()