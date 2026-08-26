"""Terminology mapping: which canonical concept does this label represent?

Separate from extraction on purpose. Extraction answers "what did the document
say?" and must never be coloured by "what do we think it meant" - so the
original label and the printed figure are already fixed before anything here
runs, and nothing here can change them.

**The resolution ladder**, in order, with the method recorded on every answer
so the source of a mapping is always visible:

1. ``dictionary`` - the document already prints the canonical wording.
2. ``cache`` - this label was resolved earlier under the same vocabulary.
3. ``llm`` - a real question, asked of the local model.

**The rule everything below is built around: a rejected answer never becomes a
guess.** Every failure - malformed JSON, a label outside the vocabulary, a
label that contradicts the section it was printed in, a confidence below the
floor, an unreachable model - lands on ``needs_review`` with the line item
fully intact. A line marked for review is a complete extracted line that has no
canonical label yet, which Module 3 can see and skip. A confidently wrong
category is one it cannot.
"""

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

# Below this, a mapping is recorded but not acted on. A policy floor, not a
# truth threshold - see the note on `confidence` in NormalizationOutcome.
DEFAULT_CONFIDENCE_FLOOR = 0.5

# Deterministic decoding. An academic result that changes between runs is not a
# result, and terminology mapping has one right answer per label anyway.
_OPTIONS: dict[str, Any] = {"temperature": 0}


@dataclass(frozen=True)
class NormalizationOutcome:
    """One terminology decision, and everything needed to audit it.

    ``confidence`` is the model's own stated number. It is **not** a calibrated
    probability: small models are routinely confident and wrong, so it is used
    in exactly one direction - it may demote a mapping to review, and it may
    never rescue one that failed a check. It is stored so the benchmark can
    measure whether it correlates with correctness at all.
    """

    canonical_label: str | None
    status: NormalizationStatus
    method: NormalizationMethod
    taxonomy_version: str
    confidence: float | None = None
    model: str | None = None
    reason: str | None = None


