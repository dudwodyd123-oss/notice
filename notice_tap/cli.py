"""notice_tap 명령줄 인터페이스."""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

from . import __version__
from .checker import CheckResult, Checker
from .config import DEFAULT_PATH, Config
from .dashboard import render_dashboard
from .discover import DiscoveryError, discover
from .fetcher import Fetcher
from .models import Site
from .notify import build_notifiers
from .parsers import PARSERS
from .store import Store

SAMPLE_COMMENT = """\
# notice_tap 설정 파일
#
#  게시판은 `python -m notice_tap add <게시판 주소>` 로 추가하는 편이 편합니다.
#  알림을 켜려면 아래 notifiers 에서 enabled 를 true 로 바꾸고 값을 채우세요.
#  자세한 설명은 README.md 를 보세요.
"""


# --- 명령 ----------------------------------------------------------------


def cmd_init(args) -> int:
    path = Path(args.config)
    if path.exists() and not args.force:
        print(f"{path} 가 이미 있습니다. 덮어쓰려면 --force 를 붙이세요.")
        return 1

    config = Config.create_default(path)
    config.save()
    path.write_text(SAMPLE_COMMENT + path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"{path} 를 만들었습니다.")
    print("다음: python -m notice_tap add <게시판 주소>")
    return 0


def cmd_add(args) -> int:
    config = Config.load(args.config)
    fetcher = Fetcher()
    added = 0

    for url in args.urls:
        try:
            if args.parser:
                site = Site(name=args.name or url, url=url, parser=args.parser)
            else:
                site = discover(url, fetcher, name=args.name)
        except (DiscoveryError, OSError, ValueError, RuntimeError) as exc:
            print(f"  실패  {url}")
            print(f"        {exc}")
            continue

        if config.add_site(site):
            print(f"  추가  {site.name}")
            print(f"        {site.url}  (parser: {site.parser})")
            added += 1
        else:
            print(f"  중복  {site.name} — 이미 등록되어 있습니다.")

    fetcher.close()
    if added:
        config.save()
        print(f"\n{added}개 게시판을 등록했습니다. `python -m notice_tap check` 로 확인하세요.")
    return 0 if added else 1


def cmd_list(args) -> int:
    config = Config.load(args.config)
    sites = config.sites
    if not sites:
        print("등록된 게시판이 없습니다. `python -m notice_tap add <주소>` 로 추가하세요.")
        return 0

    store = Store(config.get("database"))
    states = store.site_states()

    print(f"등록된 게시판 {len(sites)}개\n")
    for site in sites:
        state = states.get(site.key)
        flag = "사용" if site.enabled else "중지"
        print(f" [{flag}] {site.name}")
        print(f"     {site.url}")
        print(f"     parser={site.parser}  key={site.key}  저장된 글={store.count(site.key)}건")
        if state:
            status = f"오류: {state['last_error']}" if state["last_error"] else "정상"
            print(f"     마지막 확인 {state['last_check'] or '-'} — {status}")
        print()
    store.close()
    return 0


def cmd_remove(args) -> int:
    config = Config.load(args.config)
    site = config.remove_site(args.target)
    if site is None:
        print(f"{args.target} 에 해당하는 게시판을 찾지 못했습니다.")
        return 1

    config.save()
    if args.purge:
        store = Store(config.get("database"))
        removed = store.forget_site(site.key)
        store.close()
        print(f"{site.name} 삭제 (저장된 글 {removed}건도 함께 지움)")
    else:
        print(f"{site.name} 삭제")
    return 0


def cmd_check(args) -> int:
    config = Config.load(args.config)
    if not config.enabled_sites:
        print("확인할 게시판이 없습니다. `python -m notice_tap add <주소>` 로 추가하세요.")
        return 1

    notifiers, problems = build_notifiers(config.data)
    for problem in problems:
        print(f"  경고  {problem}")

    checker = Checker(config)
    print(f"게시판 {len(config.enabled_sites)}개 확인 중…")
    result = checker.check_all(notify_first_run=args.notify_first_run)
    _report(result)

    if not args.no_notify:
        _deliver(config, checker, notifiers)

    path = render_dashboard(checker.store, config.get("dashboard_path", "dashboard.html"))
    _alert_stale(config, checker, notifiers, muted=args.no_notify, dashboard=path)
    print(f"\n모아보기 페이지: {path.resolve()}")
    checker.close()
    return 0


