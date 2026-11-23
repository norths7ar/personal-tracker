import contextlib
from string import Template

from backend.constants import DEFAULT_CATEGORY, DEFAULT_CONFIDENCE_THRESHOLD
from backend.llm import LLMClient


class Classifier:
    def __init__(self, config: dict, llm: LLMClient):
        self.categories: dict = config.get("支出", {})
        self.threshold: float = config.get("llm", {}).get(
            "confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD
        )
        self.prompts = config.get("prompts", {})
        self.prompts.setdefault("expense_classifier", DEFAULT_EXPENSE_CLASSIFIER)
        self._llm = llm

    def classify(self, description: str, category_hint: str | None = None) -> dict:
        """
        调用 LLM 分类，返回：
        {
            "status": "confirmed" | "low_confidence" | "error",
            "category": str,
            "subcategory": str,
            "confidence": float,
            "reasoning": str,
            "candidates": [{"category", "subcategory", "confidence"}, ...]
        }
        未知类别需要用户确认。
        """
        forced_category = category_hint if category_hint in self.categories else None
        try:
            raw = self._llm.invoke(
                self._build_prompt(forced_category),
                f"消费描述：{description}",
            )
            result = self._normalize(raw)
        except Exception as e:
            return self._fallback(str(e))

        if forced_category:
            result["category"] = forced_category
        if result.get("category") in self.categories:
            subcategories = self.categories[result["category"]] or []
            if not subcategories:
                result["subcategory"] = ""

        confidence = result["confidence"]

        if (
            not self._is_known(result["category"], result["subcategory"])
            or confidence < self.threshold
        ):
            status = "low_confidence"
        else:
            status = "confirmed"

        return {**result, "status": status}

    def _build_prompt(self, category_hint: str | None = None) -> str:
        lines = []
        categories = (
            {category_hint: self.categories[category_hint]} if category_hint else self.categories
        )
        for main, subs in categories.items():
            lines.append(f"- {main}：{'、'.join(subs)}" if subs else f"- {main}")
        cats = "\n".join(lines)
        return Template(self.prompts["expense_classifier"]).substitute(categories=cats)

    @staticmethod
    def _normalize(data: dict) -> dict:
        try:
            data["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        except TypeError, ValueError:
            data["confidence"] = 0.0

        candidates = []
        for c in data.get("candidates", []):
            with contextlib.suppress(TypeError, ValueError):
                candidates.append(
                    {
                        "category": c.get("category", DEFAULT_CATEGORY),
                        "subcategory": c.get("subcategory", c.get("category", DEFAULT_CATEGORY)),
                        "confidence": max(0.0, min(1.0, float(c.get("confidence", 0.0)))),
                    }
                )
        data["candidates"] = candidates

        data.setdefault("category", DEFAULT_CATEGORY)
        data.setdefault("subcategory", data.get("category", DEFAULT_CATEGORY))
        data.setdefault("reasoning", "")
        return data

    @staticmethod
    def _fallback(reason: str) -> dict:
        return {
            "status": "error",
            "category": DEFAULT_CATEGORY,
            "subcategory": DEFAULT_CATEGORY,
            "confidence": 0.0,
            "reasoning": reason,
            "candidates": [],
            "error": True,
        }

    def _is_known(self, category: str, subcategory: str) -> bool:
        if category not in self.categories:
            return False
        subs = self.categories.get(category) or []
        return True if not subs else subcategory in subs


DEFAULT_EXPENSE_CLASSIFIER = """你是一个消费分类助手。根据消费描述，从以下类别中选出最合适的分类：

${categories}

只输出纯 JSON 对象，不要有任何其他内容，格式如下：
{
    "category": "主类别",
    "subcategory": "子类别",
    "confidence": 0.92,
    "reasoning": "一句话说明理由",
    "candidates": [
        {"category": "次选主类别", "subcategory": "次选子类别", "confidence": 0.05},
        {"category": "三选主类别", "subcategory": "三选子类别", "confidence": 0.03}
    ]
}

说明：
- category 和 subcategory 必须来自上面的类别列表；只有确实属于杂项时才填"其他"/"其他"
- 如果无法判断合适分类，选择最接近的分类但把 confidence 降到 0.5 以下，并在 reasoning 说明不确定
- 如果主类别没有子类别，subcategory 填与 category 相同的值
- candidates 填另外两个可能的分类，按置信度降序；没有合理备选就填空列表 []
"""
