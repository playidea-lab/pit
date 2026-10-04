# 작업 보고 규칙 — 저장소의 CLAUDE.md / AGENTS.md 에 붙여 넣는다

> pithub MCP(`report_start`, `report_commit`)가 연결된 에이전트용. 도구가 보이지 않으면 이 규칙은 건너뛴다.

## 일을 시작할 때 — `report_start`

커밋으로 끝날 일을 시작하면, 코드를 고치기 **전에** 한 번 부른다.

- `task`: 일감 이름 한 줄 (예: "설문 응답 soft delete")
- `task_kind`: feature | fix | research | ops | docs | refactor
- `implements`: 이 일이 실행하는 결정·목표 id — 먼저 `search_my_decisions` 로 찾는다 (목표는 `goal` 태그)
- `position`: 전체 업무에서 이 일의 자리 한두 문장
- `expected_manual_hours`: AI 없이 숙련 개발자가 손으로 하면 몇 시간짜리인가
- `expected_agent_minutes`: 너(에이전트)와 하면 몇 분 걸릴 것 같은가

예상은 이후 고칠 수 없다. 솔직하게 적는다 — 나중에 실제와 비교된다.

## 커밋한 직후 — `report_commit`

커밋을 만들 때마다 부른다. `start_id` 에 `report_start` 가 준 id 를 넣는다.

- `atomic`: 이 커밋이 논리적 변경 하나인가. 둘 이상이 섞였으면 false 와 `atomic_note`
- `message_ok`: 커밋 메시지가 무엇을·왜 바꿨는지 말하는가. 부족하면 false 와 `message_note`
- `principles_kept` / `principles_missed`: 팀 원칙(`principle` 태그 결정) 중 지킨 것·못 지킨 것
- `intent`: 무엇을 지시받아 무엇을 했나 — 요약만. 프롬프트 원문을 옮기지 않는다

보고는 주장이다. 팀은 diff·활동 기록과 대조한다. 부풀리면 어긋남으로 드러난다.
