# notice_tap

여러 학과·기관 공지 게시판을 대신 들여다보고, **새 글이 올라오면 알려주는** 도구입니다.

---

## 지금 상태

**내 PC** — 바탕화면의 `공지 모아보기` 아이콘만 열면 됩니다.

- 작업 스케줄러에 `notice_tap` 작업이 등록되어 **1시간마다 자동으로** 확인합니다 (창 안 뜸)
- 새 글이 생기면 **윈도우 알림**이 뜨고, 알림을 클릭하면 해당 글이 바로 열립니다
- 게시판이 **2일 넘게 계속 확인 실패**하면 그것도 알림으로 알려줍니다 (조용히 고장나는 걸 막습니다)
- 감시 중인 게시판 5개: 학부 공지사항 · 졸업과제 · 채용게시판 · 경진대회 안내 · 기타행사 안내
- 실행 기록은 `data/notice_tap.log` 에 쌓입니다

**GitHub** — 아래 4단계를 마치면 PC를 꺼둬도 돌아가고, 폰에서 주소로 대시보드를 볼 수 있습니다.

---

## GitHub 으로 옮기기

PC 를 켜두지 않아도 GitHub 서버가 1시간마다 확인하고, 대시보드를 인터넷 주소로 띄워줍니다.
무료이고, 준비는 이미 다 되어 있습니다. 남은 건 내 계정에 올리는 일뿐입니다.

**1. GitHub 에서 빈 저장소를 만듭니다** — <https://github.com/new>

- 이름: 아무거나 (예: `notice-tap`)
- **Public** 을 고르세요. Private 은 GitHub Pages 를 쓰려면 유료 요금제가 필요합니다
- README, .gitignore, license 는 **체크하지 마세요** (이미 있습니다)

**2. 내 PC 에서 올립니다** — `<내계정>` 과 저장소 이름만 바꿔서:

```bash
git remote add origin https://github.com/<내계정>/notice-tap.git
```

```bash
git push -u origin main
```

**3. Actions 에 쓰기 권한을 줍니다**

저장소 **Settings → Actions → General → Workflow permissions** 에서
**Read and write permissions** 를 고르고 저장합니다.
(확인 기록을 저장소에 되커밋해야 하기 때문입니다.)

**4. 첫 실행**

저장소 **Actions** 탭 → 왼쪽 `공지 확인` → **Run workflow** 를 누릅니다.
1~2분 뒤 초록 체크가 뜨면, 대시보드 주소는 이렇게 됩니다:

```
https://<내계정>.github.io/notice-tap/
```

이 주소를 폰 홈 화면에 추가해두면 앱처럼 쓸 수 있습니다.

> GitHub 쪽이 잘 도는 걸 확인한 뒤에는, 내 PC 의 작업 스케줄러는 꺼도 됩니다:
> `powershell -ExecutionPolicy Bypass -File install_task.ps1 -Remove`
> (PC 알림을 계속 받고 싶으면 그냥 두셔도 됩니다.)

### 폰으로 알림까지 받으려면

GitHub 서버에서는 윈도우 알림을 띄울 수 없으니, 채팅 앱으로 받아야 합니다.
저장소 **Settings → Secrets and variables → Actions → New repository secret** 에
아래 중 원하는 것만 등록하면 그 채널이 자동으로 켜집니다.

| Secret 이름 | 값 |
|---|---|
| `DISCORD_WEBHOOK_URL` | 디스코드 채널 설정 → 연동 → 웹후크 주소 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | @BotFather 봇 토큰 / @userinfobot 이 알려주는 내 ID |
| `KAKAO_REST_API_KEY` / `KAKAO_REFRESH_TOKEN` | `python kakao_auth.py` 가 알려주는 두 값 |

아무것도 등록하지 않으면 알림 없이 대시보드만 갱신됩니다.

---

## 기능

- 사이트를 하나하나 방문할 필요 없이 **한 페이지(`dashboard.html`)에 모아 보기**
- 새 글이 생기면 **윈도우 알림 / 카카오톡 / 텔레그램 / 디스코드 / 터미널** 로 알림
- 게시판 주소만 붙여넣으면 **구조를 알아서 파악**해 등록 (부산대 통합 CMS 완전 지원)

---

## 1. 설치

```bash
pip install -r requirements.txt
```

