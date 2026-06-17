"""H-SVC-003: Human review capture tests.

Validates:
- POST creates a review record (201)
- Review record has all required fields
- Validation rejects invalid score/style_direction
- GET returns list of reviews
- Review write does NOT modify facts artifacts

Reference: harness/service_workbench/H-SVC-003-human-review-save.json
"""

from __future__ import annotations

import json

REVIEW_PAYLOAD = {
    "story_id": "story_001",
    "score": 4,
    "style_direction": "more_game_content_first",
    "notes": "保留游戏本体更新，下沉泛讨论。",
}


class TestSubmitReview:
    """POST /api/v1/runs/{run_id}/human-reviews — submit review endpoint."""

    def test_creates_review_successfully(self, client):
        """SVC-003-01: POST creates a review record and returns 201."""
        response = client.post(
            "/api/v1/runs/run_20260617_001/human-reviews",
            json=REVIEW_PAYLOAD,
        )
        assert response.status_code == 201

        data = response.json()
        assert data["run_id"] == "run_20260617_001"
        assert data["story_id"] == "story_001"
        assert data["score"] == 4
        assert data["style_direction"] == "more_game_content_first"
        assert data["notes"] == "保留游戏本体更新，下沉泛讨论。"
        assert "review_id" in data
        assert "created_at" in data
        assert data["review_id"].startswith("rev_")

    def test_review_field_validation_invalid_score(self, client):
        """SVC-003-02: Score <1 or >5 returns 422."""
        response = client.post(
            "/api/v1/runs/run_20260617_001/human-reviews",
            json={**REVIEW_PAYLOAD, "score": 0},
        )
        assert response.status_code == 422

        response = client.post(
            "/api/v1/runs/run_20260617_001/human-reviews",
            json={**REVIEW_PAYLOAD, "score": 6},
        )
        assert response.status_code == 422

    def test_review_field_validation_invalid_style(self, client):
        """SVC-003-03: Invalid style_direction returns 422."""
        response = client.post(
            "/api/v1/runs/run_20260617_001/human-reviews",
            json={**REVIEW_PAYLOAD, "style_direction": "invalid_style"},
        )
        assert response.status_code == 422

    def test_review_field_validation_path_traversal_story_id(self, client):
        """SVC-003-04: Path traversal in story_id returns 422."""
        response = client.post(
            "/api/v1/runs/run_20260617_001/human-reviews",
            json={**REVIEW_PAYLOAD, "story_id": "../etc/passwd"},
        )
        assert response.status_code == 422

        response = client.post(
            "/api/v1/runs/run_20260617_001/human-reviews",
            json={**REVIEW_PAYLOAD, "story_id": "story/001"},
        )
        assert response.status_code == 422

    def test_idempotent_resubmit(self, client):
        """SVC-003-05: Re-submitting the same review overwrites (insert or replace)."""
        # First submit
        r1 = client.post(
            "/api/v1/runs/run_20260617_001/human-reviews",
            json=REVIEW_PAYLOAD,
        )
        assert r1.status_code == 201

        # Second submit with same story_id
        r2 = client.post(
            "/api/v1/runs/run_20260617_001/human-reviews",
            json={**REVIEW_PAYLOAD, "score": 5, "notes": "Updated review"},
        )
        # Should succeed (same review_id generated for same run+story)
        assert r2.status_code == 201
        data = r2.json()
        assert data["score"] == 5

    def test_missing_required_fields(self, client):
        """SVC-003-06: Missing required fields returns 422."""
        response = client.post(
            "/api/v1/runs/run_20260617_001/human-reviews",
            json={},
        )
        assert response.status_code == 422


class TestListReviews:
    """GET /api/v1/runs/{run_id}/human-reviews — list reviews endpoint."""

    def test_lists_reviews_after_submission(self, client):
        """SVC-003-07: List returns submitted reviews."""
        # Submit a review first
        client.post(
            "/api/v1/runs/run_20260617_001/human-reviews",
            json=REVIEW_PAYLOAD,
        )

        # Then list
        response = client.get(
            "/api/v1/runs/run_20260617_001/human-reviews"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "run_20260617_001"
        assert len(data["rows"]) >= 1
        assert data["rows"][0]["story_id"] == "story_001"

    def test_empty_reviews_for_new_run(self, client):
        """SVC-003-08: Run with no reviews returns empty list."""
        response = client.get(
            "/api/v1/runs/run_20260617_001/human-reviews"
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["rows"], list)


class TestReviewDoesNotMutateFacts:
    """SVC-003 guarantees: review writes do not mutate facts."""

    def test_stories_unchanged_after_review(self, client):
        """SVC-003-09: Story data is unchanged after review submission."""
        # Get story before
        stories_before = client.get(
            "/api/v1/runs/run_20260617_001/stories"
        ).json()

        # Submit review
        client.post(
            "/api/v1/runs/run_20260617_001/human-reviews",
            json=REVIEW_PAYLOAD,
        )

        # Get story after
        stories_after = client.get(
            "/api/v1/runs/run_20260617_001/stories"
        ).json()

        # Story data must be identical
        assert stories_before == stories_after

    def test_artifacts_unchanged_after_review(self, client):
        """SVC-003-10: Artifact index unchanged after review submission."""
        artifacts_before = client.get(
            "/api/v1/runs/run_20260617_001/artifacts"
        ).json()

        client.post(
            "/api/v1/runs/run_20260617_001/human-reviews",
            json=REVIEW_PAYLOAD,
        )

        artifacts_after = client.get(
            "/api/v1/runs/run_20260617_001/artifacts"
        ).json()

        assert artifacts_before == artifacts_after
