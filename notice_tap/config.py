"""config.yaml 읽기/쓰기."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from .models import Site

DEFAULT_PATH = Path("config.yaml")

DEFAULT_CONFIG: dict[str, Any] = {
    "poll_interval_minutes": 30,
    "database": "data/notices.db",
    "dashboard_path": "dashboard.html",
    "notify_on_pinned": True,
    "stale_alert_days": 2,
    "notifiers": {
        "console": {"enabled": True},
        "windows": {"enabled": True},
        "kakao": {"enabled": False, "rest_api_key": "", "refresh_token": ""},
        "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
        "discord": {"enabled": False, "webhook_url": ""},
    },
    "sites": [],
}


class Config:
    def __init__(self, data: dict[str, Any], path: Path):
        self.data = data
        self.path = path

    # --- 파일 입출력 ----------------------------------------------------

    @classmethod
    def load(cls, path: str | Path = DEFAULT_PATH) -> "Config":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"{path} 가 없습니다. 먼저 `python -m notice_tap init` 을 실행하세요.")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(_merge(DEFAULT_CONFIG, _expand_env(raw)), path)

    @classmethod
    def create_default(cls, path: str | Path = DEFAULT_PATH) -> "Config":
        return cls(_merge(DEFAULT_CONFIG, {}), Path(path))

    def save(self) -> None:
        self.data["sites"] = [
            site if isinstance(site, dict) else site.to_dict() for site in self.data.get("sites", [])
        ]
        body = yaml.safe_dump(self.data, allow_unicode=True, sort_keys=False, width=200)
        self.path.write_text(self._leading_comments() + body, encoding="utf-8")

    def _leading_comments(self) -> str:
        """PyYAML 은 주석을 지우므로, 파일 맨 위 설명 블록만이라도 살려둔다."""
        if not self.path.exists():
            return ""
        kept: list[str] = []
        for line in self.path.read_text(encoding="utf-8").splitlines(keepends=True):
            if line.startswith("#") or not line.strip():
                kept.append(line)
            else:
                break
        return "".join(kept)

    # --- 접근자 ---------------------------------------------------------

    @property
    def sites(self) -> list[Site]:
        return [Site.from_dict(raw) for raw in self.data.get("sites", [])]

    @property
    def enabled_sites(self) -> list[Site]:
        return [site for site in self.sites if site.enabled]

    def add_site(self, site: Site) -> bool:
        """이미 등록된 URL이면 False."""
        if any(existing.key == site.key for existing in self.sites):
            return False
        self.data.setdefault("sites", []).append(site.to_dict())
        return True

    def remove_site(self, needle: str) -> Site | None:
        for index, site in enumerate(self.sites):
            if needle in (site.key, site.name, site.url):
                self.data["sites"].pop(index)
                return site
        return None

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


ENV_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _expand_env(value):
    """설정값이 `${VAR}` 이면 환경변수로 바꿔 넣는다.

    토큰을 파일에 적지 않고 GitHub Actions 의 Secrets 로 넘기기 위한 것이다.
    값이 없으면 빈 문자열이 되고, 그 채널은 조용히 꺼진다.
    """
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, str) and (match := ENV_REF.match(value.strip())):
        return os.environ.get(match.group(1), "")
    return value


def _merge(base: dict, override: dict) -> dict:
    """기본값 위에 사용자 설정을 덮어쓴다(중첩 딕셔너리 포함)."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out
