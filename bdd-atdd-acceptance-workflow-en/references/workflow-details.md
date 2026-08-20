# BDD/ATDD Acceptance Workflow Details

## File Lifecycle

Human-editable:

```text
acceptance.md
config.yaml
fixtures/*
handwritten helper files
```

Not recommended for manual editing:

```text
feature.feature
bindings.yaml
```

Machine-owned or overwrite-prone:

```text
compiled/acceptance.normalized.yaml
acceptance.lock.yaml
reports/*
generated/* generated regions
```

## acceptance.md Example

```md
# Login Module Acceptance

## Metadata

Module: login
Specs:
- docs/auth/login.md

Code:
- internal/auth

Entry:
- auto

## Acceptance Scenarios

### AC-LOGIN-001 Verification code must be 6 digits

Status: active
Source: spoken
Priority: must
Type: auto
Tags: login, captcha, boundary

Given:
- The user is performing login verification

When:
- The user submits a non-6-digit verification code

Then:
- Login must fail
- The system must return a verification-code length error

Data:
- invalid_codes: ["", "12345", "1234567", "abcdef"]
- valid_codes: ["123456"]

Notes:
- Error code needs confirmation
```

## Spoken Acceptance Criterion Example

The user may say:

```text
Add an acceptance criterion to the login module:
When the user enters a wrong password, login fails, a password-error message is returned, and no token is generated.
```

The skill must sync this into `acceptance.md` first, then show the feature preview and `execution_plan_preview`. If the spoken criterion lacks key expectations, for example:

```text
Lock the account after several wrong passwords.
```

mark it `uncertain` or `pending` and list questions:

```text
- What is the failed-attempt threshold?
- How long is the account locked?
- What business code / message_id is returned?
- What should happen during login attempts while locked?
```

Do not invent default values for these fields.

## Validation And Normalization

May safely normalize:

```text
heading levels
field order
status casing
type spelling
Given/When/Then grouping
blank lines and list formatting
obviously duplicated tag formatting
```

Must not invent:

```text
business expectations
error codes
amounts
counts
time windows
database fields
third-party callback results
external service responses
```

If key information is missing, keep the scenario but mark it `pending` or `uncertain` and explain why.

## Feature Preview Example

Feature files must be standard Gherkin. Use English Gherkin keywords by default; step text may be localized. Do not put execution plans, JSON/YAML, test function names, or commands inside feature files.

```gherkin
Feature: Login module acceptance

  Scenario: AC-LOGIN-001 Verification code must be 6 digits
    Given the user is performing login verification
    When the user submits a non-6-digit verification code
    Then login must fail
    And the system must return a verification-code length error
```

### Gherkin Quality Rules

```text
Feature contains only business semantics.
Scenario names describe business behavior.
Given describes prerequisite business state.
When describes a user action or business event.
Then describes observable business results.
Steps describe WHAT, not HOW.
URLs, JSON, SQL, function names, mocks, runners, and commands belong in execution_plan_preview.
pending / uncertain should be represented with tags or execution_plan_preview, not as business steps.
```

Not recommended:

```gherkin
Scenario: AC-LOGIN-001 Wrong password
  Given POST /api/login
  When body.account="user@example.com" and body.password="bad"
  Then AuthHandler.Login returns code 10001
```

Recommended:

```gherkin
Scenario: AC-LOGIN-001 Wrong password cannot log in
  Given the user account exists and can log in
  When the user logs in with a wrong password
  Then login must fail
  And the system must not generate a login token
```

## Execution Plan Preview Example

The execution plan must come from read-only discovery of current code, and every case must contain `input / execute / assert`.

