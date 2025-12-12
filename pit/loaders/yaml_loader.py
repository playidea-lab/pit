"""YAML file loaders for pit data"""

from datetime import datetime
from pathlib import Path

import yaml

from pit.models.feature import Feature
from pit.models.project import Project


def get_projects_root() -> Path:
    """Get the projects root directory"""
    # Default to ./projects relative to cwd
    return Path.cwd() / "projects"


def list_projects(root: Path | None = None) -> list[Project]:
    """List all projects from the projects directory"""
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


def list_features(project_id: str, root: Path | None = None) -> list[Feature]:
    """List all features for a project"""
    root = root or get_projects_root()
    features_dir = root / project_id / "features"
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


def get_feature(project_id: str, feature_id: str, root: Path | None = None) -> Feature | None:
    """Get a specific feature by ID"""
    root = root or get_projects_root()
    features_dir = root / project_id / "features"

    if not features_dir.exists():
        return None

    # Find feature file by ID prefix
    for feature_file in features_dir.glob(f"{feature_id}*.yaml"):
        feature = load_feature(feature_file)
        if feature and feature.id == feature_id:
            return feature

    return None


def get_next_feature_id(project_id: str, root: Path | None = None) -> str:
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
    """Save a feature to YAML file"""
    root = root or get_projects_root()
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


def save_decision(project_id: str, decision_id: str, title: str, content: str, root: Path | None = None) -> Path:
    """Save a decision as markdown file"""
    root = root or get_projects_root()
    decisions_dir = root / project_id / "decisions"
    decisions_dir.mkdir(parents=True, exist_ok=True)

    slug = title.lower().replace(" ", "-")[:40]
    slug = "".join(c for c in slug if c.isalnum() or c == "-")

    filename = f"{decision_id}-{slug}.md"
    filepath = decisions_dir / filename

    frontmatter = f"""---
id: {decision_id}
project_id: {project_id}
title: {title}
status: active
created_at: {datetime.now().isoformat()}
---

"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)

    return filepath


def get_next_decision_id(project_id: str, root: Path | None = None) -> str:
    """Get next available decision ID"""
    root = root or get_projects_root()
    decisions_dir = root / project_id / "decisions"

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


def save_log(project_id: str, title: str, content: str, root: Path | None = None) -> Path:
    """Save a log as markdown file"""
    root = root or get_projects_root()
    logs_dir = root / project_id / "logs"
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
project_id: {project_id}
created_at: {now.isoformat()}
tags:
  - session
---

# {title}

"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)

    return filepath
