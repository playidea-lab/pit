# PIT 구현 계획 – `PIT_IMPLEMENTATION_PLAN.md`

> 이 문서는 pit 시스템의 **v0 ~ v1 구현 로드맵**을 정리한 것이다.  
> 실제로 1인/소규모 팀이 따라가면서 개발할 수 있도록  
> **주차별, 단계별, 체크리스트 형태**로 구성한다.

---

## 0. 전제 조건 (Assumptions)

- 주요 참고 문서
  - `PROJECT_DEFINITION.md`
  - `PIT_DATA_MODEL.md`
  - `PIT_FLOW_AND_CHECKLIST_SPEC.md`
- 1차 목표 범위
  - **파일 기반** pit (Git 레포 안에 YAML/MD로 쌓이는 구조)
  - **로컬 개발자/PM**이 바로 쓸 수 있는 수준의 v0
- 기술 스택 (가정)
  - Python 3.11+
  - Poetry 또는 uv 기반 패키지 관리
  - Typer 또는 Click 기반 CLI
  - Textual / Rich / prompt-toolkit 등 선택형 TUI (v0.5 이후)

---

## 1. 전체 타임라인 요약

> 각 “주(Week)”는 실제로는 유연하게 당겨지거나 늘어날 수 있다.  
> 여기서는 기준이 되는 **작업 순서/우선순위**에 의미를 둔다.

- **Week 0**: 레포 구조/개발 환경 부트스트랩
- **Week 1**: 데이터 모델 & 파일 구조 구현 (파서 + 검증)
- **Week 2**: 기본 CLI v0 (로컬 파일 기반 조회/생성)
- **Week 3**: CLI 확장 + Git 최소 연동 + 간단 TUI 초안
- **Week 4**: 정합도/헬스 체크 초벌 로직 + Dogfooding 시작
- **Week 5~**: 백엔드/API + 에이전트 연동(옵션), UI 고도화

각 주차마다 **“완료 기준(Checklist)”**을 함께 적어,  
스스로 pit를 사용해 pit를 관리할 수 있게 만드는 것이 목표다.

---

## 2. Week 0 – 레포 & 개발 환경 부트스트랩

### 2.1 목표

- `playidea-pit` 레포를 만들고,  
  기본적인 Python 패키징/테스트 구조를 세팅한다.
- 문서 디렉터리와 코드 디렉터리를 분리하고,  
  git 기준으로 버전 관리가 바로 가능하도록 만든다.

### 2.2 작업 항목

1. **레포 생성**
   - GitHub/GitLab 등에서 `playidea-pit` 리포지토리 생성.
   - `.gitignore`, `LICENSE`, `README.md` 기본 세팅.

2. **디렉터리 구조 초기화 (예시)**

   ```text
   playidea-pit/
     docs/
       PROJECT_DEFINITION.md
       PIT_DATA_MODEL.md
       PIT_FLOW_AND_CHECKLIST_SPEC.md
       PIT_IMPLEMENTATION_PLAN.md
     pit/
       __init__.py
       core/
       cli/
       models/
       utils/
     tests/
       __init__.py
   ```

3. **Python 프로젝트 설정**
   - `pyproject.toml` 생성 (Poetry/uv/Flit 등 선택).
   - 기본 의존성:
     - `pydantic` (데이터 모델 검증)
     - `pyyaml` (YAML 파싱)
     - `typer` or `click` (CLI)
     - `rich` (컬러 출력)

4. **기본 테스트 환경**
   - `pytest` 설정.
   - `tests/test_sanity.py` 하나 만들어 “import 잘 되는지” 정도만 확인.

### 2.3 완료 체크리스트

- [ ] `playidea-pit` 레포 생성 완료
- [ ] `docs/` 폴더에 현재까지 만든 md 문서 반영
- [ ] `pyproject.toml` 및 기본 의존성 설치
- [ ] `pytest`로 최소 1개 테스트 통과

---

## 3. Week 1 – 데이터 모델 & 파일 구조 구현

### 3.1 목표

