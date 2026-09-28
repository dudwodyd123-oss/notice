"""부산대 나눔시스템(nanum.pusan.ac.kr) 게시판 파서.

이 게시판은 목록을 통째로 가져올 방법이 없다. 화면의 목록은 자바스크립트가
암호화된 요청을 보내 받아오는데, 그 암호를 우리 쪽에서 재현할 수 없다.

대신 글 하나하나는 ?mode=DETAIL&seq=<번호> 로 그냥 열린다. 글 번호가 1씩
늘어나므로, 마지막으로 본 번호 다음부터 한 칸씩 짚어가며 새 글을 찾는다.
지워진 글이 있으면 번호가 비므로, 몇 칸 연속으로 비어야 끝으로 판단한다.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from ..fetcher import Fetcher
from ..models import Post, Site
from ..store import Store
from ..text import collapse

# 이만큼 연속으로 비어 있으면 최신 글까지 다 봤다고 판단한다.
MAX_MISSES = 5
# 한 회차에 새로 가져올 글 수 상한. 번호 체계가 어긋났을 때 폭주를 막는다.
MAX_NEW = 25
# 처음 등록할 때 화면을 채우려고 거슬러 올라가 훑는 개수.
BACKFILL = 12
# 새 글이 없을 때, 게시판이 살아 있는지 확인하려고 거슬러 올라가 볼 개수.
ANCHOR_TRIES = 5

INFO_RE = re.compile(
    r"작성자\s*(?P<author>.*?)\s*작성일\s*(?P<date>\d{4}-\d{2}-\d{2})"
)


def parse_nanum(site: Site, fetcher: Fetcher, store: Store) -> list[Post]:
    start = site.options.get("start_seq")
    if start is None:
        raise ValueError(
            f"{site.name}: 나눔시스템 게시판은 start_seq(시작 글 번호)가 필요합니다. "
            "게시판에서 아무 글이나 열어 주소의 seq 값을 적으세요."
        )

    last_seen = store.max_numeric_post_id(site.key)
    if last_seen is None:
        # 처음 등록하는 경우. 화면이 휑하지 않도록 최근 글을 거슬러 올라가며 담는다.
        numbers = range(int(start), int(start) - BACKFILL, -1)
    else:
        numbers = range(last_seen + 1, last_seen + 1 + MAX_NEW + MAX_MISSES)

    posts: list[Post] = []
    misses = 0
    for seq in numbers:
        if seq < 1:
            break
        post = _one(site, fetcher, seq)
        if post is None:
            misses += 1
            if misses >= MAX_MISSES:
                break
            continue
        misses = 0
        posts.append(post)
        if len(posts) >= MAX_NEW:
            break

    if posts or last_seen is None:
        return posts

    # 새 글이 하나도 없으면 목록이 빈 채로 돌아간다. 그런데 부르는 쪽은
    # '한 건도 못 읽었다 = 게시판이 깨졌다' 로 본다. 조용한 날과 고장을
    # 가려내려면, 마지막으로 본 글이 아직 열리는지 확인해 그 글을 내준다.
    # 이미 저장돼 있는 글이라 새 알림이 가지는 않는다.
    return _anchor(site, fetcher, last_seen)


def _anchor(site: Site, fetcher: Fetcher, last_seen: int) -> list[Post]:
    """마지막으로 본 글(없으면 그 앞 몇 개)을 읽어 게시판이 살아 있음을 보인다.

    글쓴이가 지워 버린 번호일 수도 있어 한 칸씩 거슬러 올라가며 본다.
    몇 칸을 봐도 안 열리면 그때는 정말 무언가 달라진 것이므로 빈 목록을
    돌려주어 실패로 남긴다.
    """
    for seq in range(last_seen, max(last_seen - ANCHOR_TRIES, 0), -1):
        post = _one(site, fetcher, seq)
        if post is not None:
            return [post]
    return []


parse_nanum.needs_fetcher = True
parse_nanum.needs_store = True  # 어디까지 봤는지 알아야 그 다음부터 짚어간다


def _one(site: Site, fetcher: Fetcher, seq: int) -> Post | None:
    """글 번호 하나를 열어 본다. 없는 번호면 None."""
    url = _detail_url(site.url, seq)
    try:
        html = fetcher.get_text(url)
    except Exception:
        return None  # 한 건 못 읽었다고 나머지까지 포기하지는 않는다

    box = BeautifulSoup(html, "html.parser").select_one("div.board-view-title")
    heading = box.select_one("h4") if box else None
    title = collapse(heading.get_text(" ", strip=True)) if heading else ""
    if not title:
        return None

    info = box.select_one("p.board-info")
    matched = INFO_RE.search(collapse(info.get_text(" ", strip=True))) if info else None
    return Post(
        site_key=site.key,
        site_name=site.name,
        post_id=str(seq),
        title=title,
        url=url,
        author=matched.group("author") if matched else "",
        posted_at=matched.group("date") if matched else "",
    )


def _detail_url(list_url: str, seq: int) -> str:
    """목록 주소에 mode=DETAIL&seq=<번호> 를 붙인다."""
    parsed = urlparse(list_url)
    query = dict(pair.split("=", 1) for pair in parsed.query.split("&") if "=" in pair)
    query.update({"mode": "DETAIL", "seq": str(seq)})
    return urlunparse(parsed._replace(query=urlencode(query)))
