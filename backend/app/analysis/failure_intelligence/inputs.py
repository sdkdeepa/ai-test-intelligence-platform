"""Structured inputs the Failure Intelligence Engine accepts.

All fields are optional. `test_case_id`, when supplied, is what unlocks
historical clustering (clustering.py) — without it, classification is based
on this occurrence's text alone and clustering is reported as missing
evidence rather than attempted.
"""

import uuid

from pydantic import BaseModel


class FailureIntelligenceInputs(BaseModel):
    __test__ = False  # not a pytest test class despite the name

    pytest_output: str | None = None
    playwright_output: str | None = None
    stack_trace: str | None = None
    ci_log: str | None = None
    application_log: str | None = None
    environment_info: str | None = None
    test_name: str | None = None
    test_case_id: uuid.UUID | None = None

    @property
    def combined_text(self) -> str:
        """All supplied raw text, concatenated for pattern matching.

        Order matters only for readability in prompts — detection below
        doesn't care which field a pattern came from, only whether it
        appears anywhere in what was supplied.
        """
        parts = (
            self.pytest_output,
            self.playwright_output,
            self.stack_trace,
            self.ci_log,
            self.application_log,
            self.environment_info,
        )
        return "\n".join(p for p in parts if p)

    @classmethod
    def from_context_inputs(cls, inputs: dict) -> "FailureIntelligenceInputs":
        return cls(
            pytest_output=inputs.get("pytest_output"),
            playwright_output=inputs.get("playwright_output"),
            stack_trace=inputs.get("stack_trace"),
            ci_log=inputs.get("ci_log"),
            application_log=inputs.get("application_log"),
            environment_info=inputs.get("environment_info"),
            test_name=inputs.get("test_name"),
            test_case_id=inputs.get("test_case_id"),
        )