```yaml
version: 1
unit_id: client-auth-login
plans:
  - scenario_id: AC-CLIENT-AUTH-LOGIN-001
    title: Email login only allows Gmail and Outlook
    scope: local
    remote: false
    validation_method:
      type: go_handler_test
      reason: The project already has Gin handler, httptest, and sqlmock test styles; this validates local login logic without remote HTTP.
    code_evidence:
      - path: houduan/server/cmd/server/main.go
        evidence: POST /api/auth/login -> AuthHandler.Login
      - path: houduan/server/internal/handlers/auth_handler.go
        evidence: unifiedLoginReq contains loginType/accountType/areaCode/account/password
      - path: houduan/server/internal/handlers/auth_revocation_test.go
        evidence: existing handlerJSONContext/newHandlerMockDB helpers
    case_coverage:
      positive_required: true
      negative_required: true
      boundary_required: true
      side_effect_required: true
    atdd_quality_check:
      invest:
        testable: true
      three_amigos_prompts:
        business: Confirm business value, success result, and final acceptance owner
        development: Confirm local entry point, state, data, dependencies, and fixtures
        testing: Confirm failure paths, boundaries, side effects, and regression risks
    bdd_quality_check:
      gherkin_validity:
        has_given: true
        has_when: true
        has_then: true
      declarative_language:
        feature_should_describe_what_not_how: true
    cases:
      - id: invalid_format
        dependency_resolution:
          mysql:
            required_by_assertion: false
            context_config_found: may_exist
            selected_mode: no_access_mock
            reason: This case validates early rejection, so later user queries and login-state writes must not happen.
          external_http:
            required_by_assertion: false
            selected_mode: fake_server_or_mock_transport
            reason: Real third parties are not called by default.
        mock_contract:
          required_when_using_mock_fake_or_stub: true
          expected_contract_sources:
            - DTO/struct/schema/interface
            - fields actually read by the current caller
        input:
          request:
            content_type: application/json
            json:
              loginType: password
              accountType: email
              areaCode: "233"
              account: abc
              password: valid-password
        execute:
          mode: local_handler_call
          local_code: AuthHandler.Login
          setup:
            db: sqlmock
            external_services: fake_or_none
        assert:
          response:
            http_status: 200
            json:
              code: 10001
              message_id: error.auth.email_invalid
              data: null
          side_effects:
            db_queries: none
            db_writes: none
            external_calls: none
      - id: gmail_continue
        dependency_resolution:
          mysql:
            required_by_assertion: true
            context_config_found: check_context_or_project_test_config
            selected_mode: real_test_if_safe_else_fake_or_pending
            reason: If this case must prove user state or token writes, use safe local/test/sandbox dependencies or mark pending.
        input:
          request:
            content_type: application/json
            json:
              loginType: password
              accountType: email
              areaCode: "233"
              account: user@gmail.com
              password: valid-password
        execute:
          mode: local_handler_call
          local_code: AuthHandler.Login
          setup:
            db: sqlmock
        assert:
          next_observable:
            db_query:
              table: users
              where:
                email: user@gmail.com
          external_calls: none
    generated_assets_preview:
      - houduan/server/internal/handlers/auth_email_login_acceptance_test.go
      - .acceptance/units/client-auth-login/bindings.yaml
      - .acceptance/units/client-auth-login/compiled/bindings.json
    command_preview:
      - go test ./internal/handlers -run TestAcceptanceClientAuthLoginEmailDomain -count=1
    execution_policy:
      can_modify_business_code: false
      run_after_second_confirm: true
      batch_continue_on_failure: true
```

If no local entry point exists in current code, do not invent scripts or call remote services. Mark the scenario `pending` and explain the gap.

## Candidate Tools By Language

Go:

```text
go test
httptest
godog
go run
CLI execution
worker/job trigger
```

Python:

```text
pytest
pytest-bdd
behave
httpx
framework test client
subprocess
```

Node.js / TypeScript:

```text
jest
vitest
cucumber-js
supertest
playwright
child_process
```

Java:

```text
JUnit
Cucumber JVM
RestAssured
Maven/Gradle task
```

Rust:

```text
cargo test
cucumber-rs
assert_cmd
HTTP test client
```

Generic:

```text
Hurl
Newman
Bruno
curl wrapper scripts only when the user explicitly asks for remote or local-service black-box acceptance
Shell / PowerShell
database queries
Redis queries
MQ message checks
file and log assertions
```

## bindings.yaml Example

```yaml
version: 1
unit_id: login

scenarios:
  AC-LOGIN-001:
    selected_type: go_handler_test
    execution_scope: local
    remote: false
    reason: The login module exposes POST /api/login, but acceptance executes through a local handler test instead of remote HTTP.
    alternatives:
      - go_router_test
      - go_unit_test
      - godog
    command: go test ./internal/auth -run TestAcceptanceLoginCaptchaLength -count=1
    runner: internal/auth/login_acceptance_test.go
    plan_doc: generated/ac_login_001_acceptance_plan.md
    execution_plan: compiled/execution_plan.preview.yaml
    env:
      APP_ENV: test
    assertions:
      - response.status == 400
      - response.json.code == "CAPTCHA_LENGTH_INVALID"
```

If the reason cannot be stated clearly, do not generate validation logic; mark the scenario `pending`.

## acceptance.lock.yaml Example

```yaml
version: 1
unit_id: login
scenarios:
  AC-LOGIN-001:
    source_hash: abc123
    generated_files:
      - feature.feature
      - bindings.yaml
      - generated/login_acceptance_test.go
    last_selected_type: http_api
```

Change handling:

```text
Only title/description changed => show feature preview; after confirmation usually do not rebuild test code
Given/When/Then changed => show feature preview; after confirmation update bindings and test code
New scenario => show new scenario preview; after confirmation generate validation logic
Deprecated scenario => show deprecation note; after confirmation stop running it
Type changed => show execution-method impact; after confirmation reselect validation method
Data / fixture changed => show impact; after confirmation update fixture and related tests
```

## Async Assertions

Use polling for async side effects. Do not use fixed sleeps.

