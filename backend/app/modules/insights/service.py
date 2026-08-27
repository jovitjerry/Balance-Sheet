"""Module 4 - RAG, financial insights and user Q&A.

Answers a question about one already-processed Balance Sheet, grounded in what
Modules 1-3 stored. It never re-parses a file, never OCRs, never normalizes a
term and never computes a figure: the model **explains** numbers it is handed.

The flow, and where each guard sits:

    route(question)                 rules, no model
      out of scope? ---------------> refuse. No model call at all.
      unsupported metric? ---------> refuse, naming what IS available.
    facts_for(document)             free, exact, always
    ensure_indexed + search         only when the route needs text
    build_context                   fenced; extracts marked untrusted
      nothing retrieved? ----------> refuse. No model call.
    complete_json(schema)           citations closed to a per-request enum
    verify(answer)                  every figure must be in context
      failed? ---------------------> retry once, naming the figure
      failed again? ---------------> refuse rather than state it

Three of those refusals happen without ever reaching the model, which is the
cheapest kind of correctness: a question a Balance Sheet structurally cannot
answer does not need a model's opinion.
"""

from __future__ import annotations

import logging
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings, get_settings
from app.core.errors import StageNotImplemented
from app.core.llm.base import LlmProvider, LlmUnavailable
from app.core.llm.embeddings import EmbeddingProvider
from app.core.schemas import (
    Answer,
    AnswerStatus,
    BalanceSheetDocument,
    DocumentStatus,
    Evidence,
    RetrievalRoute,
    Verification,
)
from app.core.storage import FileStorage
from app.modules.insights import prompts
from app.modules.insights.context import Context, build_context
from app.modules.insights.indexing import ensure_indexed
from app.modules.insights.retrieval import search, to_evidence
from app.modules.insights.routing import (
    RouteDecision,
    asks_for_unsupported_metric,
    route,
)
from app.modules.insights.schema import answer_schema
from app.modules.insights.structured import facts_for
from app.modules.insights.verification import VerificationResult, allowed_figures, verify
from app.modules.ratios import definitions

logger = logging.getLogger(__name__)

# Bumped when the prompts, the routing rules or the grounding checks change.
# Stored on every answer: an answer that cannot say what produced it cannot be
# compared with one produced later.
RAG_SPEC_VERSION = "1.0.0"

# Reasons an answer carries no prose. A closed set, so a caller can branch on
# them - free text here would be unusable to the frontend and to Module 4's own
# tests.
REASON_OUT_OF_SCOPE = "out_of_scope"
REASON_UNSUPPORTED_METRIC = "unsupported_metric"
REASON_NO_CONTEXT = "no_context"
REASON_INSUFFICIENT_CONTEXT = "insufficient_context"
REASON_UNVERIFIABLE_FIGURES = "unverifiable_figures"
REASON_MALFORMED_RESPONSE = "malformed_response"
REASON_LLM_UNAVAILABLE = "llm_unavailable"

REASONS: frozenset[str] = frozenset(
    {
        REASON_OUT_OF_SCOPE,
        REASON_UNSUPPORTED_METRIC,
        REASON_NO_CONTEXT,
        REASON_INSUFFICIENT_CONTEXT,
        REASON_UNVERIFIABLE_FIGURES,
        REASON_MALFORMED_RESPONSE,
        REASON_LLM_UNAVAILABLE,
    }
)

# temperature=0, as everywhere else a model is used in this project. An
# academic result that moves between runs is not a result.
_OPTIONS: dict[str, Any] = {"temperature": 0}


