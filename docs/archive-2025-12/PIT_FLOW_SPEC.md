# PIT 플로우 & 체크리스트 명세 – `PIT_FLOW_AND_CHECKLIST_SPEC.md`

> 이 문서는 pit에서 사용하는 **Feature 상태 흐름(pit-flow)** 과  
> 각 Feature에 속한 **체크리스트(Task)** 의 동작 방식을 정의한다.  
> PM/기획자/개발자가 “무엇이 언제까지, 어디까지 진행되었는지”를  
> 한 눈에 이해할 수 있도록 하는 것이 목적이다.

---

## 0. 문서 목적

1. **pit-flow = 기획자용 git-flow 추상화**를 명확히 정의한다.
2. Feature가 어떤 상태를 거쳐 `planned → released` 로 흘러가는지 서술한다.
3. 체크리스트(Task)가 이 흐름 안에서 어떤 역할을 하는지 설명한다.
4. VOC/Incident(긴급 이슈)가 pit-flow와 체크리스트에 어떻게 끼어드는지 정의한다.
5. git 상태와 연계하여 **정합도/진행도 신호(헬스 체크)** 를 어떻게 만들 수 있는지 방향을 제시한다.

---

## 1. pit-flow 개요

### 1.1 개념

- **pit-flow**는 Feature(작업 단위)가 어떤 라이프사이클을 거치는지를 나타내는 상태 머신이다.
- 기존의 git-flow(브랜치/머지/태그)를 **기획자/PM이 이해할 수 있는 수준으로 추상화**한 것이다.
- 기획자/PM은 pit-flow만 이해하면 되고,  
  브랜치 전략/머지 전략/커밋 그래프 같은 기술 디테일은 git 뒤로 숨긴다.

### 1.2 핵심 상태(State)

기본 상태는 다음 5단계이다.

1. `planned`
2. `in_progress`
3. `ready_for_merge`
4. `merged`
5. `released`

필요하다면 `cancelled`, `archived` 같은 상태를 추가로 둘 수 있지만,  
v0~v1에서는 위 5개를 기본으로 사용한다.

---

## 2. Feature 상태 정의 (pit-flow 상태 머신)

### 2.1 상태 정의 요약

#### 2.1.1 `planned`

- **의미**: 기획이 정의되었고, 해야 할 일(체크리스트)이 나눠졌지만 아직 개발이 시작되지 않은 상태.
- **특징**
  - Feature 문서가 존재한다.
  - `requirements`, `acceptance_criteria`, `checklist`가 대략 채워져 있다.
  - 관련 브랜치/PR은 아직 없거나, 있어도 실제 작업은 시작되지 않았다.

#### 2.1.2 `in_progress`

- **의미**: 개발이 실제로 진행 중인 상태.
- **특징**
  - Feature ID를 포함하는 브랜치가 생성되었다.  
    (예: `feature/F-0001-pit-core-mvp`)
  - 체크리스트 항목들에 커밋/PR이 연결되기 시작한다.
  - 일부 Task는 `done: true`가 될 수 있다.

#### 2.1.3 `ready_for_merge`

- **의미**: 구현 및 테스트가 완료되어, main/release 브랜치로 머지될 준비가 된 상태.
- **특징**
  - 해당 Feature 브랜치에 대한 PR이 열려 있고, CI가 통과했다.
  - **반드시 필요한 체크리스트 항목(필수 Task)이 모두 완료**되었다.
  - PM/리뷰어가 검토만 하면 되는 단계.

#### 2.1.4 `merged`

- **의미**: Feature 브랜치가 main/release 브랜치에 머지된 상태.
- **특징**
  - PR 상태가 `merged` 이다.
  - 코드 기준으로는 기능이 main에 포함되었다.
  - 아직 실제 사용자 환경(프로덕션)에는 반영되지 않았을 수도 있다.

#### 2.1.5 `released`

- **의미**: 기능이 실제 배포되어 사용자/운영 환경에 반영된 상태.
- **특징**
  - 배포 태그/릴리스 노트에 해당 Feature가 포함되었다.
  - PM/기획자 관점에서 “이제 사용자에게 보이는 상태”로 본다.

