"""FailureIntelligenceEngine: classification is deterministic and factual;
root-cause hypotheses are AI-generated and clearly labeled as such.

Output shape enforces the separation Sprint 8 requires: `classification`,
`evidence`, and `missing_evidence` come only from heuristics.py and
clustering.py (facts — pattern matches and historical tallies).
`root_cause_hypotheses` and `suggested_bug_report` come only from the LLM
(prompts.py) and are never allowed to influence the classification itself —
deleting the provider call changes nothing about what this run classifies
the failure as, only removes the speculative hypotheses layered on top.
"""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.analysis.failure_intelligence.clustering import (
    HistoricalPattern,
    HistoricalSignal,
    compute_historical_signal,
    record_flaky_pattern,
)
from app.analysis.failure_intelligence.heuristics import classify, compute_missing_evidence, extract_evidence
from app.analysis.failure_intelligence.inputs import FailureIntelligenceInputs
from app.analysis.failure_intelligence.prompts import build_failure_intelligence_prompt, parse_llm_output
from app.orchestration.engine import AnalysisContext, AnalysisEngine, AnalysisResult
from app.persistence.models import FailureFinding
from app.persistence.repositories import FailureFindingRepository
from app.providers.registry import ProviderRegistry


class FailureIntelligenceEngine(AnalysisEngine):
    __test__ = False  # not a pytest test class despite the name

    def __init__(self, provider_registry: ProviderRegistry, session_factory: Callable[[], Session]):
        self._provider_registry = provider_registry
        self._session_factory = session_factory

    def engine_type(self) -> str:
        return "failure_intelligence"

    def run(self, context: AnalysisContext) -> AnalysisResult:
        inputs = FailureIntelligenceInputs.from_context_inputs(context.inputs)
        evidence = extract_evidence(inputs)

        session = self._session_factory()
        try:
            historical = (
                compute_historical_signal(session, inputs.test_case_id)
                if inputs.test_case_id is not None
                else HistoricalSignal(HistoricalPattern.INSUFFICIENT_DATA, 0, 0, 0)
            )

            classification_result = classify(evidence, historical)
            missing_evidence = compute_missing_evidence(inputs, evidence, historical)

            provider = self._provider_registry.get("failure_intelligence")
            prompt = build_failure_intelligence_prompt(inputs, evidence, classification_result)
            llm_analysis = parse_llm_output(provider.generate(prompt).output)

            final_confidence = round(
                max(0.0, min(1.0, classification_result.confidence + llm_analysis.confidence_adjustment)), 4
            )
            debugging_recommendations = (
                classification_result.debugging_recommendations + llm_analysis.debugging_recommendations
            )
            rationale = (
                f"Deterministic classification: {classification_result.classification} "
                f"(confidence {classification_result.confidence:.2f}). Historical signal: {historical.summary}"
            )

            flaky_finding_id = None
            if classification_result.classification == "flaky" and inputs.test_case_id is not None:
                flaky_finding_id = record_flaky_pattern(
                    session,
                    test_case_id=inputs.test_case_id,
                    analysis_run_id=context.analysis_run_id,
                    signal=historical,
                )

            evidence_strings = [e.detail for e in evidence]
            finding = FailureFindingRepository(session).add(
                FailureFinding(
                    test_result_id=None,  # this engine analyzes raw failure text, not a specific persisted run
                    test_case_id=inputs.test_case_id,
                    analysis_run_id=context.analysis_run_id,
                    classification=classification_result.classification,
                    confidence_score=final_confidence,
                    rationale=rationale,
                    root_cause_hypotheses=llm_analysis.root_cause_hypotheses,
                    evidence=evidence_strings,
                    missing_evidence=missing_evidence,
                    debugging_recommendations=debugging_recommendations,
                    suggested_bug_report=llm_analysis.suggested_bug_report,
                )
            )
            finding_id = finding.id
            session.commit()
        finally:
            session.close()

        output = {
            "failure_finding_id": str(finding_id),
            "classification": classification_result.classification,
            "confidence": final_confidence,
            "evidence": evidence_strings,
            "root_cause_hypotheses": llm_analysis.root_cause_hypotheses,
            "missing_evidence": missing_evidence,
            "debugging_recommendations": debugging_recommendations,
            "suggested_bug_report": llm_analysis.suggested_bug_report,
            "flaky_finding_id": str(flaky_finding_id) if flaky_finding_id is not None else None,
        }
        return AnalysisResult(status="completed", output=output)
