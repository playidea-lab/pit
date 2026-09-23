"""오프라인 트윈 시험 (G7, docs/GRAPH_ENGINEERING.md)

"과거 판단 기록이 다음 판정을 맞히는 신호를 담고 있는가"를 시간 순 분할로 잰다.
훈련 구간의 결정만 보고 시험 구간 결정의 판정(승인·수정·거부)을 예측한다.

판정기는 갈아 끼운다. 여기에는 돈이 들지 않는 둘만 있다:
- prior: 훈련 구간에서 가장 많은 판정을 늘 고른다 (기록 없는 기준선)
- knn:   비슷한 과거 결정들의 판정으로 투표한다 (기록을 쓰는 판정기)
LLM·JEV 판정기는 같은 Judge 규약으로 붙인다 — 비용이 드니 사람이 승인한 뒤에.

보고는 문장이 아니라 구조화된 값이다. 합격 판단은 호출자가 값으로 한다.
"""

import random
import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime

from pit.server.conflicts import proposal_similarity

VERDICTS = ("approve", "modify", "reject")
TEST_FRACTION = 0.3
KNN_K = 5
# 이 유사도 아래의 이웃은 "비슷하지 않다"로 보고 버린다
KNN_MIN_SIMILARITY = 0.08
CONFIDENCE_THRESHOLDS = (0.0, 0.6, 0.8)
BOOTSTRAP_ROUNDS = 1000
BOOTSTRAP_SEED = 20260924
CI_LOW, CI_HIGH = 0.025, 0.975
# 설명(상황·제안)에 판정이 새어 있으면 정답을 보고 푸는 셈이다 — 웹 정리함의 VERDICT_WORDS 와 같은 규칙
_VERDICT_WORDS = re.compile(r"(거부|기각|폐기|승인|채택|확정|거절|반려|철회|rejected|approved|dropped|adopted)")


@dataclass(frozen=True)
class Item:
    id: str
    decided_at: datetime
    text: str
    label: str
    # 같은 프로젝트끼리 거의 같은 문장이 많다 — 교차 프로젝트 대조군이 이것으로 이웃을 거른다
    project: str = ""


@dataclass(frozen=True)
class Prediction:
    label: str
    confidence: float


Judge = Callable[[list[Item], Item], Prediction]


def load_items(rows: Iterable[dict[str, object]], include_leaky: bool = False) -> tuple[list[Item], dict[str, int]]:
    """판정형 결정만, 버린 것 제외. 판정이 설명에 샌 것은 기본으로 뺀다."""
    items, dropped = [], Counter()
    for row in rows:
        verdict = row.get("verdict")
        if row.get("status") == "discarded" or verdict not in VERDICTS:
            dropped["not_verdict"] += 1
            continue
        text = f"{row.get('situation', '')} {row.get('proposal', '')}"
        if not include_leaky and _VERDICT_WORDS.search(text):
            dropped["leaky"] += 1
            continue
        decided_at = datetime.fromisoformat(str(row["decided_at"]).replace("Z", "+00:00"))
        source = row.get("source") if isinstance(row.get("source"), dict) else {}
        project = str(source.get("project", "")) if isinstance(source, dict) else ""
        items.append(Item(id=str(row["id"]), decided_at=decided_at, text=text, label=str(verdict), project=project))
    return sorted(items, key=lambda item: (item.decided_at, item.id)), dict(dropped)


def time_split(items: list[Item], test_fraction: float = TEST_FRACTION) -> tuple[list[Item], list[Item]]:
    cut = max(1, round(len(items) * (1 - test_fraction)))
    return items[:cut], items[cut:]


def prior_judge(train: list[Item], _item: Item) -> Prediction:
    counts = Counter(item.label for item in train)
    label, count = counts.most_common(1)[0]
    return Prediction(label, count / len(train))


def knn_judge(train: list[Item], item: Item, k: int = KNN_K) -> Prediction:
    """비슷한 과거 결정의 판정으로 유사도 가중 투표. 비슷한 것이 없으면 기준선으로 물러나고 확신도 0."""
    scored = sorted(((proposal_similarity(item.text, past.text), past.label) for past in train), reverse=True)[:k]
    votes: Counter[str] = Counter()
    for similarity, label in scored:
        if similarity >= KNN_MIN_SIMILARITY:
            votes[label] += similarity
    if not votes:
        return Prediction(prior_judge(train, item).label, 0.0)
    label, weight = votes.most_common(1)[0]
    return Prediction(label, weight / sum(votes.values()))


