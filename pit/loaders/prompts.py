"""Prompt markdown loader

.pit/prompts/ 폴더에서 프롬프트 템플릿 로드
Frontmatter (YAML) + Markdown 본문 형식
"""

from pathlib import Path

import yaml

from pit.loaders.frontmatter import parse_frontmatter
from pit.loaders.yaml_loader import get_pit_root
from pit.models.prompt import Prompt, PromptVariable


def list_prompts(pit_root: Path | None = None) -> list[Prompt]:
    """List all prompts from .pit/prompts/

    Args:
        pit_root: .pit/ 폴더 경로 (None이면 자동 탐지)

    Returns:
        Prompt 목록
    """
    try:
        pit_dir = get_pit_root(pit_root)
    except FileNotFoundError:
        return []

    prompts_dir = pit_dir / "prompts"
    if not prompts_dir.exists():
        return []

    prompts = []
    for prompt_file in sorted(prompts_dir.glob("*.md")):
        prompt = load_prompt(prompt_file)
        if prompt:
            prompts.append(prompt)

    return prompts


def load_prompt(path: Path) -> Prompt | None:
    """Load a prompt from a markdown file with frontmatter

    Args:
        path: Prompt markdown 파일 경로

    Returns:
        Prompt 객체 또는 None
    """
    if not path.exists():
        return None

    with open(path, encoding="utf-8") as f:
        content = f.read()

    # Frontmatter 파싱
    frontmatter, body = parse_frontmatter(content)

    if not frontmatter:
        return None

    # id가 없으면 파일명에서 추출
    if "id" not in frontmatter:
        frontmatter["id"] = path.stem

    # name이 없으면 id 사용
    if "name" not in frontmatter:
        frontmatter["name"] = frontmatter["id"]

    # variables 파싱
    variables = []
    for var_data in frontmatter.get("variables", []):
        if isinstance(var_data, str):
            # 간단한 형식: "feature_title"
            variables.append(PromptVariable(name=var_data))
        elif isinstance(var_data, dict):
            # 상세 형식: {name: ..., description: ..., ...}
            variables.append(PromptVariable(**var_data))

    return Prompt(
        id=frontmatter["id"],
        name=frontmatter["name"],
        description=frontmatter.get("description"),
        variables=variables,
        content=body,
        output_tool=frontmatter.get("output_tool"),
        agent=frontmatter.get("agent"),
    )


def get_prompt(prompt_id: str, pit_root: Path | None = None) -> Prompt | None:
    """Get a specific prompt by ID

    Args:
        prompt_id: Prompt ID (예: feature-spec)
        pit_root: .pit/ 폴더 경로 (None이면 자동 탐지)

    Returns:
        Prompt 객체 또는 None
    """
    try:
        pit_dir = get_pit_root(pit_root)
    except FileNotFoundError:
        return None

    prompts_dir = pit_dir / "prompts"
    prompt_file = prompts_dir / f"{prompt_id}.md"

    return load_prompt(prompt_file)


def save_prompt(prompt: Prompt, pit_root: Path | None = None) -> Path:
    """Save a prompt to markdown file

    Args:
        prompt: Prompt 객체
        pit_root: .pit/ 폴더 경로 (None이면 자동 탐지)

    Returns:
        저장된 파일 경로
    """
    pit_dir = get_pit_root(pit_root)
    prompts_dir = pit_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{prompt.id}.md"
    filepath = prompts_dir / filename

    # Frontmatter 생성
    frontmatter_data = {
        "name": prompt.name,
    }

    if prompt.description:
        frontmatter_data["description"] = prompt.description

    if prompt.variables:
        frontmatter_data["variables"] = [
            v.model_dump(mode="json", exclude_none=True) for v in prompt.variables
        ]

    if prompt.output_tool:
        frontmatter_data["output_tool"] = prompt.output_tool

    if prompt.agent:
        frontmatter_data["agent"] = prompt.agent

    # YAML frontmatter + content
    frontmatter_str = yaml.dump(
        frontmatter_data, allow_unicode=True, default_flow_style=False, sort_keys=False
    )
    file_content = f"---\n{frontmatter_str}---\n\n{prompt.content}"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(file_content)

    return filepath

