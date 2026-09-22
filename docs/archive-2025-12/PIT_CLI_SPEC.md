# PIT CLI 명세 – `PIT_CLI_SPEC.md`

> 이 문서는 pit의 **명령줄 인터페이스(CLI)** 에 대한 스펙을 정의한다.  
> 사용자는 `pit` 명령을 통해 Project / Feature / Decision / Log / Health 등을  
> 조회·생성·수정할 수 있으며,  
> 개발자/PM의 일상 워크플로우에 자연스럽게 녹아드는 것을 목표로 한다.

---

## 0. 설계 목표

1. **개발자/PM 모두에게 직관적인 명령어 구조**
   - `git`, `poetry`, `kubectl` 등의 패턴과 비슷한 서브커맨드 구조
   - 예: `pit projects list`, `pit feature show F-0001`

2. **파일 기반 pit v0에 맞춘 범위**
   - 초기 버전에서는 **로컬 파일 시스템 + git** 에만 의존
   - 서버/API 없이도 사용할 수 있어야 한다.

3. **스크립트/툴에서 호출하기 좋은 인터페이스**
   - `--json` 옵션 등 기계가 읽기 쉬운 출력 제공
   - 나중에 에이전트/IDE 플러그인에서 재사용 가능

4. **안전한 수정 동작**
   - 직접 파일을 바로 덮어쓰기보다는
   - 가급적 “템플릿 생성 / patch 출력” 중심으로 시작
   - 자동 수정 시에는 backup 또는 diff 출력 우선

---

## 1. 기본 구조

### 1.1 실행 명령

- 기본 실행 명령: `pit`
- 설치 형태:
  - `pyproject.toml`의 `console_scripts` 로 `pit = pit.cli.main:app` 바인딩
  - Typer 또는 Click 기반 구현 가정

### 1.2 전역 옵션 (Global Options)

모든 서브커맨드에서 공통으로 쓸 수 있는 옵션:

- `-C, --chdir PATH`
  - 명령 실행 전에 디렉터리를 PATH로 변경
  - 여러 프로젝트가 섞여 있는 환경에서 유용
- `--config PATH`
  - pit 전역 설정 파일 경로 (필요 시)
- `--json`
  - 사람 친화적 출력 대신 JSON 포맷으로 출력
- `-v, --verbose`
  - 디버그/자세한 로그 출력

---

## 2. 프로젝트 관련 명령어

### 2.1 `pit projects list`

**설명**

- pit 레포 안에 존재하는 모든 Project를 나열한다.

**사용 예**

```bash
pit projects list
pit projects list --json
```

**옵션**

- `--status [active|archived|all]` (옵션, 기본 `active`)

**출력 예 (텍스트)**

```text
ID     NAME                     STATUS   REPOS
-----------------------------------------------------------
pit    pit – Product Tracker    active   1
slam   SLAM Labeling System     active   2
pios   PIOS Orchestration       active   1
```

**출력 예 (JSON, 개략)**

```json
[
  {"id": "pit", "name": "pit – Product Tracker", "status": "active", "repos": 1},
  {"id": "slam", "name": "SLAM Labeling System", "status": "active", "repos": 2}
]
```

---

### 2.2 `pit project show <project_id>`

**설명**

- 특정 Project의 상세 정보를 출력한다 (`project.yaml` 내용 기반).

**사용 예**

```bash
pit project show pit
pit project show slam --json
```

**옵션**

- 없음 (추후 필요에 따라 확장)

**출력 내용**

- id, name, description, status, owner, repos 등  
  `PIT_DATA_MODEL` 에 정의된 Project 필드

---

## 3. Feature 관련 명령어

### 3.1 `pit features list`

**설명**

- 특정 Project 안의 Feature 목록을 출력한다.

**사용 예**

```bash
pit features list --project pit
pit features list --project slam --status in_progress
pit features list --project slam --type incident
pit features list --project pit --json
```

**옵션**

- `--project, -p <project_id>` (필수)
- `--status [planned|in_progress|ready_for_merge|merged|released|all]`
- `--type [normal|incident|all]`
- `--owner <owner_id>`
- `--limit <N>` (기본 50)

