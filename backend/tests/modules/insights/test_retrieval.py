"""Ranking, filtering and ordering retrieved passages.

Pure unit tests. Ollama returns unit vectors, so cosine is the dot product and
ranking needs no model, no database and no numerical dependency to exercise -
the same reason the exact fallback is cheap enough to be a real fallback rather
than a stub.
"""

from __future__ import annotations

import math

import pytest

from app.core.schemas import DocumentChunk, EvidenceKind, PageRole
from app.modules.insights.retrieval import (
    SIMILARITY_FLOOR,
    ScoredChunk,
    in_reading_order,
    rank,
    to_evidence,
)


def _unit(*values: float) -> list[float]:
    """A unit vector, so cosine behaves as Atlas's does."""
    length = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / length for value in values]


def _chunk(
    text: str,
    embedding: list[float],
    *,
    page: int = 0,
    index: int = 0,
    role: PageRole = PageRole.SUPPLEMENTARY,
    chunk_id: str | None = None,
) -> DocumentChunk:
    return DocumentChunk(
        _id=chunk_id,
        document_id="652f1a2b3c4d5e6f70819200",
        page_index=page,
        page_role=role,
        chunk_index=index,
        char_start=0,
        char_end=len(text),
        text=text,
        embedding=embedding,
        embedding_model="test-embed",
        embedding_dim=len(embedding),
        chunk_spec_version="1.0.0",
    )


class TestRanking:
    def test_the_closest_passage_is_kept(self) -> None:
        query = _unit(1, 0, 0)
        chunks = [
            _chunk("far", _unit(0, 1, 0), index=0),
            _chunk("near", _unit(0.95, 0.05, 0), index=1),
        ]
        [best] = rank(query, chunks, top_k=1)
        assert best.chunk.text == "near"

    def test_top_k_is_respected(self) -> None:
        query = _unit(1, 0)
        chunks = [_chunk(f"c{n}", _unit(1, 0), index=n) for n in range(10)]
        assert len(rank(query, chunks, top_k=3)) == 3

    def test_ranking_is_deterministic_on_identical_passages(self) -> None:
        """Two identical chunks must not swap places between runs."""
        query = _unit(1, 0)
        chunks = [_chunk("same", _unit(1, 0), index=n) for n in range(4)]

        first = [entry.chunk.chunk_index for entry in rank(query, chunks, top_k=2)]
        second = [entry.chunk.chunk_index for entry in rank(query, chunks, top_k=2)]
        assert first == second

    def test_an_empty_corpus_returns_nothing(self) -> None:
        assert rank(_unit(1, 0), []) == []


class TestTheSimilarityFloor:
    def test_an_irrelevant_passage_is_dropped_not_padded_in(self) -> None:
        """Filling the context with near-misses is how a model gets misled."""
        query = _unit(1, 0)
        chunks = [_chunk("unrelated", _unit(0, 1))]
        assert rank(query, chunks) == []

    def test_everything_below_the_floor_yields_nothing_at_all(self) -> None:
        """Which the caller reads as "the text path found nothing"."""
        query = _unit(1, 0)
        chunks = [_chunk(f"c{n}", _unit(0, 1), index=n) for n in range(5)]
        assert rank(query, chunks) == []

    def test_a_passage_exactly_at_the_floor_is_kept(self) -> None:
        query = _unit(1, 0)
        angle = math.acos(SIMILARITY_FLOOR)
        at_floor = _unit(math.cos(angle), math.sin(angle))
        assert len(rank(query, [_chunk("borderline", at_floor)])) == 1

    def test_the_floor_is_a_constant_not_a_setting(self) -> None:
        """A deployment able to tune this could change an answer silently."""
        from app.core.config import Settings

        assert not any("similarit" in name.lower() for name in Settings.model_fields)


class TestReadingOrder:
    def test_results_come_back_in_document_order_not_score_order(self) -> None:
        """Relevance chooses which passages; the document chooses their order."""
        query = _unit(1, 0)
        chunks = [
            _chunk("later page, best match", _unit(1, 0), page=3, index=0),
            _chunk("earlier page, weaker", _unit(0.9, 0.44), page=1, index=0),
        ]
        pages = [entry.chunk.page_index for entry in rank(query, chunks, top_k=2)]
        assert pages == [1, 3]

    def test_it_orders_within_a_page_too(self) -> None:
        scored = [
            ScoredChunk(chunk=_chunk("b", _unit(1, 0), page=0, index=2), score=0.9),
            ScoredChunk(chunk=_chunk("a", _unit(1, 0), page=0, index=0), score=0.8),
        ]
        assert [entry.chunk.chunk_index for entry in in_reading_order(scored)] == [0, 2]


class TestEvidenceTagging:
    def test_passages_are_tagged_for_citation(self) -> None:
        scored = [
            ScoredChunk(chunk=_chunk("first", _unit(1, 0), page=0), score=0.9),
            ScoredChunk(chunk=_chunk("second", _unit(1, 0), page=1), score=0.8),
        ]
        evidence = to_evidence(scored)

        assert [entry.id for entry in evidence] == ["C1", "C2"]
        assert all(entry.kind is EvidenceKind.TEXT for entry in evidence)

    def test_each_carries_its_page_and_chunk_for_resolution(self) -> None:
        scored = [
            ScoredChunk(
                chunk=_chunk("policy text", _unit(1, 0), page=3, chunk_id="abc"),
                score=0.9,
            )
        ]
        [evidence] = to_evidence(scored)

        assert evidence.page_index == 3
        assert evidence.label == "page 4"  # 1-based for a human reader
        assert evidence.chunk_id == "abc"
        assert evidence.quote == "policy text"

    def test_nothing_retrieved_means_nothing_to_cite(self) -> None:
        assert to_evidence([]) == []


class TestScoreConversion:
    def test_atlas_scores_are_converted_back_to_raw_cosine(self) -> None:
        """Atlas reports (1 + cosine) / 2, so the floor must mean one thing.

        Without this the same constant would be strict in the exact path and
        lax against Atlas, and only the fallback would ever get tuned.
        """
        from app.modules.insights.retrieval import _to_cosine

        assert _to_cosine(1.0) == 1.0
        assert _to_cosine(0.5) == 0.0
        assert _to_cosine(0.775) == pytest.approx(0.55)
