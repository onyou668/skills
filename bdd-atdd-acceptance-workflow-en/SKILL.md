---
name: bdd-atdd-acceptance-workflow-en
description: "Use when the user needs BDD/ATDD acceptance rules, acceptance.md/spec/spoken criteria sync, feature previews, execution_plan_preview, acceptance scripts, local execution commands, or acceptance reports for local-code validation across HTTP, CLI, scripts, DB, Redis, MQ, files, async jobs, and mainstream languages."
---

# BDD/ATDD Acceptance Workflow

## Core Principle

Treat `acceptance.md` as the single source of acceptance truth.

`acceptance.md` defines what the business behavior must be. The current code only determines how to verify it.

Do not infer expected business behavior from implementation code. Code may only be used to discover execution entry points, language, framework, routes, functions, scripts, database tables, queues, files, side effects, and assertion mechanisms.

Do not bypass `acceptance.md` and generate tests directly from a spec, spoken request, or implementation code.

By default this skill validates the current repository, current branch, and current code locally. The business entry point may be an HTTP API, script, CLI, worker, MQ topic, scheduled job, or external HTTP-call behavior, but the validation entry point must be local code inside the current repository.

Core goal: generate a structured local acceptance execution plan from existing code logic and `acceptance.md`. `execution_plan_preview` must describe how acceptance code will be generated with `input / execute / assert`.

Read [references/workflow-details.md](references/workflow-details.md) when generating or updating concrete acceptance assets.

Prefer the bundled scripts for deterministic steps:

```text
scripts/acceptance_detect.py
scripts/acceptance_sync.py
scripts/acceptance_compile.py
scripts/acceptance_run.py
```

## Mandatory Requirements

```text
Use acceptance.md as the only acceptance-standard source.
Sync spec, spoken additions, and manual changes into acceptance.md first.
Validate acceptance.md and safely normalize fixable format issues.
Mark scenarios with missing business expectations as pending or uncertain.
Show the incremental feature preview before generating validation logic.
Before confirmation, perform read-only discovery of relevant current code to identify business entry points, local validation entry points, input/output shapes, and existing test style.
Show a standard Gherkin feature preview and a structured execution_plan_preview.
Wait for explicit user confirmation of the feature preview and execution_plan_preview.
After confirmation, generate only acceptance assets; do not modify production business code.
After generating acceptance assets, ask whether to continue and run acceptance.
Wait for explicit execution confirmation before running acceptance commands.
Choose the validation method from real local code entry points.
Record why the validation method was selected.
Prefer existing project test frameworks and execution entry points.
Update only affected units and scenarios.
Overwrite only generated blocks, never manual code.
Run acceptance in batches; one scenario failure, error, or timeout must not stop the whole batch.
Write a report after execution with failure reasons, evidence, and suggested change locations.
Distinguish pass, fail, skip, pending, uncertain, error, and timeout.
Keep context empty when initializing .acceptance/config.yaml unless the user explicitly provides project acceptance execution context.
Ask for confirmation again before production resources, paid external services, real SMS/email, data deletion, new dependencies, or broad rewrites.
```

## Mandatory Prohibitions

```text
Never generate tests directly from a spec without updating acceptance.md.
Never generate tests directly from a spoken request without updating acceptance.md.
Never generate test code, bindings.yaml, or BDD step definitions before the user confirms the feature preview and execution_plan_preview.
Never run acceptance commands before the user confirms execution.
Never infer business expectations from current code.
Never treat the current implementation as proof that acceptance behavior is correct.
Never invent expected values when error codes, amounts, counts, time windows, or key business details are missing.
Never apply fixed templates without inspecting current project code.
Never choose validation style only from the programming language.
Never assume every scenario is HTTP.
Never assume every scenario is a unit test.
Never treat an HTTP business entry point as remote HTTP acceptance by default.
Never request remote HTTP services by default.
Never connect to remote databases, Redis, MQ, object storage, or external APIs by default.
Never call real third-party services, real SMS, real email, or real payments by default.
Never invent scripts, runners, services, helpers, CLI arguments, or test entry points that do not exist in the current repository.
Never modify handlers, services, models, repositories, configuration loading, or business rules to make acceptance pass.
Never introduce a new BDD or test framework by default.
Never regenerate unrelated acceptance assets.
Never overwrite manual helpers, fixtures, or test utility code.
Never treat skip, pending, uncertain, error, or timeout as pass.
Never write AGENTS.md rules, skill safety rules, CodeGraph availability, AI inferences, or default hints into config.context.
Never operate on production databases, real payments, real SMS, real email, or irreversible scripts automatically.
```

## Workflow Loop

