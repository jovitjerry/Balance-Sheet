"""Freeze the context every candidate will be given.

Built **once**, by the real Module 4 code, and written to
``reasoning_context.json``. The runner replays it byte-identically to every
model.

Freezing is the point. Retrieval is not what this benchmark compares, and
letting it re-run per candidate would leak embedding variance and Atlas
scheduling into what is supposed to be a reasoning score. It also makes the
benchmark reproducible without Atlas: the input becomes a stored artefact.

    python -m benchmarks.reasoning_context            # structured facts only
    python -m benchmarks.reasoning_context --with-text  # + retrieved notes

Only Q11 needs retrieved document text. Without ``--with-text`` its extract is
taken directly from the notes page via the real chunker, which is deterministic
and needs no embedding model; with it, the passage is chosen by real embedding
similarity. Both go through ``build_context``, so the rendered block is
identical in shape either way.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.core.schemas import (
    BalanceSheetDocument,
    BalanceSheetSection,
    DocumentStatus,
    EquationCheck,
    Evidence,
    EvidenceKind,
    ExtractedBalanceSheet,
    ExtractionStatus,
    IdentificationEvidence,
    IdentificationSignal,
    LineItem,
    Normalization,
    NormalizationMethod,
    NormalizationStatus,
    ParserKind,
    PreliminaryExtraction,
    SourceFile,
    SourcePage,
    SourceRef,
    StorageRef,
)
from app.modules.extraction.taxonomy import TAXONOMY_VERSION
from app.modules.insights.chunking import chunks_for
from app.modules.insights.context import build_context
from app.modules.insights.retrieval import ScoredChunk, to_evidence
from app.modules.insights.routing import route
from app.modules.insights.service import RAG_SPEC_VERSION, _template_for
from app.modules.insights.structured import facts_for
from app.modules.ratios.service import compute_ratios
from benchmarks.runner import BENCHMARKS

CASES = BENCHMARKS / "reasoning_cases.json"
FROZEN = BENCHMARKS / "reasoning_context.json"

DOCUMENT_ID = "652f1a2b3c4d5e6f70819200"

# Page 0 is the Balance Sheet, page 1 the notes. Only the notes carry prose, so
# only they can answer a policy question - which is the whole reason the text
# path exists at all.
_BALANCE_SHEET_PAGE = """Meridian Industries Limited
Balance Sheet as at 31 March 2026

