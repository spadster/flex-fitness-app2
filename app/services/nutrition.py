from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple
from pathlib import Path
import json

from app.models import (
    Food,
    FoodMeasure,
    TrainerMeal,
    TrainerMealIngredient,
    MemberMeal,
    MemberMealIngredient,
    UNIT_TO_GRAMS,
)

WEIGHT_OUNCE_IN_GRAMS = 28.3495
FLUID_OUNCE_IN_ML = 29.5735

MEAL_SLOT_LABELS: Dict[str, str] = {
    "meal1": "Meal 1",
    "meal2": "Meal 2",
    "meal3": "Meal 3",
    "snacks": "Snacks",
}

DEFAULT_MACRO_RATIOS: Dict[str, float] = {
    "protein": 0.25,
    "carbs": 0.45,
    "fats": 0.30,
}

_VOLUME_CONVERSIONS_ML: Dict[str, float] = {
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "cup": 240.0,
    "cups": 240.0,
    "tbsp": 15.0,
    "tablespoon": 15.0,
    "tablespoons": 15.0,
    "tsp": 5.0,
    "teaspoon": 5.0,
    "teaspoons": 5.0,
    "fl oz": FLUID_OUNCE_IN_ML,
    "floz": FLUID_OUNCE_IN_ML,
    "fluid ounce": FLUID_OUNCE_IN_ML,
    "fluid ounces": FLUID_OUNCE_IN_ML,
}

_MEASURE_OVERRIDE_PATH = Path(__file__).resolve().parent.parent / "data" / "measure_overrides.json"
try:
    with _MEASURE_OVERRIDE_PATH.open("r", encoding="utf-8") as override_file:
        raw_overrides = json.load(override_file)
except FileNotFoundError:
    raw_overrides = {}
except json.JSONDecodeError:
    raw_overrides = {}

MEASURE_OVERRIDES: Dict[str, Dict[str, float]] = {}
for food_name, entries in raw_overrides.items():
    normalized_food = food_name.lower()
    MEASURE_OVERRIDES.setdefault(normalized_food, {})
    for entry in entries:
        unit_name = entry.get("measure_name")
        grams = entry.get("grams")
        if not unit_name or grams is None:
            continue
        MEASURE_OVERRIDES[normalized_food][unit_name.lower()] = float(grams)


def _normalize_unit(unit: Optional[str]) -> str:
    if not unit:
        return ""
    return unit.strip().lower()


def _candidate_units(unit: str) -> Iterable[str]:
    """Generate a set of candidate keys for matching FoodMeasure names."""
    base = _normalize_unit(unit)
    if not base:
        return []

    candidates = {base}
    if base.endswith("s"):
        candidates.add(base[:-1])
    candidates.add(base.replace(".", ""))
    candidates.add(base.replace(" ", ""))
    return candidates


def _serving_grams(food: Food) -> float:
    """Return the gram weight that nutrient data is based on for a food."""
    for value in (
        getattr(food, "serving_size", None),
        getattr(food, "grams_per_unit", None),
    ):
        if value and value > 0:
            return float(value)
    return 100.0


