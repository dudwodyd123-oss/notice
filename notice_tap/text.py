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


def is_muted(title: str, keywords: list[str], allow: list[str] | None = None) -> bool:
    """제목에 걸러낼 낱말이 들어 있는지. allow 에 걸리면 걸러내지 않는다.

    거르는 규칙은 여기 하나만 둔다. 화면에서 감추는 쪽과 알림을 막는 쪽이
    서로 다른 판단을 하면, 알림은 오는데 눌러 봐도 목록에 없는 글이 생긴다.

    '채용' 처럼 넓게 자르면 '채용 연계 해커톤' 같은 것까지 사라진다.
    그래서 넓게 자르되, 살려야 할 말을 따로 두어 되돌린다.
    """
    # 띄어쓰기는 글마다 제각각이다. '채용설명회' 와 '채용 설명회' 를 서로 다른
    # 말로 보면 규칙에 변형을 하나씩 다 적어 넣어야 한다. 공백을 지우고 견준다.
    packed = WHITESPACE.sub("", (title or "")).lower()

    def hits(words) -> bool:
        return any(
            packed_word in packed
            for word in words or []
            if (packed_word := WHITESPACE.sub("", str(word)).lower())
        )

    return hits(keywords) and not hits(allow)
