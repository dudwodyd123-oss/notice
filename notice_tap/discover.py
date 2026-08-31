"""게시판 URL 하나만 붙여넣으면 감시 설정을 알아서 만들어 준다.

부산대 통합 CMS 의 `subview.do?enc=...` 주소는 enc 값이 base64 라서
실제 게시판 목록 주소(`/bbs/{code}/{id}/artclList.do`)를 그대로 복원할 수 있다.
"""

from __future__ import annotations

import base64
import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from .fetcher import Fetcher
from .models import Site
from .parsers import get_parser

ARTCL_LIST_RE = re.compile(r"/bbs/[^/]+/\d+/artclList\.do")


class DiscoveryError(RuntimeError):
    pass


def discover(url: str, fetcher: Fetcher, name: str | None = None) -> Site:
    """URL 을 보고 파서와 목록 주소를 결정한 뒤 Site 를 만든다."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    list_url = _resolve_pnu_list_url(url)
    if list_url:
        # 목록 엔드포인트는 제목이 '부산대학교' 로만 나와서, 사용자가 붙여넣은
        # 원래 페이지(subview.do)의 제목이 있으면 그쪽을 더 신뢰한다.
        label = _page_title(fetcher, url) if url != list_url else ""
        label = label or _page_title(fetcher, list_url)
        site = Site(name=name or _label(label, list_url), url=list_url, parser="pnu")
        _verify(site, fetcher)
        return site

    body = fetcher.get_text(url)

    if _looks_like_feed(body):
        site = Site(name=name or _label(_feed_title(body), url), url=url, parser="rss")
        _verify(site, fetcher, body)
        return site

    # 페이지 안에 부산대 CMS 게시판 링크가 들어 있는 경우 (메뉴 페이지 등)
    if found := _find_embedded_list_url(url, body):
        site = Site(name=name or _label(_title_of(body), found), url=found, parser="pnu")
        _verify(site, fetcher)
        return site

    guess = _guess_generic(url, body)
    if guess is None:
        raise DiscoveryError(
            "이 주소에서는 게시판 표를 자동으로 찾지 못했습니다.\n"
            "config.yaml 에 parser: generic 과 row_selector 를 직접 적어주세요 "
            "(notice_tap/parsers/generic.py 상단에 예시가 있습니다)."
        )
    site = Site(name=name or _label(_title_of(body), url), url=url, parser="generic", options=guess)
    _verify(site, fetcher, body)
    return site


# --- 부산대 CMS 주소 해석 ------------------------------------------------


def _resolve_pnu_list_url(url: str) -> str | None:
    if ARTCL_LIST_RE.search(urlparse(url).path):
        return url

    enc = parse_qs(urlparse(url).query).get("enc")
    if not enc:
        return None

    decoded = _decode_enc(enc[0])
    if decoded and ARTCL_LIST_RE.search(decoded):
        # page 번호 등 붙어 있는 파라미터는 떼고 1페이지만 본다.
        return urljoin(url, decoded.split("?")[0])
    return None


def _decode_enc(value: str) -> str | None:
    padded = value + "=" * (-len(value) % 4)
    try:
        raw = base64.b64decode(padded).decode("utf-8", "replace")
    except Exception:
        return None
    # 형식: fnct1|@@|%2Fbbs%2Fcse%2F2055%2FartclList.do%3F...
    part = raw.split("|@@|")[-1]
    return unquote(part)


def _find_embedded_list_url(base_url: str, body: str) -> str | None:
    if match := ARTCL_LIST_RE.search(body):
        return urljoin(base_url, match.group(0))
    for enc in re.findall(r"subview\.do\?enc=([A-Za-z0-9+/=]{20,})", body):
        decoded = _decode_enc(enc)
        if decoded and ARTCL_LIST_RE.search(decoded):
            return urljoin(base_url, decoded.split("?")[0])
    return None


# --- 기타 형식 -----------------------------------------------------------


def _looks_like_feed(body: str) -> bool:
    head = body.lstrip()[:400].lower()
    return head.startswith("<?xml") and ("<rss" in head or "<feed" in head)


def _feed_title(body: str) -> str:
    match = re.search(r"<title>(.*?)</title>", body, re.DOTALL)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def _guess_generic(url: str, body: str) -> dict | None:
    """상세 링크가 가장 많이 들어 있는 표를 게시판으로 본다."""
    soup = BeautifulSoup(body, "html.parser")
    best, best_score = None, 0
    for index, table in enumerate(soup.select("table")):
        rows = table.select("tbody tr") or table.select("tr")
        linked = [row for row in rows if row.select_one("td a[href]")]
        if len(linked) > best_score:
            best, best_score = (table, index), len(linked)

    if best is None or best_score < 3:
        return None

    table, index = best
    selector = _selector_for(table, index)
    return {"row_selector": f"{selector} tr", "title_selector": "a"}


def _selector_for(table, index: int) -> str:
    if table_id := table.get("id"):
        return f"table#{table_id} tbody" if table.find("tbody") else f"table#{table_id}"
    if classes := table.get("class"):
        base = "table." + ".".join(classes)
        return f"{base} tbody" if table.find("tbody") else base
    return f"table:nth-of-type({index + 1}) tbody"


def _label(title: str, url: str) -> str:
    """'공지사항' 처럼 흔한 제목만으로는 사이트를 구분할 수 없어 호스트명을 붙인다."""
    host = urlparse(url).hostname or url
    title = re.sub(r"\s+", " ", title).strip()
    if title and title not in ("부산대학교", host):
        return f"{title} ({host})"

    # 제목을 못 믿을 때는 게시판 번호라도 붙여 서로 구분되게 한다.
    if match := re.search(r"/bbs/[^/]+/(\d+)/", urlparse(url).path):
        return f"{host} 게시판 {match.group(1)}"
    return host


def _title_of(body: str) -> str:
    soup = BeautifulSoup(body, "html.parser")
    return soup.title.get_text(strip=True) if soup.title else ""


def _page_title(fetcher: Fetcher, url: str) -> str:
    try:
        return _title_of(fetcher.get_text(url))
    except Exception:
        return ""


def _verify(site: Site, fetcher: Fetcher, body: str | None = None) -> None:
    """설정이 실제로 글을 뽑아내는지 확인한다."""
    body = body if body is not None else fetcher.get_text(site.url)
    posts = get_parser(site.parser)(site, body)
    if not posts:
        raise DiscoveryError(
            f"'{site.parser}' 파서로 {site.url} 에서 글을 하나도 찾지 못했습니다. "
            "config.yaml 에서 설정을 직접 조정해 주세요."
        )
