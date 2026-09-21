"""대화 글에서 시크릿·개인정보·고객 용어를 가린다

도구 입출력을 버리는 것만으로 노출면의 대부분이 사라지지만, 사람이 붙여넣은
로그나 LLM이 되읊은 값에는 비밀이 남을 수 있다. 여기서 가린 뒤의 글만
추출 LLM과 트윈에 전달된다.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

MASK_TEMPLATE = "[가림:{rule}]"

# (규칙 이름, 패턴). 값 전체를 가리되 어떤 종류였는지는 남긴다.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("gitlab_token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{16,}")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{10,}")),
    ("supabase_token", re.compile(r"\bsbp_[a-f0-9]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL)),
    (
        "assigned_secret",
        re.compile(
            # DB_PASSWORD, api-key-prod 처럼 앞뒤로 이름이 이어져도 잡는다
            r"(?i)[A-Za-z0-9_\-]*(?:password|passwd|pwd|secret|token|api[_\-]?key|access[_\-]?key)"
            r"[A-Za-z0-9_\-]*\s*[:=]\s*['\"]?[^\s'\"]{6,}"
        ),
    ),
    ("resident_number", re.compile(r"\b\d{6}-[1-4]\d{6}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
)
CUSTOMER_TERM_RULE = "customer_term"


@dataclass(frozen=True)
class RedactionRules:
    customer_terms: tuple[str, ...] = ()


@dataclass
class RedactionResult:
    text: str
    counts: Counter[str] = field(default_factory=Counter)


def redact(text: str, rules: RedactionRules) -> RedactionResult:
    """글에서 민감한 값을 가린다. 무엇을 몇 번 가렸는지 함께 돌려준다."""
    counts: Counter[str] = Counter()

    for rule, pattern in SECRET_PATTERNS:
        text, replaced = pattern.subn(MASK_TEMPLATE.format(rule=rule), text)
        if replaced:
            counts[rule] += replaced

    for term in rules.customer_terms:
        if not term:
            continue
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        text, replaced = pattern.subn(MASK_TEMPLATE.format(rule=CUSTOMER_TERM_RULE), text)
        if replaced:
            counts[CUSTOMER_TERM_RULE] += replaced

    return RedactionResult(text=text, counts=counts)
