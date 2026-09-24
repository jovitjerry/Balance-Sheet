from __future__ import annotations
from pathlib import Path
from app.modules.extraction import taxonomy
from app.modules.ratios import definitions
from app.modules.ratios.aggregation import REASONS, WARNINGS
from app.modules.ratios.definitions import InputKind, InputSpec, RatioDefinition
from app.modules.ratios.service import RATIO_DECIMAL_PLACES
DOCS = Path(__file__).resolve().parents[1] / 'docs' / 'RATIOS.md'
_KIND_PROSE = {InputKind.SECTION_TOTAL: 'the section total Module 1 located on the document and checked the accounting equation against', InputKind.DERIVED_SUM: 'summed from the normalized line items, because Module 2 excludes printed subtotals from the extraction', InputKind.COMPOSITE: 'derived from another quantity by removing named categories'}

def _fields(spec: InputSpec) -> str:
    if spec.kind is InputKind.SECTION_TOTAL:
        return f'`{spec.section.value}.total`' if spec.section else '-'
    if spec.kind is InputKind.COMPOSITE:
        assert spec.base is not None
        removed = ', '.join((f'`{label}`' for label in spec.subtract))
        return f'{spec.base.name}, less {removed}'
    if spec.include:
        return ', '.join((f'`{label}`' for label in spec.include))
    assert spec.section is not None
    labels = taxonomy.labels_for(spec.section, spec.subsection)
    return ', '.join((f'`{label}`' for label in labels))

def _quantity(spec: InputSpec) -> str:
    return f'**{spec.name}** - {_KIND_PROSE[spec.kind]}.\n\n  Fields: {_fields(spec)}'

def _section(definition: RatioDefinition) -> str:
    left = _quantity(definition.left)
    right = _quantity(definition.right)
    return '\n'.join((f'### `{definition.name}`', '', f'**Formula:** {definition.formula}', '', f'**Unit:** {definition.unit.value}', '', '**Definition.** ' + definition.definition, '', '**Inputs.**', '', f'- {left}', f'- {right}', '', '**Limitations.** ' + definition.limitations, ''))

def render() -> str:
    parts = ['# Financial ratios - definitions and assumptions', '', '**Generated from `app/modules/ratios/definitions.py`. Do not edit by hand** - run `python -m scripts.generate_ratio_docs` instead. Generated rather than written so that the formula a report quotes and the formula the code applies cannot drift apart.', '', f'Ratio specification version: `{definitions.RATIO_SPEC_VERSION}` · canonical vocabulary: `{taxonomy.TAXONOMY_VERSION}`', '', '## Scope', '', 'Balance Sheet only, and a **single reporting period**. Every ratio below is computable from a Balance Sheet alone; none requires an Income Statement or a Cash Flow Statement, and none may be added that would. There is no trend, no year-over-year comparison and no industry benchmark - a figure here describes one document at one date.', '', '## How the figures are chosen', '', '> Prefer what the document printed and Module 1 validated. Derive only what was not printed.', '', 'The three grand totals are read from the document, where Module 1 located them by anchor and checked the accounting equation against them. Current and non-current subtotals have to be summed from line items instead, because Module 2 excludes every printed subtotal from the extraction and the figure therefore does not exist in the data. Each computed ratio records which basis each of its sides used.', '', 'A line item is classified by its **canonical category**, not by the heading it was printed under: many Balance Sheets print no current/non-current headings at all, and heading-based classification would compute nothing on those.', '', '## Precision', '', f'Every figure is a `Decimal`; binary floating point is not used anywhere. Sums are exact. A quotient is computed once and rounded once, to {RATIO_DECIMAL_PLACES} decimal places, half-up. Working capital is money and is never rounded. The unrounded numerator and denominator are stored beside every result, so any consumer can re-derive the value at any precision.', '', '## No ratio is ever fabricated', '', 'A ratio whose inputs are absent, or whose denominator is zero, is reported `unavailable` with a machine-readable reason. A ratio computed from an incomplete set of line items is reported `partial`, naming the lines it left out and their total, so a reader can bound the true value. Neither is ever a number with the doubt filed off.', '', 'Reasons: ' + ', '.join((f'`{reason}`' for reason in sorted(REASONS))), '', 'Warnings: ' + ', '.join((f'`{warning}`' for warning in sorted(WARNINGS))), '', '**No language model is involved in any calculation on this page.** Module 2 uses one to map terminology and is never shown a figure; everything here is deterministic Python.', '', '## The ratios', '']
    parts.extend((_section(definition) for definition in definitions.DEFINITIONS))
    return '\n'.join(parts).rstrip() + '\n'

def main() -> None:
    DOCS.parent.mkdir(parents=True, exist_ok=True)
    DOCS.write_text(render(), encoding='utf-8')
    print(f'Wrote {DOCS}')
if __name__ == '__main__':
    main()
