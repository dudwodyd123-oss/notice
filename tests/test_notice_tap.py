"""notice_tap 회귀 시험.

여기 있는 시험은 대부분 실제로 겪은 사고에서 나왔다. 한 번 조용히
망가졌던 곳들이라, 다시 그렇게 되지 않도록 못을 박아 둔다.
외부 접속 없이 도는 것만 담았다.
"""

import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from notice_tap.checker import Checker, _turned_over  # noqa: E402
from notice_tap.config import Config  # noqa: E402
from notice_tap.dashboard import TEMPLATE, render_dashboard  # noqa: E402
from notice_tap.dates import to_iso_date  # noqa: E402
from notice_tap.models import Post, Site  # noqa: E402
from notice_tap.parsers import get_parser, parse_generic, parse_pyxis  # noqa: E402
from notice_tap.store import Store  # noqa: E402
from notice_tap.text import collapse  # noqa: E402


def _days_ago(days):
    return (date.today() - timedelta(days=days)).isoformat()


def make_post(post_id="1", site_key="s", title="글", posted_at=None, **kw):
    # 날짜를 박아두면 시간이 지나면서 보관 기간 밖으로 밀려나 시험이 썩는다.
    if posted_at is None:
        posted_at = date.today().isoformat()
    return Post(
        site_key=site_key,
        site_name=kw.pop("site_name", "테스트 게시판"),
        post_id=post_id,
        title=title,
        url=f"https://example.ac.kr/{post_id}",
        posted_at=posted_at,
        **kw,
    )


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


# --- 설정 -----------------------------------------------------------------


class ConfigTest(TempDirCase):
    """`add` 한 번에 디스코드 웹훅 주소가 지워져 알림이 끊겼던 사고."""

    def _write(self, body):
        path = self.tmp / "config.yaml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_저장해도_환경변수_자리표시자가_남는다(self):
        path = self._write(
            "notifiers:\n"
            "  discord:\n"
            "    enabled: true\n"
            "    webhook_url: ${TEST_HOOK}\n"
            "sites: []\n"
        )
        config = Config.load(path)
        config.add_site(Site(name="새 게시판", url="https://example.ac.kr/b"))
        config.save()

        self.assertIn("${TEST_HOOK}", path.read_text(encoding="utf-8"))

    def test_읽을_때는_환경변수로_바뀐다(self):
        path = self._write(
            "notifiers:\n"
            "  discord:\n"
            "    enabled: true\n"
            "    webhook_url: ${TEST_HOOK}\n"
            "sites: []\n"
        )
        os.environ["TEST_HOOK"] = "https://discord.example/hook"
        try:
            config = Config.load(path)
            self.assertEqual(
                config.data["notifiers"]["discord"]["webhook_url"],
                "https://discord.example/hook",
            )
        finally:
            del os.environ["TEST_HOOK"]

    def test_게시판을_지워도_자리표시자가_남는다(self):
        path = self._write(
            "notifiers:\n"
            "  discord:\n"
            "    enabled: true\n"
            "    webhook_url: ${TEST_HOOK}\n"
            "sites:\n"
            "- name: 지울 게시판\n"
            "  url: https://example.ac.kr/b\n"
            "  parser: pnu\n"
        )
        config = Config.load(path)
        self.assertIsNotNone(config.remove_site("지울 게시판"))
        config.save()

        text = path.read_text(encoding="utf-8")
        self.assertIn("${TEST_HOOK}", text)
        self.assertNotIn("지울 게시판", text)


