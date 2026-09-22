# 결정 원장의 생애주기와 규모 — 설계

> 2026-09-22. 결정은 [D-0007](../.pit/decisions/D-0007-knowledge-lifecycle.md).
> "지금 당장은 아니지만 설계는 해 둔다" — 나중에 스키마를 뒤엎지 않기 위한 문서다.
> 각 단계에는 **착수 조건**이 있다. 조건 전에 만드는 것은 YAGNI다.

## 1. 원칙

1. **기록은 자동, 확인은 쓰는 순간, 품질은 표본.** 사람이 전건을 보는 설계는 첫 실사용에서 깨졌다.
2. **규모의 답은 인덱스가 아니라 압축이다.** 1만 건의 사건이 아니라 50개의 원칙을 검색한다.
3. **지우지 않고 내려보낸다.** 대체·보관·순위 하락은 있어도 자동 삭제는 없다. 삭제는 사용자만.
4. **AI에게 주는 양은 항상 작다.** 검색이 100건을 찾아도 상위 5~10건의 요약만 준다. 세션의 컨텍스트를 잡아먹으면 커넥터가 꺼진다.
5. **모든 조회는 소유자로 먼저 좁힌다.** 남의 데이터가 커져도 내 검색은 느려지지 않는다.

## 2. 규모 가늠

| | 사람 1명 | 1,000명 |
|---|---|---|
| 기록 | 하루 10~30건, 연 1만 건 안팎 | 연 1,000만 행 |
| 조회 | 세션당 5~20회, 하루 ~100회 | 하루 ~10만 회 |
| 행 크기 | 1~2 KB | 연 ~20 GB |

Postgres 하나로 충분한 규모다. 병목은 행 수가 아니라 **검색의 질**과 **AI에게 주는 컨텍스트 크기**다.

## 3. 지식의 단위

| 단위 | 정의 | 저장 |
|---|---|---|
| **결정** (사건) | 특정 시점, 특정 제안에 내린 판정 | `decisions` 행 |
| **원칙** (규칙) | 결정 여러 개가 굳어진 것 | `decisions` 행 + `tags ⊇ {principle}` + `consulted`에 근거 결정 |
| 예외 | 원칙과 반대로 간 뒤 "맞음"이 눌린 결정 | 결정 행 + `supersedes` 대신 `exception_of` |

원칙은 사건보다 영향이 커서 **정리함에서 확인을 요구**한다. 확인되지 않은 원칙은 검색에서 사건과 같은 무게로만 다룬다.

## 4. 생애주기 신호와 스키마

지금 있는 열 외에 다음을 추가한다(모두 nullable/default, 마이그레이션은 추가만).

```sql
alter table decisions
  add column cited_count   int  not null default 0,   -- 검색 결과로 AI에게 전달되어 인용된 횟수
  add column last_cited_at timestamptz,
  add column repeat_count  int  not null default 1,   -- 근접 중복이 접힌 횟수
  add column exception_of  text,                      -- 이 결정이 예외를 낸 원칙의 id
  add column embedding     vector(768);               -- 4단계에서 (pgvector)

alter table decisions drop constraint decisions_status_check;
alter table decisions add constraint decisions_status_check
  check (status in ('draft', 'confirmed', 'discarded', 'archived'));

create table citations (            -- 어떤 검색이 무엇을 돌려주었고 무엇이 쓰였나 (A1의 실측)
  id bigint generated always as identity primary key,
  owner_github_id bigint not null,
  query text not null,
  returned_ids text[] not null,
  used_ids text[] not null default '{}',   -- 모델이 답에서 인용했다고 보고한 것
  created_at timestamptz not null default now()
);
```

| 신호 | 어디서 오나 | 무엇을 바꾸나 |
|---|---|---|
| 쓰임 (`cited_count`) | `search_my_decisions` 결과 중 모델이 `used`로 보고 (도구 응답에 `cite_back` 필드) | 검색 순위 ↑, 보관 후보에서 제외 |
| 확인 (`status=confirmed`, `review`) | 열람·공개·표본 | 순위 ↑, 공유 가능 |
| 대체 (`supersedes`) | 기록 시점에 모델이 관련 결정을 검색해 표시 (아래 6) | 옛 결정은 검색에서 빠지고 "이전엔 X" 한 줄로 |
| 예외 (`exception_of`) | 원칙과 반대인 결정이 확인될 때 | 원칙에 "예외 N건", 3건 이상이면 개정 제안 |
| 나이 | `decided_at` | 순위 ↓ |
| 반복 (`repeat_count`) | 같은 프로젝트·같은 제안이 며칠 안에 다시 기록될 때 접힘 | 순위 ↑ (반복은 정보다) |
| 표본 오류율 | 주간 표본 5건의 "맞음/고침" 비율 | 미확인 기록 전체의 신뢰도 표시 |

