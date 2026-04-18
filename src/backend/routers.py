# src/backend/routers.py

import logging
import math
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend import analytics_service, services
from backend.dependencies import get_current_user, get_db
from backend.models import CategoryFeedback, Receipt, User
from backend.schemas import (
    AnalyticsSummaryResponse,
    AskAdvisorRequest,
    AskAdvisorResponse,
    CategoryCorrectionRequest,
    InsightItem,
    PaginationMeta,
    ReceiptListResponse,
    ReceiptOut,
    ReceiptUpdate,
    RecentReceiptItem,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserOut,
    UserUpdate,
)
from backend.security import create_access_token, hash_password, verify_password
from rag.advisor import Advisor

logger = logging.getLogger(__name__)

router = APIRouter()
_advisor_instance: Advisor | None = None


def _get_advisor() -> Advisor:
    global _advisor_instance
    if _advisor_instance is None:
        _advisor_instance = Advisor()
    return _advisor_instance


def _get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email.lower().strip()).first()


def _get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username.strip()).first()


def _get_owned_receipt_or_404(db: Session, user_id: int, receipt_id: int) -> Receipt:
    receipt = (
        db.query(Receipt)
        .filter(Receipt.id == receipt_id, Receipt.user_id == user_id)
        .first()
    )
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        )
    return receipt


def _serialize_insights(items: list[dict]) -> list[InsightItem]:
    serialized: list[InsightItem] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        serialized.append(
            InsightItem(
                id=str(item.get("id") or f"insight-{idx}"),
                type=str(item.get("type", "tip")),
                title=str(item.get("title", "Insight")),
                message=str(item.get("message", "")),
                severity=str(item.get("severity", "info")),
                category=item.get("category"),
                amount=item.get("amount"),
                metadata=item.get("metadata"),
            )
        )
    return serialized


# -------------------------------------------------------------------
# Auth endpoints
# -------------------------------------------------------------------

