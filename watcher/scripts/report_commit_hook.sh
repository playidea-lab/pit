#!/usr/bin/env bash
# Claude Code PostToolUse 훅 (matcher: Bash): git commit 직후 report_commit 을 부르라고 에이전트에게 알린다.
# 훅 입력(JSON, stdin)의 tool_input.command 에 'git commit' 이 있고 성공했을 때만 안내를 넣는다.
input="$(cat)"
command="$(jq -r '.tool_input.command // empty' <<<"$input")"
case "$command" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac
cwd="$(jq -r '.cwd // empty' <<<"$input")"
sha="$(git -C "${cwd:-.}" rev-parse HEAD 2>/dev/null)" || exit 0
note="pithub: 방금 커밋 ${sha:0:12} 을 만들었다. report_commit 을 한 번 불러 이 커밋이 전체 업무에서 어디에 속하는지, 원자적인지, 메시지가 충분한지 보고하라 (start_id 가 있으면 함께). pithub 도구가 없으면 건너뛴다."
jq -nc --arg t "$note" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$t}}'