```yaml
eventually:
  timeout_seconds: 20
  interval_ms: 500
  assertions:
    - db.orders.status == "expired"
    - redis.order_state == "expired"
    - mq.order_events contains "order.expired"
```

Use this for script-driven DB changes, worker consumption, scheduled jobs, file generation, log output, Redis state changes, and mocked external callbacks.

## External HTTP-Call Behavior

When validating code that calls an external HTTP provider, validate current code's request construction and response handling by default. Do not call the real provider.

```yaml
external_http:
  mode: fake_server
  assert_request:
    method: POST
    path: /provider/send
    headers:
      Content-Type: application/json
    json_contains:
      to: user@example.com
  fake_response:
    status: 200
    json:
      ok: true
  assert_local_result:
    provider_status: submitted
```

## Script And Reporting Acceptance

Statistics scripts, repair scripts, and batch scripts run locally against test/sandbox fixtures by default. A successful result cannot be judged only by exit code; assert business results too.

```yaml
input:
  fixtures:
    db:
      orders:
        - id: 1
          status: paid
          amount: 100
  args:
    - --date
    - "2026-08-19"
execute:
  mode: local_script_or_runner
  command_preview: go test ./internal/stats -run TestAcceptanceDailyReport -count=1
assert:
  process:
    exit_code: 0
    stdout_contains:
      - paid_count=1
  db_after:
    daily_reports:
      - report_date: "2026-08-19"
        paid_count: 1
  idempotency:
    rerun: true
    invariant: daily_reports for date has exactly one row
```

## Report Example

```yaml
unit_id: login
run_id: 2026-08-19T10-30-00
status: fail
acceptance_state: not_accepted
summary:
  pass: 3
  fail: 1
  skip: 0
  pending: 0
  uncertain: 1
  error: 0
  timeout: 0

scenarios:
  - id: AC-LOGIN-001
    status: pass
    acceptance_state: automated_pass
    command: go test ./internal/auth -run TestAcceptanceLoginCaptchaLength

  - id: AC-LOGIN-002
    status: uncertain
    acceptance_state: not_accepted
    reason: acceptance.md does not define the account lock duration
    suggestion: Add lock duration and error code to acceptance.md
```

`acceptance_state` expresses business acceptance semantics:

```text
automated_pass   automated acceptance passed, but PO sign-off is not implied
manual_required  manual Demo / PO or business confirmation is still required
not_accepted     failed, not executed, or still pending/uncertain
```

## Bundled Scripts

This skill includes:

```text
scripts/acceptance_detect.py
scripts/acceptance_sync.py
scripts/acceptance_compile.py
scripts/acceptance_run.py
```

Scripts may only perform deterministic operations and must not invent business expectations.

### acceptance_detect.py

```bash
python scripts/acceptance_detect.py --project-root . --pretty
```

Detects:

```text
project languages
submodule paths
package managers
test frameworks
BDD tools
whether config.context exists
possible HTTP routes
local test styles and helper clues
local script entry points
suggested test commands
```

### acceptance_sync.py

```bash
python scripts/acceptance_sync.py --project-root . --unit login --criteria "Verification code must be 6 digits" --source spoken
```

Use it to:

```text
initialize .acceptance
create or update units/<unit>/acceptance.md
check similar scenarios
append a new AC scenario
show incremental feature preview
```

This script never generates `bindings.yaml`, test code, or execution commands.

### acceptance_compile.py

```bash
python scripts/acceptance_compile.py --project-root . --unit login --confirmed
```

Without `--confirmed`, it prints the feature and `execution_plan_preview` without writing execution assets.

After the user confirms the feature and `execution_plan_preview`, it generates:

```text
compiled/acceptance.normalized.yaml
compiled/execution_plan.preview.yaml
compiled/execution_plan.preview.json
feature.feature
bindings.yaml
compiled/bindings.json
acceptance.lock.yaml
generated/*_acceptance_plan.md
```

The script chooses candidate local validation methods from project detection and writes the suggested executable acceptance test path as `runner` plus the generated plan document as `plan_doc`. It does not invent business assertions, does not generate remote requests, and does not modify business code.

### acceptance_run.py

```bash
python scripts/acceptance_run.py --project-root . --unit login
```

Reads `compiled/bindings.json`, executes bound commands, and writes:

```text
reports/<run-id>.yaml
reports/<run-id>.json
reports/latest.yaml
reports/latest.json
```

Scenarios with no command or `pending`/`uncertain` status are not executed by default and are not treated as pass.

If the real acceptance test file referenced by `runner` does not exist yet, the scenario is marked `pending` and the command is not executed by default. In batch execution, one scenario failure, error, or timeout does not stop later scenarios. The final report summarizes `pass/fail/skip/pending/uncertain/error/timeout`. The runner returns 0 only when the overall status is `pass`; all other statuses return non-zero.