def knn_other_projects_judge(train: list[Item], item: Item) -> Prediction:
    """대조군: 같은 프로젝트의 과거 결정을 빼고 투표한다. 여기서도 이기면 문장 중복이 아니라 판단 방식이 옮겨 간 것이다."""
    others = [past for past in train if not item.project or past.project != item.project]
    return knn_judge(others or train, item)


@dataclass
class JudgeReport:
    accuracy: float
    balanced_accuracy: float
    coverage: dict[str, dict[str, float]] = field(default_factory=dict)


def balanced_accuracy(pairs: list[tuple[str, str]]) -> float:
    """클래스별 재현율의 평균 — 거부가 71%인 데이터에서 '늘 거부'가 높은 점수를 받지 못하게"""
    recalls = []
    for label in {truth for truth, _ in pairs}:
        hits = [pred == truth for truth, pred in pairs if truth == label]
        recalls.append(sum(hits) / len(hits))
    return sum(recalls) / len(recalls) if recalls else 0.0


def _report(pairs: list[tuple[str, str, float]]) -> JudgeReport:
    report = JudgeReport(
        accuracy=sum(t == p for t, p, _ in pairs) / len(pairs),
        balanced_accuracy=balanced_accuracy([(t, p) for t, p, _ in pairs]),
    )
    for threshold in CONFIDENCE_THRESHOLDS:
        kept = [(t, p) for t, p, c in pairs if c >= threshold]
        report.coverage[f"{threshold:.1f}"] = {
            "coverage": len(kept) / len(pairs),
            "accuracy": (sum(t == p for t, p in kept) / len(kept)) if kept else 0.0,
        }
    return report


def _bootstrap_gap(a: list[tuple[str, str]], b: list[tuple[str, str]]) -> tuple[float, float]:
    """판정기 a − b 의 balanced accuracy 차이, 시험 결정을 복원 추출한 95% 구간"""
    rng = random.Random(BOOTSTRAP_SEED)
    n, gaps = len(a), []
    for _ in range(BOOTSTRAP_ROUNDS):
        picks = [rng.randrange(n) for _ in range(n)]
        gaps.append(balanced_accuracy([a[i] for i in picks]) - balanced_accuracy([b[i] for i in picks]))
    gaps.sort()
    return gaps[int(CI_LOW * BOOTSTRAP_ROUNDS)], gaps[int(CI_HIGH * BOOTSTRAP_ROUNDS) - 1]


def evaluate(items: list[Item], judges: dict[str, Judge], baseline: str = "prior") -> dict[str, object]:
    train, test = time_split(items)
    predictions = {
        name: [(item.label, *_unpack(judge(train, item))) for item in test] for name, judge in judges.items()
    }
    result: dict[str, object] = {
        "n_train": len(train),
        "n_test": len(test),
        "test_labels": dict(Counter(item.label for item in test)),
        "split_at": test[0].decided_at.isoformat() if test else None,
        "judges": {name: vars(_report(pairs)) for name, pairs in predictions.items()},
    }
    base = [(t, p) for t, p, _ in predictions[baseline]]
    result["vs_" + baseline] = {
        name: dict(zip(("ci_low", "ci_high"), _bootstrap_gap([(t, p) for t, p, _ in pairs], base), strict=True))
        for name, pairs in predictions.items()
        if name != baseline
    }
    return result


def _unpack(prediction: Prediction) -> tuple[str, float]:
    return prediction.label, prediction.confidence


JEV_HISTORY_K = 8


def make_jev_judge(api_key: str, post: Callable[[str, dict[str, str], dict[str, object]], dict[str, object]]) -> Judge:
    """JEV 판정기: 가장 비슷한 과거 판단 K건과 새 제안을 보여 주고 승인·수정·거부를 고르게 한다.
    post(url, headers, body) -> 응답 JSON — 전송은 호출자가 준다(테스트는 가짜, CLI는 httpx)."""
    from pit.server.jev import JEV_ENDPOINT, JevError, build_request, parse_response

    def judge(train: list[Item], item: Item) -> Prediction:
        ranked = sorted(train, key=lambda past: proposal_similarity(item.text, past.text), reverse=True)[:JEV_HISTORY_K]
        history = [("", past.text, past.label) for past in ranked]
        try:
            verdict = parse_response(post(JEV_ENDPOINT, {"Authorization": f"Bearer {api_key}"}, build_request(history, "", item.text)))
        except JevError:
            return Prediction(prior_judge(train, item).label, 0.0)
        return Prediction(verdict.label, verdict.confidence)

    return judge
