#!/usr/bin/env bash
# launchd 에이전트를 설치(재설치)한다. 매일 20:00에 브리핑을 보낸다.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UV="$(command -v uv)"
LABEL="pithub.watcher"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$ROOT/logs"
sed -e "s|__ROOT__|$ROOT|g" -e "s|__UV__|$UV|g" -e "s|__HOME__|$HOME|g" "$ROOT/launchd/$LABEL.plist.template" > "$DEST"
plutil -lint "$DEST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true  # 처음 설치면 내릴 게 없다
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "설치됨: $DEST (지금 한 번 돌려보려면: launchctl kickstart gui/$(id -u)/$LABEL)"