---

### 2.2 상태 전이 (Transition) 정의

각 상태 사이의 이동 조건을 정의한다.

#### 2.2.1 `planned → in_progress`

**조건 예시**

- Feature ID를 포함하는 브랜치가 생성되었을 때  
  (예: `feature/F-0001-pit-core-mvp`).
- 또는, 체크리스트 중 `type: code/test/infra` Task에 첫 커밋/PR이 연결되었을 때.

**Step-by-step**

1. PM/기획자가 Feature 문서를 작성하고 `status: planned` 로 둔다.
2. 개발자가 해당 Feature를 맡아 브랜치를 만든다.
3. pit는 git 상태를 스캔하여:
   - “F-0001과 연결된 브랜치가 생겼습니다. `in_progress` 로 바꿀까요?”  
     라고 제안할 수 있다.
4. 사람이 수락하면 실제 상태를 `in_progress`로 변경한다.

---

#### 2.2.2 `in_progress → ready_for_merge`

**조건 예시**

- 필수 체크리스트(Task) 중 `done: false` 인 것이 없다.
- Feature와 연결된 PR이 `open` 상태이며, CI가 `passed` 인 상태.

**Step-by-step**

1. 개발자가 체크리스트 Task들을 완료하고, PR을 연다.
2. CI가 통과한다.
3. pit는:
   - “F-0001의 필수 Task가 모두 완료되었고, PR이 열려 있으며 CI가 통과했습니다.  
     `ready_for_merge`로 상태를 올릴까요?”  
     라고 제안할 수 있다.
4. 리뷰어/PM이 수락하면 상태를 `ready_for_merge`로 변경한다.

---

#### 2.2.3 `ready_for_merge → merged`

**조건 예시**

- 연결된 PR의 상태가 `merged` 로 바뀐다.

**Step-by-step**

1. 리뷰어가 PR을 리뷰하고 머지한다.
2. git 상태가 `merged`로 변경된다.
3. pit는:
   - “F-0001의 PR이 머지되었습니다. `merged` 상태로 변경할까요?”  
     라고 제안한다.
4. 수락 시 `status: merged` 로 변경한다.

---

#### 2.2.4 `merged → released`

**조건 예시**

- 해당 커밋이 포함된 릴리스 태그(또는 배포 로그)가 생성된다.
- 배포 시스템에서 “프로덕션 반영 완료” 이벤트를 받는다.

**Step-by-step**

1. Release/배포 담당자가 릴리스를 수행한다.
2. 배포 태그/로그에 Feature ID 또는 관련 PR이 포함된다.
3. pit는:
   - “F-0001이 release v1.2.0에 포함되었습니다. `released` 상태로 변경할까요?”  
     제안.
4. PM이 수락하면 `status: released` 로 변경된다.

---

### 2.3 예외 상태 (선택)

- `cancelled`: 더 이상 진행하지 않기로 결정한 Feature
- `archived`: 오래된 Feature, 유지보수 필요 없음

이 상태들은 v0에서는 선택사항이며, 필요시에만 사용하는 것을 권장한다.

---

## 3. 체크리스트(Task) 플로우

### 3.1 체크리스트 역할

- Feature를 구성하는 **구체적인 일감** 단위.
- PM/기획자/개발자가 “무슨 일을 언제까지 해야 하는지”를 공유하는 최소 단위.
- 정합도 계산 시:
  - “필요한 일들 중 얼마가 끝났는지”를 판단하는 핵심 정보.

### 3.2 Task 상태

Task는 최소 다음의 필드를 가진다.

- `done: false/true`
- (선택) `cancelled: true`
- (선택) `done_at`, `updated_at`

**권장 상태 모델**

1. `open`  
   - `done: false`, `cancelled: false`
2. `done`  
   - `done: true`
3. `cancelled`  
   - `cancelled: true` (필요한 경우)

실제 필드로는 `done`/`cancelled` 두 개만 사용하고,  
UI/툴에서 이를 조합하여 상태를 표현한다.

---

### 3.3 Task 생성 규칙 (정상 작업용)

**Step-by-step**