```text
spec document / spoken addition / manual edit
        ↓
acceptance.md
        ↓
format validation and safe normalization
        ↓
read-only discovery of relevant current code
        ↓
identify business_entrypoint and local validation_entrypoint
        ↓
standard Gherkin incremental feature preview
        ↓
structured execution_plan_preview(input / execute / assert)
        ↓
wait for user confirmation of feature + execution_plan_preview
        ↓
generate only acceptance assets: bindings / test scripts / compiled / plan
        ↓
ask whether to run acceptance
        ↓
run acceptance in batch after execution confirmation
        ↓
collect all results without interruption
        ↓
write report, failure reasons, evidence, and suggestions
```

Before the first confirmation, read code only for discovery and previews; do not generate execution assets. After the first confirmation, generate only acceptance assets and never production code. After the second confirmation, run acceptance commands.

## Default Directory

Use `.acceptance/` at the project root by default. The user may override it in `.acceptance/config.yaml`.

```text
.acceptance/
  config.yaml
  index.yaml
  units/
    <unit-id>/
      acceptance.md
      acceptance.lock.yaml
      compiled/
        acceptance.normalized.yaml
        execution_plan.preview.yaml
        execution_plan.preview.json
        bindings.json
      feature.feature
      bindings.yaml
      generated/
      fixtures/
      reports/
```

A `unit` represents a module, requirement, API, script task, worker, scheduled job, or business workflow.

## Config Context

`.acceptance/config.yaml` may contain an optional `context` field.

```yaml
version: 1
root: .acceptance

context: |
```

`context` is optional free-form project text. It does not need a schema and may be empty.

When initializing `.acceptance/config.yaml`, keep `context` empty unless the user explicitly provides project acceptance execution context.

Do not write existing `AGENTS.md` rules, skill safety rules, CodeGraph availability, AI inferences, or default hints into `context`.

If the user fills `context`, read and follow it before generating or executing validation logic. `context` describes execution environment and project constraints; it does not override business expectations in `acceptance.md`.

## Acceptance File

Each `acceptance.md` must include metadata and acceptance scenarios. Each scenario must include:

```text
ID
title
status
source
priority
type
Given
When
Then
```

Recommended optional fields:

```text
tags
Data
Notes
```

Statuses:

```text
active      effective now; generate and run it
draft       draft only; do not generate tests
pending     missing information; do not generate executable tests
uncertain   expected behavior unclear; requires user confirmation
deprecated  obsolete; do not run, keep history
manual      manual acceptance only
```

Use `auto` as the default type. `auto` means the agent must inspect current code and choose the best validation method. Do not assume HTTP, unit tests, or BDD steps.

## Sync Rules

When syncing acceptance criteria from a spec:

```text
Spec contains a criterion that acceptance.md does not contain => append it to acceptance.md
Spec changes an existing acceptance criterion => mark conflict and wait for user confirmation
Spec removes a criterion => do not delete it automatically; mark source_missing or suggest deprecated
User-added acceptance criteria => preserve them
```

When the user adds spoken acceptance criteria:

```text
1. Locate the matching unit.
2. Read the existing acceptance.md.
3. Check for the same or similar scenario.
4. If absent, insert a new AC scenario.
5. If present, ask whether to update or skip it.
6. Validate and normalize acceptance.md.
7. Show the incremental feature preview.
8. Wait for user confirmation.
```

Specs and spoken requests may only sync into `acceptance.md`; they must not directly generate test code.

## Feature Confirmation Gate

After any effective addition, modification, or deprecation in `acceptance.md`, show the incremental feature preview and execution_plan_preview first.

The feature preview must use standard Gherkin syntax:

```text
Must include Feature:
Must use Scenario: or Scenario Outline:
Must use Given / When / Then / And / But
Scenario Outline with <variables> must include Examples:
Examples headers must cover all <variables>
Multiline text must use Doc String
Tables must use Gherkin Data Table syntax
Use English Gherkin keywords by default; step text may be localized
Never mix YAML, JSON, Markdown headings, bindings, test function names, or execution plans into feature files
```

Feature files express business acceptance semantics and user-visible business triggers. Detailed JSON parameters, response shape, DB/Redis/MQ/file assertions, test function names, and command previews belong in `execution_plan_preview`.

Show only changed scenarios unless the user asks for the full feature.

`execution_plan_preview` must be structured YAML or JSON. Each case must contain:

```text
input    request JSON, command arguments, fixture, environment variables, message body, or script input
execute  local execution method, current-repository code entry point, mocks/fakes/fixtures, timeout, and command preview
assert   response, output, side effects, absence of side effects, error codes, state changes, DB/Redis/MQ/file checks
```

The execution plan must include `code_evidence` showing where the business entry point, parameters, response, test helpers, scripts, or runners were discovered in current code.

