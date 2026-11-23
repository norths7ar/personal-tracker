from string import Template

from backend.constants import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MEAL_TYPES,
)
from backend.diet.store import display_text, normalize_ingredients, resolve_meal_type
from backend.llm import LLMClient


class DietExtractor:
    """从自然语言饮食描述中提取结构化信息（一餐多食物）。"""

    def __init__(self, config: dict, llm: LLMClient):
        self.meal_types: list = config.get("diet", {}).get("meal_types", list(DEFAULT_MEAL_TYPES))
        self.threshold: float = config.get("llm", {}).get(
            "confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD
        )
        self.prompts = config.get("prompts", {})
        self.prompts.setdefault("diet_extractor", DEFAULT_DIET_EXTRACTOR)
        self._llm = llm

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
            raw = self._llm.invoke(self._build_prompt(meal_time), f"饮食描述：{description}")
            result = self._normalize(raw, meal_time)
        except Exception as e:
            return self._fallback(str(e), meal_time)

        status = "confirmed" if result["confidence"] >= self.threshold else "low_confidence"
        return {**result, "status": status}

    def _build_prompt(self, meal_time: str) -> str:
        meal_types_str = "、".join(self.meal_types)
        return Template(self.prompts["diet_extractor"]).substitute(
            meal_types=meal_types_str,
            meal_time=meal_time,
        )

    @staticmethod
    def _normalize(data: dict, meal_time: str) -> dict:
        try:
            data["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        except TypeError, ValueError:
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
        data["foods"] = foods if foods else [{"food_name": "", "quantity": "", "ingredients": []}]
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


DEFAULT_DIET_EXTRACTOR = """你是一个饮食信息提取助手。从用户的饮食描述中提取结构化信息。

用餐时间：${meal_time}
常见餐顿标签示例：${meal_types}

请从描述中提取以下信息：
1. meal_type（可选餐顿标签）：原文明确出现早餐、午餐、晚餐、brunch、夜宵等标签时填写，否则留空字符串
2. foods（菜品列表）：将描述中提到的每种菜品或食物单独列出，每项包含：
   - food_name：简洁、稳定的菜品名称，去掉数量和商户等无关修饰，但保留烹饪方式，例如“3根烤鸡腿”写成“烤鸡腿”
   - quantity：原文中的份量
   - ingredients：该菜品能从名称或原文明确认出的主要食材，使用通用食材名

只输出纯 JSON 对象，不要有任何其他内容，格式如下：
{
    "meal_type": "",
    "foods": [
        {"food_name": "豆浆", "quantity": "1杯", "ingredients": ["黄豆"]},
        {"food_name": "包子", "quantity": "2个", "ingredients": []},
        {"food_name": "煮鸡蛋", "quantity": "1个", "ingredients": ["鸡蛋"]}
    ],
    "confidence": 0.92,
    "reasoning": "一句话说明提取理由"
}

说明：
- 不要仅为了填满字段而猜测餐顿标签；系统会根据时间另行做保守推断
- 如果无法确定某食物的份量，quantity 留空字符串
- foods 必须是列表，每种食物单独一项，不要合并
- ingredients 只记录能够确认的主要食材，不猜测馅料，不记录盐、油、酱油等普通调料
- 复合菜应拆出明确食材，例如“黄瓜火腿炒蛋”的 ingredients 是 ["黄瓜", "火腿", "鸡蛋"]
- 简单食物也记录其核心食材，例如“烤鸡腿”的 ingredients 是 ["鸡腿"]
- confidence 是0.0-1.0的置信度
"""