class ShortcutTest(TempDirCase):
    """공지를 모으지 않고 링크만 걸어두는 항목."""

    def _config(self, body):
        path = self.tmp / "config.yaml"
        path.write_text(body, encoding="utf-8")
        return Config.load(path)

    def test_이름과_주소가_있는_것만_읽는다(self):
        config = self._config(
            "sites: []\n"
            "shortcuts:\n"
            "- name: 학생성공개발원\n"
            "  url: https://job.example.ac.kr/\n"
            "- name: 주소가 없는 곳\n"
        )
        self.assertEqual(
            config.shortcuts,
            [{"name": "학생성공개발원", "url": "https://job.example.ac.kr/"}],
        )

    def test_바로가기가_없으면_빈_목록(self):
        self.assertEqual(self._config("sites: []\n").shortcuts, [])

    def test_대시보드에_바로가기_칩과_주소가_들어간다(self):
        store = Store(self.tmp / "t.db")
        store.record([make_post("1")], notified=True)
        out = render_dashboard(
            store,
            self.tmp / "d.html",
            shortcuts=[{"name": "학생성공개발원", "url": "https://job.example.ac.kr/"}],
        )
        store.close()

        page = out.read_text(encoding="utf-8")
        self.assertIn('class="chip shortcut" data-site="학생성공개발원"', page)
        self.assertIn("https://job.example.ac.kr/", page)


class PinTest(TempDirCase):
    """핀 기능은 브라우저가 저장한 사본으로 글을 되살린다.

    되살리는 데 필요한 값이 하나라도 빠지면 보관 기간이 지난 순간
    핀을 꽂아 둔 글이 조용히 사라진다. 그래서 표시를 못 박아 둔다.
    """

    def _page(self, post):
        store = Store(self.tmp / "t.db")
        store.record([post], notified=True)
        out = render_dashboard(store, self.tmp / "d.html")
        store.close()
        return out.read_text(encoding="utf-8")

    def test_글마다_핀_단추와_되살릴_값이_붙는다(self):
        page = self._page(make_post("42", title="장학금 안내"))
        self.assertIn('<button class="pinbtn" type="button">', page)
        for attr in ("data-uid=", "data-title=", "data-url=", "data-sub=", "data-order="):
            self.assertIn(attr, page)
        self.assertIn('data-uid="s:42"', page)

    def test_따옴표가_섞인_제목도_표시에_갇힌다(self):
        page = self._page(make_post("7", title='"장학" <b>안내</b>'))
        self.assertNotIn('data-title=""장학"', page)
        self.assertIn("&quot;", page)
        self.assertNotIn("<b>안내</b>", page)

    def test_원래_자리로_돌아갈_순번이_박혀_있다(self):
        """핀을 뽑으면 제자리로 가야 한다.

        순번 없이 화면 차례만 바꾸면, 한 번 위로 올라간 글이 핀을 뽑은
        뒤에도 맨 위에 눌러앉는다. 실제로 그렇게 나갔다가 고쳤다.
        """
        store = Store(self.tmp / "t.db")
        store.record(
            [
                make_post("1", title="가", posted_at=_days_ago(0)),
                make_post("2", title="나", posted_at=_days_ago(1)),
                make_post("3", title="다", posted_at=_days_ago(2)),
            ],
            notified=True,
        )
        out = render_dashboard(store, self.tmp / "d.html")
        store.close()

        page = out.read_text(encoding="utf-8")
        ranks = re.findall(r'data-rank="(\d+)"', page)
        self.assertEqual(ranks, ["0", "1", "2"])
        # 순번은 화면에 그려진 차례와 같아야 한다.
        self.assertEqual(re.findall(r'data-title="([^"]*)"', page), ["가", "나", "다"])
        self.assertIn("Number(a.dataset.rank) - Number(b.dataset.rank)", TEMPLATE)

    def test_핀을_뽑기_전에_한_번_물어본다(self):
        page = self._page(make_post("5"))
        self.assertIn("confirm('핀을 뽑을까요?'", page)
        # 줄바꿈은 자바스크립트 쪽 이스케이프로 남아야 한다. 파이썬에서 진짜
        # 줄바꿈으로 새어 나가면 따옴표가 끊겨 페이지 전체가 죽는다.
        self.assertNotIn("? " + chr(39) + chr(10), page)
        self.assertIn(chr(92) + "n보관 기간이 지난 글이라", page)

    def test_핀은_숨기기가_먹도록_display를_되살린다(self):
        # li.post 에 display:flex 를 준 뒤로 hidden 속성이 무시될 뻔했다.
        self.assertIn("li.post[hidden] {{ display: none; }}", TEMPLATE)


# --- 알림 전달 -------------------------------------------------------------


