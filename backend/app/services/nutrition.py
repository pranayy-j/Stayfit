"""Nutrition consumed for an amount of a calorie-chart food."""

from dataclasses import dataclass

from app.models import CalorieChartItem


@dataclass(frozen=True)
class ConsumedNutrition:
    calories: float
    protein_g: float
    carbs_g: float
    fats_g: float
    fibre_g: float


def consumed_nutrition(food: CalorieChartItem, metric_quantity: float) -> ConsumedNutrition:
    """Scale the chart's per-100 values to `metric_quantity` g or ml.

    When the item's unit differs from the chart's (ml of a food the chart keeps in g, or the
    reverse), 1 ml is taken as 1 g.
    """
    factor = metric_quantity / 100
    return ConsumedNutrition(
        calories=round(food.calories_per_100 * factor, 2),
        protein_g=round(food.protein_g_per_100 * factor, 2),
        carbs_g=round(food.carbs_g_per_100 * factor, 2),
        fats_g=round(food.fats_g_per_100 * factor, 2),
        fibre_g=round(food.fibre_g_per_100 * factor, 2),
    )
