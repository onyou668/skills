# BDD/ATDD 验收工作流细节

## 目录

- 身份与目录
- 文件生命周期
- Feature 与模块映射
- 报告关联
- 代码状态、契约版本与 stale
- 多模块执行
- 语言、风格与真实依赖
- 失败诊断与修复续跑
- 脚本命令

## 身份与目录

统一层级：

```text
Acceptance  用户发起的一次完整验收闭环
Run         该验收中的一次实际执行
Unit        本轮实际运行的业务模块
Scenario    Feature 中的业务行为
Case        Examples 中的具体输入
```

一次 Acceptance 可以覆盖多个 Unit，也可以因失败修复产生多个 Run：

```text
ACC-20260821T131530-a7c91f
├── RUN-001  login pass / account fail
├── RUN-002  account pass / login stale
└── RUN-003  login pass / Acceptance accepted
```

目录：

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

## 文件生命周期

| 文件 | 用途 | 可变性 |
|---|---|---|
| `acceptance.md` | 自然语言输入、来源、草稿、待确认问题 | 可维护 |
| `<unit>.feature` | 唯一正式业务验收标准 | 确认后维护 |
| `acceptance-map.yaml` | Feature、入口、测试、selector、选择和最新结果映射 | 可维护 |
| 项目测试文件 | 真实集成/E2E 验收实现 | 保护人工区域 |
| `acceptances/<id>/report.md` | 整次验收的 Run 索引和当前模块有效状态 | 验收期间更新 |
| `runs/RUN-xxx.md` | 一次运行总报告 | 完成后不可覆盖 |
| `units/<unit>/reports/<id>-<run>.md` | 本轮该模块的详细证据 | 完成后不可覆盖 |
| `units/<unit>/reports/latest.md` | 最近模块报告、Run 报告和 Acceptance 报告的指针 | 原子更新 |

历史失败不得在最终通过后自动删除。验收总报告用 `superseded_by` 表示旧 Run 已被后续 Run 取代。

## Feature 与模块映射

`acceptance.md` 只是 intake。确认后的 Feature 才是正式标准：

```gherkin
Feature: login

  @AC-LOGIN-004 @integration
  Scenario Outline: 支持确认的邮箱域名登录
    Given 用户账号已存在并允许登录
    When 用户使用 <email> 登录
    Then 邮箱支持范围校验应当通过
    And 登录应当继续执行后续密码校验

    Examples:
      | case_id | email        |
      | qq      | user@qq.com  |
      | 163     | user@163.com |
```

每个 Examples 行必须有稳定 `case_id`。Feature 不写 URL、JSON、SQL、mock、测试文件或命令。

映射协议 version 3：

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
      - then: 邮箱支持范围校验应当通过
        test_assertion: response business code is not email_invalid
    generated_tests:
      - case_id: qq
        file: internal/handlers/login_acceptance_test.go
        symbol: TestAcceptanceLogin/AC-LOGIN-004/qq
        discovery_command: go test ./internal/handlers -list TestAcceptanceLogin
        command: go test ./internal/handlers -run TestAcceptanceLogin/AC-LOGIN-004/qq
    generated_tests_stale: false
