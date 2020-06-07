import os.path, sqlite3
from typing import List, Optional, Tuple

from .reasons     import ReasonsTable
from .expirations import ExpirationsTable

class BanDatabase(object):
    def __init__(self, location: str):
        new = not os.path.isfile(location)
        self._db = sqlite3.connect(location, isolation_level=None)
        self._db.execute("PRAGMA journal_mode = WAL")
        if new:
            print("we're new")
            self._db.execute("""
                CREATE TABLE bans (
                    ban_id INTEGER PRIMARY KEY,
                    channel TEXT NOT NULL,
                    type INTEGER NOT NULL,
                    mask TEXT NOT NULL,

                    set_by TEXT NOT NULL,
                    set_at INTEGER NOT NULL,

                    removed_by TEXT,
                    removed_at INTEGER
                )
            """)
        self.reasons = ReasonsTable(self._db, new)
        self.expirations = ExpirationsTable(self._db, new)

    def add(self,
            channel: str,
            type: int,
            mask: str,
            set_by: str,
            set_at: int) -> int:
        self._db.execute("""
            INSERT INTO bans (channel, type, mask, set_by, set_at)
            VALUES (?, ?, ?, ?, ?)
        """, [channel, type, mask, set_by, set_at])
        return self.get_last(channel)

    def find(self,
            channel: str,
            type:    int,
            mask:    str) -> Optional[int]:
        cursor = self._db.execute("""
            SELECT ban_id FROM bans
            WHERE channel=? AND type=? AND mask=?
        """, [channel, type, mask])
        return (cursor.fetchone() or [None])[0]

    def set_removed(self,
            ban_id:     int,
            removed_by: Optional[str],
            removed_at: int):
        self._db.execute("""
            UPDATE bans
            SET removed_by=?, removed_at=?
            WHERE ban_id=? AND removed_at IS NULL
        """, [removed_by, removed_at, ban_id])

    def get_active(self, channel: str) -> List[Tuple[int, int, str]]:
        cursor = self._db.execute("""
            SELECT ban_id, type, mask FROM bans
            WHERE channel=? AND removed_at IS NULL
        """, [channel])
        return cursor.fetchall()

    def get_last(self, channel: str):
        cursor = self._db.execute("""
            SELECT ban_id FROM bans
            WHERE channel=? AND removed_at IS NULL
            ORDER BY ban_id DESC
            LIMIT 1
        """, [channel])
        ban_id = (cursor.fetchone() or [None])[0]
        return ban_id

    def get_ban(self,
            ban_id: int
            ) -> Tuple[str, int, str, str, int, Optional[str], int]:
        cursor = self._db.execute("""
            SELECT
                channel, type, mask, set_by, set_at, removed_by, removed_at
            FROM bans
            WHERE ban_id=?
        """, [ban_id])
        return (cursor.fetchall() or [None])[0]

    def ban_exists(self, ban_id: int) -> bool:
        cursor = self._db.execute("""
            SELECT '1' FROM bans
            WHERE ban_id=?
        """, [ban_id])
        out = cursor.fetchone()
        return (out or ["0"])[0] == "1"

