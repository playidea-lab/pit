# PIT 기술 스택 정의 – `PIT_TECH_STACK.md`

> 이 문서는 **pit (Product / Idea Tracker)** 프로젝트의  
> 기본 기술 스택과 선택 기준을 정리한 문서이다.  
> v0 ~ v1 구현 동안 “웬만하면 이 방향으로 간다”는 가드레일 역할을 한다.

---

## 1. Runtime & Target 환경

### 1.1 언어 / 런타임

- **Language**: Python **3.11+**
- 이유:
  - 최신 `typing` 지원 (PEP 649 등 향후 기능 고려)
  - `pydantic v2`와의 궁합/성능
  - async/typing 관련 생태계가 3.11 이후 안정적

### 1.2 OS 타겟

- 1차 타겟:
  - **macOS**, **Linux**
- Windows는:
  - 우선순위 낮게, 기본 기능 위주로 동작 확인 수준

---

## 2. 패키지 & 환경 관리

### 2.1 패키지 / 환경 매니저

- **`uv`**
  - 가벼운 venv + 패키지 관리 + 실행을 한 번에 제공
  - 빠른 설치 속도, modern한 워크플로우

### 2.2 빌드 설정

- **`pyproject.toml`** 기반
  - 빌드 백엔드:
    - 우선 후보: `hatchling` 또는 `setuptools`
    - v0에서는 의존도 낮은 `hatchling` 선호

---

## 3. 코어 라이브러리

### 3.1 데이터 모델 & 검증

- **pydantic v2**
  - 장점:
    - 강력한 validation
    - typing 친화적인 모델 정의
    - 설정/환경/입출력 변환에 용이

용도:

- Project / Feature / Checklist / Decision / Log / HealthReport 등  
  `PIT_DATA_MODEL.md` 에 정의된 구조를 모두 Pydantic 모델로 구현.

### 3.2 YAML 파싱

- **pyyaml**
  - Feature/Project/Task 정의용 YAML 파일 파싱
  - YAML → Pydantic 모델 변환

### 3.3 Markdown + Frontmatter

- 후보:
  - `python-frontmatter` (심플)
  - 또는 `markdown-it-py` + 직접 frontmatter 처리
- 용도:
  - Decision / Log 문서에서
    - 상단 frontmatter (메타데이터)
    - 하단 markdown 본문

---

## 4. CLI & 터미널 UX

### 4.1 CLI 프레임워크

- **Typer**
  - Click 기반, type hint 친화적인 CLI 프레임워크
  - `pit` 명령과 서브커맨드 구조에 적합
  - 직관적인 함수형 API

용도:

- `PIT_CLI_SPEC.md` 에 정의된:
  - `pit projects list`
  - `pit feature show`
  - `pit feature create`
  - `pit checklist list` …  
  전체를 Typer 앱으로 구현.

### 4.2 출력 렌더링

- **Rich**
  - 컬러 출력, 표(table), 구분선, 하이라이트 등
  - CLI UX 향상을 위해 사용

용도:

- Feature 리스트/체크리스트/헬스 상태 등을  
  “문서 같은 텍스트”가 아니라  
  “한 눈에 읽히는 표/블록”으로 표현.

---

## 5. 데이터 저장 레이어 (파일 + DB)

### 5.1 v0 – 파일이 SSOT

- **Single Source of Truth (SSOT)**:
  - `projects/<project_id>/project.yaml`
  - `projects/<project_id>/features/*.yaml`
  - `projects/<project_id>/decisions/*.md`
  - `projects/<project_id>/logs/*.md`

특징:

- Git으로 버전 관리 가능
- 에디터/CLI/에이전트가 모두 같은 파일을 바라봄
- pit는 이 파일 구조를 읽고 쓰는 도구 역할

### 5.2 v0.5+ – SQLite 인덱스/캐시 레이어

- **DB: SQLite**
  - 파일 기반, 의존성 최소
  - 로컬 개발 환경에서 부담 없이 사용 가능

용도:

- Feature/Task 인덱싱
- 프로젝트/헬스 상태 빠른 조회
- 히스토리/로그 조회 최적화
- (미래) 헬스 점수/활동 타입별 통계

### 5.3 ORM/DB 접근

- 초기 전략:
  - **SQLAlchemy Core** 선호
    - ORM보다는 “쿼리 빌더 + 스키마 정의” 정도로 얇게 사용
    - pit는 “거대한 비즈니스 DB”가 아니라 “인덱스/캐시” 목적이기 때문
- 필요 시:
  - `SQLModel` 도입 검토 (Pydantic 친화적인 SQLAlchemy 래퍼)

---

## 6. Web/API 레이어 (선택 / v1 이후)

### 6.1 Web API 프레임워크

- **FastAPI**
  - Pydantic 모델과 자연스럽게 연동
  - LLM 에이전트/외부 서비스에서 pit 데이터를 HTTP로 접근하기 좋음
  - Async-friendly

예상 용도:

- `/projects`, `/projects/{id}/features`, `/features/{id}`, `/health/...` 등
- LLM 에이전트 / Web UI / 다른 마이크로서비스에서 호출

### 6.2 실행/배포

- 로컬 개발:
  - `uvicorn` + FastAPI