async def answer_question(
    document: BalanceSheetDocument,
    question: str,
    *,
    provider: LlmProvider,
    embeddings: EmbeddingProvider | None = None,
    db: AsyncDatabase[dict[str, Any]] | None = None,
    storage: FileStorage | None = None,
    settings: Settings | None = None,
    history: list[tuple[str, str]] | None = None,
) -> Answer:
    """Answer ``question`` about ``document``, grounded and cited.

    ``db`` and ``embeddings`` are needed only for the text path. Without them
    the structured path still answers every financial question - which is what
    makes the whole of this testable with no Atlas and no embedding model.

    :raises StageNotImplemented: the document has not been through Modules 2-3.
    :raises LlmUnavailable: only when ``LLM_REQUIRED`` is set; by default an
        unreachable model degrades to facts without prose.
    """
    settings = settings or get_settings()
    if document.extracted is None:
        raise StageNotImplemented(
            "This document has not been extracted yet, so there is nothing to "
            "answer questions about."
        )

    decision = route(question, document=document)

    if decision.route is RetrievalRoute.OUT_OF_SCOPE:
        return _refusal(
            document,
            question,
            decision,
            reason=REASON_OUT_OF_SCOPE,
            text=prompts.OUT_OF_SCOPE_ANSWER.format(
                terms=_english_list(decision.out_of_scope_terms)
            ),
        )

    if asks_for_unsupported_metric(question, decision):
        return _refusal(
            document,
            question,
            decision,
            reason=REASON_UNSUPPORTED_METRIC,
            text=prompts.UNSUPPORTED_METRIC_ANSWER.format(
                available=_english_list(
                    [name.replace("_", " ") for name in definitions.names()]
                )
            ),
        )

    facts = facts_for(document, decision=decision)
    extracts = await _extracts_for(
        document,
        question,
        decision,
        embeddings=embeddings,
        db=db,
        storage=storage,
    )
    context = build_context(facts=facts, extracts=extracts, history=history)

    if context.is_empty:
        return _refusal(
            document,
            question,
            decision,
            reason=REASON_NO_CONTEXT,
            text=prompts.NO_CONTEXT_ANSWER,
        )

    if not provider.available():
        return _degraded(document, question, decision, context, settings)

    return await _generate(document, question, decision, context, provider=provider)


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------


async def _extracts_for(
    document: BalanceSheetDocument,
    question: str,
    decision: RouteDecision,
    *,
    embeddings: EmbeddingProvider | None,
    db: AsyncDatabase[dict[str, Any]] | None,
    storage: FileStorage | None,
) -> list[Evidence]:
    """Passages from the document's own text, when the route calls for them.

    Failure here is not fatal. The structured facts are the authoritative half
    and answer every financial question on their own, so an unreachable
    embedding model degrades the answer rather than destroying it - the same
    rule Module 2 follows when terminology cannot be resolved.
    """
    if not decision.needs_text or db is None or embeddings is None:
        return []

    try:
        await ensure_indexed(db, document, embeddings=embeddings, storage=storage)
        if document.id is None:
            return []
        [vector] = await embeddings.embed([question])
        found = await search(db, document_id=document.id, query=vector)
    except LlmUnavailable as exc:
        logger.warning("Text retrieval unavailable for %s: %s", document.id, exc)
        return []
    except Exception as exc:  # noqa: BLE001 - retrieval is an enhancement here
        logger.exception("Text retrieval failed for %s: %s", document.id, exc)
        return []

    return to_evidence(found)


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


