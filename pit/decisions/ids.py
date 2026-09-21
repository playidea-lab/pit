"""개인 결정 ID

같은 판정 발화에서는 언제 다시 추출해도 같은 ID가 나와야 한다. 그래야 재추출이
멱등이고, 버린 후보가 되살아나지 않고, 여러 기기의 결정을 합쳐도 충돌하지 않는다.
팀 원장의 D-0001 과 섞이지 않도록 접두사를 달리한다.
"""

import hashlib
from datetime import datetime

DECISION_ID_PREFIX = "PD"
DECISION_ID_HASH_CHARS = 8


def make_decision_id(
    session_id: str, verdict_uuid: str, decided_at: datetime, part: int = 0
) -> str:
    """결정 ID를 만든다

    Args:
        session_id: 출처 세션
        verdict_uuid: 사람의 판정이 담긴 레코드의 uuid
        decided_at: 판정 시각 (날짜 부분만 쓴다)
        part: 한 레코드에서 결정이 여러 개 나올 때의 순번 (질문이 여러 개인 선택)
    """
    digest = hashlib.sha256(f"{session_id}\n{verdict_uuid}\n{part}".encode()).hexdigest()
    return f"{DECISION_ID_PREFIX}-{decided_at:%Y%m%d}-{digest[:DECISION_ID_HASH_CHARS]}"