class PendingTest(TempDirCase):
    """전송에 실패한 알림이 조용히 사라지던 사고."""

    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "t.db")

    def tearDown(self):
        self.store.close()
        super().tearDown()

    def test_새_글은_보내기_전까지_대기한다(self):
        self.store.record([make_post("1")], notified=False)
        self.assertEqual(len(self.store.pending_posts(["s"])), 1)

    def test_보냈다고_표시하면_다시_보내지_않는다(self):
        posts = [make_post("1")]
        self.store.record(posts, notified=False)
        self.store.mark_notified(self.store.pending_posts(["s"]))
        self.assertEqual(self.store.pending_posts(["s"]), [])

    def test_기준점으로_저장한_글은_보내지_않는다(self):
        self.store.record([make_post("1")], notified=True, baseline=True)
        self.assertEqual(self.store.pending_posts(["s"]), [])


# --- 새 글 판별 ------------------------------------------------------------


class FakeFetcher:
    def __init__(self, html=""):
        self.html = html

    def get_text(self, url):
        return self.html

    def close(self):
        pass


BOARD = """
<table class="board-table"><tbody>
  <tr><td class="td-num">2</td>
      <td class="td-title"><a href="/bbs/x/1/1002/artclView.do">둘째 글</a></td>
      <td class="td-date">2026.08.31</td></tr>
  <tr><td class="td-num">1</td>
      <td class="td-title"><a href="/bbs/x/1/1001/artclView.do">첫째 글</a></td>
      <td class="td-date">2026.08.30</td></tr>
</tbody></table>
"""


class CheckerTest(TempDirCase):
    def _checker(self, html=BOARD):
        path = self.tmp / "config.yaml"
        path.write_text(
            "database: " + str(self.tmp / "t.db").replace("\\", "/") + "\n"
            "sites:\n"
            "- name: 시험 게시판\n"
            "  url: https://example.ac.kr/bbs/x/1/artclList.do\n"
            "  parser: pnu\n",
            encoding="utf-8",
        )
        config = Config.load(path)
        return Checker(config, fetcher=FakeFetcher(html))

    def test_처음_등록하면_알림_없이_기준점만_잡는다(self):
        checker = self._checker()
        result = checker.check_all()
        self.assertTrue(result.sites[0].baseline)
        self.assertEqual(result.new_posts, [])
        checker.close()

    def test_두_번째부터_새_글을_알린다(self):
        checker = self._checker()
        checker.check_all()  # 기준점

        added = BOARD.replace(
            '<tr><td class="td-num">2</td>',
            '<tr><td class="td-num">3</td>'
            '<td class="td-title"><a href="/bbs/x/1/1003/artclView.do">셋째 글</a></td>'
            '<td class="td-date">2026.09.01</td></tr>'
            '<tr><td class="td-num">2</td>',
        )
        checker.fetcher = FakeFetcher(added)
        result = checker.check_all()

        self.assertEqual([p.title for p in result.new_posts], ["셋째 글"])
        checker.close()

    def test_같은_글을_두_번_알리지_않는다(self):
        checker = self._checker()
        checker.check_all()
        self.assertEqual(checker.check_all().new_posts, [])
        checker.close()


# --- 보관 기간 -------------------------------------------------------------


