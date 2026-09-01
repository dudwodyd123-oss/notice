"""CSS 선택자로 직접 지정하는 범용 게시판 파서.

sites.yaml 에서 사이트별로 선택자를 적어주면 어떤 게시판이든 읽을 수 있다:

    - name: 어느 학과 공지
      url: https://example.ac.kr/board/list
      parser: generic
      row_selector: "table.bbs tbody tr"
      title_selector: "td.subject a"
      date_selector: "td.date"
      author_selector: "td.writer"
      id_param: "nttId"        # 링크 쿼리스트링에서 글 번호를 뽑을 때
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from ..models import Post, Site
from ..text import node_text

DIGITS_RE = re.compile(r"(\d{2,})")


def parse_generic(site: Site, html: str) -> list[Post]:
    opts = site.options
    row_selector = opts.get("row_selector")
    if not row_selector:
        raise ValueError(f"[{site.name}] generic 파서에는 row_selector 설정이 필요합니다")

    title_selector = opts.get("title_selector", "a")
    soup = BeautifulSoup(html, "html.parser")

    posts: list[Post] = []
    for row in soup.select(row_selector):
        node = row.select_one(title_selector)
        if node is None:
            continue
        link = node if node.name == "a" else node.select_one("a[href]")
        href = link.get("href", "") if link else ""
        title = node_text(node)
        if not title or not href or href.startswith(("javascript:", "#")):
            continue

        url = urljoin(site.url, href)
        posts.append(
            Post(
                site_key=site.key,
                site_name=site.name,
                post_id=_post_id(url, opts),
                title=title,
                url=url,
                author=node_text(row.select_one(opts["author_selector"])) if opts.get("author_selector") else "",
                posted_at=node_text(row.select_one(opts["date_selector"])) if opts.get("date_selector") else "",
                category=node_text(row.select_one(opts["category_selector"])) if opts.get("category_selector") else "",
            )
        )
    return posts


def _post_id(url: str, opts: dict) -> str:
    """글마다 변하지 않는 고유 번호를 찾는다. 없으면 URL 해시로 대체한다."""
    if param := opts.get("id_param"):
        values = parse_qs(urlparse(url).query).get(param)
        if values:
            return values[0]

    if pattern := opts.get("id_regex"):
        if match := re.search(pattern, url):
            return match.group(1) if match.groups() else match.group(0)

    if match := DIGITS_RE.search(urlparse(url).path):
        return match.group(1)

    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
