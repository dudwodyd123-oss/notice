"""게시판 종류별 파서 모음."""

from __future__ import annotations

from typing import Callable

from ..models import Post, Site
from .generic import parse_generic
from .pnu import parse_pnu
from .rss import parse_rss

Parser = Callable[[Site, str], list[Post]]

PARSERS: dict[str, Parser] = {
    "pnu": parse_pnu,
    "generic": parse_generic,
    "rss": parse_rss,
}


def get_parser(name: str) -> Parser:
    try:
        return PARSERS[name]
    except KeyError:
        known = ", ".join(sorted(PARSERS))
        raise ValueError(f"알 수 없는 파서 '{name}'. 사용 가능: {known}") from None


__all__ = ["PARSERS", "Parser", "get_parser", "parse_generic", "parse_pnu", "parse_rss"]
