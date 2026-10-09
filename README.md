# Hyouka Flutter Workflows

A central, reusable GitHub Actions setup for Flutter projects. It uses the Flutter/Dart SDK, Android SDK tools already available on GitHub-hosted Ubuntu runners, and free open-source scanners. No paid CI provider, AI API, or paid test service is required.

## What the reusable workflow provides

- Flutter dependency resolution, analysis that keeps errors/warnings fatal while allowing `info`-level lints, unit/widget tests, optional Dart format checks, and a non-mutating `dart fix --dry-run` report.
- Optional release APK build, signature check, ABI validation, SHA-256 report, and artifact upload. The default target is `android-arm64` (arm64-v8a).
- Optional headless Android emulator execution for existing `integration_test/*_test.dart` tests.
- Gitleaks scanning of the repository's Git history and OSV-Scanner scanning of supported dependency lockfiles, including `pubspec.lock`.
- Full command logs, diagnostic files after failures, job summaries, and downloadable workflow artifacts.
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
  contents: read

jobs:
  flutter-ci:
    uses: TomasThrawat/hyouka-flutter-workflows/.github/workflows/flutter-ci.yml@v1.0.2
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
```

For maximum supply-chain stability, pin the reusable workflow reference to a full commit SHA after reviewing that commit. The examples use the published `v1.0.2` release tag. For production supply-chain stability, pin to a reviewed full commit SHA.

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
  contents: read

jobs:
  security-audit:
    uses: TomasThrawat/hyouka-flutter-workflows/.github/workflows/flutter-ci.yml@v1.0.2
    with:
      run-analyze: false
      run-tests: false
      check-format: false
      build-apk: false
      run-emulator-tests: false
      run-security-audit: true
      fail-on-security-findings: false
```

With `fail-on-security-findings: false`, scanner findings are warnings and reports are uploaded; scanner installation failures still fail. Once existing findings have been reviewed and legitimate test fixtures are configured appropriately, set it to `true` to make findings block the audit job.

## Inputs

| Input | Default | Purpose |
|---|---|---|
| `flutter-channel` | `stable` | Flutter channel |
| `flutter-version` | empty | Exact SDK version override |
| `run-analyze` | `true` | Run static analysis |
| `run-tests` | `true` | Run tests if Dart test files exist |
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

## Free-use caveat

The listed scanners and the reusable workflow are open-source/free to use. GitHub-hosted runner minutes and artifact storage are governed by the caller repository's GitHub plan. Standard runners for public repositories are free; private repositories use their included monthly quota. No workflow can guarantee zero billing if an account's plan limits are exceeded, so monitor the account's GitHub Actions usage. See [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

## Tool sources

- [Flutter](https://docs.flutter.dev/)
- [subosito/flutter-action](https://github.com/subosito/flutter-action)
- [Android Emulator Runner](https://github.com/ReactiveCircus/android-emulator-runner)
- [Gitleaks](https://github.com/gitleaks/gitleaks)
- [OSV-Scanner](https://github.com/google/osv-scanner)
