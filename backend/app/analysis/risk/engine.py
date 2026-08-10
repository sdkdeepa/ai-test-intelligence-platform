"""RiskEngine: the first concrete AnalysisEngine implementation.

Combines two independent sources, never letting one silently override the
other:

1. Deterministic heuristics (`heuristics.py`) — always compute risk_score,
   categories, evidence, affected_components, recommended_regression_scope,
   and release_recommendation. Fully reproducible, no network call.
2. A Claude (or Mock, in tests/CI) call (`prompts.py`) — supplements the
   deterministic result with a narrative and a small bounded
   confidence_score adjustment, and may add categories the heuristics
   missed. It cannot change risk_score, evidence, affected_components,
   recommended_regression_scope, or release_recommendation.

This is the "don't rely only on the LLM" requirement: delete the provider
call entirely and risk_score/categories/evidence/affected_components/
recommended_regression_scope/release_recommendation are all unchanged —
only the narrative and a +/-0.15 confidence nudge are lost.
"""

import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.analysis.risk.heuristics import compute_deterministic_assessment
from app.analysis.risk.prompts import build_risk_prompt, parse_llm_output
from app.ingestion.diff import parse_unified_diff
from app.orchestration.engine import AnalysisContext, AnalysisEngine, AnalysisResult
from app.persistence.models import RiskFinding
from app.persistence.repositories import RiskFindingRepository
from app.providers.registry import ProviderRegistry


class RiskEngine(AnalysisEngine):
    def __init__(self, provider_registry: ProviderRegistry, session_factory: Callable[[], Session]):
        self._provider_registry = provider_registry
        self._session_factory = session_factory

    def engine_type(self) -> str:
        return "risk"

    def run(self, context: AnalysisContext) -> AnalysisResult:
        diff_text = context.inputs.get("diff", "")
        diff = parse_unified_diff(diff_text)
        deterministic = compute_deterministic_assessment(diff)

        provider = self._provider_registry.get("risk")
        llm_response = provider.generate(build_risk_prompt(diff, deterministic))
        llm_assessment = parse_llm_output(llm_response.output)

        final_categories = sorted(set(deterministic.categories) | set(llm_assessment.additional_categories))
        final_confidence = round(
            max(0.0, min(1.0, deterministic.confidence_score + llm_assessment.confidence_adjustment)), 4
        )
        rationale = (
            f"Deterministic assessment: risk_score={deterministic.risk_score:.2f}, "
            f"categories={', '.join(deterministic.categories) or 'none'}.\n\n"
            f"Claude assessment ({llm_response.provider}/{llm_response.model}): {llm_assessment.narrative}"
        )

        risk_finding_id = self._persist_finding(
            context=context,
            primary_file=deterministic.primary_file,
            risk_score=deterministic.risk_score,
            rationale=rationale,
            categories=final_categories,
            evidence=deterministic.evidence,
            confidence_score=final_confidence,
            affected_components=deterministic.affected_components,
            recommended_regression_scope=deterministic.recommended_regression_scope,
            release_recommendation=deterministic.release_recommendation,
        )

        output = {
            "risk_finding_id": str(risk_finding_id),
            "risk_score": deterministic.risk_score,
            "categories": final_categories,
            "evidence": deterministic.evidence,
            "confidence_score": final_confidence,
            "affected_components": deterministic.affected_components,
            "recommended_regression_scope": deterministic.recommended_regression_scope,
            "release_recommendation": deterministic.release_recommendation,
            "rationale": rationale,
        }
        return AnalysisResult(status="completed", output=output)

    def _persist_finding(
        self,
        *,
        context: AnalysisContext,
        primary_file: str,
        risk_score: float,
        rationale: str,
        categories: list[str],
        evidence: list[str],
        confidence_score: float,
        affected_components: list[str],
        recommended_regression_scope: list[str],
        release_recommendation: str,
    ) -> uuid.UUID:
        # Returns the id, not the ORM object: the session closes before this
        # method returns, and the object's attributes aren't guaranteed to
        # survive that past a commit (SessionLocal sets expire_on_commit=False
        # in production, but nothing here should depend on that).
        session = self._session_factory()
        try:
            finding = RiskFindingRepository(session).add(
                RiskFinding(
                    analysis_run_id=context.analysis_run_id,
                    repo_id=context.repo_id,
                    file_path=primary_file,
                    risk_score=risk_score,
                    rationale=rationale,
                    categories=categories,
                    evidence=evidence,
                    confidence_score=confidence_score,
                    affected_components=affected_components,
                    recommended_regression_scope=recommended_regression_scope,
                    release_recommendation=release_recommendation,
                )
            )
            finding_id = finding.id
            session.commit()
            return finding_id
        finally:
            session.close()
