from __future__ import annotations
from collections.abc import Sequence
from app.modules.extraction.taxonomy import Section, Subsection, get
_INSTRUCTIONS = 'You classify line items from a company Balance Sheet.\n\nGiven one line item\'s label, choose the single canonical category from the list\nbelow that best describes what the line represents. Answer only with a category\nfrom that list.\n\nRules:\n- Choose from the listed categories only. Never invent a category.\n- Answer "{unknown}" when the label is too vague or ambiguous to place with\n  confidence. Abstaining is correct and useful; a confident wrong category is\n  not.\n- Choose a category beginning "other_" only when the document itself is\n  presenting a residual or miscellaneous line, not when you are unsure.\n- Judge the label by what it means in accounting, not by the words it shares\n  with a category name.\n- Set "confidence" to how certain you are, from 0 to 1.\n- Keep "reasoning" to one short sentence.\n'

def build_prompt(label: str, *, section: Section, subsection: Subsection | None, allowed: Sequence[str], neighbours: Sequence[str]=(), currency: str | None=None) -> str:
    lines: list[str] = [_INSTRUCTIONS.format(unknown='unknown'), '']
    lines.append('Categories:')
    for canonical in allowed:
        category = get(canonical)
        description = category.description if category else ''
        lines.append(f'- {canonical}: {description}')
    lines.append('')
    lines.append('Line item to classify:')
    lines.append(f'  Label: "{label}"')
    lines.append(f'  Section: {section.value}')
    if subsection is not None:
        lines.append(f'  Subsection: {subsection.value}')
    if currency:
        lines.append(f'  Reported currency: {currency}')
    if neighbours:
        lines.append('')
        lines.append('Other labels printed nearby, for context:')
        lines.extend((f'  - "{neighbour}"' for neighbour in neighbours))
    return '\n'.join(lines)
__all__ = ['build_prompt']
