from __future__ import annotations
from typing import Any, Sequence
from app.modules.extraction.taxonomy import UNKNOWN
MAX_REASONING_CHARS = 200

def response_schema(allowed: Sequence[str]) -> dict[str, Any]:
    return {'type': 'object', 'properties': {'reasoning': {'type': 'string', 'maxLength': MAX_REASONING_CHARS}, 'canonical_label': {'type': 'string', 'enum': [*allowed, UNKNOWN]}, 'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1}}, 'required': ['reasoning', 'canonical_label', 'confidence']}
__all__ = ['MAX_REASONING_CHARS', 'response_schema']
