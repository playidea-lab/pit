"""Markdown frontmatter 파싱·직렬화

프로젝트 탐지(.pit/)에 의존하지 않는 순수 함수만 둔다.
개인 보관함처럼 프로젝트 밖에서 도는 코드도 이 모듈을 쓸 수 있어야 한다.
"""

import re

import yaml

# ---\n<yaml>\n---\n<본문> 형태
_FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n?(.*)", re.DOTALL)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """YAML frontmatter와 본문을 분리한다

    Args:
        content: 전체 파일 내용

    Returns:
        (frontmatter dict, 본문) 튜플. frontmatter가 없거나 YAML이 깨졌으면
        빈 dict와 원문을 그대로 돌려준다.
    """
    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        return {}, content

    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}, content

    return frontmatter or {}, match.group(2).strip()


def dump_frontmatter(fields: dict, body: str) -> str:
    """frontmatter dict와 본문을 하나의 Markdown 문자열로 합친다

    Args:
        fields: frontmatter에 쓸 값 (키 순서 유지)
        body: Markdown 본문

    Returns:
        parse_frontmatter로 다시 읽을 수 있는 문자열
    """
    frontmatter_str = yaml.dump(
        fields, allow_unicode=True, default_flow_style=False, sort_keys=False
    )
    return f"---\n{frontmatter_str}---\n\n{body}"
