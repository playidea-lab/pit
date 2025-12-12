# PIT 사용 가이드

> 이 문서는 PM/기획자와 개발자 모두를 위한 pit 사용 설명서다.
> 역할별로 다른 부분은 명시적으로 구분하고, 공통 내용은 한 번만 설명한다.

---

## 1. pit 한 줄 요약

> **"pit는 기획/아이디어/결정/체크리스트를 Git처럼 버전 관리하고,
>  git의 실제 코드와 비교해서 '기획 대비 개발이 어디까지 왔는지'를 보여주는 PM용 관제판이다."**

- Notion / ChatGPT / Jira / 슬랙 등에 흩어져 있는 이야기들을
  **Project / Feature / Decision / Log**로 구조화해서 모아두고,
- 개발자들이 작업하는 Git 상태와 연결해서,
- **"기획이 어디까지 현실이 되었는지"** 를 파악하는 도구다.

---

## 2. 기본 개념 – 4가지 핵심 단위

pit를 쓸 때 기억해야 할 단위는 4개다:

| 단위 | 설명 | 예시 |
|------|------|------|
| **Project** | 하나의 제품/서비스/시스템 단위 | `pit`, `slam`, `pios` |
| **Feature** | 기획/개발/테스트/배포가 한 덩어리로 움직이는 작업 단위 | `F-0001 – pit core MVP` |
| **Checklist (Task)** | Feature를 이루는 구체적인 할 일 목록 | `T1: 데이터 모델 문서 작성` |
| **Decision / Log** | "왜 이렇게 했는지" 기록 / 회의·세션 기록 | `D-0001`, `2025-12-12-session-001` |

> **핵심:**
> "Project 안에 여러 Feature가 있고, Feature 안에 체크리스트가 있다.
>  배경과 이유는 Decision/Log에 있다."

---

## 3. 첫 사용: Project 등록

### 3.1 프로젝트 폴더/파일 만들기

`playidea-pit` 레포 안에 다음 구조를 만든다:

```
projects/
  pit/
    project.yaml
    features/
    decisions/
    logs/
```

### 3.2 project.yaml 작성

```yaml
id: pit
name: pit – Product / Idea Tracker
description: >
  pit는 기획/아이디어/결정/체크리스트를 버전 관리하고
  git과 비교하여 정합도를 평가하는 관제 시스템이다.

status: active
owner: changmin
repos:
  - name: pit-core
    url: git@github.com:playidealab/pit-core.git
```

이 정도면 "pit 프로젝트"가 존재하게 된다.
이제부터 이 프로젝트와 관련된 기획/결정/이력은 모두 `projects/pit/` 아래에 쌓는다.

---

## 4. Feature 기반 작업

### 4.1 PM: Feature 정의 및 관리

#### 언제 Feature를 만드는가?

- 새 프로젝트를 시작할 때
- 새 기능을 기획할 때
- ChatGPT/팀 회의에서 아이디어가 정리되었을 때

#### Step-by-step

1. **LLM과 대화 후 정리 요청**
   > "이 내용을 SLAM용 pit Feature로 정리해줘. ID는 F-0001로."

2. **생성된 Feature YAML 저장**
   - `projects/slam/features/F-0001-active-learning-v2.yaml`

3. **Feature YAML 예시**
   ```yaml
   id: F-0001
   project_id: slam
   title: Active Learning v2 파이프라인
   status: planned

   context: >
     SLAM의 샘플 선택 로직을 InfoScore 기반으로 개선하여
     라벨링 효율을 높이고자 한다.

   requirements:
     - InfoScore 기반 샘플 선택 로직 설계/구현
     - 기존 파이프라인과 호환되는 API 유지

   acceptance_criteria:
     - 데모 환경에서 v1 대비 라벨 효율 개선이 확인될 것

   checklist:
     - id: T1
       label: InfoScore 설계 문서 작성
       type: doc
       done: false
     - id: T2
       label: 샘플 선택 로직 구현
       type: code
       repo: slam-core
       path_hint: src/slam/active_learning/selector.py
       done: false
   ```

