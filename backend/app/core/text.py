from __future__ import annotations
import re
import unicodedata
_APOSTROPHES = {'‘': "'", '’': "'", 'ʼ': "'", '`': "'"}
_DASHES = {'‐': '-', '‑': '-', '‒': '-', '–': '-', '—': '-'}
_CONNECTORS = re.compile('[+&]')
_COLLAPSE = re.compile('[^a-z0-9]+')

def normalise(text: str) -> str:
    folded = unicodedata.normalize('NFKC', text)
    for source, target in {**_APOSTROPHES, **_DASHES}.items():
        folded = folded.replace(source, target)
    folded = _CONNECTORS.sub(' and ', folded)
    return _COLLAPSE.sub(' ', folded.lower()).strip()

def contains(haystack: str, phrase: str) -> bool:
    return f' {normalise(phrase)} ' in f' {normalise(haystack)} '

def matches_any(text: str, phrases: tuple[str, ...]) -> str | None:
    for phrase in sorted(phrases, key=len, reverse=True):
        if contains(text, phrase):
            return phrase
    return None
__all__ = ['contains', 'matches_any', 'normalise']
