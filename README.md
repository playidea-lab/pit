# pit – Product / Idea Tracker

> 기획/아이디어/결정/체크리스트를 Git처럼 버전 관리하고,
> git의 실제 코드와 비교하여 "기획 대비 개발 정합도"를 평가하는 PM용 관제 시스템

---

## 설치 및 실행

```bash
# 의존성 설치
uv sync

# CLI 실행
uv run pit --help
```

---

## CLI 명령어

### 프로젝트 관리
```bash
pit projects list              # 프로젝트 목록
pit projects list --json       # JSON 출력
```

### Feature 관리
```bash
pit features list <project>                    # Feature 목록
pit features create <project> -t "제목"        # Feature 생성
pit feature <project> <feature_id>             # Feature 상세
pit feature <project> <feature_id> --json      # JSON 출력
```

### 헬스 체크
```bash
pit health all                           # 전체 프로젝트 헬스
pit health project <project>             # 프로젝트 헬스
pit health feature <project> <feature>   # Feature 헬스
```

### Git 연동
```bash
pit git status                    # 현재 상태
pit git checkout <feature_id>     # Feature 브랜치 생성
pit git branches <feature_id>     # 관련 브랜치 목록
```

---

## 핵심 개념

### 4가지 핵심 단위

| 단위 | 설명 | 예시 |
|------|------|------|
| **Project** | 제품/서비스 단위 | `pit`, `slam` |
| **Feature** | 기획→개발→배포 작업 단위 | `F-0001` |
| **Checklist** | Feature 내 할 일 | `T1`, `T2` |
| **Decision/Log** | 결정 기록 / 회의 로그 | `D-0001` |

### pit-flow

```
planned → in_progress → ready_for_merge → merged → released
```

### 헬스 체크

```
🟢 Green (80+): 정상 진행
🟡 Yellow (50-79): 지연/주의
🔴 Red (<50): 위험/긴급
```

---

## 프로젝트 구조

```
pit/
├── pit/                    # Python 패키지
│   ├── cli/               # CLI 명령어 (Typer)
│   ├── core/              # 핵심 로직 (health, git)
│   ├── loaders/           # YAML 로더
│   └── models/            # Pydantic 모델
├── projects/              # 프로젝트 데이터
│   └── <project_id>/
│       ├── project.yaml
│       ├── features/
│       ├── decisions/
│       └── logs/
├── tests/                 # 테스트
└── docs/                  # 설계 문서
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
| [PIT_IMPLEMENTATION_PLAN](docs/PIT_IMPLEMENTATION_PLAN.md) | 구현 로드맵 |

---

## 기술 스택

- Python 3.11+
- uv (패키지 관리)
- Typer + Rich (CLI)
- Pydantic v2 (데이터 모델)
- 파일 기반 SSOT (YAML/MD + Git)

---

## 테스트

```bash
uv run pytest -v
```

---

## 현재 상태

**v0.1.0 - CLI MVP 완료**

- [x] Week 0: 레포/환경 설정
- [x] Week 1: 데이터 모델 구현
- [x] Week 2: CLI v0 (조회/생성)
- [x] Week 3: Git 연동
- [x] Week 4: 헬스 체크 + Dogfooding

---

## 라이선스

MIT
