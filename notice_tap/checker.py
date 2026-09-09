"""등록된 게시판을 한 바퀴 돌면서 새 글을 찾아내는 핵심 로직."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .config import Config
from .fetcher import Fetcher
from .models import Post, Site
from .parsers import get_parser
from .store import Store


@dataclass
class SiteResult:
    site: Site
    new_posts: list[Post] = field(default_factory=list)
    total_seen: int = 0
    baseline: bool = False  # 첫 등록이라 알림 없이 기준점만 잡은 경우
    error: str = ""
    # 이번에 읽은 글이 전부 처음 보는 것이면, 지난번 이후 목록이 통째로
    # 갈렸다는 뜻이다. 그 사이에 밀려난 글이 있어도 알 방법이 없다.
    gap_suspected: bool = False


@dataclass
class CheckResult:
    sites: list[SiteResult] = field(default_factory=list)

    @property
    def new_posts(self) -> list[Post]:
        return [post for result in self.sites for post in result.new_posts]

    @property
    def errors(self) -> list[SiteResult]:
        return [result for result in self.sites if result.error]

    @property
    def gaps(self) -> list[SiteResult]:
        return [result for result in self.sites if result.gap_suspected]


class Checker:
    def __init__(self, config: Config, store: Store | None = None, fetcher: Fetcher | None = None):
        self.config = config
        self.store = store or Store(config.get("database", "data/notices.db"))
        self.fetcher = fetcher or Fetcher()

    def check_all(self, notify_first_run: bool = False) -> CheckResult:
        result = CheckResult()
        for site in self.config.enabled_sites:
            result.sites.append(self.check_site(site, notify_first_run))
        return result

    def check_site(self, site: Site, notify_first_run: bool = False) -> SiteResult:
        outcome = SiteResult(site=site)
        try:
            parser = get_parser(site.parser)
            # 일부 사이트는 HTML 에 목록이 없어 파서가 직접 API 를 불러야 한다.
            if getattr(parser, "needs_fetcher", False):
                posts = parser(site, self.fetcher)
            else:
                posts = parser(site, self.fetcher.get_text(site.url))
        except Exception as exc:
            outcome.error = str(exc)
            self.store.mark_check(site.key, error=str(exc))
            return outcome

        outcome.total_seen = len(posts)
        self.store.sync_site_name(site.key, site.name)
        if not posts:
            outcome.error = "글을 하나도 읽지 못했습니다 (사이트 구조가 바뀌었을 수 있음)"
            self.store.mark_check(site.key, error=outcome.error)
            return outcome

        fresh = self.store.filter_new(posts)

        # 처음 등록한 사이트는 기존 글 전체를 '이미 본 것'으로 표시한다.
        # 그러지 않으면 첫 실행에 수십 건이 한꺼번에 쏟아진다.
        first_run = not self.store.has_seen_site(site.key)
        if first_run and not notify_first_run:
            self.store.record(fresh, notified=True, baseline=True)
            self.store.mark_check(site.key)
            outcome.baseline = True
            return outcome

        outcome.gap_suspected = _turned_over(posts, fresh)

        if not self.config.get("notify_on_pinned", True):
            fresh = [post for post in fresh if not post.pinned]

        outcome.new_posts = sorted(fresh, key=_chronological)
        # 알릴 글은 '아직 안 보냄' 으로 먼저 저장한다. 전송이 실패해도 기록이
        # 남아 다음 실행 때 다시 시도할 수 있다. (예전에는 보내기 전에 이미
        # '보냄' 으로 적어버려서, 한 번 실패한 알림은 영영 사라졌다.)
        self.store.record(outcome.new_posts, notified=False)
        # 나머지(고정글 제외 설정으로 걸러진 것 등)는 알릴 대상이 아니다.
        self.store.record(posts, notified=True)
        self.store.sync_pinned(posts)
        self.store.mark_check(site.key)
        self._prune(site, posts)
        return outcome

    def _prune(self, site: Site, live_posts: list[Post]) -> None:
        """화면에 안 보일 만큼 오래됐고 게시판에도 없는 기록을 버린다."""
        days = self.config.get("retention_days", 7)
        if not days:
            return
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        self.store.prune(site.key, {p.uid for p in live_posts}, cutoff)

    def close(self) -> None:
        self.fetcher.close()
        self.store.close()


def _turned_over(posts: list[Post], fresh: list[Post]) -> bool:
    """목록이 지난번 이후 통째로 갈렸는지 본다.

    읽어온 글 중 하나라도 이미 알던 것이 있으면, 그 글과 지금 사이에는
    빠진 것이 없다. 반대로 전부 처음 보는 글이라면 지난번 확인 이후
    목록이 한 바퀴 넘게 돌았다는 뜻이라, 그 사이에 올라왔다 밀려난 글이
    있어도 우리는 영영 알 수 없다.

    위에 고정된 공지는 몇 달씩 그대로 걸려 있어 늘 '아는 글'로 잡힌다.
    그것까지 세면 어떤 게시판도 갈렸다고 판정되지 않으므로 빼고 본다.
    """
    rotating = [post for post in posts if not post.pinned]
    if not rotating:
        return False
    fresh_ids = {post.uid for post in fresh}
    return all(post.uid in fresh_ids for post in rotating)


def _chronological(post: Post) -> tuple[int, str]:
    """글 번호가 숫자면 오래된 순으로, 아니면 문자열 순으로 정렬한다."""
    return (int(post.post_id), "") if post.post_id.isdigit() else (0, post.post_id)