## 2. 시작하기

```bash
python -m notice_tap init
```

```bash
python -m notice_tap add "https://cse.pusan.ac.kr/cse/14221/subview.do?enc=Zm5jdDF8QEB8..."
```

브라우저 주소창에 있는 게시판 주소를 그대로 붙여넣으면 됩니다.
부산대 사이트의 `subview.do?enc=...` 주소는 내부적으로 실제 게시판 목록 주소로 자동 변환됩니다.
여러 개를 한 번에 넣어도 됩니다.

```bash
python -m notice_tap check
```

**첫 확인은 알림을 보내지 않습니다.** 이미 올라와 있던 글 수십 건이 한꺼번에 쏟아지지 않도록,
처음에는 현재 목록을 "이미 본 것"으로 기록해 기준점만 잡습니다. 그 다음부터 올라오는 글이 새 글입니다.

## 3. 명령어

| 명령 | 하는 일 |
|---|---|
| `init` | `config.yaml` 생성 |
| `add <주소> [주소…]` | 게시판 등록 (`--name`, `--parser` 옵션) |
| `list` | 등록된 게시판과 마지막 확인 상태 |
| `remove <이름\|주소\|key>` | 등록 해제 (`--purge` 로 기록까지 삭제) |
| `check` | 지금 한 번 확인하고 새 글이 있으면 알림 |
| `watch` | 설정된 주기마다 계속 확인 (`--interval 10`) |
| `dashboard --open` | 모아보기 HTML 다시 만들고 브라우저로 열기 |
| `test-notify` | 알림 채널 설정이 맞는지 시험 전송 |

## 4. 자동 실행

### 방법 A — 작업 스케줄러 (권장, 창이 안 뜸)

```bash
powershell -ExecutionPolicy Bypass -File install_task.ps1 -IntervalMinutes 30
```

해제는 `-Remove` 를 붙여 다시 실행하면 됩니다.

### 방법 B — 터미널을 켜두기

`watch.bat` 을 더블클릭하거나 `python -m notice_tap watch`.

---

## 5. 윈도우 알림 (기본값, 설정 불필요)

`config.yaml` 에서 이미 켜져 있습니다. 가입도 토큰도 필요 없습니다.

- 새 글 5건까지는 글마다 알림 하나씩, 그보다 많으면 요약 알림 한 개
- 알림을 클릭하면 해당 게시글이 기본 브라우저에서 열립니다
- 알림이 안 보이면 윈도우 **설정 → 시스템 → 알림** 에서 알림이 꺼져 있거나
  **집중 지원(방해 금지)** 이 켜져 있는지 확인하세요

카톡으로 받고 싶을 때만 아래를 따라 하면 됩니다.

## 6. 카카오톡 알림 설정 (선택)

카카오 정책상 **별도 앱 심사 없이 보낼 수 있는 대상은 '나 자신'뿐**입니다.
새 공지는 내 카카오톡의 **'나와의 채팅'** 방으로 도착합니다. (친구·단톡방 전송은 카카오 검수 대상)

1. <https://developers.kakao.com> 로그인 → **내 애플리케이션 → 애플리케이션 추가하기**
2. **앱 설정 → 플랫폼 → Web** → 사이트 도메인에 `http://localhost:5000` 등록
3. **제품 설정 → 카카오 로그인** → 활성화 **ON**
   → Redirect URI 에 `http://localhost:5000/oauth` 등록
4. **제품 설정 → 카카오 로그인 → 동의항목** → **카카오톡 메시지 전송(`talk_message`)** 사용 설정
5. **앱 설정 → 앱 키** 에서 **REST API 키** 복사
6. 아래 실행 후 브라우저에서 로그인:

```bash
python kakao_auth.py
```

끝나면 `config.yaml` 에 `refresh_token` 이 저장되고 카카오 알림이 켜집니다.

```bash
python -m notice_tap test-notify
```

> `refresh_token` 은 약 2개월간 유효하고, 그 안에 알림이 한 번이라도 나가면 자동으로 연장됩니다.
> 만료되면 `python kakao_auth.py` 를 다시 실행하세요.

## 7. 다른 알림 채널

`config.yaml` 의 `notifiers` 에서 `enabled: true` 로 바꾸고 값을 채우면 됩니다. 여러 개 동시에 켜도 됩니다.