## 5. 검색 파이프라인

```
질의
 → 소유자 + status ∉ {discarded, archived} + 대체되지 않음         (인덱스: owner, status)
 → 후보 추출: 1단계 trigram(부분 일치) / 4단계 hybrid(trigram ∪ vector top-k)
 → 순위:  원칙 > 사건
          확인됨 > 미확인
          log(1 + cited_count)
          최근성 감쇠 (반감기 180일)
          repeat_count
 → 상위 N(기본 8) 요약만 반환: id · 제안 한 줄 · 판정 · 날짜 · verified · principle 여부
   대체된 결정은 "이전엔 X (PD-…)" 한 줄로 최신 결정에 붙여서
 → citations 에 (query, returned_ids) 기록; 모델이 cite_back 하면 used_ids 갱신
```

전체 본문은 `get_decision` 으로 따로 가져간다. 결과 크기 상한: 약 1,500자.

## 6. 대체 감지 (기록 시점)

서버 지침에 추가: "record_decision 전에 같은 주제의 과거 결정이 있으면 `search_my_decisions`로 확인하고, 새 결정이 그것을 뒤집으면 `supersedes: [id]` 를 넣어라." 서버는 `supersedes`의 id가 호출자 소유인지 검증한다. 사람은 정리함에서 대체 관계를 본다(대체는 "봐 둘 만한 것"에 포함).

## 7. 압축: 결정 → 원칙

- **트리거**: 같은 프로젝트 또는 같은 태그의 미압축 결정이 5건을 넘을 때, 또는 주 1회.
- **누가**: 사용자의 세션 모델. 별도 도구 `propose_principle` 없이 `search_my_decisions` → `record_decision(tags=["principle"], consulted=[...근거 결정...])` 로 한다. 비용 0.
- **확인**: 원칙은 정리함에 온다. "맞음"이 눌리기 전에는 사건과 같은 무게.
- **개정**: 예외 3건 이상이면 정리함에 "이 원칙을 고칠까요?"와 예외 목록. 개정된 원칙은 옛 원칙을 `supersedes`.
- **내보내기**: 확인된 원칙 목록을 `MEMORY.md` 형식으로 내보내 `~/.claude` 메모를 대체한다. 방향이 뒤집힌다 — 결정은 pithub에 쌓이고 메모는 거기서 생성된다.

## 8. 보관

- 조건: 1년 이상 미확인·미인용·대체 아님. 자동으로 `archived`로 옮기지 않고 **정리함에 "보관할까요? N건"** 으로 제안한다.
- 보관된 것은 검색되지 않고, 내보내기에는 포함되며, 되돌릴 수 있다.
- 사용자가 직접 보관/복원/삭제. 삭제만 되돌릴 수 없다.

## 9. 쓰기 경로의 방어

- 하네스 지침이 첫 필터(일상 승인 제외).
- 중복 키(같은 날 같은 제안+인용) — 있음.
- 근접 중복 접기: 같은 소유자·같은 프로젝트·정규화한 제안이 같음·7일 이내 → `repeat_count += 1`, 새 행 없음.
- 사용자당 시간당 300회 — 있음.
- 결정 1건 텍스트 상한 4,000자 — 있음.

## 10. 단계와 착수 조건

| 단계 | 내용 | 착수 조건 |
|---|---|---|
| **1** | `pg_trgm` GIN 인덱스, 결과 요약·상한, `citations` 테이블 + `cite_back`, 대체 감지 지침, 근접 중복 접기 | 지금 (백필 데이터 분석과 함께) |
| **2** | 순위 규칙(원칙·확인·인용·최근성), 정리함에 대체·원칙 항목 | 1단계 뒤, 기록 300건 |
| **3** | 원칙 압축 제안, 예외 추적, `MEMORY.md` 내보내기 | 기록 500건 또는 파일럿 판정 통과 |
| **4** | `pgvector` 임베딩 + 하이브리드 검색 | 한 사용자 1,000건 또는 trigram 검색이 놓치는 사례가 표본에서 반복 확인될 때 |
| **5** | 보관 제안 | 첫 사용자 1년 |

## 11. 측정

- 검색당 반환 건수·바이트 (컨텍스트 부담)
- `used_ids / returned_ids` 비율 = 검색 정밀도이자 A1
- 표본 오류율 (주간)
- 대체·예외·원칙 건수의 추이 — 원장이 압축되고 있는가
- 검색 지연 p95 (목표 200ms)

## 12. 하지 않는 것

- 자동 삭제. 자동 보관. AI가 사람 확인 없이 원칙을 확정하는 것.
- 세션 원문 저장. 벡터 검색을 위해 원문을 서버로 보내는 것 (임베딩은 결정 요약에서만).
- 팀 범위 결정의 임베딩을 제3자 API로 보내는 것 — 팀이 동의한 벤더만.
