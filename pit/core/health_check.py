"""Health check logic for pit"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from pit.models.feature import Feature


class HealthStatus(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class HealthResult(BaseModel):
    status: HealthStatus
    reasons: list[str]
    score: int  # 0-100


def check_feature_health(feature: Feature) -> HealthResult:
    """Check health of a single feature"""
    reasons = []
    score = 100

    now = datetime.now()

    # Check 1: Overdue tasks
    overdue_tasks = []
    for task in feature.checklist:
        if not task.done and task.due_date:
            if task.due_date.replace(tzinfo=None) < now:
                overdue_tasks.append(task.label)
                score -= 15

    if overdue_tasks:
        reasons.append(f"Overdue tasks: {len(overdue_tasks)}")

    # Check 2: Urgent tasks not done
    urgent_pending = [t for t in feature.checklist if t.urgent and not t.done]
    if urgent_pending:
        reasons.append(f"Urgent tasks pending: {len(urgent_pending)}")
        score -= 20 * len(urgent_pending)

    # Check 3: Stale in_progress (no update in 7 days)
    if feature.status == "in_progress" and feature.updated_at:
        days_stale = (now - feature.updated_at.replace(tzinfo=None)).days
        if days_stale > 7:
            reasons.append(f"Stale: no update in {days_stale} days")
            score -= 10

    # Check 4: Feature overdue
    if feature.due_date and feature.status not in ("merged", "released"):
        if feature.due_date.replace(tzinfo=None) < now:
            reasons.append("Feature is overdue")
            score -= 25

    # Check 5: No checklist
    if not feature.checklist:
        reasons.append("No checklist defined")
        score -= 10

    # Check 6: Progress stalled (in_progress but 0% done)
    if feature.status == "in_progress":
        done, total = feature.progress
        if total > 0 and done == 0:
            reasons.append("In progress but no tasks completed")
            score -= 15

    # Determine status
    score = max(0, min(100, score))

    if score >= 80:
        status = HealthStatus.GREEN
    elif score >= 50:
        status = HealthStatus.YELLOW
    else:
        status = HealthStatus.RED

    if not reasons:
        reasons.append("All checks passed")

    return HealthResult(status=status, reasons=reasons, score=score)


def check_project_health(features: list[Feature]) -> HealthResult:
    """Check overall health of a project based on its features"""
    if not features:
        return HealthResult(
            status=HealthStatus.YELLOW,
            reasons=["No features found"],
            score=50,
        )

    feature_results = [check_feature_health(f) for f in features]

    # Aggregate
    avg_score = sum(r.score for r in feature_results) // len(feature_results)
    red_count = sum(1 for r in feature_results if r.status == HealthStatus.RED)
    yellow_count = sum(1 for r in feature_results if r.status == HealthStatus.YELLOW)

    reasons = []
    if red_count > 0:
        reasons.append(f"{red_count} features in RED")
    if yellow_count > 0:
        reasons.append(f"{yellow_count} features in YELLOW")

    # Active features
    active = [f for f in features if f.status in ("planned", "in_progress")]
    if active:
        reasons.append(f"{len(active)} active features")

    if not reasons:
        reasons.append("All features healthy")

    if avg_score >= 80 and red_count == 0:
        status = HealthStatus.GREEN
    elif avg_score >= 50 or red_count <= 1:
        status = HealthStatus.YELLOW
    else:
        status = HealthStatus.RED

    return HealthResult(status=status, reasons=reasons, score=avg_score)