---

### 4.2 DEV: Feature 단위 개발

#### 기본 패턴

1. PM/대표로부터 담당 Feature ID(F-0001) 전달받음
2. pit 레포에서 해당 Feature 확인:
   - `projects/pit/features/F-0001-pit-core-mvp.yaml`
3. 이 Feature를 기준으로 작업

#### 브랜치 전략

브랜치 이름에 **Feature ID를 포함**한다:

```
feature/F-0001-pit-core-mvp
bugfix/F-INC-0003-payment-incident
chore/F-0007-update-docs
```

#### PR/커밋 컨벤션

- **PR 제목**: `[F-0001] pit core MVP – 데이터 모델 + 파일 스토어`
- **PR 본문**:
  ```
  [x] T1 – 프로젝트 데이터 모델 구현
  [x] T2 – Feature 파서/저장 로직 구현
  [ ] T3 – Decision 로딩 로직 구현 (다음 PR에서)
  ```
- **커밋 메시지**: `feat(F-0001): add project data model`

---

## 5. 체크리스트(Task) 활용

### 5.1 PM: Task 정의 및 추적

#### 좋은 Task 작성법

- "이건 끝났다고 딱 말할 수 있나?"를 기준으로 쪼갠다
- **결과물이 명확한 문장**으로 작성

**좋은 예:**
- "PIT_DATA_MODEL.md 초안 작성"
- "InfoScore 샘플 선택 로직에 대한 유닛 테스트 작성"

**안 좋은 예:**
- "기능 구현"
- "테스트 정리"
- "피드백 반영"

#### Task 필드

```yaml
checklist:
  - id: T1
    label: Feature 모델 정의
    type: code           # code / test / doc / infra / bug / other
    repo: pit-core
    path_hint: pit/models/feature.py
    required: true       # 이게 끝나야 Feature를 완료 처리 가능
    due_date: 2025-12-20
    done: false
```

---

### 5.2 DEV: Task 완료 및 보고

#### 개발자가 실제로 하는 일

1. **작업 시작 전**: 담당 Feature의 checklist 읽기, 오늘 손댈 Task 선정
2. **작업 중**: 커밋/PR에 관련 Task 언급
3. **작업 후**: `done: true`로 체크 (또는 PM에게 완료 보고)

---

## 6. Incident/VOC 대응

### 6.1 언제 Incident Feature를 만드는가?

- 고객 VOC/모니터링 알람으로 장애 인지
- 사용자/매출/신뢰에 영향을 주는 사건

### 6.2 Incident Feature 예시

```yaml
id: F-INC-0003
project_id: payment
title: 2025-12-12 카드사 X 결제 장애
type: incident
status: in_progress

context: >
  2025-12-12 오전 10:20~11:05 동안 카드사 X 결제가 연속 실패했음.

checklist:
  - id: T-VOC-001
    label: 카드사 X 오류 로그 분석 및 원인 파악
    type: bug
    source: voc
    severity: critical
    urgent: true
    repo: payment-service
    done: false

  - id: T-FIX-001
    label: 임시 패치 적용 및 재발 방지 코드 수정
    type: code
    repo: payment-service
    done: false

  - id: T-POSTMORTEM-001
    label: 포스트모텀 문서 작성
    type: doc
    done: false
```

### 6.3 역할별 행동

| 역할 | 행동 |
|------|------|
| **PM** | Incident Feature 생성 (F-INC-xxxx), 긴급 Task 정의 |
| **DEV** | `bugfix/F-INC-xxxx` 브랜치 생성, urgent Task 처리 |
| **공통** | 해결 후 Task 완료 처리, 포스트모템 작성 |

---

## 7. 헬스/정합도 확인

### 7.1 프로젝트 단위 헬스 체크

```bash
pit health project pit
```

**예상 출력:**

