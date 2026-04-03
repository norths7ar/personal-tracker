import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

load_dotenv(Path(__file__).parent.parent / ".env")


class LLMClient:
    def __init__(self, llm_config: dict):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY not set in .env")

        llm = ChatOpenAI(
            model=llm_config.get("model", "deepseek-chat"),
            temperature=llm_config.get("temperature", 0.3),
            max_tokens=llm_config.get("max_tokens", 500),
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            timeout=30,
        )
        self._llm = llm

    def classify(self, description: str, categories: dict) -> dict:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self._build_prompt(categories)),
            ("human", "消费描述：{description}"),
        ])
        chain = (prompt | self._llm | JsonOutputParser()).with_retry(stop_after_attempt=2)

        try:
            data = chain.invoke({"description": description})
            return self._normalize(data)
        except Exception as e:
            return self._fallback(str(e))

    # ------------------------------------------------------------------
    def _build_prompt(self, categories: dict) -> str:
        lines = []
        for main, subs in categories.items():
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
                    "category": c.get("category", "其他"),
                    "subcategory": c.get("subcategory", "其他支出"),
                    "confidence": max(0.0, min(1.0, float(c.get("confidence", 0.0)))),
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
            "category": "其他",
            "subcategory": "其他支出",
            "confidence": 0.0,
            "reasoning": reason,
            "candidates": [],
            "error": True,
        }
