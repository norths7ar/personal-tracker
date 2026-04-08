from core.config import load_config
from core.llm import LLMClient


class DietExtractor:
    """从自然语言饮食描述中提取结构化信息（一餐多食物）。"""

    def __init__(self, config: dict):
        self.meal_types: list = config.get("diet", {}).get(
            "meal_types", ["早餐", "午餐", "晚餐", "零食", "其他"]
        )
        self.threshold: float = config.get("diet", {}).get("confidence_threshold", 0.7)
        self._llm = LLMClient(config.get("llm", {}))

    def extract(self, description: str) -> dict:
        """
        返回：
        {
            "status":     "confirmed" | "low_confidence" | "error",
            "meal_type":  str,
            "foods":      [{"food_name": str, "quantity": str}, ...],
            "confidence": float,
            "reasoning":  str,
        }
        """
        try:
            raw    = self._llm.invoke(self._build_prompt(), f"饮食描述：{description}")
            result = self._normalize(raw)
        except Exception as e:
            return self._fallback(str(e))

        status = "confirmed" if result["confidence"] >= self.threshold else "low_confidence"
        return {**result, "status": status}

    # ------------------------------------------------------------------

    def _build_prompt(self) -> str:
        meal_types_str = "、".join(self.meal_types)
        return f"""你是一个饮食信息提取助手。从用户的饮食描述中提取结构化信息。

可选的餐顿类型：{meal_types_str}

请从描述中提取以下信息：
1. meal_type（餐顿类型）：必须是以上餐顿类型之一
2. foods（食物列表）：将描述中提到的每种食物单独列出，每项包含 food_name 和 quantity

只输出纯 JSON 对象，不要有任何其他内容，格式如下：
{{
    "meal_type": "早餐",
    "foods": [
        {{"food_name": "豆浆", "quantity": "1杯"}},
        {{"food_name": "包子", "quantity": "2个"}},
        {{"food_name": "煮鸡蛋", "quantity": "1个"}}
    ],
    "confidence": 0.92,
    "reasoning": "一句话说明提取理由"
}}

说明：
- 如果无法确定餐顿类型，使用"其他"
- 如果无法确定某食物的份量，quantity 留空字符串
- foods 必须是列表，每种食物单独一项，不要合并
- confidence 是0.0-1.0的置信度
"""

    @staticmethod
    def _normalize(data: dict) -> dict:
        try:
            data["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        except (TypeError, ValueError):
            data["confidence"] = 0.0

        data.setdefault("meal_type", "其他")
        data.setdefault("reasoning", "")

        raw_foods = data.get("foods", [])
        if not isinstance(raw_foods, list):
            raw_foods = []
        foods = [
            {"food_name": str(f["food_name"]), "quantity": str(f.get("quantity") or "")}
            for f in raw_foods
            if isinstance(f, dict) and f.get("food_name")
        ]
        data["foods"] = foods if foods else [{"food_name": "", "quantity": ""}]
        return data

    @staticmethod
    def _fallback(reason: str) -> dict:
        return {
            "status":     "error",
            "meal_type":  "其他",
            "foods":      [{"food_name": "", "quantity": ""}],
            "confidence": 0.0,
            "reasoning":  f"提取失败: {reason}",
        }
