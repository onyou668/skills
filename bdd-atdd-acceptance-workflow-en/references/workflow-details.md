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

```gherkin
Feature: Login module acceptance

  Scenario: AC-LOGIN-001 Verification code must be 6 digits
    Given the user is performing login verification
    When the user submits a non-6-digit verification code
    Then login must fail
    And the system must return a verification-code length error
```

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
curl wrapper scripts
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
    selected_type: http_api
    reason: The login module exposes POST /api/login and verification-code validation occurs on the real login entry point, so HTTP acceptance is closest to the business path.
    alternatives:
      - go_test_service
      - godog
    command: go test ./internal/auth -run TestAcceptanceLoginCaptchaLength
    runner: generated/login_acceptance_test.go
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

## Report Example

```yaml
unit_id: login
run_id: 2026-08-19T10-30-00
status: fail
summary:
  pass: 3
  fail: 1
  skip: 0
  pending: 0
  uncertain: 1

scenarios:
  - id: AC-LOGIN-001
    status: pass
    command: go test ./internal/auth -run TestAcceptanceLoginCaptchaLength

  - id: AC-LOGIN-002
    status: uncertain
    reason: acceptance.md does not define the account lock duration
```

## Optional Future Scripts

This skill may later include:

```text
scripts/acceptance_detect.py
scripts/acceptance_sync.py
scripts/acceptance_compile.py
scripts/acceptance_run.py
```

Scripts may only perform deterministic operations and must not invent business expectations. If scripts do not exist, do not pretend they were run.
