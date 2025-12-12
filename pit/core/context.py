"""pit context detection - .pit/ 폴더 기반 프로젝트 컨텍스트 감지"""

from pathlib import Path
from typing import Optional

import yaml


def find_pit_root(start: Path = None) -> Optional[Path]:
    """현재 디렉토리에서 .pit/ 폴더를 찾아 반환 (상위로 탐색)

    Args:
        start: 시작 디렉토리 (기본: 현재 작업 디렉토리)

    Returns:
        .pit/ 폴더 경로, 없으면 None
    """
    cwd = start or Path.cwd()

    for parent in [cwd, *cwd.parents]:
        pit_dir = parent / ".pit"
        if pit_dir.is_dir() and (pit_dir / "config.yaml").exists():
            return pit_dir

    return None


def get_project_context(start: Path = None) -> Optional[dict]:
    """현재 프로젝트의 설정 정보 반환

    Args:
        start: 시작 디렉토리 (기본: 현재 작업 디렉토리)

    Returns:
        프로젝트 config dict, 없으면 None
    """
    pit_root = find_pit_root(start)
    if not pit_root:
        return None

    config_path = pit_root / "config.yaml"
    return yaml.safe_load(config_path.read_text())


def get_project_id(start: Path = None) -> Optional[str]:
    """현재 프로젝트 ID 반환

    Args:
        start: 시작 디렉토리

    Returns:
        프로젝트 ID, 없으면 None
    """
    context = get_project_context(start)
    return context.get("id") if context else None


def require_pit_root(start: Path = None) -> Path:
    """pit 루트 반환, 없으면 에러 발생

    Args:
        start: 시작 디렉토리

    Returns:
        .pit/ 폴더 경로

    Raises:
        FileNotFoundError: .pit/ 폴더를 찾을 수 없을 때
    """
    pit_root = find_pit_root(start)
    if not pit_root:
        raise FileNotFoundError(
            "pit 프로젝트를 찾을 수 없습니다. 'pit init'으로 초기화하세요."
        )
    return pit_root
