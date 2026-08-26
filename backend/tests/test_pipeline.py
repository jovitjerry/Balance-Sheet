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

    def test_the_built_modules_are_the_ones_that_say_they_are(self) -> None:
        """Modules 1 and 2 are complete; Modules 3-4 have not been started."""
        states = {info.stage: info.state for info in STAGES}
        assert states[PipelineStage.INGEST] is StageState.IMPLEMENTED
        assert states[PipelineStage.EXTRACT] is StageState.IMPLEMENTED
        assert states[PipelineStage.RATIOS] is StageState.NOT_IMPLEMENTED
        assert states[PipelineStage.INSIGHTS] is StageState.NOT_IMPLEMENTED


class TestRunPipeline:
    async def test_it_stops_at_the_first_unbuilt_module_and_says_why(self) -> None:
        """Starting after EXTRACT, the next gap is Module 3."""
        result = await run_pipeline(_document(), start_after=PipelineStage.EXTRACT)

        assert result.stopped_at is PipelineStage.RATIOS
        assert result.completed == []
        assert result.reason is not None
        assert "Module 3" in result.reason
        assert "not implemented" in result.reason

    async def test_it_does_not_report_success_it_did_not_achieve(self) -> None:
        result = await run_pipeline(_document(), start_after=PipelineStage.EXTRACT)
        assert result.document.extracted is None

    async def test_extraction_without_a_provider_refuses_rather_than_pretending(
        self,
    ) -> None:
        """No model wired in is a wiring fault, not an empty Balance Sheet."""
        with pytest.raises(StageNotImplemented, match="provider"):
            await run_pipeline(_document())


class TestUnimplementedModules:
    """Every unbuilt module raises StageNotImplemented, never a fake result."""

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

    def test_core_does_not_import_any_module(self) -> None:
        """``core`` is the contract between modules, so it depends on none of them.

        This is what makes shared code shareable. ``core/lines.py`` holds the
        line view and the selected-period column logic that Module 1 and
        Module 2 both read; the moment ``core`` reaches back into a module
        package, that shared layer becomes one module's private property with
        a second copy waiting to be written.

        Two files are exempt, and only two: ``deps.py``, which hands the
        assembled application's parts to a request, and ``pipeline.py``, whose
        stated job is to be the orchestration boundary between modules. An
        orchestrator that may not name what it orchestrates is not one. Both
        are composition points rather than shared libraries - nothing imports
        them but the application itself - so exempting them leaves the
        invariant that matters intact: the code both modules *use* stays free
        of either.
        """
        import ast
        from pathlib import Path

        import app.core as core

        composition_points = {"deps.py", "pipeline.py"}

        for path in sorted(Path(core.__path__[0]).rglob("*.py")):
            if path.name in composition_points:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)

            for name in imported:
                assert not name.startswith("app.modules"), (
                    f"core/{path.name} imports {name} - core must not depend on "
                    "any module"
                )
