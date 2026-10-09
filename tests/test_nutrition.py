import pytest
from app.services.nutrition import NutritionService


def test_bmr_calculation_male():
    # Male: 10 * 80 + 6.25 * 180 - 5 * 25 + 5 = 800 + 1125 - 125 + 5 = 1805
    bmr = NutritionService.calculate_bmr(gender="male", weight_kg=80.0, height_cm=180.0, age=25)
    assert bmr == 1805.0


def test_bmr_calculation_female():
    # Female: 10 * 60 + 6.25 * 165 - 5 * 30 - 161 = 600 + 1031.25 - 150 - 161 = 1320.25
    bmr = NutritionService.calculate_bmr(gender="female", weight_kg=60.0, height_cm=165.0, age=30)
    assert bmr == 1320.25


def test_tdee_calculation():
    bmr = 1800.0
    assert NutritionService.calculate_tdee(bmr, "sedentary") == 1800.0 * 1.2
    assert NutritionService.calculate_tdee(bmr, "light") == 1800.0 * 1.375
    assert NutritionService.calculate_tdee(bmr, "moderate") == 1800.0 * 1.55
    assert NutritionService.calculate_tdee(bmr, "high") == 1800.0 * 1.725
    assert NutritionService.calculate_tdee(bmr, "very_high") == 1800.0 * 1.9


def test_calculate_targets_weight_loss():
    # Male, 80kg, 180cm, 25yo, moderate activity
    result = NutritionService.calculate_targets(
        gender="male",
        age=25,
        height_cm=180.0,
        weight_kg=80.0,
        activity_level="moderate",
        goal="loss"
    )
    assert result.bmr == 1805
    assert result.tdee == int(round(1805 * 1.55))
    # Target calories should be less than TDEE for weight loss
    assert result.target_calories < result.tdee
    # Protein should be around 2.0 * weight = 160g
    assert result.target_protein_g == 160
    assert result.target_fat_g >= int(round(0.8 * 80))
    assert result.target_carbs_g >= 50


def test_calculate_targets_muscle_gain():
    result = NutritionService.calculate_targets(
        gender="male",
        age=25,
        height_cm=180.0,
        weight_kg=80.0,
        activity_level="high",
        goal="gain"
    )
    # Target calories should be higher than TDEE for surplus
    assert result.target_calories > result.tdee
    assert result.target_protein_g == 160


def test_safe_floor_protection():
    # Very small female with aggressive deficit should not drop below 1200 kcal
    result = NutritionService.calculate_targets(
        gender="female",
        age=45,
        height_cm=145.0,
        weight_kg=40.0,
        activity_level="sedentary",
        goal="loss"
    )
    assert result.target_calories >= 1200


def test_validate_inputs():
    # Valid
    val = NutritionService.validate_inputs("male", 25, 180.0, 80.0, "moderate", "loss")
    assert val.is_valid is True

    # Invalid age
    val_age = NutritionService.validate_inputs("male", 5, 180.0, 80.0, "moderate", "loss")
    assert val_age.is_valid is False

    # Invalid height
    val_h = NutritionService.validate_inputs("male", 25, 50.0, 80.0, "moderate", "loss")
    assert val_h.is_valid is False

    # Invalid weight
    val_w = NutritionService.validate_inputs("male", 25, 180.0, 450.0, "moderate", "loss")
    assert val_w.is_valid is False

    # Invalid activity
    val_act = NutritionService.validate_inputs("male", 25, 180.0, 80.0, "super_extreme", "loss")
    assert val_act.is_valid is False
