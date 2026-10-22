from contextlib import closing

from core.db import _connect


def list_todos() -> list[dict]:
    with closing(_connect()) as connection:
        return [
            dict(row)
            for row in connection.execute("SELECT * FROM todos ORDER BY position, id")
        ]


def _get(connection, todo_id: int) -> dict:
    row = connection.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
    if row is None:
        raise LookupError("这件待办已不存在，请刷新列表。")
    return dict(row)


def create_todo(title: str, notes: str) -> dict:
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """INSERT INTO todos (title, notes, position)
               SELECT ?, ?, COALESCE(MAX(position), 0) + 1 FROM todos""",
            (title, notes),
        )
        return _get(connection, cursor.lastrowid)


def edit_todo(todo_id: int, title: str, notes: str) -> dict:
    with closing(_connect()) as connection, connection:
        connection.execute(
            "UPDATE todos SET title = ?, notes = ? WHERE id = ?",
            (title, notes, todo_id),
        )
        return _get(connection, todo_id)


def set_state(todo_id: int, status: str) -> dict:
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        current = _get(connection, todo_id)
        if current["status"] == status:
            return current
        # Replacing the current task is one operation, including concurrent tabs.
        if status == "active":
            connection.execute(
                "UPDATE todos SET status = 'pending' WHERE status = 'active'"
            )
        connection.execute(
            """UPDATE todos SET status = ?, completed_at =
               CASE WHEN ? = 'completed' THEN datetime('now', 'localtime') ELSE NULL END
               WHERE id = ?""",
            (status, status, todo_id),
        )
        return _get(connection, todo_id)


def move_todo(todo_id: int, direction: str) -> None:
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        current = _get(connection, todo_id)
        if current["status"] != "pending":
            raise ValueError("只能调整待做事项的顺序。")
        operator, order = ("<", "DESC") if direction == "up" else (">", "ASC")
        neighbor = connection.execute(
            f"""SELECT id, position FROM todos WHERE status = 'pending'
                AND position {operator} ? ORDER BY position {order} LIMIT 1""",
            (current["position"],),
        ).fetchone()
        if neighbor is not None:
            connection.executemany(
                "UPDATE todos SET position = ? WHERE id = ?",
                [
                    (neighbor["position"], todo_id),
                    (current["position"], neighbor["id"]),
                ],
            )


def delete_todo(todo_id: int) -> None:
    with closing(_connect()) as connection, connection:
        cursor = connection.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        if not cursor.rowcount:
            raise LookupError("这件待办已不存在，请刷新列表。")
