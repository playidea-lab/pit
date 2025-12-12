# PIT 에이전트 설계 – `PIT_AGENT_DESIGN.md`

> 이 문서는 pit 시스템에서 활용할 **LLM 에이전트 구조와 역할, 오케스트레이션 흐름**을 정의한다.  
> 특히, PM/기획자가 LLM과 대화하면서 **Project / Feature / Decision / Log** 를 생성·수정하고,  
> git 상태 및 헬스 체크를 받아볼 수 있도록 하는 에이전트 계층을 설계한다.

---

## 0. 목적 및 범위

### 0.1 목적

1. pit에서 사용할 **핵심 에이전트 타입**을 정의한다.
2. 각 에이전트가 어떤 입력을 받고, 어떤 출력을 내는지를 명확히 한다.
3. 에이전트 간 협력(오케스트레이션) 플로우를 텍스트 기반 시퀀스로 정리한다.
4. v0~v1 단계에서 **현실적으로 구현 가능한 최소 구성을 우선**으로 한다.

### 0.2 범위

- 포함:
  - pit-orchestrator (메인 PM/기획자 인터페이스)
  - spec-analyzer (Feature/Decision/Log를 읽고 해석)
  - git-analyzer (git 상태 조회 & 정리)
  - health-judge (헬스 체크/정합도 신호 계산)
  - writer 계열 에이전트 (Feature/Decision/Log 생성/수정 도우미)
- 제외:
  - 외부 Vault / 시크릿 관리 에이전트
  - 대규모 멀티테넌트 SaaS용 에이전트 체계

---

## 1. 설계 원칙 (Design Principles)

1. **Single Source of Truth는 파일/DB, 에이전트는 “뷰 + 도우미”**
   - pit의 진실은 `projects/` 폴더의 YAML/MD 파일 또는 pit-core DB에 있다.
   - 에이전트는 이를 **읽고, 요약하고, 편집 제안**을 해주는 도우미일 뿐이다.
   - 에이전트가 완전히 새 세계를 만들지 않도록 한다.

2. **역할을 작게, 그러나 조합은 유연하게**
   - 한 에이전트가 너무 많은 역할을 가지지 않도록 분리한다.
   - orchestrator가 “누구에게 어떤 일을 시킬지”를 결정하고,  
     실제 작업은 전문 에이전트에게 넘긴다.

3. **사람이 항상 마지막 승인자**
   - 특히 정합도/헬스 체크/문서 수정 제안은
   - 항상 사람이 확인·수락하는 구조를 유지한다.

4. **pit-cli / pit-api / 에이전트는 교차 사용 가능**
   - 에이전트는 pit-cli/pit-api를 통해서만 pit 데이터를 조작한다.
   - 직접 파일을 마구 건드리지 않고, 항상 동일한 인터페이스를 사용한다.

---

## 2. 에이전트 계층 개요

### 2.1 전체 구조

높은 수준에서, 에이전트 구성은 다음과 같다:

- **1) pit-orchestrator 에이전트**
  - PM/기획자와 직접 대화하는 메인 창구.
  - 나머지 에이전트들을 호출/조합하는 “컨트롤 타워”.
- **2) 도메인별 전문 에이전트**
  - `spec-analyzer` : Feature/Decision/Log 읽고 요약, 연관성 분석.
  - `git-analyzer` : git 브랜치/PR/커밋/CI 상태 조회 및 정리.
  - `health-judge` : pit 데이터 + git 데이터를 기반으로 헬스/정합도 신호 계산.
  - `writer-*` : 특정 타입의 문서를 생성/수정하는 헬퍼 (Feature/Decision/Log 등).

### 2.2 개념적 레이어

1. **User Layer**
   - 사람(대표/PM/개발자)이 사용하는 채팅/CLI/TUI/Web UI.
2. **Agent Layer**
   - LLM 기반 pit-orchestrator 및 도메인 에이전트들.
3. **Pit Core Layer**
   - pit-core 라이브러리 (데이터 모델, 파일 파서, 헬스 체크 로직 등).
4. **Infra Layer**
   - Git, CI, 이슈 트래커 등 외부 시스템.

---

## 3. 핵심 에이전트 정의

### 3.1 `pit-orchestrator` 에이전트

**역할**

- PM/기획자/대표와의 대화 담당.
- 자연어 요청을 파악해, 아래와 같은 작업을 의도 분류하고 적절한 에이전트/도구를 호출:
  - “새 Feature 정의해줘”
  - “지금 pit 프로젝트 헬스 상태 보여줘”
  - “이 대화 내용을 Feature로 정리해줘”
  - “이번 주에 뭘 해야 하지?”