```
[PROJECT: pit] Health Overview
------------------------------------------
[GREEN]
  - F-0001 pit core MVP
  - F-0002 데이터 모델 개선

[YELLOW]
  - F-0003 TUI prototype
    - 필수 체크리스트 5개 중 3개 완료
    - due_date 2일 지남

[RED]
  - F-INC-0001 2025-12-10 배포 장애
    - urgent Task 미해결
    - 최근 3일간 관련 커밋 없음
```

### 7.2 헬스 상태별 대응

| 상태 | 의미 | 대응 |
|------|------|------|
| **Green** | 정상 진행 | 지켜보기, 필요시 새 Feature/Task 분리 |
| **Yellow** | 지연/주의 | 원인 파악, 일정/범위 재조정 |
| **Red** | 위험/긴급 | 최우선 처리, 다른 Feature 일시 중단 |

---

## 8. 일상 루틴

### 8.1 PM 루틴

#### 하루 루틴

| 시점 | 행동 |
|------|------|
| **아침** | 오늘 집중할 Feature 1~3개 선정, 체크리스트 훑기 |
| **업무 중** | 새 아이디어 → 메모/Log, 중요 결정 → Decision |
| **퇴근 전** | 완료된 Task 체크, Feature status 업데이트 |

#### 주간 루틴

| 시점 | 행동 |
|------|------|
| **주간 시작** | 이번 주 집중 Feature 3~5개 선정, 팀 공유 |
| **중간 점검** | Yellow/Red Feature 확인, 지원 필요 사항 조정 |
| **주간 회고** | Incident 요약, Decision 문서 정리 확인 |

---

### 8.2 DEV 루틴

#### 하루 루틴

| 시점 | 행동 |
|------|------|
| **시작** | 담당 Feature checklist 확인, 오늘 Task 선정 |
| **개발** | 커밋/PR에 Feature ID 포함, Task 완료 시 마크 |
| **퇴근 전** | 완료 Task 보고, 막힌 부분 공유 |

#### 커뮤니케이션 패턴

**좋은 예:**
- "F-0001은 브랜치 따놨고, T1/T2까지 끝났습니다."
- "F-INC-0003의 T-FIX-001 핫픽스 PR 올렸습니다."

**안 좋은 예:**
- "그때 말했던 그거 어느 정도 했어요."
- "지난주 이슈는 거의 다 해결된 듯합니다."

---

## 9. 온보딩 패턴

### 9.1 새 팀원 온보딩 순서

1. **pit 레포 클론**
   - `playidea-pit` (프로젝트/Feature/Decision/Log 저장소)

2. **Project 문서 읽기**
   - `projects/<project_id>/project.yaml`
   - 프로젝트 목표/구조 파악

3. **핵심 Feature 살펴보기**
   - 최근/진행 중인 Feature 몇 개 확인
   - `context`, `requirements`, `acceptance_criteria` 읽기

4. **중요한 Decision 읽기**
   - "왜 이런 아키텍처를 선택했는지"
   - "왜 이 툴/모델을 쓰기로 했는지"

5. **코드 레포 작업 시작**
   - `.pit.yml` 확인
   - 브랜치/PR 네이밍 규칙 익히기

### 9.2 기대 효과

- "노션 여기저기 뒤지면서 설명" 시간 감소
- "말로만 기억나던 의사결정 반복 설명" 시간 감소
- 새 팀원이 스스로 맥락 파악 가능

---

## 10. 정리

> **pit는 "문서 더 쓰게 하는 도구"가 아니라,**
> **"이미 LLM과 대화로 쓰고 있는 문서를 덜 귀찮게 정리·추적·연결해주는 도구"다.**

- PM: Feature/Checklist를 정의하고, 헬스 상태를 모니터링
- DEV: Feature ID를 기준으로 브랜치/PR/커밋을 만들고, Task를 완료
- 공통: Incident는 `F-INC-xxxx`로, 결정은 Decision으로, 회의는 Log로
