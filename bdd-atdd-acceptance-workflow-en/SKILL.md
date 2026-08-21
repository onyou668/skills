---
name: bdd-atdd-acceptance-workflow-en
description: "Use when users maintain ATDD/BDD acceptance from development documents, spoken criteria, or Feature files; develop or change business behavior that requires integration/E2E acceptance generation, affected-acceptance checks, incremental execution, failure analysis, or confirmed repair; also applies to boundaries, API behavior, state transitions, permissions, DB/Redis/MQ/file side effects, and asynchronous flows."
---

# BDD/ATDD Acceptance Workflow

## Purpose

Add a business acceptance layer beyond an agent's TDD development: TDD validates internal units, while Feature-driven integration/E2E acceptance proves business behavior, cross-component flows, and side effects.

Implementation may vary by language, framework, and repository layout, but it must never weaken the Feature's verification requirements.

## Core Model

```text
Development document / spoken request / direct Feature edit
                          ↓
acceptance.md: natural-language intake, provenance, drafts, open questions
                          ↓
Feature change preview and approval
                          ↓
<unit>.feature: the sole canonical business acceptance contract
                          ↓
Code impact, project test style, entrypoint, and dependency discovery
                          ↓
Executable acceptance tests + acceptance-map.yaml
                          ↓
Run only affected Scenarios / Cases
                          ↓
reports/latest.md
                          ↓
Failure diagnosis -> repair proposal -> user approval -> repair and rerun until pass
```

`acceptance.md` is not the canonical contract. After Feature approval, test generation, execution, and failure decisions use the Feature only. Code reveals how to validate; it never defines the expected business result.

## Module Layout

Each unit represents a business module, API, workflow, CLI, worker, or scheduled job:

```text
.acceptance/
  config.yaml
  units/
    <unit-id>/
      acceptance.md
      <unit-id>.feature
      acceptance-map.yaml
      reports/
        latest.md
        history/                 # create only when history is requested
```

Executable test code belongs in the repository's real test directories, not under `.acceptance`. Do not generate redundant `compiled/`, bindings, lock, normalized, or per-scenario plan documents.

Read [references/workflow-details.md](references/workflow-details.md) when generating or executing assets.

## Inputs and Synchronization

Support three entry paths:

1. Development docs, PRDs, issues, or API specs: extract criteria into `acceptance.md`.
2. Spoken additions or changes: record them in `acceptance.md`, then propose an incremental Feature diff.
3. Direct Feature edits: validate and calculate changed Scenarios without letting `acceptance.md` overwrite them.

Synchronization rules:

```text
Document adds a criterion       -> append an acceptance draft
Document changes a criterion    -> show Feature diff and await approval
Document removes a criterion    -> do not delete Feature automatically; propose deprecated
Spoken/manual criterion         -> later document sync cannot overwrite it
Implementation changes          -> inspect affected Feature; do not rewrite expectations
Direct Feature edit             -> Feature wins; refresh affected test mappings
```

If an error code, amount, count, time window, state, or observable result is missing, mark the intake `pending` / `uncertain`; never invent it. Unapproved content must not enter the active Feature.

## Feature Rules

Feature files describe business WHAT only. Do not include URLs, JSON, SQL, function names, mocks, test paths, or commands.

Every Scenario needs a stable `@AC-...` tag or AC ID in its title and complete Given / When / Then steps. Prefer Scenario Outline for multiple boundaries; every Examples table must provide a stable `case_id`.

Each active Scenario covers applicable dimensions:

```text
positive / negative / boundary / permission / state-transition
side-effect / forbidden-side-effect / idempotency / concurrency
async / timeout / retry / rollback / external-dependency
```

Every Then maps to an executable assertion. BDD does not require a dedicated runner: reuse Godog, pytest-bdd, Cucumber, and similar tools when present; otherwise generate ordinary integration/E2E tests in the project's existing framework.

## Manual and Automatic Modes

Default `manual` mode:

```text
Detect acceptance impact automatically
-> show Feature and generation-map preview
-> wait for update approval
-> generate tests
-> wait for execution approval
```

After the user explicitly requests `auto`, the agent may self-approve incremental acceptance, Feature, test-code, and map updates. Execution still needs explicit authorization, unless the user explicitly requests fully automatic update and execution.

Even in auto mode, return to manual approval for ambiguity, Feature conflict, uncertain impact, new dependencies, migrations, production resources, real payment/SMS/email, paid APIs, irreversible operations, or expanded repair scope.

## Impact Analysis and Incremental Selection

Start every change from a fixed Git baseline, then calculate:

```text
Changed files and symbols
+ routes and call paths
+ shared dependencies
+ acceptance-map reverse mapping
= affected units / scenarios / cases
```

When `.codegraph/` exists, use CodeGraph first for symbols and call paths.

Generate and execute affected Cases only:

```text
Case mapping is exact       -> select that Case
Only Scenario is known      -> select all Cases in that Scenario
Only unit is known          -> select active Scenarios in that unit
Shared code changed         -> select every call-path-affected unit / Scenario
Impact is uncertain         -> mark uncertain and ask; never fall back to full run
```

