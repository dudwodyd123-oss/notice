"""등록한 모든 게시판의 글을 한 페이지에 모아 보여주는 HTML 생성기."""

from __future__ import annotations

import html
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .store import Store

# 실행은 GitHub 의 서버(UTC)에서 도는데 화면은 한국에서 본다.
# 그냥 두면 "갱신 01:10" 처럼 아홉 시간 전으로 찍혀, 하루에 한두 번밖에
# 안 도는 것처럼 보인다. 표시하는 시각만 한국 시간으로 맞춘다.
KST = timezone(timedelta(hours=9))

TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#2e8b57">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="공지 모아보기">
<link rel="icon" type="image/png" href="favicon.png">
<link rel="apple-touch-icon" href="icon-192.png">
<link rel="manifest" href="manifest.webmanifest">
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
  /* 방금 눌러서 아직 저장소에 올라가지 않은 핀. 1~3분 뒤 평소 핀으로 바뀐다.
     끝까지 이 모습으로 남아 있으면 뭔가 잘못된 것이다 - 평소 핀과 눈에
     다르게 해 두는 까닭이 그것이다(실패를 가리지 않으려고). */
  li.post.waiting {{ border-style: dashed; }}
  .waitmark {{ color: var(--accent); font-size: 11px; font-weight: 600; }}
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

// 핀은 저장소에 적혀 있다. 예전에는 이 브라우저에만 적어서 폰에서 꽂은 것이
// 컴에서 안 보였다. 글 내용까지 통째로 담아두므로, 보관 기간이 지나 목록에서
// 빠진 글도 핀을 뽑기 전까지는 이 사본으로 계속 보여줄 수 있다.
const pins = {server_pins};
// 핀 단추는 깃허브 이슈를 연다. 브라우저에 토큰을 두지 않으려는 것으로,
// '주인이 맞다'는 확인은 깃허브 로그인이 대신해 준다.
const pinRepo = {pin_repo};

// 핀을 누르면 깃허브에 쪽지를 남기고 자동 실행이 목록을 고치는데, 화면이
// 다시 만들어져 나오기까지 2분쯤 걸린다. 그동안 '내가 방금 누른 것' 을 이
// 기기에만 적어 두고 평소 핀과 다른 모습으로 미리 보여준다. 저장소가
// 따라잡으면 적어둔 것을 지운다 - 핀의 근거는 어디까지나 저장소다.
// 누른 기기에서만 즉시 보이는 것이고, 다른 기기는 저장소를 기다린다.
const WAIT_KEY = 'notice_tap.waiting';
const WAIT_MS = 6 * 60 * 60 * 1000;  // 여섯 시간이 지나면 떨어낸다
const WAIT_MAX = 50;
let waiting = {{}};

function serverPinned(uid) {{
  return Object.prototype.hasOwnProperty.call(pins, uid);
}}

// 글 번호는 '게시판키:글번호' 꼴이다. 이 틀은 {{ }} 를 특별하게 읽어서
// 정규식 횟수 표기를 못 쓰므로, 모양만 눈으로 보듯 확인한다.
function okUid(uid) {{
  if (typeof uid !== 'string' || !uid || uid.length > 160) return false;
  const at = uid.indexOf(':');
  return at > 0 && at < uid.length - 1 && !/\\s/.test(uid);
}}

// 기다리는 것 중 이미 끝난 것과 너무 오래된 것을 떨어낸다. 남겨 두면
// 다른 기기에서 뽑은 핀을 이 기기가 되살려 보여준다.
function readWaiting() {{
  let saved = null;
  try {{
    saved = JSON.parse(localStorage.getItem(WAIT_KEY) || '{{}}');
  }} catch (e) {{ saved = null; }}

  const live = {{}};
  const now = Date.now();
  if (saved && typeof saved === 'object') {{
    for (const uid of Object.keys(saved).slice(0, WAIT_MAX)) {{
      const w = saved[uid];
      if (!okUid(uid) || !w || typeof w !== 'object') continue;
      if (w.action !== 'add' && w.action !== 'remove') continue;
      if (!Number.isFinite(w.at) || w.at > now || now - w.at > WAIT_MS) continue;
      // 저장소가 이미 같은 결론이면 더 기다릴 것이 없다.
      if ((w.action === 'add') === serverPinned(uid)) continue;
      live[uid] = {{ action: w.action, at: w.at, data: w.data || null }};
    }}
  }}
  waiting = live;
  writeWaiting();
}}

