# Hyouka Flutter Workflows

A central, reusable GitHub Actions setup for Flutter projects. It uses the Flutter/Dart SDK, Android SDK tools already available on GitHub-hosted Ubuntu runners, and free open-source scanners. No paid CI provider, AI API, or paid test service is required.

## What the reusable workflow provides

- Flutter dependency resolution, analysis that keeps errors/warnings fatal while allowing `info`-level lints, unit/widget tests, optional Dart format checks, and a non-mutating `dart fix --dry-run` report.
- Optional release APK build, explicit Android plugin-registration refresh after dependency resolution, per-ABI split packaging and target-ABI selection, signature check, ABI validation, SHA-256 report, and artifact upload. The default target is `android-arm64` (arm64-v8a).
- Optional headless Android emulator execution for existing `integration_test/*_test.dart` tests.
- Gitleaks scanning of the repository's Git history and OSV-Scanner scanning of supported dependency lockfiles, including `pubspec.lock`. Flutter dependency graph/outdated reports are informational and never run an automatic upgrade.
- A complete source snapshot and SHA-256 file manifest captured before analysis, dependency resolution, or APK inspection.
- Build history cached between runs compares check outcomes, APK SHA-256, lockfile hashes, APK size, overall coverage, elapsed duration, and new-warning counts.
- A unified report combines command logs, dependency reports, coverage, APK inventory, change-impact reasoning, warning-regression output, and build-history comparisons. It verifies expected per-job artifacts and reports when one is missing.
- GitHub checkout initialization avoids the obsolete master-branch hint. Log analysis classifies application/test errors, infrastructure signals, exceptions, warnings and info lints; deduplicates warning signatures to flag regressions; and preserves original logs. Pattern matches are signals, not proven root causes.
- Detailed test coverage reports: total coverage, per-file coverage, and exact uncovered executable lines. Offline regression tests cover empty and full coverage, first-run and unchanged build-history baselines, required versus optional artifacts, log classification, high-volume log caps, and long-line truncation.
- Golden/screenshot test comparison when tests use Flutter golden matchers and checked-in baseline images; baselines are never updated automatically.
- Full APK checks cover archive integrity, full entry listing, extracted-file hashes, signature, ABI, SHA-256, package/version/minimum-SDK metadata, permissions, largest entries, and optional size/forbidden-permission gates. An opt-in emulator smoke test installs and launches the APK and preserves screenshots, logcat and package/activity diagnostics on failure.
- Opt-in diff-aware PR test selection. Pushes, manual/release runs and uncertain platform/configuration/source mappings use the complete suite. A configured coverage gate disables targeted selection. Documentation-only PRs can skip tests only when this option is explicitly enabled.
- Optional signed artifact provenance links a verified APK to its repository, workflow and commit. It records origin and integrity claims; it does not prove the application is bug-free, and consumers must verify the attestation.
- No automatic dependency upgrades, no silent source rewrites, and no automatic commits to the caller repository.

## Call it from a Flutter project

Create `.github/workflows/flutter-ci.yml` in the app repository:

```yaml
name: Shared Flutter CI

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  actions: read
  contents: read
  pull-requests: read

jobs:
  flutter-ci:
    uses: TomasThrawat/hyouka-flutter-workflows/.github/workflows/flutter-ci.yml@92cded954be5653a48fada29e926e4a3e4f402b7
    with:
      run-analyze: true
      run-tests: true
      check-format: false
      build-apk: true
      target-platform: android-arm64
      run-emulator-tests: false
      run-security-audit: true
      fail-on-security-findings: false
      artifact-name: my-app-arm64-apk
      enable-targeted-pr-tests: false
      run-apk-smoke-test: false
      min-coverage-percent: 0
      max-apk-size-mb: 0
      max-apk-entry-size-mb: 0
      forbid-permissions: ''
      fail-on-new-warnings: false
      generate-artifact-attestation: false
```