**입력 예시**

- 자유 자연어:
  - “SLAM Active Learning v2 기능을 하나 정의하고 싶어.”
  - “이번에 생긴 결제 장애를 Incident Feature로 만들어 줘.”
  - “pit 프로젝트의 전체 헬스 상태를 알려줘.”

**출력 예시**

- 사용자에게 보여줄 정리된 답변:
  - 새로 생성된 Feature/Decision/Log의 YAML/MD 블록
  - 헬스 상태 요약
  - 이번 주 TODO 리스트

**필요 도구/에이전트 호출**

- `pit-api` 또는 `pit-cli` 래퍼
- `spec-writer`, `decision-writer`, `log-writer`
- `git-analyzer`, `health-judge`

---

### 3.2 `spec-analyzer` 에이전트

**역할**

- Project / Feature / Decision / Log를 읽고,
  - 요약,
  - 관계 분석,
  - 누락된 부분 제안,
  - 중복/충돌 의심 지점 탐지.
- 예: “F-0001과 F-0002 요구사항이 어색하게 겹쳐 있다” 같은 의견.

**입력**

- 하나 또는 여러 개의 Feature/Decision/Log 원문 또는 요약.
- 예:
  - `Feature(F-0001), Feature(F-0002), Decision(D-0001)`

**출력**

- 요약 텍스트.
- 다음과 같은 분석 결과:
  - `missing_fields`, `inconsistent_requirements`, `maybe_duplicate_features` 등.

---

### 3.3 `git-analyzer` 에이전트

**역할**

- Git 레포 상태를 pit 관점에서 정리:
  - Feature ID별 브랜치/PR/커밋/CI 상태 조회.
  - 최근 활동/지연/이상 징후 파악.
- 핵심은 “pm-friendly 요약”이다.

**입력**

- `project_id`, 선택적으로 `feature_id` 목록.
- `.pit.yml` 및 pit-core에서 제공하는 repo 정보.

**출력**

- Feature별 git 상태 요약:
  - 현재 브랜치 이름
  - PR 상태 (open/merged/closed)
  - 최근 커밋 시간
  - CI 상태 (passed/failed/unknown)

---

### 3.4 `health-judge` 에이전트

**역할**

- pit 데이터(Feature/Checklist/Incident) + git 데이터로  
  **헬스/정합도 신호**를 계산한다.
- 강조: “판사(judge)”가 아니라 “신호등(signal)”이라는 원칙을 따른다.

**입력**

- Feature 객체 하나 또는 여러 개
- git-analyzer에서 넘어온 git 상태 요약
- (Optional) 과거 헬스 히스토리

**출력**

- 헬스 상태:
  - `status: green | yellow | red`
  - `reasons: [ ... ]` (스트링 리스트)
- 사람에게 보여줄 설명:
  - 왜 green/yellow/red로 판단했는지 간단히.

**예시 출력**

```yaml
feature_id: F-0001
status: yellow
reasons:
  - "필수 체크리스트 5개 중 2개만 완료되었습니다."
  - "due_date가 3일 지났습니다."
  - "최근 7일간 관련 커밋이 없습니다."
suggestions:
  - "이번 주에 T2, T3에 대한 작업 우선순위를 올리세요."
```

---

### 3.5 Writer 계열 에이전트

#### 3.5.1 `feature-writer`

- 역할: 자연어 설명/대화 로그를 받아 **Feature YAML** 초안을 만들거나 수정안 제안.
- 입력 예시:
  - “Active Learning v2를 위해 필요한 요구사항은 A, B, C고, 마감은 1월 15일이야.”
- 출력:
  - `F-0001` YAML 블록 (또는 patch 형식 제안).

#### 3.5.2 `decision-writer`

- 역할: “왜 이렇게 하기로 했는지”를 Decision MD 템플릿에 맞게 정리.
- 입력 예시:
  - 대화/회의 요약 + 주요 찬반 의견
- 출력:
  - Decision 문서 MD 블록.

#### 3.5.3 `log-writer`

- 역할: 세션/회의 종료 시 “오늘 논의 내용”을 Log 포맷으로 정리.
- 입력:
  - 대화/회의 전체 요약 또는 메시지 집합
- 출력:
  - Log MD 템플릿에 맞는 문서.

---

## 4. 에이전트 오케스트레이션 플로우

### 4.1 플로우 1 – “새 Feature 정의” 시나리오

