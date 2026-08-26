"""Measure candidate local models on the job Module 2 actually does.

The point of this file is that **no model is called better until it has been
measured here**, on this laptop, against these cases. Published benchmarks
measure other tasks on other hardware; what matters is whether a model can map
"Sundry Debtors" onto ``trade_receivables`` and abstain on "Miscellaneous
Financial Assets", in a few seconds, inside 8 GB of VRAM.

Run it from the backend directory with Ollama running::

    python -m benchmarks.runner                       # every candidate
    python -m benchmarks.runner --models qwen3:4b     # just one

Results are written to ``benchmarks/results/`` as JSON, plus a markdown table
comparing whatever has been run so far.

**Accuracy and abstention are scored separately, and deliberately.** A model
that never says "I don't know" scores well on the easy cases and is dangerous
in production, because on the ambiguous ones it will produce a confident wrong
category that nothing downstream can detect. Reporting one number would hide
exactly the failure mode worth knowing about.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.llm.ollama import build_llm_provider
from app.modules.extraction import taxonomy
from app.modules.extraction.normalization import Normalizer
from app.modules.extraction.taxonomy import Section, Subsection

BENCHMARKS = Path(__file__).parent
RESULTS = BENCHMARKS / "results"

# The shortlist. Every one has to fit in 8 GB of VRAM at Q4_K_M alongside its
# KV cache, which is the binding constraint on this hardware.
#
# `finance-llama-8b` is here as the hypothesis to disprove, not as a favourite:
# it is tuned on financial QA, sentiment and NER, none of which is
# label-to-taxonomy mapping, and domain fine-tunes commonly lose the
# instruction-following and JSON discipline of the base model they came from.
# Tags must match `ollama list` exactly. The finance model publishes an
# explicit quantisation tag rather than a `latest`, and asking for the bare
# name 404s on every request - which the first run did, silently producing a
# full result file in which nothing had been measured.
CANDIDATES: tuple[str, ...] = (
    "qwen3:8b",
    "qwen3:4b",
    "llama3.1:8b",
    "martain7r/finance-llama-8b:q4_k_m",
)

# Groups where the right answer is a category, scored on exact match.
RESOLVABLE = {"standard", "synonym", "abbreviation", "unusual"}
# Groups where the right answer is to decline. Scored separately.
ABSTAINING = {"ambiguous", "unknown"}

# Outcomes where the model never gave an answer at all - the request failed, or
# the service could not serve the model. Declining to answer is a *decision*
# and scores; failing to be asked is not and must not.
_ERROR_REASONS = {"llm_unavailable", "provider_error"}


def _is_correct(expected: str | None, actual: str | None, errored: bool) -> bool:
    """Whether the model got this case right.

    An errored case is never correct, including on the abstention cases. A
    model that cannot be reached abstains from everything perfectly, and
    rewarding that turns the safety metric into a measure of being switched
    off.
    """
    if errored:
        return False
    return actual == expected if expected else actual is None


def load_cases() -> list[dict[str, Any]]:
    data = json.loads((BENCHMARKS / "normalization_cases.json").read_text(encoding="utf-8"))
    return data["cases"]


def peak_vram_mb() -> float | None:
    """What the GPU is currently holding, via nvidia-smi. ``None`` if absent."""
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
        return max(float(line) for line in output.split() if line.strip())
    except Exception:  # noqa: BLE001 - absent GPU or tool is not an error here
        return None


async def run_model(model: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Put one model through every case and record what happened."""
    settings = get_settings()
    provider = build_llm_provider(
        host=settings.ollama_host,
        model=model,
        timeout_s=settings.ollama_timeout_s,
        num_ctx=settings.ollama_num_ctx,
    )
    installed = provider.installed_models()
    if installed is None:
        raise SystemExit(f"Ollama is not reachable at {settings.ollama_host}.")
    if model not in installed:
        # Refused rather than run. A model that 404s on every request still
        # produces a complete-looking result file - 75 rows, plausible
        # latencies, and a perfect abstention score, because a model that never
        # answers never answers wrongly. That is a fabricated result, and it is
        # exactly what the first run of this benchmark produced.
        raise SystemExit(
            f"{model!r} is not installed. Tags must match `ollama list` "
            f"exactly.\nInstalled: {', '.join(installed) or '(nothing)'}"
        )

    baseline_vram = peak_vram_mb()
    records: list[dict[str, Any]] = []
    latencies: list[float] = []

    for case in cases:
        # A fresh Normalizer per case: the cache and the identity dictionary
        # are what we are deliberately *not* measuring here. This has to be the
        # model's own score, or the benchmark measures our plumbing.
        subject = Normalizer(provider=provider, confidence_floor=0.0, retries=0)
        section = Section(case["section"])
        subsection = Subsection(case["subsection"]) if case["subsection"] else None

        started = time.perf_counter()
        outcome = await subject._ask(  # noqa: SLF001 - the LLM path is the subject
            case["label"],
            section=section,
            subsection=subsection,
            neighbours=tuple(case.get("neighbours", ())),
            currency=None,
        )
        elapsed = time.perf_counter() - started
        latencies.append(elapsed)

        expected = case["expected"]
        actual = outcome.canonical_label
        # A case the model never actually answered is an error, not a decision.
        # Counting it as a correct abstention is what let a model that 404'd on
        # every request score 100% on the metric that exists to catch unsafe
        # guessing.
        errored = outcome.reason in _ERROR_REASONS

        records.append(
            {
                "label": case["label"],
                "group": case["group"],
                "expected": expected,
                "actual": actual,
                "reason": outcome.reason,
                "confidence": outcome.confidence,
                "errored": errored,
                "correct": _is_correct(expected, actual, errored),
                "seconds": round(elapsed, 3),
            }
        )
        print(
            f"  {case['label'][:38]:40} -> {str(actual):32} "
            f"{'ok' if records[-1]['correct'] else 'MISS':4} {elapsed:5.2f}s"
        )

    return {
        "model": model,
        "taxonomy_version": taxonomy.TAXONOMY_VERSION,
        "case_version": json.loads(
            (BENCHMARKS / "normalization_cases.json").read_text(encoding="utf-8")
        )["version"],
        "metrics": _metrics(
            records,
            latencies,
            baseline_vram=baseline_vram,
            # Read while the model is still resident - Ollama unloads it after
            # a few idle minutes, and a reading taken later measures nothing.
            loaded_vram=peak_vram_mb(),
        ),
        "records": records,
    }