function writeWaiting() {{
  // 사생활 보호 모드처럼 적을 수 없는 곳도 있다. 못 적으면 즉시 보이는
  // 것만 포기하고 저장소 쪽은 그대로 돈다.
  try {{
    if (Object.keys(waiting).length) {{
      localStorage.setItem(WAIT_KEY, JSON.stringify(waiting));
    }} else {{
      localStorage.removeItem(WAIT_KEY);
    }}
  }} catch (e) {{}}
}}

function waitingFor(uid) {{
  const w = waiting[uid];
  return w ? w.action : '';
}}

function isPinned(uid) {{
  const act = waitingFor(uid);
  if (act) return act === 'add';
  return serverPinned(uid);
}}

// 되살릴 때 쓸 글 사본. 저장소 사본이 먼저고, 없으면 눌러둔 사본을 쓴다.
function pinData(uid) {{
  const w = waiting[uid];
  return pins[uid] || (w && w.data) || null;
}}

// '올리는 중' 표시. 2~3분 뒤에도 이 글자가 그대로면 잘못된 것이다.
function markWaiting(li, act) {{
  const sub = li.querySelector('.sub');
  if (!sub) return;
  let tag = sub.querySelector('.waitmark');
  if (!act) {{ if (tag) tag.remove(); return; }}
  if (!tag) {{
    tag = document.createElement('span');
    tag.className = 'waitmark';
    sub.append(tag);
  }}
  tag.textContent = act === 'add' ? '핀 올리는 중…' : '핀 빼는 중…';
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

  // 저장소에 적힌 핀과, 방금 눌러서 기다리는 것 둘 다 자리를 만들어 준다.
  for (const uid of new Set(Object.keys(pins).concat(Object.keys(waiting)))) {{
    if (present.has(uid)) continue;
    const li = buildItem(pinData(uid));
    if (li) list.append(li);
  }}

  for (const li of Array.from(list.children)) {{
    const act = waitingFor(li.dataset.uid);
    const on = isPinned(li.dataset.uid);
    // 되살린 글은 핀을 뽑는 순간 남겨 둘 근거가 없어진다. 다만 빼는 중이면
    // 저장소에 제대로 올라갔는지 눈으로 볼 수 있게 남겨 둔다.
    if (!on && !act && li.dataset.restored) {{ li.remove(); continue; }}
    li.classList.toggle('pinned', on);
    li.classList.toggle('waiting', !!act);
    markWaiting(li, act);
    const btn = li.querySelector('.pinbtn');
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.title = act
      ? '저장소에 올리는 중입니다 (1~3분)'
      : (on ? '핀 뽑기 (보관 기간이 지났으면 사라집니다)' : '맨 위에 고정해 두기');
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

// 깃허브에 '이 글을 꽂아 달라/빼 달라'는 쪽지를 미리 적어 둔 채로 연다.
// 사람이 Create 만 누르면 자동 실행이 받아 목록을 고친다.
function issueUrl(action, data) {{
  const head = (action === 'add' ? '핀 꽂기 — ' : '핀 뽑기 — ') + (data.title || data.uid);
  // 줄바꿈 없이 한 줄로 적는다. 여러 줄로 적으려다 글자가 깨진 적이 있다.
  const body = 'pin:' + action + ' ' + JSON.stringify(data);
  return pinRepo + '/issues/new?title=' + encodeURIComponent(head.slice(0, 80))
    + '&body=' + encodeURIComponent(body);
}}

list.addEventListener('click', ev => {{
  const btn = ev.target.closest('.pinbtn');
  if (!btn) return;
  if (!pinRepo) {{ alert('핀을 적어 둘 저장소가 설정돼 있지 않습니다.'); return; }}

  const li = btn.closest('li.post');
  const on = isPinned(li.dataset.uid);
  // 실수로 눌러서 보관해 둔 글을 놓치는 일이 없도록 한 번 물어본다.
  if (on && !confirm('핀을 뽑을까요?')) return;

  const action = on ? 'remove' : 'add';
  const data = snapshot(li);
  // 깃허브로 떠나기 전에 이 기기에 적고 화면을 미리 맞춰 둔다. 폰은 뒤로
  // 돌아올 때 얼려 둔 화면을 그대로 되살리는 경우가 있어서, 그때도 이미
  // 맞는 모습이 보이게 하려는 것이다.
  if (okUid(data.uid)) {{
    waiting[data.uid] = {{ action: action, at: Date.now(), data: data }};
    writeWaiting();
    refresh();
  }}
  location.href = issueUrl(action, data);
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

// 얼려 뒀던 화면이 되살아난 경우에는 코드가 처음부터 다시 돌지 않는다.
// 그때도 한 번 맞춰 준다(끝난 것과 오래된 것을 떨어내기 위해서다).
window.addEventListener('pageshow', ev => {{
  if (ev.persisted) {{ readWaiting(); refresh(); }}
}});

readWaiting();
refresh();
</script>
</body>
</html>
"""


ICON_DIR = Path(__file__).parent / "icons"
ICONS = ("favicon.png", "icon-192.png", "icon-512.png")

MANIFEST = {
    "name": "공지 모아보기",
    "short_name": "공지",
    "start_url": ".",
    "display": "standalone",
    "background_color": "#f6f7f9",
    "theme_color": "#2e8b57",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
    ],
}


def write_assets(folder: Path) -> list[Path]:
    """아이콘과 매니페스트를 페이지 옆에 파일로 놓는다.

    예전에는 이것들을 base64 로 HTML 안에 박아 넣었다. 그러면 페이지를 열
    때마다 아이콘까지 통째로 다시 받는다. 실제로 전송량 81KB 중 71KB 가
    아이콘이었다. 파일로 빼두면 브라우저가 한 번만 받아 캐시한다.
    """
    written = []
    for name in ICONS:
        target = folder / name
        target.write_bytes((ICON_DIR / name).read_bytes())
        written.append(target)

    manifest = folder / "manifest.webmanifest"
    manifest.write_text(json.dumps(MANIFEST, ensure_ascii=False), encoding="utf-8")
    written.append(manifest)
    return written


def render_dashboard(
    store: Store,
    path: str | Path = "dashboard.html",
    limit: int = 300,
    sites=None,
    days: int = 7,
    shortcuts=None,
    pins=None,
    pin_repo: str = "",
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
    write_assets(out.parent)
    out.write_text(
        TEMPLATE.format(
            site_count=len(site_names),
            post_count=len(rows),
            generated=datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
            days=days,
            chips=chips,
            shortcut_chips=shortcut_chips,
            shortcut_names=_js(shortcut_names),
            server_pins=_js({pin["uid"]: pin for pin in pins or []}),
            pin_repo=_js(pin_repo.rstrip("/")),
            items=items or "",
            homes=_js(homes),
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
    # 게시일은 한참 전인데 게시판에 이제야 올라온 글이 있다. 그런 글은
    # 목록 위쪽에 서는데 날짜만 보면 왜 여기 있나 싶으므로 이유를 적어준다.
    if (found := row["first_seen"][:10]) and found > _plus_days(row["post_date"], 1):
        bits.append(f"{found[5:].replace('-', '/')} 확인")
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
            ("data-order", row["list_date"] + "|" + row["first_seen"]),
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


def _js(value) -> str:
    """<script> 안에 끼워 넣을 값.

    제목은 남의 사이트에서 온 글자라 '</script>' 같은 것이 섞여 있을 수 있다.
    그대로 넣으면 그 자리에서 스크립트가 끊기고 뒤가 태그로 읽힌다.
    """
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _plus_days(day: str, days: int) -> str:
    """'YYYY-MM-DD' 에 며칠을 더한다. 읽을 수 없는 값이면 먼 미래로 둔다."""
    try:
        return (date.fromisoformat(day) + timedelta(days=days)).isoformat()
    except (TypeError, ValueError):
        return "9999-12-31"  # 비교에서 늘 지도록 두어 표시를 붙이지 않는다


def esc(value: str) -> str:
    return html.escape(value or "", quote=True)
