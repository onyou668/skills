# BDD/ATDD 验收工作流细节

## 目录

- 文件生命周期
- acceptance intake 示例
- Feature 示例
- acceptance-map.yaml 契约
- 测试生成协议
- 语言与框架适配
- 真实依赖与 context
- 增量影响选择
- 执行与防假绿
- 失败报告与修复循环
- 脚本命令

## 文件生命周期

| 文件 | 编辑者 | 用途 |
|---|---|---|
| `acceptance.md` | 用户或 Agent | 自然语言输入、来源、草稿、待确认问题 |
| `<unit>.feature` | 用户确认后由用户或 Agent 更新 | 唯一正式业务验收标准 |
| `acceptance-map.yaml` | Agent + 脚本 | Feature、代码入口、测试文件、selector 和运行状态映射 |
| 项目测试文件 | Agent，保护人工区域 | 真实集成/E2E 验收实现 |
| `reports/latest.md` | runner + Agent | 增量结果、证据、诊断和修复建议 |

Feature 变化后，保留原测试路径但标记 `generated_tests_stale: true`。生成并登记新测试后才清除 stale。

## acceptance intake 示例

```markdown
# login 验收输入

## 验收场景

### AC-LOGIN-004 新增支持 QQ 和 163 邮箱登录

状态: active
来源: spoken
优先级: must
类型: auto

Given:
- 用户账号已存在并允许登录

When:
- 用户使用 QQ 或 163 邮箱登录

Then:
- 邮箱支持范围校验通过
- 登录继续执行后续密码校验
- 不把合法邮箱返回为格式错误

Data:
- case_id=qq
- case_id=163
```

`acceptance.md` 可以保留未确认内容；只有完整且确认的场景进入 active Feature。

## Feature 示例

```gherkin
Feature: login

  @AC-LOGIN-004 @integration
  Scenario Outline: 支持确认的邮箱域名登录
    Given 用户账号已存在并允许登录
    When 用户使用 <email> 登录
    Then 邮箱支持范围校验应当通过
    And 登录应当继续执行后续密码校验
    And 不应返回邮箱格式错误

    Examples:
      | case_id | email          |
      | qq      | user@qq.com    |
      | 163     | user@163.com   |
```

每一行 Examples 是一个可追踪 Case。不要在 Feature 中写 handler、SQL、Redis key、mock 或命令。

## acceptance-map.yaml 契约

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
    go: houduan/server

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
      - file: houduan/server/internal/handlers/auth_handler_test.go
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
      - then: 邮箱支持范围校验应当通过
        test_assertion: response business code is not email_invalid
      - then: 不应返回邮箱格式错误
        test_assertion: response error key differs from email_invalid

    generated_tests:
      - case_id: qq
        file: houduan/server/internal/handlers/login_acceptance_test.go
        symbol: TestAcceptanceLogin/AC-LOGIN-004/qq
        language: go
        framework: go-test
        test_level: integration
        discovery_command: cd houduan/server && go test ./internal/handlers -list TestAcceptanceLogin
        command: cd houduan/server && go test -v ./internal/handlers -run "TestAcceptanceLogin/AC-LOGIN-004/qq" -count=1

    generated_tests_stale: false
```

一个 Scenario 可以映射多个测试文件；一个测试文件也可以容纳多个 Scenario 的生成区域。映射必须精确到 Case 和 symbol。

## 测试生成协议

生成前收集：

```text
Feature 场景与 Examples
业务入口和本地 validation entrypoint
同模块测试文件
项目测试框架与 CI 命令
fixture / helper / assertion / cleanup 风格
真实中间件配置与可用性
Git diff、符号和调用链影响范围
```

生成代码至少包含：

```text
Scenario / Case 稳定标识
真实业务入口调用
数据准备和隔离
真实依赖或 context 明确授权的 mock
每条 Then 的断言
副作用与无副作用断言
清理逻辑
可精确发现和运行的测试 symbol
```

禁止创建不存在的项目 helper。需要公共 helper 时，先说明新增范围；只在用户确认后添加，并遵循项目风格。

## 语言与框架适配

| 技术栈 | 常见风格证据 | 精确执行候选 |
|---|---|---|
| Go/Gin/Echo | `_test.go`、table-driven、httptest、testcontainers | `go test <package> -run <scenario>` |
| Python/FastAPI/Django | pytest fixture、TestClient、async marker | `pytest <file> -k <case>` |
| Node/TypeScript | Jest/Vitest/Mocha、supertest、Playwright | 指定文件并使用 `-t` / testNamePattern |
| Java/Kotlin/Spring | JUnit、MockMvc、Gradle/Maven、Testcontainers | `-Dtest=...` 或 Gradle `--tests` |
| Rust/Axum/Actix | `tests/`、tokio test、cargo test target | `cargo test --test <target> <filter>` |
| Flutter | `integration_test`、widget/integration 区分 | 指定 integration test 文件和设备 |
| .NET | xUnit/NUnit/MSTest、WebApplicationFactory | `dotnet test --filter ...` |

表格只是候选。必须先读当前项目。项目已有 BDD Runner 就复用；没有时不要为了 Feature 强制引入新框架。

## 真实依赖与 context

自由文本示例：

```yaml
context: |
  本项目验收连接本地 Docker 的 MySQL、Redis 和 Kafka。
  全部走真实业务流程，不允许 mock。