**출력 예 (텍스트)**

```text
[PROJECT: pit] Features
ID       TITLE                      STATUS          TYPE
---------------------------------------------------------------
F-0001   pit core MVP               in_progress     normal
F-0002   데이터 모델 개선            planned         normal
F-INC-1  2025-12-10 배포 장애        merged          incident
```

---

### 3.2 `pit feature show <feature_id>`

**설명**

- Feature의 상세 내용을 보여준다.

**사용 예**

```bash
pit feature show F-0001 --project pit
pit feature show F-INC-0003 --project payment --json
```

**옵션**

- `--project, -p <project_id>` (필수)
- `--checklist` (체크리스트만 따로 보여주고 싶을 때)
- `--no-checklist` (체크리스트는 생략하고 메타 정보만 볼 때)

**출력 내용**

- Feature 메타 정보(id, title, status, owner, priority, type 등)
- context / requirements / acceptance_criteria
- checklist(Task) 목록
- (추후) git_links, health 정보 요약

---

### 3.3 `pit feature create`

**설명**

- 새 Feature YAML을 생성하는 명령.
- 기본적으로 **템플릿 파일을 생성**하고, 사용자가 직접 수정하도록 한다.

**사용 예**

```bash
pit feature create --project pit
pit feature create --project slam --id F-0005 --title "Active Learning v2"
```

**옵션**

- `--project, -p <project_id>` (필수)
- `--id <feature_id>` (옵션, 없으면 자동 생성)
- `--title <title>` (옵션)
- `--type [normal|incident]` (옵션, 기본 `normal`)
- `--incident` (= `--type incident` 숏컷)
- `--open-in-editor` (생성 후 에디터로 바로 열기, 환경변수 `$EDITOR` 사용)

**동작**

1. `projects/<project_id>/features/` 내에 YAML 템플릿 생성
2. 파일명 규칙 예:
   - `F-0005-active-learning-v2.yaml`
3. 생성 시 기본 구조:

   ```yaml
   id: F-0005
   project_id: slam
   title: Active Learning v2
   status: planned
   type: normal
   context: >
     TODO: 여기에 기능 배경/맥락을 적습니다.
   requirements: []
   acceptance_criteria: []
   checklist: []
   ```

---

### 3.4 `pit feature edit <feature_id>`

**설명**

- Feature YAML을 편집기에서 연다.

**사용 예**

```bash
pit feature edit F-0001 --project pit
```

**옵션**

- `--project, -p <project_id>` (필수)
- `--editor <cmd>` (옵션, 기본 `$EDITOR`)

**동작**

- 해당 Feature 파일을 에디터로 열기만 한다.  
  편집 내용은 사용자가 저장.

---

### 3.5 `pit feature status <feature_id>`

**설명**

- Feature의 현재 status(플로우 상 상태)를 조회/변경한다.

**사용 예**

```bash
pit feature status F-0001 --project pit
pit feature status F-0001 --project pit --set in_progress
```

**옵션**

- `--project, -p <project_id>` (필수)
- `--set [planned|in_progress|ready_for_merge|merged|released|cancelled|archived]` (옵션)

**출력 예**

```text
[Feature] F-0001 – pit core MVP
Current status: planned
```

**변경 시**

- `--set` 옵션이 있을 경우:
  - 변경 전/후 상태 출력
  - 안전을 위해 `--yes` 또는 대화형 확인을 둘 수도 있음

---

## 4. 체크리스트(Task) 관련 명령어

### 4.1 `pit checklist list`

**설명**

- 특정 Feature의 체크리스트(Task)를 보여준다.

**사용 예**

```bash
pit checklist list F-0001 --project pit
pit checklist list F-0001 --project pit --only-open
```

**옵션**

- `--project, -p <project_id>` (필수)
- `--only-open` (done == false 인 것만)
- `--only-required` (required == true 인 것만)
- `--json`

**출력 예**

