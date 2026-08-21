# BDD/ATDD Acceptance Workflow Details

## Contents

- Identity and layout
- File lifecycle
- Feature and module mapping
- Report relationships
- Code state, contract revision, and stale results
- Multi-unit execution
- Language, style, and real dependencies
- Failure diagnosis and repair reruns
- Script commands

## Identity and Layout

Use one hierarchy:

```text
Acceptance  one complete user-started acceptance lifecycle
Run         one actual execution inside that Acceptance
Unit        a business module executed in this Run
Scenario    a business behavior in the Feature
Case        one concrete Examples input
```

One Acceptance may cover multiple Units and contain multiple Runs after repairs:

```text
ACC-20260821T131530-a7c91f
├── RUN-001  login pass / account fail
├── RUN-002  account pass / login stale
└── RUN-003  login pass / Acceptance accepted
```

Layout:

```text
.acceptance/
  config.yaml
  acceptances/
    <acceptance-id>/
      report.md
      runs/
        RUN-001.md
        RUN-002.md
  units/
    <unit-id>/
      acceptance.md
      <unit-id>.feature
      acceptance-map.yaml
      reports/
        latest.md
        <acceptance-id>-<run-id>.md
```

## File Lifecycle

| File | Purpose | Mutability |
|---|---|---|
| `acceptance.md` | Natural-language intake, provenance, drafts, open questions | Maintained |
| `<unit>.feature` | Sole canonical business acceptance contract | Maintained after approval |
| `acceptance-map.yaml` | Feature, entrypoint, test, selector, selection, and latest-result mapping | Maintained |
| Project test files | Real integration/E2E implementation | Preserve manual regions |
| `acceptances/<id>/report.md` | Run index and current effective module state | Updated during Acceptance |
| `runs/RUN-xxx.md` | One execution summary | Immutable after completion |
| `units/<unit>/reports/<id>-<run>.md` | Detailed module evidence for one Run | Immutable after completion |
| `units/<unit>/reports/latest.md` | Pointers to latest module, Run, and Acceptance reports | Atomically updated |

Never delete failed history automatically after final success. Record `superseded_by` in the Acceptance summary to link an old Run to its successor.

## Feature and Module Mapping

`acceptance.md` is intake only. The approved Feature is canonical:

```gherkin
Feature: login

  @AC-LOGIN-004 @integration
  Scenario Outline: support approved email domains
    Given the account exists and may log in
    When the user logs in with <email>
    Then email support validation passes
    And password validation continues

    Examples:
      | case_id | email        |
      | qq      | user@qq.com  |
      | 163     | user@163.com |
```

Every Examples row has a stable `case_id`. Keep URLs, JSON, SQL, mocks, test paths, and commands out of Feature business semantics.

Map protocol version 3:

```yaml
version: 3
unit: login
feature: login.feature
feature_hash: 9f9c31a8d482b9ef
contract_revision: 2
canonical_source: feature
mode: manual

execution_policy:
  incremental_only: true
  full_repository_run_forbidden_by_default: true
  real_middleware_required_unless_context_allows_mock: true
  production_code_fix_requires_confirmation: true
  multi_unit_acceptance_supported: true
  immutable_run_reports: true

latest_acceptance_id: ACC-20260821T131530-a7c91f
latest_run_id: RUN-003
latest_result: incremental_pass
latest_report: reports/ACC-20260821T131530-a7c91f-RUN-003.md

scenarios:
  - id: AC-LOGIN-004
    status: active
    selected: false
    selection_reason: accepted_current_change
    case_ids: [qq, "163"]
    business_entrypoint: POST /api/auth/login
    validation_entrypoint: AuthHandler.Login
    style_evidence:
      - file: internal/handlers/auth_handler_test.go
    dependency_resolution:
      - name: mysql
        mode: real
        availability: available
    assertion_mapping:
      - then: email support validation passes
        test_assertion: response business code is not email_invalid
    generated_tests:
      - case_id: qq
        file: internal/handlers/login_acceptance_test.go
        symbol: TestAcceptanceLogin/AC-LOGIN-004/qq
        discovery_command: go test ./internal/handlers -list TestAcceptanceLogin
        command: go test ./internal/handlers -run TestAcceptanceLogin/AC-LOGIN-004/qq
    generated_tests_stale: false
```

One Scenario may map to several test files, and one file may contain generated regions for several Scenarios. Map exact Cases, symbols, and commands.

## Report Relationships

Acceptance report:

```markdown
---
acceptance_id: "ACC-20260821T131530-a7c91f"
status: "accepted"
latest_run_id: "RUN-003"
scope_units: ["login","account"]
contract_revision: 2
contract_fingerprint: "..."
code_state_id: "..."
---

| Run | Status | Superseded by | Report |
|---|---|---|---|
| RUN-001 | fail | RUN-002 | runs/RUN-001.md |
| RUN-002 | pending | RUN-003 | runs/RUN-002.md |
| RUN-003 | incremental_pass | | runs/RUN-003.md |
```

