import os
import threading
from typing import Optional
from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile,
    File, Query, status, BackgroundTasks
)
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Receipt, User          # ✅ LineItem not needed here
from ..schemas import (
    ReceiptOut, ReceiptListOut,
    ReceiptUpdate, CategoryCorrection
)
from ..dependencies import get_current_active_user
from ..services.receipt_processor import save_upload_file, process_receipt
from ..services.categorization_service import save_category_feedback

router = APIRouter(prefix="/receipts", tags=["Receipts"])

ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/webp",
    "image/bmp", "image/tiff", "application/pdf"
}
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB


@router.post("/upload", response_model=ReceiptOut, status_code=status.HTTP_201_CREATED)
async def upload_receipt(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}"
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 15 MB)")

    import io
    file_path = save_upload_file(io.BytesIO(content), file.filename)

    # ✅ Correct column names matching models.py
    receipt = Receipt(
        owner_id=current_user.id,       # ✅ was: user_id
        filename=file.filename,
        file_path=file_path,
        file_size=len(content),
        mime_type=file.content_type,
        processing_status="pending",
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    receipt_id = receipt.id
    user_id    = current_user.id

    def run_processing():
        from ..database import SessionLocal
        bg_db = SessionLocal()
        try:
            # ✅ calls receipt_processor (was calling ocr_pipeline — dead code)
            process_receipt(bg_db, receipt_id, user_id)
        finally:
            bg_db.close()

    thread = threading.Thread(target=run_processing, daemon=True)
    thread.start()

    db.refresh(receipt)
    return receipt


@router.get("", response_model=ReceiptListOut)
def list_receipts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    status: Optional[str] = None,
    needs_review: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = db.query(Receipt).filter(Receipt.owner_id == current_user.id)

    if category:
        query = query.filter(Receipt.category == category)
    if status:
        query = query.filter(Receipt.processing_status == status)
    if needs_review is not None:
        query = query.filter(Receipt.needs_review == needs_review)
    if search:
        like = f"%{search}%"
        query = query.filter(
            Receipt.merchant.ilike(like) |
            Receipt.raw_ocr_text.ilike(like)   # ✅ was: raw_text
        )

    total = query.count()
    items = (
        query.order_by(Receipt.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ReceiptListOut(total=total, page=page, page_size=page_size, items=items)


@router.get("/{receipt_id}", response_model=ReceiptOut)
def get_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    receipt = db.query(Receipt).filter(
        Receipt.id == receipt_id,
        Receipt.owner_id == current_user.id,    # ✅ was: user_id
    ).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


@router.put("/{receipt_id}", response_model=ReceiptOut)
def update_receipt(
    receipt_id: int,
    payload: ReceiptUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    receipt = db.query(Receipt).filter(
        Receipt.id == receipt_id,
        Receipt.owner_id == current_user.id,
    ).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    old_category = receipt.category
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(receipt, field, value)

    new_category = payload.dict(exclude_unset=True).get("category")
    if new_category and new_category != old_category:
        receipt.category_source = "user"
        receipt.needs_review    = False
        receipt.user_verified   = True
        save_category_feedback(
            db=db,
            user_id=current_user.id,
            receipt_id=receipt_id,
            merchant_normalized=receipt.merchant_normalized,
            ai_predicted=old_category,
            user_corrected=new_category,
        )

    db.commit()
    db.refresh(receipt)
    return receipt


@router.delete("/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    receipt = db.query(Receipt).filter(
        Receipt.id == receipt_id,
        Receipt.owner_id == current_user.id,
    ).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    if receipt.file_path and os.path.exists(receipt.file_path):
        try:
            os.remove(receipt.file_path)
        except OSError:
            pass

    db.delete(receipt)
    db.commit()


@router.post("/{receipt_id}/reprocess", response_model=ReceiptOut)
def reprocess_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    receipt = db.query(Receipt).filter(
        Receipt.id == receipt_id,
        Receipt.owner_id == current_user.id,
    ).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    receipt.processing_status = "pending"
    db.commit()

    user_id = current_user.id

    def run_processing():
        from ..database import SessionLocal
        bg_db = SessionLocal()
        try:
            process_receipt(bg_db, receipt_id, user_id)
        finally:
            bg_db.close()

    thread = threading.Thread(target=run_processing, daemon=True)
    thread.start()

    db.refresh(receipt)
    return receipt


@router.post("/correct-category", response_model=ReceiptOut)
def correct_category(
    payload: CategoryCorrection,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    receipt = db.query(Receipt).filter(
        Receipt.id == payload.receipt_id,
        Receipt.owner_id == current_user.id,
    ).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    old_category       = receipt.category
    receipt.category   = payload.corrected_category
    if payload.corrected_subcategory:
        receipt.subcategory = payload.corrected_subcategory
    receipt.category_source = "user"
    receipt.needs_review    = False
    receipt.user_verified   = True

    save_category_feedback(
        db=db,
        user_id=current_user.id,
        receipt_id=payload.receipt_id,
        merchant_normalized=receipt.merchant_normalized,
        ai_predicted=old_category,
        user_corrected=payload.corrected_category,
    )

    db.commit()
    db.refresh(receipt)
    return receipt