# BDD/ATDD Acceptance Workflow Details

## Contents

- File lifecycle
- Acceptance intake example
- Feature example
- acceptance-map.yaml contract
- Test-generation protocol
- Language and framework adapters
- Real dependencies and context
- Incremental impact selection
- Execution and false-green prevention
- Failure report and repair loop
- Script commands

## File Lifecycle

| File | Editor | Purpose |
|---|---|---|
| `acceptance.md` | User or agent | Natural-language inputs, provenance, drafts, open questions |
| `<unit>.feature` | User or agent after approval | Sole canonical business acceptance contract |
| `acceptance-map.yaml` | Agent + scripts | Mapping between Feature, code entrypoints, tests, selectors, and run state |
| Project test files | Agent, preserving manual regions | Executable integration/E2E acceptance implementation |
| `reports/latest.md` | Runner + agent | Incremental result, evidence, diagnosis, and repair proposal |

After a Feature change, preserve old test paths but set `generated_tests_stale: true`. Clear stale only after executable tests are regenerated and recorded.

## Acceptance Intake Example

```markdown
# login acceptance intake

## Acceptance Scenarios

### AC-LOGIN-004 Support QQ and 163 email login

Status: active
Source: spoken
Priority: must
Type: auto

Given:
- the user account exists and may sign in

When:
- the user signs in with a QQ or 163 email address

Then:
- email support-range validation passes
- login continues to password validation
- a valid email is not reported as malformed

Data:
- case_id=qq
- case_id=163
```

`acceptance.md` may retain unapproved content. Only complete, approved criteria enter the active Feature.

## Feature Example

```gherkin
Feature: login

  @AC-LOGIN-004 @integration
  Scenario Outline: Support confirmed email domains
    Given the user account exists and may sign in
    When the user signs in with <email>
    Then email support-range validation passes
    And login continues to password validation
    And the response does not report a malformed email

    Examples:
      | case_id | email          |
      | qq      | user@qq.com    |
      | 163     | user@163.com   |
```

Each Examples row is a traceable Case. Do not place handlers, SQL, Redis keys, mocks, or commands in the Feature.

## acceptance-map.yaml Contract

```yaml
version: 2
unit: login
feature: login.feature
canonical_source: feature
mode: manual

project:
  languages:
    - go
  test_frameworks:
    - go test
  modules:
    go: backend/server

execution_policy:
  incremental_only: true
  full_repository_run_forbidden_by_default: true
  real_middleware_required_unless_context_allows_mock: true
  production_code_fix_requires_confirmation: true

scenarios:
  - id: AC-LOGIN-004
    status: active
    selected: true
    selection_reason: feature_added_or_changed
    test_level: integration
    case_ids:
      - qq
      - "163"

    business_entrypoint:
      type: http
      method: POST
      path: /api/auth/login
    validation_entrypoint: AuthHandler.Login

    style_evidence:
      - file: backend/server/internal/handlers/auth_handler_test.go
        source: project_existing_test

    dependency_resolution:
      - name: mysql
        mode: real
        availability: available
        evidence: docker-compose.test.yml
      - name: redis
        mode: real
        availability: available
        evidence: config/test.yaml

    assertion_mapping:
      - then: email support-range validation passes
        test_assertion: response business code is not email_invalid
      - then: the response does not report a malformed email
        test_assertion: response error key differs from email_invalid

    generated_tests:
      - case_id: qq
        file: backend/server/internal/handlers/login_acceptance_test.go
        symbol: TestAcceptanceLogin/AC-LOGIN-004/qq
        language: go
        framework: go-test
        test_level: integration
        discovery_command: cd backend/server && go test ./internal/handlers -list TestAcceptanceLogin
        command: cd backend/server && go test -v ./internal/handlers -run "TestAcceptanceLogin/AC-LOGIN-004/qq" -count=1

    generated_tests_stale: false
```

One Scenario may map to multiple test files, and one test file may contain generated regions for multiple Scenarios. Mapping is exact to Case and symbol.

## Test-Generation Protocol

Collect before generation:

```text
Feature Scenario and Examples
Business entrypoint and local validation entrypoint
Tests in the same module
Project test framework and CI commands
Fixture / helper / assertion / cleanup style
Real middleware configuration and availability
Git diff, symbols, and call-path impact
```

Generated code includes at least:

```text
Stable Scenario / Case identifiers
Real business entrypoint invocation
Test-data setup and isolation
Real dependencies or context-authorized mocks
An assertion for every Then
Side-effect and forbidden-side-effect assertions
Cleanup
A test symbol that can be discovered and run exactly
```

Never invent project helpers. If a shared helper is needed, show its scope first; add it only after approval and in the project's existing style.

## Language and Framework Adapters

