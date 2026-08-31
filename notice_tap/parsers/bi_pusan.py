"""부산대 창업지원단(bi.pusan.ac.kr) 게시판 파서.

이 사이트는 Vue 로 만들어져 HTML 에는 글 목록이 들어 있지 않고,
화면이 뜬 뒤 내부 API 를 호출해 채운다. 그래서 HTML 을 긁는 대신
같은 API 를 직접 호출한다. API 는 CSRF 토큰을 요구하므로 목록 페이지를
먼저 한 번 열어 토큰과 세션 쿠키를 받아 온다.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..fetcher import Fetcher
from ..models import Post, Site

PAGE_SIZE = 30


def parse_bi_pusan(site: Site, fetcher: Fetcher) -> list[Post]:
    origin, board_id = _split(site.url)

    page = fetcher.session.get(site.url, timeout=fetcher.timeout)
    page.raise_for_status()
    token, header_name = _csrf(page.text)

    response = fetcher.session.post(
        f"{origin}/api/article/{board_id}/list.api",
        json={
            "pageIndex": 1,
            "pageSize": site.options.get("page_size", PAGE_SIZE),
            "searchType": "",
            "searchValue": "",
            "searchArticleCtg": "",
            "searchNowBeforeListYn": False,
            "_csrf": token,
        },
        headers={header_name: token} if header_name and token else {},
        timeout=fetcher.timeout,
    )
    response.raise_for_status()
    payload = response.json()

    if not (payload.get("header") or {}).get("result"):
        message = (payload.get("header") or {}).get("message") or "알 수 없는 오류"
        raise RuntimeError(f"창업지원단 API 응답 실패: {message}")

    items = ((payload.get("body") or {}).get("data") or {}).get("list") or []
    return [
        Post(
            site_key=site.key,
            site_name=site.name,
            post_id=str(item["id"]),
            title=_clean(item.get("subject")),
            url=f"{origin}/community/{board_id}/{item['id']}",
            author=_clean(item.get("regIdName")),
            posted_at=_clean(item.get("regDtText")),
            category=_clean(item.get("articleCtgText")),
        )
        for item in items
        if item.get("id") is not None
    ]


parse_bi_pusan.needs_fetcher = True  # HTML 대신 Fetcher 를 받는 파서


def _split(url: str) -> tuple[str, str]:
    """https://bi.pusan.ac.kr/community/notice → (origin, 'notice')"""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2 or parts[0] != "community":
        raise ValueError(f"창업지원단 게시판 주소 형식이 아닙니다: {url}")
    return origin, parts[1]


def _csrf(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    token = soup.select_one('meta[name="_csrf"]')
    header = soup.select_one('meta[name="_csrf_header"]')
    return (
        token.get("content", "") if token else "",
        header.get("content", "") if header else "",
    )


def _clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