def _deliver(config: Config, checker: Checker, notifiers) -> None:
    """아직 못 보낸 글을 알린다. 모든 채널이 성공했을 때만 '보냄' 으로 표시한다.

    전송에 실패한 글은 표시하지 않고 남겨두어 다음 실행에서 다시 시도한다.
    알림이 조용히 사라지는 것보다 늦게라도 도착하는 편이 낫다.
    """
    channels = [n for n in notifiers if n.name != "console"]  # 콘솔은 이미 출력했다
    pending = checker.store.pending_posts([site.key for site in config.enabled_sites])
    if not pending:
        return

    if not channels:
        print(f"  보낼 채널이 없어 {len(pending)}건을 보류합니다 (다음 실행에서 다시 시도)")
        return

    delivered = True
    for notifier in channels:
        try:
            notifier.send(pending)
            print(f"  알림 전송 완료 → {notifier.name} ({len(pending)}건)")
        except Exception as exc:
            delivered = False
            print(f"  알림 실패 ({notifier.name}): {exc}")

    if delivered:
        checker.store.mark_notified(pending)
    else:
        print(f"  {len(pending)}건을 보류합니다 — 다음 실행에서 다시 보냅니다")


def _alert_stale(config: Config, checker: Checker, notifiers, muted: bool, dashboard: Path) -> None:
    """며칠째 계속 실패하는 게시판이 있으면 알린다.

    파싱이 깨지면 겉으로는 '새 글 없음'과 구분되지 않아 조용히 방치되기 쉽다.
    """
    days = config.get("stale_alert_days", 2)
    known = {site.key: site.name for site in config.sites}
    stale = [row for row in checker.store.stale_sites(days) if row["site_key"] in known]
    if not stale:
        return

    lines = []
    for row in stale:
        since = (row["fail_since"] or "")[:10]
        reason = (row["last_error"] or "").splitlines()[0][:90]
        lines.append(f"{known[row['site_key']]} — {since}부터 실패")
        lines.append(f"  {reason}")

    heading = f"공지 확인이 {days}일 넘게 실패 중 ({len(stale)}곳)"
    body = "\n".join(lines)

    print(f"\n  ⚠ {heading}")
    for line in lines:
        print(f"    {line}")

    if muted:
        return

    link = dashboard.resolve().as_uri()
    for notifier in notifiers:
        if notifier.name == "console":
            continue  # 바로 위에서 이미 출력했다
        try:
            notifier.send_alert(heading, body, link)
        except Exception as exc:
            print(f"  오류 알림 실패 ({notifier.name}): {exc}")

    for row in stale:
        checker.store.mark_alerted(row["site_key"])


def cmd_watch(args) -> int:
    config = Config.load(args.config)
    interval = args.interval or config.get("poll_interval_minutes", 30)
    print(f"{interval}분마다 확인합니다. 중단하려면 Ctrl+C.\n")

    while True:
        print(f"── {time.strftime('%Y-%m-%d %H:%M:%S')} ─────────────────────")
        try:
            cmd_check(args)
        except Exception as exc:
            print(f"  이번 회차 실패: {exc}")
        print()
        time.sleep(interval * 60)


def cmd_dashboard(args) -> int:
    config = Config.load(args.config)
    store = Store(config.get("database"))
    path = render_dashboard(store, config.get("dashboard_path", "dashboard.html"))
    store.close()
    print(f"모아보기 페이지: {path.resolve()}")
    if args.open:
        webbrowser.open(path.resolve().as_uri())
    return 0


def cmd_export(args) -> int:
    config = Config.load(args.config)
    store = Store(config.get("database"))
    data = store.export_state()
    store.close()

    path = Path(args.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 줄 단위로 정렬해 두면 git 이 변경분을 작게 잡는다.
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
    )
    print(f"글 {len(data['posts'])}건을 {path} 로 내보냈습니다.")
    return 0


def cmd_import(args) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"{path} 가 없습니다. 처음 실행이면 그냥 넘어가도 됩니다.")
        return 0

    config = Config.load(args.config)
    store = Store(config.get("database"))
    count = store.import_state(json.loads(path.read_text(encoding="utf-8")))
    store.close()
    print(f"{path} 에서 글 {count}건을 불러왔습니다.")
    return 0


def cmd_test_notify(args) -> int:
    config = Config.load(args.config)
    notifiers, problems = build_notifiers(config.data)
    for problem in problems:
        print(f"  경고  {problem}")
    if not notifiers:
        print("켜져 있는 알림 채널이 없습니다. config.yaml 의 notifiers 를 확인하세요.")
        return 1

    failed = 0
    for notifier in notifiers:
        try:
            notifier.send_test()
            print(f"  성공  {notifier.name}")
        except Exception as exc:
            failed += 1
            print(f"  실패  {notifier.name}: {exc}")
    return 1 if failed else 0


# --- 출력 도우미 ----------------------------------------------------------


def _report(result: CheckResult) -> None:
    for outcome in result.sites:
        name = outcome.site.name
        if outcome.error:
            print(f"  오류  {name}: {outcome.error}")
        elif outcome.baseline:
            print(f"  기준  {name} — 기존 글 {outcome.total_seen}건을 기준점으로 저장 (알림 없음)")
        elif outcome.new_posts:
            print(f"  새글  {name} — {len(outcome.new_posts)}건")
            for post in outcome.new_posts:
                date = f"{post.posted_at}  " if post.posted_at else ""
                print(f"          {date}{post.title}")
                print(f"          {post.url}")
        else:
            print(f"  없음  {name}")

    total = len(result.new_posts)
    tail = f", 오류 {len(result.errors)}건" if result.errors else ""
    print(f"\n새 글 {total}건{tail}")


