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
        system_msg = self._build_prompt(categories).replace("{", "{{").replace("}", "}}")
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("human", "消费描述：{description}"),
        ])
        chain = (prompt | self._llm | JsonOutputParser()).with_retry(stop_after_attempt=2)

        try:
            data = chain.invoke({"description": description})
            return self._normalize(data)
        except Exception as e:
            return self._fallback(str(e))

    def extract_diet_info(self, description: str, meal_types: list) -> dict:
        """从饮食描述中提取结构化信息"""
        system_msg = self._build_diet_prompt(meal_types).replace("{", "{{").replace("}", "}}")
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("human", "饮食描述：{description}"),
        ])
        chain = (prompt | self._llm | JsonOutputParser()).with_retry(stop_after_attempt=2)

        try:
            data = chain.invoke({"description": description})
            return self._normalize_diet(data)
        except Exception as e:
            return self._diet_fallback(str(e))

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

    # ------------------------------------------------------------------
    # 饮食信息提取相关方法
    # ------------------------------------------------------------------

    def _build_diet_prompt(self, meal_types: list) -> str:
        """构建饮食信息提取的提示词"""
        meal_types_str = "、".join(meal_types)
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
    def _normalize_diet(data: dict) -> dict:
        """规范化饮食提取结果"""
        try:
            data["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        except (TypeError, ValueError):
            data["confidence"] = 0.0

        data.setdefault("meal_type", "其他")
        data.setdefault("food_name", "")
        data.setdefault("quantity", "")
        data.setdefault("reasoning", "")
        data.setdefault("error", False)
        
        return data

    @staticmethod
    def _diet_fallback(reason: str) -> dict:
        """饮食提取失败时的回退结果"""
        return {
            "meal_type": "其他",
            "food_name": "",
            "quantity": "",
            "confidence": 0.0,
            "reasoning": f"提取失败: {reason}",
            "error": True,
        }
