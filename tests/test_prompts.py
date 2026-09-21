"""Prompt 모델과 로더 테스트"""

from pathlib import Path

import pytest

from pit.loaders.prompts import get_prompt, list_prompts, load_prompt
from pit.models.prompt import Prompt, PromptVariable

PROMPT_FILE = """---
name: Feature Spec
description: Create feature spec
variables:
  - name: feature_title
    description: Feature title
    required: true
output_tool: pit_create_feature
---

Create a feature named {{feature_title}}.
"""


def _make_prompt(variables: list[PromptVariable], content: str) -> Prompt:
    return Prompt(id="test", name="Test", variables=variables, content=content)


def test_prompt_render_all_variables_given_substitutes_placeholders():
    """모든 변수를 주면 자리표시자가 치환된다"""
    prompt = _make_prompt(
        [PromptVariable(name="name"), PromptVariable(name="count")],
        "Hello {{name}}! You have {{count}} items.",
    )

    assert prompt.render({"name": "Alice", "count": "5"}) == "Hello Alice! You have 5 items."


def test_prompt_render_variable_omitted_uses_default():
    """변수를 생략하면 기본값이 들어간다"""
    prompt = _make_prompt([PromptVariable(name="greeting", default="Hi")], "{{greeting}} there!")

    assert prompt.render({}) == "Hi there!"


def test_prompt_render_required_variable_missing_raises_value_error():
    """필수 변수가 없으면 ValueError"""
    prompt = _make_prompt([PromptVariable(name="title")], "{{title}}")

    with pytest.raises(ValueError, match="title"):
        prompt.render({})


def test_prompt_render_value_outside_enum_raises_value_error():
    """enum 밖의 값이면 ValueError"""
    prompt = _make_prompt([PromptVariable(name="level", enum=["low", "high"])], "{{level}}")

    with pytest.raises(ValueError, match="level"):
        prompt.render({"level": "medium"})


def test_load_prompt_file_with_frontmatter_returns_prompt(tmp_path: Path):
    """frontmatter가 있는 파일은 경로만으로 읽힌다 (.pit/ 탐지 불필요)"""
    path = tmp_path / "feature.md"
    path.write_text(PROMPT_FILE, encoding="utf-8")

    prompt = load_prompt(path)

    assert prompt is not None
    assert prompt.id == "feature"
    assert prompt.output_tool == "pit_create_feature"
    assert "{{feature_title}}" in prompt.content


def test_load_prompt_missing_file_returns_none(tmp_path: Path):
    """없는 파일은 None"""
    assert load_prompt(tmp_path / "nope.md") is None


def test_load_prompt_file_without_frontmatter_returns_none(tmp_path: Path):
    """frontmatter가 없는 파일은 None"""
    path = tmp_path / "plain.md"
    path.write_text("그냥 본문", encoding="utf-8")

    assert load_prompt(path) is None


def test_list_prompts_directory_with_one_file_returns_one_prompt(tmp_path: Path):
    """.pit/prompts/의 파일을 목록으로 읽는다"""
    prompts_dir = tmp_path / ".pit" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "feature.md").write_text(PROMPT_FILE, encoding="utf-8")

    prompts = list_prompts(tmp_path / ".pit")

    assert [p.id for p in prompts] == ["feature"]


def test_get_prompt_unknown_id_returns_none(tmp_path: Path):
    """없는 id는 None"""
    (tmp_path / ".pit" / "prompts").mkdir(parents=True)

    assert get_prompt("nonexistent", tmp_path / ".pit") is None
