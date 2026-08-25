"""The pipeline must be honest about what is not built yet."""

from __future__ import annotations

import pytest

from app.core.errors import StageNotImplemented
from app.core.pipeline import STAGES, PipelineStage, StageState, run_pipeline
from app.core.schemas import BalanceSheetDocument, SourceFile, StorageRef


def _document() -> BalanceSheetDocument:
    return BalanceSheetDocument(
        source=SourceFile(
            filename="sheet.pdf",
            content_type="application/pdf",
            size_bytes=1,
            sha256="b" * 64,
            ref=StorageRef(
                backend="local", key="bb/bb/x.pdf", size_bytes=1, content_type="application/pdf"
            ),
        )
    )


class TestStageRegistry:
    def test_stages_run_in_module_order(self) -> None:
        assert [info.module for info in STAGES] == [1, 2, 3, 4]

    def test_only_ingest_is_partially_built(self) -> None:
        states = {info.stage: info.state for info in STAGES}
        assert states[PipelineStage.INGEST] is StageState.PARTIAL
        assert states[PipelineStage.EXTRACT] is StageState.NOT_IMPLEMENTED
        assert states[PipelineStage.RATIOS] is StageState.NOT_IMPLEMENTED
        assert states[PipelineStage.INSIGHTS] is StageState.NOT_IMPLEMENTED


class TestRunPipeline:
    async def test_it_stops_at_extract_and_says_why(self) -> None:
        result = await run_pipeline(_document())
        assert result.stopped_at is PipelineStage.EXTRACT
        assert result.completed == []
        assert result.reason is not None
        assert "Module 2" in result.reason
        assert "not implemented" in result.reason

    async def test_it_does_not_report_success_it_did_not_achieve(self) -> None:
        result = await run_pipeline(_document())
        assert result.document.extracted is None
        assert result.document.equation_check is None


class TestUnimplementedModules:
    """Every unbuilt module raises StageNotImplemented, never a fake result."""

    async def test_extraction(self) -> None:
        from app.modules.extraction.service import extract

        with pytest.raises(StageNotImplemented, match="Module 2"):
            await extract(_document())

    def test_ratios(self) -> None:
        from app.modules.ratios.service import compute_ratios

        with pytest.raises(StageNotImplemented, match="Module 3"):
            compute_ratios(None)  # type: ignore[arg-type]

    async def test_insights(self) -> None:
        from app.modules.insights.service import explain

        with pytest.raises(StageNotImplemented, match="Module 4"):
            await explain(_document())

    async def test_module_1_parsing(self) -> None:
        from app.modules.ingestion.parsing import parse

        with pytest.raises(StageNotImplemented, match="Module 1"):
            await parse(b"", _document().source)

    def test_module_1_identification(self) -> None:
        from app.modules.ingestion.identification import is_balance_sheet

        with pytest.raises(StageNotImplemented, match="Module 1"):
            is_balance_sheet(None)  # type: ignore[arg-type]
