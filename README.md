# pit – Product / Idea Tracker

> 기획/아이디어/결정/체크리스트를 Git처럼 버전 관리하고,
> LLM과 대화하며 기획 내용을 구조화하는 PM용 관제 시스템

---

## Quick Start

```bash
# 설치
uv sync

# 프로젝트 초기화 (git init처럼)
cd /path/to/my-project
uv run pit init

# Feature 관리
uv run pit features list
uv run pit features create "새 기능"
uv run pit feature F-0001

# LLM 채팅 (Claude API 필요)
uv run pit chat
```

---

## 핵심 개념

### .pit/ 폴더 기반 로컬 관리

git이 `.git/` 폴더로 동작하듯이, pit도 `.pit/` 폴더로 동작합니다.

```
my-project/
├── .git/                    # git 저장소
├── .pit/                    # pit 저장소
│   ├── config.yaml          # 프로젝트 설정
│   ├── features/            # Feature 파일들
│   │   ├── F-0001-xxx.yaml
│   │   └── F-0002-xxx.yaml
│   ├── decisions/           # 결정 기록
│   │   └── D-0001-xxx.md
│   └── logs/                # 회의/대화 로그
│       └── 2025-12-12-session-001.md
├── src/
└── tests/
```

### 4가지 핵심 단위

| 단위 | 설명 | 예시 |
|------|------|------|
| **Project** | 제품/서비스 단위 (`.pit/config.yaml`) | `pit`, `slam` |
| **Feature** | 기획→개발→배포 작업 단위 | `F-0001` |
| **Checklist** | Feature 내 할 일 | `T1`, `T2` |
| **Decision/Log** | 결정 기록 / 회의 로그 | `D-0001` |

### pit-flow (상태 머신)

```
planned → in_progress → ready_for_merge → merged → released
```

---

## CLI 명령어

### 프로젝트 관리

```bash
pit init                       # .pit/ 폴더 초기화
pit init --name "프로젝트명"   # 이름 지정

pit projects list              # 현재 프로젝트 목록
pit projects info              # 현재 프로젝트 정보
```

### Feature 관리

```bash
pit features list              # Feature 목록 (현재 .pit/ 기준)
pit features create "제목"     # 새 Feature 생성
pit feature F-0001             # Feature 상세 보기
pit feature F-0001 --json      # JSON 출력
```

### 헬스 체크

```bash
pit health all                 # 전체 헬스 체크
pit health project             # 프로젝트 헬스
pit health feature F-0001      # Feature 헬스
```

```
🟢 Green (80+): 정상 진행
🟡 Yellow (50-79): 지연/주의
🔴 Red (<50): 위험/긴급
```

### Git 연동

```bash
pit git status                 # 현재 상태
pit git checkout F-0001        # Feature 브랜치 생성
pit git branches F-0001        # 관련 브랜치 목록
```

### LLM 채팅

```bash
pit chat                       # Claude와 대화하며 기획 정리

# .env에 API 키 필요
ANTHROPIC_API_KEY=sk-ant-...
```

---

## MCP Server (Claude Desktop 연동)

Claude Desktop에서 pit 도구를 직접 사용할 수 있습니다.

### 설정

`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pit": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/pit", "python", "-m", "pit.mcp_server"],
      "env": {
        "PIT_ROOT": "/path/to/your-project"
      }
    }
  }
}
```

### 사용 가능한 도구

- `pit_detect_context` - 현재 프로젝트 컨텍스트 감지
- `pit_list_features` - Feature 목록 조회
- `pit_get_feature` - Feature 상세 조회
- `pit_create_feature` - 새 Feature 생성
- `pit_create_decision` - 결정 기록 생성
- `pit_create_log` - 회의 로그 생성
- `pit_check_health` - 헬스 체크

---

## 프로젝트 구조

```
pit/
├── pit/                    # Python 패키지
│   ├── cli/               # CLI 명령어 (Typer)
│   │   ├── main.py        # 메인 엔트리
│   │   ├── features.py    # features 명령어
│   │   ├── projects.py    # projects 명령어
│   │   ├── health.py      # health 명령어
│   │   ├── git.py         # git 명령어
│   │   ├── chat.py        # chat 명령어
│   │   └── init.py        # init 명령어
│   ├── core/              # 핵심 로직
│   │   ├── context.py     # .pit/ 컨텍스트 감지
│   │   ├── health_check.py
│   │   ├── git_integration.py
│   │   └── chat.py        # LLM 채팅 로직
│   ├── loaders/           # YAML 로더
│   ├── models/            # Pydantic 모델
│   └── mcp_server.py      # MCP Server
├── .pit/                   # pit 자체 프로젝트 데이터 (dogfooding)
├── tests/                  # 테스트
└── docs/                   # 설계 문서
```

---

## 문서

| 문서 | 설명 |
|------|------|
| [PIT_OVERVIEW](docs/PIT_OVERVIEW.md) | 프로젝트 정의, 문제, 가치 제안 |
| [PIT_USAGE_GUIDE](docs/PIT_USAGE_GUIDE.md) | PM/개발자 사용 가이드 |
| [PIT_DATA_MODEL](docs/PIT_DATA_MODEL.md) | 데이터 스키마 정의 |
| [PIT_FLOW_SPEC](docs/PIT_FLOW_SPEC.md) | pit-flow 상태 머신 |
| [PIT_CLI_SPEC](docs/PIT_CLI_SPEC.md) | CLI 명령어 스펙 |
| [PIT_TECH_STACK](docs/PIT_TECH_STACK.md) | 기술 스택 |
| [PIT_AGENT_DESIGN](docs/PIT_AGENT_DESIGN.md) | LLM 에이전트 설계 |

---

## 기술 스택

- Python 3.11+
- uv (패키지 관리)
- Typer + Rich (CLI)
- Pydantic v2 (데이터 모델)
- Anthropic Claude API (LLM 연동)
- MCP (Model Context Protocol)
- 파일 기반 SSOT (YAML/MD + Git)

---

## 테스트

```bash
uv run pytest -v
uv run ruff check pit/
```

---

## 현재 상태

**v0.2.0 - .pit/ 폴더 기반 + LLM 연동**

| Feature | Status | Progress |
|---------|--------|----------|
| F-0001: CLI MVP | merged | 8/8 |
| F-0002: 문서 통합 | merged | 6/6 |
| F-0003: .pit/ 폴더 + LLM | merged | 8/8 |
| F-0004: pithub 웹 서비스 | planned | 0/8 |

---

## Roadmap

- [x] v0.1 - CLI MVP (조회/생성/헬스체크)
- [x] v0.2 - .pit/ 폴더 기반 + LLM 연동
- [ ] v0.3 - pithub 웹 서비스 (github → pithub URL 변환)
- [ ] v0.4 - GitHub Action 연동

---

## 라이선스

MIT