@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)) -> TokenResponse:
    email = user_in.email.lower().strip()
    username = user_in.username.strip()

    if _get_user_by_email(db, email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    if _get_user_by_username(db, username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is already taken",
        )

    user = User(
        email=email,
        username=username,
        full_name=user_in.full_name.strip() if user_in.full_name else None,
        hashed_password=hash_password(user_in.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(subject=user.id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user),
    )


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    user = _get_user_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    token = create_access_token(subject=user.id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user),
    )


@router.get("/auth/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.put("/auth/me", response_model=UserOut)
def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserOut:
    if payload.email is not None:
        email = payload.email.lower().strip()
        existing = db.query(User).filter(
            User.email == email,
            User.id != current_user.id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already in use",
            )
        current_user.email = email

    if payload.username is not None:
        username = payload.username.strip()
        existing = db.query(User).filter(
            User.username == username,
            User.id != current_user.id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username is already in use",
            )
        current_user.username = username

    if payload.full_name is not None:
        current_user.full_name = payload.full_name.strip() if payload.full_name else None

    if payload.password:
        current_user.hashed_password = hash_password(payload.password)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


# -------------------------------------------------------------------
# Receipt endpoints
# -------------------------------------------------------------------

@router.post("/receipts/upload", response_model=ReceiptOut, status_code=status.HTTP_201_CREATED)
async def upload_receipt(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReceiptOut:
    services.validate_upload(file)

    uploads_dir = Path(services.get_uploads_dir())
    uploads_dir.mkdir(parents=True, exist_ok=True)

    saved_path, mime_type = await services.save_upload_file(file, uploads_dir)

    receipt = Receipt(
        user_id=current_user.id,
        original_filename=file.filename or Path(saved_path).name,
        file_path=str(saved_path),
        mime_type=mime_type,
        processing_status="pending",
        needs_review=False,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    background_tasks.add_task(services.process_receipt_background, receipt.id)

    return ReceiptOut.model_validate(receipt)


@router.get("/receipts", response_model=ReceiptListResponse)
def list_receipts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReceiptListResponse:
    query = db.query(Receipt).filter(Receipt.user_id == current_user.id)

    if category:
        query = query.filter(Receipt.category == category)

    if status_filter:
        query = query.filter(Receipt.processing_status == status_filter)

    if needs_review is not None:
        query = query.filter(Receipt.needs_review == needs_review)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Receipt.merchant.ilike(term),
                Receipt.category.ilike(term),
                Receipt.subcategory.ilike(term),
                Receipt.notes.ilike(term),
                Receipt.original_filename.ilike(term),
            )
        )

    total_items = query.count()
    total_pages = math.ceil(total_items / page_size) if total_items else 0

    items = (
        query.order_by(Receipt.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ReceiptListResponse(
        items=[ReceiptOut.model_validate(item) for item in items],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
    )


@router.get("/receipts/{receipt_id}", response_model=ReceiptOut)
def get_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReceiptOut:
    receipt = _get_owned_receipt_or_404(db, current_user.id, receipt_id)
    return ReceiptOut.model_validate(receipt)


@router.put("/receipts/{receipt_id}", response_model=ReceiptOut)
def update_receipt(
    receipt_id: int,
    payload: ReceiptUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReceiptOut:
    receipt = _get_owned_receipt_or_404(db, current_user.id, receipt_id)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(receipt, field, value)

    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return ReceiptOut.model_validate(receipt)


@router.delete("/receipts/{receipt_id}")
def delete_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    receipt = _get_owned_receipt_or_404(db, current_user.id, receipt_id)

    try:
        file_path = Path(receipt.file_path)
        if file_path.exists():
            file_path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Could not delete receipt file %s: %s", receipt.file_path, exc)

    db.delete(receipt)
    db.commit()
    return {"message": "Receipt deleted successfully"}


@router.post("/receipts/{receipt_id}/reprocess", response_model=ReceiptOut)
def reprocess_receipt(
    receipt_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReceiptOut:
    receipt = _get_owned_receipt_or_404(db, current_user.id, receipt_id)
    receipt.processing_status = "pending"
    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    background_tasks.add_task(services.process_receipt_background, receipt.id)
    return ReceiptOut.model_validate(receipt)


@router.post("/receipts/{receipt_id}/correct-category", response_model=ReceiptOut)
def correct_category(
    receipt_id: int,
    payload: CategoryCorrectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReceiptOut:
    receipt = _get_owned_receipt_or_404(db, current_user.id, receipt_id)

    feedback = CategoryFeedback(
        user_id=current_user.id,
        receipt_id=receipt.id,
        merchant=receipt.merchant or "unknown",
        merchant_normalized=services.normalize_merchant(receipt.merchant or ""),
        ai_predicted_category=receipt.category,
        user_corrected_category=payload.category,
        ai_predicted_subcategory=receipt.subcategory,
        user_corrected_subcategory=payload.subcategory,
    )
    db.add(feedback)

    receipt.category = payload.category
    receipt.subcategory = payload.subcategory
    receipt.category_source = "user_correction"
    receipt.needs_review = False

    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return ReceiptOut.model_validate(receipt)


# -------------------------------------------------------------------
# Analytics endpoints
# -------------------------------------------------------------------

@router.get("/analytics", response_model=AnalyticsSummaryResponse)
def get_analytics(
    period: str = Query(default="month"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalyticsSummaryResponse:
    summary = analytics_service.get_spending_summary(db, current_user.id, period=period)
    return AnalyticsSummaryResponse(**summary)


@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
def get_analytics_summary(
    period: str = Query(default="month"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalyticsSummaryResponse:
    summary = analytics_service.get_spending_summary(db, current_user.id, period=period)
    return AnalyticsSummaryResponse(**summary)


@router.get("/analytics/recent", response_model=list[RecentReceiptItem])
def get_recent_receipts(
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RecentReceiptItem]:
    receipts = analytics_service.get_recent_receipts(db, current_user.id, limit=limit)
    return [RecentReceiptItem.model_validate(item) for item in receipts]


# -------------------------------------------------------------------
# Advisor endpoints
# -------------------------------------------------------------------

@router.get("/advisor/insights", response_model=list[InsightItem])
def get_insights(
    period: str = Query(default="month"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[InsightItem]:
    summary = analytics_service.get_spending_summary(db, current_user.id, period=period)
    insights = services.generate_insights(summary)
    return _serialize_insights(insights)


@router.get("/advisor/insights/auto", response_model=list[InsightItem])
def get_auto_insights(
    period: str = Query(default="month"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[InsightItem]:
    summary = analytics_service.get_spending_summary(db, current_user.id, period=period)

    try:
        advisor = _get_advisor()
        insights = advisor.auto_insights(summary)
    except Exception as exc:
        logger.exception("Advisor auto insights failed, using fallback: %s", exc)
        insights = services.generate_auto_insights(summary)

    return _serialize_insights(insights)


@router.post("/advisor/ask", response_model=AskAdvisorResponse)
def ask_advisor(
    payload: AskAdvisorRequest,
    period: str = Query(default="month"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AskAdvisorResponse:
    summary = analytics_service.get_spending_summary(db, current_user.id, period=period)

    try:
        advisor = _get_advisor()
        answer = advisor.advise(payload.question, summary)
    except Exception as exc:
        logger.exception("Advisor ask failed, using fallback: %s", exc)
        answer = services.answer_advisor_question(payload.question, summary)

    if isinstance(answer, str):
        return AskAdvisorResponse(
            answer=answer,
            sources=[],
            insights=[],
        )

    if not isinstance(answer, dict):
        return AskAdvisorResponse(
            answer="I could not generate a reliable answer right now.",
            sources=[],
            insights=[],
        )

    return AskAdvisorResponse(
        answer=str(answer.get("answer", "")),
        sources=answer.get("sources", []) if isinstance(answer.get("sources", []), list) else [],
        insights=_serialize_insights(answer.get("insights", [])),
    )