def _metrics(
    records: list[dict[str, Any]],
    latencies: list[float],
    *,
    baseline_vram: float | None = None,
    loaded_vram: float | None = None,
) -> dict[str, Any]:
    resolvable = [r for r in records if r["group"] in RESOLVABLE]
    abstaining = [r for r in records if r["group"] in ABSTAINING]
    errored = [r for r in records if r.get("errored")]

    # Constrained decoding should make this zero. Anything else means the
    # grammar is not being applied, which is a finding about the transport
    # rather than about the model.
    invalid = [r for r in records if r["reason"] == "invalid_label"]
    malformed = [r for r in records if r["reason"] == "incomplete_response"]
    mismatched = [r for r in records if r["reason"] == "section_mismatch"]

    def rate(subset: list[dict[str, Any]], total: list[dict[str, Any]]) -> float:
        return round(len(subset) / len(total), 4) if total else 0.0

    # The first call pays for loading several GB of weights into VRAM; every
    # call after it does not. Averaging the two together describes neither, and
    # on a laptop GPU the cold number is the one a user actually feels on the
    # first upload after a restart.
    cold = latencies[0] if latencies else None
    warm = latencies[1:]

    return {
        "accuracy_resolvable": rate([r for r in resolvable if r["correct"]], resolvable),
        "abstention_accuracy": rate([r for r in abstaining if r["correct"]], abstaining),
        # A model that never abstains scores well above and is dangerous below.
        "over_answered": rate(
            [r for r in abstaining if not r.get("errored") and r["actual"] is not None],
            abstaining,
        ),
        # Anything above zero means the run did not measure what it claims to.
        "unavailable_rate": rate(errored, records),
        "invalid_label_rate": rate(invalid, records),
        "malformed_rate": rate(malformed, records),
        "section_mismatch_rate": rate(mismatched, records),
        "latency_cold_s": round(cold, 2) if cold is not None else None,
        "latency_warm_mean_s": round(statistics.mean(warm), 2) if warm else None,
        "latency_warm_p95_s": (
            round(sorted(warm)[int(len(warm) * 0.95) - 1], 2) if len(warm) >= 20 else None
        ),
        "latency_mean_s": round(statistics.mean(latencies), 2) if latencies else None,
        # Absolute reading minus whatever the GPU was already holding, so the
        # figure is this model's footprint rather than the desktop's too.
        "vram_baseline_mb": baseline_vram,
        "vram_loaded_mb": loaded_vram,
        "vram_model_mb": (
            round(loaded_vram - baseline_vram)
            if loaded_vram is not None and baseline_vram is not None
            else None
        ),
        "cases": len(records),
    }


