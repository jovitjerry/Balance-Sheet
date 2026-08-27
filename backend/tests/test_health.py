"""API smoke tests."""

from __future__ import annotations

from httpx import AsyncClient


class TestHealth:
    async def test_health_reports_api_and_database_state(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        # "unavailable" is a legitimate answer offline; the point is that the
        # endpoint answers truthfully rather than asserting connectivity it has
        # not verified.
        assert body["database"] in {"connected", "unavailable"}


class TestPipelineEndpoint:
    async def test_it_reports_which_modules_are_implemented(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/pipeline")
        assert response.status_code == 200
        stages = {stage["stage"]: stage for stage in response.json()["stages"]}
        for name in ("ingest", "extract", "ratios", "insights"):
            assert stages[name]["state"] == "implemented", name

    async def test_it_distinguishes_upload_stages_from_the_question_answerer(
        self, client: AsyncClient
    ) -> None:
        """Module 4 is built but request-driven, and `state` alone cannot say so."""
        response = await client.get("/api/v1/pipeline")
        stages = {stage["stage"]: stage for stage in response.json()["stages"]}

        assert stages["ratios"]["trigger"] == "upload"
        assert stages["insights"]["trigger"] == "on_request"


class TestOpenAPI:
    async def test_the_schema_builds(self, client: AsyncClient) -> None:
        """Catches malformed response models across every route at once."""
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        assert "/api/v1/documents" in response.json()["paths"]