1. 새로운 Feature를 만들고, 해야 할 작업을 머릿속으로 떠올린다.
2. 그 작업을 **최소 단위의 “체크 가능한 일”**로 쪼갠다.
   - 예: “문서 설계” →  
     - `T1: PROJECT_DEFINITION.md 작성`
     - `T2: PIT_DATA_MODEL.md 작성`
     - `T3: PIT_FLOW_AND_CHECKLIST_SPEC.md 작성`
3. 각 Task에 대해:
   - `id`, `label`, `type`(code/test/doc/infra/bug/other), `repo`, `path_hint`, `due_date` 등을 채운다.
4. 나중에 git/에이전트가 이 Task와 관련 있는 커밋/PR을 자동으로 연결할 수 있다.

---

### 3.4 Task와 Feature 상태의 관계

- 원칙적으로:
  - **필수 Task가 모두 `done`이어야** Feature를 `ready_for_merge`/`merged`/`released`로 올릴 수 있다.
- 필수 여부를 표기하고 싶다면 Task에 `required: true/false` 필드를 둘 수 있다.

예시:

```yaml
checklist:
  - id: T1
    label: PROJECT_DEFINITION.md 작성
    type: doc
    required: true
    done: true

  - id: T2
    label: PIT_DATA_MODEL.md 작성
    type: doc
    required: true
    done: false

  - id: T3
    label: 파이프라인 시각화 초안
    type: doc
    required: false
    done: false
```

- 이 경우:
  - `T1`은 완료, `T2`는 미완 → `ready_for_merge`로 가기에는 아직 이르다.
  - `T3`는 나중으로 밀어도 되지만, `T2`는 반드시 해야 한다.

---

## 4. VOC / Incident 플로우

### 4.1 개념

- **VOC/Incident** = 고객 불만, 모니터링 알람, 긴급 장애.
- pit에서는 이를 **별도 Incident Feature** 또는 기존 Feature의 **긴급 Task**로 다룬다.

### 4.2 패턴 A – Incident Feature로 관리

- 새로운 Feature ID 패턴: `F-INC-0001`, `F-INC-0002`, …
- 상태 플로우는 일반 Feature와 동일: `planned → in_progress → ready_for_merge → merged → released`

**예시 Step-by-step**

1. 결제 장애 발생:
   - PM이 `F-INC-0003 – 2025-12-12 결제 장애 대응` Feature를 생성.
2. 체크리스트에:
   - `T-VOC-001`(버그 수정),  
   - `T-POSTMORTEM-001`(포스트모템 작성) 등 추가.
3. 개발자는 urgent Task만 필터링해 핫픽스 브랜치에서 작업.
4. 머지/배포 후:
   - pit-flow를 따라 `merged` → `released` 상태로 올린다.

### 4.3 패턴 B – 기존 Feature에 긴급 Task 추가

- 장애가 특정 Feature/모듈과 직접적으로 연결될 때,
- 기존 Feature의 체크리스트에 `urgent: true` Task를 추가.

**예시**

```yaml
  - id: T-VOC-002
    label: Active Learning v2 – 샘플 선택 로직에서 예외 발생
    type: bug
    source: monitoring
    severity: high
    urgent: true
    repo: slam-core
    path_hint: src/slam/active_learning/selector.py
    done: false
```

**Step-by-step**

1. 모듈 수준의 bug이자 대규모 장애는 아니라고 판단.
2. 기존 Feature에 긴급 Task를 추가하고, 우선순위를 상향 조정.
3. 개발자가 이 Task를 먼저 처리하고 `done: true`로 변경.

---

## 5. pit-flow + 체크리스트 + git 상태 = 정합도/헬스 체크

### 5.1 개념 요약

정합도/헬스 체크는 대략 다음 요소를 함께 본다.

1. Feature 상태 (`planned`/`in_progress`/…)
2. 체크리스트 진행도 (필수 Task 완료 비율)
3. git 상태 (브랜치/PR/커밋/CI/릴리스)
4. Incident/VOC의 유무 (`urgent` Task)

### 5.2 헬스 체크 신호등 예시