class GapTest(TempDirCase):
    """놓친 글을 알아채는 유일한 단서.

    확인 사이에 목록이 통째로 갈리면, 그 사이에 올라왔다 밀려난 글은
    오류도 알림도 남기지 않고 사라진다. 하나라도 겹치는 글이 있으면
    그 사이엔 빠진 것이 없다는 뜻이다.
    """

    def _check(self, first, second):
        """첫 번째 목록을 본 뒤 두 번째 목록을 봤을 때의 판정."""
        store = Store(self.tmp / "t.db")
        verdict = None
        for posts in (first, second):
            verdict = _turned_over(posts, store.filter_new(posts))
            store.record(posts, notified=True)
        store.close()
        return verdict

    def _posts(self, ids, site_key="s", pinned_ids=()):
        return [make_post(str(i), site_key=site_key, pinned=(i in pinned_ids))
                for i in ids]

    def test_하나라도_겹치면_빈틈이_없다(self):
        self.assertFalse(self._check(self._posts([1, 2, 3]), self._posts([2, 3, 4])))

    def test_전부_새_글이면_놓쳤을_수_있다고_본다(self):
        self.assertTrue(self._check(self._posts([1, 2, 3]), self._posts([7, 8, 9])))

    def test_고정공지는_세지_않는다(self):
        """고정공지는 몇 달씩 그대로라 늘 '아는 글'이다.

        그것까지 세면 어떤 게시판도 갈렸다고 판정되지 않아, 감시 장치가
        켜져 있어도 아무 일도 하지 않는 채로 남는다.
        """
        first = self._posts([1, 2, 3], pinned_ids={1})
        second = self._posts([1, 7, 8], pinned_ids={1})
        self.assertTrue(self._check(first, second))

    def test_고정공지밖에_없으면_판단하지_않는다(self):
        only_pinned = self._posts([1, 2], pinned_ids={1, 2})
        self.assertFalse(_turned_over(only_pinned, only_pinned))


class PruneTest(TempDirCase):
    """게시판에 남아 있는 오래된 고정공지를 지우면 알림이 다시 나간다."""

    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "t.db")
        self.cutoff = (date.today() - timedelta(days=7)).isoformat()
        self.old = (date.today() - timedelta(days=400)).isoformat()

    def tearDown(self):
        self.store.close()
        super().tearDown()

    def _backdate(self, uid, days):
        """그 글을 오래전에 처음 봤던 것으로 만든다."""
        when = (datetime.now().astimezone() - timedelta(days=days)).isoformat(timespec="seconds")
        self.store.conn.execute("UPDATE posts SET first_seen = ? WHERE uid = ?", (when, uid))
        self.store.conn.commit()

    def test_게시판에_아직_있으면_오래돼도_남긴다(self):
        pinned = make_post("1", posted_at=self.old, pinned=True)
        self.store.record([pinned], notified=True)
        self.store.prune("s", {pinned.uid}, self.cutoff)
        self.assertEqual(self.store.count("s"), 1)

    def test_오래됐고_게시판에도_없으면_지운다(self):
        gone = make_post("1", posted_at=self.old)
        self.store.record([gone], notified=True)
        self._backdate(gone.uid, 400)
        self.store.prune("s", {"s:9999"}, self.cutoff)
        self.assertEqual(self.store.count("s"), 0)

    def test_최근에_처음_본_글은_게시일이_오래돼도_남긴다(self):
        """화면에 보여줄 조건과 어긋나면, 떠 있어야 할 글이 먼저 지워진다."""
        late = make_post("1", posted_at=self.old)
        self.store.record([late], notified=True)  # 오늘 처음 봤다
        self.store.prune("s", {"s:9999"}, self.cutoff)
        self.assertEqual(self.store.count("s"), 1)

    def test_최근_글은_지우지_않는다(self):
        fresh = make_post("1", posted_at=date.today().isoformat())
        self.store.record([fresh], notified=True)
        self.store.prune("s", {"s:9999"}, self.cutoff)
        self.assertEqual(self.store.count("s"), 1)

    def test_목록을_못_읽은_회차에는_아무것도_지우지_않는다(self):
        gone = make_post("1", posted_at=self.old)
        self.store.record([gone], notified=True)
        self.store.prune("s", set(), self.cutoff)
        self.assertEqual(self.store.count("s"), 1)


class PinnedFlagTest(TempDirCase):
    """게시판의 '고정' 표시가 저장된 값에 반영되지 않던 문제.

    글은 INSERT OR IGNORE 로 넣어서 처음 저장할 때의 값이 굳는다. 그래서
    나중에 고정을 알아보게 고쳐도, 이미 저장된 글은 계속 고정이 아닌 채였다.
    """

    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "t.db")

    def tearDown(self):
        self.store.close()
        super().tearDown()

    def _pinned(self):
        return bool(self.store.recent(limit=1)[0]["pinned"])

    def test_나중에_고정이_붙으면_반영한다(self):
        self.store.record([make_post("1", pinned=False)], notified=True)
        self.assertFalse(self._pinned())
        self.assertEqual(self.store.sync_pinned([make_post("1", pinned=True)]), 1)
        self.assertTrue(self._pinned())

    def test_고정이_떨어지면_되돌린다(self):
        self.store.record([make_post("1", pinned=True)], notified=True)
        self.store.sync_pinned([make_post("1", pinned=False)])
        self.assertFalse(self._pinned())

    def test_바뀐_것이_없으면_건드리지_않는다(self):
        self.store.record([make_post("1", pinned=True)], notified=True)
        self.assertEqual(self.store.sync_pinned([make_post("1", pinned=True)]), 0)


