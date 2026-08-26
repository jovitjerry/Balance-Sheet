"""Score the same candidates on Module 4-style questions.

Reported **separately** from normalization, and deliberately. The two roles are
different jobs: one picks a category from a closed list under a decoding
grammar, the other writes prose about figures it has been handed. A model can
be good at either and poor at the other, and collapsing them into one number
would let a good classifier that cannot explain anything - or the reverse -
decide `OLLAMA_MODEL` unnoticed.

    python -m benchmarks.qa_runner                 # every candidate
    python -m benchmarks.qa_runner --models qwen3:4b

**The automated score is a screen, not a grade.** It checks two things a
machine can check honestly: whether the figures a correct answer must cite
actually appear, and whether a question that should have been refused was
refused rather than answered with an invented number. It judges no reasoning
and no prose. Every full answer is written to ``results/qa_answers.md`` so a
human can read what the numbers are standing in for.

Nothing here is part of Module 4, which is not built. This measures a
candidate's fitness for it while the choice is still open.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.llm.ollama import build_llm_provider
from benchmarks.runner import BENCHMARKS, RESULTS, CANDIDATES, peak_vram_mb

SYSTEM = """\
You are helping someone read a company Balance Sheet. Answer in at most four
sentences, in plain language.

You are given the complete Balance Sheet below. It is the only information you
have. A Balance Sheet reports one moment in time: it shows what a company owns,
what it owes and what is left for shareholders. It does **not** contain
revenue, profit, expenses or cash flow, and only one reporting period is
available here.

