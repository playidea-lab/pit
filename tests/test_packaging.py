"""설치본에 패키지 데이터가 들어 있는지 확인"""

import subprocess
import zipfile
from pathlib import Path

import pytest

from pit.extract.llm_extract import EXTRACT_PROMPT_NAME, load_extract_prompt

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_load_extract_prompt_bundled_prompt_is_readable(tmp_path: Path):
    """덮어쓴 프롬프트가 없으면 패키지에 든 기본 프롬프트를 읽는다"""
    content, digest = load_extract_prompt(tmp_path)

    assert "결정 지점" in content
    assert len(digest) == 12


def test_load_extract_prompt_home_override_wins(tmp_path: Path):
    override = tmp_path / "prompts" / EXTRACT_PROMPT_NAME
    override.parent.mkdir()
    override.write_text("---\nname: custom\n---\n내 프롬프트", encoding="utf-8")

    content, _ = load_extract_prompt(tmp_path)

    assert content == "내 프롬프트"


@pytest.mark.slow
def test_built_wheel_contains_bundled_prompts(tmp_path: Path):
    """wheel을 실제로 빌드해 프롬프트가 들어갔는지 본다 — 빠지면 설치한 사람만 실행 중에 알게 된다"""
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )  # fmt: skip

    (wheel,) = tmp_path.glob("*.whl")
    names = zipfile.ZipFile(wheel).namelist()

    assert f"pit/twin/prompts/{EXTRACT_PROMPT_NAME}" in names
    assert not [name for name in names if name.startswith("pithub/")]
