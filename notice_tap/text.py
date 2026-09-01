"""게시판에서 긁어온 글자를 다듬는 공통 도구.

파서마다 따로 두면 새 게시판을 붙일 때 빠뜨리기 쉬워 한곳에 모았다.
줄바꿈을 없애는 것은 보기 좋으라고만 하는 일이 아니다. 제목은 남의
사이트에서 오는 값이라, 여러 줄짜리 제목이 그대로 흘러 들어가면
알림 문구나 스크립트를 망가뜨리는 데 쓰일 수 있다.
"""

from __future__ import annotations

import re

WHITESPACE = re.compile(r"\s+")


def collapse(value: object) -> str:
    """모든 공백·줄바꿈을 한 칸으로 줄이고 양끝을 정리한 한 줄 문자열."""
    if value is None:
        return ""
    return WHITESPACE.sub(" ", str(value)).strip()


def node_text(node) -> str:
    """BeautifulSoup 노드의 글자. 노드가 없으면 빈 문자열."""
    return collapse(node.get_text(" ", strip=True)) if node is not None else ""
