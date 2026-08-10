"""Git diff ingestion model.

Scope note: this is the diff-parsing piece of ingestion only — turning a
unified diff (as `git diff` / a GitHub PR diff produces) into a structured
model engines can reason about. Fetching that diff from GitHub, webhook
verification, and event normalization are the "Git/PR Adapter" pieces of
`ingestion/` per architecture.md §4's layout, and remain future scope
(Sprint 10, GitHub PR integration) — this sprint's Risk Engine takes diff
text directly as input.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

ChangeType = Literal["added", "modified", "deleted", "renamed"]

_DIFF_GIT_RE = re.compile(r"^diff --git a/(?P<a>.*) b/(?P<b>.*)$")
_HUNK_HEADER_RE = re.compile(r"^@@ .*? @@")


class DiffHunk(BaseModel):
    header: str
    added_lines: list[str] = Field(default_factory=list)
    removed_lines: list[str] = Field(default_factory=list)


class DiffFile(BaseModel):
    path: str
    old_path: str | None = None
    change_type: ChangeType = "modified"
    hunks: list[DiffHunk] = Field(default_factory=list)

    @property
    def added_lines(self) -> list[str]:
        return [line for hunk in self.hunks for line in hunk.added_lines]

    @property
    def removed_lines(self) -> list[str]:
        return [line for hunk in self.hunks for line in hunk.removed_lines]

    @property
    def all_changed_lines(self) -> list[str]:
        return self.added_lines + self.removed_lines


class GitDiff(BaseModel):
    files: list[DiffFile] = Field(default_factory=list)

    @property
    def changed_paths(self) -> list[str]:
        return [f.path for f in self.files]

    @property
    def total_added_lines(self) -> int:
        return sum(len(f.added_lines) for f in self.files)

    @property
    def total_removed_lines(self) -> int:
        return sum(len(f.removed_lines) for f in self.files)

    @property
    def total_changed_lines(self) -> int:
        return self.total_added_lines + self.total_removed_lines


def parse_unified_diff(diff_text: str) -> GitDiff:
    """Parse `git diff`-style unified diff text into a GitDiff.

    Handles the common cases: added/deleted/renamed/modified files, hunk
    headers, and added/removed line content. Not a full diff library (no
    binary-file, combined-diff, or context-line tracking) — sufficient for
    risk analysis, which only needs *what changed*, not a byte-perfect
    reconstruction.
    """
    files: list[DiffFile] = []
    current_file: dict | None = None
    current_hunk: dict | None = None

    def flush_hunk() -> None:
        nonlocal current_hunk
        if current_hunk is not None and current_file is not None:
            current_file["hunks"].append(DiffHunk(**current_hunk))
        current_hunk = None

    def flush_file() -> None:
        nonlocal current_file
        flush_hunk()
        if current_file is not None:
            files.append(DiffFile(**current_file))
        current_file = None

    for line in diff_text.splitlines():
        match = _DIFF_GIT_RE.match(line)
        if match:
            flush_file()
            current_file = {"path": match.group("b"), "old_path": None, "change_type": "modified", "hunks": []}
            continue

        if current_file is None:
            continue  # preamble before the first `diff --git` line

        if line.startswith("new file mode"):
            current_file["change_type"] = "added"
        elif line.startswith("deleted file mode"):
            current_file["change_type"] = "deleted"
        elif line.startswith("rename from "):
            current_file["old_path"] = line[len("rename from ") :]
            current_file["change_type"] = "renamed"
        elif line.startswith("rename to "):
            current_file["path"] = line[len("rename to ") :]
        elif line.startswith("--- ") or line.startswith("+++ "):
            continue
        elif _HUNK_HEADER_RE.match(line):
            flush_hunk()
            current_hunk = {"header": line, "added_lines": [], "removed_lines": []}
        elif current_hunk is not None:
            if line.startswith("+"):
                current_hunk["added_lines"].append(line[1:])
            elif line.startswith("-"):
                current_hunk["removed_lines"].append(line[1:])
            # context lines (leading space) carry no signal for risk analysis

    flush_file()
    return GitDiff(files=files)
