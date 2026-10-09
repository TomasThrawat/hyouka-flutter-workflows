#!/usr/bin/env python3
"""Offline contract and regression tests for the central reusable Flutter workflow."""
from __future__ import annotations

import json
import os
import re
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "flutter-ci.yml"
source = WORKFLOW.read_text(encoding="utf-8")

required_contract = [
    "Snapshot the complete project before inspection",
    "Snapshot complete source before security inspection",
    "Restore previous build history",
    "Generate detailed coverage and uncovered-line report",
    "Compare screenshot and golden baselines",
    "Verify complete APK archive and inventory all entries",
    "Verify APK, signature, and ABI",
    "Collect full command logs and compare build history",
    "Resolve missing Flutter lockfile for audit without committing changes",
    "flutter pub get --enforce-lockfile",
    "pubspec_lock_sha256",
    "Dependency lock hash changed",
    "Expected exactly arm64-v8a native libraries",
    "Collect all per-job reports and analyze logs",
    "flutter-complete-report-",
    "fail-on-security-findings",
]
for marker in required_contract:
    assert marker in source, f"Required workflow capability missing: {marker}"

assert source.index("Snapshot the complete project before inspection") < source.index("Get dependencies")
assert source.index("Verify complete APK archive and inventory all entries") < source.index("Verify APK, signature, and ABI")
assert "flutter pub upgrade" not in source, "Workflow must never run flutter pub upgrade"
assert 'flutter pub get --enforce-lockfile' in source, "Committed lockfiles must be enforced"
assert 'flutter test --no-pub "${files[@]}"' not in source, "Golden tests must not run twice"
assert "dart fix --apply" not in source, "Workflow must not auto-rewrite Dart files"
assert "--update-goldens" not in source, "Workflow must not silently rewrite screenshot baselines"

# Parse all embedded Python here-documents and compile them before any runner executes.
pattern = re.compile(r"(?m)^[ \t]*python3 - <<'PY'[ \t]*\n(.*?)^[ \t]*PY[ \t]*$", re.DOTALL)
blocks = [textwrap.dedent(match) for match in pattern.findall(source)]
assert len(blocks) >= 3, f"Expected embedded coverage/history/log scripts; found {len(blocks)}"
for index, block in enumerate(blocks, 1):
    compile(block, f"embedded_workflow_python_{index}.py", "exec")

coverage_script = next(
    block for block in blocks
    if "coverage-summary.md" in block and "uncovered-lines.txt" in block
)
history_script = next(block for block in blocks if ".ci-history/history.jsonl" in block)
log_script = next(block for block in blocks if "combined-reports/log-analysis.json" in block)

