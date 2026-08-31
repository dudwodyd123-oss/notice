"""알림 채널 공통 인터페이스."""

from __future__ import annotations

from ..models import Post


class NotifierUnavailable(Exception):
    """이 환경에서는 쓸 수 없는 채널(설정이 비었거나 OS 가 다름). 조용히 건너뛴다."""


class Notifier:
    name = "base"

    def send(self, posts: list[Post]) -> None:
        """새 글 목록을 알린다. 실패하면 예외를 던진다."""
        raise NotImplementedError

    def send_alert(self, heading: str, body: str, link: str) -> None:
        """새 글이 아니라 '문제가 생겼다'는 알림. 채널마다 형식이 같아 기본 구현으로 충분하다."""
        self.send(
            [
                Post(
                    site_key="alert",
                    site_name=heading,
                    post_id="alert",
                    title=body,
                    url=link,
                )
            ]
        )

    def send_test(self) -> None:
        self.send(
            [
                Post(
                    site_key="test",
                    site_name="notice_tap 테스트",
                    post_id="0",
                    title="알림 설정이 정상적으로 동작합니다.",
                    url="https://cse.pusan.ac.kr/bbs/cse/2055/artclList.do",
                    posted_at="지금",
                )
            ]
        )


def group_by_site(posts: list[Post]) -> dict[str, list[Post]]:
    grouped: dict[str, list[Post]] = {}
    for post in posts:
        grouped.setdefault(post.site_name, []).append(post)
    return grouped


def plain_text(posts: list[Post], limit: int = 10) -> str:
    """어느 채널에서나 쓸 수 있는 순수 텍스트 요약."""
    lines: list[str] = []
    for site_name, group in group_by_site(posts).items():
        lines.append(f"[{site_name}] 새 글 {len(group)}건")
        for post in group[:limit]:
            date = f" ({post.display_date})" if post.display_date else ""
            lines.append(f"  · {post.title}{date}")
            lines.append(f"    {post.url}")
        if len(group) > limit:
            lines.append(f"  … 외 {len(group) - limit}건")
    return "\n".join(lines)
