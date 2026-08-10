"""Structured inputs the Test Intelligence Engine accepts.

All fields are optional — the engine works with whatever subset of source
code, requirement text, API specification, git diff, and existing test
context a caller provides. `heuristics.py`'s applicability detection
degrades gracefully as inputs go missing rather than requiring all of them.
"""

from pydantic import BaseModel

from app.ingestion.diff import GitDiff, parse_unified_diff


class TestIntelligenceInputs(BaseModel):
    # Not a pytest test class despite the name — see database.Base's __test__
    # for the same issue on the persistence models.
    __test__ = False

    source_code: str | None = None
    requirement_text: str | None = None
    api_specification: str | None = None
    diff: str | None = None
    existing_test_context: str | None = None
    file_path: str | None = None

    @property
    def parsed_diff(self) -> GitDiff | None:
        return parse_unified_diff(self.diff) if self.diff else None

    @property
    def code_content(self) -> str:
        """Text to pattern-match for code-shaped signals (imports, decorators,
        control flow) — combines any raw source_code with the diff's changed
        lines, since either or both may be supplied.
        """
        parts = [self.source_code or ""]
        diff = self.parsed_diff
        if diff is not None:
            parts.append("\n".join(line for f in diff.files for line in f.all_changed_lines))
        return "\n".join(p for p in parts if p)

    @property
    def prose_content(self) -> str:
        """Text to pattern-match for natural-language signals (requirements,
        existing test descriptions, API spec prose).
        """
        return "\n".join(p for p in (self.requirement_text, self.api_specification, self.existing_test_context) if p)

    @property
    def primary_reference(self) -> str:
        if self.file_path:
            return self.file_path
        diff = self.parsed_diff
        if diff is not None and diff.changed_paths:
            return diff.changed_paths[0]
        return "(unspecified)"

    @classmethod
    def from_context_inputs(cls, inputs: dict) -> "TestIntelligenceInputs":
        return cls(
            source_code=inputs.get("source_code"),
            requirement_text=inputs.get("requirement_text"),
            api_specification=inputs.get("api_specification"),
            diff=inputs.get("diff"),
            existing_test_context=inputs.get("existing_test_context"),
            file_path=inputs.get("file_path"),
        )
