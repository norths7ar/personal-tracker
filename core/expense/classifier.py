from core.constants import DEFAULT_CATEGORY
from core.llm import LLMClient
from core.prompts import load_prompt


class Classifier:
    def __init__(self, config: dict):
        self.categories: dict = config.get("支出", {})
        self.threshold: float = config.get("classifier", {}).get("confidence_threshold", 0.75)
        self._llm = LLMClient(config.get("llm", {}))

    def classify(self, description: str) -> dict:
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
        未知类别视为 low_confidence，由用户从 selectbox 中确认。
        """
        try:
            raw = self._llm.invoke(self._build_prompt(), f"消费描述：{description}")
            result = self._normalize(raw)
        except Exception as e:
            return self._fallback(str(e))

        confidence = result["confidence"]

        if not self._is_known(result["category"], result["subcategory"]):
            status = "new_category"  # page 1 handles this identically to low_confidence
        elif confidence < self.threshold:
            status = "low_confidence"
        else:
            status = "confirmed"

        return {**result, "status": status}

    # ------------------------------------------------------------------

    def _build_prompt(self) -> str:
        lines = []
        for main, subs in self.categories.items():
            lines.append(f"- {main}：{'、'.join(subs)}" if subs else f"- {main}")
        cats = "\n".join(lines)
        return load_prompt("expense_classifier.txt", categories=cats)

    @staticmethod
    def _normalize(data: dict) -> dict:
        try:
            data["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        except (TypeError, ValueError):
            data["confidence"] = 0.0

        candidates = []
        for c in data.get("candidates", []):
            try:
                candidates.append({
                    "category":    c.get("category", DEFAULT_CATEGORY),
                    "subcategory": c.get("subcategory", c.get("category", DEFAULT_CATEGORY)),
                    "confidence":  max(0.0, min(1.0, float(c.get("confidence", 0.0)))),
                })
            except (TypeError, ValueError):
                pass
        data["candidates"] = candidates

        data.setdefault("category", DEFAULT_CATEGORY)
        data.setdefault("subcategory", data.get("category", DEFAULT_CATEGORY))
        data.setdefault("reasoning", "")
        return data

    @staticmethod
    def _fallback(reason: str) -> dict:
        return {
            "status":      "error",
            "category":    DEFAULT_CATEGORY,
            "subcategory": DEFAULT_CATEGORY,
            "confidence":  0.0,
            "reasoning":   reason,
            "candidates":  [],
            "error":       True,
        }

    def _is_known(self, category: str, subcategory: str) -> bool:
        if category not in self.categories:
            return False
        subs = self.categories.get(category) or []
        return True if not subs else subcategory in subs
