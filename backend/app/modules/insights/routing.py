"""Deciding where a question should be answered from - with rules, not a model.

Two reasons this is not a classifier. A generation round-trip costs about four
seconds warm to decide something rules get right on a closed question space; and
a model would make routing non-deterministic, so the same question could route
differently between runs in a project whose whole point is that a result
reproduces.

**The asymmetry that shapes every rule below.** Structured retrieval is a
dictionary lookup on an already-loaded document: no I/O, no model, free. So a
false positive there costs nothing, and the only decision with a real price is
whether to *skip* the vector query - which risks missing an answer that is
genuinely in the notes. The rules therefore bias towards running it, and commit
to ``STRUCTURED`` only for a question that plainly names a stored figure and
asks nothing narrative about it.

**The vocabulary is derived, never hand-written.** Concept terms come from
Module 2's taxonomy - its labels *and* its descriptions - and from Module 3's
ratio names. Module 4 holds no financial synonym list of its own; that is
Module 2's job, and a second half-copy here would drift out of step with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.core.schemas import BalanceSheetDocument, RetrievalRoute
from app.core.text import matches_any, normalise
from app.modules.extraction import taxonomy
from app.modules.ratios import definitions

# Structural words, not financial ones - dropped before matching so that a
# concept is recognised by its content. Nothing here names an accounting idea.
_STOPWORDS = frozenset(
    {"and", "or", "of", "the", "a", "an", "to", "for", "in", "on", "at", "by",
     "with", "from", "is", "are", "was", "were", "be", "it", "its", "this",
     "that", "there", "how", "much", "many", "what", "which", "does", "do",
     "did", "has", "have", "company", "any", "s"}
)

# Question-shape words. These are about the *form* of the question - is it
# asking for a figure, for prose, or for a judgement - and carry no financial
# meaning, which is what keeps them out of Module 2's territory.
_NARRATIVE = frozenset(
    {"policy", "policies", "note", "notes", "describe", "describes", "described",
     "description", "method", "basis", "stated", "disclosure", "disclose",
     "disclosed", "valuation", "valued", "treatment", "recognised", "recognized",
     "says", "say", "wording", "narrative", "text", "mention", "mentions",
     "accounting"}
)

_INTERPRETIVE = frozenset(
    {"why", "explain", "explanation", "mean", "means", "meaning", "should",
     "assess", "good", "bad", "healthy", "unhealthy", "concerning", "worrying",
     "risk", "risky", "matter", "matters", "interpret", "significance",
     "significant", "imply", "implies", "suggest", "suggests", "strong", "weak",
     "able", "afford"}
)

# What a Balance Sheet structurally cannot report. This IS written out, and is
# legitimately Module 4's: it is a statement of the project's scope boundary -
# Income Statement, Cash Flow Statement, and anything multi-period or
# forward-looking - not a vocabulary of accounting terms. A question that hits
# one of these is refused without ever calling a model, because "a Balance Sheet
# does not report profit" is knowable without asking one.
OUT_OF_SCOPE_PHRASES: tuple[str, ...] = (
    # Income Statement
    "net profit", "gross profit", "operating profit", "profit for the year",
    "profit and loss", "profit or loss", "profitability", "profitable", "profit",
    "net income", "revenue", "revenues", "turnover", "sales",
    "earnings per share", "eps", "gross margin", "profit margin",
    "operating margin", "net margin", "margin", "ebitda", "ebit",
    "cost of goods sold", "cogs", "operating expenses", "interest expense",
    "interest coverage", "tax expense", "dividend paid", "dividends paid",
    # Cash Flow Statement
    "cash flow", "cash flows", "operating cash flow", "free cash flow",
    "cash generated",
    # Multi-period and forward-looking - excluded by the single-period scope
    "last year", "previous year", "prior year", "year on year",
    "year over year", "compared with last", "compared to last", "growth",
    "trend", "next year", "forecast", "forecasts", "projection", "projected",
    "expected revenue", "will be",
)


# Asking for a recommendation, as opposed to asking about the figures. Refused
# unconditionally and without a model, because a single-period Balance Sheet
# supports no investment decision - it carries no earnings, no cash flow, no
# trend, no valuation and no price - and that is knowable without asking.
#
# Every entry is multi-word on purpose. `long_term_investments` and
# `short_term_investments` are real categories, so a bare "invest" would refuse
# every question about the investments a company actually holds, which would be
# a worse failure than the one this prevents.
ADVICE_PHRASES: tuple[str, ...] = (
    "should i invest", "should we invest", "should i buy", "should we buy",
    "should i sell", "should we sell", "should i avoid", "should we avoid",
    "should i put money", "would you invest", "would you buy",
    "do you recommend", "would you recommend", "recommend investing",
    "recommend buying", "recommend selling", "good investment",
    "bad investment", "safe investment", "solid investment",
    "worth investing", "worth buying", "investment advice",
    "financial advice", "your advice", "advise me", "is it a buy",
    "is it a sell", "invest in this", "invest in them",
)


@dataclass(frozen=True)
class RouteDecision:
    """Where a question goes, and everything that decided it.

    The matched terms are carried rather than discarded so a routing choice can
    be explained - in a test, in the API response, and in the report.
    """

    route: RetrievalRoute
    reason: str
    matched_concepts: tuple[str, ...] = ()
    matched_labels: tuple[str, ...] = ()
    matched_sections: tuple[str, ...] = ()
    matched_narrative: tuple[str, ...] = ()
    matched_interpretive: tuple[str, ...] = ()
    out_of_scope_terms: tuple[str, ...] = ()
    asks_for_advice: bool = False
    """Whether the question asked for a recommendation rather than a figure.

    Carried separately from ``out_of_scope_terms`` because the refusal reads
    differently: nothing is *missing* from the document, it is that no Balance
    Sheet can support the decision being asked for.
    """

    @property
    def needs_text(self) -> bool:
        """Whether this route pays for a vector query."""
        return self.route in (RetrievalRoute.TEXT, RetrievalRoute.BOTH)

    @property
    def needs_structured(self) -> bool:
        return self.route in (
            RetrievalRoute.STRUCTURED,
            RetrievalRoute.TEXT,
            RetrievalRoute.BOTH,
        )


def route(
    question: str, *, document: BalanceSheetDocument | None = None
) -> RouteDecision:
    """Decide how to answer ``question``. Pure, deterministic, no model.

    ``document`` lets wording peculiar to one filing - *Sundry Debtors*,
    *Stock-in-Trade* - route correctly without any synonym table: the labels
    actually printed on this document are matchable terms for this document.
    """
    text = normalise(question)
    if not text:
        return RouteDecision(
            route=RetrievalRoute.BOTH, reason="empty question; retrieve everything"
        )

    # Advice is checked first and refused unconditionally. Unlike a missing
    # figure - which a question can work around by also naming something
    # answerable - a recommendation cannot be half-given, so a concept match
    # must not rescue it.
    advice = matches_any(text, ADVICE_PHRASES)
    if advice is not None:
        return RouteDecision(
            route=RetrievalRoute.OUT_OF_SCOPE,
            reason="the question asks for a recommendation, which no Balance "
            "Sheet on its own can support",
            out_of_scope_terms=(advice,),
            asks_for_advice=True,
        )

    # Out-of-scope spans are removed before concepts are matched, so that the
    # "cash" inside "operating cash flow" cannot be read as the cash line item.
    # Without this, every Cash Flow question would look like a Balance Sheet one.
    out_of_scope, remainder = _strip_out_of_scope(text)
    words = _stems(remainder)

    concepts = _concepts_in(words, remainder)
    labels = _document_labels_in(words, document)
    sections = _sections_in(remainder)
    narrative = tuple(sorted(_NARRATIVE & set(remainder.split())))
    interpretive = tuple(sorted(_INTERPRETIVE & set(remainder.split())))

    found_structured = bool(concepts or labels or sections)

    if out_of_scope and not found_structured:
        return RouteDecision(
            route=RetrievalRoute.OUT_OF_SCOPE,
            reason="the question asks for something a Balance Sheet does not report",
            out_of_scope_terms=out_of_scope,
        )

    common = {
        "matched_concepts": concepts,
        "matched_labels": labels,
        "matched_sections": sections,
        "matched_narrative": narrative,
        "matched_interpretive": interpretive,
        "out_of_scope_terms": out_of_scope,
    }

    if interpretive:
        # A judgement needs the figures *and* whatever the document says about
        # them - answering "is that good?" from one alone is half an answer.
        return RouteDecision(
            route=RetrievalRoute.BOTH,
            reason="interpretive question; needs figures and any supporting text",
            **common,
        )

    if narrative and not found_structured:
        return RouteDecision(
            route=RetrievalRoute.TEXT,
            reason="asks what the document says, and names no stored figure",
            **common,
        )

    if narrative:
        return RouteDecision(
            route=RetrievalRoute.BOTH,
            reason="names a stored figure and asks what the document says about it",
            **common,
        )

    if found_structured:
        return RouteDecision(
            route=RetrievalRoute.STRUCTURED,
            reason="names a stored figure and asks nothing narrative about it",
            **common,
        )

    # Nothing recognised. Retrieve both: structured costs nothing, and one
    # vector query is cheap insurance against missing an answer in the notes.
    return RouteDecision(
        route=RetrievalRoute.BOTH,
        reason="nothing specific recognised; retrieve both cheaply",
        **common,
    )


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------


def _stem(word: str) -> str:
    """Fold a trailing plural so ``borrowing`` matches ``borrowings``.

    Deliberately crude. It is applied identically to both sides of every
    comparison, so it only has to be *consistent* - it is not trying to be
    linguistically right, and a real stemmer would be a dependency bought for
    nothing.
    """
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _stems(text: str) -> set[str]:
    return {_stem(word) for word in text.split() if word not in _STOPWORDS}


def _content_words(phrase: str) -> frozenset[str]:
    return frozenset(
        _stem(word) for word in normalise(phrase).split() if word not in _STOPWORDS
    )


def _strip_out_of_scope(text: str) -> tuple[tuple[str, ...], str]:
    """Remove out-of-scope phrases, returning what matched and what is left."""
    found: list[str] = []
    remainder = f" {text} "
    # Longest first, so "operating cash flow" is recorded as itself rather than
    # leaving "operating" behind after "cash flow" is taken out of the middle.
    for phrase in sorted(OUT_OF_SCOPE_PHRASES, key=len, reverse=True):
        needle = f" {normalise(phrase)} "
        if needle in remainder:
            found.append(phrase)
            remainder = remainder.replace(needle, " ")
    return tuple(sorted(found)), remainder.strip()


@lru_cache(maxsize=1)
def _concept_index() -> tuple[dict[str, frozenset[str]], dict[str, str]]:
    """Matchable terms for every canonical concept, derived from Module 2 and 3.

    Two routes to a match, because neither alone is enough:

    *All the label's words.* ``short_term_borrowings`` is found by a question
    containing "short", "term" and "borrowing" - none of which is distinctive
    alone, since ``long_term_borrowings`` shares two of them.

    *One distinctive word.* "How much cash is there?" names only "cash", never
    "equivalents", so the whole-label rule misses it. A word qualifies as
    distinctive when it appears in exactly **one** category across every label
    and description - which makes the set self-maintaining as the taxonomy
    grows, rather than a list someone has to curate.
    """
    required: dict[str, frozenset[str]] = {}
    occurrences: dict[str, set[str]] = {}

    for category in taxonomy.CATEGORIES:
        label_words = _content_words(category.label.replace("_", " "))
        required[category.label] = label_words
        for word in label_words | _content_words(category.description):
            occurrences.setdefault(word, set()).add(category.label)

    for name in definitions.names():
        required[name] = _content_words(name.replace("_", " "))

    distinctive = {
        word: next(iter(owners))
        for word, owners in occurrences.items()
        if len(owners) == 1
    }
    return required, distinctive


def _concepts_in(words: set[str], text: str) -> tuple[str, ...]:
    required, distinctive = _concept_index()
    found = {
        name
        for name, needed in required.items()
        if needed and needed <= words
    }
    found |= {distinctive[word] for word in words if word in distinctive}
    return tuple(sorted(found))


@lru_cache(maxsize=1)
def _section_terms() -> dict[str, str]:
    """"total assets" and friends, derived from the taxonomy's own sections."""
    return {f"total {section.value}": section.value for section in taxonomy.Section}


