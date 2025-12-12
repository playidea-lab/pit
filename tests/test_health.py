"""Tests for health check"""

from datetime import datetime, timedelta

from pit.core.health_check import HealthStatus, check_feature_health, check_project_health
from pit.models.feature import Checklist, Feature


class TestFeatureHealth:
    def test_healthy_feature(self):
        feature = Feature(
            id="F-0001",
            project_id="test",
            title="Test",
            status="planned",
            checklist=[Checklist(id="T1", label="Task 1", done=False)],
        )
        result = check_feature_health(feature)
        assert result.status == HealthStatus.GREEN
        assert result.score >= 80

    def test_no_checklist(self):
        feature = Feature(id="F-0001", project_id="test", title="Test")
        result = check_feature_health(feature)
        assert "No checklist defined" in result.reasons
        assert result.score < 100

    def test_urgent_pending(self):
        feature = Feature(
            id="F-0001",
            project_id="test",
            title="Test",
            checklist=[Checklist(id="T1", label="Urgent!", urgent=True, done=False)],
        )
        result = check_feature_health(feature)
        assert "Urgent tasks pending" in result.reasons[0]

    def test_overdue_feature(self):
        feature = Feature(
            id="F-0001",
            project_id="test",
            title="Test",
            status="in_progress",
            due_date=datetime.now() - timedelta(days=1),
            checklist=[Checklist(id="T1", label="Task", done=False)],
        )
        result = check_feature_health(feature)
        assert "Feature is overdue" in result.reasons


class TestProjectHealth:
    def test_empty_project(self):
        result = check_project_health([])
        assert result.status == HealthStatus.YELLOW
        assert "No features found" in result.reasons

    def test_healthy_project(self):
        features = [
            Feature(
                id="F-0001",
                project_id="test",
                title="Test 1",
                status="merged",
                checklist=[Checklist(id="T1", label="Done", done=True)],
            ),
            Feature(
                id="F-0002",
                project_id="test",
                title="Test 2",
                status="released",
                checklist=[Checklist(id="T1", label="Done", done=True)],
            ),
        ]
        result = check_project_health(features)
        assert result.status == HealthStatus.GREEN