```

```yaml
context: |
  MySQL 和 Redis 使用本地测试实例。
  只有 Kafka 允许使用 fake。
```

第二个示例只授权 Kafka。不要把 Redis 或 MySQL 也改成 mock。

真实模式预检：

```text
连接目标属于 local/test/sandbox
健康检查成功
测试身份和 namespace 唯一
具备数据清理策略
不会发送真实付费消息或访问生产资源
```

错误输入场景也使用真实流程。验证无副作用时比较执行前后状态；如果业务标准要求证明“没有访问”，使用查询审计、代理或可观测计数，不要替换成 no-access mock。

## 增量影响选择

`acceptance-map.yaml` 是反向索引。Agent 将变更文件和符号映射到 business/validation entrypoint、共享依赖和测试文件。

选择预览示例：

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

共享认证中间件变化可能选中多个 unit；这仍是影响范围，不是全量。无法确定时暂停，不允许用全量运行代替分析。

## 执行与防假绿

每个 generated test 必须有 scoped discovery command。执行顺序：

```text
检查 map selected
-> 检查文件和 stale
-> 检查 context/middleware policy
-> scoped discovery 证明 symbol 存在
-> 执行 exact command
-> 收集所有选中 Case
-> 写 reports/latest.md
```

裸 `pytest`、`npm test`、`mvn test`、`cargo test` 和 `go test ./...` 默认拒绝。用户明确要求全量时也应优先按 unit 分批，报告实际扩大范围。

## 失败报告与修复循环

失败报告示例：

```markdown
### AC-LOGIN-004/qq

- expected: qq.com 通过邮箱支持范围校验
- actual: business code email_invalid
- evidence: response body and real DB/Redis state
- failure_type: business_code
- call_chain: POST /api/auth/login -> AuthHandler.Login -> EmailPolicy.IsAllowed
- abnormal_code: 当前允许域名集合缺少 qq.com
- proposed_repair: 按已确认 Feature 更新允许集合，保留其他未确认域名为拒绝
- planned_files: internal/account/email_policy.go
- repair_state: awaiting_fix_confirmation
```

Agent 必须先检查测试、环境和数据是否正确，不能看到 fail 就改生产代码。用户确认后，授权范围仅限报告列出的场景和文件。每次修复记录 iteration、changed files、commands 和 result，直到 `incremental_pass` 或出现需要重新授权的阻塞。

## 脚本命令

```powershell
# 收集口述条件
python <skill>/scripts/acceptance_sync.py --project-root . --unit login --criteria "..." --source spoken

# 手动模式预览；返回 2 表示等待确认
python <skill>/scripts/acceptance_compile.py --project-root . --unit login

# 用户确认后写正式 Feature 和模块映射
python <skill>/scripts/acceptance_compile.py --project-root . --unit login --confirmed

# 用户直接改 Feature 后校验与刷新
python <skill>/scripts/acceptance_feature.py --project-root . --unit login --confirmed

# Agent 生成真实测试后登记一个 Case
python <skill>/scripts/acceptance_map.py --project-root . --unit login record-test `
  --scenario AC-LOGIN-004 --case-id qq `
  --file houduan/server/internal/handlers/login_acceptance_test.go `
  --symbol "TestAcceptanceLogin/AC-LOGIN-004/qq" `
  --language go --framework go-test --test-level integration `
  --discovery-command "cd houduan/server && go test ./internal/handlers -list TestAcceptanceLogin" `
  --command "cd houduan/server && go test -v ./internal/handlers -run TestAcceptanceLogin/AC-LOGIN-004/qq -count=1"

# 用户确认执行后，只跑 selected Case
python <skill>/scripts/acceptance_run.py --project-root . --unit login
```

`--mode auto` 是本次调用的自动更新授权。`acceptance_run.py --all` 只允许在用户明确要求该 unit 全量验收时使用；仓库全量仍需额外明确授权。
