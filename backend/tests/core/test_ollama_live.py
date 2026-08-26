"""One real round trip against a running Ollama.

Almost nothing lives here on purpose. Every rule the normalization ladder
enforces - malformed JSON, an invalid label, a section mismatch, a low
confidence, an unreachable service - is tested against a stub provider, because
a live model offers no reliable way to produce those on demand. What is left is
the part only a live server can prove: that the request we send is one Ollama
accepts, and that a schema sent as ``format`` really does come back honoured.
"""

from __future__ import annotations

import pytest

from app.modules.extraction import taxonomy
from app.modules.extraction.schema import response_schema
from app.modules.extraction.taxonomy import Section, Subsection


class TestLiveRoundTrip:
    async def test_the_model_answers_within_the_schema(self, ollama_provider) -> None:
        allowed = taxonomy.labels_for(Section.ASSETS, Subsection.CURRENT)
        result = await ollama_provider.complete_json(
            prompt=(
                "Classify the Balance Sheet line item 'Trade Debtors', printed "
                "under current assets. Answer with one category from: "
                + ", ".join(allowed)
            ),
            schema=response_schema(allowed),
            options={"temperature": 0},
        )

        assert set(result.payload) >= {"reasoning", "canonical_label", "confidence"}
        assert result.model == ollama_provider.model

    async def test_the_enum_constraint_is_actually_enforced(self, ollama_provider) -> None:
        """The claim the whole design rests on.

        If ``format`` were being ignored, an invented category would reach the
        validation ladder instead of being structurally impossible - and the
        ladder is the only thing that would then be standing between a made-up
        label and the stored document.
        """
        allowed = taxonomy.labels_for(Section.ASSETS, Subsection.CURRENT)
        result = await ollama_provider.complete_json(
            prompt=(
                "Classify the Balance Sheet line item 'Trade Debtors', printed "
                "under current assets."
            ),
            schema=response_schema(allowed),
            options={"temperature": 0},
        )

        assert result.payload["canonical_label"] in {*allowed, taxonomy.UNKNOWN}

    async def test_it_can_map_a_synonym_the_dictionary_does_not_know(
        self, ollama_provider
    ) -> None:
        """The job itself, end to end, on the real model.

        Not asserted as a correctness bar - that is what the benchmark measures
        across candidates. This only proves the path works.
        """
        from app.modules.extraction.normalization import Normalizer

        outcome = await Normalizer(provider=ollama_provider).normalize(
            "Trade Debtors", section=Section.ASSETS, subsection=Subsection.CURRENT
        )

        assert outcome.canonical_label in {
            *taxonomy.labels_for(Section.ASSETS, Subsection.CURRENT),
            None,
        }
        if outcome.canonical_label is None:
            pytest.skip(f"the model declined: {outcome.reason}")
