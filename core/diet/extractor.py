from core.config import load_config
from core.llm import LLMClient


class DietExtractor:
    """从自然语言饮食描述中提取结构化信息。"""

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
            "status": "confirmed" | "low_confidence" | "error",
            "meal_type": str,
            "food_name": str,
            "quantity":  str,
            "confidence": float,
            "reasoning":  str,
        }
        """
        try:
            raw    = self._llm.invoke(self._build_prompt(), f"饮食描述：{description}")
            result = self._normalize(raw)
        except Exception as e:
            return self._fallback(str(e))

        confidence = result["confidence"]
        status = "confirmed" if confidence >= self.threshold else "low_confidence"
        return {**result, "status": status}

    # ------------------------------------------------------------------

    def _build_prompt(self) -> str:
        meal_types_str = "、".join(self.meal_types)
        return f"""你是一个饮食信息提取助手。从用户的饮食描述中提取结构化信息。

可选的餐顿类型：{meal_types_str}

请从描述中提取以下信息：
1. meal_type（餐顿类型）：必须是以上餐顿类型之一
2. food_name（主要食物名称）：提取主要的食物或菜品名称
3. quantity（份量描述）：描述食物的份量，如"1碗"、"2个"、"一杯"等

只输出纯 JSON 对象，不要有任何其他内容，格式如下：
{{
    "meal_type": "餐顿类型",
    "food_name": "主要食物名称",
    "quantity": "份量描述",
    "confidence": 0.92,
    "reasoning": "一句话说明提取理由"
}}

说明：
- 如果无法确定餐顿类型，使用"其他"
- 如果无法确定份量，quantity 留空字符串
- confidence 是0.0-1.0的置信度
"""

    @staticmethod
    def _normalize(data: dict) -> dict:
        try:
            data["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        except (TypeError, ValueError):
            data["confidence"] = 0.0
        data.setdefault("meal_type", "其他")
        data.setdefault("food_name", "")
        data.setdefault("quantity", "")
        data.setdefault("reasoning", "")
        return data

    @staticmethod
    def _fallback(reason: str) -> dict:
        return {
            "status":     "error",
            "meal_type":  "其他",
            "food_name":  "",
            "quantity":   "",
            "confidence": 0.0,
            "reasoning":  f"提取失败: {reason}",
        }