Each Run report lists only Units actually executed in that Run and links their module reports. Unselected Units do not enter that Run report and are not skip.

Module report frontmatter includes at least:

```yaml
acceptance_id: ACC-20260821T131530-a7c91f
run_id: RUN-003
unit_id: login
status: incremental_pass
code_revision: 6202ea3
code_state_id: 317f4c9a...
feature_hash: 9f9c31a...
contract_revision: 2
map_hash: 66a2e...
context_fingerprint: 72c0f...
run_report: ../../../acceptances/.../runs/RUN-003.md
acceptance_report: ../../../acceptances/.../report.md
```

`latest.md` stores pointers and current effective state only; it does not duplicate detailed evidence. Failed Runs remain immutable evidence.

## Code State, Contract Revision, and Stale Results

Before writing reports, every Run records:

```text
Git commit
tracked diff excluding .acceptance
relevant untracked file content
code_state_id
Feature contract fingerprint
acceptance-map hash
context fingerprint
```

Never store raw context, passwords, tokens, cookies, connection-string passwords, or other secrets in reports. Store redacted evidence and fingerprints only.

Increment a Unit's `contract_revision` when Feature content changes, and mark changed Scenarios' tests and old results stale. Increment the Acceptance contract revision when its scope or Feature fingerprint changes.

A prior pass remains reusable only while:

```text
Feature hash is unchanged
test mapping is not stale
Scenario is not selected again
shared-code impact analysis did not reselect the Unit
```

Otherwise the Unit's effective status is stale and a later Run must execute it again.

## Multi-Unit Execution

Generate one `run_id` per execution and share it across every Unit in that Run. One Unit failure must not stop the others.

Status rules:

```text
Every Unit in this Run passes                  -> Run incremental_pass
Any fail/error/timeout                         -> Run fail
No failure but uncertain exists                -> Run uncertain
Other incomplete state                         -> Run pending

Every scoped Unit has a current effective pass -> Acceptance accepted
Otherwise                                      -> not accepted
```

Write immutable module and Run reports first, refresh the Acceptance summary next, and atomically update module `latest.md` pointers last.

## Language, Style, and Real Dependencies

Test generation order:

1. Existing tests in the same module and acceptance level.
2. Other tests in the same module.
3. Integration tests using the same language and framework elsewhere.
4. Project configuration, dependencies, and actual CI commands.
5. If no style exists, the mainstream approach for the language/framework with recorded rationale.

| Stack | Exact execution candidate |
|---|---|
| Go | `go test <package> -run <scenario>` |
| Python | `pytest <file> -k <case>` |
| Node/TypeScript | exact file plus `-t` |
| Java/Kotlin | Maven `-Dtest` or Gradle `--tests` |
| Rust | `cargo test --test <target> <filter>` |
| Flutter | exact integration test file and device |
| .NET | `dotnet test --filter ...` |

Prefer real local/test/sandbox DB, Redis, Kafka/MQ, object storage, and similar dependencies. Allow mock only when free-text `context` explicitly authorizes it globally or for that named dependency. If a real dependency is unavailable, report environment error/pending; never silently fall back to mock.

## Failure Diagnosis and Repair Reruns

After a failed Run, report:

```text
Feature expectation and actual evidence
failure_type
call path, real file, and line
current abnormal code logic
root cause and confidence
correct repair logic
planned files before approval
affected scope and rerun command
repair_state: awaiting_fix_confirmation
```

After user approval, reuse the same `acceptance_id` and create the next Run. Record `parent_run`, `repair_confirmed`, `repair_note`, and `approved_files` in that Run report.

Recompute impact after repair. If shared code affects a previously passing module, select it again. Never rerun only the failed module and combine it with a now-stale old pass.

An approved Feature correction may remain in the same Acceptance, but every old Run is stale against the new contract. Start a new Acceptance for a separate requirement or after an already accepted lifecycle.

## Script Commands

```powershell
# First multi-unit Run: create acceptance_id and RUN-001
python <skill>/scripts/acceptance_run.py --project-root . `
  --unit login --unit account

# First Run using a caller-provided Acceptance ID
python <skill>/scripts/acceptance_run.py --project-root . `
  --acceptance-id ACC-20260821T131530-a7c91f `
  --unit login --unit account

# Approved repair: create the next Run under the same Acceptance
python <skill>/scripts/acceptance_run.py --project-root . `
  --acceptance-id ACC-20260821T131530-a7c91f `
  --unit account --unit login `
  --repair-confirmed `
  --repair-note "fix email policy and revalidate shared authentication" `
  --approved-file internal/account/email_policy.go
```

For multiple Units, pass `--scenario <unit>:<scenario-id>`. Without `--scenario`, execute only map entries with `selected: true`. Broad repository commands remain blocked by default.
