"""개인 보관함 위치 결정과 초기화

개인 보관함은 프로젝트 저장소 밖에 둔다. 프로젝트의 .pit/ 는 git 추적 대상이라
세션 원문을 거기에 두면 커밋되기 때문이다.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

PIT_HOME_ENV = "PIT_HOME"
DEFAULT_HOME_DIRNAME = ".pit"
CONFIG_FILENAME = "twin.yaml"

# find_pit_root()는 상위로 올라가며 ".pit/config.yaml"을 프로젝트로 본다.
# 개인 보관함에 이 파일이 생기면 홈 아래 모든 폴더가 개인 보관함을 프로젝트로 오인한다.
PROJECT_MARKER_FILENAME = "config.yaml"

HOME_DIR_MODE = 0o700

# 원문과 파생 캐시는 개인 git repo에도 넣지 않는다 (크기·시크릿 노출면)
UNTRACKED_DIRS = ("vault", "views", "candidates", "snapshots", "cache")
TRACKED_DIRS = ("decisions", "evals")


class PersonalHomeError(Exception):
    """개인 보관함을 쓸 수 없는 상태"""


def resolve_pit_home(explicit: Path | None = None) -> Path:
    """개인 보관함 경로를 정한다

    우선순위: 명시 인자 → PIT_HOME 환경변수 → ~/.pit

    Args:
        explicit: 호출자가 직접 지정한 경로 (테스트·CLI 옵션)

    Returns:
        개인 보관함 절대 경로 (존재 여부는 보장하지 않는다)
    """
    if explicit is not None:
        return explicit.expanduser()

    from_env = os.environ.get(PIT_HOME_ENV)
    if from_env:
        return Path(from_env).expanduser()

    return Path.home() / DEFAULT_HOME_DIRNAME


def ensure_home(home: Path) -> None:
    """개인 보관함 디렉터리 구조와 .gitignore를 만든다 (이미 있으면 그대로 둔다)

    Args:
        home: 개인 보관함 경로

    Raises:
        PersonalHomeError: 그 경로가 프로젝트의 .pit/ 폴더로 보일 때
    """
    if (home / PROJECT_MARKER_FILENAME).exists():
        raise PersonalHomeError(
            f"{home} 에 {PROJECT_MARKER_FILENAME} 이 있어 프로젝트 폴더로 보입니다. "
            f"{PIT_HOME_ENV} 로 다른 경로를 지정하세요."
        )

    home.mkdir(mode=HOME_DIR_MODE, parents=True, exist_ok=True)
    for name in (*UNTRACKED_DIRS, *TRACKED_DIRS):
        (home / name).mkdir(mode=HOME_DIR_MODE, exist_ok=True)

    gitignore = home / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "".join(f"{name}/\n" for name in UNTRACKED_DIRS), encoding="utf-8"
        )
        logger.info("개인 보관함 초기화", extra={"home": str(home)})
