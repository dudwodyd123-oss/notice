"""도서관(lib.pusan.ac.kr) 게시판 파서.

도서관 홈페이지는 Angular 로 만들어져 HTML 에 글 목록이 들어 있지 않다.
화면이 뜬 뒤 Pyxis 도서관 시스템의 공개 API 를 불러 채우므로, 우리도
같은 API 를 그대로 부른다. 인증도 토큰도 필요 없다.

위에 고정된 공지는 목록 API 에 다 나오지 않는다. 오래된 고정공지는
최신 목록 밖으로 밀려나 있어서, 고정공지만 따로 한 번 더 받아 합친다.
"""

from __future__ import annotations

from urllib.parse import urlparse

from ..fetcher import Fetcher
from ..models import Post, Site
from ..text import collapse

PAGE_SIZE = 30


def parse_pyxis(site: Site, fetcher: Fetcher) -> list[Post]:
    origin = _origin(site.url)
    board_id = site.options.get("board_id")
    if board_id is None:
        raise ValueError(
            f"{site.name}: 도서관 게시판은 board_id 가 필요합니다. "
            "게시판을 열고 개발자도구 네트워크 탭에서 "
            "'bulletin-boards/<번호>' 의 번호를 확인해 config.yaml 에 적으세요."
        )
    endpoint = f"{origin}/pyxis-api/1/bulletin-boards/{board_id}/bulletins"
    page_size = site.options.get("page_size", PAGE_SIZE)

    posts: dict[str, Post] = {}
    # 고정공지를 먼저 넣고 일반 목록을 덮어쓰지 않게 한다. 겹치는 글은
    # 고정 표시를 살려야 하기 때문이다.
    for pinned, params in (
        (True, {"onlyNoticableBulletin": "true", "max": page_size}),
        (False, {"dateCreated": "true", "max": page_size}),
    ):
        for item in _fetch(fetcher, endpoint, params):
            post = _post(site, item, pinned)
            if post and post.post_id not in posts:
                posts[post.post_id] = post
    return list(posts.values())


parse_pyxis.needs_fetcher = True  # HTML 대신 Fetcher 를 받는 파서


def _fetch(fetcher: Fetcher, endpoint: str, params: dict) -> list[dict]:
    response = fetcher.session.get(
        endpoint,
        params={"nameOption": "", "onlyWriter": "false", **params},
        timeout=fetcher.timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        message = payload.get("message") or payload.get("code") or "알 수 없는 오류"
        raise RuntimeError(f"도서관 API 응답 실패: {message}")
    return (payload.get("data") or {}).get("list") or []


def _post(site: Site, item: dict, pinned: bool) -> Post | None:
    post_id = item.get("id")
    if post_id is None:
        return None
    category = item.get("bulletinCategory") or {}
    return Post(
        site_key=site.key,
        site_name=site.name,
        post_id=str(post_id),
        title=collapse(item.get("title")),
        # 사람이 보는 주소는 목록 페이지 뒤에 글 번호를 붙인 모양이다.
        url=f"{site.url.rstrip('/')}/{post_id}",
        author=collapse(item.get("writer")),
        # "2026-09-03 13:34:29" 에서 날짜만 쓴다.
        posted_at=collapse(item.get("dateCreated"))[:10],
        category=collapse(category.get("name")),
        pinned=pinned,
    )


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"도서관 게시판 주소 형식이 아닙니다: {url}")
    return f"{parsed.scheme}://{parsed.netloc}"