def write_table() -> str:
    """A markdown comparison of every model measured so far."""
    rows = []
    for path in sorted(RESULTS.glob("*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        metrics = result["metrics"]
        unavailable = metrics.get("unavailable_rate", 0.0)
        rows.append(
            "| {model} | {acc:.0%} | {abst:.0%} | {over:.0%} | {cold} | {warm} | "
            "{vram} | {unavail} |".format(
                model=result["model"],
                acc=metrics["accuracy_resolvable"],
                abst=metrics["abstention_accuracy"],
                over=metrics["over_answered"],
                cold=f"{metrics['latency_cold_s']}s" if metrics.get("latency_cold_s") else "n/a",
                warm=(
                    f"{metrics['latency_warm_mean_s']}s"
                    if metrics.get("latency_warm_mean_s")
                    else "n/a"
                ),
                vram=metrics.get("vram_model_mb") or metrics.get("vram_loaded_mb") or "n/a",
                unavail="-" if not unavailable else f"**{unavailable:.0%}**",
            )
        )

    table = "\n".join(
        [
            "| Model | Accuracy | Abstained correctly | Over-answered | Cold | Warm mean | VRAM (MB) | Unmeasured |",
            "|---|---|---|---|---|---|---|---|",
            *rows,
        ]
    )
    (RESULTS / "comparison.md").write_text(
        "# Model comparison\n\n"
        "Measured on this machine against `normalization_cases.json`. "
        "**No winner is declared here** - this is the evidence, not the decision.\n\n"
        "**Accuracy** is exact canonical-label match on the cases that have a "
        "right answer. **Abstained correctly** is the ambiguous and unknown "
        "cases the model declined, and **over-answered** is the same set it "
        "answered anyway - a high score in the first column with a high "
        "over-answered rate is a model that guesses well, which is not the "
        "same thing as a model that is right.\n\n"
        "**Cold** is the first request, which pays to load the weights into "
        "VRAM; **warm mean** is every request after it. Averaging the two "
        "describes neither.\n\n"
        "**Unmeasured** is the share of cases the model never actually "
        "answered. It must be blank. Anything else means the run did not "
        "measure what the other columns claim - a model that 404s on every "
        "request abstains from everything perfectly.\n\n" + table + "\n",
        encoding="utf-8",
    )
    return table


def recompute(path: Path) -> None:
    """Rescore a stored run from its own records, without calling the model.

    The records hold every answer, its reason and its latency, so a change to
    how a run is *scored* does not need the run repeating - and re-running
    would change the numbers for unrelated reasons anyway.
    """
    result = json.loads(path.read_text(encoding="utf-8"))
    records = result["records"]
    for record in records:
        errored = record.get("reason") in _ERROR_REASONS
        record["errored"] = errored
        record["correct"] = _is_correct(record["expected"], record["actual"], errored)

    old = result.get("metrics", {})
    result["metrics"] = _metrics(
        records,
        [record["seconds"] for record in records],
        baseline_vram=old.get("vram_baseline_mb"),
        loaded_vram=old.get("vram_loaded_mb") or old.get("vram_mb_after"),
    )
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="*", default=list(CANDIDATES))
    parser.add_argument(
        "--recompute",
        action="store_true",
        help="Rescore stored runs from their records instead of calling any model.",
    )
    args = parser.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)

    if args.recompute:
        for path in sorted(RESULTS.glob("*.json")):
            recompute(path)
            print(f"  rescored {path.name}")
        print("\n" + write_table())
        return

    cases = load_cases()

    for model in args.models:
        print(f"\n=== {model} ({len(cases)} cases) ===")
        result = await run_model(model, cases)
        slug = model.replace("/", "_").replace(":", "_")
        (RESULTS / f"{slug}.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        metrics = result["metrics"]
        print(
            f"  accuracy {metrics['accuracy_resolvable']:.0%} | "
            f"abstained correctly {metrics['abstention_accuracy']:.0%} | "
            f"mean {metrics['latency_mean_s']}s"
        )

    print("\n" + write_table())


if __name__ == "__main__":
    asyncio.run(main())