The execution plan must cover positive and negative cases. Unless `acceptance.md` explicitly says only one direction is required, list positive, negative, boundary, and side-effect cases; missing or unclear cases must be marked `uncertain`.

Then pause and ask for confirmation:

```text
Please confirm whether the Feature and Execution Plan Preview match your acceptance intent.
After confirmation, I will generate only acceptance code, bindings, and compiled assets; I will not modify business code.
After generation, I will ask again before running acceptance.
```

Do not generate validation logic until the user confirms.

## New Feature Development Flow

Split new requirements into two phases.

Phase 1, before or during development:

```text
spec / user description -> acceptance.md -> required read-only code discovery -> incremental feature preview -> execution_plan_preview -> wait for user confirmation
```

This phase decides what to accept and how it will be validated locally later; it does not generate final validation code.

Phase 2, after development is complete:

Enter acceptance-asset generation only when the user explicitly says the feature/module is done or asks to generate validation logic from current code. Refresh read-only code discovery, feature preview, and execution_plan_preview first, then wait for confirmation. After confirmation, generate bindings, test code, and execution commands only; after generation, ask again before running acceptance.

## Execution Plan Preview

Before generating validation logic, output execution_plan_preview. It is the direct input for later acceptance-code generation, not loose prose.

The plan must include:

```text
code_evidence: current-code evidence
business_entrypoint: user-visible trigger
validation_entrypoint: local code entry point in the current repository
case_coverage: positive / negative / boundary / side-effect coverage
cases[].input: JSON, args, fixtures, env, message body
cases[].execute: local call method, mocks/fakes, command preview, timeout
cases[].assert: response, output, side effects, and absence-of-side-effect assertions
generated_assets_preview: acceptance assets to generate or update after confirmation
command_preview: local commands suggested after generation
execution_policy: no business-code edits, run only after second confirmation, continue batch on failure
```

If the plan involves new dependencies, broad test-structure rewrites, production resources, real external services, or irreversible operations, wait for confirmation again. For ordinary low-risk acceptance-asset generation, continue after the user confirms the feature and execution_plan_preview.

## Script Entry Points

Use `scripts/acceptance_detect.py` to detect project language, submodules, test frameworks, BDD tools, local test styles, config context, possible HTTP routes, and local script entry points.

Use `scripts/acceptance_sync.py` to initialize acceptance directories, maintain `acceptance.md` from specs or spoken criteria, and show the incremental feature preview. This script does not generate validation logic.

Before confirmation, use `scripts/acceptance_compile.py` to print a standard Gherkin feature preview and structured `execution_plan_preview` without writing execution assets.

After the user confirms the feature and `execution_plan_preview`, use `scripts/acceptance_compile.py --confirmed` to generate `feature.feature`, `bindings.yaml`, `compiled/*`, `acceptance.lock.yaml`, and safe generated-plan scaffolds.

After generation, ask whether to execute. Only after execution confirmation, use `scripts/acceptance_run.py` to batch-run bound commands from `compiled/bindings.json` and write reports. Scenarios without clear commands or with `pending`/`uncertain` status must not be treated as pass.

## Code-Aware Generation

Before generating the feature and `execution_plan_preview`, perform read-only discovery of the current project code. After user confirmation, inspect additional code details as needed to generate acceptance assets, while still never modifying business code.

Do not choose tools solely by language. Do not assume all scenarios are HTTP. Do not assume all scenarios are unit tests.

Choose the validation method from:

```text
what the scenario verifies
which business entry point the code exposes
which local validation_entrypoint exists in the current repository
input shape: JSON, DTO, CLI args, env, fixtures, message body
output shape: HTTP status, business code, JSON data, stdout/stderr, DB/Redis/MQ/file side effects
which test framework the project already uses
which helper, fake, mock, and fixture style the project already uses
which path is closest to real business behavior
which path is stable, minimally invasive, and CI-friendly
whether DB / Redis / MQ / file / log side effects are required
whether polling is required for async behavior
```

The validation entry point must be local repository code. If no local callable entry point can be found, mark the scenario `pending`, explain the missing entry point, and do not use a remote environment as a substitute.

If the project contains `.codegraph/`, use CodeGraph first to understand modules, symbols, routes, and call paths.

## Validation Method Selection

