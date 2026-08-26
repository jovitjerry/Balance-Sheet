"""Row segmentation: one visual row can carry more than one label.

Pure - no parser, no cluster, no OCR binary.

A Balance Sheet is not always printed as one column of labels. The horizontal
("T-account") layout puts Assets down the left of the page and Liabilities and
Equity down the right, so a single visual row reads

    Intangible Assets   150,000    Total Liabilities   1,350,000

Treating cell zero as *the* label makes every total in the right-hand column
invisible - which is exactly how a genuine ``Total Liabilities`` line came to be
reported as missing.
"""

from __future__ import annotations

from app.modules.ingestion.lines import Cell, DocumentLine


def line(*texts: str) -> DocumentLine:
    return DocumentLine(
        page_index=0,
        cells=[Cell(text=text, column=index) for index, text in enumerate(texts)],
    )


def shape(row: DocumentLine) -> list[tuple[str, list[str]]]:
    """The segmentation, flattened to plain strings for comparison."""
    return [
        (segment.label.text, [figure.text for figure in segment.figures])
        for segment in row.segments
    ]


class TestSegments:
    def test_a_single_column_row_is_one_segment(self) -> None:
        assert shape(line("Total Assets", "150,000")) == [("Total Assets", ["150,000"])]

    def test_a_comparative_row_keeps_both_figures_under_one_label(self) -> None:
        """Two periods, one label. Which column is read is decided later."""
        assert shape(line("Total Assets", "150,000", "120,000")) == [
            ("Total Assets", ["150,000", "120,000"])
        ]

    def test_a_side_by_side_row_yields_a_segment_per_label(self) -> None:
        assert shape(
            line("Intangible Assets", "150,000", "Total Liabilities", "1,350,000")
        ) == [
            ("Intangible Assets", ["150,000"]),
            ("Total Liabilities", ["1,350,000"]),
        ]

    def test_a_figure_belongs_to_the_label_on_its_left(self) -> None:
        """The trap in the horizontal layout.

        ``TOTAL ASSETS`` sits opposite ``Retained Earnings``. Its figure is the
        one immediately to its right, not the last figure on the row.
        """
        assert shape(
            line("TOTAL ASSETS", "2,300,000", "Retained Earnings", "350,000")
        ) == [
            ("TOTAL ASSETS", ["2,300,000"]),
            ("Retained Earnings", ["350,000"]),
        ]

    def test_a_heading_row_yields_labels_with_no_figures(self) -> None:
        assert shape(line("ASSETS", "LIABILITIES AND EQUITY")) == [
            ("ASSETS", []),
            ("LIABILITIES AND EQUITY", []),
        ]

    def test_a_row_of_bare_figures_yields_no_segment(self) -> None:
        """Nothing here is a label, so there is nothing to attribute a figure to."""
        assert shape(line("150,000", "120,000")) == []

    def test_an_empty_row_yields_no_segment(self) -> None:
        assert shape(line()) == []

    def test_segments_keep_their_cells_for_traceability(self) -> None:
        """The column index has to survive - it is what a SourceRef records."""
        row = line("Intangible Assets", "150,000", "Total Liabilities", "1,350,000")
        liabilities = row.segments[1]

        assert liabilities.label.column == 2
        assert liabilities.figures[0].column == 3


class TestLabelIsStillTheFirstCell:
    """``label`` keeps its meaning; segmentation is additive, not a rename."""

    def test_the_leading_cell_is_still_the_row_label(self) -> None:
        assert line("Total Assets", "150,000").label == "Total Assets"
