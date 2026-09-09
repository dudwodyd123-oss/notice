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
      pinned_class: "isnotice" # 위에 고정된 공지 줄에 붙는 class
      pages: 2                 # 몇 페이지까지 읽을지 (기본 1)
      page_param: "page"       # 페이지 번호를 넘길 쿼리스트링 이름
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from ..fetcher import Fetcher
from ..models import Post, Site
from ..text import node_text

DIGITS_RE = re.compile(r"(\d{2,})")


def parse_generic(site: Site, fetcher: Fetcher) -> list[Post]:
    """설정한 페이지 수만큼 목록을 읽어 합친다.

    첫 페이지만 읽으면, 고정공지가 자리를 많이 차지하는 게시판에서는 실제로
    돌아가는 자리가 몇 칸 안 남는다. 그 사이에 글이 몰리면 확인하기도 전에
    목록 밖으로 밀려나고, 그렇게 놓친 글은 영영 알 수 없다.
    """
    pages = max(int(site.options.get("pages", 1)), 1)
    param = site.options.get("page_param", "page")

    posts: dict[str, Post] = {}
    for number in range(1, pages + 1):
        url = site.url if number == 1 else _with_page(site.url, param, number)
        for post in _parse_page(site, fetcher.get_text(url)):
            posts.setdefault(post.post_id, post)  # 페이지가 겹쳐도 한 번만
    return list(posts.values())


parse_generic.needs_fetcher = True  # 여러 페이지를 직접 받아와야 한다


def _with_page(url: str, param: str, number: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query[param] = [str(number)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _parse_page(site: Site, html: str) -> list[Post]:
    opts = site.options
    row_selector = opts.get("row_selector")
    if not row_selector:
        raise ValueError(f"[{site.name}] generic 파서에는 row_selector 설정이 필요합니다")

    title_selector = opts.get("title_selector", "a")
    # 고정공지 줄에만 붙는 class. 적어두면 화면에 '고정' 표시가 붙는다.
    pinned_class = opts.get("pinned_class", "")
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
                pinned=bool(pinned_class) and pinned_class in (row.get("class") or []),
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
