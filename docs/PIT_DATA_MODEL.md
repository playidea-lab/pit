# PIT 데이터 모델 정의 – `PIT_DATA_MODEL.md`

> 이 문서는 pit 시스템에서 사용하는 **핵심 데이터 구조(스키마)** 를 정의한다.  
> Project / Feature / Checklist / Decision / Log / Incident / Git 연동 정보까지 포함한다.  
> 모든 예시는 **YAML + Markdown** 조합을 기준으로 작성한다.

---

## 0. 설계 원칙 (Design Principles)

1. **사람이 직접 읽고 쓸 수 있어야 한다.**
   - 모든 데이터는 Git 레포 안의 `yaml` + `md` 파일로 저장된다.
   - PM/대표/개발자가 코드 없이도 열어서 이해할 수 있는 구조여야 한다.

2. **ID 중심 (Feature/Decision/Incident ID가 최소 키)**  
   - `F-0001`, `F-INC-0003`, `D-0001` 같이 **짧고 명확한 ID**를 공통 키로 사용한다.
   - Git 브랜치/PR/커밋/테스트 이름에도 동일한 ID를 넣는다.

3. **프로젝트마다 분리, 그래도 한 눈에 구조를 볼 수 있게.**
   - 각 프로젝트는 `projects/<project_id>/` 디렉터리 아래에 묶인다.
   - 공통 규칙: `project.yaml`, `features/`, `decisions/`, `logs/` 폴더 구조.

4. **정합도(Alignment)를 염두에 둔 구조.**
   - Feature에는 반드시:
     - 요구사항(Requirements)
     - 수용 기준(Acceptance Criteria)
     - 체크리스트(Tasks)
     를 표현할 수 있어야 한다.
   - 나중에 정합도 평가 로직이 이 필드들을 활용하게 된다.

5. **부분적 사용도 허용.**
   - 모든 필드를 다 채우지 않아도 동작해야 한다.
   - 필드마다 `필수/권장/선택` 구분을 둔다.

---

## 1. 디렉터리 구조 개요

기본 레이아웃(예시):

```text
playidea-pit/
  projects/
    pit/
      project.yaml
      features/
        F-0001-pit-core-mvp.yaml
        F-INC-0001-2025-12-12-demo-incident.yaml
      decisions/
        D-0001-why-align-judge-is-signal-not-judge.md
      logs/
        2025-12-12-session-001.md
    slam/
      project.yaml
      features/
      decisions/
      logs/
```

- 각 프로젝트 폴더는 동일한 패턴을 따른다.
- Feature/Decision/Log 파일명에는 **ID + 짧은 설명**을 붙인다.
  - 예: `F-0001-active-learning-v2.yaml`
  - 예: `D-0001-why-v2-over-v1.md`

---

## 2. 공통 메타 필드 (모든 엔티티에 공통적으로 쓸 수 있는 필드)

아래 필드들은 Project/Feature/Decision/Log 등 대부분의 엔티티에 공통으로 붙일 수 있는 필드다.

```yaml
id: F-0001              # 고유 식별자 (필수)
title: Active Learning v2 파이프라인   # 사람용 제목 (필수)
description: >          # 한 줄 이상 설명 (권장)
  이 Feature는 SLAM에서 InfoScore 기반 Active Learning 파이프라인을 설계/구현하기 위한 작업 단위다.

created_at: 2025-12-12T10:30:00+09:00   # ISO 8601 (권장)
updated_at: 2025-12-12T11:45:00+09:00   # (권장)

owner: changmin         # 책임자 (필수 아님, 팀에서 사용하는 닉/이메일 등)
assignees:              # 협업자 목록 (선택)
  - dev1
  - dev2

tags:                   # 자유 태그 (선택)
  - slam
  - active-learning
  - pit-demo
```

### Step-by-step 사용 가이드

1. **처음 엔티티를 생성할 때**
   - `id`, `title`은 반드시 채운다.
   - `description`은 가능한 한 자세히 쓰는 게 좋다.
2. **수정할 때마다**
   - `updated_at`을 갱신하거나, 나중에 에이전트/툴이 자동으로 갱신하도록 설계한다.
3. **owner / assignees**
   - 팀 구조가 분명해지면 채우고, 초기에는 생략 가능하다.

---

## 3. Project 모델

### 3.1 파일 위치

```text
projects/<project_id>/project.yaml
```

예: `projects/pit/project.yaml`

### 3.2 필드 스키마

