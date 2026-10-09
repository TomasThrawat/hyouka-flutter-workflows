#!/usr/bin/env python3
"""Offline contract and regression tests for the central reusable Flutter workflow."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "flutter-ci.yml"
VALIDATION_WORKFLOW = ROOT / ".github" / "workflows" / "validate.yml"
source = WORKFLOW.read_text(encoding="utf-8")
validation_source = VALIDATION_WORKFLOW.read_text(encoding="utf-8")

required_contract = [
    "Snapshot the complete project before inspection",
    "Snapshot complete source before security inspection",
    "GIT_CONFIG_COUNT: 2",
    "GIT_CONFIG_KEY_0: init.defaultBranch",
    "GIT_CONFIG_VALUE_0: main",
    "GIT_CONFIG_KEY_1: advice.defaultBranchName",
    "GIT_CONFIG_VALUE_1: false",
    "Refresh Android plugin registration after dependency resolution",
    "flutter build apk --config-only",
    "--split-per-abi",
    "app-$EXPECTED_ABI-release.apk",
    'SELECTED_APK="$OUTPUT_DIR/app-$EXPECTED_ABI-release.apk"',
    "actions/cache/restore@v5",
    "actions/cache/save@v5",
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
    "gh run download",
    "GH_TOKEN: ${{ github.token }}",
    "actions: read",
    "No supported dependency lockfiles found; OSV dependency scan skipped.",
    "GITLEAKS_STATUS",
    "OSV_STATUS",
    "known_flutter_tool_noise",
    "Caught exception: Already watching path:",
    "flutter-complete-report-",
    "fail-on-security-findings",
    "enable-targeted-pr-tests",
    "Determine changed files and select safe PR tests",
    "Run Android install-and-launch smoke test",
    "Generate APK metadata and enforce size and permission rules",
    "Enforce configurable quality gates",
    "Analyze warning regressions and classify build logs",
    "generate-artifact-attestation",
    "actions/attest@v4",
    "run_duration_seconds",
    "coverage_percent",
    "apk_size_bytes",
    "new_warning_count",
]
for marker in required_contract:
    assert marker in source, f"Required workflow capability missing: {marker}"

assert "actions/download-artifact@" not in source, "The unified reporter must avoid the Node-based artifact action that emits DEP0005"
assert source.count('gh run download "$GITHUB_RUN_ID" --repo "$GITHUB_REPOSITORY" --pattern') == 1, "The unified reporter must download current-run report artifacts through GitHub CLI"
assert "GH_TOKEN: ${{ github.token }}" in source, "GitHub CLI must receive the workflow token explicitly"
assert "actions: read" in source, "The report job needs only read access to Actions artifacts"
assert "if [[ \"$EXPECT_FLUTTER_REPORT\" == \"true\" || \"$EXPECT_SECURITY_REPORT\" == \"true\" ]]" in source, "Skip download cleanly when both report-producing jobs are disabled"
for marker in ("GIT_CONFIG_COUNT: 2", "GIT_CONFIG_VALUE_0: main", "GIT_CONFIG_VALUE_1: false"):
    assert marker in validation_source, f"Validation workflow must suppress the obsolete Git default-branch hint: {marker}"

assert source.index("Snapshot the complete project before inspection") < source.index("Get dependencies")
assert source.index("Get dependencies") < source.index("Refresh Android plugin registration after dependency resolution") < source.index("Build Android release APK"), "Android plugin config must refresh after dependency resolution and before the APK build"
assert "actions/cache/restore@v4" not in source, "Cache restore must use the Node 24-compatible v5 action"
assert "actions/cache/save@v4" not in source, "Cache save must use the Node 24-compatible v5 action"
assert "flutter build --config-only" not in source, "Config-only refresh must be invoked through a supported Flutter build target"
assert "--split-per-abi" in source, "Target-platform builds must package an ABI-specific APK"
for target, abi in (
    ("android-arm64", "arm64-v8a"),
    ("android-arm", "armeabi-v7a"),
    ("android-x64", "x86_64"),
    ("android-riscv64", "riscv64"),
):
    assert f'{target}) EXPECTED_ABI="{abi}" ;;' in source, f"Missing or incorrect ABI mapping for {target}"
assert "Unsupported single release target platform" in source, "Unsupported Android targets must fail explicitly"
assert '"$APKSIGNER" verify --verbose "$APK"' in source, "The release APK must be signature-verified"
assert 'unzip -t "$APK"' in source, "The APK ZIP archive must be integrity-checked"
assert 'Expected exactly arm64-v8a native libraries' in source, "ARM64 builds must reject mixed/non-ARM64 native libraries"
assert 'app-$EXPECTED_ABI-release.apk' in source, "The workflow must select the APK matching the requested ABI"
assert source.index("Refresh Android plugin registration after dependency resolution") < source.index("Build Android release APK") < source.index("Verify APK, signature, and ABI"), "Android config, build, and verification order must remain valid"
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
        coverage_data = json.loads((report_dir / "coverage.json").read_text(encoding="utf-8"))
        assert coverage_data["covered_lines"] == 2 and coverage_data["total_lines"] == 3
        assert coverage_data["coverage_percent"] == 66.67
        assert coverage_data["files"][0]["uncovered"] == [2]
        assert coverage_data["files"][1]["uncovered"] == []

        # Empty executable-line set: handle LF=0/LH=0 without division-by-zero or stale output.
        (coverage_dir / "lcov.info").write_text(
            "TN:\nSF:lib/empty.dart\nLF:0\nLH:0\nend_of_record\n",
            encoding="utf-8",
        )
        exec(compile(coverage_script, "coverage_script_empty.py", "exec"), {})
        empty_summary = (report_dir / "coverage-summary.md").read_text(encoding="utf-8")
        empty_uncovered = (report_dir / "uncovered-lines.txt").read_text(encoding="utf-8")
        empty_data = json.loads((report_dir / "coverage.json").read_text(encoding="utf-8"))
        assert "- Lines covered: 0/0 (0.00%)" in empty_summary
        assert "| lib/empty.dart | 0 | 0 | 0.00% | none |" in empty_summary
        assert empty_uncovered == "\n", "An empty LCOV input must clear stale uncovered-line output"
        assert empty_data["covered_lines"] == 0 and empty_data["total_lines"] == 0
        assert empty_data["coverage_percent"] == 0

        # Full coverage boundary: 100% and an empty uncovered-line list.
        (coverage_dir / "lcov.info").write_text(
            "TN:\nSF:lib/all.dart\nDA:1,1\nDA:2,9\nLF:2\nLH:2\nend_of_record\n",
            encoding="utf-8",
        )
        exec(compile(coverage_script, "coverage_script_full.py", "exec"), {})
        full_summary = (report_dir / "coverage-summary.md").read_text(encoding="utf-8")
        full_uncovered = (report_dir / "uncovered-lines.txt").read_text(encoding="utf-8")
        full_data = json.loads((report_dir / "coverage.json").read_text(encoding="utf-8"))
        assert "- Lines covered: 2/2 (100.00%)" in full_summary
        assert full_uncovered == "\n", "100% coverage must not retain uncovered lines from a previous run"
        assert full_data["coverage_percent"] == 100

        # Build history regression: check previous/current status and APK hash comparison.
        history_dir = temp_path / ".ci-history"
        history_dir.mkdir()
        (report_dir / "build-history-comparison.md").unlink(missing_ok=True)
        records = [
            {"run_id": "100", "commit": "aaaa1111", "analyze": "success", "tests": "success",
             "screenshot_tests": "success", "coverage": "success", "format": "skipped",
             "emulator": "skipped", "build": "success", "apk_verify": "success", "apk_sha256": "oldhash",
             "pubspec_lock_sha256": "oldlock"},
            {"run_id": "101", "commit": "bbbb2222", "analyze": "success", "tests": "failure",
             "screenshot_tests": "skipped", "coverage": "success", "format": "skipped",
             "emulator": "skipped", "build": "success", "apk_verify": "success", "apk_sha256": "newhash",
             "pubspec_lock_sha256": "newlock"},
        ]
        (history_dir / "history.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
        )
        exec(compile(history_script, "history_script.py", "exec"), {})
        history_report = (report_dir / "build-history-comparison.md").read_text(encoding="utf-8")
        assert "Previous run: 100" in history_report
        assert "APK hash changed: yes" in history_report
        assert "Dependency lock hash changed: yes" in history_report
        assert "| tests | success | failure | changed |" in history_report

        # First run: no prior cache entry must establish a baseline instead of failing.
        (history_dir / "history.jsonl").write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
        exec(compile(history_script, "history_script_first_run.py", "exec"), {})
        first_run_report = (report_dir / "build-history-comparison.md").read_text(encoding="utf-8")
        assert "No previous cache baseline was available; this run establishes it." in first_run_report
        assert "Previous run:" not in first_run_report

        # Unchanged status and hashes: comparison should be stable and report no false changes.
        identical_current = dict(records[0])
        identical_current.update({"run_id": "102", "commit": "cccc3333"})
        (history_dir / "history.jsonl").write_text(
            json.dumps(records[0]) + "\n" + json.dumps(identical_current) + "\n",
            encoding="utf-8",
        )
        exec(compile(history_script, "history_script_unchanged.py", "exec"), {})
        unchanged_report = (report_dir / "build-history-comparison.md").read_text(encoding="utf-8")
        assert "APK hash changed: no" in unchanged_report
        assert "Dependency lock hash changed: no" in unchanged_report
        assert "| tests | success | success | same |" in unchanged_report

        # Unified-log regression: prove logs from both Flutter and security folders are analyzed.
        jobs = temp_path / "combined-reports" / "jobs"
        flutter_logs = jobs / "flutter-ci-reports-555"
        security_logs = jobs / "flutter-security-reports-555"
        flutter_logs.mkdir(parents=True)
        security_logs.mkdir(parents=True)
        (flutter_logs / "flutter-test.log").write_text(
            "All tests passed\n::error::synthetic error marker\nwarning: synthetic warning\n"
            "info • synthetic Dart info lint\n"
            "Caught exception: Already watching path: /tmp/project/android\n",
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
        assert analysis["matches_by_category"]["info_lints"] == 1, "Dart info-level lints must be counted separately"
        assert analysis["matches_by_category"]["exceptions"] == 1, "A real exception must remain detectable while the known Flutter watcher line is excluded"
        assert analysis["matches_by_category"]["known_flutter_tool_noise"] == 1, "The duplicate-directory-watch message must be categorized as known tool noise"
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

        # Artifact opt-out: no reports are required when both producer jobs are disabled.
        shutil.rmtree(flutter_logs, ignore_errors=True)
        shutil.rmtree(security_logs, ignore_errors=True)
        os.environ.update({
            "EXPECT_FLUTTER_REPORT": "false",
            "EXPECT_SECURITY_REPORT": "false",
            "DOWNLOAD_STEP_RESULT": "success",
        })
        exec(compile(log_script, "log_script_no_artifacts_expected.py", "exec"), {})
        no_artifacts = json.loads(
            (temp_path / "combined-reports" / "log-analysis.json").read_text(encoding="utf-8")
        )
        assert no_artifacts["expected_artifacts"] == []
        assert no_artifacts["missing_expected_artifacts"] == []
        assert no_artifacts["downloaded_files"] == 0
        assert no_artifacts["log_files_analyzed"] == 0
        assert all(value == 0 for value in no_artifacts["matches_by_category"].values())

        # High-volume boundary: count every matching line, cap inline findings at 500,
        # and truncate an individual matched line to 2,000 characters.
        flutter_logs.mkdir(parents=True)
        security_logs.mkdir(parents=True)
        warning_lines = [f"warning: stress-case-{index}" for index in range(505)]
        warning_lines.append("warning: " + ("x" * 2500))
        (flutter_logs / "stress.log").write_text("\n".join(warning_lines) + "\n", encoding="utf-8")
        (security_logs / "gitleaks.log").write_text("no leaks found\n", encoding="utf-8")
        os.environ.update({
            "EXPECT_FLUTTER_REPORT": "true",
            "EXPECT_SECURITY_REPORT": "true",
            "DOWNLOAD_STEP_RESULT": "success",
        })
        exec(compile(log_script, "log_script_high_volume.py", "exec"), {})
        stress_data = json.loads(
            (temp_path / "combined-reports" / "log-analysis.json").read_text(encoding="utf-8")
        )
        stress_report = (temp_path / "combined-reports" / "unified-report.md").read_text(encoding="utf-8")
        assert stress_data["matches_by_category"]["warnings"] == 506
        assert len(stress_data["matched_lines"]) == 506
        assert len(stress_data["matched_lines"][-1]["text"]) == 2000, "Long matched log lines must be truncated safely"
        assert "Inline findings capped at 500 of 506" in stress_report
        assert "warning: stress-case-504" in stress_report, "Full source logs must retain lines beyond the inline finding cap"
        assert stress_data["missing_expected_artifacts"] == []
    finally:
        os.chdir(old_cwd)

helper_tests = subprocess.run([sys.executable, str(ROOT / "scripts" / "test_ci_enhancements.py")], check=False)
assert helper_tests.returncode == 0, "CI enhancement helper regression suite failed"

print("PASS: central workflow contract markers and safe no-auto-update rules")
print(f"PASS: compiled {len(blocks)} embedded Python scripts")
print("PASS: LCOV aggregate/per-file calculations, empty input, 0% and 100% boundary regressions")
print("PASS: build-history change/no-change comparisons and first-run baseline regression")
print("PASS: unified Flutter + security log parsing, known Flutter tool-noise classification, and full-log report regression")
print("PASS: required/optional artifact detection, 500-finding cap, long-line truncation, and missing-artifact failure regression")
