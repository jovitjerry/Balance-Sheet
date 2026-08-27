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
        """Modules 1-3 are complete; Module 4 has not been started."""
        states = {info.stage: info.state for info in STAGES}
        assert states[PipelineStage.INGEST] is StageState.IMPLEMENTED
        assert states[PipelineStage.EXTRACT] is StageState.IMPLEMENTED
        assert states[PipelineStage.RATIOS] is StageState.IMPLEMENTED
        assert states[PipelineStage.INSIGHTS] is StageState.NOT_IMPLEMENTED


class TestRunPipeline:
    async def test_it_stops_at_the_first_unbuilt_module_and_says_why(self) -> None:
        """Starting after RATIOS, the next gap is Module 4."""
        result = await run_pipeline(_document(), start_after=PipelineStage.RATIOS)

        assert result.stopped_at is PipelineStage.INSIGHTS
        assert result.completed == []
        assert result.reason is not None
        assert "Module 4" in result.reason
        assert "not implemented" in result.reason

    async def test_it_does_not_report_success_it_did_not_achieve(self) -> None:
        result = await run_pipeline(_document(), start_after=PipelineStage.RATIOS)
        assert result.document.ratios is None

    async def test_the_ratio_stage_refuses_a_document_module_2_never_touched(
        self,
    ) -> None:
        """Ratios computed from nothing would be seven fabricated numbers."""
        with pytest.raises(StageNotImplemented, match="extracted Balance Sheet"):
            await run_pipeline(_document(), start_after=PipelineStage.EXTRACT)

    async def test_extraction_without_a_provider_refuses_rather_than_pretending(
        self,
    ) -> None:
        """No model wired in is a wiring fault, not an empty Balance Sheet."""
        with pytest.raises(StageNotImplemented, match="provider"):
            await run_pipeline(_document())


class TestUnimplementedModules:
    """Every unbuilt module raises StageNotImplemented, never a fake result."""

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


def _imports_of(package: object) -> dict[str, list[str]]:
    """Every module name imported by each file of a package.

    Read from the parsed import statements rather than by searching the text,
    so a docstring *describing* a boundary is not mistaken for a breach of it -
    which matters here, because Module 3's docstrings talk about the LLM at
    some length in order to say it is not involved.
    """
    import ast
    from pathlib import Path

    found: dict[str, list[str]] = {}
    for path in sorted(Path(package.__path__[0]).glob("*.py")):  # type: ignore[attr-defined]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        found[path.name] = imported
    return found


class TestModule3IsDeterministic:
    """The ratio engine's constraints, made structural rather than intended.

    "Financial calculations are never delegated to the LLM" is the project's
    central rule, and Module 2's own Q&A benchmark showed why: three of four
    candidate models made arithmetic errors on a Balance Sheet containing
    fifteen numbers. A rule that important should not rest on everyone
    remembering it.
    """

    def test_it_cannot_reach_a_language_model(self) -> None:
        import app.modules.ratios as ratios

        forbidden = ("app.core.llm", "httpx", "ollama", "app.modules.insights")
        for filename, imported in _imports_of(ratios).items():
            for name in imported:
                assert not name.startswith(forbidden), (
                    f"ratios/{filename} imports {name} - Module 3 computes in "
                    "Python and must have no path to a model"
                )

    def test_it_performs_no_io(self) -> None:
        """Pure means pure: no database, no file store, no filesystem."""
        import app.modules.ratios as ratios

        forbidden = ("pymongo", "bson", "app.core.db", "app.core.storage", "pathlib")
        for filename, imported in _imports_of(ratios).items():
            for name in imported:
                assert not name.startswith(forbidden), (
                    f"ratios/{filename} imports {name} - compute_ratios is pure"
                )

    def test_compute_ratios_is_synchronous_and_takes_no_dependencies(self) -> None:
        import inspect

        from app.modules.ratios.service import compute_ratios

        assert not inspect.iscoroutinefunction(compute_ratios)
        parameters = set(inspect.signature(compute_ratios).parameters)
        assert parameters == {"sheet", "scale_label"}, (
            "a db handle, provider or settings object in this signature would "
            "make the purity constraint a matter of habit rather than of type"
        )

    def test_module_3_does_not_import_module_4(self) -> None:
        """The dependency still runs one way: downstream never reaches forward."""
        import app.modules.ratios as ratios

        for filename, imported in _imports_of(ratios).items():
            for name in imported:
                assert not name.startswith("app.modules.insights"), filename

    def test_module_2_does_not_import_module_3(self) -> None:
        import app.modules.extraction as extraction

        for filename, imported in _imports_of(extraction).items():
            for name in imported:
                assert not name.startswith("app.modules.ratios"), filename

    def test_module_3_holds_no_terminology_of_its_own(self) -> None:
        """Synonyms stay in Module 2. Module 3 names canonical concepts only.

        "Trade Debtors" appearing here would mean the vocabulary had grown a
        second half-copy - the same trap ``anchors.py`` is guarded against.
        """
        from app.modules.extraction import taxonomy
        from app.modules.ratios import definitions

        canonical = set(taxonomy.labels())
        for definition in definitions.DEFINITIONS:
            for spec in (definition.left, definition.right):
                named = set(spec.include) | set(spec.subtract)
                if spec.base is not None:
                    named |= set(spec.base.include) | set(spec.base.subtract)
                assert named <= canonical, f"{definition.name} names a non-canonical label"