**목표**: PM이 LLM과 대화해 아이디어를 정리하면, 그걸 pit Feature로 저장.

**Step-by-step**

1. PM:  
   > “SLAM Active Learning v2 기능을 정의하고 싶은데, 다음 요구사항이야...”  
   (자연어로 맥락 설명)

2. `pit-orchestrator`:
   - 사용자의 의도 = “새 Feature 생성”으로 판단.
   - 현재 대화 내용을 정리 → `feature-writer`에 전달.

3. `feature-writer`:
   - 입력된 설명을 기반으로:
     - `id` (임시 또는 빈 값)
     - `title`, `description`, `context`
     - `requirements`, `acceptance_criteria`
     - `checklist` 초안 (T1, T2, T3)
   - YAML 블록으로 생성해서 반환.

4. `pit-orchestrator`:
   - 생성된 YAML을 사용자에게 보여주고,
   - “이대로 F-0001로 저장할까요?” 같은 확인 질문.
   - 사용자가 OK하면, pit-api/cli를 호출해 파일로 저장.

5. 결과:
   - `projects/slam/features/F-0001-active-learning-v2.yaml` 생성.
   - (선택) `logs/2025-xx-xx-session-xxx.md`로 오늘 논의 로그 남김.

---

### 4.2 플로우 2 – “현재 프로젝트 헬스 체크” 시나리오

**목표**: 프로젝트 전체의 상태를 한 번에 보고 싶을 때.

**Step-by-step**

1. PM:  
   > “pit 프로젝트 헬스 상태 좀 보여줘.”

2. `pit-orchestrator`:
   - 의도 = “헬스 체크 요청”.
   - pit-api/cli를 사용해:
     - `projects/pit/` 아래 모든 Feature 로드.

3. `pit-orchestrator` → `git-analyzer`:
   - Feature 목록과 연결된 repos 정보 전달.
   - git-analyzer가:
     - 각 Feature ID별 브랜치/PR/커밋/CI 상태 수집.

4. `git-analyzer` → `health-judge`:
   - Feature + git 상태를 전달.

5. `health-judge`:
   - 헬스 상태/사유/제안 계산.

6. `pit-orchestrator`:
   - 결과를 PM 친화적인 텍스트/표 형태로 요약:
     - Green 리스트
     - Yellow 리스트 (주의 필요)
     - Red 리스트 (즉시 액션 필요)

---

### 4.3 플로우 3 – “Incident/VOC 처리” 시나리오

**목표**: 긴급 장애를 Feature/Task로 관리.

**Step-by-step**

1. PM:  
   > “오늘 결제 서비스에서 특정 카드사 결제 실패 VOC가 들어왔어. Incident Feature로 정리해줘.”

2. `pit-orchestrator`:
   - 의도 = “Incident Feature 생성”.
   - 설명/로그를 `feature-writer`에 넘길 때:
     - `type: incident`, `id` prefix = `F-INC-...` 힌트 포함.

3. `feature-writer`:
   - `F-INC-0003` 형태의 Feature YAML 초안 생성:
     - Incident context
     - VOC/모니터링 Task (urgent/critical)

4. `pit-orchestrator`:
   - 생성된 YAML 블록을 보여주고,
   - 수락 시 pit에 저장.

5. 이후:
   - 개발자가 `F-INC-0003` 기준으로 브랜치/PR 생성.
   - git-analyzer, health-judge가 이 Incident의 진행 상황을 추적.

---

### 4.4 플로우 4 – “문서 리팩토링/정리” 시나리오

**목표**: 시간이 지나면서 흩어진 Feature/Decision/Log를 정리.

**Step-by-step**

1. PM:  
   > “최근 3개월간 slam 프로젝트의 Feature/Decision을 정리해서,  
   >  중복되거나 정리 필요해 보이는 것들 알려줘.”

2. `pit-orchestrator`:
   - `spec-analyzer`에게 해당 프로젝트의 Feature/Decision/Log를 넘김.

3. `spec-analyzer`:
   - 내용 유사도/연관성/중복 가능성 등을 분석.
   - “병합 추천”, “명확하지 않은 Feature” 등을 리스트로 반환.

4. `pit-orchestrator`:
   - PM에게:
     - 어떤 Feature를 병합/정리할지 제안.
   - PM이 선택하면:
     - `feature-writer`/`decision-writer`와 협업해 새 문서/patch 생성.

---

## 5. 인터페이스 설계 (추상)

### 5.1 pit-core / pit-api / pit-cli 인터페이스

