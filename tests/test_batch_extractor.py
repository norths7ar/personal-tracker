import unittest

from core.batch.extractor import BatchExtractor


class ScriptedLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def invoke(self, prompt, text):
        self.calls.append((prompt, text))
        return self.responses.pop(0)


class RecordingClassifier:
    def __init__(self):
        self.calls = []

    def classify(self, description, category_hint=None):
        self.calls.append((description, category_hint))
        subcategory = "旅行交通" if "火车" in description else "美食特产"
        return {
            "status": "confirmed",
            "category": category_hint,
            "subcategory": subcategory,
            "confidence": 0.95,
            "reasoning": "constrained by trip context",
        }


class StubDietExtractor:
    def extract(self, description, meal_time):
        return {
            "status": "confirmed",
            "meal_type": "午餐",
            "foods": [{"food_name": description, "quantity": ""}],
            "confidence": 0.9,
            "reasoning": "meal block",
        }


class BatchExtractorTest(unittest.TestCase):
    def setUp(self):
        self.config = {
            "支出": {
                "旅行": ["景点门票", "美食特产", "酒店住宿", "旅行交通"],
                "餐饮": ["堂食"],
                "其他": ["其他"],
            },
            "收入": {"其他": []},
            "迁移": {"其他": []},
            "diet": {"meal_types": ["早餐", "午餐", "晚餐"]},
            "llm": {"confidence_threshold": 0.75},
        }

    def test_finance_events_inherit_parent_category_context(self):
        blocks = {
            "blocks": [
                {
                    "block_type": "财务",
                    "text": "上海到镇江火车票360；周六晚饭280+73",
                    "context": "旅游",
                    "date": "2026-08-30",
                }
            ],
            "reasoning": "one trip block",
        }
        events = {
            "events": [
                {
                    "event_type": "支出",
                    "text": "上海到镇江火车票",
                    "amount": 360,
                },
                {
                    "event_type": "支出",
                    "text": "周六晚饭",
                    "amount": 353,
                },
            ]
        }
        extractor = BatchExtractor(self.config)
        extractor._llm = ScriptedLLM(blocks, events)
        classifier = RecordingClassifier()
        extractor._classifier = classifier

        result = extractor.extract("以下框内为旅游：【……】", "2026-08-30")

        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(
            [record["category"] for record in result["records"]],
            ["旅行", "旅行"],
        )
        self.assertEqual(
            classifier.calls,
            [("上海到镇江火车票", "旅行"), ("周六晚饭", "旅行")],
        )

    def test_first_phase_keeps_finance_and_meal_pipelines_separate(self):
        blocks = {
            "blocks": [
                {
                    "block_type": "财务",
                    "text": "中午去老乡鸡花了45元",
                    "date": "2026-08-30",
                    "time": "12:00",
                    "linked_group": "lunch_1",
                },
                {
                    "block_type": "饮食",
                    "text": "中午吃了杂粮饭和鸡腿",
                    "date": "2026-08-30",
                    "time": "12:00",
                    "meal_type_hint": "午餐",
                    "linked_group": "lunch_1",
                },
            ]
        }
        events = {
            "events": [
                {
                    "event_type": "支出",
                    "text": "老乡鸡午餐",
                    "amount": 45,
                    "category_hint": "餐饮",
                    "subcategory_hint": "堂食",
                }
            ]
        }
        extractor = BatchExtractor(self.config)
        llm = ScriptedLLM(blocks, events)
        extractor._llm = llm
        classifier = RecordingClassifier()
        classifier.classify = lambda description, category_hint=None: {
            "status": "confirmed",
            "category": "餐饮",
            "subcategory": "堂食",
            "confidence": 0.95,
            "reasoning": "restaurant",
        }
        extractor._classifier = classifier
        extractor._diet_extractor = StubDietExtractor()

        result = extractor.extract("中午去老乡鸡花45，吃了杂粮饭和鸡腿")

        self.assertEqual(
            [record["record_type"] for record in result["records"]],
            ["支出", "饮食"],
        )
        self.assertEqual(len(llm.calls), 2)
        self.assertEqual(
            result["records"][1]["foods"][0]["food_name"], "中午吃了杂粮饭和鸡腿"
        )


if __name__ == "__main__":
    unittest.main()