```yaml
id: pit                          # 프로젝트 ID (폴더명과 동일, 필수)
name: pit – Product / Idea Tracker  # 정식 이름 (필수)
description: >                   # 프로젝트 설명 (권장)
  pit는 기획/아이디어/결정/체크리스트를 버전 관리하고
  git과 비교하여 정합도를 평가하는 관제 시스템이다.

status: active                   # active / paused / archived (필수)
owner: changmin                  # 대표 책임자 (권장)
team:
  - name: changmin
    role: founder
  - name: dev1
    role: backend

repos:                           # 이 프로젝트와 연결된 Git 레포 목록 (권장)
  - name: pit-core
    path: /Users/changmin/git/pit-core        # 로컬 경로 (선택)
    url: git@github.com:playidealab/pit-core.git  # 원격 URL (필수에 가까움)
  - name: pit-tui
    path: /Users/changmin/git/pit-tui
    url: git@github.com:playidealab/pit-tui.git

labels:                          # 프로젝트 수준 태그/라벨 (선택)
  domain:
    - tooling
    - pm
  tech_stack:
    - python
    - fastapi
    - tui
```

### 3.3 Step-by-step

1. 새 프로젝트를 만들면 `projects/<id>/` 폴더와 `project.yaml`을 만든다.
2. `id`, `name`, `status`는 반드시 채운다.
3. Git 레포를 연결하고 싶으면 `repos`에 추가한다.
4. 나중에 서비스가 늘어나면 `repos`를 계속 확장해도 된다.

---

## 4. Feature 모델

### 4.1 파일 위치

```text
projects/<project_id>/features/<feature_id>-<slug>.yaml
```

예:
- `projects/pit/features/F-0001-pit-core-mvp.yaml`
- `projects/slam/features/F-0001-active-learning-v2.yaml`

### 4.2 필수/권장/선택 필드

```yaml
id: F-0001                       # 필수
project_id: pit                  # 필수
title: pit core MVP              # 필수
description: >                   # 권장
  pit의 가장 기본적인 데이터 모델과 파일 구조를 정의하고,
  실제 팀에서 문서를 쌓을 수 있는 v0를 만든다.

status: planned                  # 필수: planned / in_progress / ready_for_merge / merged / released

# 일정 관련
created_at: 2025-12-12T10:30:00+09:00   # 권장
updated_at: 2025-12-12T11:45:00+09:00   # 권장
due_date: 2026-01-15T00:00:00+09:00     # 선택

# 책임자
owner: changmin                        # 권장
assignees:
  - dev1

# 우선순위 (선택)
priority: high                         # low / medium / high / critical

# 요구사항 및 수용 기준
context: >                             # 권장
  pit 프로젝트에서 가장 먼저 해야 하는 것은
  데이터 모델과 파일 구조를 정의하여,
  대표/PM이 실제로 사용할 수 있게 만드는 것이다.

requirements:                          # 권장
  - "Project / Feature / Decision / Log 데이터 모델을 정의한다."
  - "YAML + Markdown 파일 구조를 설계한다."
  - "샘플 파일을 최소 1개 이상 생성한다."

acceptance_criteria:                   # 권장
  - "새 프로젝트에 pit 데이터 모델을 적용할 수 있을 정도로 문서가 완성되어야 한다."
  - "팀원 1명 이상이 문서를 읽고 이해했다는 피드백을 남긴다."

# 체크리스트 (Tasks)
checklist:                             # 필수 (단, 초기에는 하나만 있어도 됨)
  - id: T1
    label: PROJECT_DEFINITION.md 작성
    type: doc                          # code / test / infra / doc / bug ...
    repo: pit-core                     # 선택 (doc만 있는 경우 비워도 됨)
    path_hint: docs/PROJECT_DEFINITION.md
    done: true

  - id: T2
    label: PIT_DATA_MODEL.md 작성
    type: doc
    repo: pit-core
    path_hint: docs/PIT_DATA_MODEL.md
    done: false
    due_date: 2025-12-13T23:59:59+09:00

# Git 연동 정보 (선택이지만 매우 권장)
git_links:
  - repo: pit-core
    branch: feature/F-0001-pit-core-mvp
    prs:
      - url: https://github.com/playidealab/pit-core/pull/12
        status: open        # open / merged / closed

# 관련 Decision / Log 참조 (선택)
decisions:
  - D-0001
logs:
  - 2025-12-12-session-001
```

### 4.3 Feature Step-by-step

1. **기획/대화가 어느 정도 정리되면**, 새로운 Feature를 만든다.
   - ID를 부여: `F-0001`, `F-0002` …
   - `title`, `description`, `context`를 채운다.
2. **요구사항/수용 기준을 최대한 글로 적는다.**
   - 나중의 정합도 평가와 테스트 설계의 근거가 된다.
3. **checklist에 작업을 쪼갠다.**
   - Task ID는 간단히 `T1`, `T2`, `T-VOC-001` 식으로.
4. **개발이 시작되면 git_links를 연결한다.**
   - Feature ID를 포함하는 브랜치/PR을 만든 뒤 그 정보를 여기에 기록.
