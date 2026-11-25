"""SQLite persistence for personal notes and event dates."""

import re
from contextlib import closing
from sqlite3 import Connection
from typing import Literal

from backend.db import connect, placeholders
from backend.notes.models import EventDateRange, NoteCreate, NoteUpdate


class NoteNotFound(LookupError):
    pass


def _contains_folded(text: str | None, needle: str) -> bool:
    return text is not None and needle in text.casefold()


def _replace_event_dates(conn: Connection, note_id: int, dates: list[EventDateRange]) -> None:
    conn.execute("DELETE FROM note_event_dates WHERE note_id = ?", (note_id,))
    if dates:
        conn.executemany(
            "INSERT INTO note_event_dates (note_id, start_date, end_date) VALUES (?, ?, ?)",
            [(note_id, item.start_date.isoformat(), item.end_date.isoformat()) for item in dates],
        )


def _load_event_dates(conn: Connection, note_ids: list[int]) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {note_id: [] for note_id in note_ids}
    if not note_ids:
        return grouped
    marks = placeholders(len(note_ids))
    for row in conn.execute(
        f"""SELECT note_id, start_date, end_date FROM note_event_dates
            WHERE note_id IN ({marks})
            ORDER BY start_date, end_date, id""",
        note_ids,
    ):
        grouped[row["note_id"]].append(
            {"start_date": row["start_date"], "end_date": row["end_date"]}
        )
    return grouped


def _years(conn: Connection) -> list[str]:
    rows = conn.execute(
        """SELECT DISTINCT year FROM (
               SELECT substr(recorded_date, 1, 4) AS year FROM notes
               UNION
               SELECT substr(start_date, 1, 4) AS year FROM note_event_dates
               UNION
               SELECT substr(end_date, 1, 4) AS year FROM note_event_dates
           )
           WHERE year GLOB '[0-9][0-9][0-9][0-9]'
           ORDER BY year DESC"""
    ).fetchall()
    return [row["year"] for row in rows]


def _serialize_rows(conn: Connection, rows: list) -> list[dict]:
    event_map = _load_event_dates(conn, [row["id"] for row in rows])
    return [{**dict(row), "event_dates": event_map[row["id"]]} for row in rows]


def list_notes(
    *,
    year: str | None = None,
    q: str = "",
    sort: Literal["recorded", "event"] = "recorded",
) -> dict:
    filters: list[str] = []
    parameters: dict[str, object] = {}
    if year is not None and (year := year.strip()):
        if not re.fullmatch(r"\d{4}", year):
            raise ValueError("年份格式应为 YYYY")
        filters.append(
            """(substr(notes.recorded_date, 1, 4) = :year
                OR EXISTS (
                    SELECT 1 FROM note_event_dates d
                    WHERE d.note_id = notes.id
                      AND d.start_date <= :year_end
                      AND d.end_date >= :year_start
                ))"""
        )
        parameters["year"] = year
        parameters["year_start"] = f"{year}-01-01"
        parameters["year_end"] = f"{year}-12-31"
    if q := q.strip().casefold():
        filters.append("(contains_folded(notes.title, :q) OR contains_folded(notes.content, :q))")
        parameters["q"] = q

    clause = " WHERE " + " AND ".join(filters) if filters else ""
    order_by = (
        """COALESCE(
               (SELECT MIN(start_date) FROM note_event_dates WHERE note_id = notes.id),
               notes.recorded_date
           ) DESC, notes.recorded_date DESC, notes.id DESC"""
        if sort == "event"
        else "notes.recorded_date DESC, notes.id DESC"
    )

    with closing(connect(readonly=True)) as conn:
        conn.create_function("contains_folded", 2, _contains_folded, deterministic=True)
        rows = conn.execute(
            f"SELECT id, title, content, recorded_date, created_at, updated_at FROM notes"
            f"{clause} ORDER BY {order_by}",
            parameters,
        ).fetchall()
        return {"items": _serialize_rows(conn, rows), "years": _years(conn)}


def get_note(note_id: int) -> dict:
    with closing(connect(readonly=True)) as conn:
        row = conn.execute(
            "SELECT id, title, content, recorded_date, created_at, updated_at "
            "FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        if row is None:
            raise NoteNotFound("找不到这条随手记")
        return _serialize_rows(conn, [row])[0]


def create_note(body: NoteCreate) -> dict:
    with closing(connect()) as conn, conn:
        cursor = conn.execute(
            """INSERT INTO notes (title, content, recorded_date, created_at, updated_at)
               VALUES (?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))""",
            (body.title, body.content, body.recorded_date.isoformat()),
        )
        note_id = cursor.lastrowid
        assert note_id is not None
        _replace_event_dates(conn, note_id, body.event_dates)
    return get_note(note_id)


def update_note(note_id: int, body: NoteUpdate) -> dict:
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT id FROM notes WHERE id = ?", (note_id,)).fetchone()
        if existing is None:
            raise NoteNotFound("找不到这条随手记")
        fields = body.model_dump(exclude={"event_dates"}, exclude_unset=True)
        if "recorded_date" in fields:
            fields["recorded_date"] = fields["recorded_date"].isoformat()
        assignments = [f"{name} = :{name}" for name in fields]
        assignments.append("updated_at = datetime('now', 'localtime')")
        conn.execute(
            f"UPDATE notes SET {', '.join(assignments)} WHERE id = :id",
            {**fields, "id": note_id},
        )
        if body.event_dates is not None:
            _replace_event_dates(conn, note_id, body.event_dates)
    return get_note(note_id)


def delete_note(note_id: int) -> None:
    with closing(connect()) as conn, conn:
        deleted = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        if deleted.rowcount == 0:
            raise NoteNotFound("找不到这条随手记")
