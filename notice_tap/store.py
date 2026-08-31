"""이미 본 글을 기억하는 SQLite 저장소."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Post

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    uid        TEXT PRIMARY KEY,
    site_key   TEXT NOT NULL,
    site_name  TEXT NOT NULL,
    post_id    TEXT NOT NULL,
    title      TEXT NOT NULL,
    url        TEXT NOT NULL,
    author     TEXT DEFAULT '',
    posted_at  TEXT DEFAULT '',
    category   TEXT DEFAULT '',
    pinned     INTEGER DEFAULT 0,
    first_seen TEXT NOT NULL,
    notified   INTEGER DEFAULT 0,
    baseline   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_posts_seen ON posts(first_seen DESC);
CREATE INDEX IF NOT EXISTS idx_posts_site ON posts(site_key);

CREATE TABLE IF NOT EXISTS sites_state (
    site_key    TEXT PRIMARY KEY,
    last_check  TEXT,
    last_ok     TEXT,
    last_error  TEXT DEFAULT '',
    fail_since  TEXT DEFAULT '',
    last_alert  TEXT DEFAULT ''
);
"""


class Store:
    def __init__(self, path: str | Path = "data/notices.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """예전 버전에서 만든 데이터베이스도 그대로 쓸 수 있게 한다."""
        posts_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(posts)")}
        if "baseline" not in posts_columns:
            self.conn.execute("ALTER TABLE posts ADD COLUMN baseline INTEGER DEFAULT 0")

        state_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(sites_state)")}
        for column in ("fail_since", "last_alert"):
            if column not in state_columns:
                self.conn.execute(f"ALTER TABLE sites_state ADD COLUMN {column} TEXT DEFAULT ''")

    # --- 신규 글 판별 -------------------------------------------------

    def filter_new(self, posts: list[Post]) -> list[Post]:
        """아직 저장된 적 없는 글만 골라낸다."""
        if not posts:
            return []
        known = self._known_uids(posts[0].site_key)
        return [p for p in posts if p.uid not in known]

    def _known_uids(self, site_key: str) -> set[str]:
        rows = self.conn.execute("SELECT uid FROM posts WHERE site_key = ?", (site_key,))
        return {row["uid"] for row in rows}

    def has_seen_site(self, site_key: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM posts WHERE site_key = ? LIMIT 1", (site_key,)
        ).fetchone()
        return row is not None

    # --- 쓰기 ---------------------------------------------------------

    def record(self, posts: list[Post], notified: bool, baseline: bool = False) -> None:
        """baseline=True 는 사이트를 처음 등록할 때 잡는 기준점이다(새 글이 아니다)."""
        now = _now()
        self.conn.executemany(
            """INSERT OR IGNORE INTO posts
               (uid, site_key, site_name, post_id, title, url, author,
                posted_at, category, pinned, first_seen, notified, baseline)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    p.uid, p.site_key, p.site_name, p.post_id, p.title, p.url,
                    p.author, p.posted_at, p.category, int(p.pinned), now,
                    int(notified), int(baseline),
                )
                for p in posts
            ],
        )
        self.conn.commit()

    def sync_site_name(self, site_key: str, name: str) -> int:
        """config.yaml 에서 이름을 바꾸면 이미 저장된 글에도 반영한다.

        글마다 사이트 이름을 함께 갖고 있어서, 맞춰주지 않으면 모아보기 화면에
        옛 이름과 새 이름이 서로 다른 게시판처럼 나란히 남는다.
        """
        cur = self.conn.execute(
            "UPDATE posts SET site_name = ? WHERE site_key = ? AND site_name <> ?",
            (name, site_key, name),
        )
        self.conn.commit()
        return cur.rowcount

    def mark_check(self, site_key: str, error: str = "") -> None:
        """확인 결과를 기록한다. 연속 실패가 언제 시작됐는지도 함께 남긴다."""
        now = _now()
        self.conn.execute(
            "INSERT OR IGNORE INTO sites_state (site_key, last_check) VALUES (?, ?)",
            (site_key, now),
        )

        if error:
            # fail_since 는 연속 실패가 '시작된' 시각이라 이미 값이 있으면 건드리지 않는다.
            self.conn.execute(
                """UPDATE sites_state
                      SET last_check = ?,
                          last_error = ?,
                          fail_since = CASE WHEN COALESCE(fail_since, '') = '' THEN ?
                                            ELSE fail_since END
                    WHERE site_key = ?""",
                (now, error, now, site_key),
            )
        else:
            self.conn.execute(
                """UPDATE sites_state
                      SET last_check = ?, last_ok = ?, last_error = '',
                          fail_since = '', last_alert = ''
                    WHERE site_key = ?""",
                (now, now, site_key),
            )
        self.conn.commit()

    # --- 오래된 오류 감지 ------------------------------------------------

    def stale_sites(self, days: float, cooldown_hours: float = 24.0) -> list[sqlite3.Row]:
        """며칠째 계속 실패 중이고, 아직 알리지 않은(또는 알린 지 오래된) 사이트."""
        if days <= 0:
            return []

        now = datetime.now(timezone.utc).astimezone()
        failing_before = (now - timedelta(days=days)).isoformat(timespec="seconds")
        alerted_before = (now - timedelta(hours=cooldown_hours)).isoformat(timespec="seconds")

        return list(
            self.conn.execute(
                """SELECT * FROM sites_state
                    WHERE COALESCE(fail_since, '') <> ''
                      AND fail_since <= ?
                      AND COALESCE(last_alert, '') <= ?""",
                (failing_before, alerted_before),
            )
        )

    def mark_alerted(self, site_key: str) -> None:
        self.conn.execute(
            "UPDATE sites_state SET last_alert = ? WHERE site_key = ?", (_now(), site_key)
        )
        self.conn.commit()

    def forget_site(self, site_key: str) -> int:
        cur = self.conn.execute("DELETE FROM posts WHERE site_key = ?", (site_key,))
        self.conn.execute("DELETE FROM sites_state WHERE site_key = ?", (site_key,))
        self.conn.commit()
        return cur.rowcount

    # --- 읽기 ---------------------------------------------------------

    def recent(self, limit: int = 200, site_key: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM posts"
        params: list = []
        if site_key:
            sql += " WHERE site_key = ?"
            params.append(site_key)
        sql += " ORDER BY first_seen DESC, posted_at DESC, post_id DESC LIMIT ?"
        params.append(limit)
        return list(self.conn.execute(sql, params))

    def site_states(self) -> dict[str, sqlite3.Row]:
        return {row["site_key"]: row for row in self.conn.execute("SELECT * FROM sites_state")}

    def count(self, site_key: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM posts WHERE site_key = ?", (site_key,)
        ).fetchone()
        return row["n"]

    # --- 내보내기 / 가져오기 ---------------------------------------------

    def export_state(self) -> dict:
        """본 글 기록 전체를 JSON 으로 옮길 수 있는 형태로 뽑는다.

        GitHub Actions 처럼 매번 새 컴퓨터에서 도는 환경에서는 SQLite 파일 대신
        이 JSON 을 저장소에 커밋해 상태를 이어간다. 텍스트라서 변경분도 작다.
        """
        # last_check / last_ok 는 매번 값이 달라지기만 할 뿐 다음 실행에 필요하지 않다.
        # 빼두어야 새 글이 없는 시간대에는 내보낸 내용이 전혀 바뀌지 않고,
        # 저장소에 쓸데없는 커밋이 쌓이지 않는다.
        return {
            "version": 1,
            "posts": [
                dict(row)
                for row in self.conn.execute("SELECT * FROM posts ORDER BY uid")
            ],
            "sites_state": [
                dict(row)
                for row in self.conn.execute(
                    """SELECT site_key, last_error, fail_since, last_alert
                         FROM sites_state ORDER BY site_key"""
                )
            ],
        }

    def import_state(self, data: dict) -> int:
        """export_state 로 뽑은 기록을 되돌려 넣는다. 이미 있는 글은 건드리지 않는다."""
        posts = data.get("posts", [])
        if posts:
            columns = [c for c in posts[0] if c != "id"]
            placeholders = ",".join("?" * len(columns))
            self.conn.executemany(
                f"INSERT OR IGNORE INTO posts ({','.join(columns)}) VALUES ({placeholders})",
                [tuple(row.get(c) for c in columns) for row in posts],
            )

        for row in data.get("sites_state", []):
            columns = list(row)
            placeholders = ",".join("?" * len(columns))
            self.conn.execute(
                f"INSERT OR REPLACE INTO sites_state ({','.join(columns)}) VALUES ({placeholders})",
                tuple(row.values()),
            )

        self.conn.commit()
        return len(posts)

    def close(self) -> None:
        self.conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