def _sections_in(text: str) -> tuple[str, ...]:
    padded = f" {text} "
    return tuple(
        sorted(
            {
                section
                for phrase, section in _section_terms().items()
                if f" {phrase} " in padded
            }
        )
    )


def _document_labels_in(
    words: set[str], document: BalanceSheetDocument | None
) -> tuple[str, ...]:
    """Labels printed on *this* document that the question names.

    This is what lets a filing's own wording route correctly with no synonym
    table anywhere: "Sundry Debtors" is matchable because the document printed
    it, not because anyone wrote it down as meaning trade receivables.
    """
    if document is None or document.extracted is None:
        return ()

    found: list[str] = []
    for section_name in ("assets", "liabilities", "equity"):
        part = getattr(document.extracted, section_name)
        for item in part.line_items:
            needed = _content_words(item.label)
            if needed and needed <= words:
                found.append(item.label)
    return tuple(sorted(set(found)))


# Words that announce a request for a named financial measure. Used only to
# notice that one was asked for - never to guess which.
_METRIC_WORDS = frozenset({"ratio", "score", "multiple", "index", "coverage", "metric"})


def asks_for_unsupported_metric(question: str, decision: RouteDecision) -> bool:
    """Whether the question wants a measure this system does not compute.

    Deliberately narrow: it fires only when the question plainly asks for a
    named measure and none of the seven matched. "What is the Altman Z-score?"
    is refused with the available list rather than sent to a model that would
    cheerfully produce a number - and a number produced by a model looks
    exactly like a correct one.

    A question that merely mentions a ratio in passing ("is the ratio of
    inventory to assets high?") is left alone: it names a real concept, so it
    goes through the ordinary path, where the numeric verifier is what catches
    a computed answer.
    """
    if decision.route is RetrievalRoute.OUT_OF_SCOPE:
        return False  # already refused, and for a better-stated reason

    words = set(normalise(question).split())
    if not (words & _METRIC_WORDS):
        return False

    known_ratios = set(definitions.names())
    return not (set(decision.matched_concepts) & known_ratios) and not (
        decision.matched_concepts or decision.matched_labels or decision.matched_sections
    )


__all__ = [
    "ADVICE_PHRASES",
    "OUT_OF_SCOPE_PHRASES",
    "RouteDecision",
    "asks_for_unsupported_metric",
    "route",
]
