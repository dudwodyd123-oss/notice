"""설정을 읽어 활성화된 알림 채널을 만들어준다."""

from __future__ import annotations

from typing import Any

from .base import Notifier, NotifierUnavailable, group_by_site, plain_text
from .console import ConsoleNotifier
from .discord import DiscordNotifier
from .kakao import KakaoNotifier
from .telegram import TelegramNotifier
from .windows import WindowsNotifier

BUILDERS = {
    "console": lambda cfg: ConsoleNotifier(),
    "windows": lambda cfg: WindowsNotifier(
        dashboard_path=cfg.get("dashboard_path", "dashboard.html")
    ),
    "kakao": lambda cfg: KakaoNotifier(
        rest_api_key=cfg.get("rest_api_key", ""),
        refresh_token=cfg.get("refresh_token", ""),
        token_cache=cfg.get("token_cache", "data/kakao_token.json"),
        max_messages=cfg.get("max_messages", 8),
    ),
    "telegram": lambda cfg: TelegramNotifier(
        bot_token=cfg.get("bot_token", ""), chat_id=cfg.get("chat_id", "")
    ),
    "discord": lambda cfg: DiscordNotifier(webhook_url=cfg.get("webhook_url", "")),
}


def build_notifiers(config: dict[str, Any]) -> tuple[list[Notifier], list[str]]:
    """(사용 가능한 알림 채널, 설정 오류 메시지) 를 돌려준다."""
    notifiers: list[Notifier] = []
    problems: list[str] = []

    for name, settings in (config.get("notifiers") or {}).items():
        settings = settings or {}
        if not settings.get("enabled"):
            continue
        builder = BUILDERS.get(name)
        if builder is None:
            problems.append(f"알 수 없는 알림 채널 '{name}' (사용 가능: {', '.join(BUILDERS)})")
            continue
        try:
            notifiers.append(builder(settings))
        except NotifierUnavailable:
            continue  # 설정이 비었거나 이 OS 에서 못 쓰는 채널 - 경고할 일이 아니다
        except Exception as exc:
            problems.append(f"[{name}] 설정 오류: {exc}")

    return notifiers, problems


__all__ = [
    "BUILDERS",
    "ConsoleNotifier",
    "DiscordNotifier",
    "KakaoNotifier",
    "Notifier",
    "NotifierUnavailable",
    "TelegramNotifier",
    "WindowsNotifier",
    "build_notifiers",
    "group_by_site",
    "plain_text",
]