# --- 인자 파서 ------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="notice_tap",
        description="여러 학과/기관 공지 게시판을 모아 보고, 새 글이 올라오면 알려줍니다.",
    )
    parser.add_argument("--version", action="version", version=f"notice_tap {__version__}")
    parser.add_argument("-c", "--config", default=str(DEFAULT_PATH), help="설정 파일 경로")
    subs = parser.add_subparsers(dest="command", required=True)

    p = subs.add_parser("init", help="설정 파일을 만든다")
    p.add_argument("--force", action="store_true", help="기존 설정을 덮어쓴다")
    p.set_defaults(func=cmd_init)

    p = subs.add_parser("add", help="게시판 주소를 등록한다 (구조는 자동으로 파악)")
    p.add_argument("urls", nargs="+", help="게시판 주소. 여러 개를 한 번에 넣어도 된다")
    p.add_argument("--name", help="표시할 이름 (생략하면 자동)")
    p.add_argument("--parser", choices=sorted(PARSERS), help="파서를 직접 지정")
    p.set_defaults(func=cmd_add)

    p = subs.add_parser("list", help="등록된 게시판을 보여준다")
    p.set_defaults(func=cmd_list)

    p = subs.add_parser("remove", help="게시판을 등록 해제한다")
    p.add_argument("target", help="이름 / 주소 / key 중 아무거나")
    p.add_argument("--purge", action="store_true", help="저장된 글 기록까지 삭제")
    p.set_defaults(func=cmd_remove)

    p = subs.add_parser("check", help="지금 한 번 확인하고 새 글이 있으면 알린다")
    p.add_argument("--no-notify", action="store_true", help="화면 출력만 하고 알림은 보내지 않는다")
    p.add_argument(
        "--notify-first-run",
        action="store_true",
        help="새로 등록한 게시판의 기존 글까지 전부 알린다 (기본은 조용히 기준점만 저장)",
    )
    p.set_defaults(func=cmd_check)

    p = subs.add_parser("watch", help="주기적으로 계속 확인한다")
    p.add_argument("--interval", type=int, help="확인 주기(분). 생략하면 설정값 사용")
    p.add_argument("--no-notify", action="store_true")
    p.add_argument("--notify-first-run", action="store_true")
    p.set_defaults(func=cmd_watch)

    p = subs.add_parser("dashboard", help="모아보기 HTML 을 다시 만든다")
    p.add_argument("--open", action="store_true", help="만든 뒤 브라우저로 연다")
    p.set_defaults(func=cmd_dashboard)

    p = subs.add_parser("export", help="본 글 기록을 JSON 으로 내보낸다")
    p.add_argument("--path", default="data/state.json")
    p.set_defaults(func=cmd_export)

    p = subs.add_parser("import", help="내보낸 JSON 기록을 되돌려 넣는다")
    p.add_argument("--path", default="data/state.json")
    p.set_defaults(func=cmd_import)

    p = subs.add_parser("test-notify", help="알림 채널 설정이 맞는지 시험 전송한다")
    p.set_defaults(func=cmd_test_notify)

    return parser


LOG_PATH = Path("data/notice_tap.log")
LOG_MAX_BYTES = 1_000_000


def _trim_log() -> None:
    """30분마다 쌓이는 로그가 무한정 커지지 않도록 절반씩 잘라낸다."""
    try:
        if LOG_PATH.stat().st_size <= LOG_MAX_BYTES:
            return
        text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
        kept = text[len(text) // 2 :]
        # 잘린 자리가 회차 중간이면 다음 회차 머리부터 남긴다.
        marker = kept.find("\n===== ")
        LOG_PATH.write_text(kept[marker + 1 :] if marker >= 0 else kept, encoding="utf-8")
    except OSError:
        pass  # 로그 정리 실패가 본 작업을 막아서는 안 된다


def _setup_output() -> None:
    """콘솔 한글 깨짐을 막고, 창 없는 실행(pythonw)에서는 로그 파일에 기록한다."""
    if sys.stdout is None:
        # 작업 스케줄러가 pythonw 로 띄우면 stdout 이 없어 기록이 하나도 남지 않는다.
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _trim_log()
        handle = LOG_PATH.open("a", encoding="utf-8", buffering=1)
        handle.write("\n===== " + time.strftime("%Y-%m-%d %H:%M:%S") + " =====\n")
        sys.stdout = sys.stderr = handle
        return

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _setup_output()

    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(exc)
        return 1
    except KeyboardInterrupt:
        print("\n중단했습니다.")
        return 130
