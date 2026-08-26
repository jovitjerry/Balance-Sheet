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

from app.core.errors import StageNotImplemented
from app.core.schemas import BalanceSheetDocument


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

    @property
    def implemented(self) -> bool:
        return self.state is not StageState.NOT_IMPLEMENTED


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
        "Full Data Extraction & Normalization",
        StageState.NOT_IMPLEMENTED,
    ),
    StageInfo(
        PipelineStage.RATIOS,
        3,
        "Deterministic Financial Ratio Engine",
        StageState.NOT_IMPLEMENTED,
    ),
    StageInfo(
        PipelineStage.INSIGHTS,
        4,
        "LLM + RAG insight generation",
        StageState.NOT_IMPLEMENTED,
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


async def run_pipeline(
    document: BalanceSheetDocument,
    *,
    start_after: PipelineStage = PipelineStage.INGEST,
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

        if not info.implemented:
            result.stopped_at = info.stage
            result.reason = (
                f"Module {info.module} ({info.description}) is not implemented yet."
            )
            return result

        await _run_stage(info, document)  # pragma: no cover - no stage qualifies yet
        result.completed.append(info.stage)

    return result


async def _run_stage(info: StageInfo, document: BalanceSheetDocument) -> None:
    """Dispatch one stage. Stages are wired in as their modules are built."""
    raise StageNotImplemented(
        f"Stage {info.stage.value!r} is registered but has no implementation wired in."
    )


__all__ = [
    "STAGES",
    "STAGES_BY_NAME",
    "PipelineResult",
    "PipelineStage",
    "StageInfo",
    "StageState",
    "run_pipeline",
]
