import os.path, sqlite3
from typing import List, Tuple

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

                    expires_by TEXT,
                    expires_at INTEGER NOT NULL,

                    reason_by TEXT,
                    reason TEXT
                )
            """)


    def get_existing(self, channel: str, type: int) -> List[str]:
        cursor = self._db.cursor()
        cursor.execute("""
            SELECT mask FROM bans
            WHERE channel=? AND type=? AND expires_at > -1
        """, [channel, type])
        return [row[0] for row in cursor.fetchall()]

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

    def set_expired(self, channel: str, type: int, mask: str):
        self._db.execute("""
            UPDATE bans
            SET expires_at=-1
            WHERE channel=? AND mask=? AND expires_at > -1
        """, [channel, mask])

    def get_last(self, channel: str):
        cursor = self._db.cursor()
        cursor.execute("""
            SELECT ban_id FROM bans
            WHERE channel=? AND expires_at > -1
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
            INSERT INTO bans (channel, type, mask, set_by, set_at, expires_at)
            VALUES (?, ?, ?, ?, ?, 0)
        """, [channel, type, mask, set_by, set_at])
        return self.get_last(channel)

    def set_reason(self, ban_id: int, reason_by: str, reason: str):
        self._db.execute("""
            UPDATE bans
            SET reason=?, reason_by=?
            WHERE ban_id=?
        """, [reason, reason_by, ban_id])

    def set_duration(self, ban_id: int, duration_by: str, duration: int):
        cursor = self._db.cursor()
        cursor.execute("""
            SELECT set_at FROM bans
            WHERE ban_id=?
        """, [ban_id])
        set_at = cursor.fetchone()[0]
        expires_at = set_at+duration

        self._db.execute("""
            UPDATE bans
            SET expires_at=?, expires_by=?
            WHERE ban_id=?
        """, [expires_at, duration_by, ban_id])

    def get_before(self, timestamp: int) -> List[Tuple[str, int, str]]:
        cursor = self._db.cursor()
        cursor.execute("""
            SELECT channel, type, mask FROM bans
            WHERE expires_at > 0 AND expires_at < ?
        """, [timestamp])
        return cursor.fetchall() or []
