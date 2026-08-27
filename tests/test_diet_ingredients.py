import sqlite3
import unittest
from unittest.mock import patch

import core.db as core_db
import core.diet.db as diet_db
from core.diet.ingredients import normalize_ingredients


class NoCloseConnection(core_db.Connection):
    def close(self):
        pass


class DietIngredientTest(unittest.TestCase):
    def setUp(self):
        self.raw = sqlite3.connect(":memory:")
        self.raw.row_factory = sqlite3.Row
        self.raw.execute("PRAGMA foreign_keys = ON")
        self.conn = NoCloseConnection(self.raw, "sqlite")
        self.patchers = [
            patch.object(core_db, "_connect", return_value=self.conn),
            patch.object(core_db, "get_backend", return_value="sqlite"),
            patch.object(core_db, "is_postgres", return_value=False),
            patch.object(diet_db, "_connect", return_value=self.conn),
            patch.object(diet_db, "is_postgres", return_value=False),
        ]
        for patcher in self.patchers:
            patcher.start()
        core_db.init_db()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.raw.close()

    def test_normalizes_ingredient_text_without_duplicates(self):
        self.assertEqual(
            normalize_ingredients("黄瓜、鸡蛋，黄瓜；火腿"),
            ["黄瓜", "鸡蛋", "火腿"],
        )

    def test_meal_foods_store_and_replace_ingredients_atomically(self):
        meal_id = diet_db.add_meal(
            "2026-08-27",
            "12:30",
            "午餐",
            "黄瓜火腿炒蛋",
            None,
            0.95,
            [
                {
                    "food_name": "黄瓜火腿炒蛋",
                    "quantity": "1份",
                    "ingredients": ["黄瓜", "火腿", "鸡蛋", "黄瓜"],
                }
            ],
        )

        meal = diet_db.get_meals()[0]
        self.assertEqual(meal["id"], meal_id)
        self.assertEqual(
            meal["foods"],
            [
                {
                    "food_name": "黄瓜火腿炒蛋",
                    "quantity": "1份",
                    "ingredients": ["黄瓜", "火腿", "鸡蛋"],
                }
            ],
        )

        diet_db.update_meal_with_foods(
            meal_id,
            [
                {
                    "food_name": "煮鸡蛋",
                    "quantity": "2个",
                    "ingredients": ["鸡蛋"],
                }
            ],
        )

        updated = diet_db.get_meals()[0]
        self.assertEqual(
            updated["foods"],
            [
                {
                    "food_name": "煮鸡蛋",
                    "quantity": "2个",
                    "ingredients": ["鸡蛋"],
                }
            ],
        )
        ingredient_names = [
            row["ingredient_name"]
            for row in self.raw.execute(
                "SELECT ingredient_name FROM diet_ingredients ORDER BY id"
            ).fetchall()
        ]
        self.assertEqual(ingredient_names, ["鸡蛋"])


if __name__ == "__main__":
    unittest.main()
