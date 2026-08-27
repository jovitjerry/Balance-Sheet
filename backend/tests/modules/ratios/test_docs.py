"""The generated ratio reference must match the declarations it came from.

``docs/RATIOS.md`` is quoted in the project report. A reference that has drifted
from the code is worse than no reference at all: it documents a formula the
system does not apply, and nothing about reading it would reveal that.
"""

from __future__ import annotations

from pathlib import Path

from app.modules.ratios import definitions
from scripts.generate_ratio_docs import DOCS, render


class TestGeneratedReference:
    def test_the_checked_in_file_is_current(self) -> None:
        """Regenerate with: python -m scripts.generate_ratio_docs"""
        assert DOCS.exists(), "docs/RATIOS.md has not been generated"
        assert DOCS.read_text(encoding="utf-8") == render(), (
            "docs/RATIOS.md is out of date with definitions.py - "
            "run `python -m scripts.generate_ratio_docs`"
        )

    def test_every_ratio_appears(self) -> None:
        text = render()
        for name in definitions.names():
            assert f"### `{name}`" in text

    def test_it_records_both_versions(self) -> None:
        """A reader must be able to tell which formulas and which vocabulary."""
        text = render()
        assert definitions.RATIO_SPEC_VERSION in text

    def test_it_states_the_scope_limits(self) -> None:
        text = render()
        assert "single reporting period" in text
        assert "Income Statement" in text

    def test_it_says_no_model_computes_anything(self) -> None:
        assert "No language model is involved" in render()

    def test_it_is_marked_as_generated(self) -> None:
        """So nobody edits it and loses the edit on the next run."""
        assert "Do not edit by hand" in render()

    def test_it_lives_where_the_report_can_find_it(self) -> None:
        assert DOCS.name == "RATIOS.md"
        assert DOCS.parent.name == "docs"
        assert isinstance(DOCS, Path)
