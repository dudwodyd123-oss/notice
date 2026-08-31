"""카카오톡 '나에게 보내기'(메모 API) 알림.

카카오 정책상 별도 앱 심사 없이 보낼 수 있는 대상은 '나 자신'뿐이다.
따라서 내 카카오톡의 '나와의 채팅방'으로 새 공지가 도착한다.
최초 1회 `python kakao_auth.py` 로 refresh_token 을 발급받아야 한다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from ..models import Post
from .base import Notifier, NotifierUnavailable, group_by_site

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
TEXT_LIMIT = 190  # 카카오 텍스트 템플릿 상한 200자에 여유를 둔다


class KakaoNotifier(Notifier):
    name = "kakao"

    def __init__(
        self,
        rest_api_key: str,
        refresh_token: str = "",
        token_cache: str | Path = "data/kakao_token.json",
        max_messages: int = 8,
        timeout: int = 15,
    ):
        if not rest_api_key:
            raise NotifierUnavailable("카카오 REST API 키가 비어 있습니다")
        self.rest_api_key = rest_api_key
        self.token_cache = Path(token_cache)
        self.max_messages = max_messages
        self.timeout = timeout
        self._refresh_token = refresh_token or self._cached().get("refresh_token", "")
        if not self._refresh_token:
            raise ValueError("kakao refresh_token 이 없습니다. `python kakao_auth.py` 를 먼저 실행하세요")

    # --- 토큰 -----------------------------------------------------------

    def _cached(self) -> dict:
        if self.token_cache.exists():
            try:
                return json.loads(self.token_cache.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self, data: dict) -> None:
        self.token_cache.parent.mkdir(parents=True, exist_ok=True)
        self.token_cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _access_token(self) -> str:
        cache = self._cached()
        if cache.get("access_token") and cache.get("expires_at", 0) > time.time() + 60:
            return cache["access_token"]

        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self.rest_api_key,
                "refresh_token": self._refresh_token,
            },
            timeout=self.timeout,
        )
        if not resp.ok:
            raise RuntimeError(
                f"카카오 토큰 갱신 실패 ({resp.status_code}): {resp.text[:200]}\n"
                "refresh_token 이 만료되었을 수 있습니다. `python kakao_auth.py` 를 다시 실행하세요."
            )
        body = resp.json()
        # 카카오는 refresh_token 만료가 가까울 때만 새 값을 함께 내려준다.
        self._refresh_token = body.get("refresh_token", self._refresh_token)
        self._save(
            {
                "access_token": body["access_token"],
                "expires_at": time.time() + body.get("expires_in", 21600),
                "refresh_token": self._refresh_token,
            }
        )
        return body["access_token"]

    # --- 전송 -----------------------------------------------------------

    def send(self, posts: list[Post]) -> None:
        token = self._access_token()
        headers = {"Authorization": f"Bearer {token}"}

        for message, link in _messages(posts, self.max_messages):
            resp = requests.post(
                MEMO_URL,
                headers=headers,
                data={
                    "template_object": json.dumps(
                        {
                            "object_type": "text",
                            "text": message,
                            "link": {"web_url": link, "mobile_web_url": link},
                            "button_title": "게시글 보기",
                        },
                        ensure_ascii=False,
                    )
                },
                timeout=self.timeout,
            )
            if not resp.ok:
                raise RuntimeError(f"카카오톡 전송 실패 ({resp.status_code}): {resp.text[:200]}")


def _messages(posts: list[Post], max_messages: int) -> list[tuple[str, str]]:
    """카카오는 한 통에 200자 제한이 있어 글 하나당 한 통으로 나눠 보낸다."""
    if len(posts) > max_messages:
        grouped = group_by_site(posts)
        lines = [f"📢 새 공지 {len(posts)}건이 올라왔습니다."]
        lines += [f"· {name} {len(group)}건" for name, group in grouped.items()]
        return [(_truncate("\n".join(lines)), posts[0].url)]

    out: list[tuple[str, str]] = []
    for post in posts:
        date = f"\n{post.posted_at}" if post.posted_at else ""
        out.append((_truncate(f"📢 [{post.site_name}]\n{post.title}{date}"), post.url))
    return out


def _truncate(text: str) -> str:
    return text if len(text) <= TEXT_LIMIT else text[: TEXT_LIMIT - 1] + "…"
