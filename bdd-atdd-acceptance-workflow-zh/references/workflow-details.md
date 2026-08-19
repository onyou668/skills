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

```gherkin
Feature: 登录模块验收

  Scenario: AC-LOGIN-001 验证码必须为 6 位数字
    Given 用户正在进行登录验证
    When 用户提交非 6 位验证码
    Then 登录必须失败
    And 系统必须返回验证码长度错误
```

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
curl 包装脚本
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
    selected_type: http_api
    reason: 当前登录模块暴露 POST /api/login，验证码校验发生在真实登录入口，HTTP 验收最接近业务路径
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

## 报告示例

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
    reason: 验收文件没有说明账号锁定持续时间
```

## 可选脚本

后续版本可以包含：

```text
scripts/acceptance_detect.py
scripts/acceptance_sync.py
scripts/acceptance_compile.py
scripts/acceptance_run.py
```

脚本只能执行确定性操作，不能凭空创造业务期望。如果脚本尚未存在，不要假装已经运行脚本。
