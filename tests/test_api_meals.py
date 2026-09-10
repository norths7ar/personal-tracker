import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.db as core_db
import core.diet.db as diet_db
from api.main import create_app


class NoCloseConnection(sqlite3.Connection):
    def close(self):
        pass


class MealBulkApiTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(
            ":memory:", check_same_thread=False, factory=NoCloseConnection
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.patchers = [
            patch.object(core_db, "_connect", return_value=self.conn),
            patch.object(diet_db, "_connect", return_value=self.conn),
            patch("api.main.init_db", side_effect=core_db.init_db),
            patch(
                "api.security.get_secret",
                side_effect=lambda name, default=None: (
                    "false" if name == "AUTH_ENABLED" else default
                ),
            ),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.client_context = TestClient(create_app())
        self.client = self.client_context.__enter__()
        self.ids = [
            diet_db.add_meal(
                "2026-09-07",
                "12:30",
                "午餐",
                description,
                "原备注",
                0.9,
                [
                    {
                        "food_name": description,
                        "quantity": "1份",
                        "ingredients": ["鸡蛋"],
                    }
                ],
            )
            for description in ("炒蛋", "蒸蛋")
        ]

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        for patcher in reversed(self.patchers):
            patcher.stop()
        sqlite3.Connection.close(self.conn)

    def test_bulk_update_preserves_unset_fields_and_foods(self):
        self.conn.execute(
            "UPDATE diet_meals SET time = NULL WHERE id = ?", self.ids[:1]
        )
        self.conn.commit()
        before = {row["id"]: row for row in diet_db.get_meals()}
        response = self.client.patch(
            "/api/meals/bulk-update",
            json={"ids": [*self.ids, self.ids[0]], "date": "2026-09-08", "notes": None},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"updated_count": 2})
        for row in diet_db.get_meals():
            original = before[row["id"]]
            self.assertEqual(row, {**original, "date": "2026-09-08", "notes": None})

    def test_stats_separate_food_names_and_distinct_record_ingredients(self):
        diet_db.add_meal(
            "2026-09-08",
            "15:00",
            None,
            "零食与蛋",
            None,
            None,
            [
                {"food_name": "炒蛋", "ingredients": ["鸡蛋", " 鸡蛋 "]},
                {"food_name": "蒸蛋", "ingredients": ["鸡蛋"]},
                {"food_name": "辣翅", "ingredients": ["鸡翅"]},
                {"food_name": "香辣翅中", "ingredients": ["鸡翅"]},
            ],
        )
        diet_db.add_meal(
            "2026-09-08",
            "19:00",
            "晚餐",
            "历史无食材",
            None,
            None,
            [{"food_name": "面包"}],
        )
        diet_db.add_meal(
            "2026-09-09",
            "12:00",
            "午餐",
            "范围外",
            None,
            None,
            [{"food_name": "鱼", "ingredients": ["鱼"]}],
        )
        response = self.client.get(
            "/api/meals/stats",
            params={"start_date": "2026-09-01", "end_date": "2026-09-08"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        stats = response.json()
        self.assertEqual(
            stats["ingredient_freq"],
            [
                {"ingredient_name": "鸡蛋", "count": 3},
                {"ingredient_name": "鸡翅", "count": 1},
            ],
        )
        self.assertEqual(stats["ingredient_record_count"], 3)
        foods = {row["food_name"]: row["count"] for row in stats["food_freq"]}
        self.assertEqual(foods["炒蛋"], 2)
        self.assertEqual(foods["辣翅"], 1)
        self.assertEqual(foods["香辣翅中"], 1)
        self.assertNotIn("鱼", foods)
        self.assertEqual(
            stats["daily_meals"],
            [
                {"date": "2026-09-07", "count": 2},
                {"date": "2026-09-08", "count": 2},
            ],
        )

    def test_stats_empty_period_has_no_ingredient_coverage(self):
        response = self.client.get(
            "/api/meals/stats",
            params={"start_date": "2026-08-01", "end_date": "2026-08-31"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        stats = response.json()
        self.assertEqual(stats["ingredient_freq"], [])
        self.assertEqual(stats["ingredient_record_count"], 0)
        self.assertEqual(stats["daily_meals"], [])

    def test_bulk_update_normalizes_time_and_clears_label(self):
        response = self.client.patch(
            "/api/meals/bulk-update",
            json={"ids": self.ids, "time": "9:05", "meal_type": None},
        )
        self.assertEqual(response.status_code, 200, response.text)
        for row in diet_db.get_meals():
            self.assertEqual(row["time"], "09:05")
            self.assertIsNone(row["meal_type"])

    def test_invalid_changes_are_rejected_without_writes(self):
        before = diet_db.get_meals()
        for changes in (
            {},
            {"time": "24:00"},
            {"time": "12:60"},
            {"time": None},
            {"date": None},
            {"date": "2026-02-30"},
            {"description": "替换"},
            {"foods": []},
            {"ingredients": []},
        ):
            with self.subTest(changes=changes):
                response = self.client.patch(
                    "/api/meals/bulk-update", json={"ids": self.ids, **changes}
                )
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(diet_db.get_meals(), before)

    def test_missing_id_fails_both_operations_atomically(self):
        before = diet_db.get_meals()
        response = self.client.patch(
            "/api/meals/bulk-update",
            json={"ids": [self.ids[0], 9999], "notes": "修改"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(diet_db.get_meals(), before)
        response = self.client.post(
            "/api/meals/bulk-delete", json={"ids": [self.ids[0], 9999]}
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(diet_db.get_meals(), before)

    def test_bulk_delete_cascades_and_counts_unique_ids(self):
        response = self.client.post(
            "/api/meals/bulk-delete", json={"ids": [*self.ids, self.ids[0]]}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"deleted_count": 2})
        for table in ("diet_meals", "diet_foods", "diet_ingredients"):
            self.assertEqual(
                self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0
            )

    def test_invalid_ids_and_unknown_delete_fields_are_rejected(self):
        for body in (
            {"ids": []},
            {"ids": [0]},
            {"ids": [True]},
            {"ids": self.ids, "date": None},
        ):
            response = self.client.post("/api/meals/bulk-delete", json=body)
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(len(diet_db.get_meals()), 2)


if __name__ == "__main__":
    unittest.main()
