"""TestIntelligenceEngine: AI-assisted test suggestion generation.

Same combination discipline as the Risk Engine: deterministic heuristics
(heuristics.py) decide which test types apply and why, and always run —
this never depends on the LLM producing anything usable. The Claude call
generates the actual proposed test content per applicable type; if its
response can't be parsed (e.g. MockProvider's deterministic non-JSON echo),
each applicable type falls back to a deterministic placeholder proposal
rather than the run silently producing nothing.
"""

import re
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.analysis.test_intelligence.heuristics import compute_applicability, compute_input_gaps
from app.analysis.test_intelligence.inputs import TestIntelligenceInputs
from app.analysis.test_intelligence.prompts import build_test_intelligence_prompt, parse_llm_output
from app.observability.llm_tracking import observed_generate
from app.orchestration.engine import AnalysisContext, AnalysisEngine, AnalysisResult
from app.persistence.models import TestSuggestion
from app.persistence.repositories import TestSuggestionRepository
from app.providers.registry import ProviderRegistry

_TARGET_FUNCTION_RX = re.compile(r"\bdef\s+(\w+)\s*\(")

_BASE_ASSUMPTIONS = ["Assumes the supplied code/requirements reflect the final version to be tested."]


def _infer_target_function(code: str) -> str | None:
    match = _TARGET_FUNCTION_RX.search(code)
    return match.group(1) if match else None


class TestIntelligenceEngine(AnalysisEngine):
    __test__ = False  # not a pytest test class despite the name

    def __init__(self, provider_registry: ProviderRegistry, session_factory: Callable[[], Session]):
        self._provider_registry = provider_registry
        self._session_factory = session_factory

    def engine_type(self) -> str:
        return "test_intelligence"

    def run(self, context: AnalysisContext) -> AnalysisResult:
        inputs = TestIntelligenceInputs.from_context_inputs(context.inputs)
        applicability = compute_applicability(inputs)
        applicable = [a for a in applicability if a.applicable]
        input_gaps = compute_input_gaps(inputs)

        if not applicable:
            return AnalysisResult(
                status="completed",
                output={
                    "test_suggestion_ids": [],
                    "suggestions": [],
                    "uncovered_risks": [*input_gaps, "No applicable test types detected from the supplied inputs."],
                },
            )

        applicable_types = {a.test_type for a in applicable}
        provider = self._provider_registry.get("test_intelligence")
        llm_response = observed_generate(
            provider,
            build_test_intelligence_prompt(inputs, applicability),
            analysis_run_id=context.analysis_run_id,
            engine_type=self.engine_type(),
            session_factory=self._session_factory,
            correlation_id=context.correlation_id,
            trace_id=context.trace_id,
        )
        llm_suggestions = parse_llm_output(llm_response.output, applicable_types)

        target_function = _infer_target_function(inputs.code_content)
        proposals = []
        for a in applicable:
            llm = llm_suggestions.get(a.test_type)
            if llm is not None:
                proposed_test = llm.proposed_test
                rationale = llm.rationale
                assumptions = _BASE_ASSUMPTIONS + llm.assumptions
                uncovered_risks = input_gaps + llm.uncovered_risks
                confidence = max(0.0, min(1.0, a.confidence + llm.confidence_adjustment))
            else:
                proposed_test = (
                    f"# TODO: add a {a.test_type} test for {inputs.primary_reference}.\n"
                    f"# Deterministic fallback — the provider response could not be parsed "
                    f"into a structured suggestion."
                )
                rationale = (
                    f"Deterministic fallback for {a.test_type}: applicable because "
                    f"{'; '.join(a.evidence)}. The provider response could not be parsed as JSON."
                )
                assumptions = list(_BASE_ASSUMPTIONS)
                uncovered_risks = list(input_gaps)
                confidence = a.confidence

            proposals.append(
                {
                    "test_type": a.test_type,
                    "proposed_test": proposed_test,
                    "rationale": rationale,
                    "evidence": a.evidence,
                    "assumptions": assumptions,
                    "confidence": round(confidence, 4),
                    "uncovered_risks": uncovered_risks,
                    "recommended_follow_up_validation": [a.follow_up],
                }
            )

        suggestion_ids = self._persist_suggestions(context, inputs, target_function, proposals)

        output = {
            "test_suggestion_ids": [str(i) for i in suggestion_ids],
            "suggestions": proposals,
        }
        return AnalysisResult(status="completed", output=output)

    def _persist_suggestions(
        self,
        context: AnalysisContext,
        inputs: TestIntelligenceInputs,
        target_function: str | None,
        proposals: list[dict],
    ) -> list[uuid.UUID]:
        session = self._session_factory()
        try:
            repo = TestSuggestionRepository(session)
            ids = []
            for proposal in proposals:
                suggestion = repo.add(
                    TestSuggestion(
                        analysis_run_id=context.analysis_run_id,
                        repo_id=context.repo_id,
                        file_path=inputs.primary_reference,
                        target_function=target_function,
                        suggested_test_code=proposal["proposed_test"],
                        rationale=proposal["rationale"],
                        status="pending",
                        test_type=proposal["test_type"],
                        evidence=proposal["evidence"],
                        assumptions=proposal["assumptions"],
                        confidence=proposal["confidence"],
                        uncovered_risks=proposal["uncovered_risks"],
                        recommended_follow_up_validation=proposal["recommended_follow_up_validation"],
                    )
                )
                ids.append(suggestion.id)
            session.commit()
            return ids
        finally:
            session.close()
