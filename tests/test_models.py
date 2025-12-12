"""Tests for pit models"""


from pit.models.feature import Checklist, Feature
from pit.models.project import Project, Repo


class TestProject:
    def test_create_minimal(self):
        project = Project(id="test", name="Test Project")
        assert project.id == "test"
        assert project.name == "Test Project"
        assert project.status == "active"

    def test_create_with_repos(self):
        project = Project(
            id="test",
            name="Test",
            repos=[Repo(name="repo1", url="git@github.com:test/repo1.git")],
        )
        assert len(project.repos) == 1
        assert project.repos[0].name == "repo1"


class TestFeature:
    def test_create_minimal(self):
        feature = Feature(id="F-0001", project_id="test", title="Test Feature")
        assert feature.id == "F-0001"
        assert feature.status == "planned"
        assert feature.priority == "medium"

    def test_progress_empty(self):
        feature = Feature(id="F-0001", project_id="test", title="Test")
        assert feature.progress == (0, 0)
        assert feature.progress_percent == 0

    def test_progress_with_tasks(self):
        feature = Feature(
            id="F-0001",
            project_id="test",
            title="Test",
            checklist=[
                Checklist(id="T1", label="Task 1", done=True),
                Checklist(id="T2", label="Task 2", done=False),
                Checklist(id="T3", label="Task 3", done=True),
            ],
        )
        assert feature.progress == (2, 3)
        assert feature.progress_percent == 66


class TestChecklist:
    def test_create_minimal(self):
        task = Checklist(id="T1", label="Do something")
        assert task.id == "T1"
        assert task.type == "code"
        assert task.done is False
        assert task.urgent is False

    def test_create_urgent(self):
        task = Checklist(id="T1", label="Fix bug", type="bug", urgent=True)
        assert task.urgent is True
        assert task.type == "bug"
