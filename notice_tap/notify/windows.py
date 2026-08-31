"""윈도우 알림(토스트). 토큰도 가입도 필요 없이 바로 동작한다.

알림을 클릭하면 해당 게시글이 기본 브라우저에서 바로 열린다.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import xml.sax.saxutils as saxutils
from pathlib import Path

from ..models import Post
from .base import Notifier, NotifierUnavailable, group_by_site

MAX_TOASTS = 5  # 이보다 많으면 요약 한 통으로 묶는다

# 알림 내용은 스크립트에 글자로 끼워 넣지 않고 별도 파일에서 읽는다.
# 게시글 제목은 남의 사이트에서 가져온 값이라, 스크립트 안에 그대로 넣으면
# 제목에 줄바꿈과 따옴표를 섞어 PowerShell 명령을 실행시킬 수 있다.
PS_SCRIPT = """\
$ErrorActionPreference = 'Stop'
$null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime]
$null = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime]
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Microsoft.Windows.Computer')

$payload = Get-Content -LiteralPath $args[0] -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($item in $payload) {
    $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
    $doc.LoadXml($item)
    $notifier.Show((New-Object Windows.UI.Notifications.ToastNotification $doc))
    Start-Sleep -Milliseconds 400
}
"""


class WindowsNotifier(Notifier):
    name = "windows"

    def __init__(self, dashboard_path: str = "dashboard.html", timeout: int = 60):
        if sys.platform != "win32":
            # GitHub Actions(리눅스) 처럼 윈도우가 아닌 곳에서는 그냥 빠진다.
            raise NotifierUnavailable("윈도우에서만 쓸 수 있는 알림입니다")
        self.dashboard_path = dashboard_path
        self.timeout = timeout

    def send(self, posts: list[Post]) -> None:
        _run_powershell(self._toasts(posts), self.timeout)

    def _toasts(self, posts: list[Post]) -> list[str]:
        if len(posts) > MAX_TOASTS:
            grouped = group_by_site(posts)
            detail = ", ".join(f"{name} {len(group)}건" for name, group in grouped.items())
            return [_toast_xml("새 공지 " + str(len(posts)) + "건", detail, self._dashboard_uri())]

        return [
            _toast_xml(post.site_name, post.title, post.url, post.posted_at) for post in posts
        ]

    def _dashboard_uri(self) -> str:
        return Path(self.dashboard_path).resolve().as_uri()


def _toast_xml(heading: str, body: str, launch: str, footer: str = "") -> str:
    lines = [
        f"    <text>{saxutils.escape(heading)}</text>",
        f"    <text>{saxutils.escape(body)}</text>",
    ]
    if footer:
        lines.append(f"    <text placement='attribution'>{saxutils.escape(footer)}</text>")

    return (
        f'<toast activationType="protocol" launch="{saxutils.quoteattr(launch)[1:-1]}">\n'
        "  <visual><binding template=\"ToastGeneric\">\n"
        + "\n".join(lines)
        + "\n  </binding></visual>\n</toast>"
    )


def _run_powershell(toasts: list[str], timeout: int) -> None:
    """알림 XML 은 JSON 파일로 건네고, 스크립트는 고정된 내용만 실행한다."""
    # 한글이 깨지지 않도록 BOM 붙은 UTF-8 파일로 넘긴다.
    with tempfile.NamedTemporaryFile(
        "w", suffix=".ps1", delete=False, encoding="utf-8-sig"
    ) as handle:
        handle.write(PS_SCRIPT)
        script_path = handle.name

    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8-sig"
    ) as handle:
        json.dump(toasts, handle, ensure_ascii=False)
        data_path = handle.name

    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", script_path, data_path,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise RuntimeError(f"윈도우 알림 실패: {(result.stderr or result.stdout).strip()[:300]}")
    finally:
        Path(script_path).unlink(missing_ok=True)
        Path(data_path).unlink(missing_ok=True)
