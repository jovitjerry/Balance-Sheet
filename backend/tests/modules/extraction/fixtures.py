"""Building a Module 1 document to hand to Module 2.

Built by running the real Module 1 code over a real generated file rather than
by hand-assembling a document, so these tests consume exactly what the pipeline
produces - including the parts that are easy to get subtly wrong by hand, like
the selected period and the section totals' source references.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.core.llm.base import LlmResult
from app.core.schemas import BalanceSheetDocument
from app.modules.ingestion.identification import (
    detect_units,
    is_balance_sheet,
    locate_totals,
    select_period,
)
from app.modules.ingestion.parsing import parse
from app.modules.ingestion.service import _extracted_from
from app.modules.ingestion.validation import UploadKind
from tests.modules.ingestion.test_parsing import PDF_SOURCE, XLSX_SOURCE


async def validated_document(
    data: bytes, settings: Settings, *, xlsx: bool = False
) -> BalanceSheetDocument:
    """A document exactly as Module 1 leaves it: totals located, nothing more."""
    source = XLSX_SOURCE if xlsx else PDF_SOURCE
    kwargs: dict[str, Any] = {"kind": UploadKind.XLSX} if xlsx else {}
    preliminary = await parse(data, source, settings=settings, **kwargs)

    period = select_period(preliminary)
    units = detect_units(preliminary)
    totals = locate_totals(preliminary, period=period)

    return BalanceSheetDocument(
        source=source,
        preliminary=preliminary,
        period=period,
        units=units,
        identification=is_balance_sheet(preliminary),
        extracted=_extracted_from(totals, period, units),
    )


class OfflineProvider:
    """A provider that is simply not there - Ollama not installed, or stopped."""

    name = "offline"
    model = "none"

    def available(self) -> bool:
        return False

    async def complete_json(self, **kwargs: Any) -> LlmResult:  # pragma: no cover
        raise AssertionError("an unavailable provider must never be called")


class FixedProvider:
    """A provider that answers every label with the same canonical category."""

    name = "fixed"

    def __init__(self, canonical: str, *, model: str = "test-model") -> None:
        self.model = model
        self._canonical = canonical
        self.calls = 0

    def available(self) -> bool:
        return True

    async def complete_json(self, **kwargs: Any) -> LlmResult:
        self.calls += 1
        return LlmResult(
            payload={
                "reasoning": "fixed answer",
                "canonical_label": self._canonical,
                "confidence": 0.99,
            },
            model=self.model,
        )


__all__ = ["FixedProvider", "OfflineProvider", "validated_document"]
