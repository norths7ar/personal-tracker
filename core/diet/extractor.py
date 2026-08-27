from core.constants import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MEAL_TYPES,
)
from core.diet.ingredients import normalize_ingredients
from core.diet.meal_time import resolve_meal_type
from core.llm import LLMClient
from core.prompts import load_prompt
from core.text import display_text


class DietExtractor:
    """从自然语言饮食描述中提取结构化信息（一餐多食物）。"""

    def __init__(self, config: dict):
        self.meal_types: list = config.get("diet", {}).get(
            "meal_types", list(DEFAULT_MEAL_TYPES)
        )
        self.threshold: float = config.get("llm", {}).get(
            "confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD
        )
        self._llm = LLMClient(config.get("llm", {}))

    def extract(self, description: str, meal_time: str) -> dict:
        """
        返回：
        {
            "status":     "confirmed" | "low_confidence" | "error",
            "meal_type":  str | None,
            "foods":      [{"food_name": str, "quantity": str,
                              "ingredients": [str, ...]}, ...],
            "confidence": float,
            "reasoning":  str,
        }
        """
        try:
            raw = self._llm.invoke(
                self._build_prompt(meal_time), f"饮食描述：{description}"
            )
            result = self._normalize(raw, meal_time)
        except Exception as e:
            return self._fallback(str(e), meal_time)

        status = (
            "confirmed" if result["confidence"] >= self.threshold else "low_confidence"
        )
        return {**result, "status": status}

    # ------------------------------------------------------------------

    def _build_prompt(self, meal_time: str) -> str:
        meal_types_str = "、".join(self.meal_types)
        return load_prompt(
            "diet_extractor.txt",
            meal_types=meal_types_str,
            meal_time=meal_time,
        )

    @staticmethod
    def _normalize(data: dict, meal_time: str) -> dict:
        try:
            data["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        except (TypeError, ValueError):
            data["confidence"] = 0.0

        data["meal_type"] = resolve_meal_type(data.get("meal_type"), meal_time)
        data.setdefault("reasoning", "")

        raw_foods = data.get("foods", [])
        if not isinstance(raw_foods, list):
            raw_foods = []
        foods = [
            {
                "food_name": str(f["food_name"]),
                "quantity": display_text(f.get("quantity")),
                "ingredients": normalize_ingredients(f.get("ingredients")),
            }
            for f in raw_foods
            if isinstance(f, dict) and f.get("food_name")
        ]
        data["foods"] = (
            foods if foods else [{"food_name": "", "quantity": "", "ingredients": []}]
        )
        return data

    @staticmethod
    def _fallback(reason: str, meal_time: str) -> dict:
        return {
            "status": "error",
            "meal_type": resolve_meal_type(None, meal_time),
            "foods": [{"food_name": "", "quantity": "", "ingredients": []}],
            "confidence": 0.0,
            "reasoning": f"提取失败: {reason}",
        }
