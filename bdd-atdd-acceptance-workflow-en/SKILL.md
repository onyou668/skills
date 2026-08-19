---
name: bdd-atdd-acceptance-workflow-en
description: "Maintain, confirm, generate, and run BDD/ATDD acceptance workflows with acceptance.md as the single source of acceptance truth. Use when the user needs to sync acceptance criteria from specs, spoken requirements, or manually edited acceptance files; preview incremental Gherkin feature changes; then, after user confirmation, inspect the real project code to generate bindings, test scripts, execution commands, and reports for Go, Python, Node.js, Java, Rust, HTTP APIs, CLIs, DB, Redis, MQ, files, and async jobs."
---

# BDD/ATDD Acceptance Workflow

## Core Principle

Treat `acceptance.md` as the single source of acceptance truth.

`acceptance.md` defines what the business behavior must be. The current code only determines how to verify it.

Do not infer expected business behavior from implementation code. Code may only be used to discover execution entry points, language, framework, routes, functions, scripts, database tables, queues, files, side effects, and assertion mechanisms.

Do not bypass `acceptance.md` and generate tests directly from a spec, spoken request, or implementation code.

Read [references/workflow-details.md](references/workflow-details.md) when generating or updating concrete acceptance assets.

## Mandatory Requirements

```text
Use acceptance.md as the only acceptance-standard source.
Sync spec, spoken additions, and manual changes into acceptance.md first.
Validate acceptance.md and safely normalize fixable format issues.
Mark scenarios with missing business expectations as pending or uncertain.
Show the incremental feature preview before generating validation logic.
Wait for explicit user confirmation of the feature preview.
Inspect current code only after the user confirms the feature preview.
Choose the validation method from real code entry points.
Record why the validation method was selected.
Prefer existing project test frameworks and execution entry points.
Update only affected units and scenarios.
Overwrite only generated blocks, never manual code.
Write a report after execution.
Distinguish pass, fail, skip, pending, and uncertain.
Ask for confirmation again before production resources, paid external services, real SMS/email, data deletion, new dependencies, or broad rewrites.
```

## Mandatory Prohibitions

```text
Never generate tests directly from a spec without updating acceptance.md.
Never generate tests directly from a spoken request without updating acceptance.md.
Never generate test code, bindings.yaml, or BDD step definitions before the user confirms the feature preview.
Never run acceptance commands before the user confirms the feature preview.
Never infer business expectations from current code.
Never treat the current implementation as proof that acceptance behavior is correct.
Never invent expected values when error codes, amounts, counts, time windows, or key business details are missing.
Never apply fixed templates without inspecting current project code.
Never choose validation style only from the programming language.
Never assume every scenario is HTTP.
Never assume every scenario is a unit test.
Never introduce a new BDD or test framework by default.
Never regenerate unrelated acceptance assets.
Never overwrite manual helpers, fixtures, or test utility code.
Never treat skip, pending, or uncertain as pass.
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
incremental feature preview
        ↓
wait for user confirmation
        ↓
inspect real project code
        ↓
choose the best BDD/ATDD validation method
        ↓
generate bindings / test scripts / execution commands
        ↓
run acceptance
        ↓
write report
```

Before confirmation, only maintain acceptance standards and show the feature preview. After confirmation, generate validation logic.

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
  Optional free-form project acceptance context.
  Use this for MySQL/Redis/MQ connection rules, HTTP base_url, setup commands, mock rules, CI limits, and project-specific notes.
```

`context` is optional free-form project text. It does not need a schema and may be empty. If present, read and follow it before generating or executing validation logic. `context` describes execution environment and project constraints; it does not override business expectations in `acceptance.md`.

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

After any effective addition, modification, or deprecation in `acceptance.md`, show the incremental feature preview first.

Show only changed scenarios unless the user asks for the full feature.

Then pause and ask for confirmation:

```text
Please confirm whether the acceptance scenario above matches your intent.
After confirmation, I will inspect the current code and generate bindings, BDD/ATDD scripts, and execution commands.
```

Do not generate validation logic until the user confirms.

## New Feature Development Flow

Split new requirements into two phases.

Phase 1, before or during development:

```text
spec / user description -> acceptance.md -> incremental feature preview -> wait for user confirmation of acceptance standard
```

This phase only decides what to accept; it does not generate final validation code.

Phase 2, after development is complete:

Enter code-aware generation only when the user explicitly says the feature/module is done or asks to generate validation logic from current code. After entering phase 2, refresh the feature preview and wait for user confirmation again. Then inspect current code and generate bindings, test code, and execution commands.

## Pre-Generation Plan

After feature confirmation and before generating validation logic, output a generation plan.

The plan must include:

```text
which code entry points will be read
which validation method will be selected
which files will be generated or updated
whether new dependencies are needed
which commands will be executed
whether DB / Redis / MQ / files / external services are involved
```

If the plan involves new dependencies, broad rewrites, production resources, real external services, or irreversible operations, wait for confirmation again. For ordinary low-risk generation, continue after showing the plan.

## Code-Aware Generation

After feature confirmation, inspect the real project code.

Do not choose tools solely by language. Do not assume all scenarios are HTTP. Do not assume all scenarios are unit tests.

Choose the validation method from:

```text
what the scenario verifies
which real entry point the code exposes
which test framework the project already uses
which path is closest to real business behavior
which path is stable, minimally invasive, and CI-friendly
whether DB / Redis / MQ / file / log side effects are required
whether polling is required for async behavior
```

If the project contains `.codegraph/`, use CodeGraph first to understand modules, symbols, routes, and call paths.

## Validation Method Selection

```text
Real HTTP/API entry point and scenario targets API behavior => use HTTP/API acceptance
Core function, rule, calculation, or boundary behavior => use unit or module-level tests
Full business workflow, transaction, or multi-component side effects => use integration tests
CLI, script, or batch task => use command acceptance with exit code, stdout, stderr, and side-effect assertions
Worker, consumer, or async job => use task trigger plus DB/Redis/MQ/log polling assertions
Project already has a BDD framework and the scenario fits executable Given/When/Then steps => generate BDD step bindings
Project has no BDD runner and adding one is costly => keep feature as BDD documentation and execute with the existing project test approach
```

Language only determines candidate tools. Scenario and code structure determine the final validation method. See [references/workflow-details.md](references/workflow-details.md) for candidate tools and detailed examples.

## Incremental Updates And Generated Regions

On every run, compare `acceptance.md` with `acceptance.lock.yaml`. Update only changed scenarios. Do not regenerate unrelated units.

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
```

Do not treat `skip`, `pending`, or `uncertain` as pass.

## Final Response Requirements

After each run, tell the user:

```text
which acceptance unit was updated
whether acceptance.md was normalized
which scenarios were added or updated
what the incremental feature preview is
whether the user has confirmed it
which assets were generated or updated
which validation method was selected and why
which commands were executed
pass / fail / skip / pending / uncertain counts
which acceptance details are still missing
```

If waiting for user confirmation, only report acceptance-file changes and the feature preview. Do not claim tests were generated or acceptance completed.

## Final Principle

`acceptance.md` defines acceptance standards.

`config.context` provides free-form project execution context.

The incremental `feature` preview lets the user confirm acceptance semantics.

Current code exposes validation entry points.

BDD/ATDD assets express and execute acceptance.

Before user confirmation, maintain only acceptance standards. After user confirmation, generate validation logic.
