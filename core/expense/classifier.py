from core.config import load_config
from core.llm import LLMClient


class Classifier:
    def __init__(self, config: dict):
        self.categories: dict = config.get("支出", {})
        self.threshold: float = config.get("classifier", {}).get("confidence_threshold", 0.75)
        self._llm = LLMClient(config.get("llm", {}))

    def classify(self, description: str) -> dict:
        """
        调用 LLM 分类，返回：
        {
            "status": "confirmed" | "low_confidence" | "new_category" | "error",
            "category": str,
            "subcategory": str,
            "confidence": float,
            "reasoning": str,
            "candidates": [{"category", "subcategory", "confidence"}, ...]
        }
        """
        try:
            raw = self._llm.invoke(self._build_prompt(), f"消费描述：{description}")
            result = self._normalize(raw)
        except Exception as e:
            return self._fallback(str(e))

        category   = result["category"]
        subcategory = result["subcategory"]
        confidence  = result["confidence"]

        if not self._is_known(category, subcategory):
            status = "new_category"
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
        return f"""你是一个消费分类助手。根据消费描述，从以下类别中选出最合适的分类：

{cats}

只输出纯 JSON 对象，不要有任何其他内容，格式如下：
{{
    "category": "主类别",
    "subcategory": "子类别",
    "confidence": 0.92,
    "reasoning": "一句话说明理由",
    "candidates": [
        {{"category": "次选主类别", "subcategory": "次选子类别", "confidence": 0.05}},
        {{"category": "三选主类别", "subcategory": "三选子类别", "confidence": 0.03}}
    ]
}}

说明：
- category 和 subcategory 必须来自上面的类别列表；确实不匹配时用"其他"/"其他支出"
- 如果主类别没有子类别，subcategory 填与 category 相同的值
- candidates 填另外两个可能的分类，按置信度降序；没有合理备选就填空列表 []
"""

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
                    "category":    c.get("category", "其他"),
                    "subcategory": c.get("subcategory", "其他支出"),
                    "confidence":  max(0.0, min(1.0, float(c.get("confidence", 0.0)))),
                })
            except (TypeError, ValueError):
                pass
        data["candidates"] = candidates

        data.setdefault("category", "其他")
        data.setdefault("subcategory", "其他支出")
        data.setdefault("reasoning", "")
        return data

    @staticmethod
    def _fallback(reason: str) -> dict:
        return {
            "status":     "error",
            "category":   "其他",
            "subcategory": "其他支出",
            "confidence": 0.0,
            "reasoning":  reason,
            "candidates": [],
            "error":      True,
        }

    def _is_known(self, category: str, subcategory: str) -> bool:
        if category not in self.categories:
            return False
        subs = self.categories.get(category) or []
        return True if not subs else subcategory in subs
