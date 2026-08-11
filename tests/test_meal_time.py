import unittest

from core.diet.meal_time import (
    infer_meal_type,
    normalize_meal_time,
    require_meal_time,
    resolve_meal_type,
)


class MealTimeTest(unittest.TestCase):
    def test_normalizes_valid_time(self):
        self.assertEqual(normalize_meal_time("8:05"), "08:05")
        self.assertEqual(require_meal_time("23:40"), "23:40")

    def test_rejects_blank_or_invalid_time(self):
        self.assertIsNone(normalize_meal_time(""))
        self.assertIsNone(normalize_meal_time("24:00"))
        self.assertIsNone(normalize_meal_time("12点30"))
        with self.assertRaises(ValueError):
            require_meal_time(None)

    def test_infers_only_conventional_meal_windows(self):
        self.assertEqual(infer_meal_type("08:30"), "早餐")
        self.assertEqual(infer_meal_type("12:30"), "午餐")
        self.assertEqual(infer_meal_type("19:15"), "晚餐")
        self.assertIsNone(infer_meal_type("10:30"))
        self.assertIsNone(infer_meal_type("15:00"))
        self.assertIsNone(infer_meal_type("22:30"))

    def test_explicit_label_overrides_time_inference(self):
        self.assertEqual(resolve_meal_type("brunch", "12:00"), "brunch")
        self.assertEqual(resolve_meal_type("", "12:00"), "午餐")


if __name__ == "__main__":
    unittest.main()
