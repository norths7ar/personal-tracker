import logging
from contextlib import closing
from datetime import date
from string import Template

from backend.constants import (
    DEFAULT_CATEGORY,
    DEFAULT_MEAL_TYPES,
    PENDING_CATEGORY,
    TRANSACTION_TYPES,
    TYPE_EXPENSE,
    TYPE_INCOME,
    TYPE_MEAL,
    TYPE_TRANSFER,
)
from backend.db import connect, hash_payload
from backend.diet.extractor import DietExtractor
from backend.diet.store import insert_meal, normalize_meal_time, resolve_meal_type
from backend.ledger.classifier import Classifier
from backend.ledger.transactions import insert_transaction
from backend.llm import LLMClient

logger = logging.getLogger(__name__)


class BatchExtractor:
    """Turn a note into records via contextual blocks and domain pipelines."""

    BLOCK_FINANCE = "财务"
    BLOCK_MEAL = TYPE_MEAL
    BLOCK_TYPES = {BLOCK_FINANCE, BLOCK_MEAL}
    FINANCE_TYPES = set(TRANSACTION_TYPES)
    RECORD_TYPES = FINANCE_TYPES | {TYPE_MEAL}
    EXPENSE_CATEGORY_ALIASES = {"旅游": "旅行"}

    def __init__(self, config: dict, llm: LLMClient):
        self.config = config
        self.expense_categories: dict = config.get("支出", {})
        self.income_categories: dict = config.get("收入", {})
        self.transfer_categories: dict = config.get("迁移", {})
        self.meal_types: list = config.get("diet", {}).get("meal_types", list(DEFAULT_MEAL_TYPES))
        self.prompts = config.get("prompts", {})
        self.prompts.setdefault("batch_blocks", DEFAULT_BATCH_BLOCKS)
        self.prompts.setdefault("batch_finance_events", DEFAULT_BATCH_FINANCE_EVENTS)
        self._llm = llm
        self._classifier = Classifier(config, llm)
        self._diet_extractor = DietExtractor(config, llm)

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
                finance_raw = self._llm.invoke(self._build_finance_prompt(block), block["text"])
                block_events, block_rejected = self._normalize_events(
                    finance_raw,
                    block["date"],
                    defaults=block,
                )
                events.extend(block_events)
                rejected_events.extend(block_rejected)
            except Exception as e:
                rejected_events.append({"reason": f"财务块拆分失败：{e}", "record": block})

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
        return Template(self.prompts["batch_blocks"]).substitute(
            default_date=default_date, meal_types=meal_types_str
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
        return Template(self.prompts["batch_finance_events"]).substitute(
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
        category_hint = self._resolve_expense_category_hint(event.get("category_hint", ""))
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
            result = self._classifier.classify(event["text"], category_hint=category_hint)
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
            meal_type = resolve_meal_type(event.get("meal_type_hint"), event.get("time"))
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

    def _normalize_blocks(self, raw: dict, default_date: str) -> tuple[list[dict], list[dict]]:
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
                rejected.append({"reason": f"未知语义块类型：{block_type}", "record": item})
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
                except TypeError, ValueError:
                    rejected.append({"reason": "财务事件缺少有效金额", "record": item})
                    continue
                if amount <= 0:
                    rejected.append({"reason": "财务事件金额必须大于 0", "record": item})
                    continue
            else:
                amount = None

            event_date = str(item.get("date") or defaults.get("date") or default_date).strip()[:10]
            try:
                date.fromisoformat(event_date)
            except ValueError:
                event_date = default_date

            events.append(
                {
                    "event_type": event_type,
                    "text": text,
                    "date": event_date,
                    "time": normalize_meal_time(item.get("time") or defaults.get("time")) or "",
                    "amount": amount,
                    "category_hint": str(
                        item.get("category_hint") or defaults.get("category_hint") or ""
                    ).strip(),
                    "subcategory_hint": str(item.get("subcategory_hint") or "").strip(),
                    "meal_type_hint": str(
                        item.get("meal_type_hint") or defaults.get("meal_type_hint") or ""
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
        except TypeError, ValueError:
            return 0.0


DEFAULT_BATCH_BLOCKS = """你是 personal-tracker 的第一阶段语义分组助手。只把用户输入分成“财务”和“饮食”语义块，并保留上层语境；不要在这一阶段按每个金额拆成原子事件，也不要做最终分类。

默认日期：${default_date}

只输出纯 JSON 对象，不要有任何其他内容：
{
  "blocks": [
    {
      "block_type": "财务",
      "text": "火车票上海到镇江360，镇江到丹阳42",
      "context": "旅游",
      "date": "YYYY-MM-DD",
      "time": "",
      "meal_type_hint": "",
      "reasoning": "这是旅游框内的一组财务描述"
    },
    {
      "block_type": "饮食",
      "text": "中午吃了杂粮饭和鸡腿",
      "context": "",
      "date": "YYYY-MM-DD",
      "time": "12:00",
      "meal_type_hint": "午餐",
      "reasoning": "这是饮食内容"
    }
  ],
  "reasoning": "整体分组说明"
}

分组原则：
- 财务块包含支出、收入或账户迁移；饮食块只描述实际吃下或喝下的东西。
- 第一阶段要保留同一标题、括号、方框或段落下的共同语境。例如“以下框内为旅游：【火车票…… 打车……】”必须输出 context="旅游" 的一个财务块，不能让后续金额脱离“旅游”。
- 同一语境下连续的同类内容尽量保留在一个块中，具体金额和项目留给下一阶段拆分。
- “中午去老乡鸡花了45元，吃了杂粮饭和鸡腿”拆成一个财务块和一个饮食块。
- “晚上花27元买3根烤鸡腿，全吃了”也拆成财务块和饮食块。
- 日期不明确时使用默认日期。
- 饮食块应尽量给出 HH:MM 时间。明确时刻直接使用；早上/早餐、中午/午餐、下午、晚上/晚餐可近似为 08:00/12:00/15:00/19:00；完全没有时间线索填空字符串。
- meal_type_hint 只在原文明示餐顿标签时填写。常见标签：${meal_types}
- 保留所有内容；不确定时也不要丢弃语义块。
"""

DEFAULT_BATCH_FINANCE_EVENTS = """你是 personal-tracker 的第二阶段财务事件拆分助手。输入已经确定是一个财务语义块；现在把它拆成可独立记账的支出、收入或迁移事件，并继承上层语境。

默认日期：${default_date}
上层语境：${category_context}

可用分类：
${categories}

只输出纯 JSON 对象，不要有任何其他内容：
{
  "events": [
    {
      "event_type": "支出",
      "text": "上海到镇江火车票",
      "date": "YYYY-MM-DD",
      "amount": 360.0,
      "category_hint": "旅行",
      "subcategory_hint": "旅行交通",
      "confidence": 0.95,
      "reasoning": "一句话说明"
    }
  ],
  "reasoning": "本块拆分说明"
}

拆分原则：
- 出现多个明确、可分别记账的金额时拆成多条事件；加法表达式中的每个金额若对应同一笼统项目且无法分别命名，可以合并为一条并计算总额，不能漏算。
- amount 必须是大于 0 的数字，单位元。不要把人数、日期、数量当金额。
- event_type 只能是“支出”“收入”“迁移”。退款是收入；还款、投资、提现、充值和账户间转移是迁移。
- category_hint 和 subcategory_hint 必须来自可用分类。上层语境若能映射到主类别，所有子事件都必须继承该主类别；例如“旅游”对应“旅行”，其中火车票、打车、吃饭仍属于“旅行”，再选择旅行下的子类别。
- confidence 表示这条财务类型与分类判断的可信度，范围 0 到 1。
- text 应保留足够语义以供后续分类，不要只写“费用”或金额。
- 日期不明确时使用默认日期。
- 保留所有可识别的财务事件；不确定分类时降低判断强度，但不要丢弃。
"""


class BatchSubmissionConflict(ValueError):
    pass


logger = logging.getLogger(__name__)


def save_batch(submission_id: str, records: list[dict]) -> dict:
    """Save one reviewed batch atomically and make retries idempotent."""
    submission_id = str(submission_id or "").strip()
    if not submission_id:
        raise ValueError("批次缺少 submission_id")
    if not records:
        raise ValueError("批次没有可保存记录")

    payload_hash = hash_payload(records)
    with closing(connect()) as conn:
        try:
            inserted = conn.execute(
                """INSERT INTO batch_submissions
                   (submission_id, payload_hash, record_count)
                   VALUES (?, ?, ?)
                   ON CONFLICT(submission_id) DO NOTHING""",
                (submission_id, payload_hash, len(records)),
            )
            if inserted.rowcount == 0:
                existing = conn.execute(
                    """SELECT payload_hash, record_count FROM batch_submissions
                       WHERE submission_id = ?""",
                    (submission_id,),
                ).fetchone()
                if existing is None or existing["payload_hash"] != payload_hash:
                    logger.warning("batch submission conflict submission_id=%s", submission_id)
                    raise BatchSubmissionConflict("同一批次已使用不同内容保存")
                logger.info(
                    "batch duplicate ignored submission_id=%s record_count=%s",
                    submission_id,
                    existing["record_count"],
                )
                return {
                    "saved_count": int(existing["record_count"]),
                    "duplicate": True,
                }

            for record in records:
                _insert_record(conn, record)
            conn.commit()
            logger.info(
                "batch saved submission_id=%s record_count=%s",
                submission_id,
                len(records),
            )
        except Exception:
            conn.rollback()
            raise

    return {"saved_count": len(records), "duplicate": False}


def _insert_record(conn, record: dict) -> int:
    record_type = str(record.get("record_type") or "").strip()
    if record_type == TYPE_MEAL:
        return insert_meal(
            conn,
            date=str(record.get("date") or "").strip(),
            time=str(record.get("time") or "").strip(),
            meal_type=record.get("meal_type"),
            description=str(record.get("description") or "").strip(),
            notes=record.get("notes"),
            confidence=record.get("confidence"),
            foods=record.get("foods") or [],
        )
    if record_type not in TRANSACTION_TYPES:
        raise ValueError(f"不支持的批量记录类型：{record_type}")
    return insert_transaction(
        conn,
        record_type,
        str(record.get("description") or "").strip(),
        float(record.get("amount")),
        str(record.get("date") or "").strip(),
        category=record.get("category"),
        subcategory=record.get("subcategory"),
        notes=record.get("notes"),
        confidence=record.get("confidence"),
        reviewed=bool(record.get("reviewed")),
    )
