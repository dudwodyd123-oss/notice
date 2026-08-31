"""카카오톡 '나에게 보내기' 최초 인증 도우미 (한 번만 실행하면 됩니다).

미리 해둘 일 — https://developers.kakao.com 에서:
  1. 내 애플리케이션 > 애플리케이션 추가하기
  2. 앱 설정 > 플랫폼 > Web > 사이트 도메인에 `http://localhost:5000` 등록
  3. 제품 설정 > 카카오 로그인 > 활성화 ON
     · Redirect URI 에 `http://localhost:5000/oauth` 등록
  4. 제품 설정 > 카카오 로그인 > 동의항목 > '카카오톡 메시지 전송(talk_message)' 사용 설정
  5. 앱 설정 > 앱 키 > REST API 키 복사

그 다음 이 파일을 실행하면 브라우저가 열리고, 로그인하면
refresh_token 이 config.yaml 에 자동으로 저장됩니다.
"""

from __future__ import annotations

import http.server
import json
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests
import yaml

REDIRECT_URI = "http://localhost:5000/oauth"
PORT = 5000
AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
CONFIG_PATH = Path("config.yaml")
TOKEN_CACHE = Path("data/kakao_token.json")

_received: dict[str, str] = {}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (표준 라이브러리 규약)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _received.update({k: v[0] for k, v in query.items()})

        body = (
            "<h2>인증이 끝났습니다. 이 창을 닫고 터미널로 돌아가세요.</h2>"
            if "code" in query
            else f"<h2>인증 실패</h2><p>{query}</p>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"<meta charset='utf-8'>{body}".encode("utf-8"))

    def log_message(self, *args) -> None:
        pass  # 콘솔을 조용히 유지한다


def read_rest_api_key() -> str:
    if CONFIG_PATH.exists():
        config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        key = ((config.get("notifiers") or {}).get("kakao") or {}).get("rest_api_key", "")
        if key:
            print(f"config.yaml 의 REST API 키를 사용합니다 ({key[:6]}…)")
            return key
    return input("카카오 REST API 키를 붙여넣으세요: ").strip()


def wait_for_code(timeout: int = 180) -> str:
    server = http.server.HTTPServer(("127.0.0.1", PORT), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    deadline = time.time() + timeout
    while time.time() < deadline:
        if "code" in _received:
            break
        if "error" in _received:
            server.shutdown()
            raise SystemExit(f"인증이 거부되었습니다: {_received.get('error_description', _received['error'])}")
        time.sleep(0.3)
    else:
        server.shutdown()
        raise SystemExit("시간 안에 인증이 끝나지 않았습니다. 다시 실행해 주세요.")

    server.shutdown()
    return _received["code"]


def exchange(rest_api_key: str, code: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": rest_api_key,
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
        timeout=15,
    )
    if not resp.ok:
        raise SystemExit(f"토큰 발급 실패 ({resp.status_code}): {resp.text}")
    return resp.json()


def save(rest_api_key: str, tokens: dict) -> None:
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(
        json.dumps(
            {
                "access_token": tokens["access_token"],
                "expires_at": time.time() + tokens.get("expires_in", 21600),
                "refresh_token": tokens["refresh_token"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if not CONFIG_PATH.exists():
        print(f"\nconfig.yaml 이 없어 토큰만 {TOKEN_CACHE} 에 저장했습니다.")
        return

    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    kakao = (config.get("notifiers") or {}).get("kakao") or {}

    # config.yaml 은 GitHub 에 올라가는 파일이다. 값을 환경변수로 받도록
    # 설정해 두었다면 토큰을 파일에 적지 않고 그대로 둔다.
    if str(kakao.get("refresh_token", "")).startswith("${"):
        print("\nconfig.yaml 이 토큰을 환경변수에서 읽도록 설정되어 있어 파일은 건드리지 않았습니다.")
        print("GitHub 저장소 Settings → Secrets and variables → Actions 에 아래 두 개를 등록하세요:\n")
        print(f"  KAKAO_REST_API_KEY   = {rest_api_key}")
        print(f"  KAKAO_REFRESH_TOKEN  = {tokens['refresh_token']}")
        print(f"\n(내 PC 에서만 쓸 거라면 토큰은 {TOKEN_CACHE} 에 이미 저장돼 있습니다.)")
        return

    config.setdefault("notifiers", {}).setdefault("kakao", {}).update(
        {
            "enabled": True,
            "rest_api_key": rest_api_key,
            "refresh_token": tokens["refresh_token"],
        }
    )
    CONFIG_PATH.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8"
    )
    print("config.yaml 에 refresh_token 을 저장하고 카카오 알림을 켰습니다.")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    rest_api_key = read_rest_api_key()
    if not rest_api_key:
        print("REST API 키가 필요합니다.")
        return 1

    params = urllib.parse.urlencode(
        {
            "client_id": rest_api_key,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "talk_message",
        }
    )
    url = f"{AUTH_URL}?{params}"
    print("\n브라우저에서 카카오 로그인 창을 엽니다.")
    print("창이 자동으로 열리지 않으면 아래 주소를 직접 붙여넣으세요:\n")
    print(url + "\n")
    webbrowser.open(url)

    code = wait_for_code()
    tokens = exchange(rest_api_key, code)
    save(rest_api_key, tokens)

    print("\n끝났습니다. `python -m notice_tap test-notify` 로 확인해 보세요.")
    print("refresh_token 은 약 2개월간 유효하며, 그 안에 알림이 한 번이라도 나가면 자동 연장됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