Unaffected content is `not_selected`, not skipped. Reject repository-wide defaults such as `go test ./...`, bare `pytest`, `npm test`, `mvn test`, and `cargo test`. Expand to a whole unit or repository only after the user explicitly requests it.

## Project Style and Language Adapters

Test-generation priority:

1. Existing tests in the same module and same acceptance level.
2. Other tests in the same module.
3. Integration tests using the same language and framework elsewhere in the repository.
4. Test configuration, dependencies, and commands actually used by CI.
5. If none exist, the mainstream approach for the detected language and framework.

Record `style_evidence`. Match paths, package/namespace, naming, fixtures, setup/teardown, assertion library, containers, asynchronous waiting, and selector conventions.

Style consistency must not lower the test level. A Feature requiring HTTP, DB, Redis, MQ, or a complete workflow cannot be reduced to a pure-function unit test. Obtain approval before adding a framework or dependency.

Language changes the adapter and generated syntax, not the common acceptance protocol. If no reliable adapter exists, mark pending instead of producing plausible but non-executable code.

## Real Dependency Policy

`.acceptance/config.yaml` `context` is free text. Do not require structured fields; interpret its meaning.

```text
Context explicitly authorizes global mocks           -> global mocks allowed
Context authorizes one dependency's mock              -> only that dependency may be mocked
Context does not authorize mocks
+ usable local/test/sandbox configuration exists      -> real middleware required
Configured real dependency is unavailable             -> environment error / pending; no mock fallback
```

Real mode enters through the real business entrypoint, uses real test DB, Redis, Kafka/MQ, object storage, and similar middleware, and verifies final state, side effects, and forbidden side effects. Isolate and clean data with run IDs, test schemas/transactions, key prefixes, topics, and consumer groups.

Never mock the business entrypoint or production logic under acceptance. Real payment, SMS, email, push, and paid third-party calls still require separate approval even when credentials exist.

## Test Generation and Mapping

After Feature and generation-preview approval, inspect current code and generate real executable acceptance tests. A plan document is not test generation.

For every Scenario / Case, `acceptance-map.yaml` records at least:

```text
scenario_id / case_id / test_level
style_evidence
business_entrypoint / validation_entrypoint
dependency_resolution
test_file / test_symbol
exact command / discovery command
Then -> assertion mapping
selected / selection_reason / stale
```

Mark generated regions with Scenario IDs. Update only those regions; preserve manual helpers, fixtures, and test logic.

## Execution Gates

Before execution, prove:

1. Test files exist.
2. Scoped discovery finds the exact symbol / case.
3. Commands cover only selected scope.
4. Feature and test mapping are not stale.
5. Context explicitly authorizes every mock.
6. Real dependencies are available and isolated.
7. Every Then has an assertion.

Exit code 0 with no discovered or executed test is pending, never pass. One failed or timed-out Case must not stop other selected Cases.

Report `incremental_pass` only when every selected Case passes. This does not mean the whole repository passed acceptance.

## Failure Diagnosis and Repair Loop

Classify failures as `business_code`, `acceptance_test`, `environment`, `test_data`, or `feature_uncertain`.

The report includes the Feature expectation, actual evidence, route-to-symbol call path, real file and line, current abnormal code logic, root cause with confidence, correct repair logic, planned files, affected scope, and rerun command.

Stop at `awaiting_fix_confirmation`. Do not modify production code before approval.

After the user confirms repair and continued acceptance, repair only the reported scope and never change the Feature to fit implementation. Recompute impact and rerun affected acceptance after each iteration until pass. Reconfirm when the root cause changes, scope expands, or work needs a dependency, migration, or dangerous operation.

## Safety Boundary

The acceptance-generation phase may modify only Feature files, module maps, reports, and project test code. Production repair is a separate user-approved phase.

Default to local/test/sandbox. Never connect to production databases, run irreversible scripts, or call real paid services automatically.

## Scripts

```text
acceptance_detect.py   Project language, test style, route, and middleware config evidence
acceptance_sync.py     Document/spoken criteria into the acceptance.md intake
acceptance_compile.py  Feature and generation preview; confirmed canonical Feature and module map
acceptance_feature.py  Validate direct Feature edits and refresh affected mappings
acceptance_map.py      Record test paths, symbols, selectors, and incremental selection
acceptance_run.py      Run selected Cases only and write module reports/latest.md
```

Prefer scripts for deterministic operations. The agent still generates test code from the repository's real code and conventions.

## Completion Standard

A Scenario is accepted only when its Feature is approved, every boundary Case is mapped, tests exist and are discoverable, dependency policy is compliant, every Then is asserted, all affected Cases pass, and the report contains reviewable evidence.

The final response states the updated unit and Feature, affected and not-selected scope, generated files/symbols, real dependency mode, exact commands, evidence, failure diagnosis, whether repair approval is pending, and whether the result proves only an incremental pass or a complete unit pass.
