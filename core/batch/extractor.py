import logging
from datetime import date

from core.constants import (
    DEFAULT_CATEGORY,
    DEFAULT_MEAL_TYPES,
    PENDING_CATEGORY,
    TRANSACTION_TYPES,
    TYPE_EXPENSE,
    TYPE_INCOME,
    TYPE_MEAL,
    TYPE_TRANSFER,
)
from core.diet.extractor import DietExtractor
from core.diet.meal_time import normalize_meal_time, resolve_meal_type
from core.expense.classifier import Classifier
from core.llm import LLMClient
from core.prompts import load_prompt

logger = logging.getLogger(__name__)


class BatchExtractor:
    """Turn a note into records via contextual blocks and domain pipelines."""

    BLOCK_FINANCE = "财务"
    BLOCK_MEAL = TYPE_MEAL
    BLOCK_TYPES = {BLOCK_FINANCE, BLOCK_MEAL}
    FINANCE_TYPES = set(TRANSACTION_TYPES)
    RECORD_TYPES = FINANCE_TYPES | {TYPE_MEAL}
    EXPENSE_CATEGORY_ALIASES = {"旅游": "旅行"}

    def __init__(self, config: dict):
        self.config = config
        self.expense_categories: dict = config.get("支出", {})
        self.income_categories: dict = config.get("收入", {})
        self.transfer_categories: dict = config.get("迁移", {})
        self.meal_types: list = config.get("diet", {}).get(
            "meal_types", list(DEFAULT_MEAL_TYPES)
        )
        self._llm = LLMClient(config.get("llm", {}))
        self._classifier = Classifier(config)
        self._diet_extractor = DietExtractor(config)

    def extract(self, text: str, default_date: str | None = None) -> dict:
        default_date = default_date or date.today().isoformat()
        try:
            raw = self._llm.invoke(self._build_block_prompt(default_date), text)
            blocks, rejected_blocks = self._normalize_blocks(raw, default_date)
        except Exception as e:
            logger.exception("BatchExtractor.extract failed")
            return {"status": "error", "records": [], "reasoning": str(e)}

        events = []
        rejected_events = []
        for block in blocks:
            if block["block_type"] == self.BLOCK_MEAL:
                events.append(self._meal_block_to_event(block))
                continue
            try:
                finance_raw = self._llm.invoke(
                    self._build_finance_prompt(block), block["text"]
                )
                block_events, block_rejected = self._normalize_events(
                    finance_raw,
                    block["date"],
                    defaults=block,
                )
                events.extend(block_events)
                rejected_events.extend(block_rejected)
            except Exception as e:
                rejected_events.append(
                    {"reason": f"财务块拆分失败：{e}", "record": block}
                )

        records, rejected_records = self._events_to_records(events)
        rejected = [*rejected_blocks, *rejected_events, *rejected_records]

        return {
            "status": "confirmed" if records else "empty",
            "records": records,
            "rejected_records": rejected,
            "reasoning": raw.get("reasoning", "") if isinstance(raw, dict) else "",
        }

    def _build_block_prompt(self, default_date: str) -> str:
        meal_types_str = "、".join(self.meal_types)
        return load_prompt(
            "batch_blocks.txt", default_date=default_date, meal_types=meal_types_str
        )

    def _build_finance_prompt(self, block: dict) -> str:
        category_lines = []
        for type_ in TRANSACTION_TYPES:
            categories = self.config.get(type_, {})
            rendered = "、".join(
                f"{main}（{'、'.join(subs)}）" if subs else main
                for main, subs in categories.items()
            )
            category_lines.append(f"- {type_}：{rendered}")
        context = block.get("category_hint") or block.get("context") or "未指定"
        return load_prompt(
            "batch_finance_events.txt",
            default_date=block["date"],
            category_context=context,
            categories="\n".join(category_lines),
        )

    def _meal_block_to_event(self, block: dict) -> dict:
        return {
            "event_type": TYPE_MEAL,
            "text": block["text"],
            "date": block["date"],
            "time": block.get("time", ""),
            "amount": None,
            "category_hint": "",
            "subcategory_hint": "",
            "meal_type_hint": block.get("meal_type_hint", ""),
            "confidence": 0.0,
            "reasoning": block.get("reasoning", ""),
        }

    def _events_to_records(self, events: list[dict]) -> tuple[list[dict], list[dict]]:
        records = []
        rejected = []
        for event in events:
            event_type = event["event_type"]
            try:
                if event_type == TYPE_EXPENSE:
                    records.append(self._expense_event_to_record(event))
                elif event_type == TYPE_MEAL:
                    records.append(self._meal_event_to_record(event))
                elif event_type in {TYPE_INCOME, TYPE_TRANSFER}:
                    records.append(self._simple_finance_event_to_record(event))
            except Exception as e:
                rejected.append(
                    {
                        "reason": f"{event_type} pipeline 失败：{e}",
                        "record": event,
                    }
                )
        return records, rejected

    def _expense_event_to_record(self, event: dict) -> dict:
        category_hint = self._resolve_expense_category_hint(
            event.get("category_hint", "")
        )
        subcategory_hint = str(event.get("subcategory_hint") or "").strip()
        categories = self.expense_categories.get(category_hint) or []
        valid_hint = bool(category_hint) and (
            (not categories and not subcategory_hint) or subcategory_hint in categories
        )
        if valid_hint:
            category = category_hint
            subcategory = subcategory_hint
            confidence = event.get("confidence", 0.0)
            reasoning = event.get("reasoning", "")
        else:
            result = self._classifier.classify(
                event["text"], category_hint=category_hint
            )
            if result.get("status") == "confirmed":
                category = result["category"]
                subcategory = result["subcategory"]
            else:
                category = PENDING_CATEGORY
                subcategory = PENDING_CATEGORY
            confidence = result.get("confidence", event.get("confidence", 0.0))
            reasoning = result.get("reasoning", event.get("reasoning", ""))

        return self._record(
            record_type=TYPE_EXPENSE,
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
        result = self._diet_extractor.extract(event["text"], event.get("time", ""))
        meal_type = resolve_meal_type(
            result.get("meal_type") or event.get("meal_type_hint"),
            event.get("time"),
        )
        foods = result.get("foods") or []
        confidence = result.get("confidence", 0.0)
        reasoning = result.get("reasoning", event.get("reasoning", ""))

        if result.get("status") == "error":
            meal_type = resolve_meal_type(
                event.get("meal_type_hint"), event.get("time")
            )
            foods = []
            reasoning = result.get("reasoning") or "饮食提取失败，请人工填写食物清单"

        return self._record(
            record_type=TYPE_MEAL,
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
        categories = (
            self.income_categories
            if event["event_type"] == TYPE_INCOME
            else self.transfer_categories
        )
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
        meal_type: str | None,
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
    def _pick_category(
        categories: dict, category_hint: str, subcategory_hint: str
    ) -> tuple[str, str]:
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

    def _resolve_expense_category_hint(self, value: str) -> str:
        hint = str(value or "").strip()
        hint = self.EXPENSE_CATEGORY_ALIASES.get(hint, hint)
        return hint if hint in self.expense_categories else ""

    def _normalize_blocks(
        self, raw: dict, default_date: str
    ) -> tuple[list[dict], list[dict]]:
        if not isinstance(raw, dict):
            return [], [{"reason": "LLM 输出不是 JSON 对象", "record": raw}]
        raw_blocks = raw.get("blocks", [])
        if not isinstance(raw_blocks, list):
            return [], [{"reason": "blocks 不是列表", "record": raw_blocks}]

        blocks = []
        rejected = []
        for item in raw_blocks:
            if not isinstance(item, dict):
                rejected.append({"reason": "语义块不是 JSON 对象", "record": item})
                continue
            block_type = str(item.get("block_type") or "").strip()
            if block_type not in self.BLOCK_TYPES:
                rejected.append(
                    {"reason": f"未知语义块类型：{block_type}", "record": item}
                )
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                rejected.append({"reason": "语义块缺少 text", "record": item})
                continue
            block_date = str(item.get("date") or default_date).strip()[:10]
            try:
                date.fromisoformat(block_date)
            except ValueError:
                block_date = default_date
            context = str(item.get("context") or "").strip()
            blocks.append(
                {
                    "block_type": block_type,
                    "text": text,
                    "date": block_date,
                    "time": normalize_meal_time(item.get("time")) or "",
                    "context": context,
                    "category_hint": self._resolve_expense_category_hint(context),
                    "meal_type_hint": str(item.get("meal_type_hint") or "").strip(),
                    "reasoning": str(item.get("reasoning") or "").strip(),
                }
            )
        return blocks, rejected

    def _normalize_events(
        self, raw: dict, default_date: str, defaults: dict | None = None
    ) -> tuple[list[dict], list[dict]]:
        defaults = defaults or {}
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
                rejected.append(
                    {"reason": f"未知事件类型：{event_type}", "record": item}
                )
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
                    rejected.append(
                        {"reason": "财务事件金额必须大于 0", "record": item}
                    )
                    continue
            else:
                amount = None

            event_date = str(
                item.get("date") or defaults.get("date") or default_date
            ).strip()[:10]
            try:
                date.fromisoformat(event_date)
            except ValueError:
                event_date = default_date

            events.append(
                {
                    "event_type": event_type,
                    "text": text,
                    "date": event_date,
                    "time": normalize_meal_time(
                        item.get("time") or defaults.get("time")
                    )
                    or "",
                    "amount": amount,
                    "category_hint": str(
                        item.get("category_hint") or defaults.get("category_hint") or ""
                    ).strip(),
                    "subcategory_hint": str(item.get("subcategory_hint") or "").strip(),
                    "meal_type_hint": str(
                        item.get("meal_type_hint")
                        or defaults.get("meal_type_hint")
                        or ""
                    ).strip(),
                    "confidence": self._normalize_confidence(item.get("confidence")),
                    "reasoning": str(item.get("reasoning") or "").strip(),
                }
            )
        return events, rejected

    @staticmethod
    def _normalize_confidence(value) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0
