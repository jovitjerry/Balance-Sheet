"""Score candidate models on Module 4 generation and financial reasoning.

    python -m benchmarks.reasoning_runner                 # every candidate
    python -m benchmarks.reasoning_runner --models qwen3:4b
    python -m benchmarks.reasoning_runner --rescore       # Tier 1 only, no model called
    python -m benchmarks.reasoning_runner --unblind       # after scoring is fixed

**Why this exists.** Module 4 verifies that every figure in an answer appears in
its context, and that works. It is not enough. Handed the correct
``current_ratio = 1.307692``, a candidate wrote that the company had "weak
liquidity" and could not pay its bills - the opposite of what 850,000 against
650,000 shows. Every figure was right, so every numeric check passed. That is a
reasoning failure wearing correct figures, and no grounding check can catch it.

**Two tiers, and the split is the point.**

*Tier 1* is automated and objective: figures grounded, required facts stated,
forbidden claims absent, refusals made, citations resolvable, schema honoured.
It reuses the shipped ``verification.py`` so the benchmark cannot drift from
production. It verifies **necessary conditions only** - the failure above passes
every Tier 1 gate.

*Tier 2* is the human dimensions - reasoning, interpretation, clarity - scored
blind from ``reasoning_answers_blind.md``. Tier 1 is a floor, never a grade.

Nothing here touches production code or ``OLLAMA_MODEL``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import shutil
import statistics
import subprocess
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.llm.ollama import build_llm_provider
from app.modules.insights import prompts
from app.modules.insights.context import Context
from app.modules.insights.schema import answer_schema
from app.modules.insights.verification import allowed_figures, extract_numbers, verify
from benchmarks.qa_runner import _REFUSAL_PHRASES
from benchmarks.reasoning_context import FROZEN, load_cases
from benchmarks.runner import CANDIDATES, RESULTS, peak_vram_mb

# Fixed so the blinding reproduces. Changing it reshuffles the keying and
# invalidates any scoresheet already written against the old order.
BLIND_SEED = 20260827

# Characters of surrounding text kept with every phrase match, so a human can
# see whether the phrase was negated before treating the flag as a failure.
_WINDOW = 70


# --------------------------------------------------------------------------
# Tier 1 - automated gates
# --------------------------------------------------------------------------


def _find(haystack: str, phrases: list[str] | tuple[str, ...]) -> list[dict[str, str]]:
    """Every phrase that appears, with the text around it.

    Substring matching, and deliberately reported with context rather than as a
    bare boolean: "the company is not unable to pay" contains "unable to pay",
    and only a reader can tell those apart. The window is what makes the flag
    adjudicable instead of merely alarming.
    """
    lowered = haystack.lower()
    found: list[dict[str, str]] = []
    for phrase in phrases:
        position = lowered.find(phrase.lower())
        if position == -1:
            continue
        start = max(0, position - _WINDOW)
        end = min(len(haystack), position + len(phrase) + _WINDOW)
        found.append({"phrase": phrase, "context": haystack[start:end].strip()})
    return found


# A reply that is technically schema-valid but says nothing. The first trial run
# produced the literal answer "false" for the investment question - the model
# appears to have emitted the `sufficient` boolean into the answer field. That
# is neither a refusal nor advice, and scoring it as "did not refuse" described
# the wrong failure.
_MIN_ANSWER_CHARS = 25
_NON_ANSWERS = {"true", "false", "null", "none", "n/a", "yes", "no", ""}


def _is_degenerate(answer: str) -> bool:
    stripped = answer.strip().rstrip(".").lower()
    return stripped in _NON_ANSWERS or len(answer.strip()) < _MIN_ANSWER_CHARS


@lru_cache(maxsize=1)
def _hedging_phrases() -> tuple[str, ...]:
    """Uncertainty wording, read once rather than per answer."""
    return tuple(load_cases()["hedging_phrases"])


def _states_any(answer: str, figures: list[float | int]) -> list[str]:
    """Which required figures the answer states, tolerant of how they are written."""
    from decimal import Decimal

    present = extract_numbers(answer)
    stated: list[str] = []
    for figure in figures:
        target = Decimal(str(figure))
        places = -target.as_tuple().exponent
        quantum = Decimal(1).scaleb(-places) if places > 0 else Decimal(1)
        if any(value.quantize(quantum) == target for value in present):
            stated.append(str(figure))
    return stated


def tier1(
    case: dict[str, Any], frozen: dict[str, Any], reply: dict[str, Any] | None, answer: str
) -> dict[str, Any]:
    """Run every automated gate over one answer.

    Returns what was checked, never a verdict on quality - which is exactly the
    distinction the Module 2 benchmark got wrong by reporting figure presence as
    though it were a score.
    """
    if reply is None:
        return {"schema_valid": False, "gates_passed": False, "critical_automated": True}

    context = Context(
        text=frozen["context_text"], evidence=(), groundable=frozen["groundable_text"]
    )
    allowed = allowed_figures(context)
    grounding = verify(answer, figures_used=reply.get("figures_used", []), allowed=allowed)

    required = case.get("must_state_any", [])
    stated = _states_any(answer, required)

    mentions = case.get("must_mention_any", [])
    mentioned = [m for m in mentions if m.lower() in answer.lower()]

    forbidden: dict[str, list[dict[str, str]]] = {}
    for group, phrases in case.get("forbidden_claims", {}).items():
        hits = _find(answer, phrases)
        if hits:
            forbidden[group] = hits

    hedged = _find(answer, _hedging_phrases())
    refused = bool(_find(answer.lower(), list(_REFUSAL_PHRASES)))
    degenerate = _is_degenerate(answer)

    tags = reply.get("citations", [])
    unresolvable = [tag for tag in tags if tag not in frozen["citation_ids"]]

    result: dict[str, Any] = {
        "schema_valid": True,
        "grounded": grounding.passed,
        "figures_unverified": list(grounding.unverified),
        "required_figures": [str(f) for f in required],
        "required_stated": stated,
        "required_met": (not required) or bool(stated),
        "must_mention_met": (not mentions) or bool(mentioned),
        "forbidden_matched": forbidden,
        "hedged": bool(hedged),
        "hedging_met": (not case.get("requires_hedging")) or bool(hedged),
        "refused": refused,
        "refusal_met": (not case.get("must_refuse")) or refused,
        "degenerate": degenerate,
        "citations_returned": tags,
        "citations_unresolvable": unresolvable,
        "citation_required_met": (not case.get("requires_citation")) or bool(tags),
        "model_said_sufficient": reply.get("sufficient"),
    }

    result["gates_passed"] = all(
        (
            not degenerate,
            result["grounded"],
            result["required_met"],
            result["must_mention_met"],
            not forbidden,
            result["hedging_met"],
            result["refusal_met"],
            not unresolvable,
            result["citation_required_met"],
        )
    )
    # An automated *candidate* for critical, not a verdict. The human decides,
    # and the disagreement between the two is itself reported.
    # A degenerate reply is a generation failure, not a safety failure - it is
    # reported in its own column rather than counted as though the model had
    # given dangerous advice.
    result["critical_automated"] = bool(forbidden) or (
        not result["refusal_met"] and not degenerate
    )
    return result


# --------------------------------------------------------------------------
# Running one model
# --------------------------------------------------------------------------


def _template(name: str) -> str:
    return getattr(prompts, name)


async def run_model(model: str, frozen: dict[str, Any], cases: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    provider = build_llm_provider(
        host=settings.ollama_host,
        model=model,
        timeout_s=settings.ollama_timeout_s,
        num_ctx=max(settings.ollama_num_ctx, 4096),
    )
    installed = provider.installed_models()
    if installed is None:
        raise SystemExit(f"Ollama is not reachable at {settings.ollama_host}.")
    if model not in installed:
        raise SystemExit(
            f"{model!r} is not installed. Tags must match `ollama list` exactly.\n"
            f"Installed: {', '.join(installed) or '(nothing)'}\n"
            "The first Module 2 run asked for a tag that did not exist and produced "
            "a complete-looking result file in which nothing had been measured."
        )

    # Evict first, so every candidate pays a real cold start. Without this the
    # first model measured is whichever happened to be resident already - the
    # trial run reported 12.68s for a model Module 2 measured at 80.9s cold,
    # purely because it was still loaded from earlier work.
    _unload(model)

    baseline = peak_vram_mb()
    by_id = {q["id"]: q for q in cases["questions"]}
    records: list[dict[str, Any]] = []
    latencies: list[float] = []
    cold: float | None = None

    for index, (qid, entry) in enumerate(frozen["questions"].items()):
        case = by_id[qid]
        prompt = prompts.build(
            _template(entry["template"]),
            context=entry["context_text"],
            question=entry["question"],
        )
        schema = answer_schema(entry["citation_ids"])

        started = time.perf_counter()
        reply: dict[str, Any] | None = None
        answer = ""
        error: str | None = None
        try:
            result = await provider.complete_json(
                prompt=prompt, schema=schema, options={"temperature": 0}
            )
            payload = result.payload
            if isinstance(payload, dict) and isinstance(payload.get("answer"), str):
                reply = payload
                answer = payload["answer"].strip()
        except Exception as exc:  # noqa: BLE001 - recorded, never hidden
            error = str(exc)
        elapsed = time.perf_counter() - started

        if index == 0:
            cold = elapsed  # first call pays the model load
        else:
            latencies.append(elapsed)

        gates = tier1(case, entry, reply, answer)
        records.append(
            {
                "id": qid,
                "category": case["category"],
                "question": entry["question"],
                "route": entry["route"],
                "refused_before_model_in_production": entry["refused_before_model"],
                "template": entry["template"],
                "answer": answer,
                "raw_reply": reply,
                "error": error,
                "seconds": round(elapsed, 2),
                "tier1": gates,
            }
        )
        print(f"  {qid:4} {_mark(records[-1]):26} {elapsed:6.2f}s")

    scored = [r for r in records if r["tier1"].get("schema_valid")]
    return {
        "model": model,
        "cases_version": cases["version"],
        "rag_spec_version": frozen["rag_spec_version"],
        "retrieval": frozen["retrieval"],
        "metrics": {
            "questions": len(records),
            "schema_valid": len(scored),
            "gates_passed": len([r for r in scored if r["tier1"]["gates_passed"]]),
            "grounded": len([r for r in scored if r["tier1"]["grounded"]]),
            "forbidden_claims": len([r for r in scored if r["tier1"]["forbidden_matched"]]),
            "degenerate": len([r for r in scored if r["tier1"].get("degenerate")]),
            "refusals_met": len([r for r in scored if r["tier1"]["refusal_met"]]),
            "citations_unresolvable": len(
                [r for r in scored if r["tier1"]["citations_unresolvable"]]
            ),
            "critical_automated": [
                r["id"] for r in scored if r["tier1"]["critical_automated"]
            ],
            "errored": len([r for r in records if r["error"]]),
            "latency_cold_s": round(cold, 2) if cold else None,
            "latency_warm_mean_s": (
                round(statistics.mean(latencies), 2) if latencies else None
            ),
            "latency_warm_p95_s": (
                round(sorted(latencies)[int(len(latencies) * 0.95) - 1], 2)
                if len(latencies) >= 2
                else None
            ),
            "vram_baseline_mb": baseline,
            "vram_loaded_mb": peak_vram_mb(),
        },
        "records": records,
    }


def _mark(record: dict[str, Any]) -> str:
    gates = record["tier1"]
    if record["error"]:
        return "ERROR"
    if not gates.get("schema_valid"):
        return "INVALID SCHEMA"
    problems = []
    if gates.get("degenerate"):
        problems.append("DEGENERATE")
    if not gates["grounded"]:
        problems.append("ungrounded")
    if gates["forbidden_matched"]:
        problems.append("FORBIDDEN")
    if not gates["required_met"]:
        problems.append("missing figure")
    if not gates["refusal_met"]:
        problems.append("DID NOT REFUSE")
    if not gates["hedging_met"]:
        problems.append("no hedging")
    if gates["citations_unresolvable"]:
        problems.append("bad citation")
    return ", ".join(problems) if problems else "tier1 ok"


def _slug(model: str) -> str:
    return model.replace("/", "_").replace(":", "_")


_OLLAMA_BIN = shutil.which("ollama") or r"C:\Users\jovit\AppData\Local\Programs\Ollama\ollama.exe"


def _unload(model: str) -> None:
    """Evict a model from the card. 8 GB will not hold two of these.

    Best effort: if the CLI is not reachable the next load evicts anyway, and
    the only cost is a cold-start figure that is really a warm one - which the
    result file would then be reporting wrongly, so a failure is logged rather
    than swallowed silently.
    """
    try:
        subprocess.run([_OLLAMA_BIN, "stop", model], capture_output=True, timeout=60)
    except Exception as exc:  # noqa: BLE001
        print(f"  (could not evict {model}: {exc}; cold-start timing may be understated)")


# --------------------------------------------------------------------------
# Blinding and reports
# --------------------------------------------------------------------------


# Written into the same directory and matching the same glob, but not a result.
# Leaving it in made the first run die with KeyError: 'metrics' *after* every
# model had already been called - the expensive place to discover a typo.
_NOT_RESULTS = {"reasoning_key.json"}


def _result_paths() -> list[Path]:
    return [
        path
        for path in sorted(RESULTS.glob("reasoning_*.json"))
        if path.name not in _NOT_RESULTS
    ]


def _results() -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in _result_paths()]


def write_blind(cases: dict[str, Any]) -> None:
    """Answers keyed A/B/C/D, and the mapping in a file opened only afterwards.

    Blinding removes two pulls a reader cannot fully resist: toward the
    incumbent, and against the candidate already written up as failing. The
    seeded shuffle is per question, so no key holds one model throughout.
    """
    results = _results()
    if not results:
        raise SystemExit("No results to blind. Run the benchmark first.")

    by_id = {q["id"]: q for q in cases["questions"]}
    letters = "ABCDEFGH"
    key: dict[str, dict[str, str]] = {}
    lines = [
        "# Reasoning benchmark - answers for blind scoring",
        "",
        "Candidates are keyed **A/B/C/D per question**, shuffled independently, so "
        "no letter is one model throughout. The mapping is in `reasoning_key.json` "
        "and must not be opened until every score in `reasoning_scoresheet.md` is "
        "fixed.",
        "",
        "Score each answer 0-2 on **reasoning correctness**, **financial "
        "interpretation** and **clarity**, and mark CRITICAL where the question's "
        "`critical_if` applies.",
        "",
        "**Tier 1 results are deliberately not shown here.** Seeing that a machine "
        "flagged an answer would anchor the score to the machine's verdict, and the "
        "disagreement between automated and human judgement is one of the things "
        "this benchmark is meant to measure - it cannot be measured if one side saw "
        "the other's answer first. The gates are in the per-model JSON and are "
        "joined in only at `--unblind`.",
        "",
    ]

    for qid, case in by_id.items():
        lines += [
            f"\n---\n\n## {qid} - {case['brief_category']}",
            "",
            f"**Question:** {case['question']}",
            "",
            "**Ground truth**",
            *[f"- {fact}" for fact in case["ground_truth"]],
            "",
            f"**Critical if:** {case['critical_if']}",
            "",
        ]
        if case.get("acceptable_claims"):
            lines += ["**Acceptable:** " + " · ".join(case["acceptable_claims"]), ""]

        order = [r["model"] for r in results]
        random.Random(BLIND_SEED + int(qid[1:])).shuffle(order)
        key[qid] = {letters[i]: model for i, model in enumerate(order)}

        for letter, model in key[qid].items():
            result = next(r for r in results if r["model"] == model)
            record = next(r for r in result["records"] if r["id"] == qid)
            answer = record["answer"] or "(no answer produced)"
            lines += [
                f"### {qid} · candidate {letter}",
                "",
                "> " + answer.replace("\n", "\n> "),
                "",
                "Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __",
                "",
                "Justification:",
                "",
            ]

    (RESULTS / "reasoning_answers_blind.md").write_text("\n".join(lines), encoding="utf-8")
    (RESULTS / "reasoning_key.json").write_text(
        json.dumps({"seed": BLIND_SEED, "mapping": key}, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  wrote reasoning_answers_blind.md ({len(by_id)} questions x {len(results)})")
    print("  wrote reasoning_key.json - do not open until scoring is fixed")


def write_comparison(cases: dict[str, Any]) -> str:
    """Tier 1 table. Tier 2 is joined in by --unblind once scoring exists."""
    results = _results()
    rows = []
    for result in results:
        m = result["metrics"]
        critical = m["critical_automated"]
        rows.append(
            f"| {result['model']} | {m['gates_passed']}/{m['questions']} | "
            f"{m['grounded']}/{m['schema_valid']} | {m['forbidden_claims']} | "
            f"{m.get('degenerate', 0)} | "
            f"{m['refusals_met']}/{m['schema_valid']} | "
            f"{len(critical)} {'(' + ', '.join(critical) + ')' if critical else ''} | "
            f"{m['latency_cold_s']}s | {m['latency_warm_mean_s']}s | "
            f"{m['vram_loaded_mb']} |"
        )

    table = "\n".join(
        [
            "| Model | Tier 1 passed | Grounded | Forbidden claims | Degenerate | "
            "Refusals met | Critical (automated) | Cold | Warm mean | VRAM MB |",
            "|---|---|---|---|---|---|---|---|---|---|",
            *rows,
        ]
    )

    (RESULTS / "reasoning_comparison.md").write_text(
        "# Module 4 generation and reasoning - Tier 1\n\n"
        "**This table is a floor, not a grade.** Every column is a necessary "
        "condition a machine can check honestly. None of them judges whether the "
        "reasoning is sound.\n\n"
        "The failure this benchmark was built for passes every column here: "
        "handed the correct `current_ratio = 1.307692`, a model called it \"weak "
        "liquidity\" and said the company could not pay its bills. No figure was "
        "wrong, so nothing automated objected. *Forbidden claims* is the one "
        "column aimed at it, and it is phrase matching - it catches that failure "
        "and near paraphrases, not a novel wrong conclusion in unforeseen "
        "words.\n\n"
        "Read `reasoning_answers_blind.md` and score Tier 2 before choosing "
        "anything.\n\n" + table + "\n\n"
        "**Critical (automated)** flags a matched forbidden phrase or a missed "
        "refusal. It is a candidate for a critical failure, not a verdict: the "
        "phrase may be negated in context. The human scoresheet decides, and the "
        "disagreements are listed in `reasoning_disagreements.md`.\n\n"
        "## Known false positive in the grounding gate\n\n"
        "`verification.extract_numbers` reads a parenthesised number as the "
        "accountant's negative - `(2,300)` is -2300, which is correct on a "
        "Balance Sheet. It applies the same rule to an enumerated list marker, so "
        "an answer written \"because: (1) ... and (2) ...\" yields -1 and -2, "
        "neither of which is in the context, and the answer is marked ungrounded "
        "when nothing about it is.\n\n"
        "It fired once here, on **qwen3:4b Q3** (`figures_unverified: ['-1', "
        "'-2']`). That answer is in fact fully grounded and should be read as "
        "such.\n\n"
        "This is a defect in **shipped Module 4 code**, not in the benchmark: in "
        "production the same answer would be regenerated once and could then be "
        "refused, so a model that writes numbered lists is penalised for its "
        "formatting. It is recorded rather than fixed here because fixing it "
        "means changing production code, which this benchmark must not do while "
        "it is the thing being measured.\n",
        encoding="utf-8",
    )
    return table


def unblind() -> None:
    """Join Tier 2 to Tier 1 and list where the two disagree."""
    key_path = RESULTS / "reasoning_key.json"
    sheet_path = RESULTS / "reasoning_scoresheet.md"
    if not key_path.exists():
        raise SystemExit("No reasoning_key.json - run the benchmark first.")
    if not sheet_path.exists():
        raise SystemExit(
            "No reasoning_scoresheet.md. Score the blind answers before unblinding - "
            "unblinding first is how the bias the keying exists to prevent gets in."
        )

    key = json.loads(key_path.read_text(encoding="utf-8"))["mapping"]
    print("Mapping (candidate letter -> model), per question:")
    for qid, mapping in key.items():
        print(f"  {qid:4} " + "  ".join(f"{k}={v}" for k, v in mapping.items()))
    print(
        "\nJoin these against reasoning_scoresheet.md, then write "
        "reasoning_disagreements.md and MODULE4_MODEL_SELECTION.md."
    )


def rescore(cases: dict[str, Any]) -> None:
    """Re-run Tier 1 over stored answers without calling any model.

    A rubric fix must not require regeneration - and regenerating would change
    every latency for reasons unrelated to the fix.
    """
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in cases["questions"]}

    for path in _result_paths():
        result = json.loads(path.read_text(encoding="utf-8"))
        for record in result["records"]:
            record["tier1"] = tier1(
                by_id[record["id"]],
                frozen["questions"][record["id"]],
                record.get("raw_reply"),
                record.get("answer", ""),
            )
        scored = [r for r in result["records"] if r["tier1"].get("schema_valid")]
        result["metrics"].update(
            {
                "gates_passed": len([r for r in scored if r["tier1"]["gates_passed"]]),
                "grounded": len([r for r in scored if r["tier1"]["grounded"]]),
                "forbidden_claims": len(
                    [r for r in scored if r["tier1"]["forbidden_matched"]]
                ),
                "degenerate": len([r for r in scored if r["tier1"].get("degenerate")]),
                "refusals_met": len([r for r in scored if r["tier1"]["refusal_met"]]),
                "critical_automated": [
                    r["id"] for r in scored if r["tier1"]["critical_automated"]
                ],
            }
        )
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"  rescored {path.name}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="*", default=list(CANDIDATES))
    parser.add_argument("--rescore", action="store_true")
    parser.add_argument("--unblind", action="store_true")
    args = parser.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    cases = load_cases()

    if args.unblind:
        unblind()
        return

    if args.rescore:
        rescore(cases)
        write_blind(cases)
        print("\n" + write_comparison(cases))
        return

    if not FROZEN.exists():
        raise SystemExit(
            "No reasoning_context.json. Run `python -m benchmarks.reasoning_context` "
            "first - every candidate must be given byte-identical input."
        )
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    if frozen["cases_version"] != cases["version"]:
        raise SystemExit(
            f"Frozen context is for cases {frozen['cases_version']}, but "
            f"reasoning_cases.json is {cases['version']}. Re-freeze."
        )

    for model in args.models:
        print(f"\n=== {model} ({len(frozen['questions'])} questions) ===")
        result = await run_model(model, frozen, cases)
        (RESULTS / f"reasoning_{_slug(model)}.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        m = result["metrics"]
        print(
            f"  tier 1 {m['gates_passed']}/{m['questions']} | "
            f"forbidden {m['forbidden_claims']} | "
            f"critical {len(m['critical_automated'])} | warm {m['latency_warm_mean_s']}s"
        )
        _unload(model)

    print()
    write_blind(cases)
    print("\n" + write_comparison(cases))


if __name__ == "__main__":
    asyncio.run(main())