에이전트들은 직접 파일을 만지기보다 **다음 계층을 통해서만** pit 데이터에 접근하는 것을 원칙으로 한다.

- `pit-core` (Python 라이브러리)
  - 프로젝트/Feature/Decision/Log 로딩/저장 함수.
  - 헬스 체크/정합도 계산 함수.

- `pit-api` (선택)
  - HTTP 기반 API: `/projects`, `/features`, `/health` 등.

- `pit-cli`
  - 명령형 인터페이스:
    - `pit projects list`, `pit feature create`, `pit health project pit` …

에이전트 구현 언어/환경에 따라 적절한 인터페이스를 선택해 래핑한다.

---

### 5.2 에이전트 입출력 포맷 (예시)

#### 5.2.1 `feature-writer` 입력/출력

- 입력:
  - 자연어 설명
  - (선택) `project_id`, `feature_id` (수정 시)
- 출력:
  - YAML 블록 (신규 Feature)
  - 또는 YAML patch (기존 Feature 수정 제안)

#### 5.2.2 `health-judge` 입력/출력

- 입력:
  - `Feature` JSON
  - git 상태 요약 JSON
- 출력:
  - `health_report` JSON:
    - `status`, `reasons`, `suggestions`

---

## 6. 에이전트 단계적 도입 전략

### 6.1 v0 – 수동 + 단일 에이전트 단계

- 사실상 지금처럼:
  - ChatGPT 한 명(pit-orchestrator 비슷한 역할)이
  - 문서/Feature/Decision/Log를 직접 생성하는 시기.
- 이 단계에서:
  - `PIT_DATA_MODEL`, `PIT_FLOW`, `IMPLEMENTATION_PLAN`을  
    그대로 따라가며 수작업을 한다.
- 별도의 코드 레벨 에이전트 구현은 없어도 된다.

### 6.2 v0.5 – 스크립트/도구 + 부분 에이전트화

- Python 스크립트/CLI를 통해:
  - Feature/Decision/Log 생성 및 검증 자동화.
- LLM은:
  - 주로 `feature-writer`/`decision-writer` 정도의 역할을 수행.
- git-analyzer/health-judge는 규칙 기반 함수로 구현,  
  LLM은 결과를 설명/요약해주는 정도.

### 6.3 v1 – 명시적인 멀티 에이전트 구조

- 별도 오케스트레이션 레이어(예: langgraph, custom framework)를 두고:
  - pit-orchestrator
  - spec-analyzer
  - git-analyzer
  - health-judge
  - writer 계열
  를 명시적으로 분리.
- 에이전트 간 메시지 형식(예: JSON schema) 확립.
- ChatGPT/Claude/기타 LLM을 백엔드로 교체 가능하게 추상화.

---

## 7. 리스크 및 완화 전략

1. **에이전트 난립/복잡성 증가**
   - v0~v0.5는 최대 3~4개의 역할로 제한.
   - 새 역할이 필요하면 먼저 문서에 정의하고, 그 다음 구현.

2. **LLM 오판/환각**
   - Feature/Decision/Log 수정은 항상 “제안(patch)” 형식.
   - 사람이 마지막으로 diff를 보고 수락/거부.

3. **성능/비용**
   - 헬스 체크/정합도 계산은 최대한 규칙/코드 기반으로.
   - LLM은 요약/설명/초안 생성에 집중.

4. **보안/시크릿**
   - pit 자체는 API 키 저장소가 아님.
   - 민감한 설정은 `.env`/Vault 등 다른 계층에서 관리.

---

## 8. 요약

- `pit-orchestrator`는 사람과 대화하며,
  - `spec-analyzer`, `git-analyzer`, `health-judge`, `writer-*` 에이전트를 조합해  
  pit 데이터를 생성/해석/요약하는 컨트롤 타워다.
- 모든 에이전트는 **pit-core/cli/api를 통해서만** pit 데이터에 접근한다.
- 정합도/헬스 판단은 “신호등”에 가깝게 다루고,  
  최종 결정/승인은 항상 사람에게 있다.
- v0에서는 사실상 “문서화 + 수작업”이지만,  
  이 설계를 기반으로 v0.5~v1에서 서서히 코드/에이전트를 붙여갈 수 있다.

이 문서(`PIT_AGENT_DESIGN.md`)는  
향후 MCP 연동, IDE 플러그인, Web UI, 고급 오케스트레이션을 구현할 때  
**에이전트들의 역할과 경계를 잊지 않기 위한 기준선** 역할을 한다.