with tempfile.TemporaryDirectory(prefix="hyouka-ci-contract-") as temp:
    temp_path = Path(temp)

    # Coverage regression: prove line percentage and exact uncovered line numbers.
    coverage_dir = temp_path / "coverage"
    report_dir = temp_path / "ci-reports"
    coverage_dir.mkdir()
    report_dir.mkdir()
    (coverage_dir / "lcov.info").write_text(
        "TN:\n"
        "SF:lib/math.dart\nDA:1,1\nDA:2,0\nLF:2\nLH:1\nend_of_record\n"
        "SF:lib/ui.dart\nDA:10,3\nLF:1\nLH:1\nend_of_record\n",
        encoding="utf-8",
    )
    old_cwd = Path.cwd()
    try:
        os.chdir(temp_path)
        exec(compile(coverage_script, "coverage_script.py", "exec"), {})
        summary = (report_dir / "coverage-summary.md").read_text(encoding="utf-8")
        uncovered = (report_dir / "uncovered-lines.txt").read_text(encoding="utf-8")
        assert "2/3 (66.67%)" in summary, "Coverage percentage was calculated incorrectly"
        assert "lib/math.dart: 2" in uncovered, "Exact uncovered source line was not reported"

        # Build history regression: check previous/current status and APK hash comparison.
        history_dir = temp_path / ".ci-history"
        history_dir.mkdir()
        (report_dir / "build-history-comparison.md").unlink(missing_ok=True)
        records = [
            {"run_id": "100", "commit": "aaaa1111", "analyze": "success", "tests": "success",
             "screenshot_tests": "success", "coverage": "success", "format": "skipped",
             "emulator": "skipped", "build": "success", "apk_verify": "success", "apk_sha256": "oldhash"},
            {"run_id": "101", "commit": "bbbb2222", "analyze": "success", "tests": "failure",
             "screenshot_tests": "skipped", "coverage": "success", "format": "skipped",
             "emulator": "skipped", "build": "success", "apk_verify": "success", "apk_sha256": "newhash"},
        ]
        (history_dir / "history.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
        )
        exec(compile(history_script, "history_script.py", "exec"), {})
        history_report = (report_dir / "build-history-comparison.md").read_text(encoding="utf-8")
        assert "Previous run: 100" in history_report
        assert "APK hash changed: yes" in history_report
        assert "| tests | success | failure | changed |" in history_report

        # Unified-log regression: prove logs from both Flutter and security folders are analyzed.
        jobs = temp_path / "combined-reports" / "jobs"
        flutter_logs = jobs / "flutter-ci-reports-555"
        security_logs = jobs / "flutter-security-reports-555"
        flutter_logs.mkdir(parents=True)
        security_logs.mkdir(parents=True)
        (flutter_logs / "flutter-test.log").write_text(
            "All tests passed\n::error::synthetic error marker\nwarning: synthetic warning\n",
            encoding="utf-8",
        )
        (security_logs / "gitleaks.log").write_text(
            "no leaks found\nCaught exception while parsing fixture\n", encoding="utf-8"
        )
        os.environ.update({
            "WORKFLOW_RUN_ID": "555",
            "WORKFLOW_COMMIT": "deadbeef",
            "FLUTTER_JOB_RESULT": "success",
            "SECURITY_JOB_RESULT": "success",
            "EXPECT_FLUTTER_REPORT": "true",
            "EXPECT_SECURITY_REPORT": "true",
            "DOWNLOAD_STEP_RESULT": "success",
        })
        exec(compile(log_script, "log_script.py", "exec"), {})
        analysis = json.loads(
            (temp_path / "combined-reports" / "log-analysis.json").read_text(encoding="utf-8")
        )
        combined = (temp_path / "combined-reports" / "unified-report.md").read_text(encoding="utf-8")
        assert analysis["log_files_analyzed"] == 2
        assert analysis["matches_by_category"]["errors"] == 1
        assert analysis["matches_by_category"]["warnings"] == 1
        assert analysis["matches_by_category"]["exceptions"] == 1
        assert analysis["missing_expected_artifacts"] == []
        assert "synthetic error marker" in combined and "Caught exception" in combined

        # Missing report regression: create the report, flag the missing artifact, and fail.
        import shutil
        shutil.rmtree(security_logs)
        try:
            exec(compile(log_script, "log_script_missing_artifact.py", "exec"), {})
        except SystemExit as exc:
            assert isinstance(exc.code, str) and "Expected per-job report artifacts are missing" in exc.code, "Missing required report artifacts must fail with a diagnostic"
        else:
            raise AssertionError("Missing expected security report artifact did not fail")
        missing_analysis = json.loads(
            (temp_path / "combined-reports" / "log-analysis.json").read_text(encoding="utf-8")
        )
        assert missing_analysis["missing_expected_artifacts"] == ["flutter-security-reports-555"]
        assert "MISSING REQUIRED ARTIFACT" in (
            (temp_path / "combined-reports" / "unified-report.md").read_text(encoding="utf-8")
        )
    finally:
        os.chdir(old_cwd)

print("PASS: central workflow contract markers and safe no-auto-update rules")
print(f"PASS: compiled {len(blocks)} embedded Python scripts")
print("PASS: LCOV percentage and exact uncovered-line regression")
print("PASS: cross-run build history and APK SHA-256 comparison regression")
print("PASS: unified Flutter + security log parsing and full-log report regression")
print("PASS: missing per-job report detection fails with a diagnostic report preserved")