ASSETS
Current Assets
Cash and cash equivalents 125,000
Trade receivables 280,000
Inventory 350,000
Other current assets 95,000
Total Current Assets 850,000
Non-Current Assets
Property, plant and equipment 1,200,000
Intangible assets 150,000
Other non-current assets 100,000
TOTAL ASSETS 2,300,000
"""


def load_cases() -> dict[str, Any]:
    return json.loads(CASES.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Building the document the real modules expect
# --------------------------------------------------------------------------


def _item(label: str, value: int, canonical: str, subsection: str | None, row: int) -> LineItem:
    """One normalized line item, as Module 2 would leave it."""
    return LineItem(
        label=label,
        value=Decimal(value),
        raw=f"{value:,}",
        subsection=subsection,
        source=SourceRef(page_index=0, row=row, column=1),
        status=ExtractionStatus.EXTRACTED,
        normalization=Normalization(
            canonical_label=canonical,
            status=NormalizationStatus.NORMALIZED,
            method=NormalizationMethod.DICTIONARY,
            confidence=1.0,
            taxonomy_version=TAXONOMY_VERSION,
            model=None,
            reason=None,
        ),
    )


def _section(total: int, items: list[LineItem], label: str) -> BalanceSheetSection:
    line_total = sum((i.value for i in items if i.value is not None), Decimal(0))
    return BalanceSheetSection(
        total=Decimal(total),
        total_label=label,
        total_raw=f"{total:,}",
        total_source=SourceRef(page_index=0, row=99, column=1),
        line_items=items,
        line_items_total=line_total,
        reconciliation_difference=Decimal(total) - line_total,
    )


def build_document(cases: dict[str, Any]) -> BalanceSheetDocument:
    """The analyzed document, exactly as Modules 1-3 would leave it.

    Figures come from ``reasoning_cases.json`` so ground truth lives in one
    place, and the ratios come from Module 3's real engine rather than being
    written down - a benchmark whose "correct" ratios were hand-typed could
    drift from the system it is testing.
    """
    sheet = cases["balance_sheet"]
    row = 1
    assets: list[LineItem] = []
    for group, subsection in (("current", "current"), ("non_current", "non_current")):
        for label, value, canonical in sheet["assets"][group]:
            assets.append(_item(label, value, canonical, subsection, row))
            row += 1

    liabilities: list[LineItem] = []
    for group, subsection in (("current", "current"), ("non_current", "non_current")):
        for label, value, canonical in sheet["liabilities"][group]:
            liabilities.append(_item(label, value, canonical, subsection, row))
            row += 1

    equity = [
        _item(label, value, canonical, None, row + offset)
        for offset, (label, value, canonical) in enumerate(sheet["equity"]["items"])
    ]

    extracted = ExtractedBalanceSheet(
        entity_name=sheet["entity"],
        period_label=sheet["period"],
        period_end_date=date(2026, 3, 31),
        currency=sheet["currency"],
        assets=_section(sheet["assets"]["total"], assets, "TOTAL ASSETS"),
        liabilities=_section(sheet["liabilities"]["total"], liabilities, "Total Liabilities"),
        equity=_section(sheet["equity"]["total"], equity, "Total Equity"),
        taxonomy_version=TAXONOMY_VERSION,
        normalization_summary={"normalized": len(assets) + len(liabilities) + len(equity)},
    )

    return BalanceSheetDocument(
        _id=DOCUMENT_ID,
        status=DocumentStatus.ANALYZED,
        source=SourceFile(
            filename="meridian.pdf",
            content_type="application/pdf",
            size_bytes=2048,
            sha256="f" * 64,
            ref=StorageRef(
                backend="local", key="ff/ff/x.pdf", size_bytes=2048,
                content_type="application/pdf",
            ),
        ),
        preliminary=PreliminaryExtraction(
            parser=ParserKind.PDF_TEXT,
            pages=[
                SourcePage(index=0, text=_BALANCE_SHEET_PAGE, page_width=612.0, page_height=792.0),
                SourcePage(index=1, text=cases["notes_page"], page_width=612.0, page_height=792.0),
            ],
        ),
        identification=IdentificationEvidence(
            is_balance_sheet=True, score=8, threshold=4,
            signals=[
                IdentificationSignal(
                    kind="title", text="Balance Sheet as at 31 March 2026",
                    weight=4, source=SourceRef(page_index=0, row=1),
                )
            ],
        ),
        extracted=extracted,
        ratios=compute_ratios(extracted),
        equation_check=EquationCheck(
            total_assets=Decimal(sheet["assets"]["total"]),
            total_liabilities=Decimal(sheet["liabilities"]["total"]),
            total_equity=Decimal(sheet["equity"]["total"]),
            expected=Decimal(sheet["liabilities"]["total"] + sheet["equity"]["total"]),
            difference=Decimal(0),
            tolerance_applied=Decimal(1),
            balanced=True,
        ),
    )


# --------------------------------------------------------------------------
# Freezing
# --------------------------------------------------------------------------


async def _extracts_for(
    document: BalanceSheetDocument, question: str, *, with_text: bool
) -> list[Evidence]:
    """Document passages for one question, through the real chunker.

    With ``--with-text`` the passage is chosen by real embedding similarity, so
    the frozen artefact reflects what production retrieval would actually
    surface. Without it, the notes chunk is taken directly - deterministic, and
    it needs no embedding model, which keeps the benchmark buildable on a
    machine that has only the generation model pulled.
    """
    chunks = [chunk for chunk in chunks_for(document) if chunk.page_index == 1]
    if not chunks:
        return []

    if not with_text:
        return to_evidence([ScoredChunk(chunk=chunks[0], score=1.0)])

    from app.core.config import get_settings
    from app.core.llm.embeddings import build_embedding_provider, cosine
    from app.modules.insights.retrieval import SIMILARITY_FLOOR, in_reading_order

    settings = get_settings()
    embeddings = build_embedding_provider(
        host=settings.ollama_host,
        model=settings.embedding_model,
        dimensions=settings.embedding_dim,
        timeout_s=settings.embedding_timeout_s,
    )
    vectors = await embeddings.embed([chunk.text for chunk in chunks])
    [query] = await embeddings.embed([question])

    scored = [
        ScoredChunk(chunk=chunk, score=cosine(query, vector))
        for chunk, vector in zip(chunks, vectors)
    ]
    kept = [entry for entry in scored if entry.score >= SIMILARITY_FLOOR]
    return to_evidence(in_reading_order(sorted(kept, key=lambda e: -e.score)[:5]))


async def freeze(*, with_text: bool) -> dict[str, Any]:
    """Build the frozen context for every question."""
    cases = load_cases()
    document = build_document(cases)

    frozen: dict[str, Any] = {
        "cases_version": cases["version"],
        "rag_spec_version": RAG_SPEC_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "retrieval": "embedding" if with_text else "deterministic",
        "ratios": {r.name: str(r.value) if r.value is not None else None
                   for r in document.ratios.ratios},
        "questions": {},
    }

    # Ratios must match what the case file claims, or the benchmark is testing a
    # different Balance Sheet from the one it documents.
    expected = cases["expected_ratios"]
    for name, value in frozen["ratios"].items():
        if expected.get(name) not in (None, value):
            raise SystemExit(
                f"Ratio mismatch for {name}: engine says {value}, "
                f"reasoning_cases.json says {expected[name]}."
            )

    for question in cases["questions"]:
        text = question["question"]
        decision = route(text, document=document)
        facts = facts_for(document, decision=decision)
        # Only the policy question needs prose; giving every question the notes
        # would change what is being measured elsewhere.
        extracts = (
            await _extracts_for(document, text, with_text=with_text)
            if question["category"] == "policy_narrative"
            else []
        )
        context = build_context(facts=facts, extracts=extracts)

        frozen["questions"][question["id"]] = {
            "question": text,
            "route": decision.route.value,
            "routed_reason": decision.reason,
            "refused_before_model": decision.route.value == "out_of_scope",
            "template": _template_name(decision, context),
            "context_text": context.text,
            "groundable_text": context.groundable,
            "citation_ids": list(context.citation_ids),
            "evidence": [e.model_dump(mode="json") for e in context.evidence],
        }

    return frozen


def _template_name(decision: Any, context: Any) -> str:
    """Which real Module 4 prompt this question selects."""
    from app.modules.insights import prompts

    template = _template_for(decision, context)
    for name in ("GROUNDED_QA", "RATIO_EXPLANATION", "STRUCTURED_FACT", "INSUFFICIENT_CONTEXT"):
        if template is getattr(prompts, name):
            return name
    return "UNKNOWN"  # pragma: no cover


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-text",
        action="store_true",
        help="Choose the retrieved passage by real embedding similarity "
        "(needs the embedding model pulled) instead of deterministically.",
    )
    args = parser.parse_args()

    frozen = await freeze(with_text=args.with_text)
    FROZEN.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")

    print(f"Froze {len(frozen['questions'])} questions -> {FROZEN.name}")
    print(f"  retrieval: {frozen['retrieval']}")
    for qid, entry in frozen["questions"].items():
        note = " (refused before the model)" if entry["refused_before_model"] else ""
        print(
            f"  {qid:4} {entry['route']:12} {entry['template']:20} "
            f"{len(entry['citation_ids']):2} tags{note}"
        )


if __name__ == "__main__":
    asyncio.run(main())
