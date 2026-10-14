import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Body, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.database.models import UserDB
from app.api.deps import get_current_user, get_db_manager, get_gemini_service
from app.database.connection import DatabaseManager
from app.services.gemini import GeminiService
from app.services.smart_input import SmartInputService, ProcessedInputOutcome, SmartInputItem
from app.services.image import ImageProcessingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/input", tags=["Smart Input"])


class TextInputRequest(BaseModel):
    text: str = Field(..., description="Single-phrase input from user")
    occurred_at: Optional[str] = None


class UndoInputRequest(BaseModel):
    link_id: str


class ConfirmInputRequest(BaseModel):
    link_id: str
    items: List[SmartInputItem]
    intent: str
    currency: str = "₸"


def get_smart_input_service(
    db: DatabaseManager = Depends(get_db_manager),
    gemini: GeminiService = Depends(get_gemini_service),
) -> SmartInputService:
    return SmartInputService(db_manager=db, gemini_service=gemini)


@router.post("", response_model=ProcessedInputOutcome)
async def process_unified_input(
    payload: Optional[TextInputRequest] = Body(None),
    file: Optional[UploadFile] = File(None),
    text_form: Optional[str] = Form(None),
    current_user: UserDB = Depends(get_current_user),
    service: SmartInputService = Depends(get_smart_input_service),
    gemini: GeminiService = Depends(get_gemini_service),
):
    """
    Unified smart input endpoint.
    Accepts text, image (photo of food or receipt), or audio recording.
    """
    raw_text = payload.text if payload else (text_form or "")

    # If file is attached (image or audio)
    if file:
        content_bytes = await file.read()
        mime_type = file.content_type or "image/jpeg"

        if mime_type.startswith("audio/"):
            # Audio transcription fallback
            try:
                # Transcribe with Gemini
                from google.genai import types
                audio_part = types.Part.from_bytes(data=content_bytes, mime_type=mime_type)
                prompt = "Транскрибируй аудиозапись в чистый русский текст. Напиши только распознанный текст без пояснений."
                config = types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=0))
                resp = await gemini._generate_with_fallback([audio_part, prompt], config=config, user_id=current_user.id)
                raw_text = (resp.text or "").strip()
            except Exception as e:
                logger.error(f"Voice transcription error: {e}")
                raise HTTPException(status_code=400, detail="Не удалось распознать голосовое сообщение.")
        else:
            # Image uploaded via unified input bar
            image_service = ImageProcessingService()
            processed_bytes, _ = image_service.process_image_bytes(content_bytes)

            # Analyze image as food first, fallback to receipt
            try:
                food_res = await gemini.analyze_food(processed_bytes, mime_type="image/jpeg", user_id=current_user.id)
                # Format as items
                text_equiv = f"Съел {food_res.meal_name}: " + ", ".join(f"{it.name} {it.portion_g}г" for it in food_res.items)
                raw_text = text_equiv
            except Exception:
                try:
                    rec_res = await gemini.analyze_receipt(processed_bytes, mime_type="image/jpeg", user_id=current_user.id)
                    text_equiv = f"Покупка в {rec_res.merchant} на сумму {rec_res.total_amount} {rec_res.currency}"
                    raw_text = text_equiv
                except Exception as ex:
                    raise HTTPException(status_code=400, detail=f"Не удалось распознать фото: {ex}")

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Текст или файл не переданы.")

    outcome = await service.execute_input(
        text=raw_text,
        user_id=current_user.id,
        timezone_str=current_user.timezone or "Asia/Almaty"
    )
    return outcome


@router.post("/undo")
async def undo_unified_input(
    payload: UndoInputRequest,
    current_user: UserDB = Depends(get_current_user),
    service: SmartInputService = Depends(get_smart_input_service),
):
    """
    Atomic undo: deletes both food entry and expense tied to link_id.
    """
    success = await service.undo_by_link_id(link_id=payload.link_id, user_id=current_user.id)
    return {"success": success, "link_id": payload.link_id}
