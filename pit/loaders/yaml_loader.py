"""YAML file loaders for pit data

.pit/ 폴더 기반 로컬 프로젝트 관리 (git처럼)
"""

from datetime import datetime
from pathlib import Path

import yaml

from pit.core.context import find_pit_root
from pit.models.feature import Feature
from pit.models.project import Project


def get_pit_root(pit_root: Path | None = None) -> Path:
    """Get the .pit/ directory

    Args:
        pit_root: 명시적 .pit 경로 (None이면 자동 탐지)

    Returns:
        .pit/ 폴더 경로

    Raises:
        FileNotFoundError: .pit/ 폴더를 찾을 수 없을 때
    """
    if pit_root:
        return pit_root

    found = find_pit_root()
    if not found:
        raise FileNotFoundError(
            "pit 프로젝트를 찾을 수 없습니다. 'pit init'으로 초기화하세요."
        )
    return found


# Legacy compatibility
def get_projects_root() -> Path:
    """Legacy: Get the projects root directory"""
    return Path.cwd() / "projects"


def load_project_config(pit_root: Path | None = None) -> Project | None:
    """Load project config from .pit/config.yaml

    Args:
        pit_root: .pit/ 폴더 경로 (None이면 자동 탐지)
    """
    try:
        pit_dir = get_pit_root(pit_root)
    except FileNotFoundError:
        return None

    config_path = pit_dir / "config.yaml"
    if not config_path.exists():
        return None

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return Project(**data) if data else None


def list_projects(root: Path | None = None) -> list[Project]:
    """List all projects from the projects directory

    Legacy mode: projects/ 폴더에서 여러 프로젝트 로드
    New mode: 현재 .pit/ 프로젝트만 반환
    """
    # New mode: .pit/ 폴더가 있으면 현재 프로젝트만 반환
    if root is None:
        project = load_project_config()
        if project:
            return [project]

    # Legacy mode: projects/ 폴더에서 로드
    root = root or get_projects_root()
    projects = []

    if not root.exists():
        return projects

    for project_dir in sorted(root.iterdir()):
        if not project_dir.is_dir():
            continue
        project_file = project_dir / "project.yaml"
        if project_file.exists():
            project = load_project(project_file)
            if project:
                projects.append(project)

    return projects


def load_project(path: Path) -> Project | None:
    """Load a project from a YAML file"""
    if not path.exists():
        return None

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return Project(**data) if data else None


def list_features(project_id: str | None = None, root: Path | None = None) -> list[Feature]:
    """List all features for a project

    Args:
        project_id: 프로젝트 ID (None이면 현재 .pit/ 프로젝트)
        root: 프로젝트 루트 경로 (legacy mode)
    """
    # New mode: .pit/ 폴더에서 직접 로드
    if project_id is None and root is None:
        try:
            pit_dir = get_pit_root()
            features_dir = pit_dir / "features"
        except FileNotFoundError:
            return []
    else:
        # Legacy mode: projects/<project_id>/features/
        root = root or get_projects_root()
        features_dir = root / (project_id or "") / "features"

    features = []

    if not features_dir.exists():
        return features

    for feature_file in sorted(features_dir.glob("*.yaml")):
        feature = load_feature(feature_file)
        if feature:
            features.append(feature)

    return features


def load_feature(path: Path) -> Feature | None:
    """Load a feature from a YAML file"""
    if not path.exists():
        return None

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return Feature(**data) if data else None


def get_feature(
    project_id: str | None = None,
    feature_id: str = "",
    root: Path | None = None,
) -> Feature | None:
    """Get a specific feature by ID

    Args:
        project_id: 프로젝트 ID (None이면 현재 .pit/ 프로젝트)
        feature_id: Feature ID (예: F-0001)
        root: 프로젝트 루트 경로 (legacy mode)
    """
    # New mode: .pit/ 폴더에서 직접 로드
    if project_id is None and root is None:
        try:
            pit_dir = get_pit_root()
            features_dir = pit_dir / "features"
        except FileNotFoundError:
            return None
    else:
        # Legacy mode
        root = root or get_projects_root()
        features_dir = root / (project_id or "") / "features"

    if not features_dir.exists():
        return None

    # Find feature file by ID prefix
    for feature_file in features_dir.glob(f"{feature_id}*.yaml"):
        feature = load_feature(feature_file)
        if feature and feature.id == feature_id:
            return feature

    return None


