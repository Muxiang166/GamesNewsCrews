"""H-SVC-001: Run list API tests.

Validates:
- Run list returns review-ready summaries with open_notification_count
- Run summary includes table_counts and notifications
- Stories, candidates, notifications, artifacts, quality-flags endpoints
- No raw SQL in responses
- 404 for unknown run_id
- Graceful handling when no database exists

Reference: harness/service_workbench/H-SVC-001-run-list-api.json
"""

from __future__ import annotations


class TestRunList:
    """H-SVC-001: GET /api/v1/runs — run list endpoint."""

    def test_returns_run_list_with_notification_counts(self, client):
        """SVC-001-01: Run list returns runs with open_notification_count."""
        response = client.get("/api/v1/runs")
        assert response.status_code == 200

        data = response.json()
        assert data["schema_version"] == "agent_db_query_v0"
        assert data["query_type"] == "runs"
        assert len(data["rows"]) >= 1

        run = data["rows"][0]
        assert run["run_id"] == "run_20260617_001"
        assert run["status"] == "completed"
        assert "open_notification_count" in run
        assert isinstance(run["open_notification_count"], int)

    def test_no_raw_sql_in_response(self, client):
        """SVC-001-02: Response must not expose raw SQL or sensitive data."""
        response = client.get("/api/v1/runs")
        data = response.json()

        # Ensure no raw SQL strings leak
        body = response.text
        assert "sqlite_master" not in body.lower()
        assert "select " not in body.lower()
        assert "create table" not in body.lower()

    def test_limit_enforced(self, client):
        """SVC-001-03: Limit query parameter is enforced."""
        response = client.get("/api/v1/runs?limit=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) <= 1

    def test_no_database_graceful(self, client_no_db):
        """SVC-001-04: Missing database returns empty list, not 500."""
        response = client_no_db.get("/api/v1/runs")
        assert response.status_code == 200
        data = response.json()
        assert data["rows"] == []
        assert data["summary"]["row_count"] == 0


class TestRunSummary:
    """GET /api/v1/runs/{run_id} — run summary endpoint."""

    def test_returns_summary_with_table_counts(self, client):
        """SVC-001-05: Run summary includes table counts."""
        response = client.get(f"/api/v1/runs/run_20260617_001")
        assert response.status_code == 200

        data = response.json()
        assert data["query_type"] == "summary"
        assert data["run_id"] == "run_20260617_001"
        assert "table_counts" in data["summary"]
        assert "open_notifications" in data["summary"]
        assert isinstance(data["summary"]["open_notifications"], int)

    def test_latest_resolves_to_most_recent(self, client):
        """SVC-001-06: 'latest' run_id resolves to the most recent run."""
        response = client.get("/api/v1/runs/latest")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "run_20260617_001"

    def test_unknown_run_id_404(self, client):
        """SVC-001-07: Unknown run_id returns 404."""
        response = client.get("/api/v1/runs/nonexistent_run")
        assert response.status_code == 404


class TestStories:
    """GET /api/v1/runs/{run_id}/stories — stories endpoint."""

    def test_returns_stories(self, client):
        """SVC-001-08: Stories endpoint returns story list."""
        response = client.get(f"/api/v1/runs/run_20260617_001/stories")
        assert response.status_code == 200
        data = response.json()
        assert data["query_type"] == "stories"
        assert len(data["rows"]) >= 1
        story = data["rows"][0]
        assert story["story_id"] == "story_001"
        assert story["title"] == "Test Story: Major Game Update"

    def test_filter_by_theme_section(self, client):
        """SVC-001-09: Stories filtered by theme_section."""
        response = client.get(
            f"/api/v1/runs/run_20260617_001/stories?theme_section=sony"
        )
        assert response.status_code == 200
        data = response.json()
        for story in data["rows"]:
            assert story["theme_section"] == "sony"


class TestCandidates:
    """GET /api/v1/runs/{run_id}/candidates — candidates endpoint."""

    def test_returns_candidates(self, client):
        """SVC-001-10: Candidates endpoint returns candidate list."""
        response = client.get(f"/api/v1/runs/run_20260617_001/candidates")
        assert response.status_code == 200
        data = response.json()
        assert data["query_type"] == "candidates"
        assert len(data["rows"]) >= 1

    def test_filter_by_lane(self, client):
        """SVC-001-11: Candidates filtered by lane."""
        response = client.get(
            f"/api/v1/runs/run_20260617_001/candidates?lane=main"
        )
        assert response.status_code == 200
        data = response.json()
        for c in data["rows"]:
            assert c["lane"] == "main"


class TestNotifications:
    """GET /api/v1/runs/{run_id}/notifications — notifications endpoint."""

    def test_returns_notifications(self, client):
        """SVC-001-12: Notifications endpoint returns notifications."""
        response = client.get(f"/api/v1/runs/run_20260617_001/notifications")
        assert response.status_code == 200
        data = response.json()
        assert data["query_type"] == "notifications"
        assert len(data["rows"]) >= 1
        notif = data["rows"][0]
        assert notif["notification_id"] == "notif_abc"
        assert notif["status"] == "open"

    def test_filter_by_severity(self, client):
        """SVC-001-13: Notifications filtered by severity."""
        response = client.get(
            f"/api/v1/runs/run_20260617_001/notifications?severity=warning&status=open"
        )
        assert response.status_code == 200
        data = response.json()
        for n in data["rows"]:
            assert n["severity"] == "warning"
            assert n["status"] == "open"


class TestQualityFlags:
    """GET /api/v1/runs/{run_id}/quality-flags — quality flags endpoint."""

    def test_returns_quality_flags(self, client):
        """SVC-001-14: Quality flags endpoint returns flags."""
        response = client.get(f"/api/v1/runs/run_20260617_001/quality-flags")
        assert response.status_code == 200
        data = response.json()
        assert data["query_type"] == "quality-flags"
        # Should include open notification as a flag
        assert isinstance(data["rows"], list)


class TestHealth:
    """GET /api/v1/health — health check endpoint."""

    def test_health_returns_ok(self, client):
        """SVC-001-15: Health check returns ok."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"
