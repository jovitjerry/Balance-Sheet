from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from app.core.errors import BalanceSheetError

class LlmUnavailable(BalanceSheetError):
    status_code = 503
    code = 'llm_unavailable'

@dataclass(frozen=True)
class LlmResult:
    payload: dict[str, Any]
    model: str
    raw: str = ''

@runtime_checkable
class LlmProvider(Protocol):
    name: str
    model: str

    def available(self) -> bool:
        ...

    async def complete_json(self, *, prompt: str, schema: dict[str, Any], options: dict[str, Any] | None=None) -> LlmResult:
        ...
__all__ = ['LlmProvider', 'LlmResult', 'LlmUnavailable']
