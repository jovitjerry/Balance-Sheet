"""Local language-model access, behind a provider seam.

Lives in ``core`` because Module 2 (terminology normalization) and Module 4
(explanations and RAG chat) drive the same local model. What each module keeps
to itself is everything task-specific: its prompt, its response schema, its
validation. Only the transport is shared.
"""

from app.core.llm.base import LlmProvider, LlmResult, LlmUnavailable

__all__ = ["LlmProvider", "LlmResult", "LlmUnavailable"]
