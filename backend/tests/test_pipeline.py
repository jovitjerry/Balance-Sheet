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

    def test_only_ingest_is_built(self) -> None:
        """Module 1 is complete; Modules 2-4 have not been started."""
        states = {info.stage: info.state for info in STAGES}
        assert states[PipelineStage.INGEST] is StageState.IMPLEMENTED
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


class TestModuleBoundaries:
    """Module 1 must not have absorbed work that belongs to Module 2."""

    def test_module_1_holds_no_line_item_vocabulary(self) -> None:
        """anchors.py is total lines and section headers - nothing more.

        The moment a line-item synonym appears there, Module 2's vocabulary has
        a competing half-copy in Module 1 that will drift out of step with it.
        """
        from app.modules.ingestion import anchors

        every_phrase = " ".join(
            phrase
            for group in (
                anchors.TITLE_PHRASES,
                anchors.ASSETS_HEADERS,
                anchors.LIABILITIES_HEADERS,
                anchors.EQUITY_HEADERS,
                anchors.COMBINED_HEADERS,
                anchors.TOTAL_ASSETS_PHRASES,
                anchors.TOTAL_LIABILITIES_PHRASES,
                anchors.TOTAL_EQUITY_PHRASES,
                anchors.COMBINED_TOTAL_PHRASES,
            )
            for phrase in group
        ).lower()

        for line_item_term in (
            "receivable",
            "payable",
            "inventor",
            "cash",
            "goodwill",
            "depreciation",
            "borrowing",
            "provision",
            "prepaid",
            "debtor",
            "creditor",
        ):
            assert line_item_term not in every_phrase, (
                f"{line_item_term!r} is line-item vocabulary and belongs to "
                "Module 2, not to Module 1's anchors"
            )

    def test_module_1_does_not_import_modules_2_to_4(self) -> None:
        """The dependency runs one way. Module 1 knows nothing downstream.

        Read from the parsed import statements rather than by searching the
        text, so that a docstring *describing* the boundary - which several of
        these files carry - is not mistaken for a breach of it.
        """
        import ast
        from pathlib import Path

        import app.modules.ingestion as ingestion

        forbidden = ("app.modules.extraction", "app.modules.ratios", "app.modules.insights")
        for path in Path(ingestion.__path__[0]).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)

            for name in imported:
                assert not name.startswith(forbidden), (
                    f"{path.name} imports {name} - Module 1 must not depend on "
                    "a later module"
                )
