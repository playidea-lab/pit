---
id: D-0005
project_id: pit
title: pithub는 원격 MCP 서버다 - Python FastMCP + GitHub 로그인, Fly.io + Supabase
status: active
supersedes: [D-0003]
created_at: 2026-09-22T08:00:00+09:00
---

# pithub는 원격 MCP 서버다

> D-0004는 `wip/f-0005-agents` 브랜치에 보존돼 있어 번호를 건너뛴다.

## 배경

pit을 "설치해서 쓰는 제품"으로 만들고, 개발자가 아닌 사람도 claude.ai · Claude Code · Codex를
쓰기만 하면 결정이 기록되게 하려 한다. 처음 설계는 도구마다 세션 기록 파서를 만들고 별도의
LLM 호출로 결정을 추출하는 것이었다. 그 방식은 claude.ai를 지원할 길이 없고(로컬 기록이 없다),
API 키가 없는 사람은 추출을 쓸 수 없다.

## 결정

1. **pithub가 원격 MCP 서버가 된다.** 세 도구가 같은 커넥터(`/mcp`)에 붙고, 세션의 LLM이
   결정이 내려질 때 도구를 호출해 기록한다. 비개발자의 설치는 "커넥터 추가 + GitHub 로그인"이다.
2. **인증은 직접 구현하지 않는다.** Python FastMCP의 `GitHubProvider`가 GitHub OAuth를 중계하면서
   claude.ai 커스텀 커넥터의 요구(OAuth 2.1, 동적 클라이언트 등록, PKCE S256)를 채운다.
   요청 권한은 `read:user`뿐이다. 토큰의 `sub`(GitHub 숫자 id)가 pithub 계정을 잇는 열쇠다.
3. **MCP 서버는 Python, Fly.io에 올린다.** 상시 프로세스라 가능하고, `pit/`의 가림 처리·결정
   모델을 서버가 그대로 import한다. 데이터는 Supabase(Postgres + RLS), 웹은 Next.js.
4. **로컬 `pit`(보관함·추출)은 선택 설치이자 감사 도구다.** 원문 보존, 백필, 그리고 MCP 기록의
   누락·수위 완화를 원문 추출과 대조해 재는 데 쓴다.

## 근거 — 연결 시험(P0) 결과, 2026-09-22

`https://pit.fly.dev/mcp` (도구 `whoami` 하나)에 대해:

| 클라이언트 | 연결 방법 | 결과 |
|---|---|---|
| Claude Code | `claude mcp add --transport http` → `/mcp` → Authenticate | 통과 |
| claude.ai | 설정 → 커넥터 → 커스텀 커넥터 추가 | **통과** (가장 큰 미지수였다) |
| Codex 앱 | Settings → MCP servers → Add server (Streamable HTTP) | 통과 |

서버 로그: `/auth/callback` 302, `/token` 200, 인증된 `/mcp` 200. 공개 주소에서 인가 서버 메타데이터,
보호 리소스 메타데이터, 미인증 401 + `WWW-Authenticate`, claude.ai 콜백 주소로의 클라이언트 등록을 확인했다.

## D-0003을 대체하는 이유

D-0003은 "백엔드가 Python이면 `pit`의 모델·로더를 재사용할 수 있다"는 이유로 FastAPI + Next.js를
골랐다. 실제 구현은 Deno Edge Functions로 흘러갔고 Python 재사용은 한 줄도 일어나지 않았으며,
FastAPI 쪽은 호출하는 곳 없는 사본으로 남았다(삭제함). 이번에는 같은 목적이 실제로 성립한다.
단, 백엔드의 역할이 "GitHub 저장소의 `.pit/`를 읽어 보여 주는 API"에서 "결정을 받는 MCP 서버"로 바뀌었다.

## 대안

- **Supabase Auth의 OAuth 2.1 서버를 인가 서버로** — 시험하지 않았다. `GitHubProvider`가 먼저 통과했고
  직접 구현할 코드가 없어서 더 단순하다.
- **MCP 서버만 Cloudflare Workers(공식 GitHub OAuth 템플릿)로 분리** — claude.ai가 붙지 않을 때의
  대비책이었다. 필요 없어졌다. 플랫폼이 셋으로 늘고 Python 재사용이 불가능해진다.
- **도구별 세션 파서 + 별도 LLM 추출을 주경로로** — claude.ai 불가, 비개발자 불가. 감사용으로만 남긴다.

## 알고 가는 대가

- 도구 호출은 모델 재량이라 기록이 누락된다. 거부("아니 그거 말고")일수록 빠지기 쉽다.
- 판정받은 당사자(LLM)가 판정을 기록한다. 수위가 누그러질 수 있다.
- 결정 초안이 사람의 검토 전에 서버에 도착한다. 원문은 나가지 않지만 "본인만 본다"는 서버에 대한 신뢰 약속이 된다.
- 세션에 도구 호출 표시가 보인다.

앞의 둘은 추측하지 않고 잰다: 같은 Claude Code 세션에서 MCP 기록과 원문 추출을 대조한다
(사전 선언 기준: 재현율 ≥ 60%, 거부 재현율 ≥ 50%, 판정 일치율 ≥ 85%).

## 재검토 조건

- 위 측정이 기준에 미달하고 지침 보강으로도 회복되지 않을 때 → 개발자 도구에서는 추출을 다시 주경로로.
- claude.ai가 커넥터 인증 요구사항을 바꿔 `GitHubProvider`가 더는 붙지 않을 때.
- 연결 시험 서버는 OAuth 클라이언트 등록을 프로세스 메모리에 둔다. 재배포하면 재로그인이 필요하다 —
  실제 도구를 올리기 전에 영속 저장소로 옮긴다.