```text
[Feature: F-0001] Checklist
ID    DONE  REQ  TYPE   LABEL
--------------------------------------------------------------
T1    [x]   [*]  doc    PROJECT_DEFINITION.md 작성
T2    [ ]   [*]  doc    PIT_DATA_MODEL.md 작성
T3    [ ]        doc    PIT_FLOW_AND_CHECKLIST_SPEC.md 초안
```

---

### 4.2 `pit checklist set-done <feature_id> <task_id>`

**설명**

- 특정 Task의 `done` 상태를 토글하거나 명시적으로 설정.

**사용 예**

```bash
pit checklist set-done F-0001 T2 --project pit --true
pit checklist set-done F-0001 T3 --project pit --false
```

**옵션**

- `--project, -p <project_id>` (필수)
- `--true` / `--false` (둘 다 없으면 토글로 동작)

**동작**

- Feature YAML에서 해당 Task의 `done` 값 수정
- 변경 후 결과를 간단히 출력

---

### 4.3 `pit checklist add <feature_id>`

**설명**

- 체크리스트 항목을 하나 추가한다.

**사용 예**

```bash
pit checklist add F-0001 --project pit   --id T4   --label "PIT_IMPLEMENTATION_PLAN.md 작성"   --type doc   --required
```

**옵션**

- `--project, -p <project_id>` (필수)
- `--id <task_id>` (옵션, 없으면 자동 생성)
- `--label <text>` (필수)
- `--type [code|test|doc|infra|bug|other]` (옵션)
- `--repo <repo_name>` (옵션)
- `--path-hint <path>` (옵션)
- `--required` / `--not-required` (옵션)
- `--due-date <YYYY-MM-DD>` (옵션)

---

## 5. Git 연동 관련 명령어 (초기 버전)

### 5.1 `pit feature checkout <feature_id>`

**설명**

- 현재 코드 레포(.pit.yml 기준)에서 Feature용 브랜치를 생성.

**사용 예**

```bash
cd /Users/changmin/git/pit-core
pit feature checkout F-0001
```

**동작**

1. 현재 디렉터리에서 `.pit.yml` 읽기
2. `project_id`, `pit_repo_path` 확인
3. Feature YAML 로드
4. 브랜치 이름 제안:
   - 예: `feature/F-0001-pit-core-mvp`
5. `git checkout -b` 실행 (또는 이미 있으면 `git checkout`)

**옵션**

- `--name <branch_name>` (수동 지정)
- `--base <base_branch>` (기본 `main`)

---

### 5.2 `pit feature link-git <feature_id>`

**설명**

- 현재 브랜치/리모트/PR URL 등을 Feature의 `git_links`에 기록.

**사용 예**

```bash
pit feature link-git F-0001 --project pit
```

**옵션**

- `--project, -p <project_id>` (필수)
- `--repo <repo_name>` (옵션, 없으면 `.pit.yml` 기반 추론)
- `--branch <branch_name>` (옵션, 없으면 현재 브랜치 사용)
- `--pr-url <url>` (옵션)

**동작**

- Feature YAML의 `git_links` 배열에 항목 추가 또는 갱신:

  ```yaml
  git_links:
    - repo: pit-core
      branch: feature/F-0001-pit-core-mvp
      pr_url: https://github.com/playidealab/pit-core/pull/12
  ```

---

### 5.3 `pit feature status <feature_id> --with-git`

**설명**

- Feature 상태와 git 상태를 함께 보여준다.

**사용 예**

```bash
pit feature status F-0001 --project pit --with-git
```

**추가 출력 예**

```text
Git:
  repo: pit-core
  branch: feature/F-0001-pit-core-mvp
  last_commit: 2025-12-12 10:23
  pr: open (CI passed)
```

---

## 6. 헬스/정합도 관련 명령어

### 6.1 `pit health project <project_id>`

**설명**

- Project 안의 Feature들을 헬스 상태별(Green/Yellow/Red)로 보여준다.

**사용 예**

```bash
pit health project pit
pit health project slam --json
```

**출력 예**

