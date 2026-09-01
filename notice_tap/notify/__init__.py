"""설정을 읽어 활성화된 알림 채널을 만들어준다."""

from __future__ import annotations

from typing import Any

from .base import Notifier, NotifierUnavailable, group_by_site
from .console import ConsoleNotifier
from .discord import DiscordNotifier

BUILDERS = {
    "console": lambda cfg: ConsoleNotifier(),
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
    "Notifier",
    "NotifierUnavailable",
    "build_notifiers",
    "group_by_site",
]
