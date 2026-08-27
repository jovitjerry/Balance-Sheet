"""Join blind Tier 2 scores to the key and Tier 1, and write the decision record.

    python -m benchmarks.reasoning_report

Run **after** `reasoning_scoresheet.md` is complete. It opens
`reasoning_key.json`, attaches a model name to every blind score, and writes:

    reasoning_comparison.md      per-model, per-dimension, per-question
    reasoning_disagreements.md   where automation and human judgement differ
    MODULE4_MODEL_SELECTION.md   the decision record

Kept as a script rather than done by hand so the join is reproducible and any
arithmetic in the report can be re-derived from the stored artefacts.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmarks.reasoning_context import load_cases
from benchmarks.runner import RESULTS

DIMENSIONS = ("reasoning", "interpretation", "clarity")


def _tier2() -> dict[tuple[str, str], dict[str, Any]]:
    """Parse the per-question score tables out of the human scoresheet."""
    text = (RESULTS / "reasoning_scoresheet.md").read_text(encoding="utf-8")
    scores: dict[tuple[str, str], dict[str, Any]] = {}
    question: str | None = None
    for line in text.splitlines():
        header = re.match(r"^## (Q\d+) ", line)
        if header:
            question = header.group(1)
            continue
        row = re.match(r"^\| ([ABCD]) \| ([0-2]) \| ([0-2]) \| ([0-2]) \| (.+?) \|$", line)
        if row and question:
            letter, reasoning, interpretation, clarity, critical = row.groups()
            scores[(question, letter)] = {
                "reasoning": int(reasoning),
                "interpretation": int(interpretation),
                "clarity": int(clarity),
                "critical": "YES" in critical,
            }
    return scores


def join() -> dict[str, Any]:
    key = json.loads((RESULTS / "reasoning_key.json").read_text(encoding="utf-8"))["mapping"]
    scores = _tier2()
    if len(scores) != 56:
        raise SystemExit(f"Expected 56 scored answers, parsed {len(scores)}.")

    results = {}
    for path in sorted(RESULTS.glob("reasoning_*.json")):
        if path.name == "reasoning_key.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        results[data["model"]] = data

    by_model: dict[str, dict[str, dict]] = defaultdict(dict)
    for (question, letter), score in scores.items():
        by_model[key[question][letter]][question] = {**score, "letter": letter}

    joined: dict[str, Any] = {"models": {}, "disagreements": []}
    for model, data in results.items():
        per_question = by_model[model]
        count = len(per_question)
        totals = {
            dimension: sum(entry[dimension] for entry in per_question.values())
            for dimension in DIMENSIONS
        }
        criticals = sorted(q for q, e in per_question.items() if e["critical"])

        rows = []
        for record in data["records"]:
            question = record["id"]
            gates, human = record["tier1"], per_question[question]
            human_bad = (
                human["reasoning"] == 0 or human["interpretation"] == 0 or human["critical"]
            )
            auto_bad = not gates.get("gates_passed", False)
            rows.append(
                {
                    "id": question,
                    "category": record["category"],
                    "letter": human["letter"],
                    **{d: human[d] for d in DIMENSIONS},
                    "critical_human": human["critical"],
                    "critical_auto": gates.get("critical_automated", False),
                    "gates_passed": auto_bad is False,
                    "grounded": gates.get("grounded"),
                    "degenerate": gates.get("degenerate", False),
                    "refusal_met": gates.get("refusal_met"),
                    "seconds": record["seconds"],
                    "answer": record["answer"],
                }
            )
            if human_bad != auto_bad or human["critical"] != gates.get(
                "critical_automated", False
            ):
                joined["disagreements"].append({"model": model, **rows[-1]})

        joined["models"][model] = {
            "n": count,
            "totals": totals,
            "max": 2 * count,
            "criticals": criticals,
            "eligible": not criticals,
            "metrics": data["metrics"],
            "rows": rows,
        }
    return joined


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


def _order(joined: dict[str, Any]) -> list[str]:
    """Eligible first, then by reasoning. Eligibility is not a tiebreak."""
    return sorted(
        joined["models"],
        key=lambda m: (
            bool(joined["models"][m]["criticals"]),
            -joined["models"][m]["totals"]["reasoning"],
        ),
    )


def write_comparison(joined: dict[str, Any]) -> None:
    models = joined["models"]
    lines = [
        "# Module 4 generation and reasoning — full comparison",
        "",
        "Four candidates, 14 questions, identical frozen context, `temperature=0`.",
        "Tier 1 is automated and objective. Tier 2 was scored **blind** against the",
        "published rubric before the key was opened.",
        "",
        "**A critical failure disqualifies**, per the benchmark's stated rule. Every",
        "score is still published: a table where a disqualified model has good",
        "averages is a finding worth printing, not one to hide.",
        "",
        "## Tier 2 — human dimensions (max 28 each: 14 questions × 2)",
        "",
        "| Model | Reasoning | Interpretation | Clarity | Critical | Eligible |",
        "|---|---|---|---|---|---|",
    ]
    for model in _order(joined):
        d = models[model]
        t = d["totals"]
        crit = f"**{len(d['criticals'])}** ({', '.join(d['criticals'])})" if d["criticals"] else "0"
        lines.append(
            f"| `{model}` | {t['reasoning']}/28 ({t['reasoning']/28:.0%}) | "
            f"{t['interpretation']}/28 ({t['interpretation']/28:.0%}) | "
            f"{t['clarity']}/28 ({t['clarity']/28:.0%}) | {crit} | "
            f"{'**yes**' if d['eligible'] else 'no'} |"
        )

    lines += [
        "",
        "## Tier 1 — automated gates, latency, VRAM",
        "",
        "| Model | Gates passed | Grounded | Schema valid | Degenerate | Refusals met | Cold | Warm mean | Warm p95 | VRAM MB |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model in _order(joined):
        m = models[model]["metrics"]
        lines.append(
            f"| `{model}` | {m['gates_passed']}/14 | {m['grounded']}/{m['schema_valid']} | "
            f"{m['schema_valid']}/14 | {m.get('degenerate', 0)} | "
            f"{m['refusals_met']}/{m['schema_valid']} | {m['latency_cold_s']}s | "
            f"{m['latency_warm_mean_s']}s | {m['latency_warm_p95_s']}s | "
            f"{m['vram_loaded_mb']:.0f} |"
        )

    lines += [
        "",
        "Cold starts were measured after an explicit `ollama stop`, but all four",
        "models had been pulled minutes earlier and were still in the OS file cache.",
        "Treat these as warm-disk cold starts, not first-boot figures — Module 2",
        "measured `qwen3:8b` at 80.9 s on a cold disk.",
        "",
        "## Per question, per model",
        "",
        "Reasoning / Interpretation / Clarity, `!` marking a critical failure.",
        "",
    ]

    cases = {q["id"]: q for q in load_cases()["questions"]}
    order = _order(joined)
    header = "| Question | " + " | ".join(f"`{m.split('/')[-1]}`" for m in order) + " |"
    lines += [header, "|---|" + "---|" * len(order)]
    for question in sorted(cases, key=lambda q: int(q[1:])):
        cells = []
        for model in order:
            row = next(r for r in models[model]["rows"] if r["id"] == question)
            mark = " !" if row["critical_human"] else ""
            cells.append(
                f"{row['reasoning']}/{row['interpretation']}/{row['clarity']}{mark}"
            )
        lines.append(
            f"| {question} {cases[question]['brief_category'][:34]} | " + " | ".join(cells) + " |"
        )

    lines += [
        "",
        "## Known false positive in the grounding gate",
        "",
        "`verification.extract_numbers` reads a parenthesised number as the",
        "accountant's negative, which is correct for `(2,300)` on a Balance Sheet and",
        "wrong for an enumerated list marker. An answer written \"because: (1) … and",
        "(2) …\" yields -1 and -2, neither in context, and is marked ungrounded when",
        "nothing about it is.",
        "",
        "It fired once, on **`qwen3:4b` Q3**, whose answer is fully grounded. This is a",
        "defect in shipped Module 4 code, recorded rather than fixed here because the",
        "code is the thing under measurement.",
        "",
    ]
    (RESULTS / "reasoning_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_disagreements(joined: dict[str, Any]) -> None:
    rows = joined["disagreements"]
    missed = [r for r in rows if r["critical_human"] and not r["critical_auto"]]
    silent = [
        r
        for r in rows
        if (r["reasoning"] == 0 or r["interpretation"] == 0) and r["gates_passed"]
    ]
    strict = [
        r
        for r in rows
        if not r["gates_passed"] and r["reasoning"] > 0 and r["interpretation"] > 0
        and not r["critical_human"]
    ]

    lines = [
        "# Automated vs human scoring — where they disagree",
        "",
        f"{len(rows)} of 56 answers were judged differently by the Tier 1 gates and by",
        "blind human scoring. Tier 2 was scored without sight of Tier 1, so these are",
        "genuine disagreements rather than one side echoing the other.",
        "",
        "**This section is the benchmark's main evidence for its own design.** If",
        "automation and human judgement agreed everywhere, Tier 2 would be redundant",
        "and Module 4's existing numeric verifier would be sufficient. They do not.",
        "",
        f"## Automation missed a critical failure — {len(missed)} cases",
        "",
        "The dangerous direction. Every one passed the automated critical check.",
        "",
        "| Model | Q | Human critical | Why automation missed it |",
        "|---|---|---|---|",
    ]
    for r in missed:
        why = (
            "`must_refuse` is false for this question and no forbidden phrase matched a bare \"No\""
            if r["id"] == "Q12"
            else "the degenerate carve-out suppressed the missed-refusal flag"
        )
        lines.append(f"| `{r['model']}` | {r['id']} | yes | {why} |")

    lines += [
        "",
        f"## Automation passed an answer the human scored 0 — {len(silent)} cases",
        "",
        "Every figure present and correct; the reasoning wrong. No grounding check can",
        "see these, which is the entire premise of this benchmark.",
        "",
    ]
    for r in silent:
        lines += [
            f"**`{r['model']}` {r['id']}** — reasoning {r['reasoning']}, "
            f"interpretation {r['interpretation']}, gates passed, grounded "
            f"{r['grounded']}",
            "",
            "> " + r["answer"].replace("\n", "\n> ")[:600],
            "",
        ]

    lines += [
        f"## Automation flagged an answer the human accepted — {len(strict)} cases",
        "",
        "Over-strictness, and almost all of it is one gate: `degenerate`, which treats",
        "any answer under 25 characters as empty. \"creditors\", \"Not stated\" and",
        "\"Insufficient information\" are all correct answers that the gate rejected for",
        "being short. Terse is not the same as empty, and the gate currently conflates",
        "them.",
        "",
        "| Model | Q | Answer | Human R/I/C |",
        "|---|---|---|---|",
    ]
    for r in strict:
        answer = r["answer"].replace("\n", " ")
        lines.append(
            f"| `{r['model']}` | {r['id']} | {answer[:60]!r} | "
            f"{r['reasoning']}/{r['interpretation']}/{r['clarity']} |"
        )

    lines += [
        "",
        "## What this says about the instrument",
        "",
        "Automation was wrong in **both** directions, and one error is in the benchmark's",
        "own code rather than in the models:",
        "",
        "- The `degenerate` gate (<25 characters) rejects correct terse answers. It should",
        "  test for a *non-answer* — a bare boolean, or a token echoing the schema — not",
        "  for brevity.",
        "- The same carve-out suppressed a genuine critical flag: `qwen3:4b` answered",
        "  \"No\" to \"should I invest?\", which is an avoid recommendation, but the answer",
        "  was short enough to be classed degenerate and the missed-refusal flag was",
        "  cancelled. Being brief does not stop advice being advice.",
        "- `critical_automated` cannot fire on questions where the failure is a *judgement*",
        "  rather than a phrase. Q12 has no `must_refuse` and no phrase covering a bare",
        "  \"No\", so three critical failures passed silently.",
        "",
        "None of these were adjusted after seeing the results. They are recorded as",
        "defects to fix in a v1.1, which must not be applied retroactively to this run.",
        "",
    ]
    (RESULTS / "reasoning_disagreements.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    joined = join()
    write_comparison(joined)
    write_disagreements(joined)
    print("wrote reasoning_comparison.md and reasoning_disagreements.md")
    for model in _order(joined):
        d = joined["models"][model]
        t = d["totals"]
        print(
            f"  {model:36} R{t['reasoning']:3}/28 I{t['interpretation']:3}/28 "
            f"C{t['clarity']:3}/28  crit={len(d['criticals'])}  "
            f"{'ELIGIBLE' if d['eligible'] else 'ineligible'}"
        )


if __name__ == "__main__":
    main()
