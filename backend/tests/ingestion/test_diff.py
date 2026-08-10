from app.ingestion.diff import parse_unified_diff
from tests.fixtures.loader import load_diff_fixture

_SIMPLE_DIFF = """\
diff --git a/app/example.py b/app/example.py
index 1111111..2222222 100644
--- a/app/example.py
+++ b/app/example.py
@@ -1,3 +1,4 @@
 def foo():
-    return 1
+    return 2
+    # extra line
"""


def test_parses_a_single_modified_file():
    diff = parse_unified_diff(_SIMPLE_DIFF)

    assert diff.changed_paths == ["app/example.py"]
    file = diff.files[0]
    assert file.change_type == "modified"
    assert file.added_lines == ["    return 2", "    # extra line"]
    assert file.removed_lines == ["    return 1"]


def test_empty_diff_produces_no_files():
    diff = parse_unified_diff("")

    assert diff.files == []
    assert diff.changed_paths == []
    assert diff.total_changed_lines == 0


def test_detects_added_file():
    diff = parse_unified_diff(load_diff_fixture("new_feature_endpoint"))

    assert len(diff.files) == 1
    assert diff.files[0].change_type == "added"
    assert diff.files[0].path == "backend/app/api/webhooks.py"


def test_detects_multiple_files_in_one_diff():
    diff = parse_unified_diff(load_diff_fixture("multi_signal_change"))

    assert diff.changed_paths == [
        "backend/app/auth/permissions.py",
        "backend/app/persistence/models.py",
        ".env",
    ]


def test_total_line_counts_across_hunks():
    diff = parse_unified_diff(load_diff_fixture("dependency_bump"))

    assert diff.total_added_lines == 1
    assert diff.total_removed_lines == 1
    assert diff.total_changed_lines == 2


def test_context_lines_are_not_counted_as_changes():
    diff_text = """\
diff --git a/f.py b/f.py
index 111..222 100644
--- a/f.py
+++ b/f.py
@@ -1,3 +1,3 @@
 context before
-old
+new
 context after
"""
    diff = parse_unified_diff(diff_text)

    assert diff.files[0].added_lines == ["new"]
    assert diff.files[0].removed_lines == ["old"]
