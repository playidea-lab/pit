# git-watcher

사내 GitLab과 GitHub 커밋을 사람별로 정리해 메일로 보낸다.

- **일일 브리핑** — 평일 20:00. 커밋한 날짜별로 사람마다 수작업 환산 작업량(하루 8시간 대비)과 쉬운 말 요약.
- **월간 리포트** — 매월 첫 근무일 20:00 (주말·공휴일 제외). 지난달 일별 첫·마지막 GitLab 활동 시각과 수작업 환산 작업량을 엑셀로 첨부하고, 본문에는 월별 요약만.

## 동작

1. **기간**: 지난 발송 성공 시점 → 지금 (첫 실행은 24시간, 최대 7일). Mac이 잠들어 하루를 건너뛰어도 빈틈이 없다.
2. **수집**: 기간 내 활동한 모든 프로젝트의 모든 브랜치 커밋 — GitLab과, 설정하면 GitHub(`GITHUB_OWNERS`의 계정·조직 저장소)까지. 같은 사람의 커밋은 호스트와 상관없이 합친다. GitHub의 외부 기여자(매핑도 조직 멤버도 아닌 계정)는 뺀다. 머지 커밋과 리베이스·체리픽 사본(같은 제목+작성시각)은 제외.
3. **계정 귀속**: 커밋 작성자 이메일 → GitLab 계정. 개인 메일(예: naver)로 커밋하는 사람은 **push 이벤트 다수결로 별칭을 학습**해 `.state/aliases.json`에 쌓는다. 등록된 이메일이 항상 우선하며, 틀린 매핑은 이 파일을 직접 고친다.
4. **요약·추정**: 커밋 메시지·변경 파일 경로·증감 줄 수를 이 Mac에 로그인된 Claude Code(`claude -p`, 구독 한도 사용)에 보내 결과 중심 요약과 수작업 환산 작업량 범위를 받는다. `ANTHROPIC_API_KEY`는 자식 프로세스에서 지워 API 과금을 막는다. 코드 diff 본문은 보내지 않는다.
5. **발송**: SMTP(Gmail 앱 비밀번호)로 `MAIL_TO`에 보낸다.

## 숫자를 읽는 법

- **수작업 환산 작업량**은 AI가 커밋 결과물을 보고 "AI 없이 숙련 개발자가 손으로 만들었다면 걸렸을 시간"을 범위로 추정한 값이다. 실제로 일한 시간이 아니라 결과물의 크기다. 재현 실험(2026-10)에서 에이전트 혼자 하면 이 값의 약 1/57 시간이 걸렸다.
- **첫·마지막 활동**은 GitLab에 남은 흔적(커밋 작성·push·이슈·MR·댓글)의 시각이다. 근무 시작·종료 시각이 아니다.

## 설정

```bash
cp .env.example .env               # GITLAB_TOKEN(admin), SMTP_USER, SMTP_PASSWORD 채우기
cp people.example.json people.json # 표시 이름(한글), 보고 제외 계정, GitHub 계정 → 사람 매핑(github)
```

## 실행

```bash
uv run git-watcher --dry-run --no-llm --hours 24   # 수집만 확인
uv run git-watcher --dry-run --hours 24            # 요약까지, 메일은 안 보냄
uv run git-watcher --date 2026-10-01               # 그날 정기 보고 재현·발송
uv run git-watcher --monthly 2026-09 [--dry-run]   # 월간 리포트 (엑셀은 .state/reports/)
uv run git-watcher                                  # 정기 실행: 일일 발송 + 월초면 월간도
./scripts/install_launchd.sh                        # 평일 20:00 등록
tail -f logs/git-watcher.log
```

`--dry-run`·`--hours`·`--date`는 상태 파일(`.state/last_run`)을 건드리지 않는다. 월간 발송은 `.state/monthly_sent`로 중복을 막는다.

## 에이전트 활동 (텔레메트리)

```bash
./scripts/install_collector.sh   # 요약 전용 OTLP 수집기 상시 실행 (127.0.0.1:4318)
uv run git-watcher --backfill <Claude Code 대화.jsonl>   # 대화 기록 소급 (SessionEnd 훅이 자동 실행)
```

Claude Code·Codex가 보내는 이벤트에서 시각·길이·도구·토큰·비용만 저장한다. 프롬프트·출력 원문은 저장하지 않는다.

## 한계

- 실행 시각에 Mac이 **꺼져** 있으면 실행되지 않는다 (잠자기는 깨어난 뒤 실행). 다음 성공 실행이 빠진 기간을 메운다.
- 커밋 시각(committed date) 기준으로 거른다. 며칠 전에 만든 커밋을 오늘 push하면 잡히지 않을 수 있다.
- AI 추정은 같은 데이터로도 돌릴 때마다 조금씩 다르다.