If a question asks for something the Balance Sheet does not contain, say so
plainly and do not estimate a figure.
"""


def load_qa() -> dict[str, Any]:
    return json.loads((BENCHMARKS / "qa_cases.json").read_text(encoding="utf-8"))


def build_prompt(sheet: dict[str, Any], question: str) -> str:
    lines = [SYSTEM, "", "Balance Sheet:", f"  {sheet['entity']} - {sheet['period']}", ""]
    for section in ("assets", "liabilities", "equity"):
        lines.append(f"  {section.upper()}:")
        for key, value in sheet[section].items():
            name = "TOTAL" if key == "total" else key.replace("_", " ")
            lines.append(f"    {name}: {value:,} {sheet['currency']}")
        lines.append("")
    lines.append(f"Question: {question}")
    return "\n".join(lines)


def _mentions_figure(answer: str, figure: int) -> bool:
    """Whether the answer states this amount, in any ordinary printed form.

    Accepts Western and Indian grouping, a bare figure, and the "1.2 million"
    style a plain-language answer often uses.
    """
    digits = re.sub(r"[,\s]", "", answer)
    if str(figure) in digits:
        return True
    # 1200000 -> "1.2 million" / "1.2m"
    for unit, divisor in (("million", 1_000_000), ("lakh", 100_000), ("crore", 10_000_000)):
        if figure % (divisor // 10) == 0:
            scaled = figure / divisor
            text = f"{scaled:g}"
            if re.search(rf"{re.escape(text)}\s*(?:{unit}|m\b)", answer, re.IGNORECASE):
                return True
    return False


# Ways of saying "the Balance Sheet does not contain that". Kept broad on
# purpose: the first version of this list scored two correct refusals as
# failures because they said "does not contain" where the list only had "does
# not show". A screen that is too narrow does not report a worse model, it
# reports the wrong model.
_REFUSAL_PHRASES = (
    "does not contain",
    "does not show",
    "does not include",
    "does not provide",
    "does not report",
    "doesn't contain",
    "doesn't show",
    "doesn't include",
    "not contain",
    "not shown",
    "not available",
    "not included",
    "not provided",
    "cannot be determined",
    "cannot determine",
    "cannot",
    "can't",
    "unable to",
    "income statement",
    "profit and loss",
    "single point in time",
    "one point in time",
    "point in time",
    "one period",
    "single period",
    "only one reporting period",
    "prior year",
    "comparative",
    "no revenue",
    "no profit",
)


def score(
    question: dict[str, Any], answer: str, known_figures: set[str] | None = None
) -> dict[str, Any]:
    """Screen one answer. Returns what was checked, not a verdict on quality."""
    figures = question.get("figures", [])
    hit = [figure for figure in figures if _mentions_figure(answer, figure)]

    result: dict[str, Any] = {
        "figures_expected": len(figures),
        "figures_cited": len(hit),
        "figures_missing": [f for f in figures if f not in hit],
    }

    if question["type"] == "refusal":
        lowered = answer.lower()
        acknowledged = any(phrase in lowered for phrase in _REFUSAL_PHRASES) or any(
            phrase in lowered for phrase in question.get("must_mention_any", [])
        )
        # The dangerous failure is a *confident invented* figure. Quoting the
        # sheet's own totals while explaining what is missing is not that -
        # scoring it as fabrication marked a model that refused correctly as
        # one that had not.
        known = known_figures or set()
        invented = [
            figure
            for figure in re.findall(r"\b\d[\d,]{4,}\b", answer)
            if re.sub(r"[,\s]", "", figure) not in known
        ]
        result.update(
            {
                "refused": acknowledged and not invented,
                "acknowledged_limit": acknowledged,
                "invented_figures": invented[:5],
            }
        )
    else:
        result["passed"] = len(hit) == len(figures)

    return result


def sheet_figures(sheet: dict[str, Any]) -> set[str]:
    """Every amount actually printed on the Balance Sheet, as bare digits.

    A model repeating one of these has quoted the document, not invented a
    number, however irrelevant the quotation is to the question.
    """
    figures: set[str] = set()
    for section in ("assets", "liabilities", "equity"):
        for value in sheet[section].values():
            figures.add(str(value))
    return figures


async def run_model(model: str, qa: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    provider = build_llm_provider(
        host=settings.ollama_host,
        model=model,
        timeout_s=settings.ollama_timeout_s,
        # Prose over a whole Balance Sheet needs more room than one label does.
        num_ctx=max(settings.ollama_num_ctx, 4096),
    )
    installed = provider.installed_models()
    if installed is None:
        raise SystemExit(f"Ollama is not reachable at {settings.ollama_host}.")
    if model not in installed:
        raise SystemExit(
            f"{model!r} is not installed. Tags must match `ollama list` exactly.\n"
            f"Installed: {', '.join(installed) or '(nothing)'}"
        )

    baseline = peak_vram_mb()
    records: list[dict[str, Any]] = []
    latencies: list[float] = []

    for question in qa["questions"]:
        prompt = build_prompt(qa["balance_sheet"], question["question"])
        started = time.perf_counter()
        try:
            # No schema: this is prose, and constraining it would measure
            # something other than the job Module 4 will ask for.
            result = await provider.complete_text(prompt=prompt, options={"temperature": 0})
            answer = result.strip()
            failed = False
        except Exception as exc:  # noqa: BLE001 - recorded, never hidden
            answer = f"[error: {exc}]"
            failed = True
        elapsed = time.perf_counter() - started
        latencies.append(elapsed)

        scored = (
            score(question, answer, sheet_figures(qa["balance_sheet"]))
            if not failed
            else {"errored": True}
        )
        records.append(
            {
                "id": question["id"],
                "type": question["type"],
                "question": question["question"],
                "answer": answer,
                "rubric": question["rubric"],
                "seconds": round(elapsed, 2),
                "errored": failed,
                **scored,
            }
        )
        mark = _mark(records[-1])
        print(f"  {question['id']:4} {question['type']:10} {mark:12} {elapsed:5.2f}s")

    answerable = [r for r in records if r["type"] == "answerable" and not r["errored"]]
    refusals = [r for r in records if r["type"] == "refusal" and not r["errored"]]

    return {
        "model": model,
        "case_version": qa["version"],
        "metrics": {
            "figure_accuracy": _rate(
                sum(r["figures_cited"] for r in answerable),
                sum(r["figures_expected"] for r in answerable),
            ),
            "questions_fully_cited": _rate(
                len([r for r in answerable if r.get("passed")]), len(answerable)
            ),
            "refusals_handled": _rate(
                len([r for r in refusals if r.get("refused")]), len(refusals)
            ),
            "fabricated_on_refusal": _rate(
                len([r for r in refusals if r.get("invented_figures")]), len(refusals)
            ),
            "errored": len([r for r in records if r["errored"]]),
            "latency_cold_s": round(latencies[0], 2) if latencies else None,
            "latency_warm_mean_s": (
                round(statistics.mean(latencies[1:]), 2) if len(latencies) > 1 else None
            ),
            "vram_baseline_mb": baseline,
            "vram_loaded_mb": peak_vram_mb(),
            "questions": len(records),
        },
        "records": records,
    }


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _mark(record: dict[str, Any]) -> str:
    if record["errored"]:
        return "ERROR"
    if record["type"] == "refusal":
        return "refused" if record.get("refused") else "ANSWERED IT"
    return f"{record['figures_cited']}/{record['figures_expected']} figures"


def write_report() -> str:
    rows, answers = [], []
    for path in sorted(RESULTS.glob("qa_*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        m = result["metrics"]
        rows.append(
            f"| {result['model']} | {m['figure_accuracy']:.0%} | "
            f"{m['questions_fully_cited']:.0%} | {m['refusals_handled']:.0%} | "
            f"{m['fabricated_on_refusal']:.0%} | {m['latency_cold_s']}s | "
            f"{m['latency_warm_mean_s']}s |"
        )
        answers.append(f"\n## {result['model']}\n")
        for record in result["records"]:
            answers.append(
                f"\n**{record['id']} ({record['type']})** - {record['question']}\n\n"
                f"> {record['answer'].replace(chr(10), chr(10) + '> ')}\n\n"
                f"*Rubric:* {'; '.join(record['rubric'])}  \n"
                f"*Screen:* {_mark(record)}\n"
            )

    table = "\n".join(
        [
            "| Model | Figures cited | Questions fully cited | Refusals handled | Fabricated on refusal | Cold | Warm mean |",
            "|---|---|---|---|---|---|---|",
            *rows,
        ]
    )

    (RESULTS / "qa_comparison.md").write_text(
        "# Module 4-style Q&A comparison\n\n"
        "Scored **separately** from normalization: picking a category from a "
        "closed list and explaining figures in prose are different jobs, and a "
        "model can be good at one and poor at the other.\n\n"
        "**This is a screen, not a grade.** *Figures cited* is whether the "
        "amounts a correct answer must mention actually appear. *Refusals "
        "handled* is the two questions that ask for something a Balance Sheet "
        "does not contain - profit, and a year-on-year change - where the "
        "right answer is to say so. *Fabricated on refusal* is those same "
        "questions answered with a number instead, which is the failure that "
        "matters: a confident invented figure is the one a reader has no way "
        "to catch.\n\n"
        "Neither column judges reasoning or prose. The full answers are in "
        "`qa_answers.md`; read them before choosing.\n\n" + table + "\n",
        encoding="utf-8",
    )
    (RESULTS / "qa_answers.md").write_text(
        "# Q&A answers, verbatim\n\nFor human review - the table in "
        "`qa_comparison.md` is only a screen.\n" + "".join(answers),
        encoding="utf-8",
    )
    return table


def rescore() -> None:
    """Re-screen stored answers without asking any model again.

    The answers are saved verbatim, so a correction to *how* they are screened
    does not need the models re-run - and re-running them would change the
    latencies for reasons unrelated to the fix.
    """
    qa = load_qa()
    questions = {q["id"]: q for q in qa["questions"]}
    known = sheet_figures(qa["balance_sheet"])

    for path in sorted(RESULTS.glob("qa_*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        for record in result["records"]:
            if record.get("errored"):
                continue
            record.update(score(questions[record["id"]], record["answer"], known))

        answerable = [r for r in result["records"] if r["type"] == "answerable"]
        refusals = [r for r in result["records"] if r["type"] == "refusal"]
        result["metrics"].update(
            {
                "figure_accuracy": _rate(
                    sum(r["figures_cited"] for r in answerable),
                    sum(r["figures_expected"] for r in answerable),
                ),
                "questions_fully_cited": _rate(
                    len([r for r in answerable if r.get("passed")]), len(answerable)
                ),
                "refusals_handled": _rate(
                    len([r for r in refusals if r.get("refused")]), len(refusals)
                ),
                "fabricated_on_refusal": _rate(
                    len([r for r in refusals if r.get("invented_figures")]), len(refusals)
                ),
            }
        )
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"  rescreened {path.name}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="*", default=list(CANDIDATES))
    parser.add_argument(
        "--rescore",
        action="store_true",
        help="Re-screen stored answers instead of asking any model again.",
    )
    args = parser.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)

    if args.rescore:
        rescore()
        print("\n" + write_report())
        return

    qa = load_qa()

    for model in args.models:
        print(f"\n=== {model} ({len(qa['questions'])} questions) ===")
        result = await run_model(model, qa)
        slug = model.replace("/", "_").replace(":", "_")
        (RESULTS / f"qa_{slug}.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        m = result["metrics"]
        print(
            f"  figures {m['figure_accuracy']:.0%} | "
            f"refusals handled {m['refusals_handled']:.0%} | "
            f"warm {m['latency_warm_mean_s']}s"
        )

    print("\n" + write_report())


if __name__ == "__main__":
    asyncio.run(main())