5. 필요시 `decisions`, `logs`에 참고 ID를 추가한다.

---

## 5. Checklist(Task) 서브 모델

Checklist는 Feature 안에 포함되는 **서브 모델**이지만 중요도가 높아서 따로 정의한다.

### 5.1 필드 스키마

```yaml
checklist:
  - id: T1                             # 필수 (Feature 내에서 유니크)
    label: InfoScore 샘플 선택 로직 구현   # 필수
    type: code                         # 필수: code / test / infra / doc / bug / other
    source: internal                   # 선택: internal / voc / monitoring / qa ...
    severity: medium                   # 선택: low / medium / high / critical
    urgent: false                      # 선택: true / false

    repo: slam-core                    # 선택 (code/test/infra 등에는 권장)
    path_hint: src/slam/active_learning/selector.py    # 선택 (있으면 정합도 분석에 유리)

    created_at: 2025-12-12T10:30:00+09:00   # 권장
    updated_at: 2025-12-12T11:45:00+09:00   # 선택
    due_date: 2025-12-20T23:59:59+09:00     # 선택

    done: false                        # 필수
    done_at: null                      # 선택 (완료 시 채우기)
```

### 5.2 Incident/VOC용 Task 예시

```yaml
  - id: T-VOC-001
    label: "결제 실패 VOC – 특정 카드사에서 오류 발생"
    type: bug
    source: voc
    severity: critical
    urgent: true
    repo: payment-service
    path_hint: src/payment/gateway_adapter.py
    created_at: 2025-12-12T10:32:00+09:00
    due_date: 2025-12-12T14:00:00+09:00
    done: false
```

### 5.3 Step-by-step

1. 새로운 일을 정의할 때마다 **체크리스트에 Task를 하나씩 추가**한다.
2. 긴급/VOC/Incident는 `urgent: true`, `severity: high/critical`로 표시한다.
3. 개발/테스트/문서 작업이 완료되면 `done: true`로 바꾸고, 가능하면 `done_at`도 적는다.
4. 나중에 에이전트/툴이:
   - git 상태와 Task 정보를 결합해서  
     “이 Task는 끝난 것 같다/아직 아닌 것 같다”는 신호를 줄 수 있다.

---

## 6. Decision 모델

### 6.1 파일 위치

```text
projects/<project_id>/decisions/<decision_id>-<slug>.md
```

예: `projects/pit/decisions/D-0001-why-align-judge-is-signal-not-judge.md`

### 6.2 내용 템플릿 (Markdown)

```markdown
---
id: D-0001
project_id: pit
title: 정합도(Alignment)는 판사가 아니라 신호등이다
status: active              # active / superseded / archived
related_features:
  - F-0001
created_at: 2025-12-12T10:30:00+09:00
updated_at: 2025-12-12T11:00:00+09:00
owner: changmin
tags:
  - decision
  - alignment
---

## 1. 배경 (Context)

- pit는 기획–코드 정합도를 다루는 툴이다.
- LLM을 이용해 코드를 분석할 수 있지만, 완전한 참/거짓 판정은 위험하다.

## 2. 결정 (Decision)

- 정합도 평가는 **판결(judgement)** 이 아니라 **신호(signal)** 로 다룬다.
- PM/개발자가 최종 결정을 내리도록 하고,
- pit는 어떤 부분이 위험/부족해 보이는지만 알려준다.

## 3. 근거 (Rationale)

- LLM과 정적 분석만으로는 실제 비즈니스 요구사항을 완전히 이해하기 어렵다.
- 잘못된 자동 판결은 팀의 신뢰를 떨어뜨릴 수 있다.

## 4. 대안 (Alternatives)

- 대안 1: 모든 정합도를 자동으로 pass/fail 판정
- 대안 2: 현재 결정처럼, 신호에 그치고 최종 판단은 사람에게 맡김 (채택)

## 5. 후속 조치 / TODO (Consequences / TODO)

- 정합도 평가 API는 항상 근거 슬라이스를 함께 반환해야 한다.
- UI에서는 신호등/점수 형태로만 표현한다.

## 6. 재검토 조건 (Review)

- 팀 규모가 커지고, 테스트/정적 분석 커버리지가 크게 늘어날 경우
- 일부 영역에 대해선 자동 판결을 도입할 수 있다.
```

### 6.3 Step-by-step

1. “왜 이렇게 하기로 했는지”가 명확해지는 순간마다 Decision 문서를 하나 만든다.
2. `related_features`에 영향을 받는 Feature ID를 연결한다.
3. 나중에 Feature를 볼 때 Decision을 함께 참조하여, 의도를 빠르게 이해한다.

---

## 7. Log(Session/History) 모델

### 7.1 파일 위치

```text
projects/<project_id>/logs/<date>-session-<nnn>.md
```

