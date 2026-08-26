"""The model comparison, as an opt-in test run.

    pytest -m benchmark --require-ollama

Slow by construction - it puts every candidate through 75 cases on a laptop
GPU - so it is marked ``benchmark`` and excluded from every normal run. It is
not a pass/fail gate on the code; it is the measurement that decides which
model ``OLLAMA_MODEL`` should name.

The dataset itself is checked here too, and those checks *are* pure. A
benchmark with a duplicated case or an expected label outside the taxonomy
measures the wrong thing quietly, which is worse than not measuring.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.extraction import taxonomy
from app.modules.extraction.taxonomy import Section, Subsection

BENCHMARKS = Path(__file__).resolve().parents[2] / "benchmarks"


def load_cases() -> list[dict]:
    data = json.loads((BENCHMARKS / "normalization_cases.json").read_text(encoding="utf-8"))
    return data["cases"]


class TestTheDatasetIsSound:
    """Pure checks. A silently wrong dataset measures the wrong thing."""

    def test_every_expected_label_is_in_the_taxonomy(self) -> None:
        for case in load_cases():
            if case["expected"] is not None:
                assert taxonomy.get(case["expected"]) is not None, case["label"]

    def test_every_expected_label_fits_the_section_it_is_filed_under(self) -> None:
        """Otherwise the validation ladder would reject a case we call correct."""
        for case in load_cases():
            if case["expected"] is None:
                continue
            section = Section(case["section"])
            subsection = Subsection(case["subsection"]) if case["subsection"] else None
            assert taxonomy.fits(case["expected"], section, subsection), case["label"]

    def test_labels_are_unique(self) -> None:
        labels = [case["label"] for case in load_cases()]
        assert len(labels) == len(set(labels))

    def test_no_case_is_already_in_the_identity_dictionary(self) -> None:
        """A case the dictionary answers measures our plumbing, not the model.

        The canonical spellings are deliberately present in the "standard"
        group as a floor, so they are exempt - but a synonym or abbreviation
        that resolves locally would inflate the score for free.
        """
        from app.modules.extraction import aliases

        for case in load_cases():
            if case["group"] in {"standard"}:
                continue
            assert aliases.lookup(case["label"]) is None, (
                f"{case['label']!r} is answered by the dictionary, so it "
                "measures nothing about the model"
            )

    def test_there_are_enough_cases_where_declining_is_correct(self) -> None:
        """Scored separately, so they have to exist in usable numbers.

        A model that never abstains scores well on everything else and is
        dangerous in production; this is the only part of the set that catches
        it.
        """
        abstaining = [c for c in load_cases() if c["expected"] is None]
        assert len(abstaining) >= 10


@pytest.mark.benchmark
class TestModelComparison:
    async def test_run_the_candidates(self, ollama_provider) -> None:
        """Measure whichever candidates are actually pulled, and write the table.

        Candidates that are not installed are reported and skipped rather than
        failing the run: pulling four models is ~20 GB, and a partial
        comparison is still a comparison as long as it says what it covered.
        """
        from benchmarks.runner import CANDIDATES, RESULTS, run_model, write_table

        installed = set(ollama_provider.installed_models() or [])
        present = [model for model in CANDIDATES if model in installed]
        missing = [model for model in CANDIDATES if model not in installed]

        if not present:
            pytest.skip(
                "None of the candidate models are pulled. Run: "
                + "; ".join(f"ollama pull {model}" for model in CANDIDATES)
            )

        RESULTS.mkdir(parents=True, exist_ok=True)
        cases = load_cases()

        for model in present:
            result = await run_model(model, cases)
            slug = model.replace("/", "_").replace(":", "_")
            (RESULTS / f"{slug}.json").write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8"
            )
            metrics = result["metrics"]

            # Not a quality bar - the comparison decides that. This only
            # asserts the measurement itself is meaningful.
            assert metrics["cases"] == len(cases)
            assert metrics["malformed_rate"] < 1.0, f"{model} returned nothing usable"

        table = write_table()
        print(f"\n{table}")
        if missing:
            print(f"\nNot measured (not pulled): {', '.join(missing)}")