async def _generate(
    document: BalanceSheetDocument,
    question: str,
    decision: RouteDecision,
    context: Context,
    *,
    provider: LlmProvider,
) -> Answer:
    """Ask the model, then check what it said before believing it."""
    template = _template_for(decision, context)
    prompt = prompts.build(template, context=context.text, question=question)
    schema = answer_schema(context.citation_ids)
    allowed = allowed_figures(context)

    try:
        reply = await _ask(provider, prompt, schema)
    except LlmUnavailable:
        raise
    except ValueError as exc:
        # Constrained decoding makes malformed JSON rare, but a truncated
        # response is still possible - and half an answer is worse than none.
        logger.warning("The model returned an unusable answer: %s", exc)
        return _refusal(
            document,
            question,
            decision,
            reason=REASON_MALFORMED_RESPONSE,
            text=prompts.NO_CONTEXT_ANSWER,
        )

    if reply is None:
        return _refusal(
            document,
            question,
            decision,
            reason=REASON_MALFORMED_RESPONSE,
            text=prompts.NO_CONTEXT_ANSWER,
        )

    result = verify(reply.answer, figures_used=reply.figures_used, allowed=allowed)
    retried = False

    if not result.passed:
        # One retry, naming the offending figure. A retry that does not say
        # what was wrong is just a second roll of the dice.
        logger.info(
            "Regenerating an answer for %s: unverified %s",
            document.id,
            result.unverified,
        )
        retried = True
        corrected = f"{prompt}\n\n{result.correction()}"
        try:
            second = await _ask(provider, corrected, schema)
        except ValueError:
            second = None
        if second is not None:
            reply = second
            result = verify(
                reply.answer, figures_used=reply.figures_used, allowed=allowed
            )

    if not result.passed:
        # Refuse rather than ship a figure nobody can trace. This is the whole
        # point: on this project's own benchmark a model stated 550,000 for a
        # true 850,000 and drew the opposite conclusion, fluently.
        return _refusal(
            document,
            question,
            decision,
            reason=REASON_UNVERIFIABLE_FIGURES,
            text=(
                "I could not answer without stating a figure this document does "
                "not support, so I have not answered. The figures below are the "
                "ones the document actually contains."
            ),
            facts=list(context.evidence),
            verification=_record(result, retried),
        )

    citations = _resolve(reply.citations, context)
    return Answer(
        document_id=document.id or "",
        question=question,
        answer=reply.answer,
        status=AnswerStatus.ANSWERED if reply.sufficient else AnswerStatus.REFUSED,
        route=decision.route,
        supporting_facts=list(context.evidence),
        citations=citations,
        verification=_record(result, retried),
        reason=None if reply.sufficient else REASON_INSUFFICIENT_CONTEXT,
        model=reply.model,
        spec_version=RAG_SPEC_VERSION,
    )


class _Reply:
    """One parsed model response."""

    __slots__ = ("answer", "sufficient", "citations", "figures_used", "model")

    def __init__(
        self,
        *,
        answer: str,
        sufficient: bool,
        citations: list[str],
        figures_used: list[str],
        model: str,
    ) -> None:
        self.answer = answer
        self.sufficient = sufficient
        self.citations = citations
        self.figures_used = figures_used
        self.model = model


async def _ask(
    provider: LlmProvider, prompt: str, schema: dict[str, Any]
) -> _Reply | None:
    """One round trip, parsed and type-checked.

    The grammar guarantees the *shape*, so this is defence in depth rather than
    the primary check - but a truncated response is still possible, and a
    silently missing field would become an answer with no grounding.
    """
    result = await provider.complete_json(
        prompt=prompt, schema=schema, options=_OPTIONS
    )
    payload = result.payload
    if not isinstance(payload, dict):
        return None

    answer = payload.get("answer")
    sufficient = payload.get("sufficient")
    citations = payload.get("citations")
    figures = payload.get("figures_used")

    if not isinstance(answer, str) or not answer.strip():
        return None
    if not isinstance(sufficient, bool):
        return None

    return _Reply(
        answer=answer.strip(),
        sufficient=sufficient,
        citations=[tag for tag in (citations or []) if isinstance(tag, str)],
        figures_used=[str(figure) for figure in (figures or [])],
        model=result.model,
    )


def _template_for(decision: RouteDecision, context: Context) -> str:
    """The narrowest prompt that fits this question.

    Four small task-specific prompts rather than one branching one: a long
    prompt with conditionals is where an 8B model starts skipping clauses.
    """
    if not context.has_facts and not context.has_text:  # pragma: no cover - guarded above
        return prompts.INSUFFICIENT_CONTEXT
    if _names_a_ratio(decision):
        return prompts.RATIO_EXPLANATION
    if decision.route is RetrievalRoute.STRUCTURED:
        return prompts.STRUCTURED_FACT
    return prompts.GROUNDED_QA


def _names_a_ratio(decision: RouteDecision) -> bool:
    return bool(set(decision.matched_concepts) & set(definitions.names()))


