import os.path, sqlite3
from typing import List, Optional, Tuple

class MaskDatabase(object):
    def __init__(self, location: str):
        new = not os.path.isfile(location)
        self._db = sqlite3.connect(location, isolation_level=None)
        self._db.execute("PRAGMA journal_mode = WAL")
        if new:
            self._db.execute("""
                CREATE TABLE masks (
                    mask_id INTEGER PRIMARY KEY,
                    mask    TEXT NOT NULL,
                    comment TEXT,
                    removed INTEGER NOT NULL
                )
            """)

    def get_last(self) -> int:
        cursor = self._db.execute("""
            SELECT mask_id FROM masks
            ORDER BY mask_id DESC
            LIMIT 1
        """)
        mask_id = (cursor.fetchone() or [None])[0]
        return mask_id

    def add(self,
            mask:    str,
            comment: Optional[str]) -> int:
        self._db.execute("""
            INSERT INTO masks (mask, comment, removed)
            VALUES (?, ?, 0)
        """, [mask, comment])
        return self.get_last()

    def get_all(self) -> List[Tuple[int, str]]:
        cursor = self._db.execute("""
            SELECT mask_id, mask
            FROM  masks
            WHERE removed = 0
        """)
        return list(cursor.fetchall())

    def find(self, mask: str) -> Optional[int]:
        cursor = self._db.execute("""
            SELECT mask_id
            FROM  masks
            WHERE mask = ? AND removed = 0
        """, [mask])
        return (cursor.fetchone() or [None])[0]

    def get(self, mask_id: int) -> str:
        cursor = self._db.execute("""
            SELECT mask
            FROM  masks
            WHERE mask_id = ?
        """, [mask_id])
        return cursor.fetchone()[0]

    def get_comment(self, mask_id: int) -> Optional[str]:
        cursor = self._db.execute("""
            SELECT comment
            FROM masks
            WHERE mask_id = ?
        """, [mask_id])
        return cursor.fetchone()[0]
    def set_comment(self,
            mask_id: int,
            comment: Optional[str]):
        self._db.execute("""
            UPDATE masks
            SET   comment = ?
            where mask_id = ?
        """, [comment, mask_id])

    def remove(self, mask_id: int):
        self._db.execute("""
            UPDATE masks
            SET   removed = 1
            WHERE mask_id=?
        """, [mask_id])
