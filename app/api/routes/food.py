import logging
from datetime import datetime, timedelta
from typing import Optional, List
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Body
from pydantic import BaseModel, Field

from app.api.deps import (
    get_current_user,
    get_food_repo,
    get_gemini_service,
)
from app.api.schemas import (
    FoodEntryResponse,
    FoodItemSchema,
    FoodTextAnalyzeRequest,
    FoodSaveRequest,
)
from app.database.models import UserDB, FoodEntryDB, FoodItemDB
from app.database.repositories import FoodRepository
from app.services import GeminiService, ImageProcessingService, InvalidImageError, GeminiServiceError
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/food", tags=["food"])


class PortionUpdateRequest(BaseModel):
    new_portion_g: Optional[float] = None
    delta_g: Optional[float] = None


class CustomFoodCreateRequest(BaseModel):
    name: str
    calories_per_100g: int
    protein_per_100g: float
    fat_per_100g: float
    carbs_per_100g: float
    is_favorite: bool = False


@router.get("", response_model=list[FoodEntryResponse])
@router.get("/today", response_model=list[FoodEntryResponse])
async def get_today_food(
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    entries_db = await food_repo.get_entries_by_date(user.id, today_str)
    return [
        FoodEntryResponse(
            id=e.id,
            meal_type=e.meal_type,
            entry_date=e.entry_date,
            entry_time=e.entry_time,
            total_calories=e.total_calories,
            total_protein=e.total_protein,
            total_fat=e.total_fat,
            total_carbs=e.total_carbs,
            advice=e.advice,
            items=[
                FoodItemSchema(
                    id=it.id,
                    name=it.name,
                    portion_g=it.portion_g,
                    calories=it.calories,
                    protein_g=it.protein_g,
                    fat_g=it.fat_g,
                    carbs_g=it.carbs_g,
                )
                for it in e.items
            ]
        )
        for e in entries_db
    ]


@router.patch("/entries/{entry_id}/items/{item_id}", response_model=FoodEntryResponse)
async def update_item_portion(
    entry_id: int,
    item_id: int,
    payload: PortionUpdateRequest,
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    """
    Modifies portion of a specific food item (±50g or exact value)
    and recalculates total KBJU proportionally.
    """
    entry = await food_repo.get_entry_by_id(entry_id)
    if not entry or entry.user_id != user.id:
        raise HTTPException(status_code=404, detail="Запись еды не найдена.")

    target_item = next((it for it in entry.items if it.id == item_id), None)
    if not target_item:
        raise HTTPException(status_code=404, detail="Позиция блюда не найдена.")

    new_portion = payload.new_portion_g
    if new_portion is None and payload.delta_g is not None:
        new_portion = max(10.0, target_item.portion_g + payload.delta_g)

    if new_portion is None or new_portion <= 0:
        raise HTTPException(status_code=400, detail="Некорректный размер порции.")

    updated_entry = await food_repo.update_item_portion(
        entry_id=entry_id,
        item_id=item_id,
        new_portion_g=new_portion,
        user_id=user.id
    )
    if not updated_entry:
        raise HTTPException(status_code=400, detail="Не удалось обновить порцию.")

    return FoodEntryResponse(
        id=updated_entry.id,
        meal_type=updated_entry.meal_type,
        entry_date=updated_entry.entry_date,
        entry_time=updated_entry.entry_time,
        total_calories=updated_entry.total_calories,
        total_protein=updated_entry.total_protein,
        total_fat=updated_entry.total_fat,
        total_carbs=updated_entry.total_carbs,
        advice=updated_entry.advice,
        items=[
            FoodItemSchema(
                id=it.id,
                name=it.name,
                portion_g=it.portion_g,
                calories=it.calories,
                protein_g=it.protein_g,
                fat_g=it.fat_g,
                carbs_g=it.carbs_g,
            ) for it in updated_entry.items
        ]
    )


@router.post("/repeat-yesterday", response_model=list[FoodEntryResponse])
async def repeat_yesterday_food(
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    """
    Duplicates yesterday's logged meals into today for rapid bulking tracking.
    """
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    now_local = datetime.now(tz)
    today_str = now_local.strftime("%Y-%m-%d")
    yesterday_str = (now_local - timedelta(days=1)).strftime("%Y-%m-%d")

    created_entries = await food_repo.repeat_yesterday_entries(
        user_id=user.id,
        today_str=today_str,
        yesterday_str=yesterday_str
    )
    return [
        FoodEntryResponse(
            id=e.id,
            meal_type=e.meal_type,
            entry_date=e.entry_date,
            entry_time=e.entry_time,
            total_calories=e.total_calories,
            total_protein=e.total_protein,
            total_fat=e.total_fat,
            total_carbs=e.total_carbs,
            advice=e.advice,
            items=[
                FoodItemSchema(
                    id=it.id,
                    name=it.name,
                    portion_g=it.portion_g,
                    calories=it.calories,
                    protein_g=it.protein_g,
                    fat_g=it.fat_g,
                    carbs_g=it.carbs_g,
                ) for it in e.items
            ]
        ) for e in created_entries
    ]


@router.get("/custom")
async def get_custom_foods(
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    return await food_repo.get_custom_foods(user.id)


@router.post("/custom")
async def create_custom_food(
    payload: CustomFoodCreateRequest,
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    food_id = await food_repo.create_custom_food(
        user_id=user.id,
        name=payload.name,
        calories_per_100g=payload.calories_per_100g,
        protein_per_100g=payload.protein_per_100g,
        fat_per_100g=payload.fat_per_100g,
        carbs_per_100g=payload.carbs_per_100g,
        is_favorite=payload.is_favorite
    )
    return {"id": food_id, "name": payload.name, "success": True}


@router.post("/analyze/photo")
async def analyze_food_photo(
    file: UploadFile = File(...),
    user: UserDB = Depends(get_current_user),
    gemini_service: GeminiService = Depends(get_gemini_service),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Загруженный файл не является изображением.")

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
        analysis = await gemini_service.analyze_food(processed_bytes, mime_type, user_id=user.id)
        return analysis.model_dump()
    except InvalidImageError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except GeminiServiceError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except Exception as e:
        logger.error(f"Error in analyze_food_photo: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка при анализе фотографии.")


@router.post("/analyze/text")
async def analyze_food_text(
    payload: FoodTextAnalyzeRequest,
    user: UserDB = Depends(get_current_user),
    gemini_service: GeminiService = Depends(get_gemini_service),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    # Check if custom food matches user database first (priority over Gemini estimation)
    custom_match = await food_repo.match_custom_food(user.id, payload.text)
    if custom_match:
        # Construct exact 100g or typical portion from user's custom dish
        return {
            "meal_name": custom_match["name"],
            "total_calories": custom_match["calories_per_100g"],
            "total_protein": custom_match["protein_per_100g"],
            "total_fat": custom_match["fat_per_100g"],
            "total_carbs": custom_match["carbs_per_100g"],
            "items": [
                {
                    "name": custom_match["name"],
                    "portion_g": 100.0,
                    "calories": custom_match["calories_per_100g"],
                    "protein_g": custom_match["protein_per_100g"],
                    "fat_g": custom_match["fat_per_100g"],
                    "carbs_g": custom_match["carbs_per_100g"],
                }
            ],
            "advice": "Использованы данные из ваших сохранённых блюд."
        }

    try:
        analysis = await gemini_service.analyze_food_text(payload.text, user_id=user.id)
        return analysis.model_dump()
    except GeminiServiceError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except Exception as e:
        logger.error(f"Error in analyze_food_text: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка при анализе описания блюда.")


@router.post("", response_model=FoodEntryResponse)
async def save_food_entry(
    payload: FoodSaveRequest,
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    try:
        tz = ZoneInfo(user.timezone)
    except Exception:
        tz = ZoneInfo("Asia/Almaty")
    now_local = datetime.now(tz)
    today_str = now_local.strftime("%Y-%m-%d")
    time_str = now_local.strftime("%H:%M")

    meal_type = payload.meal_type
    if not meal_type:
        hour = now_local.hour
        if 5 <= hour < 11:
            meal_type = "Завтрак"
        elif 11 <= hour < 16:
            meal_type = "Обед"
        elif 16 <= hour < 22:
            meal_type = "Ужин"
        else:
            meal_type = "Перекус"

    items_db = [
        FoodItemDB(
            name=it.name,
            portion_g=it.portion_g,
            calories=it.calories,
            protein_g=it.protein_g,
            fat_g=it.fat_g,
            carbs_g=it.carbs_g,
        )
        for it in payload.items
    ]

    entry = FoodEntryDB(
        user_id=user.id,
        meal_type=meal_type,
        entry_date=today_str,
        entry_time=time_str,
        total_calories=payload.total_calories,
        total_protein=payload.total_protein,
        total_fat=payload.total_fat,
        total_carbs=payload.total_carbs,
        advice=payload.advice,
        items=items_db,
    )

    saved = await food_repo.create_food_entry(entry)

    # Automatic pantry deduction: deduct items matching pantry
    try:
        consumed_names = [it.name for it in payload.items]
        await food_repo.deduct_pantry_items(user.id, consumed_names)
    except Exception as pe:
        logger.warning(f"Error deducting pantry items: {pe}")

    return FoodEntryResponse(
        id=saved.id,
        meal_type=saved.meal_type,
        entry_date=saved.entry_date,
        entry_time=saved.entry_time,
        total_calories=saved.total_calories,
        total_protein=saved.total_protein,
        total_fat=saved.total_fat,
        total_carbs=saved.total_carbs,
        advice=saved.advice,
        items=[
            FoodItemSchema(
                id=it.id,
                name=it.name,
                portion_g=it.portion_g,
                calories=it.calories,
                protein_g=it.protein_g,
                fat_g=it.fat_g,
                carbs_g=it.carbs_g,
            )
            for it in saved.items
        ]
    )


@router.delete("/{entry_id}")
@router.delete("/entries/{entry_id}")
async def delete_food_entry(
    entry_id: int,
    user: UserDB = Depends(get_current_user),
    food_repo: FoodRepository = Depends(get_food_repo),
):
    deleted = await food_repo.delete_entry(entry_id, user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена.")
    return {"success": True, "message": "Запись удалена"}
