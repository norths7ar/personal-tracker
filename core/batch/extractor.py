from datetime import date

from core.constants import DEFAULT_CATEGORY, DEFAULT_MEAL_TYPE
from core.diet.extractor import DietExtractor
from core.expense.classifier import Classifier
from core.llm import LLMClient
from core.prompts import load_prompt


class BatchExtractor:
    """Turn one natural-language note into records via event extraction + pipelines."""

    FINANCE_TYPES = {"支出", "收入", "迁移"}
    RECORD_TYPES = FINANCE_TYPES | {"饮食"}

    def __init__(self, config: dict):
        self.config = config
        self.expense_categories: dict = config.get("支出", {})
        self.income_categories: dict = config.get("收入", {})
        self.transfer_categories: dict = config.get("迁移", {})
        self.meal_types: list = config.get("diet", {}).get(
            "meal_types", ["早餐", "午餐", "晚餐", "零食", DEFAULT_MEAL_TYPE]
        )
        self._llm = LLMClient(config.get("llm", {}))
        self._classifier = Classifier(config)
        self._diet_extractor = DietExtractor(config)

    def extract(self, text: str, default_date: str | None = None) -> dict:
        default_date = default_date or date.today().isoformat()
        try:
            raw = self._llm.invoke(self._build_event_prompt(default_date), text)
            events, rejected_events = self._normalize_events(raw, default_date)
        except Exception as e:
            return {"status": "error", "records": [], "reasoning": str(e)}

        records, rejected_records = self._events_to_records(events)
        rejected = [*rejected_events, *rejected_records]

        return {
            "status": "confirmed" if records else "empty",
            "records": records,
            "raw_records": raw.get("events", []) if isinstance(raw, dict) else [],
            "rejected_records": rejected,
            "reasoning": raw.get("reasoning", "") if isinstance(raw, dict) else "",
        }

    def _build_event_prompt(self, default_date: str) -> str:
        meal_types_str = "、".join(self.meal_types)
        return load_prompt("batch_events.txt", default_date=default_date, meal_types=meal_types_str)

    def _events_to_records(self, events: list[dict]) -> tuple[list[dict], list[dict]]:
        records = []
        rejected = []
        for event in events:
            event_type = event["event_type"]
            try:
                if event_type == "支出":
                    records.append(self._expense_event_to_record(event))
                elif event_type == "饮食":
                    records.append(self._meal_event_to_record(event))
                elif event_type in {"收入", "迁移"}:
                    records.append(self._simple_finance_event_to_record(event))
            except Exception as e:
                rejected.append({
                    "reason": f"{event_type} pipeline 失败：{e}",
                    "record": event,
                })
        return records, rejected

    def _valid_expense_subcategory(self, category: str, preferred: str) -> str:
        """Return preferred if it is valid for category, else fall back to DEFAULT_CATEGORY."""
        subs = self.expense_categories.get(category) or []
        if not subs:
            return preferred
        return preferred if preferred in subs else DEFAULT_CATEGORY

    def _expense_event_to_record(self, event: dict) -> dict:
        result = self._classifier.classify(event["text"])
        category = result.get("category") or event.get("category_hint") or DEFAULT_CATEGORY
        raw_sub = result.get("subcategory") or event.get("subcategory_hint") or ""
        subcategory = self._valid_expense_subcategory(category, raw_sub)
        confidence = result.get("confidence", event.get("confidence", 0.0))
        reasoning = result.get("reasoning", event.get("reasoning", ""))

        if result.get("status") == "error":
            category = event.get("category_hint") or DEFAULT_CATEGORY
            raw_sub = event.get("subcategory_hint") or ""
            subcategory = self._valid_expense_subcategory(category, raw_sub)
            reasoning = result.get("reasoning") or event.get("reasoning", "")

        return self._record(
            record_type="支出",
            event=event,
            amount=event["amount"],
            category=category,
            subcategory=subcategory,
            meal_type="",
            foods=[],
            confidence=confidence,
            reasoning=reasoning,
        )

    def _meal_event_to_record(self, event: dict) -> dict:
        result = self._diet_extractor.extract(event["text"])
        meal_type = result.get("meal_type") or event.get("meal_type_hint") or DEFAULT_MEAL_TYPE
        foods = result.get("foods") or []
        confidence = result.get("confidence", 0.0)
        reasoning = result.get("reasoning", event.get("reasoning", ""))

        if result.get("status") == "error":
            meal_type = event.get("meal_type_hint") or DEFAULT_MEAL_TYPE
            foods = [{"food_name": event["text"], "quantity": ""}]

        return self._record(
            record_type="饮食",
            event=event,
            amount=None,
            category="",
            subcategory="",
            meal_type=meal_type,
            foods=foods,
            confidence=confidence,
            reasoning=reasoning,
        )

    def _simple_finance_event_to_record(self, event: dict) -> dict:
        categories = self.income_categories if event["event_type"] == "收入" else self.transfer_categories
        category, subcategory = self._pick_category(
            categories,
            event.get("category_hint", ""),
            event.get("subcategory_hint", ""),
        )
        return self._record(
            record_type=event["event_type"],
            event=event,
            amount=event["amount"],
            category=category,
            subcategory=subcategory,
            meal_type="",
            foods=[],
            confidence=event.get("confidence", 0.0),
            reasoning=event.get("reasoning", ""),
        )

    @staticmethod
    def _record(
        record_type: str,
        event: dict,
        amount,
        category: str,
        subcategory: str,
        meal_type: str,
        foods: list[dict],
        confidence: float,
        reasoning: str,
    ) -> dict:
        return {
            "include": True,
            "record_type": record_type,
            "date": event["date"],
            "time": event.get("time", ""),
            "description": event["text"],
            "amount": amount,
            "category": category,
            "subcategory": subcategory,
            "meal_type": meal_type,
            "foods": foods,
            "notes": "",
            "confidence": confidence,
            "reasoning": reasoning,
        }

    @staticmethod
    def _pick_category(categories: dict, category_hint: str, subcategory_hint: str) -> tuple[str, str]:
        if category_hint in categories:
            subs = categories.get(category_hint) or []
            if not subs:
                return category_hint, ""
            if subcategory_hint in subs:
                return category_hint, subcategory_hint
            return category_hint, subs[0]
        if DEFAULT_CATEGORY in categories:
            return DEFAULT_CATEGORY, ""
        if categories:
            first = next(iter(categories))
            subs = categories.get(first) or []
            return first, subs[0] if subs else ""
        return DEFAULT_CATEGORY, ""

    def _normalize_events(self, raw: dict, default_date: str) -> tuple[list[dict], list[dict]]:
        if not isinstance(raw, dict):
            return [], [{"reason": "LLM 输出不是 JSON 对象", "record": raw}]
        raw_events = raw.get("events", [])
        if not isinstance(raw_events, list):
            return [], [{"reason": "events 不是列表", "record": raw_events}]

        events = []
        rejected = []
        for item in raw_events:
            if not isinstance(item, dict):
                rejected.append({"reason": "事件不是 JSON 对象", "record": item})
                continue

            event_type = str(item.get("event_type") or "").strip()
            if event_type not in self.RECORD_TYPES:
                rejected.append({"reason": f"未知事件类型：{event_type}", "record": item})
                continue

            text = str(item.get("text") or "").strip()
            if not text:
                rejected.append({"reason": "事件缺少 text", "record": item})
                continue

            amount = item.get("amount")
            if event_type in self.FINANCE_TYPES:
                try:
                    amount = round(float(amount), 2)
                except (TypeError, ValueError):
                    rejected.append({"reason": "财务事件缺少有效金额", "record": item})
                    continue
                if amount <= 0:
                    rejected.append({"reason": "财务事件金额必须大于 0", "record": item})
                    continue
            else:
                amount = None

            event_date = str(item.get("date") or default_date).strip()[:10]
            try:
                date.fromisoformat(event_date)
            except ValueError:
                event_date = default_date

            events.append({
                "event_type": event_type,
                "text": text,
                "date": event_date,
                "time": str(item.get("time") or "").strip(),
                "amount": amount,
                "category_hint": str(item.get("category_hint") or "").strip(),
                "subcategory_hint": str(item.get("subcategory_hint") or "").strip(),
                "meal_type_hint": str(item.get("meal_type_hint") or "").strip(),
                "linked_group": str(item.get("linked_group") or "").strip(),
                "confidence": 0.0,
                "reasoning": str(item.get("reasoning") or "").strip(),
            })
        return events, rejected
