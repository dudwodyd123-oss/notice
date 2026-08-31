"""게시글/사이트 데이터 모델."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .dates import to_iso_date


@dataclass(frozen=True)
class Post:
    """게시판에서 긁어온 글 하나."""

    site_key: str
    site_name: str
    post_id: str
    title: str
    url: str
    author: str = ""
    posted_at: str = ""
    category: str = ""
    pinned: bool = False

    @property
    def posted_on(self) -> str:
        """게시판마다 다른 날짜 표기를 YYYY-MM-DD 로 맞춘 값. 정렬에 쓴다."""
        return to_iso_date(self.posted_at)

    @property
    def display_date(self) -> str:
        """화면과 알림에 보여줄 날짜.

        게시판마다 2026.08.31 / 2026-08-31 / 2026.08.31 09:15 처럼 표기가 달라
        여러 곳의 글을 나란히 놓으면 지저분하다. 통일된 값을 쓰되,
        알아볼 수 없는 표기는 원문 그대로 둔다.
        """
        return self.posted_on or self.posted_at

    @property
    def uid(self) -> str:
        return f"{self.site_key}:{self.post_id}"

    def summary_line(self) -> str:
        bits = [self.title]
        if self.display_date:
            bits.append(f"({self.display_date})")
        return " ".join(bits)


@dataclass
class Site:
    """감시 대상 게시판 하나."""

    name: str
    url: str
    parser: str = "pnu"
    enabled: bool = True
    key: str = ""
    options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key:
            self.key = make_site_key(self.url)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Site":
        known = {"name", "url", "parser", "enabled", "key"}
        options = {k: v for k, v in raw.items() if k not in known}
        return cls(
            name=raw.get("name") or raw["url"],
            url=raw["url"],
            parser=raw.get("parser", "pnu"),
            enabled=raw.get("enabled", True),
            key=raw.get("key", ""),
            options=options,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "url": self.url,
            "parser": self.parser,
            "key": self.key,
        }
        if not self.enabled:
            out["enabled"] = False
        out.update(self.options)
        return out


def make_site_key(url: str) -> str:
    """URL에서 짧고 안정적인 사이트 식별자를 만든다."""
    return hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:12]