The examples pin commit [92cded954be5653a48fada29e926e4a3e4f402b7](https://github.com/TomasThrawat/hyouka-flutter-workflows/commit/92cded954be5653a48fada29e926e4a3e4f402b7), which contains the new inputs. The older v1.1.8 tag does not include these features. Review and update the full commit SHA when choosing a newer revision. Enabling targeted PR selection requires the caller to grant pull-requests: read. Enabling artifact attestation additionally requires the reusable-call job to grant id-token: write and attestations: write; leave attestation off unless the repository is eligible.

## Audit existing custom builds without replacing them

Projects with special Android setup, release signing, OAuth configuration, native patches, or custom packaging should keep those existing build workflows until they are intentionally migrated. To add only the security audit, use this caller configuration:

```yaml
name: Shared Flutter Security Audit

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  actions: read
  contents: read

jobs:
  security-audit:
    uses: TomasThrawat/hyouka-flutter-workflows/.github/workflows/flutter-ci.yml@92cded954be5653a48fada29e926e4a3e4f402b7
    with:
      run-analyze: false
      run-tests: false
      check-format: false
      build-apk: false
      run-emulator-tests: false
      run-security-audit: true
      fail-on-security-findings: false
```

With `fail-on-security-findings: false`, scanner findings are warnings and reports are uploaded; scanner installation failures still fail. Screenshot/golden matchers are detected and listed separately, but are not executed twice: the complete `flutter test --coverage` suite already runs them, and their actual failures are captured in the full test log. The workflow never creates or updates baselines. Build history uses GitHub Actions cache and starts a new baseline if no prior cache is available. Complete source snapshots and report artifacts follow GitHub Actions artifact retention and storage limits. Once existing findings have been reviewed and legitimate test fixtures are configured appropriately, set it to `true` to make findings block the audit job.

## Inputs

| Input | Default | Purpose |
|---|---|---|
| `flutter-channel` | `stable` | Flutter channel |
| `flutter-version` | empty | Exact SDK version override |
| `run-analyze` | `true` | Run static analysis |
| `run-tests` | `true` | Run unit/widget tests if Dart test files exist and generate LCOV coverage |
| `run-screenshot-tests` | `true` | Compare existing golden/screenshot matcher tests with committed baselines |
| `generate-coverage-report` | `true` | Generate per-file coverage and uncovered-line reports when LCOV exists |
| `check-format` | `false` | Verify formatting without modifying source |
| `build-apk` | `true` | Build release APK |
| `target-platform` | `android-arm64` | Target Flutter Android ABI |
| `generate-android` | `false` | Generate `android/` only if absent |
| `android-project-name` | `app` | Used only during explicit Android generation |
| `android-organization` | `com.example` | Used only during explicit Android generation |
| `run-emulator-tests` | `false` | Run existing instrumentation/integration tests on an emulator |
| `emulator-api-level` | `35` | Android emulator API level |
| `run-security-audit` | `true` | Enable secret and dependency scans |
| `fail-on-security-findings` | `false` | Make findings fail the scanner steps |
| `artifact-name` | `flutter-android-arm64-apk` | APK artifact name |
| `enable-targeted-pr-tests` | `false` | Opt-in conservative PR-only targeted test selection; uncertain mappings run the full suite |
| `run-apk-smoke-test` | `false` | Install and launch the APK on a headless emulator; upload diagnostics on failure |
| `min-coverage-percent` | `0` | Optional minimum total line coverage; 0 disables the gate and targeted-test shortcut |
| `max-apk-size-mb` | `0` | Optional maximum compressed APK size in MiB |
| `max-apk-entry-size-mb` | `0` | Optional maximum expanded APK entry size in MiB |
| `forbid-permissions` | `empty` | Optional Android permissions that must not appear in the APK |
| `fail-on-new-warnings` | `false` | Fail when new normalized warning signatures appear after a prior baseline exists |
| `generate-artifact-attestation` | `false` | Generate signed provenance for the verified APK (requires caller permissions and eligible repository) |

## Reports and baseline requirements

Each run uploads the complete source snapshot and hashes, command logs, dependency audit, coverage summary/JSON/uncovered lines, APK metadata/permissions/largest entries, change-impact report, warning classifications/signatures, optional quality-gate report, and prior-run comparisons for checks, APK digest/size, coverage, duration and warnings.

Dependency inspection does not upgrade package constraints: when a committed `pubspec.lock` exists, `flutter pub get --enforce-lockfile` enforces it; if no lockfile exists, `flutter pub get` resolves declared constraints without committing generated files. The workflow records the lockfile SHA-256 and compares it with the previous run. `flutter pub deps`, `flutter pub outdated`, Gitleaks, and OSV-Scanner produce reports. If an app has no committed `pubspec.lock`, the security job generates a runner-local lockfile only for OSV scanning and includes it in the report; it does not commit it. If no supported lockfile can be found or generated, the audit reports the scan as skipped with a warning. No package upgrade or source rewrite is performed automatically.

## Free-use caveat

The listed scanners and the reusable workflow are open-source/free to use. GitHub-hosted runner minutes and artifact storage are governed by the caller repository's GitHub plan. Standard runners for public repositories are free; private repositories use their included monthly quota. No workflow can guarantee zero billing if an account's plan limits are exceeded, so monitor the account's GitHub Actions usage. See [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

## Tool sources

- [Flutter](https://docs.flutter.dev/)
- [subosito/flutter-action](https://github.com/subosito/flutter-action)
- [Android Emulator Runner](https://github.com/ReactiveCircus/android-emulator-runner)
- [Gitleaks](https://github.com/gitleaks/gitleaks)
- [OSV-Scanner](https://github.com/google/osv-scanner)
