import os.path, sqlite3
from typing import List, Optional, Tuple

class ReasonsTable(object):
    def __init__(self, db: sqlite3.Connection, new: bool):
        self._db = db
        if new:
            self._db.execute("""
                CREATE TABLE reasons (
                    reason_id INTEGER PRIMARY KEY,
                    ban_id INTEGER NOT NULL,

                    reason_set_by TEXT NOT NULL,
                    reason_set_at INTEGER NOT NULL,
                    reason TEXT NOT NULL,

                    FOREIGN KEY (ban_id) REFERENCES bans(ban_id)
                )
            """)
    def set(self,
            ban_id: int,
            reason_set_by: str,
            reason_set_at: int,
            reason: str):
        self._db.execute("""
            INSERT INTO reasons (
                ban_id, reason_set_by, reason_set_at, reason
            )
            VALUES (?, ?, ?, ?)
        """, [ban_id, reason_set_by, reason_set_at, reason])

    def get(self, ban_id: int) -> Optional[Tuple[str, str, int]]:
        cursor = self._db.execute("""
            SELECT reason, reason_set_by, reason_set_at FROM reasons
            WHERE ban_id=?
            ORDER BY reason_id DESC
            LIMIT 1
        """, [ban_id])
        return cursor.fetchone()

    def get_all(self, ban_id: int) -> List[Tuple[str, str, int]]:
        cursor = self._db.execute("""
            SELECT reason, reason_set_by, reason_set_at FROM reasons
            WHERE ban_id=?
            ORDER BY reason_id
        """, [ban_id])
        return cursor.fetchall()
