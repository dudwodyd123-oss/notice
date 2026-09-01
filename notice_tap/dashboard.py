"""등록한 모든 게시판의 글을 한 페이지에 모아 보여주는 HTML 생성기."""

from __future__ import annotations

import base64
import html
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from .store import Store

TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#2e8b57">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="공지 모아보기">
<link rel="icon" type="image/png" href="data:image/png;base64,{favicon}">
<link rel="apple-touch-icon" href="data:image/png;base64,{icon192}">
<link rel="manifest" href="data:application/manifest+json;charset=utf-8;base64,{manifest}">
<title>공지 모아보기 — notice_tap</title>
<style>
  /* 기기 설정과 상관없이 항상 밝은 화면으로 고정한다. */
  :root {{
    color-scheme: light;
    --bg: #f6f7f9; --card: #ffffff; --text: #16181d; --muted: #6b7280;
    --line: #e4e7ec; --accent: #2e8b57; --accent-soft: #e8f3ec;
    --new: #d92d20; --chip: #eef2f7;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.6 "Pretendard", "Malgun Gothic", -apple-system, system-ui, sans-serif; }}
  .wrap {{ max-width: 900px; margin: 0 auto; padding: 28px 18px 64px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; letter-spacing: -0.02em; }}
  .meta {{ color: var(--muted); font-size: 13px; margin-bottom: 20px; }}
  .controls {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; align-items: center; }}
  input[type=search] {{ flex: 1 1 240px; padding: 9px 12px; border: 1px solid var(--line);
    border-radius: 8px; background: var(--card); color: var(--text); font-size: 14px; }}
  input[type=search]:focus {{ outline: none; border-color: var(--accent); }}
  .chip {{ border: 1px solid var(--line); background: var(--chip); color: var(--text);
    border-radius: 999px; padding: 6px 12px; font-size: 13px; cursor: pointer; }}
  .chip:hover {{ border-color: var(--accent); color: var(--accent); }}
  .chip.on {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
  .chip.on:hover {{ color: #fff; }}
  /* 공지를 모으지 않고 링크만 걸어둔 곳. 색으로 구분한다. */
  .chip.shortcut {{ background: var(--accent-soft); border-color: #cfe3d6;
    color: #1f6b42; }}
  .chip.shortcut:hover {{ border-color: var(--accent); }}
  .chip.shortcut.on {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
  .board-link {{ display: none; align-items: center; gap: 8px; margin-bottom: 14px;
    padding: 11px 14px; border: 1px solid var(--line); border-radius: 10px;
    background: var(--card); color: var(--accent); text-decoration: none;
    font-size: 14px; font-weight: 600; }}
  .board-link.show {{ display: flex; }}
  .board-link:hover {{ background: var(--accent-soft); }}
  .board-link .arrow {{ margin-left: auto; color: var(--muted); font-weight: 400; }}
  ul {{ list-style: none; margin: 0; padding: 0; }}
  li.post {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 12px 14px; margin-bottom: 8px; }}
  li.post a {{ color: var(--text); text-decoration: none; font-weight: 600; }}
  li.post a:hover {{ color: var(--accent); text-decoration: underline; }}
  .sub {{ color: var(--muted); font-size: 12.5px; margin-top: 4px;
    display: flex; gap: 8px; flex-wrap: wrap; }}
  .badge {{ color: var(--new); font-weight: 700; font-size: 11px; letter-spacing: .04em; }}
  .pin {{ color: var(--muted); font-size: 11px; border: 1px solid var(--line);
    border-radius: 4px; padding: 0 4px; }}
  .empty {{ color: var(--muted); text-align: center; padding: 48px 0; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>공지 모아보기</h1>
  <div class="meta">최근 {days}일 · {site_count}개 게시판 · 글 {post_count}건 · 갱신 {generated}</div>

  <div class="controls">
    <input type="search" id="q" placeholder="제목 검색…">
    <button class="chip on" data-site="">전체</button>
    {chips}
    {shortcut_chips}
  </div>

  <a class="board-link" id="boardLink" href="#" target="_blank" rel="noopener"></a>

  <ul id="list">{items}</ul>
  <div class="empty" id="empty" hidden></div>
</div>

<script>
const homes = {homes};
const shortcutNames = {shortcut_names};
const boardLink = document.getElementById('boardLink');
const list = document.getElementById('list');
const empty = document.getElementById('empty');
const q = document.getElementById('q');
let site = '';

function render() {{
  const needle = q.value.trim().toLowerCase();
  let shown = 0;
  for (const li of list.children) {{
    const okSite = !site || li.dataset.site === site;
    const okText = !needle || li.dataset.search.includes(needle);
    const visible = okSite && okText;
    li.hidden = !visible;
    if (visible) shown++;
  }}
  empty.hidden = shown > 0;
  empty.textContent = shortcutNames.includes(site)
    ? '이곳은 바로가기만 등록되어 있습니다. 위 링크로 이동하세요.'
    : '조건에 맞는 글이 없습니다.';
}}

function showBoardLink() {{
  const url = site ? homes[site] : null;
  if (!url) {{ boardLink.classList.remove('show'); return; }}
  boardLink.href = url;
  boardLink.innerHTML = '';
  const label = shortcutNames.includes(site) ? ' 사이트로 이동' : ' 공지사항 페이지로 이동';
  boardLink.append(site + label);
  const arrow = document.createElement('span');
  arrow.className = 'arrow';
  arrow.textContent = '↗';
  boardLink.append(arrow);
  boardLink.classList.add('show');
}}

q.addEventListener('input', render);
document.querySelectorAll('.chip').forEach(chip => {{
  chip.addEventListener('click', () => {{
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('on'));
    chip.classList.add('on');
    site = chip.dataset.site;
    showBoardLink();
    render();
  }});
}});
</script>
</body>
</html>
"""


ICON_DIR = Path(__file__).parent / "icons"


def _icon(name: str) -> str:
    return base64.b64encode((ICON_DIR / name).read_bytes()).decode("ascii")


def _manifest() -> str:
    """홈 화면에 추가했을 때 앱처럼 보이게 하는 설명서."""
    body = {
        "name": "공지 모아보기",
        "short_name": "공지",
        "start_url": ".",
        "display": "standalone",
        "background_color": "#f6f7f9",
        "theme_color": "#2e8b57",
        "icons": [
            {
                "src": f"data:image/png;base64,{_icon('icon-192.png')}",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": f"data:image/png;base64,{_icon('icon-512.png')}",
                "sizes": "512x512",
                "type": "image/png",
            },
        ],
    }
    return base64.b64encode(json.dumps(body, ensure_ascii=False).encode("utf-8")).decode("ascii")


def render_dashboard(
    store: Store,
    path: str | Path = "dashboard.html",
    limit: int = 300,
    sites=None,
    days: int = 7,
    shortcuts=None,
) -> Path:
    """sites 를 주면 분류마다 실제 게시판으로 가는 링크가 함께 붙는다.

    shortcuts 는 공지를 모으지 않고 링크만 걸어두는 곳이다.
    """
    since = (date.today() - timedelta(days=days)).isoformat() if days else ""
    rows = store.recent(limit=limit, since=since)
    # 같은 분류를 여러 게시판이 공유하므로 먼저 등록된 쪽 주소를 대표로 쓴다.
    homes: dict[str, str] = {}
    for site in sites or []:
        homes.setdefault(site.name, site.home)

    shortcut_names = []
    for item in shortcuts or []:
        homes.setdefault(item["name"], item["url"])
        shortcut_names.append(item["name"])
    cutoff = (datetime.now().astimezone() - timedelta(hours=24)).isoformat()

    site_names = sorted({row["site_name"] for row in rows})
    chips = "\n    ".join(
        f'<button class="chip" data-site="{html.escape(name, quote=True)}">{html.escape(name)}</button>'
        for name in site_names
    )

    shortcut_chips = "\n    ".join(
        f'<button class="chip shortcut" data-site="{html.escape(name, quote=True)}">'
        f"{html.escape(name)}</button>"
        for name in shortcut_names
    )

    items = "\n".join(_item(row, cutoff) for row in rows)

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        TEMPLATE.format(
            site_count=len(site_names),
            post_count=len(rows),
            generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
            days=days,
            favicon=_icon("favicon.png"),
            icon192=_icon("icon-192.png"),
            manifest=_manifest(),
            chips=chips,
            shortcut_chips=shortcut_chips,
            shortcut_names=json.dumps(shortcut_names, ensure_ascii=False),
            items=items or "",
            homes=json.dumps(homes, ensure_ascii=False),
        ),
        encoding="utf-8",
    )
    return out


def _item(row, cutoff: str) -> str:
    title = html.escape(row["title"])
    site_name = html.escape(row["site_name"])
    is_new = row["first_seen"] >= cutoff and not row["baseline"]
    badge = '<span class="badge">NEW</span> ' if is_new else ""
    pin = '<span class="pin">고정</span>' if row["pinned"] else ""
    bits = [site_name]
    # 저장할 때 통일해 둔 날짜를 쓴다. 해석 못 한 것만 원문을 보여준다.
    if shown_date := (row["posted_on"] or row["posted_at"]):
        bits.append(html.escape(shown_date))
    if row["author"]:
        bits.append(html.escape(row["author"]))
    if row["category"]:
        bits.append(html.escape(row["category"]))

    search = html.escape((row["title"] + " " + row["site_name"]).lower(), quote=True)
    return (
        f'<li class="post" data-site="{site_name}" data-search="{search}">'
        f'{badge}<a href="{html.escape(row["url"], quote=True)}" target="_blank" rel="noopener">{title}</a>'
        f'<div class="sub">{" · ".join(bits)} {pin}</div></li>'
    )
