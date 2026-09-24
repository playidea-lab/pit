# pit · pithub

> AI가 같은 실수를 두 번 하지 않게 하는 교정 메모리.
> **pit**은 오픈소스 — 회사 서버에서. **pithub**는 그것을 2분 만에 켜고 팀이 같은 판단 원장을 읽는 곳.

claude.ai · Claude Code · Codex에 MCP 커넥터 하나를 붙이면, 당신이 AI의 제안을 **거부하고 고치고 방향을 정한 순간**이
기록됩니다. 다음 세션의 AI는 제안하기 전에 그 기록을 찾아봅니다. 대화 원문은 서버로 가지 않습니다 — 결정 한 건의 요약과
당신의 말 한 줄만 갑니다.

```
사용자 ──(제안을 거부/수정/선택)──▶ 세션의 AI ──record_decision──▶ pithub 원장 (본인만)
다음 세션의 AI ──search_my_decisions──▶ "지난주에 같은 방식을 재보고 폐기하셨습니다"
```

## 왜

- AI가 제안하고 사람이 "ㅇㅇ"으로 넘긴 결정이 코드와 문서에 쌓이는데, "왜 이렇게 했지?"에 아무도 답하지 못한다.
- 같은 교정을 세션마다, 도구마다 반복한다. Claude의 메모리는 Codex를 모르고, Codex는 Claude를 모른다.
- `CLAUDE.md` · `AGENTS.md`는 손으로 관리하는 결정 원장이고, 늘 낡아 있다.

## 원칙

1. **원문은 나가지 않는다.** 결정의 요약과 인용문만 저장한다. 수신 시점에 시크릿·개인정보를 가린다.
2. **회사 밖으로 나가지 않는다.** 공개 기능이 없다. 팀 저장소에서 기록된 판단은 3일 뒤 팀에 보이고, 그 전에 본인이 뺄 수 있다.
3. **기록에 드는 노력은 0.** 확인은 쓰는 순간(열람·팀 공유 전)에만, 품질은 주간 표본으로 잰다.
4. **내 것은 지우면 정말 사라진다.** 팀에 보인 판단은 회사의 기록 — 퇴사해도 남고 팀 소유자만 지운다.
5. **트윈은 묻는 사람이 볼 수 있는 결정만큼만 안다.** 경계는 프롬프트가 아니라 행 접근 권한(RLS)이다.

## 구성

| 디렉터리 | 무엇 |
|---|---|
| `pit/server/` | 원격 MCP 서버 (FastMCP, GitHub OAuth). 도구: `record_decision` · `search_my_decisions` · `get_decision` · `whoami`, 로컬 CLI용 토큰 API |
| `pithub/web/` | Next.js 웹 — 정리함, 내 결정, 팀 `/t/<팀>`(커넥터 주소·원칙·떠난 구성원·AGENTS.md 초안), 설정 |
| `pithub/supabase/` | Postgres 스키마와 RLS (마이그레이션) |
| `pit/` (그 외) | 로컬 CLI `pit` — 세션 원문 보관함, 결정 추출, MCP 기록 감사, push/pull |
| `docs/` | 설계 문서. `PRODUCT.md`(제품 정의 — 판단 그래프와 트윈), `PIT_KNOWLEDGE_DESIGN.md`(생애주기), `BACKFILL_MEMORY.md`(메모 백필) |
| `.pit/decisions/` | 이 프로젝트 자체의 결정 기록 (도그푸딩) |

## 호스팅된 pithub 쓰기

**팀 관리자**: 웹에서 팀을 만들고, 초대 링크를 팀 채널에 붙인다.
**팀원**: 링크를 누르고 GitHub로 로그인한다(바로 팀원) → 쓰는 도구에 주소 하나를 붙인다 → 평소처럼 일한다.

| 도구 | 연결 |
|---|---|
| Claude Code | `claude mcp add -s user --transport http pithub <MCP URL>` → `/mcp` 에서 로그인 |
| claude.ai | 설정 → 커넥터 → 커스텀 커넥터에 주소 → 로그인 |
| Codex | `codex mcp add pithub --url <MCP URL> && codex mcp login pithub` |

주소는 하나다. 팀이 하나뿐인 사람은 서버가 그 팀으로 기록한다(여러 팀이면 팀 주소 `…/t/<팀>/mcp`).
기록은 3일 뒤 팀에 보이고, 그 전에 정리함에서 뺄 수 있다.

## 직접 돌리기 (셀프호스트)

