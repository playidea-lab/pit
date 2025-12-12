"""Git integration for pit"""

import subprocess
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


class PitConfig(BaseModel):
    """Configuration from .pit.yml"""

    project_id: str
    pit_repo_path: Optional[str] = None


def find_pit_config(start_path: Path | None = None) -> Path | None:
    """Find .pit.yml in current or parent directories"""
    path = start_path or Path.cwd()

    while path != path.parent:
        config_file = path / ".pit.yml"
        if config_file.exists():
            return config_file
        path = path.parent

    return None


def load_pit_config(path: Path | None = None) -> PitConfig | None:
    """Load .pit.yml configuration"""
    config_path = path or find_pit_config()
    if not config_path or not config_path.exists():
        return None

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return PitConfig(**data) if data else None


def get_current_branch() -> str | None:
    """Get current git branch name"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_repo_root() -> Path | None:
    """Get git repository root directory"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None


def create_feature_branch(feature_id: str, slug: str) -> tuple[bool, str]:
    """Create a git branch for a feature"""
    branch_name = f"feature/{feature_id}-{slug}"

    try:
        # Check if branch exists
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch_name],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            return False, f"Branch '{branch_name}' already exists"

        # Create and checkout branch
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            capture_output=True,
            text=True,
            check=True,
        )

        return True, branch_name

    except subprocess.CalledProcessError as e:
        return False, f"Failed to create branch: {e.stderr}"


def checkout_branch(branch_name: str) -> tuple[bool, str]:
    """Checkout an existing branch"""
    try:
        subprocess.run(
            ["git", "checkout", branch_name],
            capture_output=True,
            text=True,
            check=True,
        )
        return True, f"Switched to '{branch_name}'"
    except subprocess.CalledProcessError as e:
        return False, f"Failed to checkout: {e.stderr}"


def get_last_commit_info() -> dict | None:
    """Get info about the last commit"""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H|%s|%ci"],
            capture_output=True,
            text=True,
            check=True,
        )
        parts = result.stdout.strip().split("|")
        if len(parts) >= 3:
            return {
                "hash": parts[0][:8],
                "message": parts[1],
                "date": parts[2],
            }
    except subprocess.CalledProcessError:
        pass
    return None


def list_branches_for_feature(feature_id: str) -> list[str]:
    """List all branches containing the feature ID"""
    try:
        result = subprocess.run(
            ["git", "branch", "-a"],
            capture_output=True,
            text=True,
            check=True,
        )
        branches = []
        for line in result.stdout.strip().split("\n"):
            branch = line.strip().lstrip("* ")
            if feature_id in branch:
                branches.append(branch)
        return branches
    except subprocess.CalledProcessError:
        return []
