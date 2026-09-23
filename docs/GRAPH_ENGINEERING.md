# 판단 그래프 — 구축 현황과 개발 계획

> 제품 정의: [PRODUCT.md](PRODUCT.md) · 결정: [D-0009](../.pit/decisions/D-0009-judgment-graph-twin.md), [D-0010](../.pit/decisions/D-0010-company-product.md)
> 2026-09-24 작성. 그래프는 원래 10/27 판정 뒤였으나, 도그푸딩이 "그래프가 판단을 옮기는가"를 시험하므로 G0~G5를 도그푸딩 중에 만든다. G6(트윈)만 오프라인 시험(G7) 통과 뒤.

## 목표

claude.ai · Claude Code · Codex · 로컬 `pit` 어디서든 사용자의 판단이 **노드와 엣지**로 허브에 쌓이고,
그 그래프를 토대로 동료의 AI와 트윈이 **근거와 함께** 답한다.

## 현황 (2026-09-24)

| 층 | 필요한 것 | 상태 |
|---|---|---|
| 수집 | 세 클라이언트 MCP 기록 (팀 주소 포함) | ✅ 세 곳 모두 실측 |
| | 로컬 `pit` push | ✅ 결정만 |
| 그래프 | 결정 노드 | ✅ `decisions` |
| | 주제·프로젝트·산출물 노드 | ❌ 프로젝트는 문자열 힌트뿐 |
| | `supersedes` | ✅ 본인 결정끼리 |
| | `cites` (누가 → 누구의 판단을 가져갔나) | ⚠️ 횟수만 → **G0** |
| | `conflicts_with` · `depends_on` | ❌ |
| | 이름 맞추기 | ❌ |
| 공유·권한 | private/team, 3일 자동 공유, 회사 소유, 떠난 구성원 | ✅ RLS 테스트 |
| 읽기 | 본문 검색(trigram)·범위·순위 | ✅ |
| | 주제에서 연결 따라가기 | ❌ |
| 답변 | 세션 AI의 인용(L1) | ✅ |
| | `ask_twin`(L2)·판정기·기권→본인 질문 | ❌ |
| 관리 | 정리함·주간 표본·사용량 | ✅ |
| | 원칙 승격 제안·감쇠 | ❌ |
| 계측 | 검색 결과 중 읽힌 비율 | ✅ 근사 |
| | 건너간 판단 | ❌ → **G0** |

기록·권한 기반 약 70%, 그래프 약 15%, 그래프로 답하기 약 20%.

## 데이터 모델

모든 엣지의 한쪽 끝은 결정이다 — "판단에 매달린 그래프"(D-0009)를 스키마로 강제한다.

```
transfers        (decision_id, owner_github_id, reader_github_id, team_id, via, client, created_at)   G0 — cites
nodes            (id, team_id, kind[topic|project|artifact], name, norm_name, aliases[], merged_into, created_by)   G1
decision_nodes   (decision_id → node_id, relation='about')                                            G1
decision_links   (from_decision → to_decision, relation[supersedes|conflicts_with|depends_on],
                  status[proposed|confirmed], created_by)                                             G1
```

- 노드·엣지의 가시성은 **부모 결정을 따른다**(3일 규칙·회사 소유 포함).
- `decisions.supersedes` 는 `decision_links` 로 옮기고 호환을 위해 한동안 남긴다.

## 단계

| 단계 | 산출물 | 완료 기준 | 예상 |
|---|---|---|---|
| **G0 계측** ✅ 9c92ed3 | `transfers`. 남의 결정을 `get_decision` 하는 순간 기록. `/t/<slug>`에 "이번 주 건너간 판단" | 남의 결정 읽기 → 한 행, 본인 것 읽기 → 없음 (테스트) | 1일 |
| **G1 스키마** ✅ c901d24 | `nodes`·`decision_nodes`·`decision_links` + RLS, `supersedes` 이관 | 팀원은 팀에 보인 결정의 노드·엣지만 본다 (RLS) | 1~2일 |
| **G2 쓰기** ✅ MCP (push 규약은 남음) | `record_decision.about`·`links`, 이름 정규화 → 기존 노드에 붙이거나 생성, 검색 결과에 주제 이름(`topics`), push 같은 규약 | 두 세션이 같은 주제를 기록하면 노드 하나 | 2일 |
| **G3 이름 맞추기** | trigram 후보 → 정리함 "같은 주제입니까?" → `merged_into` | 병합 뒤 두 이름 모두 같은 결정 | 2일 |
| **G4 그래프 읽기** | 주제 1-hop 확장 검색, `/topic/<id>`, `get_decision` 에 연결 결정 | claude.ai에서 주제로 물으면 개발자 판단이 근거로 | 2~3일 |
| **G5 충돌** | 같은 주제 반대 판정 → `conflicts_with` 후보 → 정리함 확인 | 기획·개발의 상반된 결정이 정리함에 | 2일 |
| **G7 오프라인 시험** | 282건 시간 순 분할, 기록 있는 판정 vs 없는 판정 | 구조화된 리포트 | 2일 |
| **G6 트윈 L2** | `ask_twin(login, proposal)`: 근거 수집 → 판정기(기본 세션 LLM, 선택 JEV) → 낮으면 본인 정리함에 질문 → 답이 결정·라벨 · "내 트윈" 화면 | G7 통과 | 3~4일 |

합계 약 15~18일. **G0~G2를 도그푸딩 첫 주에** — 처음부터 노드·엣지가 쌓여야 한다.

## 트윈이 답하는 흐름 (G6)

```
ask_twin("dev-kim", "평가를 무작위 분할로")
 ① 묻는 사람 권한으로 dev-kim 의 같은 주제·산출물 결정 + 1-hop 연결 (RLS)
 ② 판정기: 기본은 근거만 → 세션 LLM이 판단 / 선택 시 JEV "거부할까?" 확신도
 ③ 높음 → 판정 + 근거 + 날짜 (떠난 구성원 표시)   낮음 → 기권 + 본인(떠났으면 후임) 정리함에 질문
 ④ transfers · consult_log 기록 → 주인이 "내 트윈"에서 본다
```

## 지키는 것

- 원문은 서버로 가지 않는다. 노드는 판단에 매달린 것만.
- 도구를 늘리지 않는다 — 기존 도구에 필드, 새 도구는 `ask_twin` 하나.
- 단계마다 마이그레이션 → RLS 테스트 → 서버 테스트 → 배포.
