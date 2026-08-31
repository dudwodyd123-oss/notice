"""RSS / Atom 피드 파서. 피드를 제공하는 사이트는 이게 가장 안정적이다."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET

from ..models import Post, Site

ATOM = "{http://www.w3.org/2005/Atom}"


def parse_rss(site: Site, body: str) -> list[Post]:
    root = ET.fromstring(body.strip())

    items = root.findall(".//item")
    if items:
        return [_from_rss_item(site, item) for item in items]

    entries = root.findall(f".//{ATOM}entry")
    return [_from_atom_entry(site, entry) for entry in entries]


def _from_rss_item(site: Site, item: ET.Element) -> Post:
    title = _text(item.find("title"))
    link = _text(item.find("link"))
    guid = _text(item.find("guid")) or link
    return Post(
        site_key=site.key,
        site_name=site.name,
        post_id=_stable_id(guid),
        title=title,
        url=link,
        author=_text(item.find("author")) or _text(item.find("{http://purl.org/dc/elements/1.1/}creator")),
        posted_at=_text(item.find("pubDate")),
    )


def _from_atom_entry(site: Site, entry: ET.Element) -> Post:
    link_node = entry.find(f"{ATOM}link")
    link = link_node.get("href", "") if link_node is not None else ""
    guid = _text(entry.find(f"{ATOM}id")) or link
    author = entry.find(f"{ATOM}author")
    return Post(
        site_key=site.key,
        site_name=site.name,
        post_id=_stable_id(guid),
        title=_text(entry.find(f"{ATOM}title")),
        url=link,
        author=_text(author.find(f"{ATOM}name")) if author is not None else "",
        posted_at=_text(entry.find(f"{ATOM}updated")) or _text(entry.find(f"{ATOM}published")),
    )


def _stable_id(raw: str) -> str:
    if match := re.search(r"(\d{3,})", raw):
        return match.group(1)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return re.sub(r"\s+", " ", node.text).strip()
