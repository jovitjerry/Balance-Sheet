"""The orchestration boundary between modules.

This defines the order modules run in and nothing more. It deliberately does
**not** pretend Modules 2-4 exist: an unimplemented stage stops the run
cleanly and says so, rather than raising something opaque or - far worse -
reporting success it did not achieve.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, ConfigDict

from typing import Any

from app.core.errors import StageNotImplemented
from app.core.schemas import BalanceSheetDocument, DocumentStatus


class PipelineStage(str, Enum):
    INGEST = "ingest"
    EXTRACT = "extract"
    RATIOS = "ratios"
    INSIGHTS = "insights"


class StageState(str, Enum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    NOT_IMPLEMENTED = "not_implemented"


@dataclass(frozen=True)
class StageInfo:
    stage: PipelineStage
    module: int
    description: str
    state: StageState
    automatic: bool = True
    """Whether an upload runs this stage.

    Module 4 is built, but it is **request-driven**: it answers a question
    somebody asks, so there is nothing for it to do when a document arrives.
    Marking it ``NOT_IMPLEMENTED`` would be untrue, and running it at upload
    would mean generating an answer to a question nobody asked - at the cost of
    a model call on every upload. This flag is how the registry says "built,
    but not part of the upload pipeline" instead of having to lie either way.
    """

    @property
    def implemented(self) -> bool:
        return self.state is not StageState.NOT_IMPLEMENTED

    @property
    def trigger(self) -> str:
        return "upload" if self.automatic else "on_request"


STAGES: tuple[StageInfo, ...] = (
    StageInfo(
        PipelineStage.INGEST,
        1,
        "Upload & Validation (file and content validation, PDF/Excel parsing, "
        "OCR for scanned pages, Balance Sheet identification, current-period "
        "selection, section totals and the accounting-equation check)",
        StageState.IMPLEMENTED,
    ),
    StageInfo(
        PipelineStage.EXTRACT,
        2,
        "Full Data Extraction & Normalization (complete line-item extraction, "
        "section and subsection structure, and terminology mapping onto the "
        "canonical vocabulary using a local language model)",
        StageState.IMPLEMENTED,
    ),
    StageInfo(
        PipelineStage.RATIOS,
        3,
        "Deterministic Financial Ratio Engine (Balance Sheet liquidity and "
        "leverage ratios, computed in Python from the normalized line items)",
        StageState.IMPLEMENTED,
    ),
    StageInfo(
        PipelineStage.INSIGHTS,
        4,
        "Grounded Q&A over the processed document (hybrid retrieval: exact "
        "structured facts plus semantic search of the document's own text, "
        "answered by a local model that may explain figures but never compute "
        "them). Request-driven - ask a question rather than wait for an upload",
        StageState.IMPLEMENTED,
        automatic=False,
    ),
)

STAGES_BY_NAME: dict[PipelineStage, StageInfo] = {info.stage: info for info in STAGES}


class PipelineResult(BaseModel):
    """What a run actually accomplished.

    ``stopped_at`` being set is not a failure - it is the honest report that
    the next module has not been built.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    document: BalanceSheetDocument
    completed: list[PipelineStage] = []
    stopped_at: PipelineStage | None = None
    reason: str | None = None


@dataclass(frozen=True)
class StageContext:
    """What the stages need from outside themselves.

    Passed in rather than reached for, so a pipeline run in a test is wired to
    a stub provider the same way the application wires it to Ollama.
    """

    llm: Any | None = None
    settings: Any | None = None
    # Needed only for a document whose raw extraction was large enough that
    # Module 1 spilled it to the file store rather than inline it.
    storage: Any | None = None


async def run_pipeline(
    document: BalanceSheetDocument,
    *,
    start_after: PipelineStage = PipelineStage.INGEST,
    context: StageContext | None = None,
) -> PipelineResult:
    """Run the stages following ``start_after``, stopping at the first gap.

    The document is returned exactly as far along as it genuinely got.
    """
    result = PipelineResult(document=document)
    reached_start = False

    for info in STAGES:
        if not reached_start:
            if info.stage is start_after:
                reached_start = True
            continue

        if not info.automatic:
            # Built, but nothing for it to do here. Reported as the point the
            # automatic run finished rather than as a gap - "stopped" would
            # read as a failure, and there is none.
            result.stopped_at = info.stage
            result.reason = (
                f"Module {info.module} is request-driven and does not run at "
                "upload; it answers questions about the stored document."
            )
            return result

        if not info.implemented:
            result.stopped_at = info.stage
            result.reason = (
                f"Module {info.module} ({info.description}) is not implemented yet."
            )
            return result

        await _run_stage(info, document, context or StageContext())
        result.completed.append(info.stage)

    return result


async def _run_stage(
    info: StageInfo, document: BalanceSheetDocument, context: StageContext
) -> None:
    """Dispatch one stage. Stages are wired in as their modules are built.

    The imports are local to this function on purpose. Importing Module 2 at
    the top of a ``core`` file would make the shared layer depend on a module,
    which is the thing ``core`` exists not to do; here the dependency is
    confined to the one function whose job is dispatch.
    """
    if info.stage is PipelineStage.EXTRACT:
        from app.modules.extraction.service import extract

        if context.llm is None:
            raise StageNotImplemented(
                "The extraction stage needs a language-model provider."
            )
        document.extracted = await extract(
            document,
            provider=context.llm,
            settings=context.settings,
            storage=context.storage,
        )
        document.status = DocumentStatus.EXTRACTED
        return

    if info.stage is PipelineStage.RATIOS:
        from app.modules.ratios.service import compute_ratios

        if document.extracted is None:
            raise StageNotImplemented(
                "The ratio stage needs an extracted Balance Sheet."
            )
        # No provider and no settings are passed, deliberately. Module 3 needs
        # neither, and handing it either would weaken the constraint that keeps
        # financial calculation out of a language model's reach.
        document.ratios = compute_ratios(
            document.extracted,
            scale_label=document.units.scale_label if document.units else None,
        )
        document.status = DocumentStatus.ANALYZED
        return

    raise StageNotImplemented(
        f"Stage {info.stage.value!r} is registered but has no implementation wired in."
    )


__all__ = [
    "STAGES",
    "STAGES_BY_NAME",
    "PipelineResult",
    "PipelineStage",
    "StageContext",
    "StageInfo",
    "StageState",
    "run_pipeline",
]