class WindowTest(TempDirCase):
    """디스코드로는 알림이 갔는데 모아보기 화면에는 안 뜨던 사고.

    몇 달 전에 올라온 고정공지가 뒤늦게 목록에 들어오면 우리한테는 새 글이라
    알림이 나간다. 그런데 화면은 게시일만 보고 걸러내서, 알림을 받고 들어와도
    그 글이 어디에도 없었다.
    """

    def setUp(self):
        super().setUp()
        self.store = Store(self.tmp / "t.db")
        self.since = (date.today() - timedelta(days=7)).isoformat()
        self.old = (date.today() - timedelta(days=40)).isoformat()

    def tearDown(self):
        self.store.close()
        super().tearDown()

    def _titles(self):
        return [row["title"] for row in self.store.recent(since=self.since)]

    def test_게시일이_오래돼도_방금_처음_봤으면_보여준다(self):
        self.store.record([make_post("1", title="뒤늦게 들어온 고정공지",
                                     posted_at=self.old)], notified=True)
        self.assertEqual(self._titles(), ["뒤늦게 들어온 고정공지"])

    def test_처음_등록할_때_잡아둔_기준점은_보여주지_않는다(self):
        """이게 없으면 게시판을 새로 붙일 때마다 옛날 글이 화면을 덮는다."""
        self.store.record([make_post("1", title="원래 있던 글", posted_at=self.old)],
                          notified=True, baseline=True)
        self.assertEqual(self._titles(), [])

    def test_오래전에_본_오래된_글은_보여주지_않는다(self):
        post = make_post("1", title="지나간 글", posted_at=self.old)
        self.store.record([post], notified=True)
        when = (datetime.now().astimezone() - timedelta(days=40)).isoformat(timespec="seconds")
        self.store.conn.execute("UPDATE posts SET first_seen = ? WHERE uid = ?",
                                (when, post.uid))
        self.store.conn.commit()
        self.assertEqual(self._titles(), [])

    def test_최근_글은_그대로_보여준다(self):
        self.store.record([make_post("1", title="새 글",
                                     posted_at=date.today().isoformat())], notified=True)
        self.assertEqual(self._titles(), ["새 글"])


# --- 저장 기록 주고받기 -----------------------------------------------------


class StateTest(TempDirCase):
    """GitHub Actions 는 매번 빈 서버에서 시작해 이 기록으로 이어 붙인다."""

    def test_내보냈다_불러오면_그대로다(self):
        first = Store(self.tmp / "a.db")
        first.record([make_post("1"), make_post("2")], notified=False)
        data = first.export_state()
        first.close()

        second = Store(self.tmp / "b.db")
        second.import_state(json.loads(json.dumps(data)))
        self.assertEqual(second.count("s"), 2)
        self.assertEqual(len(second.pending_posts(["s"])), 2)
        second.close()

    def test_내보낸_기록에는_매번_바뀌는_시각이_없다(self):
        store = Store(self.tmp / "a.db")
        store.record([make_post("1")], notified=True)
        store.mark_check("s")
        exported = store.export_state()
        store.close()

        # last_check 이 들어가면 새 글이 없어도 매시간 커밋이 쌓인다.
        for row in exported["sites_state"]:
            self.assertNotIn("last_check", row)
            self.assertNotIn("last_ok", row)


# --- 글자 다듬기 -----------------------------------------------------------


