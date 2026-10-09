import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
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


@router.post("/analyze/photo")
async def analyze_food_photo(
    file: UploadFile = File(...),
    user: UserDB = Depends(get_current_user),
    gemini_service: GeminiService = Depends(get_gemini_service),
):
    # Validate MIME type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Загруженный файл не является изображением.",
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
        analysis = await gemini_service.analyze_food(processed_bytes, mime_type)
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
):
    try:
        analysis = await gemini_service.analyze_food_text(payload.text)
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
    # Enforce user isolation
    deleted = await food_repo.delete_entry(entry_id, user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена.")
    return {"success": True, "message": "Запись удалена"}
