"""등록된 게시판을 한 바퀴 돌면서 새 글을 찾아내는 핵심 로직."""

from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass
class CheckResult:
    sites: list[SiteResult] = field(default_factory=list)

    @property
    def new_posts(self) -> list[Post]:
        return [post for result in self.sites for post in result.new_posts]

    @property
    def errors(self) -> list[SiteResult]:
        return [result for result in self.sites if result.error]


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
            posts = get_parser(site.parser)(site, self.fetcher.get_text(site.url))
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

        if not self.config.get("notify_on_pinned", True):
            fresh = [post for post in fresh if not post.pinned]

        outcome.new_posts = sorted(fresh, key=_chronological)
        self.store.record(posts, notified=True)
        self.store.mark_check(site.key)
        return outcome

    def close(self) -> None:
        self.fetcher.close()
        self.store.close()


def _chronological(post: Post) -> tuple[int, str]:
    """글 번호가 숫자면 오래된 순으로, 아니면 문자열 순으로 정렬한다."""
    return (int(post.post_id), "") if post.post_id.isdigit() else (0, post.post_id)
