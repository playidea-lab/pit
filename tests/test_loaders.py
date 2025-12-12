"""Tests for pit loaders"""


from pit.loaders import get_feature, list_features, list_projects


class TestLoaders:
    def test_list_projects(self):
        projects = list_projects()
        assert len(projects) >= 1
        assert any(p.id == "pit" for p in projects)

    def test_list_features(self):
        features = list_features("pit")
        assert len(features) >= 2
        ids = [f.id for f in features]
        assert "F-0001" in ids
        assert "F-0002" in ids

    def test_get_feature(self):
        feature = get_feature("pit", "F-0001")
        assert feature is not None
        assert feature.id == "F-0001"
        assert feature.title == "pit CLI MVP"

    def test_get_feature_not_found(self):
        feature = get_feature("pit", "F-9999")
        assert feature is None

    def test_list_features_nonexistent_project(self):
        features = list_features("nonexistent")
        assert features == []