class Normalizer:
    """Resolves labels to canonical categories, cheapest route first.

    The cache is held per instance, which is one document's run. A persistent
    cache across documents is keyed identically and is layered on at the
    service boundary; keeping this object free of I/O is what lets the whole
    ladder be tested without a database or a model.
    """

    def __init__(
        self,
        *,
        provider: LlmProvider,
        confidence_floor: float = DEFAULT_CONFIDENCE_FLOOR,
        retries: int = 1,
    ) -> None:
        self._provider = provider
        self._floor = confidence_floor
        self._retries = retries
        self._cache: dict[tuple[str, str, str], NormalizationOutcome] = {}
        # Latched the first time the service says it cannot serve this model at
        # all. Every label after that would fail identically, so asking again -
        # forty more round trips on a full Balance Sheet - discovers nothing
        # and only makes the document slower to give up on.
        self._unusable = False

    async def normalize(
        self,
        label: str,
        *,
        section: Section,
        subsection: Subsection | None,
        neighbours: tuple[str, ...] = (),
        currency: str | None = None,
    ) -> NormalizationOutcome:
        """Map one printed label onto the canonical vocabulary."""
        if canonical := aliases.lookup(label):
            return self._resolved(canonical, NormalizationMethod.DICTIONARY)

        key = self._cache_key(label, section, subsection)
        if (cached := self._cache.get(key)) is not None:
            return _as_cached(cached)

        outcome = await self._ask(
            label,
            section=section,
            subsection=subsection,
            neighbours=neighbours,
            currency=currency,
        )
        self._cache[key] = outcome
        return outcome

    # -- internals ---------------------------------------------------------

    def _cache_key(
        self, label: str, section: Section, subsection: Subsection | None
    ) -> tuple[str, str, str]:
        """Vocabulary, wording and place on the sheet.

        The section belongs in the key because it is part of the question:
        "Other balances" under ASSETS and under LIABILITIES are two different
        questions with two different right answers.
        """
        return (
            taxonomy.TAXONOMY_VERSION,
            normalise(label),
            f"{section.value}/{subsection.value if subsection else ''}",
        )

    def _resolved(
        self, canonical: str, method: NormalizationMethod
    ) -> NormalizationOutcome:
        return NormalizationOutcome(
            canonical_label=canonical,
            status=NormalizationStatus.NORMALIZED,
            method=method,
            taxonomy_version=taxonomy.TAXONOMY_VERSION,
        )

    def _review(
        self,
        reason: str,
        *,
        method: NormalizationMethod = NormalizationMethod.LLM,
        confidence: float | None = None,
        model: str | None = None,
        status: NormalizationStatus = NormalizationStatus.NEEDS_REVIEW,
    ) -> NormalizationOutcome:
        return NormalizationOutcome(
            canonical_label=None,
            status=status,
            method=method,
            taxonomy_version=taxonomy.TAXONOMY_VERSION,
            confidence=confidence,
            model=model,
            reason=reason,
        )

    def _unavailable(self) -> NormalizationOutcome:
        """The model could not be asked. The line item is untouched and kept."""
        return self._review(
            "llm_unavailable",
            method=NormalizationMethod.UNAVAILABLE,
            status=NormalizationStatus.UNAVAILABLE,
        )

    async def _ask(
        self,
        label: str,
        *,
        section: Section,
        subsection: Subsection | None,
        neighbours: tuple[str, ...],
        currency: str | None,
    ) -> NormalizationOutcome:
        if self._unusable or not self._provider.available():
            # Not a failure of the document. The extraction is complete and
            # correct; only the terminology step could not run, and saying so
            # leaves it re-runnable once the model is back.
            return self._unavailable()

        allowed = taxonomy.labels_for(section, subsection)
        prompt = build_prompt(
            label,
            section=section,
            subsection=subsection,
            allowed=allowed,
            neighbours=neighbours,
            currency=currency,
        )
        schema = response_schema(allowed)

        result = None
        for attempt in range(self._retries + 1):
            try:
                result = await self._provider.complete_json(
                    prompt=prompt, schema=schema, options=_OPTIONS
                )
                break
            except LlmUnavailable as exc:
                # The service cannot serve this model - it is not pulled, or it
                # went away mid-document. A configuration problem, not a
                # transient one: retrying it is pointless and so is asking
                # again for the next label.
                logger.warning("The local model became unusable: %s", exc)
                self._unusable = True
                return self._unavailable()
            except Exception as exc:  # noqa: BLE001 - any transport failure counts
                if attempt >= self._retries:
                    # One item, not the document. Everything else continues.
                    logger.warning("Normalization failed for a label: %s", exc)
                    return self._review("provider_error")

        assert result is not None  # pragma: no cover - the loop returns otherwise
        return self._validate(result.payload, section, subsection, result.model)

    def _validate(
        self,
        payload: Any,
        section: Section,
        subsection: Subsection | None,
        model: str,
    ) -> NormalizationOutcome:
        """The gauntlet every answer passes before it is believed.

        Ordered so the reason recorded is the *first* thing wrong, which is the
        one worth reading.
        """
        parsed = _parse(payload)
        if parsed is None:
            return self._review("incomplete_response", model=model)

        canonical, confidence = parsed

        if canonical == taxonomy.UNKNOWN:
            # The model declined, which the prompt explicitly permits. This is
            # the answer working as intended, not the answer failing.
            return self._review("model_abstained", confidence=confidence, model=model)

        if taxonomy.get(canonical) is None:
            # Constrained decoding should make this unreachable. If it is ever
            # reached, something about the transport has silently changed.
            return self._review("invalid_label", confidence=confidence, model=model)

        if not taxonomy.fits(canonical, section, subsection):
            # Structurally valid, factually wrong. No grammar can catch this.
            return self._review("section_mismatch", confidence=confidence, model=model)

        if confidence < self._floor:
            return self._review("low_confidence", confidence=confidence, model=model)

        return NormalizationOutcome(
            canonical_label=canonical,
            status=NormalizationStatus.NORMALIZED,
            method=NormalizationMethod.LLM,
            taxonomy_version=taxonomy.TAXONOMY_VERSION,
            confidence=confidence,
            model=model,
        )


def _parse(payload: Any) -> tuple[str, float] | None:
    """Pull the two fields that matter out of a response, or refuse it."""
    if not isinstance(payload, dict):
        return None

    canonical = payload.get("canonical_label")
    confidence = payload.get("confidence")
    if not isinstance(canonical, str) or not canonical:
        return None
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None
    if not 0 <= float(confidence) <= 1:
        return None
    if not isinstance(payload.get("reasoning"), str):
        return None
    return canonical, float(confidence)


def _as_cached(outcome: NormalizationOutcome) -> NormalizationOutcome:
    """The same decision, relabelled as having come from the cache."""
    from dataclasses import replace

    return replace(outcome, method=NormalizationMethod.CACHE)


__all__ = [
    "DEFAULT_CONFIDENCE_FLOOR",
    "NormalizationOutcome",
    "Normalizer",
]
