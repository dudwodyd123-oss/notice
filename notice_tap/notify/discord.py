"""디스코드 웹훅 알림. 웹훅 URL 하나만 있으면 되고 개인 서버에 쌓아두기 좋다."""

from __future__ import annotations

import requests

from ..models import Post
from .base import Notifier, NotifierUnavailable, group_by_site

MAX_EMBEDS = 10


def _linkable(url: str) -> str:
    """디스코드가 받아 주는 주소만 남긴다.

    embed 의 url 은 http/https 여야 한다. 내 컴퓨터 안의 경로(file://)를
    그대로 넣으면 글 내용과 상관없이 400 이 떨어져 그 통보 전체가 사라진다.
    """
    return url if url.startswith(("http://", "https://")) else ""


class DiscordNotifier(Notifier):
    name = "discord"

    def __init__(self, webhook_url: str, timeout: int = 15):
        if not webhook_url:
            raise NotifierUnavailable("디스코드 웹훅 주소가 비어 있습니다")
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send(self, posts: list[Post]) -> None:
        for batch in _batches(posts):
            self._post(
                f"📢 새 공지 {len(batch)}건",
                [
                    {
                        "title": post.title[:250],
                        "url": _linkable(post.url),
                        "description": " · ".join(
                            filter(None, [post.site_name, post.display_date, post.author])
                        )[:300],
                        "color": 0x0B5ED7,
                    }
                    for post in batch
                ],
            )

    def send_alert(self, heading: str, body: str, link: str) -> None:
        """새 글이 아니라 '무언가 잘못됐다'는 통보. 새 글과 눈에 띄게 달라야 한다."""
        self._post(
            f"⚠️ {heading}",
            [{
                "title": heading[:250],
                "url": _linkable(link),
                "description": body[:2000],
                "color": 0xD93025,
            }],
        )

    def _post(self, content: str, embeds: list[dict]) -> None:
        for embed in embeds:
            if not embed.get("url"):
                embed.pop("url", None)  # 빈 문자열도 디스코드는 거절한다
        resp = requests.post(
            self.webhook_url,
            json={"content": content, "embeds": embeds},
            timeout=self.timeout,
        )
        if not resp.ok:
            raise RuntimeError(f"디스코드 전송 실패 ({resp.status_code}): {resp.text[:200]}")


def _batches(posts: list[Post]) -> list[list[Post]]:
    ordered = [post for group in group_by_site(posts).values() for post in group]
    return [ordered[i : i + MAX_EMBEDS] for i in range(0, len(ordered), MAX_EMBEDS)]