# --------------------------------------------------------------------------
# Outcomes
# --------------------------------------------------------------------------


def _resolve(tags: list[str], context: Context) -> list[Evidence]:
    """Map cited tags back to the evidence they name.

    A tag that resolves to nothing is **dropped**, not passed through. The enum
    makes an unsupplied tag unreachable, so this should never fire - but a
    citation pointing nowhere is worse than none, and the cost of checking is a
    dictionary lookup.
    """
    by_id = {entry.id: entry for entry in context.evidence}
    seen: set[str] = set()
    resolved: list[Evidence] = []
    for tag in tags:
        entry = by_id.get(tag)
        if entry is None:
            logger.warning("Dropped an unresolvable citation: %r", tag)
            continue
        if entry.id in seen:
            continue
        seen.add(entry.id)
        resolved.append(entry)
    return resolved


def _refusal(
    document: BalanceSheetDocument,
    question: str,
    decision: RouteDecision,
    *,
    reason: str,
    text: str,
    facts: list[Evidence] | None = None,
    verification: Verification | None = None,
) -> Answer:
    """A grounded refusal - a correct outcome, not an error.

    Saying "a Balance Sheet does not report profit" is the right answer to that
    question, so it comes back as a normal answer with a reason attached rather
    than as a failure the caller has to interpret.
    """
    return Answer(
        document_id=document.id or "",
        question=question,
        answer=text,
        status=AnswerStatus.REFUSED,
        route=decision.route,
        supporting_facts=facts or [],
        citations=[],
        verification=verification or Verification(passed=True),
        reason=reason,
        model=None,
        spec_version=RAG_SPEC_VERSION,
    )


def _degraded(
    document: BalanceSheetDocument,
    question: str,
    decision: RouteDecision,
    context: Context,
    settings: Settings,
) -> Answer:
    """No model, but the figures are known - so return them.

    Following the rule Module 2 already set: degrade, do not fail. "What is the
    current ratio?" is answerable with no model at all, because Module 3
    computed the number and stored it. Withholding it because a language model
    is offline would help nobody. ``LLM_REQUIRED`` turns this into a 503 for CI
    and demos, where a quietly answerless system would be a false green.
    """
    if settings.llm_required:
        raise LlmUnavailable(
            "The local model is not reachable, and LLM_REQUIRED is set."
        )

    return Answer(
        document_id=document.id or "",
        question=question,
        answer=None,
        status=AnswerStatus.DEGRADED,
        route=decision.route,
        supporting_facts=list(context.evidence),
        citations=[],
        verification=Verification(passed=True),
        reason=REASON_LLM_UNAVAILABLE,
        model=None,
        spec_version=RAG_SPEC_VERSION,
    )


def _record(result: VerificationResult, retried: bool) -> Verification:
    return Verification(
        passed=result.passed,
        figures_verified=list(result.verified),
        figures_unverified=list(result.unverified),
        retried=retried,
    )


def _english_list(items: list[str] | tuple[str, ...]) -> str:
    """Join for prose: "a, b and c"."""
    values = list(dict.fromkeys(items))
    if not values:
        return "that information"
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + " and " + values[-1]


async def explain(document: BalanceSheetDocument, question: str | None = None) -> Answer:
    """Kept for the pipeline's contract; prefer :func:`answer_question`.

    :raises StageNotImplemented: always. Answering needs a provider, and a
        function that fabricated one would hide which model produced an answer.
    """
    raise StageNotImplemented(
        "Use answer_question(), which takes the model provider explicitly."
    )


__all__ = [
    "RAG_SPEC_VERSION",
    "REASONS",
    "REASON_INSUFFICIENT_CONTEXT",
    "REASON_LLM_UNAVAILABLE",
    "REASON_MALFORMED_RESPONSE",
    "REASON_NO_CONTEXT",
    "REASON_OUT_OF_SCOPE",
    "REASON_UNSUPPORTED_METRIC",
    "REASON_UNVERIFIABLE_FIGURES",
    "answer_question",
    "explain",
]
