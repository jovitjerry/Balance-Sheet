"""What the model is shown, and what it is deliberately not shown.

One prompt, one line item. Batching several into a single request was
considered and rejected: one malformed item corrupts the JSON for every item
beside it, and per-item requests keep each failure isolated, each answer
individually cacheable, and each decision separately explainable.

**No figure ever appears in a prompt.** The model maps terminology; the numbers
come from :func:`~app.core.amounts.parse_amount` and are never put where a
model could restate one. It is not being asked to check anything, and it is
given nothing it could alter.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.modules.extraction.taxonomy import Section, Subsection, get

_INSTRUCTIONS = """\
You classify line items from a company Balance Sheet.

Given one line item's label, choose the single canonical category from the list
below that best describes what the line represents. Answer only with a category
from that list.

Rules:
- Choose from the listed categories only. Never invent a category.
- Answer "{unknown}" when the label is too vague or ambiguous to place with
  confidence. Abstaining is correct and useful; a confident wrong category is
  not.
- Choose a category beginning "other_" only when the document itself is
  presenting a residual or miscellaneous line, not when you are unsure.
- Judge the label by what it means in accounting, not by the words it shares
  with a category name.
- Set "confidence" to how certain you are, from 0 to 1.
- Keep "reasoning" to one short sentence.
"""


def build_prompt(
    label: str,
    *,
    section: Section,
    subsection: Subsection | None,
    allowed: Sequence[str],
    neighbours: Sequence[str] = (),
    currency: str | None = None,
) -> str:
    """The prompt for one line item.

    The section and subsection are stated because the same wording means
    different things on different parts of a sheet, and the neighbouring labels
    are supplied because a line reads in the company of its siblings: "Stock"
    beside "Trade Debtors" and "Cash at bank" is inventory, and on its own it
    is a guess.
    """
    lines: list[str] = [_INSTRUCTIONS.format(unknown="unknown"), ""]

    lines.append("Categories:")
    for canonical in allowed:
        category = get(canonical)
        description = category.description if category else ""
        lines.append(f"- {canonical}: {description}")
    lines.append("")

    lines.append("Line item to classify:")
    lines.append(f'  Label: "{label}"')
    lines.append(f"  Section: {section.value}")
    if subsection is not None:
        lines.append(f"  Subsection: {subsection.value}")
    if currency:
        lines.append(f"  Reported currency: {currency}")

    if neighbours:
        lines.append("")
        lines.append("Other labels printed nearby, for context:")
        lines.extend(f'  - "{neighbour}"' for neighbour in neighbours)

    return "\n".join(lines)


__all__ = ["build_prompt"]
