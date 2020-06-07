import os.path, sqlite3
from typing import List, Optional, Tuple

class ExpirationsTable(object):
    def __init__(self, db: sqlite3.Connection, new: bool):
        self._db = db
        if new:
            self._db.execute("""
                CREATE TABLE expirations (
                    expire_id INTEGER PRIMARY KEY,
                    ban_id INTEGER NOT NULL,

                    expire_set_by TEXT NOT NULL,
                    expire_set_at INTEGER NOT NULL,
                    expire INTEGER NOT NULL,

                    FOREIGN KEY (ban_id) REFERENCES bans(ban_id)
                )
            """)

    def set(self,
            ban_id: int,
            expire_set_by: str,
            expire_set_at: int,
            duration: int):
        cursor = self._db.execute("""
            SELECT set_at FROM bans
            WHERE ban_id=?
        """, [ban_id])
        set_at = cursor.fetchone()[0]
        expire = set_at+duration

        self._db.execute("""
            INSERT INTO expirations (
                ban_id, expire_set_by, expire_set_at, expire
            )
            VALUES (?, ?, ?, ?)
        """, [ban_id, expire_set_by, expire_set_at, expire])

    def get(self, ban_id: int) -> Optional[Tuple[str, str, int]]:
        cursor = self._db.execute("""
            SELECT expire, expire_set_by, expire_set_at FROM expirations
            WHERE ban_id=?
            ORDER BY expire_id DESC
            LIMIT 1
        """, [ban_id])
        return cursor.fetchone()

    def get_all(self, ban_id: int) -> List[Tuple[str, str, int]]:
        cursor = self._db.execute("""
            SELECT expire, expire_set_by, expire_set_at FROM expirations
            WHERE ban_id=?
            ORDER BY expire_id
        """, [ban_id])
        return cursor.fetchone()

    def find_expired(self,
            now: int
            ) -> List[int]:
        cursor = self._db.execute("""
            SELECT ban_id, max(expire_id) FROM expirations
            WHERE expire < ?
            GROUP BY ban_id
        """, [now])
        return [r[0] for r in cursor.fetchall()]
