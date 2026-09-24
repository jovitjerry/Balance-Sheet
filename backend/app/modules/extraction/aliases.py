from __future__ import annotations
from app.core.text import normalise
from app.modules.extraction import taxonomy
_IDENTITY: dict[str, str] = {normalise(label.replace('_', ' ')): label for label in taxonomy.labels()}

def lookup(label: str) -> str | None:
    return _IDENTITY.get(normalise(label))
__all__ = ['lookup']