```

一个 Scenario 可以映射多个测试文件；一个测试文件也可以包含多个 Scenario 生成区域。必须精确到 Case、symbol 和命令。

## 报告关联

Acceptance 总报告：

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

每个 Run 总报告记录本轮实际执行的模块，并链接模块报告。未选择模块不进入本轮报告，也不记为 skip。

模块报告 frontmatter 至少包含：

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

`latest.md` 只保留指针和当前有效状态，不复制详细证据。失败 Run 仍保留；日常查看从 latest 进入最新模块报告。

## 代码状态、契约版本与 stale

每个 Run 在写报告前记录：

```text
Git commit
排除 .acceptance 后的 tracked diff
相关 untracked 文件内容
code_state_id
Feature contract fingerprint
acceptance-map hash
context fingerprint
```

不得在报告中保存 context 原文、密码、Token、Cookie、连接串密码或其他秘密，只保存脱敏证据和 fingerprint。

Feature 内容变化时递增模块 `contract_revision`，变化 Scenario 的旧测试和结果标记 stale。同一 Acceptance 的 scope 或 Feature fingerprint 变化时递增 Acceptance `contract_revision`。

旧 pass 只有同时满足以下条件才可沿用：

```text
Feature hash 未变化
测试映射未 stale
Scenario 未重新 selected
共享代码影响分析未重新选中该 Unit
```

任一条件不满足，模块有效状态是 stale，必须在后续 Run 重新执行。

## 多模块执行

一个 Run 生成一次 `run_id`，所有模块共享它。单模块失败不得中断其他模块。

整体状态：

```text
本轮所有模块通过                         -> Run incremental_pass
任一模块 fail/error/timeout              -> Run fail
没有失败但存在 uncertain                 -> Run uncertain
其余未完成                               -> Run pending

Acceptance 所有 scope Unit 当前有效结果 pass -> accepted
否则不得 accepted
```

运行报告和模块报告先写入不可变路径，随后刷新 Acceptance 总报告，最后原子更新各模块 `latest.md`。

## 语言、风格与真实依赖

测试生成顺序：

1. 同模块、同验收层级已有测试。
2. 同模块其他测试。
3. 仓库内同语言、同框架集成测试。
4. 项目配置、依赖和 CI 命令。
5. 没有既有风格时采用对应语言和框架的主流方式，并记录推荐依据。

| 技术栈 | 精确执行候选 |
|---|---|
| Go | `go test <package> -run <scenario>` |
| Python | `pytest <file> -k <case>` |
| Node/TypeScript | 指定文件并使用 `-t` |
| Java/Kotlin | Maven `-Dtest` 或 Gradle `--tests` |
| Rust | `cargo test --test <target> <filter>` |
| Flutter | 指定 integration test 文件和设备 |
| .NET | `dotnet test --filter ...` |

真实 DB、Redis、Kafka/MQ、对象存储等必须优先使用 local/test/sandbox 配置。只有自由文本 `context` 明确授权全局或指定依赖时才允许 mock。真实依赖不可用时记 environment error/pending，不得静默降级 mock。

## 失败诊断与修复续跑

Run 失败后先报告：

```text
Feature 预期与实际证据
failure_type
调用链、真实文件和行号
当前异常代码逻辑
根因与可信度
正确修复逻辑
批准前计划修改的文件
影响范围和重跑命令
repair_state: awaiting_fix_confirmation
```

用户确认后，仍使用原 `acceptance_id`，新建下一个 Run。Run 报告记录 `parent_run`、`repair_confirmed`、`repair_note` 和 `approved_files`。

修复后必须重新计算影响范围。若共享代码影响先前通过模块，重新 select 这些模块；不允许只重跑原失败模块并拼接旧 pass。

Feature 纠正经过确认后可以留在同一 Acceptance，但所有旧 Run 对新 contract 都是 stale。新增独立业务需求或已 accepted 后再次验收，创建新的 Acceptance。

## 脚本命令

```powershell
# 首次多模块运行：自动创建 acceptance_id 和 RUN-001
python <skill>/scripts/acceptance_run.py --project-root . `
  --unit login --unit account

# 使用指定 Acceptance ID 首次运行
python <skill>/scripts/acceptance_run.py --project-root . `
  --acceptance-id ACC-20260821T131530-a7c91f `
  --unit login --unit account

# 修复确认后，在同一 Acceptance 下创建下一次 Run
python <skill>/scripts/acceptance_run.py --project-root . `
  --acceptance-id ACC-20260821T131530-a7c91f `
  --unit account --unit login `
  --repair-confirmed `
  --repair-note "修复邮箱策略并重新验证共享认证逻辑" `
  --approved-file internal/account/email_policy.go
```

多 Unit 使用 `--scenario <unit>:<scenario-id>`。未提供 `--scenario` 时只运行各模块 map 中 `selected: true` 的场景。裸全量命令仍默认拒绝。
