"""부산대학교 통합 홈페이지 CMS(artclList.do) 게시판 파서.

부산대 대부분의 학과/기관 사이트가 같은 표준 프레임을 쓰기 때문에
이 파서 하나로 여러 학과 게시판을 동시에 처리할 수 있다.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Post, Site

ARTCL_ID_RE = re.compile(r"/(\d+)/artclView\.do")
# 목록에 붙는 장식용 배지("새글" 등)는 제목에서 떼어낸다.
BADGE_RE = re.compile(r"(새글|new)\s*$", re.IGNORECASE)


def parse_pnu(site: Site, html: str) -> list[Post]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.board-table tbody tr") or soup.select("table tbody tr")

    posts: list[Post] = []
    for row in rows:
        link = row.select_one("td.td-title a[href]") or row.select_one("td a[href*='artclView.do']")
        if link is None:
            continue

        href = link.get("href", "")
        match = ARTCL_ID_RE.search(href)
        if not match:
            continue

        title = _clean(link.get_text(" ", strip=True))
        if not title:
            continue

        posts.append(
            Post(
                site_key=site.key,
                site_name=site.name,
                post_id=match.group(1),
                title=title,
                url=urljoin(site.url, href),
                author=_cell(row, "td.td-write"),
                posted_at=_cell(row, "td.td-date"),
                category=_cell(row, "td.td-num span.notice-title"),
                pinned="notice" in (row.get("class") or []),
            )
        )
    return posts


def _cell(row, selector: str) -> str:
    node = row.select_one(selector)
    return _clean(node.get_text(" ", strip=True)) if node else ""


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return BADGE_RE.sub("", text).strip()
