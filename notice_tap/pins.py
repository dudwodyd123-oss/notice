"""핀 목록을 저장소에 적어 두고 모든 기기에서 같이 본다.

예전에는 핀을 브라우저(localStorage)에만 적었다. 정적 페이지라 서버에 쓸
곳이 없었기 때문인데, 그러면 폰에서 꽂은 핀이 컴에서 안 보이고 브라우저
기록을 지우면 날아간다.

지금은 화면의 핀 단추가 깃허브 이슈를 열고, 그 이슈를 보고 자동 실행이
이 파일을 고친다. 브라우저에 토큰을 두지 않아도 되는 것이 요점이다 -
'이 사람이 주인이 맞다'는 확인을 깃허브 로그인이 대신해 준다.

글 내용을 통째로 담아 두므로, 보관 기간이 지나 목록에서 빠진 글도 핀을
뽑기 전까지 계속 보여줄 수 있다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path("data/pins.json")

ADD, REMOVE = "add", "remove"
# 이슈 본문에 적히는 지시. 뒤에 글 정보(JSON)가 한 줄로 이어진다.
COMMAND_RE = re.compile(r"pin:(add|remove)\b")
# 글 번호는 '게시판키:글번호' 꼴이다. 게시판 키는 설정에서 직접 적을 수도
# 있어 16진수로 못 박지 않고, 공백 없는 짧은 글자인지만 본다.
UID_RE = re.compile(r"^[\w.-]{1,64}:[^\s]{1,120}$")

# 남의 사이트에서 온 글자가 그대로 들어오므로 길이를 잘라 둔다.
LIMITS = {"uid": 160, "title": 300, "url": 500, "site": 100, "sub": 300, "bp": 1}


def load(path: str | Path = DEFAULT_PATH) -> list[dict[str, str]]:
    """핀 목록을 읽는다. 파일이 없거나 깨졌으면 빈 목록."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    pins = data.get("pins") if isinstance(data, dict) else None
    return [clean for pin in pins or [] if (clean := _clean(pin))]


def save(pins: list[dict[str, str]], path: str | Path = DEFAULT_PATH) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # 줄 단위로 정렬해 두면 git 이 변경분을 작게 잡는다.
    out.write_text(
        json.dumps({"version": 1, "pins": pins}, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8",
    )
    return out


def apply_issue(body: str, pins: list[dict[str, str]]) -> tuple[list[dict[str, str]], str]:
    """이슈 본문을 읽어 핀을 더하거나 뺀다. (새 목록, 사람에게 보일 말)

    본문이 엉뚱하면 목록을 그대로 돌려준다. 알아듣지 못한 것을 넘겨짚어
    핀을 건드리느니 아무것도 안 하는 편이 낫다.
    """
    matched = COMMAND_RE.search(body or "")
    if not matched:
        return pins, "무엇을 하라는 것인지 알 수 없어 그대로 두었습니다."

    action = matched.group(1)
    payload = _payload(body[matched.end():])
    if payload is None:
        return pins, "글 정보를 읽지 못해 그대로 두었습니다."

    uid = payload["uid"]
    kept = [pin for pin in pins if pin["uid"] != uid]
    if action == REMOVE:
        if len(kept) == len(pins):
            return pins, "이미 핀이 꽂혀 있지 않습니다."
        return kept, f"핀을 뽑았습니다 — {payload.get('title') or uid}"

    return kept + [payload], f"핀을 꽂았습니다 — {payload.get('title') or uid}"


def _payload(text: str) -> dict[str, str] | None:
    """지시 뒤에 붙은 글 정보(JSON). uid 만 적혀 있어도 받아 준다."""
    body = text.strip()
    if not body:
        return None

    if body.startswith("{"):
        try:
            raw = json.loads(body)
        except ValueError:
            return None
        return _clean(raw)

    return _clean({"uid": body.splitlines()[0].strip()})


def _clean(raw: Any) -> dict[str, str] | None:
    """믿을 수 없는 값이므로 모양을 확인하고 길이를 자른다."""
    if not isinstance(raw, dict):
        return None
    uid = str(raw.get("uid", "")).strip()
    if not UID_RE.match(uid):
        return None

    url = str(raw.get("url", "")).strip()
    if url and not url.startswith(("http://", "https://")):
        url = ""  # 화면에서 누를 주소다. http(s) 가 아니면 버린다

    pin = {"uid": uid, "url": url[: LIMITS["url"]]}
    for key in ("title", "site", "sub", "bp"):
        pin[key] = str(raw.get(key, "")).strip()[: LIMITS[key]]
    return pin
