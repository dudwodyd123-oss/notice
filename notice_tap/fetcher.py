"""HTTP 가져오기 - 재시도와 한글 인코딩 처리를 포함."""

from __future__ import annotations

import time

import requests

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class FetchError(RuntimeError):
    pass


class Fetcher:
    def __init__(self, user_agent: str = DEFAULT_UA, timeout: int = 20, retries: int = 3):
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            }
        )

    def get_text(self, url: str) -> str:
        """페이지 본문을 문자열로 반환한다. 인코딩은 스스로 추정한다."""
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                resp.raise_for_status()
                return _decode(resp)
            except Exception as exc:  # 네트워크는 종종 흔들린다
                last = exc
                if attempt < self.retries - 1:
                    time.sleep(1.5 * (attempt + 1))
        raise FetchError(f"{url} 가져오기 실패: {last}") from last

    def close(self) -> None:
        self.session.close()


def _decode(resp: requests.Response) -> str:
    """국내 사이트는 euc-kr/cp949가 섞여 있어 헤더만 믿을 수 없다."""
    declared = (resp.encoding or "").lower()
    if declared in ("", "iso-8859-1"):
        # requests가 헤더에 charset이 없으면 iso-8859-1로 찍는다. 본문을 보고 정한다.
        guessed = (resp.apparent_encoding or "utf-8").lower()
        resp.encoding = "cp949" if guessed in ("euc-kr", "ks_c_5601-1987") else guessed
    elif declared in ("euc-kr", "ks_c_5601-1987"):
        resp.encoding = "cp949"  # cp949가 euc-kr의 상위 집합이라 더 안전하다
    return resp.text