- `PIT_DATA_MODEL.md` 내용을 코드로 옮겨  
  **Pydantic 모델 + 파일 파서/직렬화기**로 구현한다.
- `projects/` 디렉터리 구조를 생성하고,  
  실제 예시 데이터를 1~2개 만들어본다.

### 3.2 작업 항목

1. **Pydantic 모델 정의**

   - `pit/models/project.py`
   - `pit/models/feature.py`
   - `pit/models/decision.py`
   - `pit/models/log.py`
   - `pit/models/task.py` (Checklist Task)
   - 각 모델은 `PIT_DATA_MODEL.md`의 필드/타입을 최대한 반영.

2. **파일 레이어 구현**

   - `pit/core/file_store.py` (예시 이름)
     - `load_project(project_id) -> Project`
     - `list_projects() -> list[Project]`
     - `load_feature(project_id, feature_id) -> Feature`
     - `list_features(project_id) -> list[Feature]`
   - YAML/MD 읽기:
     - Feature: YAML
     - Decision/Log: Frontmatter + Markdown 본문 패턴 지원

3. **샘플 데이터 생성**

   - `projects/pit/project.yaml`
   - `projects/pit/features/F-0001-pit-core-mvp.yaml`
   - `projects/pit/decisions/D-0001-...md`
   - `projects/pit/logs/2025-12-12-session-001.md`

4. **간단 검증 테스트**

   - `tests/test_project_loading.py`
   - `tests/test_feature_loading.py`
   - 실제 샘플 파일을 로딩해서, 필드가 제대로 채워지는지 확인.

### 3.3 완료 체크리스트

- [ ] Pydantic 기반 데이터 모델 정의 완료
- [ ] `projects/` 폴더 아래 pit 샘플 데이터 구성
- [ ] 프로젝트/Feature/Decision/Log 로딩 테스트 통과
- [ ] md/YAML를 직접 수정해보고, 다시 로드했을 때 문제 없는지 확인

---

## 4. Week 2 – CLI v0 (파일 기반 조회/생성)

### 4.1 목표

- 터미널에서 **프로젝트/Feature 목록을 조회하고,  
  새로운 Feature/Decision/Log를 생성할 수 있는** 기본 CLI를 만든다.
- 아직 git 연동은 하지 않고, 오직 **파일 읽기/쓰기**에 집중한다.

### 4.2 작업 항목

1. **CLI 엔트리포인트**

   - `pit/cli/main.py` + `console_scripts` 설정
   - `pit` 명령으로 실행되도록 구성

2. **기본 명령 설계**

   - `pit projects list`
   - `pit features list --project pit`
   - `pit feature show F-0001 --project pit`
   - `pit feature create --project pit`  
     (대화형 입력 or 템플릿 기반 생성)

3. **생성 로직 구현**

   - Feature 생성 시:
     - ID 자동 부여(`F-0001` 등) or 수동 입력 옵션
     - 템플릿 YAML을 기반으로 파일 생성
   - Decision/Log 생성도 비슷한 패턴 적용 가능 (v0에서는 선택)

4. **출력 포맷 개선**

   - `rich` 를 사용해서:
     - Feature 리스트를 표 형태로 깔끔하게 출력
     - 상태/우선순위/owner 등을 색깔로 구분

5. **테스트**

   - CLI 레벨 테스트 or 핵심 함수 단위 테스트 작성
   - 최소한 `projects list`, `features list`가 정상 동작하는지 확인

### 4.3 완료 체크리스트

- [ ] `pit` 명령으로 프로젝트/Feature 목록 조회 가능
- [ ] 새로운 Feature를 CLI로 생성 가능
- [ ] 생성된 파일이 `PIT_DATA_MODEL` 형식에 맞게 잘 만들어지는지 확인
- [ ] 실제 pit 프로젝트에서 1~2개 새로운 Feature를 CLI로 생성해봄

---

## 5. Week 3 – CLI 확장 + Git 최소 연동 + TUI 초안

### 5.1 목표