```text
[PROJECT: pit] Health Overview
------------------------------------------
[GREEN]
  - F-0001 pit core MVP

[YELLOW]
  - F-0002 데이터 모델 개선
    - 필수 체크리스트 5개 중 3개 완료
    - due_date 2일 지남

[RED]
  - F-INC-0001 2025-12-10 배포 장애
    - urgent Task 미해결
    - 최근 3일간 관련 커밋 없음
```

---

### 6.2 `pit health feature <feature_id>`

**설명**

- 특정 Feature의 헬스/정합도 평가 결과를 보여준다.

**사용 예**

```bash
pit health feature F-0001 --project pit
```

**출력 예**

```text
[Feature: F-0001] Health: YELLOW
Reasons:
  - 필수 체크리스트 3/5 완료
  - due_date 1일 지남
Suggestions:
  - 이번 주 안에 T4, T5를 우선적으로 처리하세요.
```

---

## 7. Decision / Log 관련 명령어 (v0 기본)

### 7.1 `pit decisions list`

**설명**

- Project 내 Decision 문서 목록을 보여준다.

**사용 예**

```bash
pit decisions list --project pit
```

**옵션**

- `--project, -p <project_id>` (필수)
- `--limit <N>` (옵션)
- `--json`

---

### 7.2 `pit decision create`

**설명**

- 템플릿 기반 Decision MD 파일 생성.

**사용 예**

```bash
pit decision create --project pit   --title "왜 pit를 별도 레포로 분리했는가"
```

**동작**

- `projects/<project_id>/decisions/D-YYYYMMDD-xxxx.md` 생성
- 기본 템플릿 채워 넣기 (제목, 배경, 선택지, 결론 등)

---

### 7.3 `pit logs create`

**설명**

- 회의/세션 끝나고 Log 템플릿 생성.

**사용 예**

```bash
pit logs create --project pit --title "2025-12-12 pit 설계 세션"
```

**동작**

- `projects/<project_id>/logs/2025-12-12-session-xxx.md` 생성

---

## 8. 안전장치 및 UX 고려 사항

1. **파일 수정 전 백업 옵션**
   - `--backup` 또는 전역 설정으로  
     수정 전 원본을 `<filename>.bak` 으로 복사 가능하게.

2. **대화형 모드**
   - 일부 명령(`feature create`, `checklist add`, `status --set` 등)은  
     `--interactive` 옵션으로 질의응답 형태 지원.

3. **에러 메시지**
   - “파일 없음”, “project_id/feature_id 잘못됨” 같은 경우  
     최대한 친절한 메시지 제공:
     - “projects/pit/features/F-0001-*.yaml 중  
        F-0001이 포함된 파일을 찾지 못했습니다.” 등.

4. **탭 완성 (추후)**
   - `shell completion` 지원:
     - `pit feature show F-<TAB>` 하면 ID 자동완성 등

---

## 9. 구현 우선순위 단계

### 9.1 1단계 (v0 CLI)

- 필수:
  - `projects list`, `project show`
  - `features list`, `feature show`
  - `feature create`, `feature edit`
  - `checklist list`
- 선택:
  - `checklist set-done`
  - `decisions/logs create`

### 9.2 2단계

- Git 연동:
  - `feature checkout`
  - `feature link-git`
- 기본 헬스 체크:
  - `health project`
  - `health feature`

### 9.3 3단계

- 대화형/자동화 편의:
  - interactive 모드
- 에이전트/IDE 연계:
  - `--json` 기반의 안정적인 출력 스펙 확립
  - MCP/LLM 에이전트에 쉽게 붙일 수 있는 래퍼 스크립트

---

## 10. 요약

- `pit` CLI는  
  - Project/Feature/Checklist/Decision/Log를  
    **로컬 파일 기반으로 다루는 표준 인터페이스** 이며,
  - 나중에 API/에이전트/Web UI가 붙더라도  
    이 CLI 스펙이 “행동의 기준” 역할을 한다.
- 이 문서(`PIT_CLI_SPEC.md`)를 기준으로  
  `pit/cli/` 구현을 진행하면,  
  PM/개발자/에이전트 모두가 **같은 언어로 pit를 조작**하게 된다.