예: `projects/pit/logs/2025-12-12-session-001.md`

### 7.2 내용 템플릿

```markdown
---
id: 2025-12-12-session-001
project_id: pit
related_features:
  - F-0001
  - F-0002
created_at: 2025-12-12T10:00:00+09:00
created_by: changmin
tags:
  - chatgpt
  - planning
---

## 1. 요약 (Summary)

- pit 프로젝트 전체 정의를 정리했다.
- 데이터 모델 초안 범위를 합의했다.

## 2. 주요 논의 내용 (Key Points)

- pit는 기획/결정/체크리스트를 버전 관리하는 SSoT 역할이다.
- 정합도 평가는 신호등 역할을 하며, 최종 판단은 사람에게 맡긴다.

## 3. 액션 아이템 (Action Items)

- [ ] PIT_DATA_MODEL.md 작성 (F-0001, T2)
- [ ] PIT_FLOW_AND_CHECKLIST_SPEC.md 초안 정리

## 4. 원본 링크/참고 (References)

- ChatGPT 대화 링크(있는 경우)
- Notion/문서 링크
```

### 7.3 Step-by-step

1. 의미 있는 회의/LLM 대화/논의가 끝나면 Log를 하나 남긴다.
2. 관련 Feature/Decision ID를 `related_features`/본문에 연결해둔다.
3. 나중에 “이때 무슨 얘기를 했더라?” 싶을 때 로그를 빠르게 찾을 수 있다.

---

## 8. Incident용 Feature 패턴 (선택이지만 강력 추천)

Incident는 **별도의 Feature ID 패턴**을 쓰거나, `type: incident` 필드를 붙여 관리할 수 있다.

### 8.1 예시

```yaml
id: F-INC-0003
project_id: payment
title: 2025-12-12 결제 장애 대응
type: incident                     # incident / feature / chore ...
status: in_progress

context: >
  2025-12-12 오전, 특정 카드사 결제가 연속 실패하는 장애가 발생했다.
  고객 VOC 및 모니터링 알람을 기반으로 긴급 대응이 필요하다.

checklist:
  - id: T-VOC-001
    label: "결제 실패 VOC – 특정 카드사에서 오류 발생"
    type: bug
    source: voc
    severity: critical
    urgent: true
    repo: payment-service
    path_hint: src/payment/gateway_adapter.py
    created_at: 2025-12-12T10:32:00+09:00
    due_date: 2025-12-12T14:00:00+09:00
    done: false

  - id: T-POSTMORTEM-001
    label: 포스트모템 문서 작성
    type: doc
    repo: payment-docs
    path_hint: docs/incidents/2025-12-12-payment-incident.md
    done: false
```

---

## 9. Git 연동 서브 모델 (간단 정의)

자세한 내용은 `PIT_GIT_INTEGRATION_SPEC.md`에서 다루지만,  
Feature 관점에서 필요한 최소 필드를 여기서 정의한다.

```yaml
git_links:
  - repo: pit-core
    branch: feature/F-0001-pit-core-mvp
    prs:
      - url: https://github.com/playidealab/pit-core/pull/12
        status: open        # open / merged / closed
    last_commit_at: 2025-12-12T11:40:00+09:00   # 선택
    ci_status: passed       # 선택: unknown / passed / failed
```

- 이 정보는 정합도/진행도 평가의 **기계적 근거**가 된다.
- 초기에 수동으로 채우더라도, 나중에는 CLI/에이전트가 자동 갱신해 줄 수 있다.

---

## 10. 마이그레이션 / 확장 고려사항 (Step-by-step 성장 전략)

1. **v0 – 수동 작성 단계**
   - Project / Feature / Decision / Log를 손으로 작성.
   - ChatGPT에게 “pit용 Feature yaml 만들어줘” 식으로 부탁해서 복붙.

2. **v0.5 – 파서/검증 도입**
   - 간단한 스크립트로 `projects/` 폴더를 읽어서
     - YAML 파싱
     - 필수 필드 누락 여부 체크
   - CLI로 `pit validate` 같은 명령 제공.

3. **v1 – API/TUI/에이전트 연동**
   - FastAPI로 이 데이터 모델을 서빙.
   - TUI/웹에서 Project/Feature/Task를 조회/수정.
   - LLM 에이전트가:
     - 새 Feature/Decision/Log 생성
     - 체크리스트 업데이트 제안
     - 정합도 평가를 수행.

---

이 문서(`PIT_DATA_MODEL.md`)는  
**“pit에서 다루는 모든 데이터의 원본 정의서”** 역할을 한다.  
이후 작성할 `PIT_FLOW_AND_CHECKLIST_SPEC.md`, `PIT_API_SPEC.md` 등은  
여기 정의된 모델을 기반으로 동작해야 한다.
