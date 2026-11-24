"""Recent repeated wording and explicit pins, without model requests."""

from contextlib import closing
from datetime import date, timedelta

from backend.db import connect


def suggestions() -> list[dict]:
    since = (date.today() - timedelta(days=60)).isoformat()
    with closing(connect()) as conn:
        pinned = [
            row[0]
            for row in conn.execute("SELECT text FROM capture_phrases ORDER BY created_at, text")
        ]
        rows = conn.execute(
            """SELECT text, SUM(frequency) AS frequency FROM (
                 SELECT trim(f.food_name) AS text, COUNT(*) AS frequency
                 FROM diet_foods f JOIN diet_meals m ON m.id=f.meal_id
                 WHERE m.date >= ? AND m.date <= ? GROUP BY trim(f.food_name)
                 UNION ALL
                 SELECT trim(description) AS text, COUNT(*) AS frequency FROM transactions
                 WHERE type = '支出' AND date >= ? AND date <= ? GROUP BY trim(description) HAVING COUNT(*) >= 2
               ) GROUP BY text ORDER BY frequency DESC, text""",
            (since, date.today().isoformat(), since, date.today().isoformat()),
        ).fetchall()
    frequencies = {row["text"]: row["frequency"] for row in rows if 0 < len(row["text"]) <= 80}
    result = [{"text": text, "pinned": True, "count": frequencies.get(text, 0)} for text in pinned]
    result.extend(
        {"text": text, "pinned": False, "count": count}
        for text, count in frequencies.items()
        if text not in pinned
    )
    return result[:10]


def pin(text: str) -> list[dict]:
    text = text.strip()
    if not text or len(text) > 80:
        raise ValueError("常用词应为 1–80 个字符")
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT 1 FROM capture_phrases WHERE text=?", (text,)).fetchone():
            if conn.execute("SELECT COUNT(*) FROM capture_phrases").fetchone()[0] >= 10:
                raise ValueError("最多固定 10 项，请先取消一项")
            conn.execute("INSERT INTO capture_phrases(text) VALUES (?)", (text,))
    return suggestions()


def unpin(text: str) -> list[dict]:
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM capture_phrases WHERE text=?", (text.strip(),))
    return suggestions()
