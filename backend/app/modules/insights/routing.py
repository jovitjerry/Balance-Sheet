from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from app.core.schemas import BalanceSheetDocument, RetrievalRoute
from app.core.text import matches_any, normalise
from app.modules.extraction import taxonomy
from app.modules.ratios import definitions
_STOPWORDS = frozenset({'and', 'or', 'of', 'the', 'a', 'an', 'to', 'for', 'in', 'on', 'at', 'by', 'with', 'from', 'is', 'are', 'was', 'were', 'be', 'it', 'its', 'this', 'that', 'there', 'how', 'much', 'many', 'what', 'which', 'does', 'do', 'did', 'has', 'have', 'company', 'any', 's'})
_NARRATIVE = frozenset({'policy', 'policies', 'note', 'notes', 'describe', 'describes', 'described', 'description', 'method', 'basis', 'stated', 'disclosure', 'disclose', 'disclosed', 'valuation', 'valued', 'treatment', 'recognised', 'recognized', 'says', 'say', 'wording', 'narrative', 'text', 'mention', 'mentions', 'accounting'})
_INTERPRETIVE = frozenset({'why', 'explain', 'explanation', 'mean', 'means', 'meaning', 'should', 'assess', 'good', 'bad', 'healthy', 'unhealthy', 'concerning', 'worrying', 'risk', 'risky', 'matter', 'matters', 'interpret', 'significance', 'significant', 'imply', 'implies', 'suggest', 'suggests', 'strong', 'weak', 'able', 'afford'})
OUT_OF_SCOPE_PHRASES: tuple[str, ...] = ('net profit', 'gross profit', 'operating profit', 'profit for the year', 'profit and loss', 'profit or loss', 'profitability', 'profitable', 'profit', 'net income', 'revenue', 'revenues', 'turnover', 'sales', 'earnings per share', 'eps', 'gross margin', 'profit margin', 'operating margin', 'net margin', 'margin', 'ebitda', 'ebit', 'cost of goods sold', 'cogs', 'operating expenses', 'interest expense', 'interest coverage', 'tax expense', 'dividend paid', 'dividends paid', 'cash flow', 'cash flows', 'operating cash flow', 'free cash flow', 'cash generated', 'last year', 'previous year', 'prior year', 'year on year', 'year over year', 'compared with last', 'compared to last', 'growth', 'trend', 'next year', 'forecast', 'forecasts', 'projection', 'projected', 'expected revenue', 'will be')
ADVICE_PHRASES: tuple[str, ...] = ('should i invest', 'should we invest', 'should i buy', 'should we buy', 'should i sell', 'should we sell', 'should i avoid', 'should we avoid', 'should i put money', 'would you invest', 'would you buy', 'do you recommend', 'would you recommend', 'recommend investing', 'recommend buying', 'recommend selling', 'good investment', 'bad investment', 'safe investment', 'solid investment', 'worth investing', 'worth buying', 'investment advice', 'financial advice', 'your advice', 'advise me', 'is it a buy', 'is it a sell', 'invest in this', 'invest in them')

@dataclass(frozen=True)
class RouteDecision:
    route: RetrievalRoute
    reason: str
    matched_concepts: tuple[str, ...] = ()
    matched_labels: tuple[str, ...] = ()
    matched_sections: tuple[str, ...] = ()
    matched_narrative: tuple[str, ...] = ()
    matched_interpretive: tuple[str, ...] = ()
    out_of_scope_terms: tuple[str, ...] = ()
    asks_for_advice: bool = False
    'Whether the question asked for a recommendation rather than a figure.\n\n    Carried separately from ``out_of_scope_terms`` because the refusal reads\n    differently: nothing is *missing* from the document, it is that no Balance\n    Sheet can support the decision being asked for.\n    '

    @property
    def needs_text(self) -> bool:
        return self.route in (RetrievalRoute.TEXT, RetrievalRoute.BOTH)

    @property
    def needs_structured(self) -> bool:
        return self.route in (RetrievalRoute.STRUCTURED, RetrievalRoute.TEXT, RetrievalRoute.BOTH)