```yaml
notifiers:
  telegram:            # 설정이 가장 쉽고 안정적입니다
    enabled: true
    bot_token: "123456:AA..."   # @BotFather 에서 봇 생성 후 받은 토큰
    chat_id: "987654321"        # @userinfobot 에게 말 걸면 알려줍니다
  discord:
    enabled: true
    webhook_url: "https://discord.com/api/webhooks/..."   # 채널 설정 → 연동 → 웹후크
```

## 8. 고장 알림

학교가 사이트를 개편하면 글을 못 읽게 되는데, 겉으로는 "새 글 없음"과 구분되지 않아
모르는 채로 방치되기 쉽습니다. 그래서 한 게시판이 **연속으로 `stale_alert_days` 일(기본 2일)**
넘게 실패하면 알림이 옵니다.

- 매번 시끄럽지 않도록 같은 게시판에 대해 **하루 한 번만** 알립니다
- 게시판이 다시 정상으로 돌아오면 실패 기록은 자동으로 지워집니다
- 지금 상태는 `python -m notice_tap list` 로 언제든 볼 수 있습니다

## 9. 부산대가 아닌 사이트 추가하기

`add` 는 RSS 피드와 흔한 표(table) 형태 게시판도 자동으로 인식하려고 시도합니다.
자동 인식이 안 되면 `config.yaml` 에 CSS 선택자를 직접 적어주세요.

```yaml
sites:
  - name: 어느 학과 공지
    url: https://example.ac.kr/board/list
    parser: generic
    row_selector: "table.bbs tbody tr"    # 글 한 줄에 해당하는 선택자 (필수)
    title_selector: "td.subject a"        # 제목 링크
    date_selector: "td.date"
    author_selector: "td.writer"
    id_param: "nttId"                     # 링크 주소에서 글 번호를 뽑을 쿼리 이름
```

`parser` 로 쓸 수 있는 값:

- `pnu` — 부산대 통합 홈페이지 CMS(`artclList.do`). 대부분의 부산대 학과·기관 게시판이 여기 해당합니다.
- `generic` — CSS 선택자를 직접 지정하는 범용 표 게시판
- `rss` — RSS / Atom 피드

## 10. 설정 항목

| 키 | 기본값 | 설명 |
|---|---|---|
| `poll_interval_minutes` | `60` | `watch` 의 확인 주기(분) |
| `database` | `data/notices.db` | 본 글을 기억하는 SQLite 파일 |
| `dashboard_path` | `dashboard.html` | 모아보기 페이지 경로 |
| `notify_on_pinned` | `true` | 상단 고정 공지가 새로 올라와도 알릴지 |
| `stale_alert_days` | `2` | 며칠째 계속 실패하면 알릴지. `0` 이면 이 알림을 끕니다 |

`notifiers` 아래 각 채널의 `enabled` 를 `false` 로 바꾸면 그 채널만 끕니다.

## 11. 구조

```
notice_tap/
  models.py      Post / Site 데이터 모델
  fetcher.py     HTTP 가져오기 (재시도 + euc-kr/cp949 인코딩 처리)
  parsers/       pnu · generic · rss 파서
  store.py       SQLite - 본 글 기억
  checker.py     새 글 판별 핵심 로직
  notify/        console · windows · kakao · telegram · discord
  dashboard.py   모아보기 HTML 생성
  cli.py         명령줄 인터페이스
kakao_auth.py    카카오 최초 인증 (1회)
install_task.ps1 윈도우 작업 스케줄러 등록/해제
```

## 12. 참고

- 게시판을 30분 주기 정도로 확인하는 것은 일반적인 사람의 방문 빈도와 비슷한 수준이지만,
  주기를 지나치게 짧게(예: 1분) 두면 상대 서버에 부담이 됩니다. 기본값 정도를 권장합니다.
- 사이트 개편으로 HTML 구조가 바뀌면 `list` 에 오류가 표시됩니다.
  이때는 `config.yaml` 의 선택자를 손보거나 `add` 로 다시 등록하면 됩니다.
- `config.yaml` 에는 토큰이 들어가므로 그대로 공유하거나 공개 저장소에 올리지 마세요.
  (`.gitignore` 에 이미 제외돼 있습니다.)
