from __future__ import annotations
import logging
from typing import Any
from pymongo.asynchronous.database import AsyncDatabase
from app.core.config import Settings, get_settings
from app.core.errors import StageNotImplemented
from app.core.llm.base import LlmProvider, LlmUnavailable
from app.core.llm.embeddings import EmbeddingProvider
from app.core.schemas import Answer, AnswerStatus, BalanceSheetDocument, DocumentStatus, Evidence, RetrievalRoute, Verification
from app.core.storage import FileStorage
from app.modules.insights import prompts
from app.modules.insights.context import Context, build_context
from app.modules.insights.indexing import ensure_indexed
from app.modules.insights.retrieval import search, to_evidence
from app.modules.insights.routing import RouteDecision, asks_for_unsupported_metric, route
from app.modules.insights.schema import answer_schema
from app.modules.insights.structured import facts_for
from app.modules.insights.verification import VerificationResult, allowed_figures, verify
from app.modules.ratios import definitions
logger = logging.getLogger(__name__)
RAG_SPEC_VERSION = '1.0.0'
REASON_OUT_OF_SCOPE = 'out_of_scope'
REASON_UNSUPPORTED_METRIC = 'unsupported_metric'
REASON_NO_CONTEXT = 'no_context'
REASON_INSUFFICIENT_CONTEXT = 'insufficient_context'
REASON_UNVERIFIABLE_FIGURES = 'unverifiable_figures'
REASON_MALFORMED_RESPONSE = 'malformed_response'
REASON_LLM_UNAVAILABLE = 'llm_unavailable'
REASONS: frozenset[str] = frozenset({REASON_OUT_OF_SCOPE, REASON_UNSUPPORTED_METRIC, REASON_NO_CONTEXT, REASON_INSUFFICIENT_CONTEXT, REASON_UNVERIFIABLE_FIGURES, REASON_MALFORMED_RESPONSE, REASON_LLM_UNAVAILABLE})
_OPTIONS: dict[str, Any] = {'temperature': 0}

async def answer_question(document: BalanceSheetDocument, question: str, *, provider: LlmProvider, embeddings: EmbeddingProvider | None=None, db: AsyncDatabase[dict[str, Any]] | None=None, storage: FileStorage | None=None, settings: Settings | None=None, history: list[tuple[str, str]] | None=None) -> Answer:
    settings = settings or get_settings()
    if document.extracted is None:
        raise StageNotImplemented('This document has not been extracted yet, so there is nothing to answer questions about.')
    decision = route(question, document=document)
    if decision.route is RetrievalRoute.OUT_OF_SCOPE:
        return _refusal(document, question, decision, reason=REASON_OUT_OF_SCOPE, text=prompts.ADVICE_ANSWER if decision.asks_for_advice else prompts.OUT_OF_SCOPE_ANSWER.format(terms=_english_list(decision.out_of_scope_terms)))
    if asks_for_unsupported_metric(question, decision):
        return _refusal(document, question, decision, reason=REASON_UNSUPPORTED_METRIC, text=prompts.UNSUPPORTED_METRIC_ANSWER.format(available=_english_list([name.replace('_', ' ') for name in definitions.names()])))
    facts = facts_for(document, decision=decision)
    extracts = await _extracts_for(document, question, decision, embeddings=embeddings, db=db, storage=storage)
    context = build_context(facts=facts, extracts=extracts, history=history)
    if context.is_empty:
        return _refusal(document, question, decision, reason=REASON_NO_CONTEXT, text=prompts.NO_CONTEXT_ANSWER)
    if not provider.available():
        return _degraded(document, question, decision, context, settings)
    return await _generate(document, question, decision, context, provider=provider)

async def _extracts_for(document: BalanceSheetDocument, question: str, decision: RouteDecision, *, embeddings: EmbeddingProvider | None, db: AsyncDatabase[dict[str, Any]] | None, storage: FileStorage | None) -> list[Evidence]:
    if not decision.needs_text or db is None or embeddings is None:
        return []
    try:
        await ensure_indexed(db, document, embeddings=embeddings, storage=storage)
        if document.id is None:
            return []
        [vector] = await embeddings.embed([question])
        found = await search(db, document_id=document.id, query=vector)
    except LlmUnavailable as exc:
        logger.warning('Text retrieval unavailable for %s: %s', document.id, exc)
        return []
    except Exception as exc:
        logger.exception('Text retrieval failed for %s: %s', document.id, exc)
        return []
    return to_evidence(found)

