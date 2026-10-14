from typing import Optional
from pydantic import BaseModel, Field


class NutritionCalculationResult(BaseModel):
    bmr: int = Field(description="Basal Metabolic Rate in kcal")
    tdee: int = Field(description="Total Daily Energy Expenditure in kcal")
    target_calories: int = Field(description="Target daily calories in kcal")
    target_protein_g: int = Field(description="Target protein in grams")
    target_fat_g: int = Field(description="Target fat in grams")
    target_carbs_g: int = Field(description="Target carbs in grams")


class NutritionValidationResult(BaseModel):
    is_valid: bool
    error_message: Optional[str] = None


class NutritionService:
    # Activity multipliers
    ACTIVITY_MULTIPLIERS = {
        "sedentary": 1.2,     # Минимальная
        "light": 1.375,       # Лёгкая
        "moderate": 1.55,     # Средняя
        "high": 1.725,        # Высокая
        "very_high": 1.9,     # Очень высокая
    }

    # Minimum safe calorie intakes
    MIN_CALORIES_MALE = 1500
    MIN_CALORIES_FEMALE = 1200

    @classmethod
    def validate_inputs(
        cls,
        gender: str,
        age: int,
        height_cm: float,
        weight_kg: float,
        activity_level: str,
        goal: str
    ) -> NutritionValidationResult:
        """Validate user profile inputs to protect against unreasonable or dangerous values."""
        if gender not in ("male", "female"):
            return NutritionValidationResult(is_valid=False, error_message="Пол должен быть 'male' или 'female'.")

        if not (14 <= age <= 100):
            return NutritionValidationResult(
                is_valid=False,
                error_message="Возраст должен быть в пределах от 14 до 100 лет."
            )

        if not (100.0 <= height_cm <= 250.0):
            return NutritionValidationResult(
                is_valid=False,
                error_message="Рост должен быть в пределах от 100 до 250 см."
            )

        if not (30.0 <= weight_kg <= 300.0):
            return NutritionValidationResult(
                is_valid=False,
                error_message="Вес должен быть в пределах от 30 до 300 кг."
            )

        if activity_level not in cls.ACTIVITY_MULTIPLIERS:
            return NutritionValidationResult(
                is_valid=False,
                error_message=f"Неизвестный уровень активности: {activity_level}."
            )

        if goal not in ("loss", "maintain", "gain"):
            return NutritionValidationResult(
                is_valid=False,
                error_message="Цель должна быть 'loss', 'maintain' или 'gain'."
            )

        return NutritionValidationResult(is_valid=True)

    @classmethod
    def calculate_bmr(cls, gender: str, weight_kg: float, height_cm: float, age: int) -> float:
        """Calculate BMR using the Mifflin-St Jeor equation."""
        # Men: 10 * weight + 6.25 * height - 5 * age + 5
        # Women: 10 * weight + 6.25 * height - 5 * age - 161
        base = (10.0 * weight_kg) + (6.25 * height_cm) - (5.0 * age)
        if gender == "male":
            return base + 5.0
        else:
            return base - 161.0

    @classmethod
    def calculate_tdee(cls, bmr: float, activity_level: str) -> float:
        """Calculate TDEE based on BMR and activity multiplier."""
        multiplier = cls.ACTIVITY_MULTIPLIERS.get(activity_level, 1.2)
        return bmr * multiplier

    @classmethod
    def calculate_targets(
        cls,
        gender: str,
        age: int,
        height_cm: float,
        weight_kg: float,
        activity_level: str,
        goal: str
    ) -> NutritionCalculationResult:
        """
        Calculate full nutrition targets including calories and macros.
        Protects against extreme deficits or unhealthy targets.
        """
        bmr_val = cls.calculate_bmr(gender, weight_kg, height_cm, age)
        tdee_val = cls.calculate_tdee(bmr_val, activity_level)

        min_allowed = cls.MIN_CALORIES_MALE if gender == "male" else cls.MIN_CALORIES_FEMALE

        if goal == "loss":
            # 20% healthy deficit
            target_cal = tdee_val * 0.80
            # Safe floor protection
            target_cal = max(target_cal, float(min_allowed))
            # Protein: 2.0g per kg body weight to preserve lean mass
            protein_g = 2.0 * weight_kg
            # Fat: 25% of total calories
            fat_calories = target_cal * 0.25
            fat_g = fat_calories / 9.0
            # Floor fat at 0.8g/kg
            fat_g = max(fat_g, 0.8 * weight_kg)
        elif goal == "gain":
            # 12-15% healthy surplus
            target_cal = tdee_val * 1.15
            # Protein: 1.8g - 2.0g per kg
            protein_g = 2.0 * weight_kg
            # Fat: 25% of total calories
            fat_g = (target_cal * 0.25) / 9.0
        else:  # maintain
            target_cal = tdee_val
            protein_g = 1.8 * weight_kg
            fat_g = (target_cal * 0.28) / 9.0

        # Remaining calories go to carbs (1g carb = 4 kcal, 1g protein = 4 kcal, 1g fat = 9 kcal)
        protein_cals = protein_g * 4.0
        fat_cals = fat_g * 9.0
        remaining_cals = target_cal - (protein_cals + fat_cals)

        # Carbs floor at 50g for metabolic health
        carbs_g = max(50.0, remaining_cals / 4.0)

        # Recalibrate total calories to match macros precisely
        total_calories = int(round(protein_g * 4.0 + fat_g * 9.0 + carbs_g * 4.0))

        return NutritionCalculationResult(
            bmr=int(round(bmr_val)),
            tdee=int(round(tdee_val)),
            target_calories=total_calories,
            target_protein_g=int(round(protein_g)),
            target_fat_g=int(round(fat_g)),
            target_carbs_g=int(round(carbs_g)),
        )
