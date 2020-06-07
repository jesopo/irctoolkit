import os.path, sqlite3
from typing import List, Optional, Tuple

class BanDatabase(object):
    def __init__(self, location: str):
        new = not os.path.isfile(location)
        self._db = sqlite3.connect(location, isolation_level=None)
        self._db.execute("PRAGMA journal_mode = WAL")
        if new:
            self._db.execute("""
                CREATE TABLE bans (
                    ban_id INTEGER PRIMARY KEY,
                    channel TEXT,
                    type INTEGER,
                    mask TEXT,

                    set_by TEXT,
                    set_at INTEGER,

                    expire_set_by TEXT,
                    expire_set_at INTEGER,
                    expires_at INTEGER,

                    reason_set_by TEXT,
                    reason_set_at INTEGER,
                    reason TEXT,

                    removed_by TEXT,
                    removed_at INTEGER
                )
            """)


    def get_existing(self, channel: str) -> List[Tuple[int, str]]:
        cursor = self._db.cursor()
        cursor.execute("""
            SELECT type, mask FROM bans
            WHERE channel=? AND removed_at IS NULL
        """, [channel])
        return cursor.fetchall()

    def get_ban(self, ban_id: int) -> Tuple[str, int, str, str, int, str]:
        cursor = self._db.cursor()
        cursor.execute("""
            SELECT channel, type, mask, set_by, expires_at, reason FROM bans
            WHERE ban_id=?
        """, [ban_id])
        return (cursor.fetchall() or [None])[0]

    def ban_exists(self, ban_id: int) -> bool:
        cursor = self._db.cursor()
        cursor.execute("""
            SELECT '1' FROM bans
            WHERE ban_id=?
        """, [ban_id])
        out = cursor.fetchone()
        return (out or ["0"])[0] == "1"

    def set_removed(self,
            channel: str,
            type: int,
            mask: str,
            removed_by: Optional[str],
            removed_at: int):
        print("removing", channel, mask, removed_by, removed_at)
        self._db.execute("""
            UPDATE bans
            SET removed_by=?, removed_at=?
            WHERE type=? AND channel=? AND mask=? AND removed_at IS NULL
        """, [removed_by, removed_at, type, channel, mask])

    def get_last(self, channel: str):
        cursor = self._db.cursor()
        cursor.execute("""
            SELECT ban_id FROM bans
            WHERE channel=? AND removed_at IS NULL
            ORDER BY ban_id DESC
            LIMIT 1
        """, [channel])
        ban_id = (cursor.fetchone() or [None])[0]
        return ban_id

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

    def set_reason(self,
            ban_id: int,
            reason_set_by: str,
            reason_set_at: int,
            reason: str):
        self._db.execute("""
            UPDATE bans
            SET reason_set_by=?, reason_set_at=?, reason=?
            WHERE ban_id=?
        """, [reason_set_by, reason_set_at, reason, ban_id])

    def set_duration(self,
            ban_id: int,
            expire_set_by: str,
            expire_set_at: int,
            duration: int):
        cursor = self._db.cursor()
        cursor.execute("""
            SELECT set_at FROM bans
            WHERE ban_id=?
        """, [ban_id])
        set_at = cursor.fetchone()[0]
        expires_at = set_at+duration

        self._db.execute("""
            UPDATE bans
            SET expire_set_by=?, expire_set_at=?, expires_at=?
            WHERE ban_id=?
        """, [expire_set_by, expire_set_at, expires_at, ban_id])

    def get_before(self, timestamp: int) -> List[Tuple[str, int, str]]:
        cursor = self._db.cursor()
        cursor.execute("""
            SELECT channel, type, mask FROM bans
            WHERE removed_at IS NULL AND expires_at < ?
        """, [timestamp])
        return cursor.fetchall() or []
