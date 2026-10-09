import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from app.api.deps import (
    get_current_user,
    get_expense_repo,
    get_expense_service,
    get_gemini_service,
)
from app.api.schemas import (
    ExpensesSummaryResponse,
    ExpenseEntryResponse,
    ExpenseItemSchema,
    CategoryExpenseSummary,
    ExpenseTextAnalyzeRequest,
    ExpenseSaveRequest,
    BudgetSchema,
    BudgetUpdateRequest,
)
from app.database.models import UserDB, ExpenseDB, ExpenseItemDB
from app.database.repositories import ExpenseRepository
from app.services import (
    ExpenseService,
    GeminiService,
    ImageProcessingService,
    InvalidImageError,
    GeminiServiceError,
)
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("", response_model=ExpensesSummaryResponse)
async def get_expenses_summary(
    user: UserDB = Depends(get_current_user),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
    expense_service: ExpenseService = Depends(get_expense_service),
):
    stats = await expense_service.get_expense_statistics(user.id, user.timezone)
    recent_db = await expense_repo.get_recent_expenses(user.id, limit=20)

    categories_list = [
        CategoryExpenseSummary(
            category=cat["category"],
            label=cat["label"],
            total=cat["total"],
            count=cat["count"],
        )
        for cat in stats["categories"]
    ]

    recent_list = [
        ExpenseEntryResponse(
            id=e.id,
            merchant=e.merchant,
            amount=e.amount,
            currency=e.currency,
            category=e.category,
            category_label=ExpenseService.get_category_name(e.category),
            entry_type=e.entry_type,
            is_impulsive=e.is_impulsive,
            ai_analysis=e.ai_analysis,
            description=e.description,
            expense_date=e.expense_date,
            items=[
                ExpenseItemSchema(
                    id=it.id,
                    name=it.name,
                    price=it.price,
                    quantity=it.quantity,
                )
                for it in e.items
            ]
        )
        for e in recent_db
    ]

    budget_schema = None
    if stats.get("budget"):
        budget_schema = BudgetSchema(**stats["budget"])

    return ExpensesSummaryResponse(
        today_total=stats["today_total"],
        week_total=stats["week_total"],
        month_total=stats["month_total"],
        month_income=stats.get("month_income", 0.0),
        net_balance=stats.get("net_balance", 0.0),
        month_title=stats["month_title"],
        categories=categories_list,
        recent=recent_list,
        budget=budget_schema,
    )


@router.post("/analyze/photo")
async def analyze_receipt_photo(
    file: UploadFile = File(...),
    user: UserDB = Depends(get_current_user),
    gemini_service: GeminiService = Depends(get_gemini_service),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл не является изображением.",
        )

    image_bytes = await file.read()
    if len(image_bytes) > settings.max_image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Размер файла превышает допустимый ({settings.MAX_IMAGE_SIZE_MB} МБ).",
        )

    try:
        processed_bytes, mime_type = ImageProcessingService.process_image(
            image_bytes, max_size_bytes=settings.max_image_bytes
        )
        analysis = await gemini_service.analyze_receipt(processed_bytes, mime_type)
        return analysis.model_dump()
    except InvalidImageError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except GeminiServiceError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except Exception as e:
        logger.error(f"Error in analyze_receipt_photo: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка при анализе чека.")


@router.post("/analyze/text")
async def analyze_expense_text(
    payload: ExpenseTextAnalyzeRequest,
    user: UserDB = Depends(get_current_user),
    gemini_service: GeminiService = Depends(get_gemini_service),
):
    try:
        parsed = await gemini_service.parse_expense(payload.text)
        return parsed.model_dump()
    except GeminiServiceError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except Exception as e:
        logger.error(f"Error in analyze_expense_text: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка при анализе текста расхода.")


@router.post("", response_model=ExpenseEntryResponse)
async def save_expense(
    payload: ExpenseSaveRequest,
    user: UserDB = Depends(get_current_user),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
):
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    items_db = [
        ExpenseItemDB(
            name=it.name,
            price=it.price,
            quantity=it.quantity,
        )
        for it in payload.items
    ]

    expense = ExpenseDB(
        user_id=user.id,
        merchant=payload.merchant,
        amount=payload.amount,
        currency=payload.currency,
        category=payload.category,
        entry_type=payload.entry_type,
        is_impulsive=payload.is_impulsive,
        ai_analysis=payload.ai_analysis,
        description=payload.description,
        raw_text=payload.raw_text,
        expense_date=today_str,
        items=items_db,
    )

    saved = await expense_repo.create_expense(expense)
    return ExpenseEntryResponse(
        id=saved.id,
        merchant=saved.merchant,
        amount=saved.amount,
        currency=saved.currency,
        category=saved.category,
        category_label=ExpenseService.get_category_name(saved.category),
        entry_type=saved.entry_type,
        is_impulsive=saved.is_impulsive,
        ai_analysis=saved.ai_analysis,
        description=saved.description,
        expense_date=saved.expense_date,
        items=[
            ExpenseItemSchema(
                id=it.id,
                name=it.name,
                price=it.price,
                quantity=it.quantity,
            )
            for it in saved.items
        ]
    )


@router.get("/budget", response_model=BudgetSchema)
async def get_budget(
    user: UserDB = Depends(get_current_user),
    expense_service: ExpenseService = Depends(get_expense_service),
):
    summary = await expense_service.get_budget_summary(user.id, user.timezone)
    return BudgetSchema(**summary)


@router.post("/budget", response_model=BudgetSchema)
async def update_budget(
    payload: BudgetUpdateRequest,
    user: UserDB = Depends(get_current_user),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
    expense_service: ExpenseService = Depends(get_expense_service),
):
    await expense_repo.save_budget(
        user_id=user.id,
        weekly_budget=payload.weekly_budget,
        monthly_budget=payload.monthly_budget,
    )
    summary = await expense_service.get_budget_summary(user.id, user.timezone)
    return BudgetSchema(**summary)


@router.delete("/{expense_id}")
async def delete_expense(
    expense_id: int,
    user: UserDB = Depends(get_current_user),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
):
    # Enforce user isolation
    deleted = await expense_repo.delete_expense(expense_id, user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Расход/доход не найден.")
    return {"success": True, "message": "Запись успешно удалена"}
