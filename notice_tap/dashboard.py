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
    padding: 12px 14px; margin-bottom: 8px;
    display: flex; align-items: flex-start; gap: 10px; }}
  /* display 를 지정했으므로 hidden 이 먹도록 따로 되살려 준다. */
  li.post[hidden] {{ display: none; }}
  .body {{ flex: 1; min-width: 0; }}
  li.post a {{ color: var(--text); text-decoration: none; font-weight: 600; }}
  li.post a:hover {{ color: var(--accent); text-decoration: underline; }}
  .sub {{ color: var(--muted); font-size: 12.5px; margin-top: 4px;
    display: flex; gap: 8px; flex-wrap: wrap; }}
  .badge {{ color: var(--new); font-weight: 700; font-size: 11px; letter-spacing: .04em; }}
  .pin {{ color: var(--muted); font-size: 11px; border: 1px solid var(--line);
    border-radius: 4px; padding: 0 4px; }}
  /* 내가 직접 꽂은 핀. 게시판이 붙여 놓은 '고정'(.pin) 과는 다른 것이다. */
  .pinbtn {{ flex: none; width: 32px; height: 32px; padding: 0; cursor: pointer;
    border: 1px solid var(--line); border-radius: 8px; background: var(--card);
    font-size: 14px; line-height: 1; filter: grayscale(1); opacity: .45; }}
  .pinbtn:hover {{ border-color: var(--accent); opacity: .8; }}
  li.post.pinned {{ border-color: var(--accent); background: var(--accent-soft); }}
  li.post.pinned .pinbtn {{ border-color: var(--accent); background: var(--card);
    filter: none; opacity: 1; }}
  .keep {{ color: var(--accent); font-size: 11px; font-weight: 600; }}
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

// 핀은 이 브라우저에만 저장된다. 정적 페이지라 서버에 적어 둘 곳이 없다.
// 글 내용까지 통째로 담아두므로, 보관 기간이 지나 목록에서 빠진 글도
// 핀을 뽑기 전까지는 여기 저장된 사본으로 계속 보여줄 수 있다.
const PIN_KEY = 'notice_tap_pins';
let pins = {{}};
try {{ pins = JSON.parse(localStorage.getItem(PIN_KEY)) || {{}}; }} catch (e) {{ pins = {{}}; }}

function savePins() {{
  try {{ localStorage.setItem(PIN_KEY, JSON.stringify(pins)); }} catch (e) {{}}
}}

function isPinned(uid) {{
  return Object.prototype.hasOwnProperty.call(pins, uid);
}}

function snapshot(li) {{
  const d = li.dataset;
  return {{ uid: d.uid, title: d.title, url: d.url, site: d.site,
            sub: d.sub, bp: d.bp, order: d.order }};
}}

function pinButton() {{
  const b = document.createElement('button');
  b.className = 'pinbtn';
  b.type = 'button';
  b.textContent = '📌';
  return b;
}}

// 되살릴 주소는 이 브라우저에 저장돼 있던 값이므로 형식을 한 번 확인하고 쓴다.
function safeUrl(url) {{
  try {{
    const u = new URL(url, location.href);
    return (u.protocol === 'http:' || u.protocol === 'https:') ? u.href : '';
  }} catch (e) {{ return ''; }}
}}

// 서버에서 이미 지워진 글을 저장해 둔 사본으로 다시 그린다.
function buildItem(data) {{
  const href = data && data.uid ? safeUrl(data.url || '') : '';
  if (!href) return null;
  const li = document.createElement('li');
  li.className = 'post';
  li.dataset.uid = data.uid;
  li.dataset.site = data.site || '';
  li.dataset.url = href;
  li.dataset.title = data.title || '';
  li.dataset.sub = data.sub || '';
  li.dataset.bp = data.bp || '0';
  li.dataset.order = data.order || '';
  li.dataset.restored = '1';
  li.dataset.rank = '999999';
  li.dataset.search = ((data.title || '') + ' ' + (data.site || '')).toLowerCase();

  const body = document.createElement('div');
  body.className = 'body';
  const a = document.createElement('a');
  a.href = href;
  a.target = '_blank';
  a.rel = 'noopener';
  a.textContent = data.title || '(제목 없음)';
  body.append(a);

  const sub = document.createElement('div');
  sub.className = 'sub';
  sub.append(document.createTextNode(data.sub || ''));
  if (data.bp === '1') {{
    const bp = document.createElement('span');
    bp.className = 'pin';
    bp.textContent = '고정';
    sub.append(bp);
  }}
  const keep = document.createElement('span');
  keep.className = 'keep';
  keep.textContent = '핀으로 보관 중';
  sub.append(keep);
  body.append(sub);

  li.append(body, pinButton());
  return li;
}}