필요한 것: Python 3.11+ · [uv](https://docs.astral.sh/uv/) · Postgres(Supabase 권장) · GitHub OAuth App · HTTPS 주소(claude.ai 커넥터 요건).

```bash
git clone https://github.com/playidea-lab/pit.git && cd pit
uv sync --extra server

# 1. DB — Supabase 프로젝트를 만들고 마이그레이션 적용
cd pithub/supabase && supabase link --project-ref <ref> && supabase db push && cd ../..

# 2. MCP 서버 — 환경변수로만 설정한다 (코드에 주소·비밀 없음)
export PITHUB_GITHUB_CLIENT_ID=… PITHUB_GITHUB_CLIENT_SECRET=…   # OAuth App, 콜백 https://<서버>/auth/callback
export PITHUB_MCP_BASE_URL=https://<서버> PITHUB_JWT_SIGNING_KEY=$(openssl rand -hex 32)
export PITHUB_SUPABASE_URL=https://<ref>.supabase.co PITHUB_SUPABASE_SERVICE_KEY=…
export PITHUB_OAUTH_STORAGE_DIR=/data/oauth PITHUB_OAUTH_STORAGE_KEY=<Fernet 키>   # 재배포해도 로그인 유지
uv run python -m pit.server            # 또는 Dockerfile · fly.toml

# 3. 웹
cd pithub/web && cp .env.example .env.local   # Supabase URL·anon 키·MCP 주소
npm ci && npm run build && npm start
```

Supabase Auth의 GitHub provider에 같은 OAuth App을 넣고, OAuth App에 Supabase 콜백 URL을 추가한다.

**로그인 방식** (`PITHUB_AUTH`)
- `github` (기본): 서버가 GitHub OAuth를 중계한다. GitHub 계정만.
- `supabase` (권장): Supabase Auth의 OAuth 2.1 서버가 AI 도구 로그인을 맡고, 서버는 토큰만 검증한다. **GitHub와 이메일(매직 링크)** 모두.
  Supabase 대시보드에서 Authentication → OAuth Server 켜기 · Allow Dynamic OAuth Apps 켜기 ·
  Authorization path `/oauth/consent` · Site URL = 웹 주소 · Providers → Email 켜기.
서버는 Supabase 없이도 뜨지만 그때는 기록 도구가 "저장소 준비 중"을 돌려준다.

## 로컬 CLI `pit` (선택, 개발자용)

원문 보존과 감사를 원하는 사람만. Claude Code 세션 원문을 개인 보관함(`~/.pit`)에 지워지지 않게 복사하고,
원문에서 추출한 결정과 MCP가 기록한 결정을 대조해 **기록 누락률·판정 일치율**을 잰다.

```bash
uv tool install git+https://github.com/playidea-lab/pit.git
PITHUB_URL=https://<서버> pit setup     # 보관함 초기화, 첫 sync, 커넥터 명령 안내
pit login                               # 웹 설정에서 발급한 토큰
pit pull && pit audit mcp               # MCP 기록 감사
```

## 개발

```bash
uv sync --extra server
uv run ruff check pit tests && uv run pytest -q          # 단위 (200+)
docker run -d --name db -e POSTGRES_PASSWORD=x -p 55432:5432 postgres:17
PITHUB_TEST_DATABASE_URL=postgresql://postgres:x@127.0.0.1:55432/postgres uv run pytest -m integration   # RLS
cd pithub/web && npm ci && npm run lint && npm run build
```

테스트는 합성 데이터만 쓴다. 실제 세션 기록을 테스트에 넣지 않는다.

### 배포

`main` 에 push 하면 CI가 시험을 통과한 뒤 바뀐 부분만 운영에 올린다 (`.github/workflows/ci.yml` 의 `deploy`).
순서는 **DB 마이그레이션 → MCP 서버 → 웹**. 그래서 마이그레이션은 옛 서버와 함께 돌아도 깨지지 않게(확장만) 쓴다.
열·테이블을 지우는 마이그레이션은 첫 줄을 `-- deploy: after-server` 로 시작해 서버 배포 뒤로 미룬다.

필요한 설정: 저장소 Secrets `FLY_API_TOKEN` · `SUPABASE_ACCESS_TOKEN` · `SUPABASE_DB_PASSWORD`, Variables `SUPABASE_PROJECT_REF`.
없으면 배포 단계는 경고만 남기고 건너뛴다.

## 기여할 자리

- **소스 어댑터** — Codex, Gemini, Cursor 세션 기록 파서. `pit/vault/sources.py`의 `SourceAdapter`와
  `pit/transcripts/events.py`의 `EVENT_BUILDERS`에 등록하면 보관·추출·감사가 그대로 돈다.
- 검색 순위·원칙 압축 — `docs/PIT_KNOWLEDGE_DESIGN.md`의 단계별 착수 조건을 따른다.

## 라이선스

[AGPL-3.0-or-later](LICENSE). 이 코드로 호스팅 서비스를 제공하면 그 변경도 공개해야 합니다.