- Feature ↔ Git을 **부드럽게 이어주는 최소 기능**을 만든다.
- 간단한 TUI 프로토타입을 만들어,  
  “좌측 리스트 + 우측 상세” 형태를 느껴본다.

### 5.2 작업 항목

1. **`.pit.yml` 스펙 정의 & 파서**

   - 각 코드 레포 루트에 `.pit.yml` 배치 (예: slam, pit-core 등)
   - 필드 예:
     ```yaml
     project_id: pit
     pit_repo_path: /Users/changmin/git/playidea-pit
     ```
   - `pit/core/repo_config.py` 등으로 파싱/캐싱

2. **Git 연동 최소 기능**

   - `pit feature checkout F-0001` 명령
     - 현재 디렉터리 기준으로 `.pit.yml` 읽기
     - Feature ID 기반으로 브랜치 이름 제안
       - 예: `feature/F-0001-pit-core-mvp`
     - 실제 git 브랜치 생성 (`gitpython` 또는 `subprocess`)

3. **Feature ↔ git_links 연결**

   - `pit feature link-git F-0001` 등으로:
     - 현재 브랜치 정보 읽어서 Feature의 `git_links`에 반영
   - 간단한 `status` 명령:
     - `pit feature status F-0001` →  
       - 체크리스트 진행도
       - git 브랜치/PR 상태(간단)

4. **TUI 초안**

   - 예: `pit/cli/tui.py`
   - Textual/Rich/TUI 라이브러리 중 하나 선택:
     - 좌측: Feature 리스트
     - 우측: 선택된 Feature 상세 + 체크리스트
   - v0에서는 **읽기 전용(read-only)** 만 구현해도 충분

### 5.3 완료 체크리스트

- [ ] `.pit.yml` 기반 레포 ↔ 프로젝트 연결 가능
- [ ] `pit feature checkout` 으로 브랜치 생성 테스트 완료
- [ ] 간단한 `pit feature status F-0001` 출력 구현
- [ ] TUI 초안에서 Feature 목록/상세를 볼 수 있음

---

## 6. Week 4 – 정합도/헬스 체크 초벌 + Dogfooding 시작

### 6.1 목표

- 아주 단순한 규칙 기반으로라도 **헬스 체크/정합도 신호**를 구현.
- 실제로 pit, slam, pios 같은 프로젝트에 적용해보며  
  “실제 업무에 도움이 되는지”를 검증한다.

### 6.2 작업 항목

1. **헬스 체크 로직 초벌**

   - `pit/core/health_check.py` (예시)
   - 입력:
     - Feature 객체
     - git_links 정보 (브랜치/최근 커밋 시각 등)
   - 출력:
     - `status: green/yellow/red`
     - `reasons: [ ... ]` (문자열 리스트)

   - 예시 규칙:
     - 필수 Task 미완료 + due_date 지남 → yellow/red
     - urgent Task 존재 + 최근 커밋 없음 → red
     - 상태가 `in_progress`인데 오래 변동 없음 → yellow

2. **CLI 연동**

   - `pit health project pit`
   - `pit health feature F-0001`
   - 결과를 색깔/아이콘으로 표시

3. **실제 프로젝트 적용 (Dogfooding)**

   - pit 프로젝트 자체부터 pit에 등록:
     - PROJECT_DEFINITION, DATA_MODEL, FLOW_SPEC, IMPLEMENTATION_PLAN을  
       실존 Feature로 관리
   - slam, pios 중 하나를 골라 최소 1~2개 Feature를 pit로 관리.

4. **피드백 기록**

   - 실제로 쓰면서 느낀 불편/개선점을  
     새로운 Feature/Decision/Log로 남기기 (자기 자신을 먹는 구조)

### 6.3 완료 체크리스트

- [ ] 간단 헬스 체크 로직 구현
- [ ] `pit health` 명령으로 프로젝트/Feature 헬스 출력
- [ ] pit 프로젝트에 최소 3개 이상 Feature를 등록하고 사용
- [ ] 실제 사용 피드백을 Log/Decision으로 기록

---

## 7. Week 5~ – API/에이전트 연동 (선택, 필요 시 확장)

