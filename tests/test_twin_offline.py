"""오프라인 트윈 시험 하네스 (G7) — 합성 데이터만"""

from datetime import datetime, timedelta, timezone

from pit.twin.offline import (
    balanced_accuracy,
    evaluate,
    knn_judge,
    load_items,
    prior_judge,
    time_split,
)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _rows(pairs: list[tuple[str, str]]) -> list[dict[str, object]]:
    return [
        {"id": f"D{i:03d}", "decided_at": (START + timedelta(days=i)).isoformat(), "verdict": verdict,
         "status": "confirmed", "situation": "상황", "proposal": proposal}
        for i, (proposal, verdict) in enumerate(pairs)
    ]  # fmt: skip


def test_load_items_drops_choices_discarded_and_verdict_leaking_text():
    rows = _rows([("캐시 도입", "approve"), ("채택된 설계", "approve")])
    rows.append({"id": "C", "decided_at": START.isoformat(), "verdict": None, "chosen": "A", "proposal": "x"})
    rows.append({**rows[0], "id": "X", "status": "discarded"})

    items, dropped = load_items(rows)

    assert [item.id for item in items] == ["D000"]
    assert dropped == {"leaky": 1, "not_verdict": 2}


def test_time_split_keeps_order_so_the_test_is_always_later():
    items, _ = load_items(_rows([(f"p{i}", "reject") for i in range(10)]))
    train, test = time_split(items)
    assert (len(train), len(test)) == (7, 3)
    assert max(i.decided_at for i in train) < min(i.decided_at for i in test)


def test_balanced_accuracy_does_not_reward_always_predicting_the_majority():
    pairs = [("reject", "reject")] * 9 + [("approve", "reject")]
    assert balanced_accuracy(pairs) == 0.5


def test_knn_uses_similar_history_where_prior_cannot_and_reports_the_gap():
    """주제별로 판정이 갈리는 사람: 캐시 관련은 늘 거부, 문서 관련은 늘 승인"""
    history = []
    for i in range(20):
        history.append((f"요청 캐시 계층을 추가한다 {i}", "reject"))
        history.append((f"설계 문서를 먼저 쓴다 {i}", "approve"))
    items, _ = load_items(_rows(history))

    report = evaluate(items, {"prior": prior_judge, "knn": knn_judge})

    assert report["judges"]["knn"]["balanced_accuracy"] == 1.0
    assert report["judges"]["prior"]["balanced_accuracy"] == 0.5
    assert report["vs_prior"]["knn"]["ci_low"] > 0


def test_knn_without_similar_history_falls_back_with_zero_confidence():
    items, _ = load_items(_rows([("캐시 계층", "reject"), ("캐시 계층 둘", "reject")]))
    prediction = knn_judge(items, items[0].__class__(id="n", decided_at=START, text="전혀 다른 날씨 이야기", label="approve"))
    assert (prediction.label, prediction.confidence) == ("reject", 0.0)


def test_cross_project_control_ignores_neighbors_from_the_same_project():
    from pit.twin.offline import Item, knn_other_projects_judge

    same = Item(id="a", decided_at=START, text="캐시 계층 추가", label="reject", project="borch")
    other = Item(id="b", decided_at=START, text="캐시 계층 추가 검토", label="approve", project="pit")
    query = Item(id="q", decided_at=START, text="캐시 계층 추가", label="reject", project="borch")

    assert knn_other_projects_judge([same, other], query).label == "approve"


def test_jev_judge_shows_nearest_history_and_falls_back_on_bad_answer():
    from pit.twin.offline import Item, make_jev_judge

    train = [Item(id=str(i), decided_at=START, text=f"캐시 계층 {i}", label="reject") for i in range(12)]
    sent: list[dict] = []

    def post(url, headers, body):  # noqa: ANN001, ANN202
        sent.append(body)
        return {"answers": {"verdict": {"choice": "modify", "confidence": 0.7}}}

    prediction = make_jev_judge("k", post)(train, Item(id="q", decided_at=START, text="캐시 계층", label="reject"))

    assert (prediction.label, prediction.confidence) == ("modify", 0.7)
    assert len(sent[0]["state"]["earlier_judgments"]) == 8
    broken = make_jev_judge("k", lambda *_: {"answers": {}})(train, train[0])
    assert (broken.label, broken.confidence) == ("reject", 0.0)
