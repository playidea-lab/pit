"""frontmatter 파싱·직렬화 테스트"""

from pit.loaders.frontmatter import dump_frontmatter, parse_frontmatter


def test_parse_frontmatter_valid_block_returns_fields_and_body():
    """정상 frontmatter는 dict와 본문으로 나뉜다"""
    fields, body = parse_frontmatter("---\nid: PD-1\ntags:\n- a\n---\n\n본문입니다\n")

    assert fields == {"id": "PD-1", "tags": ["a"]}
    assert body == "본문입니다"


def test_parse_frontmatter_missing_block_returns_empty_fields_and_original():
    """frontmatter가 없으면 빈 dict와 원문을 그대로 돌려준다"""
    content = "# 제목만 있는 문서"

    fields, body = parse_frontmatter(content)

    assert fields == {}
    assert body == content


def test_parse_frontmatter_invalid_yaml_returns_empty_fields_and_original():
    """YAML이 깨졌으면 빈 dict와 원문을 돌려준다"""
    content = "---\nid: [unclosed\n---\n본문"

    fields, body = parse_frontmatter(content)

    assert fields == {}
    assert body == content


def test_dump_frontmatter_roundtrip_preserves_fields_and_body():
    """dump한 결과를 다시 parse하면 같은 값이 나온다"""
    fields = {"id": "PD-20260922-ab12cd34", "verdict": "modify", "supersedes": ["PD-1"]}

    text = dump_frontmatter(fields, "한국어 본문\n둘째 줄")

    assert parse_frontmatter(text) == (fields, "한국어 본문\n둘째 줄")


def test_dump_frontmatter_preserves_key_order_and_unicode():
    """키 순서를 유지하고 한글을 이스케이프하지 않는다"""
    text = dump_frontmatter({"zeta": "가", "alpha": "나"}, "")

    assert text.index("zeta") < text.index("alpha")
    assert "가" in text
