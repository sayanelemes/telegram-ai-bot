import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, status
from app.api.deps import (
    get_current_user,
    get_expense_repo,
    get_expense_service,
    get_gemini_service,
    get_stats_service,
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
    CategoryBudgetSchema,
    CategoryBudgetCreateRequest,
    ImpulseToggleRequest,
    ImpulseLimitUpdateRequest,
    ImpulseStatsResponse,
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

    month_start_str = datetime.now(tz).strftime("%Y-%m-01")
    alert_info = await expense_repo.check_category_budget_alert(
        user_id=user.id,
        category=saved.category,
        month_start_date=month_start_str,
        current_date=today_str,
    )
    alert_msg = alert_info["message"] if alert_info else None

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
        alert=alert_msg,
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


@router.get("/export/csv")
async def export_expenses_csv(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: UserDB = Depends(get_current_user),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
):
    csv_data = await expense_repo.export_expenses_csv(
        user_id=user.id,
        start_date=start_date,
        end_date=end_date,
    )
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="expenses.csv"'}
    )


@router.get("/category-limits", response_model=list[CategoryBudgetSchema])
async def get_category_limits(
    user: UserDB = Depends(get_current_user),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
    stats_service: "StatsService" = Depends(get_stats_service),
):
    stats = await stats_service.get_expense_stats(user.id, period="month", timezone_str=user.timezone)
    return [CategoryBudgetSchema(**cb) for cb in stats["category_budgets"]]


@router.post("/category-limits", response_model=CategoryBudgetSchema)
async def set_category_limit(
    payload: CategoryBudgetCreateRequest,
    user: UserDB = Depends(get_current_user),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
):
    saved = await expense_repo.save_category_budget(
        user_id=user.id,
        category=payload.category,
        monthly_limit=payload.monthly_limit,
    )
    return CategoryBudgetSchema(
        category=saved["category"],
        monthly_limit=saved["monthly_limit"],
    )


@router.delete("/category-limits/{category}")
async def delete_category_limit(
    category: str,
    user: UserDB = Depends(get_current_user),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
):
    deleted = await expense_repo.delete_category_budget(user.id, category)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Лимит категории не найден.")
    return {"success": True, "message": "Лимит категории удален"}


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


@router.get("/impulse-stats", response_model=ImpulseStatsResponse)
async def get_impulse_stats(
    user: UserDB = Depends(get_current_user),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
):
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    now = datetime.now(tz)
    month_start_str = now.strftime("%Y-%m-01")
    today_str = now.strftime("%Y-%m-%d")

    stats = await expense_repo.get_impulse_stats(
        user_id=user.id,
        start_date=month_start_str,
        end_date=today_str,
    )
    return ImpulseStatsResponse(**stats)


@router.post("/impulse-limit")
async def update_impulse_limit(
    payload: ImpulseLimitUpdateRequest,
    user: UserDB = Depends(get_current_user),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
):
    new_limit = await expense_repo.update_impulse_monthly_limit(
        user_id=user.id,
        limit=payload.impulse_monthly_limit,
    )
    return {
        "success": True,
        "impulse_monthly_limit": new_limit,
    }


@router.patch("/{expense_id}/impulse", response_model=ExpenseEntryResponse)
async def toggle_expense_impulse(
    expense_id: int,
    payload: Optional[ImpulseToggleRequest] = None,
    user: UserDB = Depends(get_current_user),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
):
    is_imp = payload.is_impulse if payload else None
    reason = payload.impulse_reason if payload else None

    updated = await expense_repo.toggle_or_set_impulse(
        user_id=user.id,
        expense_id=expense_id,
        is_impulse=is_imp,
        impulse_reason=reason,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Расход не найден.")

    return ExpenseEntryResponse(
        id=updated.id,
        merchant=updated.merchant,
        amount=updated.amount,
        currency=updated.currency,
        category=updated.category,
        category_label=ExpenseService.get_category_name(updated.category),
        entry_type=updated.entry_type,
        is_impulsive=updated.is_impulsive,
        ai_analysis=updated.ai_analysis,
        description=updated.description,
        expense_date=updated.expense_date,
        items=[
            ExpenseItemSchema(
                id=it.id,
                name=it.name,
                price=it.price,
                quantity=it.quantity,
            )
            for it in updated.items
        ]
    )


@router.delete("/{expense_id}")
async def delete_expense(
    expense_id: int,
    user: UserDB = Depends(get_current_user),
    expense_repo: ExpenseRepository = Depends(get_expense_repo),
):
    deleted = await expense_repo.delete_expense(expense_id, user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Расход/доход не найден.")
    return {"success": True, "message": "Запись успешно удалена"}

