# BDD/ATDD 验收工作流细节

## 文件生命周期

允许人工编辑：

```text
acceptance.md
config.yaml
fixtures/*
手写 helper 文件
```

不建议人工编辑：

```text
feature.feature
bindings.yaml
```

禁止人工编辑或编辑后可能被覆盖：

```text
compiled/acceptance.normalized.yaml
acceptance.lock.yaml
reports/*
generated/* 中的生成区域
```

## acceptance.md 示例

```md
# 登录模块验收文档

## 元信息

模块: login
关联规范:
- docs/auth/login.md

关联代码:
- internal/auth

关联入口:
- auto

## 验收场景

### AC-LOGIN-001 验证码必须为 6 位数字

状态: active
来源: spoken
优先级: must
类型: auto
标签: login, captcha, boundary

Given:
- 用户正在进行登录验证

When:
- 用户提交非 6 位验证码

Then:
- 登录必须失败
- 系统必须返回验证码长度错误

Data:
- invalid_codes: ["", "12345", "1234567", "abcdef"]
- valid_codes: ["123456"]

Notes:
- 错误码待确认
```

## 口头新增验收条件示例

用户可以说：

```text
给登录模块新增一个验收条件：
用户输入错误密码时，登录失败，返回密码错误提示，并且不生成 token。
```

Skill 应先同步到 `acceptance.md`，然后输出 feature 预览和 `execution_plan_preview`。如果口头条件缺少关键期望，例如：

```text
连续多次错误密码后锁定账号
```

则必须标记为 `uncertain` 或 `pending`，并列出待确认问题：

```text
- 错误次数阈值是多少？
- 锁定时长是多少？
- 返回的业务 code / message_id 是什么？
- 已锁定期间再次登录应该返回什么？
```

不要为这些值编造默认答案。

## 验收文件校验与修正

可以自动修正：

```text
标题层级
字段顺序
状态大小写
类型写法
Given/When/Then 格式
空行和列表格式
明显重复的标签格式
```

不能自动编造：

```text
业务期望值
错误码
金额
次数
时间窗口
数据库字段
第三方回调结果
外部服务响应
```

缺少关键信息时，保留场景，但标记为 `pending` 或 `uncertain`，并说明原因。

## Feature 预览示例

Feature 必须是标准 Gherkin。默认使用英文关键字，步骤文本可中文；执行计划、JSON/YAML、测试函数名和命令不要混入 feature。

```gherkin
Feature: 登录模块验收

  Scenario: AC-LOGIN-001 验证码必须为 6 位数字
    Given 用户正在进行登录验证
    When 用户提交非 6 位验证码
    Then 登录必须失败
    And 系统必须返回验证码长度错误
```

### Gherkin 质量规则

```text
Feature 只写业务语义。
Scenario 名称描述业务行为。
Given 写业务前置状态。
When 写用户动作或业务事件。
Then 写可观察业务结果。
步骤描述 WHAT，不描述 HOW。
URL、JSON、SQL、函数名、mock、runner、命令必须放到 execution_plan_preview。
pending / uncertain 应使用 tag 或 execution_plan_preview 表示，不能写成业务步骤。
```

不推荐：

```gherkin
Scenario: AC-LOGIN-001 错误密码
  Given POST /api/login
  When body.account="user@example.com" and body.password="bad"
  Then AuthHandler.Login returns code 10001
```

推荐：

```gherkin
Scenario: AC-LOGIN-001 错误密码不能登录
  Given 用户账号存在且可以登录
  When 用户使用错误密码登录
  Then 登录必须失败
  And 系统不得生成登录 token
```

## Execution Plan Preview 示例

执行计划必须来自当前代码只读发现，并且每个 case 都包含 `input / execute / assert`。

```yaml
version: 1
unit_id: client-auth-login
plans:
  - scenario_id: AC-CLIENT-AUTH-LOGIN-001
    title: 邮箱登录只允许 Gmail 和 Outlook
    scope: local
    remote: false
    validation_method:
      type: go_handler_test
      reason: 当前项目已有 Gin handler、httptest、sqlmock 测试风格；本场景验证本地登录逻辑，不请求远程 HTTP。
    code_evidence:
      - path: houduan/server/cmd/server/main.go
        evidence: POST /api/auth/login -> AuthHandler.Login
      - path: houduan/server/internal/handlers/auth_handler.go
        evidence: unifiedLoginReq 包含 loginType/accountType/areaCode/account/password
      - path: houduan/server/internal/handlers/auth_revocation_test.go
        evidence: 已有 handlerJSONContext/newHandlerMockDB 测试 helper
    case_coverage:
      positive_required: true
      negative_required: true
      boundary_required: true
      side_effect_required: true
    atdd_quality_check:
      invest:
        testable: true
      three_amigos_prompts:
        business: 确认业务价值、成功结果和最终验收人
        development: 确认本地入口、状态、数据、依赖和 fixture
        testing: 确认失败路径、边界、副作用和回归风险
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
            reason: 本 case 验证早期拦截，后续用户查询和登录状态写入不应发生。
          external_http:
            required_by_assertion: false
            selected_mode: fake_server_or_mock_transport
            reason: 默认不调用真实第三方。
        mock_contract:
          required_when_using_mock_fake_or_stub: true
          expected_contract_sources:
            - DTO/struct/schema/interface
            - 当前调用方实际读取的字段
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
            reason: 本 case 如需证明用户状态或 token 写入，必须使用安全的 local/test/sandbox 依赖或标记 pending。
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

如果当前代码没有本地入口，不要伪造脚本或远程请求，标记 `pending` 并说明缺口。

## 语言候选工具

Go：

```text
go test
httptest
godog
go run
CLI 执行
worker/job 触发器
```

Python：

```text
pytest
pytest-bdd
behave
httpx
框架 test client
subprocess
```

Node.js / TypeScript：

```text
jest
vitest
cucumber-js
supertest
playwright
child_process
```

Java：

```text
JUnit
Cucumber JVM
RestAssured
Maven/Gradle task
```

Rust：

```text
cargo test
cucumber-rs
assert_cmd
HTTP test client
```

通用：

```text
Hurl
Newman
Bruno
curl 包装脚本（仅用户明确要求远程或本地服务黑盒验收时）
Shell / PowerShell
数据库查询
Redis 查询
MQ 消息检查
文件和日志断言
```

## bindings.yaml 示例

```yaml
version: 1
unit_id: login

