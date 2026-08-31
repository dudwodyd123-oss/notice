"""텔레그램 봇 알림. 설정이 가장 간단하고 링크 미리보기도 깔끔하다."""

from __future__ import annotations

import html

import requests

from ..models import Post
from .base import Notifier, NotifierUnavailable, group_by_site

API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_LEN = 3800  # 텔레그램 상한 4096자에 여유를 둔다


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str, timeout: int = 15):
        if not bot_token and not chat_id:
            raise NotifierUnavailable("텔레그램 설정이 비어 있습니다")
        if not bot_token or not chat_id:
            raise ValueError("telegram 알림에는 bot_token 과 chat_id 가 모두 필요합니다")
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.timeout = timeout

    def send(self, posts: list[Post]) -> None:
        for chunk in _chunks(_render(posts)):
            resp = requests.post(
                API.format(token=self.bot_token),
                json={
                    "chat_id": self.chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=self.timeout,
            )
            if not resp.ok:
                raise RuntimeError(f"텔레그램 전송 실패 ({resp.status_code}): {resp.text[:200]}")


def _render(posts: list[Post]) -> str:
    blocks: list[str] = []
    for site_name, group in group_by_site(posts).items():
        lines = [f"<b>📢 {html.escape(site_name)}</b> — 새 글 {len(group)}건"]
        for post in group:
            date = f" <i>{html.escape(post.display_date)}</i>" if post.display_date else ""
            lines.append(f'• <a href="{html.escape(post.url, quote=True)}">{html.escape(post.title)}</a>{date}')
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _chunks(text: str) -> list[str]:
    if len(text) <= MAX_LEN:
        return [text]
    out, buf = [], ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > MAX_LEN:
            out.append(buf)
            buf = ""
        buf += line + "\n"
    if buf.strip():
        out.append(buf)
    return out
