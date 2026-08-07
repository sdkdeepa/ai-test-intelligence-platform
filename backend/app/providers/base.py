from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class PromptSpec(BaseModel):
    """A provider-agnostic description of a single generation request."""

    user: str
    system: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """A provider-agnostic result of a generation request.

    `output` holds the structured or free-text result; its shape is a contract
    between a prompt template and its caller, not the provider layer.
    """

    output: Any
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    request_id: str | None = None


class LLMProvider(ABC):
    """Interface every LLM backend (real or mock) must implement.

    Callers depend only on this interface, never on a concrete provider —
    see architecture.md §7.
    """

    @abstractmethod
    def name(self) -> str:
        """Stable identifier used for provider selection and usage accounting."""

    @abstractmethod
    def generate(self, prompt: PromptSpec) -> LLMResponse:
        """Run a single generation request against the provider."""
