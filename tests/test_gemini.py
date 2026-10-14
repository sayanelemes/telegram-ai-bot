import pytest
from app.services.gemini import (
    GeminiService,
    FoodAnalysisResult,
    ReceiptAnalysisResult,
    ExpenseParsedResult,
)


def test_food_analysis_pydantic_validation():
    data = {
        "meal_name": "Обед",
        "items": [
            {"name": "Куриное филе", "portion_g": 150.0, "calories": 248, "protein_g": 46.0, "fat_g": 5.0, "carbs_g": 0.0},
            {"name": "Рис", "portion_g": 180.0, "calories": 230, "protein_g": 5.0, "fat_g": 1.0, "carbs_g": 50.0},
        ],
        "total_calories": 478,
        "total_protein": 51.0,
        "total_fat": 6.0,
        "total_carbs": 50.0,
        "advice": "Отличный баланс!"
    }
    result = FoodAnalysisResult.model_validate(data)
    assert result.meal_name == "Обед"
    assert len(result.items) == 2
    assert result.total_calories == 478


def test_receipt_analysis_pydantic_validation():
    data = {
        "merchant": "Magnum",
        "date": "2026-10-08",
        "currency": "₸",
        "category": "food",
        "items": [
            {"name": "Молоко", "price": 500.0, "quantity": 1.0},
            {"name": "Хлеб", "price": 350.0, "quantity": 1.0},
        ],
        "total_amount": 850.0
    }
    result = ReceiptAnalysisResult.model_validate(data)
    assert result.merchant == "Magnum"
    assert result.total_amount == 850.0
    assert len(result.items) == 2


def test_extract_json_text_helper():
    raw_markdown = "```json\n{\"merchant\": \"Magnum\", \"total_amount\": 1000}\n```"
    cleaned = GeminiService._extract_json_text(raw_markdown)
    assert cleaned == "{\"merchant\": \"Magnum\", \"total_amount\": 1000}"


@pytest.mark.asyncio
async def test_mocked_gemini_service(mock_gemini_service):
    food_res = await mock_gemini_service.analyze_food(b"test_image_bytes")
    assert isinstance(food_res, FoodAnalysisResult)
    assert food_res.total_calories == 478

    receipt_res = await mock_gemini_service.analyze_receipt(b"test_receipt_bytes")
    assert isinstance(receipt_res, ReceiptAnalysisResult)
    assert receipt_res.total_amount == 870.0

    parsed_exp = await mock_gemini_service.parse_expense("кофе 1200 тг")
    assert isinstance(parsed_exp, ExpenseParsedResult)
    assert parsed_exp.amount == 1200.0
