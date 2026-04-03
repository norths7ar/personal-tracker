import yaml
from pathlib import Path

from .llm import LLMClient

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Classifier:
    def __init__(self, config: dict):
        self.categories: dict = config.get("支出", {})
        self.threshold: float = config.get("classifier", {}).get("confidence_threshold", 0.75)
        self._llm = LLMClient(config.get("llm", {}))

    def classify(self, description: str) -> dict:
        """
        调用 LLM 分类，返回结果：
        {
            "status": "confirmed" | "low_confidence" | "new_category" | "error",
            "category": str,
            "subcategory": str,
            "confidence": float,
            "reasoning": str,
            "candidates": [{"category", "subcategory", "confidence"}, ...]
        }

        - confirmed:      置信度达标且类别已知，可直接保存
        - low_confidence: 置信度低于阈值，需用户从候选中确认
        - new_category:   LLM 返回的类别不在 config.yaml 中，询问是否新建
        - error:          LLM 调用或解析失败
        """
        result = self._llm.classify(description, self.categories)

        if result.get("error"):
            return {**result, "status": "error"}

        category = result["category"]
        subcategory = result["subcategory"]
        confidence = result["confidence"]

        if not self._is_known(category, subcategory):
            status = "new_category"
        elif confidence < self.threshold:
            status = "low_confidence"
        else:
            status = "confirmed"

        return {**result, "status": status}

    def _is_known(self, category: str, subcategory: str) -> bool:
        if category not in self.categories:
            return False
        subs = self.categories.get(category) or []
        if not subs:
            return True  # 无子类定义，主类匹配即视为已知
        return subcategory in subs
