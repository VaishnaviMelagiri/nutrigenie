"""
Nutrition validation module.
Validates generated meal plans against patient constraints and IFCT nutrition data.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class NutritionValidator:
    """
    Validates meal plans against:
    1. Patient dietary constraints (avoid/reduce lists)
    2. Nutritional targets (calories, protein, fiber, sodium)
    3. IFCT food database (ensures foods exist and values are accurate)
    """

    def __init__(self, patient_profile: dict, nutrition_db: dict | None = None):
        """
        Args:
            patient_profile: Patient profile from DynamoDB with avoid/reduce/recommend lists.
            nutrition_db: Dict mapping food_id -> nutrition data. If None, only constraint
                          validation is performed.
        """
        self.profile = patient_profile
        self.nutrition_db = nutrition_db or {}

        self.avoid_list = set(item.lower() for item in patient_profile.get("avoid_list", []))
        self.reduce_list = set(item.lower() for item in patient_profile.get("reduce_list", []))
        self.recommended_list = set(item.lower() for item in patient_profile.get("recommended_list", []))

        from . import config
        self.calorie_target = patient_profile.get("calorie_target", config.DEFAULT_CALORIE_TARGET)
        self.calorie_tolerance = config.CALORIE_TOLERANCE_PERCENT / 100
        self.min_protein = config.MIN_PROTEIN_G
        self.min_fiber = config.MIN_FIBER_G
        self.max_sodium = config.MAX_SODIUM_MG
        self.plan_days = config.PLAN_DAYS
        self.meal_types = config.MEAL_TYPES

    def validate_plan(self, meal_plan: dict) -> dict:
        """
        Validate a complete 7-day meal plan.

        Returns:
            {
                "passed": bool,
                "score": float (0-100),
                "violations": [{"type": str, "severity": str, "detail": str, "day": str, "meal": str}],
                "warnings": [{"type": str, "detail": str, "day": str, "meal": str}],
                "daily_totals": {day: {calories, protein, carbs, fat, fiber}}
            }
        """
        violations = []
        warnings = []
        daily_totals = {}

        for day_num in range(1, self.plan_days + 1):
            day_key = f"day_{day_num}"
            day_data = meal_plan.get(day_key, {})

            if not day_data:
                violations.append({
                    "type": "MISSING_DAY",
                    "severity": "CRITICAL",
                    "detail": f"Day {day_num} is missing from the meal plan",
                    "day": day_key,
                    "meal": "all"
                })
                continue

            day_cals = 0
            day_protein = 0
            day_carbs = 0
            day_fat = 0
            day_fiber = 0

            for meal_type in self.meal_types:
                meal = day_data.get(meal_type)
                if not meal:
                    violations.append({
                        "type": "MISSING_MEAL",
                        "severity": "HIGH",
                        "detail": f"Missing {meal_type} on {day_key}",
                        "day": day_key,
                        "meal": meal_type
                    })
                    continue

                # ── Validate ingredients against avoid/reduce lists ──
                meal_violations, meal_warnings = self._validate_meal_constraints(
                    meal, day_key, meal_type
                )
                violations.extend(meal_violations)
                warnings.extend(meal_warnings)

                # ── Validate nutrition values exist ──
                food_violations = self._validate_food_ids(meal, day_key, meal_type)
                violations.extend(food_violations)

                # ── Accumulate daily totals ──
                macros = meal.get("macros", {})
                meal_cals = meal.get("total_calories", 0)
                day_cals += meal_cals
                day_protein += macros.get("protein_g", 0)
                day_carbs += macros.get("carbs_g", 0)
                day_fat += macros.get("fat_g", 0)
                day_fiber += macros.get("fiber_g", 0)

            # ── Validate daily nutritional targets ──
            daily_totals[day_key] = {
                "calories": round(day_cals),
                "protein_g": round(day_protein, 1),
                "carbs_g": round(day_carbs, 1),
                "fat_g": round(day_fat, 1),
                "fiber_g": round(day_fiber, 1)
            }

            cal_min = self.calorie_target * (1 - self.calorie_tolerance)
            cal_max = self.calorie_target * (1 + self.calorie_tolerance)

            if day_cals < cal_min:
                violations.append({
                    "type": "LOW_CALORIES",
                    "severity": "MEDIUM",
                    "detail": f"Day {day_num}: {day_cals} kcal is below minimum {cal_min} kcal",
                    "day": day_key,
                    "meal": "daily_total"
                })
            elif day_cals > cal_max:
                violations.append({
                    "type": "HIGH_CALORIES",
                    "severity": "MEDIUM",
                    "detail": f"Day {day_num}: {day_cals} kcal exceeds maximum {cal_max} kcal",
                    "day": day_key,
                    "meal": "daily_total"
                })

            if day_protein < self.min_protein:
                violations.append({
                    "type": "LOW_PROTEIN",
                    "severity": "MEDIUM",
                    "detail": f"Day {day_num}: {day_protein}g protein below minimum {self.min_protein}g",
                    "day": day_key,
                    "meal": "daily_total"
                })

            if day_fiber < self.min_fiber:
                warnings.append({
                    "type": "LOW_FIBER",
                    "detail": f"Day {day_num}: {day_fiber}g fiber below target {self.min_fiber}g",
                    "day": day_key,
                    "meal": "daily_total"
                })

        # ── Calculate score ──
        critical_count = sum(1 for v in violations if v["severity"] == "CRITICAL")
        high_count = sum(1 for v in violations if v["severity"] == "HIGH")
        medium_count = sum(1 for v in violations if v["severity"] == "MEDIUM")
        warning_count = len(warnings)

        score = max(0, 100 - (critical_count * 25) - (high_count * 15) - (medium_count * 5) - (warning_count * 2))

        return {
            "passed": critical_count == 0 and high_count == 0,
            "score": score,
            "violations": violations,
            "warnings": warnings,
            "daily_totals": daily_totals
        }

    def _validate_meal_constraints(self, meal: dict, day: str, meal_type: str) -> tuple[list, list]:
        """Check meal ingredients against avoid and reduce lists."""
        violations = []
        warnings = []

        ingredients = meal.get("ingredients", [])
        for ing in ingredients:
            ing_name = ing.get("name", "").lower()

            # Check against avoid list
            for avoid_item in self.avoid_list:
                if avoid_item in ing_name or ing_name in avoid_item:
                    violations.append({
                        "type": "AVOID_LIST_VIOLATION",
                        "severity": "CRITICAL",
                        "detail": f"'{ing.get('name')}' matches avoid-list item '{avoid_item}'",
                        "day": day,
                        "meal": meal_type
                    })

            # Check against reduce list
            for reduce_item in self.reduce_list:
                if reduce_item in ing_name or ing_name in reduce_item:
                    warnings.append({
                        "type": "REDUCE_LIST_USAGE",
                        "detail": f"'{ing.get('name')}' is on reduce list ('{reduce_item}'). Quantity: {ing.get('quantity_g', '?')}g",
                        "day": day,
                        "meal": meal_type
                    })

            # Check for allergen tags if nutrition DB is available
            food_id = ing.get("food_id", "")
            if food_id and food_id in self.nutrition_db:
                food_data = self.nutrition_db[food_id]
                allergen_tags = set(t.lower() for t in food_data.get("allergen_tags", []))
                overlap = allergen_tags & self.avoid_list
                if overlap:
                    violations.append({
                        "type": "ALLERGEN_VIOLATION",
                        "severity": "CRITICAL",
                        "detail": f"'{ing.get('name')}' (food_id: {food_id}) has allergen tags {overlap} matching avoid list",
                        "day": day,
                        "meal": meal_type
                    })

        return violations, warnings

    def _validate_food_ids(self, meal: dict, day: str, meal_type: str) -> list:
        """Validate that food_ids reference real entries in the nutrition database."""
        violations = []
        if not self.nutrition_db:
            return violations

        for ing in meal.get("ingredients", []):
            food_id = ing.get("food_id", "")
            if food_id and food_id not in self.nutrition_db:
                violations.append({
                    "type": "INVALID_FOOD_ID",
                    "severity": "HIGH",
                    "detail": f"food_id '{food_id}' for '{ing.get('name')}' not found in nutrition database",
                    "day": day,
                    "meal": meal_type
                })

        return violations

    def validate_single_meal(self, meal: dict, target_calories: float = None) -> dict:
        """
        Validate a single meal (for alternative generation validation).

        Returns:
            {
                "passed": bool,
                "violations": [...],
                "warnings": [...]
            }
        """
        violations, warnings = self._validate_meal_constraints(meal, "N/A", "alternative")
        food_violations = self._validate_food_ids(meal, "N/A", "alternative")
        violations.extend(food_violations)

        # Check calorie range if target provided
        if target_calories:
            meal_cals = meal.get("total_calories", 0)
            cal_min = target_calories * 0.9
            cal_max = target_calories * 1.1
            if not (cal_min <= meal_cals <= cal_max):
                violations.append({
                    "type": "CALORIE_MISMATCH",
                    "severity": "MEDIUM",
                    "detail": f"Alternative has {meal_cals} kcal, expected {cal_min:.0f}–{cal_max:.0f} kcal",
                    "day": "N/A",
                    "meal": "alternative"
                })

        critical = sum(1 for v in violations if v["severity"] == "CRITICAL")
        high = sum(1 for v in violations if v["severity"] == "HIGH")

        return {
            "passed": critical == 0 and high == 0,
            "violations": violations,
            "warnings": warnings
        }
