"""Label text shaping: shape only, never meaning."""

from __future__ import annotations

import pytest

from app.core import text as core_text


class TestNormalise:
    def test_it_lowercases_and_collapses_whitespace(self) -> None:
        assert core_text.normalise("  TOTAL   ASSETS \n") == "total assets"

    def test_a_typographic_apostrophe_matches_a_plain_one(self) -> None:
        """PDF fonts render an apostrophe as U+2019; the label is ordinary."""
        assert core_text.normalise("SHAREHOLDERS\u2019 EQUITY") == "shareholders equity"

    @pytest.mark.parametrize("label", ["A + B", "A+B", "A & B", "A&B"])
    def test_connector_symbols_fold_to_the_word_and(self, label: str) -> None:
        assert core_text.normalise(label) == "a and b"

    def test_a_slash_is_left_alone(self) -> None:
        """It separates the parts of a date far more often than two nouns."""
        assert core_text.normalise("As at 31/03/2024") == "as at 31 03 2024"
