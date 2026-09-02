"""notice_tap 회귀 시험.

여기 있는 시험은 대부분 실제로 겪은 사고에서 나왔다. 한 번 조용히
망가졌던 곳들이라, 다시 그렇게 되지 않도록 못을 박아 둔다.
외부 접속 없이 도는 것만 담았다.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from notice_tap.checker import Checker  # noqa: E402
from notice_tap.config import Config  # noqa: E402
from notice_tap.dashboard import TEMPLATE, render_dashboard  # noqa: E402
from notice_tap.dates import to_iso_date  # noqa: E402
from notice_tap.models import Post, Site  # noqa: E402
from notice_tap.parsers import get_parser  # noqa: E402
from notice_tap.store import Store  # noqa: E402
from notice_tap.text import collapse  # noqa: E402


def make_post(post_id="1", site_key="s", title="글", posted_at="2026-08-31", **kw):
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

    def test_게시판에_아직_있으면_오래돼도_남긴다(self):
        pinned = make_post("1", posted_at=self.old, pinned=True)
        self.store.record([pinned], notified=True)
        self.store.prune("s", {pinned.uid}, self.cutoff)
        self.assertEqual(self.store.count("s"), 1)

    def test_오래됐고_게시판에도_없으면_지운다(self):
        gone = make_post("1", posted_at=self.old)
        self.store.record([gone], notified=True)
        self.store.prune("s", {"s:9999"}, self.cutoff)
        self.assertEqual(self.store.count("s"), 0)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
