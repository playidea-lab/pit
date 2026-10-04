#!/usr/bin/env bash
# Claude Code SessionEnd 훅: 끝난 대화를 요약 이벤트로 소급 기록한다.
# 훅 입력(JSON, stdin)의 transcript_path 를 읽는다. 실패는 로그에 남기고 세션 종료는 막지 않는다.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/logs/backfill.log"
mkdir -p "$ROOT/logs"
path="$(jq -r '.transcript_path // empty')"
if [ -z "$path" ] || [ ! -f "$path" ]; then
  echo "$(date '+%F %T') 대화 기록 경로 없음 — 건너뜀" >> "$LOG"
  exit 0
fi
if ! "$HOME/.local/bin/uv" run --directory "$ROOT" --frozen --quiet git-watcher --backfill "$path" >> "$LOG" 2>&1; then
  echo "$(date '+%F %T') 소급 기록 실패: $path" >> "$LOG"
fi
exit 0
