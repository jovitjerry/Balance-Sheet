from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any
from app.core.llm.base import LlmProvider, LlmUnavailable
from app.core.schemas import NormalizationMethod, NormalizationStatus
from app.core.text import normalise
from app.modules.extraction import aliases, taxonomy
from app.modules.extraction.prompts import build_prompt
from app.modules.extraction.schema import response_schema
from app.modules.extraction.taxonomy import Section, Subsection
logger = logging.getLogger(__name__)
DEFAULT_CONFIDENCE_FLOOR = 0.5
_OPTIONS: dict[str, Any] = {'temperature': 0}

@dataclass(frozen=True)
class NormalizationOutcome:
    canonical_label: str | None
    status: NormalizationStatus
    method: NormalizationMethod
    taxonomy_version: str
    confidence: float | None = None
    model: str | None = None
    reason: str | None = None

class Normalizer:

    def __init__(self, *, provider: LlmProvider, confidence_floor: float=DEFAULT_CONFIDENCE_FLOOR, retries: int=1) -> None:
        self._provider = provider
        self._floor = confidence_floor
        self._retries = retries
        self._cache: dict[tuple[str, str, str], NormalizationOutcome] = {}
        self._unusable = False

    async def normalize(self, label: str, *, section: Section, subsection: Subsection | None, neighbours: tuple[str, ...]=(), currency: str | None=None) -> NormalizationOutcome:
        if (canonical := aliases.lookup(label)):
            return self._resolved(canonical, NormalizationMethod.DICTIONARY)
        key = self._cache_key(label, section, subsection)
        if (cached := self._cache.get(key)) is not None:
            return _as_cached(cached)
        outcome = await self._ask(label, section=section, subsection=subsection, neighbours=neighbours, currency=currency)
        self._cache[key] = outcome
        return outcome

    def _cache_key(self, label: str, section: Section, subsection: Subsection | None) -> tuple[str, str, str]:
        return (taxonomy.TAXONOMY_VERSION, normalise(label), f"{section.value}/{(subsection.value if subsection else '')}")

    def _resolved(self, canonical: str, method: NormalizationMethod) -> NormalizationOutcome:
        return NormalizationOutcome(canonical_label=canonical, status=NormalizationStatus.NORMALIZED, method=method, taxonomy_version=taxonomy.TAXONOMY_VERSION)

    def _review(self, reason: str, *, method: NormalizationMethod=NormalizationMethod.LLM, confidence: float | None=None, model: str | None=None, status: NormalizationStatus=NormalizationStatus.NEEDS_REVIEW) -> NormalizationOutcome:
        return NormalizationOutcome(canonical_label=None, status=status, method=method, taxonomy_version=taxonomy.TAXONOMY_VERSION, confidence=confidence, model=model, reason=reason)

    def _unavailable(self) -> NormalizationOutcome:
        return self._review('llm_unavailable', method=NormalizationMethod.UNAVAILABLE, status=NormalizationStatus.UNAVAILABLE)

    async def _ask(self, label: str, *, section: Section, subsection: Subsection | None, neighbours: tuple[str, ...], currency: str | None) -> NormalizationOutcome:
        if self._unusable or not self._provider.available():
            return self._unavailable()
        allowed = taxonomy.labels_for(section, subsection)
        prompt = build_prompt(label, section=section, subsection=subsection, allowed=allowed, neighbours=neighbours, currency=currency)
        schema = response_schema(allowed)
        result = None
        for attempt in range(self._retries + 1):
            try:
                result = await self._provider.complete_json(prompt=prompt, schema=schema, options=_OPTIONS)
                break
            except LlmUnavailable as exc:
                logger.warning('The local model became unusable: %s', exc)
                self._unusable = True
                return self._unavailable()
            except Exception as exc:
                if attempt >= self._retries:
                    logger.warning('Normalization failed for a label: %s', exc)
                    return self._review('provider_error')
        assert result is not None
        return self._validate(result.payload, section, subsection, result.model)

    def _validate(self, payload: Any, section: Section, subsection: Subsection | None, model: str) -> NormalizationOutcome:
        parsed = _parse(payload)
        if parsed is None:
            return self._review('incomplete_response', model=model)
        canonical, confidence = parsed
        if canonical == taxonomy.UNKNOWN:
            return self._review('model_abstained', confidence=confidence, model=model)
        if taxonomy.get(canonical) is None:
            return self._review('invalid_label', confidence=confidence, model=model)
        if not taxonomy.fits(canonical, section, subsection):
            return self._review('section_mismatch', confidence=confidence, model=model)
        if confidence < self._floor:
            return self._review('low_confidence', confidence=confidence, model=model)
        return NormalizationOutcome(canonical_label=canonical, status=NormalizationStatus.NORMALIZED, method=NormalizationMethod.LLM, taxonomy_version=taxonomy.TAXONOMY_VERSION, confidence=confidence, model=model)

def _parse(payload: Any) -> tuple[str, float] | None:
    if not isinstance(payload, dict):
        return None
    canonical = payload.get('canonical_label')
    confidence = payload.get('confidence')
    if not isinstance(canonical, str) or not canonical:
        return None
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None
    if not 0 <= float(confidence) <= 1:
        return None
    if not isinstance(payload.get('reasoning'), str):
        return None
    return (canonical, float(confidence))

def _as_cached(outcome: NormalizationOutcome) -> NormalizationOutcome:
    from dataclasses import replace
    return replace(outcome, method=NormalizationMethod.CACHE)
__all__ = ['DEFAULT_CONFIDENCE_FLOOR', 'NormalizationOutcome', 'Normalizer']
