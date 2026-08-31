"""디스코드 웹훅 알림. 웹훅 URL 하나만 있으면 되고 개인 서버에 쌓아두기 좋다."""

from __future__ import annotations

import requests

from ..models import Post
from .base import Notifier, NotifierUnavailable, group_by_site

MAX_EMBEDS = 10


class DiscordNotifier(Notifier):
    name = "discord"

    def __init__(self, webhook_url: str, timeout: int = 15):
        if not webhook_url:
            raise NotifierUnavailable("디스코드 웹훅 주소가 비어 있습니다")
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send(self, posts: list[Post]) -> None:
        for batch in _batches(posts):
            resp = requests.post(
                self.webhook_url,
                json={
                    "content": f"📢 새 공지 {len(batch)}건",
                    "embeds": [
                        {
                            "title": post.title[:250],
                            "url": post.url,
                            "description": " · ".join(
                                filter(None, [post.site_name, post.posted_at, post.author])
                            )[:300],
                            "color": 0x0B5ED7,
                        }
                        for post in batch
                    ],
                },
                timeout=self.timeout,
            )
            if not resp.ok:
                raise RuntimeError(f"디스코드 전송 실패 ({resp.status_code}): {resp.text[:200]}")


def _batches(posts: list[Post]) -> list[list[Post]]:
    ordered = [post for group in group_by_site(posts).values() for post in group]
    return [ordered[i : i + MAX_EMBEDS] for i in range(0, len(ordered), MAX_EMBEDS)]
