import sqlite3
from typing import Optional

from workload_analyzer.models import Role


class OverlapError(ValueError):
    """Raised when a time entry would overlap with an existing entry."""


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # --- Roles ---

    def create_role(self, name: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO roles (name) VALUES (?)", (name,)
        )
        return cur.lastrowid

    def list_roles(self) -> list[Role]:
        rows = self.conn.execute(
            "SELECT id, name FROM roles ORDER BY name"
        ).fetchall()
        return [Role(id=r["id"], name=r["name"]) for r in rows]

    def get_role(self, role_id: int) -> Optional[Role]:
        row = self.conn.execute(
            "SELECT id, name FROM roles WHERE id = ?", (role_id,)
        ).fetchone()
        if row is None:
            return None
        return Role(id=row["id"], name=row["name"])

    def rename_role(self, role_id: int, new_name: str) -> None:
        self.conn.execute(
            "UPDATE roles SET name = ? WHERE id = ?", (new_name, role_id)
        )

    def delete_role(self, role_id: int) -> None:
        self.conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))

    # --- Categories ---

    def create_category(
        self,
        name: str,
        color: str,
        role_id: int,
        active: bool = True,
        outlook_category_name: Optional[str] = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO categories (name, color, role_id, active, outlook_category_name)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, color, role_id, 1 if active else 0, outlook_category_name),
        )
        return cur.lastrowid

    def list_categories(self, active_only: bool = False) -> list["Category"]:
        from workload_analyzer.models import Category
        sql = "SELECT id, name, color, role_id, active, outlook_category_name FROM categories"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY name"
        rows = self.conn.execute(sql).fetchall()
        return [
            Category(
                id=r["id"], name=r["name"], color=r["color"],
                role_id=r["role_id"], active=bool(r["active"]),
                outlook_category_name=r["outlook_category_name"],
            )
            for r in rows
        ]

    def get_category(self, category_id: int) -> Optional["Category"]:
        from workload_analyzer.models import Category
        row = self.conn.execute(
            "SELECT id, name, color, role_id, active, outlook_category_name "
            "FROM categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        if row is None:
            return None
        return Category(
            id=row["id"], name=row["name"], color=row["color"],
            role_id=row["role_id"], active=bool(row["active"]),
            outlook_category_name=row["outlook_category_name"],
        )

    def update_category(
        self, category_id: int, name: str, color: str, role_id: int,
        active: bool, outlook_category_name: Optional[str],
    ) -> None:
        self.conn.execute(
            """
            UPDATE categories
            SET name = ?, color = ?, role_id = ?, active = ?, outlook_category_name = ?
            WHERE id = ?
            """,
            (name, color, role_id, 1 if active else 0, outlook_category_name, category_id),
        )

    def set_category_active(self, category_id: int, active: bool) -> None:
        self.conn.execute(
            "UPDATE categories SET active = ? WHERE id = ?",
            (1 if active else 0, category_id),
        )

    def find_category_by_outlook_name(self, outlook_name: str) -> Optional["Category"]:
        from workload_analyzer.models import Category
        row = self.conn.execute(
            "SELECT id, name, color, role_id, active, outlook_category_name "
            "FROM categories WHERE outlook_category_name = ?",
            (outlook_name,),
        ).fetchone()
        if row is None:
            return None
        return Category(
            id=row["id"], name=row["name"], color=row["color"],
            role_id=row["role_id"], active=bool(row["active"]),
            outlook_category_name=row["outlook_category_name"],
        )

    def delete_category(self, category_id: int) -> None:
        self.conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))

    # --- Time entries ---

    def get_open_entry(self) -> Optional["TimeEntry"]:
        from workload_analyzer.models import TimeEntry, EntrySource
        row = self.conn.execute(
            "SELECT id, category_id, start_ts, end_ts, source, comment "
            "FROM time_entries WHERE end_ts IS NULL"
        ).fetchone()
        if row is None:
            return None
        return TimeEntry(
            id=row["id"], category_id=row["category_id"],
            start_ts=row["start_ts"], end_ts=row["end_ts"],
            source=EntrySource(row["source"]), comment=row["comment"],
        )

    def start_entry(self, category_id: int, start_ts: int, source: "EntrySource") -> int:
        if self.get_open_entry() is not None:
            raise OverlapError("Another entry is currently open")
        self._check_no_overlap(start_ts, None, exclude_id=None)
        cur = self.conn.execute(
            "INSERT INTO time_entries (category_id, start_ts, end_ts, source) "
            "VALUES (?, ?, NULL, ?)",
            (category_id, start_ts, source.value),
        )
        return cur.lastrowid

    def close_entry(self, entry_id: int, end_ts: int) -> None:
        row = self.conn.execute(
            "SELECT start_ts FROM time_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"No entry {entry_id}")
        if end_ts <= row["start_ts"]:
            raise ValueError("end_ts must be after start_ts")
        self._check_no_overlap(row["start_ts"], end_ts, exclude_id=entry_id)
        self.conn.execute(
            "UPDATE time_entries SET end_ts = ?, modified_at = datetime('now') WHERE id = ?",
            (end_ts, entry_id),
        )

    def insert_closed_entry(
        self, category_id: int, start_ts: int, end_ts: int,
        source: "EntrySource", comment: Optional[str] = None,
    ) -> int:
        if end_ts <= start_ts:
            raise ValueError("end_ts must be after start_ts")
        self._check_no_overlap(start_ts, end_ts, exclude_id=None)
        cur = self.conn.execute(
            "INSERT INTO time_entries (category_id, start_ts, end_ts, source, comment) "
            "VALUES (?, ?, ?, ?, ?)",
            (category_id, start_ts, end_ts, source.value, comment),
        )
        return cur.lastrowid

    def update_entry(
        self, entry_id: int, category_id: int, start_ts: int, end_ts: Optional[int],
        comment: Optional[str],
    ) -> None:
        if end_ts is not None and end_ts <= start_ts:
            raise ValueError("end_ts must be after start_ts")
        self._check_no_overlap(start_ts, end_ts, exclude_id=entry_id)
        self.conn.execute(
            """
            UPDATE time_entries
            SET category_id = ?, start_ts = ?, end_ts = ?, comment = ?,
                modified_at = datetime('now')
            WHERE id = ?
            """,
            (category_id, start_ts, end_ts, comment, entry_id),
        )

    def delete_entry(self, entry_id: int) -> None:
        self.conn.execute("DELETE FROM time_entries WHERE id = ?", (entry_id,))

    def list_entries_between(self, from_ts: int, to_ts: int) -> list["TimeEntry"]:
        from workload_analyzer.models import TimeEntry, EntrySource
        rows = self.conn.execute(
            """
            SELECT id, category_id, start_ts, end_ts, source, comment
            FROM time_entries
            WHERE start_ts < ? AND (end_ts IS NULL OR end_ts > ?)
            ORDER BY start_ts
            """,
            (to_ts, from_ts),
        ).fetchall()
        return [
            TimeEntry(
                id=r["id"], category_id=r["category_id"],
                start_ts=r["start_ts"], end_ts=r["end_ts"],
                source=EntrySource(r["source"]), comment=r["comment"],
            )
            for r in rows
        ]

    def _check_no_overlap(
        self, start_ts: int, end_ts: Optional[int], exclude_id: Optional[int],
    ) -> None:
        # An overlap exists if any other entry has start < new_end AND (end IS NULL OR end > new_start).
        # If new_end is None (open entry), treat as +infinity.
        effective_end = end_ts if end_ts is not None else 2**63 - 1
        params: list = [effective_end, start_ts]
        sql = (
            "SELECT id FROM time_entries "
            "WHERE start_ts < ? "
            "AND (end_ts IS NULL OR end_ts > ?)"
        )
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        sql += " LIMIT 1"
        row = self.conn.execute(sql, params).fetchone()
        if row is not None:
            raise OverlapError(
                f"Entry [{start_ts}, {end_ts}] overlaps existing entry id={row['id']}"
            )

    # --- Settings ---

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return default
        return row["value"]

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