> 이 단계는 “있으면 좋다” 영역이다.  
> 당장 필요하지 않으면 뒤로 미뤄도 된다.

### 7.1 목표

- 백엔드 API를 만들어,  
  나중에 웹/UI/에이전트에서 pit 데이터를 쉽게 가져다 쓸 수 있게 한다.
- 에이전트 설계 문서(`PIT_AGENT_DESIGN.md`)를 반영한다.

### 7.2 작업 항목

1. **FastAPI 백엔드 초안**

   - `pit/api/main.py`
   - 엔드포인트:
     - `GET /projects`
     - `GET /projects/{id}/features`
     - `GET /features/{id}`
     - `GET /features/{id}/health`

2. **에이전트/LLM 연동**

   - (예: 별도 리포 또는 노트북에서)
   - ChatGPT/LLM이:
     - pit API를 호출해 Feature 목록/내용을 가져오고,
     - 새로운 Feature YAML/MD 블록을 생성하도록 한다.

3. **간단 Web UI (있으면 좋음)**

   - React/Next/Vue 중 아무거나
   - “프로젝트/Feature 리스트 + 헬스 신호등” 화면만 있어도 OK

### 7.3 완료 체크리스트

- [ ] FastAPI로 최소 GET API 3~4개 구현
- [ ] LLM이 pit API를 읽고, Feature 생성 yaml을 제안하는 플로우 테스트
- [ ] 필요 시 Web UI PoC 1개 작성

---

## 8. 기술 부채 / 리스크 리스트

개발하면서 의식적으로 모아둘 문제들:

1. **데이터 스키마 변경**
   - 초기엔 자주 바뀔 수 있다.
   - 가능한 한 Pydantic 모델/마이그레이션 스크립트로 흡수.

2. **Git 의존성**
   - `gitpython` 같은 라이브러리에 과도하게 종속되지 않도록 주의.
   - 핵심 로직은 “상태 추상화” 레이어에서 처리.

3. **에이전트 난립 리스크**
   - 초기에는 “pit-orchestrator + git-analyzer + spec-analyzer” 정도로 제한.
   - 새로운 역할이 필요할 때마다 문서에 먼저 정의 후 추가.

4. **과도한 UI 욕심**
   - CLI/TUI가 이미 강력하다면, Web UI는 나중으로 미뤄도 된다.
   - “실사용에 도움이 되는 최소 화면”에 집중.

---

## 9. 일일/주간 운영 루틴 예시

### 9.1 하루 루틴 (대표/PM 관점)

1. 하루 시작:
   - `pit health project pit` 한 번 찍어봄.
   - urgent/critical Task 확인.
2. 작업/회의 후:
   - 중요한 논의는 Log로 정리.
   - 새로운 Feature 아이디어가 나오면 중간중간 등록만 해두기.
3. 하루 마감:
   - 그날 진행된 Task를 체크하고,
   - 상태 변화가 있는 Feature는 `status`를 업데이트.

### 9.2 주간 루틴

1. 주간 계획:
   - 이번 주에 집중할 Feature를 pit에서 고른다.
   - 각 Feature의 체크리스트를 정제/우선순위 조정.
2. 중간 점검:
   - `pit health project pit` 상태를 보며  
     “이번 주에 위험한 녀석들”을 식별.
3. 회고:
   - Incident나 의미 있는 결정이 있었다면  
     Decision/Log 문서로 정리.

---

## 10. 요약

- 이 구현 계획은 **“지금 당장 작은 팀에서 쓸 수 있는 pit”** 을 목표로 한다.
- Week 0~4만 잘 따라가도:
  - 파일 기반 SSOT,
  - 데이터 모델/플로우,
  - CLI + 간단한 헬스 체크,
  - 실제 프로젝트에 적용해보는 Dogfooding  
  까지 도달할 수 있다.
- 이후에는 필요와 여유에 따라:
  - API,
  - 에이전트 연동,
  - Web UI,
  - 정교한 정합도 엔진  
  을 단계적으로 추가해 나가면 된다.
