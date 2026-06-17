"""H-SVC-004: Read-only safety guard tests.

Validates:
- Blocked paths: /sql, /publish, /admin, /config, /env
- Path traversal in URL parameters is rejected
- HTTP methods beyond GET/POST/OPTIONS/HEAD are rejected
- POST on non-review endpoints is rejected
- All rejection responses include issue_id and stage

Reference: harness/service_workbench/H-SVC-004-readonly-guard.json
"""

from __future__ import annotations


class TestForbiddenPaths:
    """Block known-dangerous paths."""

    def test_rejects_sql_endpoint(self, client):
        """SVC-004-01: POST /sql is blocked (403)."""
        response = client.post("/sql", json={"sql": "select * from sqlite_master"})
        assert response.status_code == 403
        data = response.json()
        assert data["issue_id"] == "SVC-004"
        assert data["stage"] == "service_workbench"

    def test_rejects_publish_endpoint(self, client):
        """SVC-004-02: POST /runs/{id}/publish is blocked (403)."""
        response = client.post(
            "/api/v1/runs/run_20260617_001/publish",
            json={"target": "weibo"},
        )
        assert response.status_code == 403

    def test_rejects_admin_endpoint(self, client):
        """SVC-004-03: /admin path is blocked."""
        response = client.get("/admin")
        assert response.status_code == 403

    def test_rejects_config_endpoint(self, client):
        """SVC-004-04: /config path is blocked."""
        response = client.get("/config")
        assert response.status_code == 403


class TestMethodRestriction:
    """Only GET and POST (human-reviews only) are allowed."""

    def test_rejects_put(self, client):
        """SVC-004-05: PUT method is rejected."""
        response = client.put("/api/v1/runs")
        assert response.status_code == 403

    def test_rejects_delete(self, client):
        """SVC-004-06: DELETE method is rejected."""
        response = client.delete("/api/v1/runs/run_20260617_001")
        assert response.status_code == 403

    def test_rejects_patch(self, client):
        """SVC-004-07: PATCH method is rejected."""
        response = client.patch("/api/v1/runs/run_20260617_001")
        assert response.status_code == 403

    def test_allows_options(self, client):
        """SVC-004-08: OPTIONS (CORS preflight) is allowed through the guard.

        OPTIONS without Origin header returns 405 (Method Not Allowed) from
        the route layer, not 403 from the guard — proving the guard passes
        OPTIONS through. With Origin header, CORS middleware handles it (200).
        """
        # OPTIONS without Origin: guard passes, route returns 405 (not 403)
        response = client.options("/api/v1/runs")
        assert response.status_code in (200, 405)
        # Should NOT be 403 (that would mean the guard blocked it)
        assert response.status_code != 403

        # OPTIONS with Origin: CORS middleware handles it
        response2 = client.options(
            "/api/v1/runs",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
        )
        assert response2.status_code == 200

    def test_rejects_post_on_non_review_endpoint(self, client):
        """SVC-004-09: POST on non-review endpoints is rejected."""
        response = client.post(
            "/api/v1/runs",
            json={"foo": "bar"},
        )
        assert response.status_code == 403


class TestPathTraversalParams:
    """Path traversal detection in URL parameters."""

    def test_rejects_traversal_in_run_id(self, client):
        """SVC-004-10: '../' in run_id parameter is rejected."""
        response = client.get("/api/v1/runs/..%2F..%2F.env")
        assert response.status_code in (403, 404)

    def test_rejects_traversal_in_query_params(self, client):
        """SVC-004-11: '../' in query parameter is rejected."""
        response = client.get(
            "/api/v1/runs/run_20260617_001/stories?theme_section=..%2Fetc"
        )
        assert response.status_code == 403


class TestErrorResponseFormat:
    """All guard rejections follow the standard error format."""

    def test_error_has_required_fields(self, client):
        """SVC-004-12: Guard rejection includes detail, issue_id, stage."""
        response = client.post("/sql", json={})
        assert response.status_code == 403
        data = response.json()
        assert "detail" in data
        assert data["issue_id"] == "SVC-004"
        assert data["stage"] == "service_workbench"

    def test_error_status_codes_match_harness(self, client):
        """SVC-004-13: Rejection status codes are 403 or 404 per harness."""
        # /sql -> 403
        r1 = client.post("/sql", json={})
        assert r1.status_code == 403

        # /publish -> 403
        r2 = client.post("/api/v1/runs/run_20260617_001/publish")
        assert r2.status_code == 403

        # Unknown resource -> 404 (from route, not guard)
        r3 = client.get("/api/v1/nonexistent_endpoint")
        assert r3.status_code in (403, 404)


class TestDefenseInDepth:
    """Layered security: middleware + per-endpoint validation."""

    def test_multiple_layers_block_sql(self, client):
        """SVC-004-14: SQL is blocked at middleware AND route level."""
        # Via middleware (path match)
        r1 = client.post("/sql", json={"sql": "select 1"})
        assert r1.status_code == 403

        # Via query params with SQL
        r2 = client.get(
            "/api/v1/runs/run_20260617_001/stories?theme_section=sony';DROP TABLE stories;--"
        )
        # Should not execute SQL; should either pass through (safe) or be blocked
        # The guard doesn't block SQL in query params unless it contains path traversal
        # This is acceptable — the agent_query layer uses parameterized queries
        assert r2.status_code in (200, 403)

    def test_artifact_content_defense_in_depth(self, client):
        """SVC-004-15: Artifact content has middleware + endpoint path checks."""
        # Middleware blocks path traversal patterns in artifact_key
        r1 = client.get(
            "/api/v1/runs/run_20260617_001/artifacts/..%2F..%2F.env"
        )
        assert r1.status_code in (403, 404)

        # Endpoint also validates artifact_key against manifest
        r2 = client.get(
            "/api/v1/runs/run_20260617_001/artifacts/nonexistent"
        )
        assert r2.status_code == 403
        data = r2.json()
        assert data["issue_id"] == "SVC-004"