function refresh() {{
  const present = new Set();
  for (const li of list.children) present.add(li.dataset.uid);

  let dropped = false;
  for (const uid of Object.keys(pins)) {{
    if (present.has(uid)) continue;
    const li = buildItem(pins[uid]);
    if (li) list.append(li);
    else {{ delete pins[uid]; dropped = true; }}
  }}
  if (dropped) savePins();

  for (const li of Array.from(list.children)) {{
    const on = isPinned(li.dataset.uid);
    // 되살린 글은 핀을 뽑는 순간 남겨 둘 근거가 없어진다.
    if (!on && li.dataset.restored) {{ li.remove(); continue; }}
    li.classList.toggle('pinned', on);
    const btn = li.querySelector('.pinbtn');
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.title = on ? '핀 뽑기 (보관 기간이 지났으면 사라집니다)' : '맨 위에 고정해 두기';
  }}

  // 핀만 위로 끌어올리고, 나머지는 서버가 매겨 준 순번(rank)대로 되돌린다.
  // 여기서 순번을 안 보고 현재 차례를 그대로 두면, 한 번 위로 올라간 글이
  // 핀을 뽑은 뒤에도 그 자리에 눌러앉는다.
  const rows = Array.from(list.children);
  rows.sort((a, b) => {{
    const pa = a.classList.contains('pinned') ? 1 : 0;
    const pb = b.classList.contains('pinned') ? 1 : 0;
    if (pa !== pb) return pb - pa;
    if (pa) return (b.dataset.order || '').localeCompare(a.dataset.order || '');
    return Number(a.dataset.rank) - Number(b.dataset.rank);
  }});
  for (const li of rows) list.append(li);

  render();
}}

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

list.addEventListener('click', ev => {{
  const btn = ev.target.closest('.pinbtn');
  if (!btn) return;
  const li = btn.closest('li.post');
  const uid = li.dataset.uid;
  if (isPinned(uid)) {{
    // 실수로 눌러서 보관해 둔 글을 놓치는 일이 없도록 한 번 물어본다.
    const warn = li.dataset.restored
      ? '\\n보관 기간이 지난 글이라 목록에서 바로 사라집니다.'
      : '';
    if (!confirm('핀을 뽑을까요?' + warn)) return;
    delete pins[uid];
  }} else {{
    pins[uid] = snapshot(li);
  }}
  savePins();
  refresh();
}});

document.querySelectorAll('.chip').forEach(chip => {{
  chip.addEventListener('click', () => {{
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('on'));
    chip.classList.add('on');
    site = chip.dataset.site;
    showBoardLink();
    render();
  }});
}});

refresh();
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

    items = "\n".join(_item(row, cutoff, rank) for rank, row in enumerate(rows))

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


def _item(row, cutoff: str, rank: int) -> str:
    is_new = row["first_seen"] >= cutoff and not row["baseline"]
    badge = '<span class="badge">NEW</span> ' if is_new else ""
    board_pin = '<span class="pin">고정</span>' if row["pinned"] else ""

    bits = [row["site_name"]]
    # 저장할 때 통일해 둔 날짜를 쓴다. 해석 못 한 것만 원문을 보여준다.
    if shown_date := (row["posted_on"] or row["posted_at"]):
        bits.append(shown_date)
    if row["author"]:
        bits.append(row["author"])
    if row["category"]:
        bits.append(row["category"])
    sub = " · ".join(bits)

    # 핀을 꽂아 둔 글은 보관 기간이 지나 서버에서 지워져도 브라우저가
    # 아래 값들만 가지고 같은 모양으로 다시 그린다.
    attrs = " ".join(
        f'{name}="{esc(value)}"'
        for name, value in (
            ("data-uid", row["uid"]),
            ("data-site", row["site_name"]),
            ("data-title", row["title"]),
            ("data-url", row["url"]),
            ("data-sub", sub),
            ("data-bp", "1" if row["pinned"] else "0"),
            ("data-order", (row["posted_on"] or "") + "|" + row["first_seen"]),
            # 핀을 뽑았을 때 돌아갈 자리. 이 값이 없으면 위로 끌어올린 글이
            # 그 자리에 눌러앉는다.
            ("data-rank", str(rank)),
            ("data-search", (row["title"] + " " + row["site_name"]).lower()),
        )
    )
    return (
        f'<li class="post" {attrs}><div class="body">'
        f'{badge}<a href="{esc(row["url"])}" target="_blank" rel="noopener">'
        f"{html.escape(row['title'])}</a>"
        f'<div class="sub">{html.escape(sub)} {board_pin}</div></div>'
        f'<button class="pinbtn" type="button">📌</button></li>'
    )


def esc(value: str) -> str:
    return html.escape(value or "", quote=True)