def route(question: str, *, document: BalanceSheetDocument | None=None) -> RouteDecision:
    text = normalise(question)
    if not text:
        return RouteDecision(route=RetrievalRoute.BOTH, reason='empty question; retrieve everything')
    advice = matches_any(text, ADVICE_PHRASES)
    if advice is not None:
        return RouteDecision(route=RetrievalRoute.OUT_OF_SCOPE, reason='the question asks for a recommendation, which no Balance Sheet on its own can support', out_of_scope_terms=(advice,), asks_for_advice=True)
    out_of_scope, remainder = _strip_out_of_scope(text)
    words = _stems(remainder)
    concepts = _concepts_in(words, remainder)
    labels = _document_labels_in(words, document)
    sections = _sections_in(remainder)
    narrative = tuple(sorted(_NARRATIVE & set(remainder.split())))
    interpretive = tuple(sorted(_INTERPRETIVE & set(remainder.split())))
    found_structured = bool(concepts or labels or sections)
    if out_of_scope and (not found_structured):
        return RouteDecision(route=RetrievalRoute.OUT_OF_SCOPE, reason='the question asks for something a Balance Sheet does not report', out_of_scope_terms=out_of_scope)
    common = {'matched_concepts': concepts, 'matched_labels': labels, 'matched_sections': sections, 'matched_narrative': narrative, 'matched_interpretive': interpretive, 'out_of_scope_terms': out_of_scope}
    if interpretive:
        return RouteDecision(route=RetrievalRoute.BOTH, reason='interpretive question; needs figures and any supporting text', **common)
    if narrative and (not found_structured):
        return RouteDecision(route=RetrievalRoute.TEXT, reason='asks what the document says, and names no stored figure', **common)
    if narrative:
        return RouteDecision(route=RetrievalRoute.BOTH, reason='names a stored figure and asks what the document says about it', **common)
    if found_structured:
        return RouteDecision(route=RetrievalRoute.STRUCTURED, reason='names a stored figure and asks nothing narrative about it', **common)
    return RouteDecision(route=RetrievalRoute.BOTH, reason='nothing specific recognised; retrieve both cheaply', **common)

def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith('s') else word

def _stems(text: str) -> set[str]:
    return {_stem(word) for word in text.split() if word not in _STOPWORDS}

def _content_words(phrase: str) -> frozenset[str]:
    return frozenset((_stem(word) for word in normalise(phrase).split() if word not in _STOPWORDS))

def _strip_out_of_scope(text: str) -> tuple[tuple[str, ...], str]:
    found: list[str] = []
    remainder = f' {text} '
    for phrase in sorted(OUT_OF_SCOPE_PHRASES, key=len, reverse=True):
        needle = f' {normalise(phrase)} '
        if needle in remainder:
            found.append(phrase)
            remainder = remainder.replace(needle, ' ')
    return (tuple(sorted(found)), remainder.strip())

@lru_cache(maxsize=1)
def _concept_index() -> tuple[dict[str, frozenset[str]], dict[str, str]]:
    required: dict[str, frozenset[str]] = {}
    occurrences: dict[str, set[str]] = {}
    for category in taxonomy.CATEGORIES:
        label_words = _content_words(category.label.replace('_', ' '))
        required[category.label] = label_words
        for word in label_words | _content_words(category.description):
            occurrences.setdefault(word, set()).add(category.label)
    for name in definitions.names():
        required[name] = _content_words(name.replace('_', ' '))
    distinctive = {word: next(iter(owners)) for word, owners in occurrences.items() if len(owners) == 1}
    return (required, distinctive)

def _concepts_in(words: set[str], text: str) -> tuple[str, ...]:
    required, distinctive = _concept_index()
    found = {name for name, needed in required.items() if needed and needed <= words}
    found |= {distinctive[word] for word in words if word in distinctive}
    return tuple(sorted(found))

@lru_cache(maxsize=1)
def _section_terms() -> dict[str, str]:
    return {f'total {section.value}': section.value for section in taxonomy.Section}

def _sections_in(text: str) -> tuple[str, ...]:
    padded = f' {text} '
    return tuple(sorted({section for phrase, section in _section_terms().items() if f' {phrase} ' in padded}))

def _document_labels_in(words: set[str], document: BalanceSheetDocument | None) -> tuple[str, ...]:
    if document is None or document.extracted is None:
        return ()
    found: list[str] = []
    for section_name in ('assets', 'liabilities', 'equity'):
        part = getattr(document.extracted, section_name)
        for item in part.line_items:
            needed = _content_words(item.label)
            if needed and needed <= words:
                found.append(item.label)
    return tuple(sorted(set(found)))
_METRIC_WORDS = frozenset({'ratio', 'score', 'multiple', 'index', 'coverage', 'metric'})

def asks_for_unsupported_metric(question: str, decision: RouteDecision) -> bool:
    if decision.route is RetrievalRoute.OUT_OF_SCOPE:
        return False
    words = set(normalise(question).split())
    if not words & _METRIC_WORDS:
        return False
    known_ratios = set(definitions.names())
    return not set(decision.matched_concepts) & known_ratios and (not (decision.matched_concepts or decision.matched_labels or decision.matched_sections))
__all__ = ['ADVICE_PHRASES', 'OUT_OF_SCOPE_PHRASES', 'RouteDecision', 'asks_for_unsupported_metric', 'route']