class TextTest(unittest.TestCase):
    """제목의 줄바꿈은 알림 문구와 스크립트를 망가뜨리는 데 쓰일 수 있다."""

    def test_줄바꿈과_연속_공백을_없앤다(self):
        self.assertEqual(collapse("앞\n\t 뒤  글"), "앞 뒤 글")

    def test_None_은_빈_문자열이_된다(self):
        self.assertEqual(collapse(None), "")

    def test_파서가_내놓는_제목에는_줄바꿈이_없다(self):
        site = Site(name="t", url="https://example.ac.kr/bbs/x/1/artclList.do")
        html = BOARD.replace("둘째 글", "여러\n줄\n제목")
        posts = get_parser("pnu")(site, html)
        self.assertTrue(all("\n" not in p.title for p in posts))


# --- 날짜 ------------------------------------------------------------------


class DateTest(unittest.TestCase):
    def test_게시판마다_다른_표기를_한_형식으로_맞춘다(self):
        cases = {
            "2026.08.31": "2026-08-31",
            "2026-08-31": "2026-08-31",
            "2026.08.31 09:15": "2026-08-31",
            "2026/8/5": "2026-08-05",
            "Fri, 29 Aug 2026 10:00:00 +0900": "2026-08-29",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(to_iso_date(raw), expected)

    def test_알아볼_수_없으면_빈_문자열(self):
        self.assertEqual(to_iso_date("등록일 없음"), "")
        self.assertEqual(to_iso_date("2026.13.45"), "")

    def test_화면에는_통일된_날짜를_쓰고_해석_실패시_원문을_쓴다(self):
        self.assertEqual(make_post(posted_at="2026.08.31").display_date, "2026-08-31")
        self.assertEqual(make_post(posted_at="곧 공지").display_date, "곧 공지")



# --- 도서관 게시판 ---------------------------------------------------------


class StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class StubSession:
    """도서관 API 를 흉내낸다. 어떤 조건으로 불렀는지도 기록해 둔다."""

    def __init__(self, pinned, listing):
        self.pinned = pinned
        self.listing = listing
        self.calls = []

    def get(self, url, params=None, timeout=None):
        params = params or {}
        self.calls.append(params)
        rows = self.pinned if params.get("onlyNoticableBulletin") else self.listing
        return StubResponse({"success": True, "data": {"list": rows}})


class StubFetcher:
    def __init__(self, session):
        self.session = session
        self.timeout = 5


def bulletin(post_id, title, created="2026-09-03 13:34:29", category="일반"):
    return {
        "id": post_id,
        "title": title,
        "writer": "도서관",
        "dateCreated": created,
        "bulletinCategory": {"name": category},
    }


class PagedFetcher:
    """페이지마다 다른 HTML 을 돌려주는 흉내용 Fetcher."""

    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    def get_text(self, url):
        self.urls.append(url)
        return self.pages.get(url, "")


def board_html(*titles):
    rows = "".join(
        f'<tr><td class="subject"><a href="/view?seq={n}">{t}</a></td>'
        f'<td class="date">2026-09-01</td></tr>'
        for n, t in titles
    )
    return f"<table><tbody>{rows}</tbody></table>"


class PagedBoardTest(unittest.TestCase):
    """한 페이지만 읽으면, 글이 몰리는 날 목록 밖으로 밀려난 글을 놓친다.

    부산대학교 게시판은 스무 칸 중 열다섯 칸이 고정공지라 실제로 돌아가는
    자리가 다섯 칸뿐이었다. 실제로 하루치 글이 통째로 새어 나갔다.
    """

    def _site(self, **options):
        return Site(
            name="게시판",
            url="https://example.ac.kr/list?mCode=MN095",
            parser="generic",
            options={"row_selector": "tbody tr", "title_selector": "td.subject a",
                     "id_param": "seq", **options},
        )

    def test_설정한_페이지_수만큼_읽어_합친다(self):
        base = "https://example.ac.kr/list?mCode=MN095"
        fetcher = PagedFetcher({
            base: board_html((1, "첫째"), (2, "둘째")),
            "https://example.ac.kr/list?mCode=MN095&page=2": board_html((3, "셋째")),
        })
        posts = parse_generic(self._site(pages=2), fetcher)
        self.assertEqual([p.title for p in posts], ["첫째", "둘째", "셋째"])

    def test_기본은_한_페이지만_읽는다(self):
        base = "https://example.ac.kr/list?mCode=MN095"
        fetcher = PagedFetcher({base: board_html((1, "첫째"))})
        parse_generic(self._site(), fetcher)
        self.assertEqual(fetcher.urls, [base])

    def test_페이지가_겹쳐도_한_번만_센다(self):
        base = "https://example.ac.kr/list?mCode=MN095"
        same = board_html((1, "첫째"))
        fetcher = PagedFetcher({base: same,
                                "https://example.ac.kr/list?mCode=MN095&page=2": same})
        posts = parse_generic(self._site(pages=2), fetcher)
        self.assertEqual(len(posts), 1)

    def test_원래_쿼리스트링을_잃지_않는다(self):
        """mCode 가 떨어지면 엉뚱한 게시판을 읽게 된다."""
        base = "https://example.ac.kr/list?mCode=MN095"
        fetcher = PagedFetcher({base: board_html((1, "첫째"))})
        parse_generic(self._site(pages=2), fetcher)
        self.assertIn("mCode=MN095", fetcher.urls[1])
        self.assertIn("page=2", fetcher.urls[1])


class PyxisTest(unittest.TestCase):
    """도서관은 화면에 목록이 없어 API 를 직접 부른다."""

    def _site(self, **options):
        return Site(
            name="도서관",
            url="https://lib.example.ac.kr/guide/notice",
            parser="pyxis",
            options={"board_id": 2, **options},
        )

    def _parse(self, pinned, listing):
        session = StubSession(pinned, listing)
        posts = parse_pyxis(self._site(), StubFetcher(session))
        return posts, session

    def test_목록을_글로_바꾼다(self):
        posts, _ = self._parse([], [bulletin(57733, "  개관시간   공고 ")])
        self.assertEqual(len(posts), 1)
        post = posts[0]
        self.assertEqual(post.post_id, "57733")
        self.assertEqual(post.title, "개관시간 공고")
        self.assertEqual(post.url, "https://lib.example.ac.kr/guide/notice/57733")
        self.assertEqual(post.category, "일반")
        # 시각까지 들어오지만 날짜만 쓴다.
        self.assertEqual(post.posted_at, "2026-09-03")
        self.assertEqual(post.display_date, "2026-09-03")

    def test_고정공지를_따로_받아_합친다(self):
        """오래된 고정공지는 최신 목록 밖으로 밀려나 있어 따로 받아야 한다."""
        posts, session = self._parse(
            [bulletin(100, "고정된 글", created="2026-04-10 09:00:00")],
            [bulletin(200, "새 글")],
        )
        self.assertEqual({p.post_id for p in posts}, {"100", "200"})
        self.assertTrue(next(p for p in posts if p.post_id == "100").pinned)
        self.assertFalse(next(p for p in posts if p.post_id == "200").pinned)
        self.assertEqual(len(session.calls), 2)

    def test_양쪽에_겹치면_한_번만_고정으로_남는다(self):
        """겹치는 글이 두 번 들어오면 알림도 두 번 나간다."""
        posts, _ = self._parse([bulletin(100, "고정된 글")], [bulletin(100, "고정된 글")])
        self.assertEqual(len(posts), 1)
        self.assertTrue(posts[0].pinned)

    def test_board_id_가_없으면_알아듣게_알려준다(self):
        site = Site(name="도서관", url="https://lib.example.ac.kr/guide/notice",
                    parser="pyxis", options={})
        with self.assertRaises(ValueError) as caught:
            parse_pyxis(site, StubFetcher(StubSession([], [])))
        self.assertIn("board_id", str(caught.exception))

    def test_API_가_실패를_돌려주면_예외로_올린다(self):
        """조용히 빈 목록으로 넘어가면 '며칠째 실패' 알림도 안 뜬다."""
        session = StubSession([], [])
        session.get = lambda *a, **k: StubResponse({"success": False, "message": "권한 없음"})
        with self.assertRaises(RuntimeError) as caught:
            parse_pyxis(self._site(), StubFetcher(session))
        self.assertIn("권한 없음", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
