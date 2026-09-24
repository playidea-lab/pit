#!/bin/sh
# pithub 기록 상기 훅 설치 — Claude Code · Codex 공통
#
# 사용자가 메시지를 보낼 때마다 AI에게 한 줄을 붙인다: "이 메시지가 당신의 제안에 대한 거부·수정·선택·방향 승인이면
# pithub record_decision 을 한 번 불러라". AI는 일에 몰두하면 기록 도구를 잊는다(개발 세션 실측 재현율 0%).
# 여러 번 실행해도 한 번만 들어간다. 원래 파일은 .bak-pithub 로 남긴다. 지우려면 각 파일에서 "pithub:" 항목을 빼면 된다.
set -eu

MARKER="pithub:"
TEXT="pithub: if this message rejects, corrects, chooses among, or approves a direction you proposed, call the pithub record_decision tool once (verbatim quote, about topics) before continuing. Skip routine ok/continue and new requests."

if ! command -v jq >/dev/null 2>&1; then
  echo "jq 가 필요합니다 (macOS: brew install jq)." >&2
  exit 1
fi

# 훅이 실행할 명령: 같은 문장을 hookSpecificOutput.additionalContext 로 내보낸다 (두 도구 형식이 같다)
HOOK_CMD=$(jq -rn --arg t "$TEXT" '"jq -nc --arg t " + ($t|@sh) + " '"'"'{hookSpecificOutput:{hookEventName:\"UserPromptSubmit\",additionalContext:$t}}'"'"'"')

install_into() {
  file="$1"
  label="$2"
  if [ -f "$file" ] && jq -e --arg m "$MARKER" '[.hooks.UserPromptSubmit[]?.hooks[]?.command | select(contains($m))] | length > 0' "$file" >/dev/null 2>&1; then
    echo "· $label: 이미 설치돼 있습니다 ($file)"
    return
  fi
  [ -f "$file" ] || echo '{}' > "$file"
  cp "$file" "$file.bak-pithub"
  tmp="$file.tmp-pithub"
  jq --arg c "$HOOK_CMD" '.hooks.UserPromptSubmit = ((.hooks.UserPromptSubmit // []) + [{"hooks":[{"type":"command","command":$c,"timeout":5}]}])' "$file" > "$tmp"
  mv "$tmp" "$file"
  echo "✓ $label: 설치했습니다 ($file)"
}

found=0
if [ -d "$HOME/.claude" ]; then
  install_into "$HOME/.claude/settings.json" "Claude Code"
  found=1
fi
if [ -d "$HOME/.codex" ]; then
  install_into "$HOME/.codex/hooks.json" "Codex"
  echo "  Codex 를 다음에 열 때 새 훅을 믿을지 물으면 허용하세요."
  found=1
fi
if [ "$found" = 0 ]; then
  echo "Claude Code(~/.claude)나 Codex(~/.codex)를 찾지 못했습니다. 도구를 한 번 실행한 뒤 다시 시도하세요." >&2
  exit 1
fi
echo "끝. 새 세션부터 적용됩니다."