| Stack | Typical style evidence | Exact execution candidate |
|---|---|---|
| Go/Gin/Echo | `_test.go`, table-driven tests, httptest, testcontainers | `go test <package> -run <scenario>` |
| Python/FastAPI/Django | pytest fixtures, TestClient, async markers | `pytest <file> -k <case>` |
| Node/TypeScript | Jest/Vitest/Mocha, supertest, Playwright | exact file plus `-t` / testNamePattern |
| Java/Kotlin/Spring | JUnit, MockMvc, Gradle/Maven, Testcontainers | `-Dtest=...` or Gradle `--tests` |
| Rust/Axum/Actix | `tests/`, tokio test, cargo test target | `cargo test --test <target> <filter>` |
| Flutter | `integration_test`, widget/integration distinction | exact integration-test file and device |
| .NET | xUnit/NUnit/MSTest, WebApplicationFactory | `dotnet test --filter ...` |

These are candidates only. Inspect the repository first. Reuse an existing BDD runner; do not add one merely because the contract is a Feature.

## Real Dependencies and Context

Free-text examples:

```yaml
context: |
  Acceptance connects to MySQL, Redis, and Kafka in local Docker.
  Use the real business flow and do not use mocks.
```

```yaml
context: |
  MySQL and Redis use local test instances.
  Only Kafka may use a fake.
```

The second example authorizes Kafka only. It does not authorize mocked Redis or MySQL.

Real-mode preflight:

```text
Target is local/test/sandbox
Health check succeeds
Test identity and namespace are unique
Cleanup is defined
No paid message or production resource will be used
```

Invalid-input Scenarios still use the real flow. Compare state before and after to prove no side effect. If the contract requires proof of no access, use query audit, a proxy, or observable counters rather than a no-access mock.

## Incremental Impact Selection

`acceptance-map.yaml` is the reverse index. Map changed files and symbols to business/validation entrypoints, shared dependencies, and test files.

Selection preview:

```text
baseline: main
changed: internal/account/email_policy.go

selected:
- login / AC-LOGIN-004 / qq
- login / AC-LOGIN-004 / 163

not selected:
- login / password scenarios
- payment / all scenarios
- profile / all scenarios
```

A shared authentication middleware change may select multiple units; that is still impact scope, not a full run. If impact is uncertain, stop and ask rather than substituting a full run.

## Execution and False-Green Prevention

Every generated test records a scoped discovery command. Execution order:

```text
Check map selected
-> check file and stale state
-> check context/middleware policy
-> scoped discovery proves symbol exists
-> run exact command
-> collect all selected Cases
-> write reports/latest.md
```

Reject bare `pytest`, `npm test`, `mvn test`, `cargo test`, and `go test ./...` by default. Even after explicit full-run authorization, prefer batching by unit and report the expanded scope.

## Failure Report and Repair Loop

Failure-report example:

```markdown
### AC-LOGIN-004/qq

- expected: qq.com passes email support-range validation
- actual: business code email_invalid
- evidence: response body and real DB/Redis state
- failure_type: business_code
- call_chain: POST /api/auth/login -> AuthHandler.Login -> EmailPolicy.IsAllowed
- abnormal_code: the current allowed-domain set omits qq.com
- proposed_repair: update the allowed set from the approved Feature and keep unapproved domains rejected
- planned_files: internal/account/email_policy.go
- repair_state: awaiting_fix_confirmation
```

Inspect test, environment, and data correctness before blaming production code. Approval authorizes only the reported Scenarios and files. Record each repair iteration, changed files, commands, and result until `incremental_pass` or a blocker needs renewed approval.

## Script Commands

```powershell
# Collect a spoken criterion
python <skill>/scripts/acceptance_sync.py --project-root . --unit login --criteria "..." --source spoken

# Manual preview; exit 2 means awaiting approval
python <skill>/scripts/acceptance_compile.py --project-root . --unit login

# Write canonical Feature and module map after approval
python <skill>/scripts/acceptance_compile.py --project-root . --unit login --confirmed

# Validate and refresh a directly edited Feature
python <skill>/scripts/acceptance_feature.py --project-root . --unit login --confirmed

# Record one executable Case after the agent generates it
python <skill>/scripts/acceptance_map.py --project-root . --unit login record-test `
  --scenario AC-LOGIN-004 --case-id qq `
  --file backend/server/internal/handlers/login_acceptance_test.go `
  --symbol "TestAcceptanceLogin/AC-LOGIN-004/qq" `
  --language go --framework go-test --test-level integration `
  --discovery-command "cd backend/server && go test ./internal/handlers -list TestAcceptanceLogin" `
  --command "cd backend/server && go test -v ./internal/handlers -run TestAcceptanceLogin/AC-LOGIN-004/qq -count=1"

# Run selected Cases only after execution approval
python <skill>/scripts/acceptance_run.py --project-root . --unit login
```

`--mode auto` authorizes automatic updates for that invocation. `acceptance_run.py --all` is allowed only after the user explicitly requests full acceptance for that unit; repository-wide execution needs separate explicit authorization.