- 추후 배포:
  - Docker 컨테이너로 감싸서 dev/stage/prod 환경에 배포 가능  
  (단, pit는 기본적으로 “로컬에서 잘 돌아가는 도구”에 우선순위)

---

## 7. Git 연동

### 7.1 기본 접근 방식

- v0:
  - **`subprocess` 기반 `git` wrapper**
    - `git status`, `git rev-parse`, `git log`, `git branch`, `git push` 등
    - OS에 설치된 git CLI를 호출하는 방식
- 장점:
  - 의존성 최소
  - GitPython, LibGit2 등에 lock-in 되지 않음

### 7.2 확장 가능성

- 필요 시:
  - **GitPython** 도입 고려
    - 고급 기능/복잡한 연산 (rebase, cherry-pick 등)이 필요할 때
- Abstract Layer:
  - 내부적으로는 `GitClient` 인터페이스 정의:
    - `get_current_branch()`
    - `get_latest_commit()`
    - `create_branch_from(base, name)` 등
  - 구현체:
    - `SubprocessGitClient` (기본)
    - 추후 `GitPythonGitClient` 등 추가 가능

---

## 8. 테스트 & 품질 도구

### 8.1 테스트

- **pytest**
  - Python 표준 사실상 디팩토
  - fixture 기반, CLI 플러그인 풍부

용도:

- 데이터 모델 테스트
- 파일 파서/직렬화 테스트
- CLI 명령 테스트 (Typer + CliRunner)
- 헬스 체크/정합도 로직 테스트

### 8.2 Lint & Format

- **ruff**
  - lint + 일부 포매팅까지 지원
  - 빠른 속도
- (옵션) **black**
  - 코드 포매터로 ruff와 조합 가능
  - 또는 `ruff format`만 사용

### 8.3 타입 체크

- 선택:
  - **mypy** 또는 **pyright**
- 권장:
  - H/M 레벨의 중요 패스 (모델/파일 파서/헬스 엔진)에 타입 체크 적용

### 8.4 pre-commit

- **pre-commit hooks**
  - `ruff`, `black`, `pytest -q` 일부 등을 hook으로 설정
  - 팀 내부 일관성 유지

---

## 9. TUI & 기타 UX

### 9.1 TUI 프레임워크

- 후보:
  - **Textual**
    - 리치한 TUI 화면 (리스트/패널/레이아웃)
  - 또는 간단히:
    - Rich + Typer 조합에서 시작해 “반-TUI 스타일”

전략:

- v0:
  - Typer + Rich 기반 CLI에 집중
- v0.5:
  - Textual로
    - 좌측: Feature 리스트
    - 우측: 선택된 Feature 상세/체크리스트
    - 하단: 로그/헬스 메시지  
    정도의 TUI PoC 구현

---

## 10. 에이전트/LLM 연동

### 10.1 LLM 백엔드와의 관계

- pit-core는 특정 LLM 서비스(OpenAI, Claude 등)에 의존하지 않는다.
- 대신, **“LLM 클라이언트 추상화 레이어”**만 제공한다:

예시:

- `pit/agent/client.py`:
  - `generate_completion(prompt: str, ...) -> str`
  - `structured_output(prompt: str, schema: ...) -> dict`

### 10.2 사용 맥락

- `PIT_AGENT_DESIGN.md` 에 정의된:
  - `feature-writer`, `decision-writer`, `log-writer`
  - `spec-analyzer`, `git-analyzer`, `health-judge`  
  등의 에이전트가 이 클라이언트 레이어를 통해 LLM을 호출.

### 10.3 안전/보안

- API 키/secret 관리는 pit의 책임에서 제외:
  - `.env` / Vault / OS Keychain 등 외부 시스템 활용
- pit 문서에는:
  - “LLM API 키는 pit 내에 저장하지 말 것” 원칙 정도만 명시

---

## 11. 우선순위 정리

### 11.1 v0 (필수)

- Python 3.11
- uv
- Typer + Rich
- Pydantic v2 + PyYAML
- 파일 기반 SSOT
- pytest + ruff
- subprocess 기반 git wrapper

### 11.2 v0.5 (고도화)

- SQLite 인덱스/캐시
- SQLAlchemy Core
- Textual TUI 초안
- 헬스/정합도 엔진 1차 구현

### 11.3 v1 이후 (선택/확장)

- FastAPI 기반 Web/API
- GitPython (필요 시)
- 더 정교한 헬스 분석/타임라인/통계
- LLM 에이전트 통합 (MCP, IDE 플러그인 등)

---

## 12. 요약

> pit 기술 스택은  
> **“로컬에서 가볍게 돌고, Git과 잘 붙고,  
>  나중에 Web/API/에이전트까지 확장 가능한 Python 도구”**  
> 를 목표로 한다.
>
> - uv + Typer + Rich + Pydantic v2 + PyYAML 조합을 기본 축으로 두고,  
> - SQLite/SQLAlchemy/ FastAPI/ Textual/에이전트 연동은  
>   필요와 여유에 따라 단계적으로 올리는 구조다.
>
> 이 문서(`PIT_TECH_STACK.md`)는  
> 앞으로 pit 구현을 시작할 때,  
> “무슨 라이브러리 쓰지?” 고민을 줄이기 위한  
> **초기 합의안(Convention)** 으로 사용된다.