- **Green (건강함)**
  - 필수 체크리스트 90% 이상 완료
  - 최근 PR/커밋이 활발
  - 장애/VOC 없음
- **Yellow (주의)**
  - 필수 체크리스트 완료율이 낮음
  - due_date가 지났거나 임박했는데 활동이 적음
  - `urgent` Task가 열려 있지만 대응이 느림
- **Red (위험)**
  - critical Incident가 열려 있고 커밋/PR이 거의 없음
  - Acceptance Criteria에 맞는 테스트/코드가 부족해 보임
  - 오랫동안 상태가 `in_progress`에 머물러 있음

> 이 문서는 정합도 계산의 **정성적 기준**만 정의하고,  
> 실제 점수/알고리즘은 추후 `ALIGNMENT_ENGINE_SPEC` 같은 별도 문서에서 다룬다.

---

## 6. 역할별 Step-by-step 사용 시나리오

### 6.1 PM/기획자 – 새 Feature 기획부터 릴리스까지

1. **기획/대화 단계**
   - ChatGPT/회의 등을 통해 기능 요구사항을 정리한다.
   - “이제 pit Feature로 정리하자”고 선언.

2. **Feature 생성**
   - `F-0001` ID를 부여하고, Feature yaml 생성.
   - `status: planned`로 시작.
   - `requirements`, `acceptance_criteria`, `checklist`를 가능한 한 구체적으로 작성.

3. **진행 상황 모니터링**
   - 개발자가 브랜치/PR을 만들면 pit가 `in_progress` 제안.
   - 체크리스트의 done 비율을 보며 진행 상태를 감으로 파악.

4. **머지/릴리스**
   - PR 머지 → `merged` 제안 수락.
   - 릴리스/배포 완료 후 → `released` 제안 수락.

5. **회고/정리**
   - 필요 시 Feature를 `archived` 상태로 넘기고,
   - 관련 Decision/Log를 연결해두어 나중에 참고.

---

### 6.2 개발자 – 할당된 Feature를 구현할 때

1. PM으로부터 “이번 주는 F-0001, F-0002를 맡아줘” 전달 받음.
2. 코드 레포(`.pit.yml` 설정됨)에서:
   - `pit feature checkout F-0001` 명령을 사용(예정)
   - 또는 Feature ID를 포함한 브랜치를 수동으로 생성.
3. 체크리스트의 Task를 보며 개발/테스트/문서 작업 진행.
4. Task 완료 시:
   - 직접 `done: true`로 수정하거나,
   - 나중에 에이전트가 자동 제안하는 것을 수락.
5. PR 생성/머지 후:
   - pit 상태가 `ready_for_merge`, `merged`로 자연스레 흐르도록 돕는다.

---

### 6.3 Incident 대응 – 긴급 장애 발생 시

1. 모니터링/VOC에서 장애 인지.
2. PM이:
   - Incident Feature 생성(`F-INC-00xx`) 또는
   - 기존 Feature에 `urgent` Task 추가.
3. 개발자는 urgent Task만 필터링해서 핫픽스 진행.
4. 머지/배포 후:
   - 장애 해결 확인,
   - Incident Feature의 Task를 `done: true`로 처리.
5. 필요 시 포스트모템/Decision을 남겨  
   이후에 같은 문제가 발생하지 않도록 한다.

---

## 7. 정리

- **pit-flow**는 Feature의 라이프사이클을 기획자 관점에서 단순하게 표현한 상태 머신이다.
- **체크리스트(Task)** 는 실제 일을 쪼갠 단위로, 정합도/진행도 평가의 핵심 데이터이다.
- VOC/Incident는 별도 Feature(`F-INC-xxxx`)나 `urgent` Task로 표현하여  
  일반 작업과 같은 흐름 위에서 관리한다.
- git 상태와 결합하면:
  - “기획 대비 구현이 어디까지 왔는지”
  - “지금 어디가 위험/지연/장애 상태인지”  
  를 신호등처럼 볼 수 있다.

이 문서는 향후 구현될 CLI/TUI/API/에이전트들이  
**어떻게 상태를 변경하고, 어떤 기준으로 제안/알림을 줄지**를 결정하는 기준이 된다.
