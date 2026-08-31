"""터미널 출력 알림. 설정이 필요 없어 항상 켜둘 수 있다."""

from __future__ import annotations

from ..models import Post
from .base import Notifier, group_by_site


class ConsoleNotifier(Notifier):
    name = "console"

    def send_alert(self, heading: str, body: str, link: str) -> None:
        print(f"\n  ⚠ {heading}")
        for line in body.splitlines():
            print(f"    {line}")

    def send(self, posts: list[Post]) -> None:
        for site_name, group in group_by_site(posts).items():
            print(f"\n  {site_name} — 새 글 {len(group)}건")
            for post in group:
                marker = "고정" if post.pinned else "신규"
                date = post.posted_at or "-"
                print(f"    [{marker}] {date}  {post.title}")
                print(f"           {post.url}")
