"""The identity dictionary: canonical spellings, and nothing else.

Deliberately not a synonym table. "Trade Debtors", "Sundry Debtors" and
"Stock-in-Trade" all go to the model, because semantic equivalence is what the
model is for - and a hand-written alias table large enough to catch them would
make the model decorative, the benchmark meaningless, and the vocabulary
something two people maintain in two places.

What this catches is a document that already prints the canonical wording, in
whatever case and punctuation its typesetter chose. That is not interpretation;
it is recognising the same words. Nothing is hand-written here at all - the
entries are derived from the taxonomy, so the dictionary cannot drift from the
vocabulary it serves.
"""

from __future__ import annotations

from app.core.text import normalise
from app.modules.extraction import taxonomy

# "cash_and_cash_equivalents" -> "cash and cash equivalents", which is what
# normalise() makes of "Cash and Cash Equivalents", "CASH AND CASH EQUIVALENTS"
# and "Cash & Cash Equivalents" alike.
_IDENTITY: dict[str, str] = {
    normalise(label.replace("_", " ")): label for label in taxonomy.labels()
}


def lookup(label: str) -> str | None:
    """The canonical label this text already spells, or ``None``.

    ``None`` is the common case and is not a failure - it means the question is
    a real one, and it goes to the model.
    """
    return _IDENTITY.get(normalise(label))


__all__ = ["lookup"]
