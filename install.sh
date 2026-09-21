#!/bin/sh
# 로컬 pit 한 줄 설치 (macOS / Linux) — 개발자용 선택 설치
#
#   curl -fsSL https://<pithub 주소>/install.sh | sh
#
# 비개발자는 이 스크립트가 필요 없다: 도구에 커넥터를 추가하고 GitHub로 로그인하면 끝난다.
# 이 스크립트는 (1) uv 가 없으면 설치하고 (2) pit CLI 를 uv tool 로 설치한 뒤 (3) pit setup 을 안내한다.
set -eu

PITHUB_URL="${PITHUB_URL:-}"
PIT_SOURCE="${PIT_SOURCE:-git+https://github.com/playideas/pit.git@feature/pithub-mcp}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv 를 설치합니다 (Python 패키지 관리자)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "pit CLI 를 설치합니다…"
uv tool install --force "$PIT_SOURCE"

echo
echo "설치됐습니다. 다음을 실행하세요:"
if [ -n "$PITHUB_URL" ]; then
  echo "  PITHUB_URL=$PITHUB_URL pit setup"
else
  echo "  PITHUB_URL=https://<pithub 주소> pit setup"
fi
