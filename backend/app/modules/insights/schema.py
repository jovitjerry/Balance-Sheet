from __future__ import annotations
from collections.abc import Sequence
from typing import Any
MAX_ANSWER_CHARS = 1800

def answer_schema(citation_ids: Sequence[str]) -> dict[str, Any]:
    return {'type': 'object', 'properties': {'answer': {'type': 'string', 'maxLength': MAX_ANSWER_CHARS, 'description': 'The answer, using only figures given in the context. State plainly when the document does not support an answer.'}, 'sufficient': {'type': 'boolean', 'description': 'False when the supplied context does not contain what the question asks for.'}, 'citations': _citations(citation_ids), 'figures_used': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 20, 'description': 'Every figure stated in the answer, copied exactly as it appears in the context.'}}, 'required': ['answer', 'sufficient', 'citations', 'figures_used']}

def _citations(citation_ids: Sequence[str]) -> dict[str, Any]:
    if not citation_ids:
        return {'type': 'array', 'maxItems': 0, 'items': {'type': 'string'}}
    return {'type': 'array', 'maxItems': 8, 'items': {'type': 'string', 'enum': list(dict.fromkeys(citation_ids))}, 'description': 'Tags of the context entries this answer relies on.'}
__all__ = ['MAX_ANSWER_CHARS', 'answer_schema']