def get_next_feature_id(project_id: str | None = None, root: Path | None = None) -> str:
    """Get next available feature ID for a project"""
    features = list_features(project_id, root)
    max_num = 0
    for f in features:
        if f.id.startswith("F-"):
            try:
                num = int(f.id.split("-")[1])
                max_num = max(max_num, num)
            except (IndexError, ValueError):
                pass
    return f"F-{max_num + 1:04d}"


def save_feature(feature: Feature, root: Path | None = None) -> Path:
    """Save a feature to YAML file

    Args:
        feature: Feature 객체
        root: 프로젝트 루트 경로 (None이면 현재 .pit/ 사용)
    """
    # New mode: .pit/ 폴더에 저장
    if root is None:
        try:
            pit_dir = get_pit_root()
            features_dir = pit_dir / "features"
        except FileNotFoundError:
            # Fallback to legacy
            root = get_projects_root()
            features_dir = root / feature.project_id / "features"
    else:
        # Legacy mode
        features_dir = root / feature.project_id / "features"

    features_dir.mkdir(parents=True, exist_ok=True)

    # Create slug from title
    slug = feature.title.lower().replace(" ", "-")[:30]
    slug = "".join(c for c in slug if c.isalnum() or c == "-")

    filename = f"{feature.id}-{slug}.yaml"
    filepath = features_dir / filename

    data = feature.model_dump(mode="json", exclude_none=True)
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return filepath


def save_decision(
    project_id: str | None,
    decision_id: str,
    title: str,
    content: str,
    root: Path | None = None,
) -> Path:
    """Save a decision as markdown file"""
    # New mode: .pit/ 폴더에 저장
    if root is None and project_id is None:
        try:
            pit_dir = get_pit_root()
            decisions_dir = pit_dir / "decisions"
        except FileNotFoundError:
            raise FileNotFoundError("pit 프로젝트를 찾을 수 없습니다.")
    else:
        root = root or get_projects_root()
        decisions_dir = root / (project_id or "") / "decisions"

    decisions_dir.mkdir(parents=True, exist_ok=True)

    slug = title.lower().replace(" ", "-")[:40]
    slug = "".join(c for c in slug if c.isalnum() or c == "-")

    filename = f"{decision_id}-{slug}.md"
    filepath = decisions_dir / filename

    frontmatter = f"""---
id: {decision_id}
project_id: {project_id or ""}
title: {title}
status: active
created_at: {datetime.now().isoformat()}
---

"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)

    return filepath


def get_next_decision_id(project_id: str | None = None, root: Path | None = None) -> str:
    """Get next available decision ID"""
    # New mode: .pit/ 폴더
    if root is None and project_id is None:
        try:
            pit_dir = get_pit_root()
            decisions_dir = pit_dir / "decisions"
        except FileNotFoundError:
            return "D-0001"
    else:
        root = root or get_projects_root()
        decisions_dir = root / (project_id or "") / "decisions"

    if not decisions_dir.exists():
        return "D-0001"

    max_num = 0
    for f in decisions_dir.glob("D-*.md"):
        try:
            num = int(f.name.split("-")[1])
            max_num = max(max_num, num)
        except (IndexError, ValueError):
            pass
    return f"D-{max_num + 1:04d}"


def save_log(
    project_id: str | None,
    title: str,
    content: str,
    root: Path | None = None,
) -> Path:
    """Save a log as markdown file"""
    # New mode: .pit/ 폴더에 저장
    if root is None and project_id is None:
        try:
            pit_dir = get_pit_root()
            logs_dir = pit_dir / "logs"
        except FileNotFoundError:
            raise FileNotFoundError("pit 프로젝트를 찾을 수 없습니다.")
    else:
        root = root or get_projects_root()
        logs_dir = root / (project_id or "") / "logs"

    logs_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    # Find next session number for today
    existing = list(logs_dir.glob(f"{date_str}-session-*.md"))
    session_num = len(existing) + 1

    log_id = f"{date_str}-session-{session_num:03d}"
    filename = f"{log_id}.md"
    filepath = logs_dir / filename

    frontmatter = f"""---
id: {log_id}
project_id: {project_id or ""}
created_at: {now.isoformat()}
tags:
  - session
---

# {title}

"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)

    return filepath