```text
HTTP/API business entry point and the scenario targets current local logic => prefer a local handler/router/test client such as Go httptest, Python test client, Node supertest, Java MockMvc, or Rust local router
Core function, rule, calculation, or boundary behavior => use local unit or module-level tests
Full business workflow, transaction, or multi-component side effects => use local integration tests, sqlmock, temporary DB, fake Redis/MQ, or test containers
CLI, script, or batch task => execute an existing local script or runner with test/sandbox fixtures, and assert exit code, stdout, stderr, and side effects
Worker, consumer, or async job => trigger the current repository's local worker/consumer/job entry point and poll DB/Redis/MQ/log/file side effects
External HTTP-call behavior => use a local fake server, mock transport, or recorded fixture; assert method/path/header/body/query and response handling; never call the real third party by default
Project already has a BDD framework and the scenario fits executable Given/When/Then steps => generate BDD step bindings
Project has no BDD runner and adding one is costly => keep feature as BDD documentation and execute with the existing project test approach
```

Language only determines candidate tools. Scenario and code structure determine the final validation method. See [references/workflow-details.md](references/workflow-details.md) for candidate tools and detailed examples.

Business entry point is not the same as validation method. `POST /api/auth/login` is a business entry point; a Go repository may validate it locally through `AuthHandler.Login`, a Gin router, a service, or an email-validation function.

## Incremental Updates And Generated Regions

On every run, compare `acceptance.md` with `acceptance.lock.yaml`. Update only changed scenarios. Do not regenerate unrelated units.

Acceptance generation may only add or update acceptance assets. Acceptance assets include `.acceptance/*`, `feature.feature`, `bindings.yaml`, `compiled/*`, `generated/*`, `fixtures/*`, `reports/*`, and acceptance test files under the project test directories.

Never modify production business code during acceptance generation, including handlers, services, models, repositories, config loading, business rules, migrations, or real external-service code. After an acceptance failure, only report the reason, evidence, and suggestions. Modify business code only when the user starts a separate implementation/fix task.

Generated code must use markers:

```text
BEGIN ACCEPTANCE GENERATED: AC-LOGIN-001
...
END ACCEPTANCE GENERATED: AC-LOGIN-001
```

Overwrite only generated regions. Do not overwrite manual helpers, fixtures, test utilities, or existing test logic.

## Execution Safety And Reports

Default to test, local, or sandbox environments.

Ask before:

```text
production databases
data deletion or overwrite
real payments
real SMS
real email
real push notifications
paid external APIs
irreversible scripts
database migrations
new test dependencies
broad test-structure rewrites
```

Write reports under `.acceptance/units/<unit-id>/reports/`.

Allowed statuses:

```text
pass
fail
skip
pending
uncertain
error
timeout
```

Do not treat `skip`, `pending`, `uncertain`, `error`, or `timeout` as pass.

In batch execution, a scenario failure, runtime error, panic, non-zero command exit, or timeout must be recorded for that scenario and execution must continue with later scenarios. Write the final report after all scenarios finish.

Acceptance execution may return exit code 0 only when the overall status is `pass`. If any result is `fail`, `pending`, `uncertain`, `skip`, `error`, or `timeout`, return non-zero so CI and users do not mistake it for a pass.

Reports must include:

```text
summary: pass / fail / skip / pending / uncertain / error / timeout counts
per-scenario result: scenario ID, title, validation method, command, status
failure evidence: HTTP status, business code, response body, stdout/stderr, DB/Redis/MQ/file assertion result
failure reason: actual result versus acceptance.md / feature / execution_plan_preview expectation
suggested change: which business code or config area likely needs change, and why
risk note: whether the problem may be acceptance script, environment, data, or missing business implementation
```

## Final Response Requirements

After each run, tell the user:

```text
which acceptance unit was updated
whether acceptance.md was normalized
which scenarios were added or updated
what the incremental feature preview is
what the execution_plan_preview is
whether the user has confirmed the feature and execution_plan_preview
which assets were generated or updated
which validation method was selected and why
whether execution has been confirmed a second time
which commands were executed; if not executed, say execution confirmation is pending
pass / fail / skip / pending / uncertain / error / timeout counts
failure reasons, evidence, and suggested change locations
which acceptance details are still missing
```

If waiting for the first confirmation, only report acceptance-file changes, the feature preview, and the `execution_plan_preview`. Do not claim tests were generated or acceptance completed.

If acceptance assets were generated but execution confirmation is pending, report generated assets and command previews. Do not claim acceptance passed.

## Final Principle

`acceptance.md` defines acceptance standards.

`config.context` provides free-form project execution context.

The incremental `feature` preview lets the user confirm acceptance semantics.

Current code provides the local business entry point, `validation_entrypoint`, and code evidence.

`execution_plan_preview` maps acceptance standards and current code into `input / execute / assert`.

BDD/ATDD assets express and execute acceptance.

Before the first confirmation, perform read-only code discovery and preview the feature plus `execution_plan_preview`. After the first confirmation, generate only acceptance assets. After the second confirmation, run acceptance. After failures, report differences and suggestions without modifying business code.