scenarios:
  AC-LOGIN-001:
    selected_type: go_handler_test
    execution_scope: local
    remote: false
    reason: 当前登录模块暴露 POST /api/login，但验收执行入口是本地 handler 测试，不请求远程 HTTP
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

如果原因说不清，不能生成验证逻辑，应标记为 `pending`。

## acceptance.lock.yaml 示例

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

变更处理：

```text
只改标题/描述 => 输出 feature 预览，确认后通常不重建测试代码
修改 Given/When/Then => 输出 feature 预览，确认后更新 bindings 和测试代码
新增 Scenario => 输出新增 Scenario 预览，确认后生成验证逻辑
废弃 Scenario => 输出废弃说明，确认后停止执行该场景
修改 type => 输出执行方式变化说明，确认后重新选择验收方式
修改 Data / fixture => 输出影响说明，确认后更新 fixture 和相关测试
```

## 异步断言

异步副作用必须使用轮询，不要固定 sleep。

```yaml
eventually:
  timeout_seconds: 20
  interval_ms: 500
  assertions:
    - db.orders.status == "expired"
    - redis.order_state == "expired"
    - mq.order_events contains "order.expired"
```

适用于脚本执行后数据库数字变化、worker 消费队列、定时任务执行、文件生成、日志输出、Redis 状态变化和外部回调模拟。

## 外部 HTTP 调用逻辑

验收外部 HTTP 调用逻辑时，默认验证当前代码的请求构造和响应处理，不请求真实第三方。

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

## 脚本和统计报表验收

统计脚本、修复脚本、批处理脚本默认在本地 test/sandbox fixture 中运行。判断 OK 不能只看 exit code，还要断言业务结果。

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

## 报告示例

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
    reason: 验收文件没有说明账号锁定持续时间
    suggestion: 在 acceptance.md 中补充锁定持续时间和错误码
```

`acceptance_state` 表达业务验收语义：

```text
automated_pass   自动化验收通过，但不等于 PO 已签核
manual_required  需要人工 Demo / PO 或业务确认
not_accepted     未通过、未执行或仍有 pending/uncertain
```

## 内置脚本

本 Skill 包含：

```text
scripts/acceptance_detect.py
scripts/acceptance_sync.py
scripts/acceptance_compile.py
scripts/acceptance_run.py
```

脚本只能执行确定性操作，不能凭空创造业务期望。

### acceptance_detect.py

```bash
python scripts/acceptance_detect.py --project-root . --pretty
```

用于识别：

```text
项目语言
子模块路径
包管理器
测试框架
BDD 工具
config.context 是否存在
可能的 HTTP 路由
本地测试风格和 helper 线索
本地脚本入口
建议测试命令
```

### acceptance_sync.py

```bash
python scripts/acceptance_sync.py --project-root . --unit login --criteria "验证码必须为 6 位数字" --source spoken
```

用于：

```text
初始化 .acceptance
创建或更新 units/<unit>/acceptance.md
检查相似场景
追加新的 AC 场景
输出增量 feature 预览
```

该脚本不会生成 `bindings.yaml`、测试代码或执行命令。

### acceptance_compile.py

```bash
python scripts/acceptance_compile.py --project-root . --unit login --confirmed
```

未带 `--confirmed` 时用于输出 feature + execution_plan_preview，不写入执行资产。

用于在用户确认 feature + execution_plan_preview 后生成：

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

该脚本会根据项目检测结果选择候选本地验收方式，写入建议的真实验收测试文件路径 `runner` 和计划文档 `plan_doc`。它不会编造业务断言、不会生成远程请求、不会修改业务代码。

### acceptance_run.py

```bash
python scripts/acceptance_run.py --project-root . --unit login
```

用于读取 `compiled/bindings.json`，执行已绑定命令，并生成：

```text
reports/<run-id>.yaml
reports/<run-id>.json
reports/latest.yaml
reports/latest.json
```

如果场景缺少命令或状态为 `pending`/`uncertain`，默认不会执行，也不会当作通过。

如果 `runner` 指向的真实验收测试文件还不存在，默认标记为 `pending`，不会执行命令。批量执行时，单个场景失败、报错或超时不会中断后续场景；最终报告会统一统计 `pass/fail/skip/pending/uncertain/error/timeout`。只有整体状态为 `pass` 时返回 0，其他状态返回非 0。
