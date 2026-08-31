"""게시판마다 제각각인 날짜 표기를 하나의 형식(YYYY-MM-DD)으로 맞춘다.

사이트를 여러 개 모아 보려면 날짜를 서로 비교할 수 있어야 하는데,
게시판마다 `2026.08.28`, `2026-08-28`, `2026.01.05 09:15`, RSS 의
`Fri, 29 Aug 2026 10:00:00 +0900` 처럼 표기가 다르다.
"""

from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime

# 2026.08.28 / 2026-08-28 / 2026/8/5 …
YMD = re.compile(r"(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})")
# 26.08.28 처럼 연도가 두 자리인 경우
YY_MD = re.compile(r"^(\d{2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})")


def to_iso_date(raw: str) -> str:
    """어떤 표기든 'YYYY-MM-DD' 로 바꾼다. 알아볼 수 없으면 빈 문자열."""
    if not raw:
        return ""
    text = raw.strip()

    if match := YMD.search(text):
        return _build(*match.groups())

    if match := YY_MD.match(text):
        year, month, day = match.groups()
        return _build(f"20{year}", month, day)

    # RSS 의 pubDate 형식
    try:
        return parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError):
        pass

    # Atom 의 ISO 8601 형식
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return ""


def _build(year: str, month: str, day: str) -> str:
    try:
        return datetime(int(year), int(month), int(day)).date().isoformat()
    except ValueError:
        return ""  # 2026-13-45 같은 값