def scale_food_nutrients(food: Optional[Food], quantity_in_grams: float) -> Dict[str, float]:
    """Scale a food's macro profile to a quantity in grams, inferring calories when missing."""
    if not food:
        return {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fats": 0.0}

    grams = float(quantity_in_grams or 0.0)
    serving_grams = _serving_grams(food)
    factor = grams / serving_grams if serving_grams else 0.0

    base_protein = float(food.protein_g or 0.0)
    base_carbs = float(food.carbs_g or 0.0)
    base_fats = float(food.fats_g or 0.0)
    base_calories = float(food.calories or 0.0)

    macro_calories = (base_protein * 4) + (base_carbs * 4) + (base_fats * 9)
    adjusted_calories = base_calories

    if macro_calories:
        if not adjusted_calories:
            adjusted_calories = macro_calories
        else:
            ratio = adjusted_calories / macro_calories if macro_calories else 1
            if ratio > 2 or ratio < 0.5:
                adjusted_calories = macro_calories

    macro_scaled = macro_calories * factor if macro_calories else None
    calorie_value = macro_scaled if macro_scaled is not None else adjusted_calories * factor

    return {
        "calories": calorie_value,
        "protein": base_protein * factor,
        "carbs": base_carbs * factor,
        "fats": base_fats * factor,
    }


def derive_macro_targets(
    calorie_target: Optional[float],
    custom_protein_g: Optional[float],
    custom_carbs_g: Optional[float],
    custom_fats_g: Optional[float],
    *,
    ratio_overrides: Optional[Dict[str, Optional[float]]] = None,
    macro_mode: Optional[str] = None,
) -> Dict[str, Optional[float]]:
    """Return macro targets in grams based on calorie goal, explicit grams, or ratio overrides."""
    macros: Dict[str, Optional[float]] = {"calories": calorie_target}
    ratios = dict(DEFAULT_MACRO_RATIOS)
    if ratio_overrides:
        for key, value in ratio_overrides.items():
            if value is None:
                continue
            try:
                ratios[key] = max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                continue

    mode = (macro_mode or "").lower()
    use_percent_mode = mode == "percent"

    def _calc(macro_key: str, custom_value: Optional[float]) -> Optional[float]:
        ratio = ratios.get(macro_key, 0.0)
        divisor = 4 if macro_key in ("protein", "carbs") else 9
        if use_percent_mode:
            if not calorie_target or ratio <= 0:
                return None
            return round((calorie_target * ratio) / divisor, 1)
        if custom_value is not None:
            return round(custom_value, 1)
        if not calorie_target or ratio <= 0:
            return None
        return round((calorie_target * ratio) / divisor, 1)

    macros["protein"] = _calc("protein", custom_protein_g)
    macros["carbs"] = _calc("carbs", custom_carbs_g)
    macros["fats"] = _calc("fats", custom_fats_g)
    return macros


def find_measure(food_id: int, unit: str) -> Optional[FoodMeasure]:
    """Try to locate a FoodMeasure for a given unit name, ignoring pluralization and punctuation."""
    for candidate in _candidate_units(unit):
        if not candidate:
            continue
        measure = FoodMeasure.query.filter_by(food_id=food_id, measure_name=candidate).first()
        if measure and measure.grams:
            return measure
    return None


def _override_measure(food: Optional[Food], unit: str) -> Optional[float]:
    if not food:
        return None
    overrides = MEASURE_OVERRIDES.get((food.name or "").lower())
    if not overrides:
        return None
    for candidate in _candidate_units(unit):
        if not candidate:
            continue
        grams = overrides.get(candidate)
        if grams:
            return float(grams)
    return None


def convert_to_grams(
    food_id: int,
    quantity: float,
    unit: Optional[str],
    grams_override: Optional[float] = None,
    volume_override: Optional[float] = None,
) -> Tuple[float, Optional[float]]:
    """Convert a quantity and unit to grams (and optional volume in milliliters).

    When creating custom foods we may already know the gram weight and optional volume,
    so we allow overrides to short-circuit the lookup.
    """
    if quantity is None:
        raise ValueError("Quantity is required.")

    normalized_unit = _normalize_unit(unit)

    grams: Optional[float] = None
    volume_ml: Optional[float] = None

    food = Food.query.get(food_id)

    if grams_override is not None:
        grams = float(quantity) * float(grams_override)
    else:
        if not normalized_unit or normalized_unit == "g":
            grams = float(quantity)
        else:
            measure = find_measure(food_id, normalized_unit)
            if measure and measure.grams:
                grams = float(quantity) * float(measure.grams)
            elif normalized_unit in UNIT_TO_GRAMS:
                grams = float(quantity) * float(UNIT_TO_GRAMS[normalized_unit])
            else:
                override_grams = _override_measure(food, normalized_unit)
                if override_grams:
                    grams = float(quantity) * override_grams

    # Fallback to direct grams if no conversion rule found
    if grams is None:
        grams = float(quantity)
        normalized_unit = "g"

    # Attempt to compute volume information where possible
    if volume_override is not None:
        volume_ml = float(quantity) * float(volume_override)
    elif normalized_unit in _VOLUME_CONVERSIONS_ML:
        volume_ml = float(quantity) * _VOLUME_CONVERSIONS_ML[normalized_unit]

    return grams, volume_ml


def calculate_meal_macros(meal: TrainerMeal) -> Dict[str, float]:
    totals = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fats": 0.0}
    for ingredient in meal.ingredients:
        scaled = scale_food_nutrients(
            ingredient.food,
            float(ingredient.quantity_grams or 0.0)
        )
        totals["calories"] += scaled["calories"]
        totals["protein"] += scaled["protein"]
        totals["carbs"] += scaled["carbs"]
        totals["fats"] += scaled["fats"]

    return {key: round(value, 1) for key, value in totals.items()}


def serialize_ingredient(ingredient: TrainerMealIngredient) -> Dict[str, Optional[float]]:
    grams = float(ingredient.quantity_grams or 0.0)
    ounces = grams / WEIGHT_OUNCE_IN_GRAMS if grams else 0.0
    volume_ml = float(ingredient.volume_ml or 0.0)
    fluid_oz = volume_ml / FLUID_OUNCE_IN_ML if volume_ml else 0.0

    return {
        "id": ingredient.id,
        "food_id": ingredient.food_id,
        "name": ingredient.food.name if ingredient.food else "Unknown Food",
        "quantity": ingredient.quantity_value,
        "unit": ingredient.quantity_unit,
        "grams": round(grams, 1),
        "ounces": round(ounces, 2) if ounces else None,
        "volume_ml": round(volume_ml, 1) if volume_ml else None,
        "fluid_oz": round(fluid_oz, 2) if fluid_oz else None,
        "notes": ingredient.notes,
        "position": ingredient.position,
    }


def serialize_meal(meal) -> Dict[str, object]:
    owner = 'trainer'
    if isinstance(meal, MemberMeal):
        owner = 'member'
    return {
        "id": meal.id,
        "name": meal.name,
        "description": meal.description,
        "slot": meal.meal_slot,
        "slot_label": MEAL_SLOT_LABELS.get(meal.meal_slot, meal.meal_slot.title()),
        "member_id": getattr(meal, "member_id", None),
        "user_id": getattr(meal, "user_id", None),
        "owner": owner,
        "macros": calculate_meal_macros(meal),
        "ingredients": [serialize_ingredient(ing) for ing in meal.ingredients],
    }


def group_meals_by_slot(meals: Iterable[TrainerMeal]) -> Dict[str, list]:
    grouped = {slot: [] for slot in MEAL_SLOT_LABELS}
    for meal in meals:
        grouped.setdefault(meal.meal_slot, []).append(serialize_meal(meal))
    for items in grouped.values():
        items.sort(key=lambda m: m["name"].lower())
    return grouped
