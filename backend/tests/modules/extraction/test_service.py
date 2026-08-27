"""The Module 2 stage end to end, and what it does when the model is missing.

Pure unit tests - no cluster, no Ollama. The provider is a stub, which is the
whole point of the seam: the behaviour that matters most here is what happens
when the model *cannot* be reached, and that is not something a live model
gives you a reliable way to produce.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.core.errors import StageNotImplemented, StorageError
from app.core.llm.base import LlmUnavailable
from app.core.pipeline import PipelineStage, StageContext, run_pipeline
from app.core.schemas import (
    BalanceSheetDocument,
    DocumentStatus,
    NormalizationMethod,
    NormalizationStatus,
)
from app.core.storage import LocalFileStorage, key_for
from app.modules.extraction import taxonomy
from app.modules.extraction.service import extract
from app.modules.ingestion.service import PRELIMINARY_SUFFIX
from tests.modules.extraction.fixtures import (
    FixedProvider,
    OfflineProvider,
    validated_document,
)
from tests.modules.ingestion.fixtures import (
    side_by_side_balance_sheet_pdf,
    simple_balance_sheet_pdf,
    simple_balance_sheet_xlsx,
)


def all_items(extracted):
    return [
        item
        for section in (extracted.assets, extracted.liabilities, extracted.equity)
        for item in section.line_items
    ]


class TestTheStage:
    async def test_it_fills_in_the_line_items_module_1_left_empty(
        self, settings: Settings
    ) -> None:
        document = await validated_document(simple_balance_sheet_pdf(), settings)
        assert document.extracted.assets.line_items == []

        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        assert len(extracted.assets.line_items) == 3
        assert len(extracted.liabilities.line_items) == 2
        assert len(extracted.equity.line_items) == 2

    async def test_module_1s_totals_are_carried_through_untouched(
        self, settings: Settings
    ) -> None:
        """Module 2 adds to the sections. It does not restate them."""
        document = await validated_document(simple_balance_sheet_pdf(), settings)
        before = document.extracted.assets

        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        assert extracted.assets.total == before.total
        assert extracted.assets.total_label == before.total_label
        assert extracted.assets.total_source == before.total_source

    async def test_the_taxonomy_version_is_stamped_on_the_result(
        self, settings: Settings
    ) -> None:
        document = await validated_document(simple_balance_sheet_pdf(), settings)
        extracted = await extract(document, provider=OfflineProvider(), settings=settings)
        assert extracted.taxonomy_version == taxonomy.TAXONOMY_VERSION

    async def test_a_summary_says_how_much_needs_a_human(
        self, settings: Settings
    ) -> None:
        document = await validated_document(simple_balance_sheet_pdf(), settings)
        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        assert sum(extracted.normalization_summary.values()) == len(all_items(extracted))


class TestReconciliation:
    async def test_the_line_items_are_summed_beside_the_total(
        self, settings: Settings
    ) -> None:
        document = await validated_document(side_by_side_balance_sheet_pdf(), settings)
        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        assert extracted.assets.line_items_total == Decimal("2300000")
        assert extracted.liabilities.line_items_total == Decimal("1350000")
        assert extracted.equity.line_items_total == Decimal("950000")

    async def test_the_difference_from_module_1s_total_is_recorded(
        self, settings: Settings
    ) -> None:
        document = await validated_document(side_by_side_balance_sheet_pdf(), settings)
        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        assert extracted.assets.reconciliation_difference == Decimal(0)

    async def test_a_shortfall_is_reported_not_hidden(self, settings: Settings) -> None:
        """Subtotals and rounding make a gap ordinary. Concealing one is not.

        This is a diagnostic, never a rejection - and never the accounting
        equation, which Module 1 checked on the printed totals.
        """
        document = await validated_document(simple_balance_sheet_pdf(), settings)
        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        difference = extracted.assets.total - extracted.assets.line_items_total
        assert extracted.assets.reconciliation_difference == difference


class TestTraceability:
    async def test_every_item_keeps_its_printed_label_and_figure(
        self, settings: Settings
    ) -> None:
        document = await validated_document(simple_balance_sheet_pdf(), settings)
        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        item = next(
            i for i in all_items(extracted) if i.label == "Property, plant and equipment"
        )
        assert item.raw == "50,000"
        assert item.value == Decimal("50000")

    async def test_every_item_points_back_at_the_document(
        self, settings: Settings
    ) -> None:
        document = await validated_document(simple_balance_sheet_pdf(), settings)
        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        for item in all_items(extracted):
            assert item.source is not None
            assert item.source.page_index == 0
            assert item.source.row is not None

    async def test_a_workbook_item_points_at_its_sheet(self, settings: Settings) -> None:
        document = await validated_document(
            simple_balance_sheet_xlsx(), settings, xlsx=True
        )
        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        assert all(item.source.sheet_name == "Balance Sheet" for item in all_items(extracted))

    async def test_the_original_label_is_never_replaced_by_the_canonical_one(
        self, settings: Settings
    ) -> None:
        document = await validated_document(simple_balance_sheet_pdf(), settings)
        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        item = next(i for i in all_items(extracted) if i.label == "Cash and cash equivalents")
        assert item.label == "Cash and cash equivalents"
        assert item.normalization.canonical_label == "cash_and_cash_equivalents"

    async def test_the_deciding_model_is_recorded_on_the_item(
        self, settings: Settings
    ) -> None:
        document = await validated_document(simple_balance_sheet_pdf(), settings)
        extracted = await extract(
            document, provider=FixedProvider("inventory", model="qwen3:4b"), settings=settings
        )

        decided = [
            item
            for item in all_items(extracted)
            if item.normalization.method is NormalizationMethod.LLM
        ]
        assert decided, "no label reached the model"
        assert all(item.normalization.model == "qwen3:4b" for item in decided)


class TestWithoutOllama:
    """The half of Module 2 that never needed a model still runs."""

    async def test_extraction_completes_with_the_model_offline(
        self, settings: Settings
    ) -> None:
        document = await validated_document(side_by_side_balance_sheet_pdf(), settings)
        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        assert len(all_items(extracted)) == 14
        assert all(item.value is not None for item in all_items(extracted))

    async def test_canonical_wording_still_normalizes(self, settings: Settings) -> None:
        """Most of a well-formed sheet resolves without a model at all."""
        document = await validated_document(side_by_side_balance_sheet_pdf(), settings)
        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        assert extracted.normalization_summary.get("normalized") == 14

    async def test_an_unresolvable_label_is_marked_not_guessed(
        self, settings: Settings
    ) -> None:
        document = await validated_document(simple_balance_sheet_pdf(), settings)
        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        unresolved = [
            item
            for item in all_items(extracted)
            if item.normalization.status is NormalizationStatus.UNAVAILABLE
        ]
        assert unresolved, "expected 'Inventories' to need the model"
        for item in unresolved:
            assert item.normalization.canonical_label is None
            assert item.normalization.method is NormalizationMethod.UNAVAILABLE
            # The line itself survives intact - it is the label that is pending.
            assert item.value is not None
            assert item.label

    async def test_llm_required_turns_that_into_a_refusal(
        self, settings: Settings
    ) -> None:
        """For CI and demos, where a quietly un-normalized document is a false green."""
        document = await validated_document(simple_balance_sheet_pdf(), settings)
        strict = settings.model_copy(update={"llm_required": True})

        with pytest.raises(LlmUnavailable) as caught:
            await extract(document, provider=OfflineProvider(), settings=strict)

        assert "LLM_REQUIRED" in str(caught.value)


class TestThroughThePipeline:
    async def test_the_stage_runs_and_sets_the_status(self, settings: Settings) -> None:
        document = await validated_document(simple_balance_sheet_pdf(), settings)

        result = await run_pipeline(
            document,
            start_after=PipelineStage.INGEST,
            context=StageContext(llm=OfflineProvider(), settings=settings),
        )

        assert PipelineStage.EXTRACT in result.completed
        assert result.document.extracted.assets.line_items

    async def test_module_2_itself_computes_no_ratio(self, settings: Settings) -> None:
        """The boundary: Module 2 produces what Module 3 needs and stops there."""
        document = await validated_document(simple_balance_sheet_pdf(), settings)

        extracted = await extract(document, provider=OfflineProvider(), settings=settings)

        assert extracted.assets.line_items
        assert document.ratios is None
        assert not hasattr(extracted, "ratios")

    async def test_it_then_stops_at_module_4(self, settings: Settings) -> None:
        """Modules 2 and 3 both run; Module 4 is the next real gap."""
        document = await validated_document(simple_balance_sheet_pdf(), settings)

        result = await run_pipeline(
            document, context=StageContext(llm=OfflineProvider(), settings=settings)
        )

        assert result.completed == [PipelineStage.EXTRACT, PipelineStage.RATIOS]
        assert result.document.status is DocumentStatus.ANALYZED
        assert result.document.ratios is not None
        assert result.stopped_at is PipelineStage.INSIGHTS
        assert "Module 4" in result.reason

    async def test_a_stage_with_no_provider_refuses(self, settings: Settings) -> None:
        document = await validated_document(simple_balance_sheet_pdf(), settings)
        with pytest.raises(StageNotImplemented):
            await run_pipeline(document, context=StageContext(settings=settings))


class TestAnOffloadedPreliminaryExtraction:
    """A document whose raw extraction was too large to inline still extracts.

    Module 1 spills the raw payload to file storage when it approaches
    MongoDB's document cap, leaving only a ``preliminary_ref``. Reading that
    back was never implemented, so this path failed with "the document has no
    preliminary extraction to work from" - on a document that had one all
    along. These tests pin the repair.
    """

    async def test_it_extracts_from_the_offloaded_payload(
        self, settings: Settings, storage: LocalFileStorage
    ) -> None:
        inline = await validated_document(side_by_side_balance_sheet_pdf(), settings)
        offloaded = await _offload(inline, storage)

        assert offloaded.preliminary is None  # exactly as it comes back from Mongo

        extracted = await extract(
            offloaded, provider=OfflineProvider(), settings=settings, storage=storage
        )

        assert extracted.assets.line_items
        assert {item.label for item in extracted.assets.line_items} >= {
            "Cash and cash equivalents",
            "Inventory",
        }

    async def test_it_matches_the_inline_result_exactly(
        self, settings: Settings, storage: LocalFileStorage
    ) -> None:
        """Where the payload was stored must not change a single figure."""
        inline = await validated_document(side_by_side_balance_sheet_pdf(), settings)
        offloaded = await _offload(inline, storage)

        from_inline = await extract(
            inline, provider=OfflineProvider(), settings=settings
        )
        from_storage = await extract(
            offloaded, provider=OfflineProvider(), settings=settings, storage=storage
        )

        assert from_inline.model_dump() == from_storage.model_dump()

    async def test_without_a_file_store_it_says_so_rather_than_reporting_nothing(
        self, settings: Settings, storage: LocalFileStorage
    ) -> None:
        """The failure that made this bug invisible: an empty answer, not an error."""
        inline = await validated_document(side_by_side_balance_sheet_pdf(), settings)
        offloaded = await _offload(inline, storage)

        with pytest.raises(StorageError, match="file store"):
            await extract(offloaded, provider=OfflineProvider(), settings=settings)


async def _offload(
    document: BalanceSheetDocument, storage: LocalFileStorage
) -> BalanceSheetDocument:
    """The document as Module 1 leaves it when the payload took the spill path."""
    assert document.preliminary is not None
    ref = await storage.save(
        json.dumps(
            document.preliminary.model_dump(mode="python", exclude_none=True),
            default=str,
        ).encode("utf-8"),
        key=key_for(document.source.sha256, PRELIMINARY_SUFFIX),
        content_type="application/json",
    )
    return document.model_copy(update={"preliminary": None, "preliminary_ref": ref})


class TestIdempotence:
    async def test_running_twice_gives_the_same_answer(self, settings: Settings) -> None:
        """An academic result that moves between runs is not a result."""
        document = await validated_document(side_by_side_balance_sheet_pdf(), settings)

        first = await extract(document, provider=OfflineProvider(), settings=settings)
        second = await extract(document, provider=OfflineProvider(), settings=settings)

        assert first.model_dump() == second.model_dump()
