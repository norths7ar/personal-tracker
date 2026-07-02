from datetime import date

from core.llm import LLMClient


class BatchExtractor:
    """Extract multiple expense and diet records from one natural-language note."""

    def __init__(self, config: dict):
        self.config = config
        self.expense_categories: dict = config.get("支出", {})
        self.income_categories: dict = config.get("收入", {})
        self.transfer_categories: dict = config.get("迁移", {})
        self.meal_types: list = config.get("diet", {}).get(
            "meal_types", ["早餐", "午餐", "晚餐", "零食", "其他"]
        )
        self._llm = LLMClient(config.get("llm", {}))

    def extract(self, text: str, default_date: str | None = None) -> dict:
        default_date = default_date or date.today().isoformat()
        try:
            raw = self._llm.invoke(self._build_prompt(default_date), text)
            records, rejected = self._normalize_records(raw)
        except Exception as e:
            return {"status": "error", "records": [], "reasoning": str(e)}

        return {
            "status": "confirmed" if records else "empty",
            "records": records,
            "raw_records": raw.get("records", []) if isinstance(raw, dict) else [],
            "rejected_records": rejected,
            "reasoning": raw.get("reasoning", "") if isinstance(raw, dict) else "",
        }

    def _build_prompt(self, default_date: str) -> str:
        return f"""你是 personal-tracker 的批量记录解析助手。把用户的一段自然语言拆成多条结构化记录。

默认日期：{default_date}

可选记录类型：
- 支出：有消费金额的支出
- 收入：收入、退款、红包、理财收益等
- 迁移：还款、投资、提现、充值等不参与收支结余的流水
- 饮食：吃了什么，不要求有金额

支出分类：
{self._format_categories(self.expense_categories)}

收入分类：
{self._format_categories(self.income_categories)}

迁移分类：
{self._format_categories(self.transfer_categories)}

饮食餐顿类型：{'、'.join(self.meal_types)}

只输出纯 JSON 对象，不要有任何其他内容，格式如下：
{{
  "records": [
    {{
      "record_type": "支出",
      "date": "YYYY-MM-DD",
      "time": "",
      "description": "麦当劳",
      "amount": 35.0,
      "category": "餐饮",
      "subcategory": "堂食",
      "meal_type": "",
      "foods": [],
      "notes": "",
      "confidence": 0.9,
      "reasoning": "一句话说明"
    }},
    {{
      "record_type": "饮食",
      "date": "YYYY-MM-DD",
      "time": "",
      "description": "中午吃了麦当劳",
      "amount": null,
      "category": "",
      "subcategory": "",
      "meal_type": "午餐",
      "foods": [
        {{"food_name": "麦当劳", "quantity": ""}}
      ],
      "notes": "",
      "confidence": 0.8,
      "reasoning": "一句话说明"
    }}
  ],
  "reasoning": "整体拆分说明"
}}

必须完整保留的信息：
- 输入中出现“早上/早餐”“中午/午餐”“晚上/晚餐”等多个餐段时，每个餐段都必须至少输出一条饮食记录。
- 输入中出现“花了/买了/支付/消费/元”等金额事件时，必须输出对应的支出记录。
- 如果一个餐段既有金额又有食物，必须输出两条：一条支出，一条饮食。

示例：
用户输入：
今天早上在家里吃了3个煮鸡蛋，1根黄瓜，适量坚果
中午去老乡鸡，花了45元，吃了杂粮饭、一根卤鸡腿、黄瓜火腿炒蛋、西蓝花炒肉和蒜蓉粉丝虾
晚上花了27元买了3根烤鸡腿，全吃了，然后又吃了200g蓝莓和1个橙子

应该输出 5 条记录：
- 饮食：早餐，煮鸡蛋/黄瓜/坚果
- 支出：午餐老乡鸡 45 元
- 饮食：午餐，杂粮饭/卤鸡腿/黄瓜火腿炒蛋/西蓝花炒肉/蒜蓉粉丝虾
- 支出：晚餐烤鸡腿 27 元
- 饮食：晚餐，烤鸡腿/蓝莓/橙子

规则：
- record_type 必须是 支出、收入、迁移、饮食 之一。
- 用户一句话中有多个事件时，拆成多条 records。
- 如果一个吃饭事件同时包含金额，可以同时输出一条支出和一条饮食。
- 支出、收入、迁移的 amount 必须是数字，单位为元；不确定金额时不要输出该财务记录。
- 饮食记录的 amount 填 null。
- category 和 subcategory 尽量从上面的分类中选择；没有子类别时 subcategory 填空字符串。
- 日期不明确时使用默认日期。
- time 不明确时填空字符串。
- foods 只用于饮食记录；每种食物单独一项，不确定份量时 quantity 为空字符串。
- notes 可以为空字符串。
- confidence 是 0.0 到 1.0。
"""

    @staticmethod
    def _format_categories(categories: dict) -> str:
        if not categories:
            return "- 其他"
        lines = []
        for main, subs in categories.items():
            lines.append(f"- {main}：{'、'.join(subs)}" if subs else f"- {main}")
        return "\n".join(lines)

    @staticmethod
    def _normalize_records(raw: dict) -> tuple[list[dict], list[dict]]:
        if not isinstance(raw, dict):
            return [], [{"reason": "LLM 输出不是 JSON 对象", "record": raw}]
        raw_records = raw.get("records", [])
        if not isinstance(raw_records, list):
            return [], [{"reason": "records 不是列表", "record": raw_records}]

        records = []
        rejected = []
        for item in raw_records:
            if not isinstance(item, dict):
                rejected.append({"reason": "记录不是 JSON 对象", "record": item})
                continue
            record_type = str(item.get("record_type") or "").strip()
            if record_type not in {"支出", "收入", "迁移", "饮食"}:
                rejected.append({"reason": f"未知记录类型：{record_type}", "record": item})
                continue

            amount = item.get("amount")
            if record_type != "饮食":
                try:
                    amount = round(float(amount), 2)
                except (TypeError, ValueError):
                    rejected.append({"reason": "财务记录缺少有效金额", "record": item})
                    continue
                if amount <= 0:
                    rejected.append({"reason": "财务记录金额必须大于 0", "record": item})
                    continue
            else:
                amount = None

            try:
                confidence = max(0.0, min(1.0, float(item.get("confidence", 0.0))))
            except (TypeError, ValueError):
                confidence = 0.0

            foods = item.get("foods", [])
            if not isinstance(foods, list):
                foods = []
            normalized_foods = []
            for food in foods:
                if isinstance(food, dict) and food.get("food_name"):
                    normalized_foods.append({
                        "food_name": str(food.get("food_name") or "").strip(),
                        "quantity": str(food.get("quantity") or "").strip(),
                    })

            records.append({
                "include": True,
                "record_type": record_type,
                "date": str(item.get("date") or date.today().isoformat())[:10],
                "time": str(item.get("time") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "amount": amount,
                "category": str(item.get("category") or "").strip(),
                "subcategory": str(item.get("subcategory") or "").strip(),
                "meal_type": str(item.get("meal_type") or "").strip(),
                "foods": normalized_foods,
                "notes": str(item.get("notes") or "").strip(),
                "confidence": confidence,
                "reasoning": str(item.get("reasoning") or "").strip(),
            })
        return records, rejected