async def _generate(document: BalanceSheetDocument, question: str, decision: RouteDecision, context: Context, *, provider: LlmProvider) -> Answer:
    template = _template_for(decision, context)
    prompt = prompts.build(template, context=context.text, question=question)
    schema = answer_schema(context.citation_ids)
    allowed = allowed_figures(context)
    try:
        reply = await _ask(provider, prompt, schema)
    except LlmUnavailable:
        raise
    except ValueError as exc:
        logger.warning('The model returned an unusable answer: %s', exc)
        return _refusal(document, question, decision, reason=REASON_MALFORMED_RESPONSE, text=prompts.NO_CONTEXT_ANSWER)
    if reply is None:
        return _refusal(document, question, decision, reason=REASON_MALFORMED_RESPONSE, text=prompts.NO_CONTEXT_ANSWER)
    result = verify(reply.answer, figures_used=reply.figures_used, allowed=allowed)
    retried = False
    if not result.passed:
        logger.info('Regenerating an answer for %s: unverified %s', document.id, result.unverified)
        retried = True
        corrected = f'{prompt}\n\n{result.correction()}'
        try:
            second = await _ask(provider, corrected, schema)
        except ValueError:
            second = None
        if second is not None:
            reply = second
            result = verify(reply.answer, figures_used=reply.figures_used, allowed=allowed)
    if not result.passed:
        return _refusal(document, question, decision, reason=REASON_UNVERIFIABLE_FIGURES, text='I could not answer without stating a figure this document does not support, so I have not answered. The figures below are the ones the document actually contains.', facts=list(context.evidence), verification=_record(result, retried))
    citations = _resolve(reply.citations, context)
    return Answer(document_id=document.id or '', question=question, answer=reply.answer, status=AnswerStatus.ANSWERED if reply.sufficient else AnswerStatus.REFUSED, route=decision.route, supporting_facts=list(context.evidence), citations=citations, verification=_record(result, retried), reason=None if reply.sufficient else REASON_INSUFFICIENT_CONTEXT, model=reply.model, spec_version=RAG_SPEC_VERSION)

class _Reply:
    __slots__ = ('answer', 'sufficient', 'citations', 'figures_used', 'model')

    def __init__(self, *, answer: str, sufficient: bool, citations: list[str], figures_used: list[str], model: str) -> None:
        self.answer = answer
        self.sufficient = sufficient
        self.citations = citations
        self.figures_used = figures_used
        self.model = model

async def _ask(provider: LlmProvider, prompt: str, schema: dict[str, Any]) -> _Reply | None:
    result = await provider.complete_json(prompt=prompt, schema=schema, options=_OPTIONS)
    payload = result.payload
    if not isinstance(payload, dict):
        return None
    answer = payload.get('answer')
    sufficient = payload.get('sufficient')
    citations = payload.get('citations')
    figures = payload.get('figures_used')
    if not isinstance(answer, str) or not answer.strip():
        return None
    if not isinstance(sufficient, bool):
        return None
    return _Reply(answer=answer.strip(), sufficient=sufficient, citations=[tag for tag in citations or [] if isinstance(tag, str)], figures_used=[str(figure) for figure in figures or []], model=result.model)

def _template_for(decision: RouteDecision, context: Context) -> str:
    if not context.has_facts and (not context.has_text):
        return prompts.INSUFFICIENT_CONTEXT
    if _names_a_ratio(decision):
        return prompts.RATIO_EXPLANATION
    if decision.route is RetrievalRoute.STRUCTURED:
        return prompts.STRUCTURED_FACT
    return prompts.GROUNDED_QA

def _names_a_ratio(decision: RouteDecision) -> bool:
    return bool(set(decision.matched_concepts) & set(definitions.names()))

def _resolve(tags: list[str], context: Context) -> list[Evidence]:
    by_id = {entry.id: entry for entry in context.evidence}
    seen: set[str] = set()
    resolved: list[Evidence] = []
    for tag in tags:
        entry = by_id.get(tag)
        if entry is None:
            logger.warning('Dropped an unresolvable citation: %r', tag)
            continue
        if entry.id in seen:
            continue
        seen.add(entry.id)
        resolved.append(entry)
    return resolved

def _refusal(document: BalanceSheetDocument, question: str, decision: RouteDecision, *, reason: str, text: str, facts: list[Evidence] | None=None, verification: Verification | None=None) -> Answer:
    return Answer(document_id=document.id or '', question=question, answer=text, status=AnswerStatus.REFUSED, route=decision.route, supporting_facts=facts or [], citations=[], verification=verification or Verification(passed=True), reason=reason, model=None, spec_version=RAG_SPEC_VERSION)

def _degraded(document: BalanceSheetDocument, question: str, decision: RouteDecision, context: Context, settings: Settings) -> Answer:
    if settings.llm_required:
        raise LlmUnavailable('The local model is not reachable, and LLM_REQUIRED is set.')
    return Answer(document_id=document.id or '', question=question, answer=None, status=AnswerStatus.DEGRADED, route=decision.route, supporting_facts=list(context.evidence), citations=[], verification=Verification(passed=True), reason=REASON_LLM_UNAVAILABLE, model=None, spec_version=RAG_SPEC_VERSION)

def _record(result: VerificationResult, retried: bool) -> Verification:
    return Verification(passed=result.passed, figures_verified=list(result.verified), figures_unverified=list(result.unverified), retried=retried)

def _english_list(items: list[str] | tuple[str, ...]) -> str:
    values = list(dict.fromkeys(items))
    if not values:
        return 'that information'
    if len(values) == 1:
        return values[0]
    return ', '.join(values[:-1]) + ' and ' + values[-1]

async def explain(document: BalanceSheetDocument, question: str | None=None) -> Answer:
    raise StageNotImplemented('Use answer_question(), which takes the model provider explicitly.')
__all__ = ['RAG_SPEC_VERSION', 'REASONS', 'REASON_INSUFFICIENT_CONTEXT', 'REASON_LLM_UNAVAILABLE', 'REASON_MALFORMED_RESPONSE', 'REASON_NO_CONTEXT', 'REASON_OUT_OF_SCOPE', 'REASON_UNSUPPORTED_METRIC', 'REASON_UNVERIFIABLE_FIGURES', 'answer_question', 'explain']
