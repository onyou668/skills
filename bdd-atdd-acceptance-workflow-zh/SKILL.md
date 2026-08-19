---
name: bdd-atdd-acceptance-workflow-zh
description: "以 acceptance.md 验收文件为唯一标准源，维护、确认、生成并执行 BDD/ATDD 验收工作流。Use when 用户需要根据 spec 规范文档、口头新增验收条件或手动编辑的验收文件，增量生成 feature 预览，并在用户确认后结合当前项目真实代码生成 bindings、测试脚本、执行命令和验收报告，支持 Go、Python、Node.js、Java、Rust、HTTP API、CLI、DB、Redis、MQ、文件和异步任务等主流场景。"
---

# BDD/ATDD 验收工作流

## 核心原则

一切以 `acceptance.md` 验收文件为准。

`acceptance.md` 定义业务应该怎样。当前代码只决定应该怎样验证。

不要从当前代码反推业务期望值。代码只能用于发现执行入口、技术栈、测试框架、路由、函数、脚本、数据库表、队列、文件、副作用和断言方式。

不要绕过 `acceptance.md` 直接从 spec、口头描述或当前代码生成测试。

需要生成或更新实际验收资产时，阅读 [references/workflow-details.md](references/workflow-details.md)。

## 必须要求

```text
必须以 acceptance.md 作为唯一验收标准源头。
必须先把 spec、口头新增、手动变更同步到 acceptance.md。
必须校验 acceptance.md 格式，并主动修正可安全修正的格式问题。
必须把缺失业务期望的场景标记为 pending 或 uncertain。
必须在生成验证逻辑前输出本次增量 feature 预览。
必须等待用户明确确认 feature 预览。
必须在用户确认后再读取当前代码生成验证逻辑。
必须根据当前代码实际入口选择验收方式。
必须记录验收方式选择原因。
必须优先复用项目已有测试体系和执行入口。
必须只更新受影响的 unit 和 scenario。
必须只覆盖 generated block，不覆盖人工代码。
必须在执行后生成报告。
必须区分 pass、fail、skip、pending、uncertain。
必须在涉及生产资源、外部付费服务、真实短信邮件、删除数据、新依赖、大范围改动时再次请求用户确认。
```

## 必须禁止

```text
禁止绕过 acceptance.md 直接从 spec 生成测试。
禁止绕过 acceptance.md 直接根据用户口头描述生成测试。
禁止在用户确认 feature 预览前生成测试代码、bindings.yaml 或 BDD step definitions。
禁止在用户确认 feature 预览前执行验收命令。
禁止从当前代码反推业务期望。
禁止因为当前实现如此就认为验收标准正确。
禁止在验收文件缺少错误码、金额、次数、时间窗口等关键信息时编造期望值。
禁止脱离当前项目代码套固定模板。
禁止按语言固定选择验收方式。
禁止默认所有场景都是 HTTP。
禁止默认所有场景都是单元测试。
禁止默认引入新的 BDD/测试框架。
禁止全量重建无关模块的验收资产。
禁止覆盖人工维护的 helper、fixture、测试辅助代码。
禁止把 skip、pending、uncertain 当作通过。
禁止自动操作生产数据库、真实支付、真实短信、真实邮件或不可逆脚本。
```

## 工作流闭环

```text
spec 规范文档 / 用户口头新增 / 手动编辑
        ↓
acceptance.md 验收文件
        ↓
格式校验与必要修正
        ↓
增量 feature 预览
        ↓
等待用户确认
        ↓
读取当前项目真实代码
        ↓
选择最合适的 BDD/ATDD 验收方式
        ↓
生成 bindings / 测试脚本 / 执行命令
        ↓
执行验收
        ↓
生成报告
```

确认前，只能维护验收标准和输出 feature 预览。确认后，才能生成验证逻辑。

## 默认目录

默认在项目根目录使用 `.acceptance/`。用户可以通过 `.acceptance/config.yaml` 修改目录。

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

一个 `unit` 表示一个模块、需求、接口、脚本任务、worker、定时任务或业务流程。

## 配置上下文

`.acceptance/config.yaml` 可以包含可选字段 `context`。

```yaml
version: 1
root: .acceptance

context: |
  可选。这里可以写任意项目验收上下文。
  例如 MySQL/Redis/MQ 连接方式、HTTP base_url、脚本前置命令、mock 规则、CI 限制等。
```

`context` 是项目级自由文本说明，不要求结构化，可以为空。如果存在，必须在生成或执行验收逻辑前优先读取并尽量遵守。`context` 只描述项目执行上下文，不覆盖 `acceptance.md` 中的业务验收标准。

## 验收文件

每个 `acceptance.md` 必须包含元信息和验收场景。每个场景必须包含：

```text
ID
标题
状态
来源
优先级
类型
Given
When
Then
```

推荐可选字段：

```text
标签
Data
Notes
```

状态：

```text
active      当前有效，必须生成和执行
draft       草稿，不生成测试
pending     信息不足，暂不生成可执行测试
uncertain   期望不明确，需要用户确认
deprecated  已废弃，不执行但保留历史
manual      只能人工验收
```

类型默认使用 `auto`。`auto` 表示不要固定生成 HTTP、单元测试或 BDD step，必须读取当前代码后选择最合适的验收方式。

## 同步规则

从 spec 同步验收条件时：

```text
spec 中存在、acceptance.md 不存在 => 追加到 acceptance.md
spec 中修改了已有验收条件 => 标记冲突，等待用户确认
spec 中删除了验收条件 => 不自动删除，只标记 source_missing 或建议 deprecated
用户手动添加的验收条件 => 必须保留
```

用户口头新增验收条件时：

```text
1. 定位对应 unit
2. 读取已有 acceptance.md
3. 检查是否已有相同或相近场景
4. 如果不存在，插入新的 AC 场景
5. 如果已存在，提示用户是更新还是跳过
6. 校验并修正 acceptance.md 格式
7. 输出本次新增或变化的 feature 预览
8. 等待用户确认
```

spec 和口头描述只能先同步到 `acceptance.md`，不能直接生成测试代码。

## Feature 确认关卡

`acceptance.md` 有有效新增、修改、废弃后，必须先输出增量 feature 预览。

只输出本次变化的 Scenario，除非用户要求全量输出。

输出后必须暂停，并询问用户确认：

```text
请确认以上验收场景是否符合你的预期。
确认后我再根据当前代码生成 bindings、BDD/ATDD 脚本和执行命令。
```

用户未确认前，不允许生成验证逻辑。

## 新需求开发流程

新需求分两个阶段。

阶段一：开发前或开发中：

```text
spec / 用户描述 -> acceptance.md -> 增量 feature 预览 -> 等待用户确认验收标准
```

这个阶段只确定要验收什么，不生成最终验证代码。

阶段二：开发完成后：

只有用户明确表示功能或模块开发完成，或要求根据当前代码生成验证逻辑，才进入代码感知生成阶段。进入阶段二后，仍然必须先刷新 feature 预览并等待用户确认。确认后才读取当前代码并生成 bindings、测试代码和执行命令。

## 生成前计划

用户确认 feature 后，生成验证逻辑前，必须输出生成计划。

计划必须包含：

```text
将读取哪些代码入口
将选择哪种验收方式
将生成或更新哪些文件
是否引入新依赖
将执行哪些命令
是否涉及 DB / Redis / MQ / 文件 / 外部服务
```

如果计划涉及新依赖、大范围改动、生产资源、外部真实服务或不可逆操作，必须再次等待用户确认。普通低风险生成可以在输出计划后继续执行。

## 代码感知生成

用户确认 feature 后，必须读取当前项目真实代码。

不要按语言固定选择测试工具。不要默认所有场景都是 HTTP。不要默认所有场景都是单元测试。

验收方式由以下因素决定：

```text
验收场景要验证什么
当前代码实际暴露的入口是什么
项目已有测试框架是什么
哪种方式最接近真实业务路径
哪种方式最稳定、最小侵入、适合 CI
是否需要 DB / Redis / MQ / 文件 / 日志副作用断言
是否需要异步轮询
```

如果项目存在 `.codegraph/`，优先使用 CodeGraph 理解模块、符号、路由和调用链。

## 验收方式选择

```text
有真实 HTTP/API 入口，且验收关注接口行为 => 使用 HTTP/API 验收
验收关注核心函数、规则、计算、边界判断 => 使用单元测试或模块级测试
验收关注完整业务流程、事务或多组件副作用 => 使用集成测试
验收对象是 CLI、脚本、批处理任务 => 使用命令执行验收，并断言 exit code、stdout、stderr 和副作用
验收对象是 worker、消费者、异步任务 => 使用任务触发 + DB/Redis/MQ/日志轮询断言
项目已有 BDD 框架，且场景适合 Given/When/Then 执行 => 可以生成 BDD step binding
项目没有 BDD runner，且引入成本高 => 只生成 feature 作为 BDD 文档，执行层使用项目已有测试方式
```

语言只影响候选工具集合，场景和代码结构决定最终验收方式。候选工具和详细格式见 [references/workflow-details.md](references/workflow-details.md)。

## 增量更新与生成区域

每次运行时，对比 `acceptance.md` 和 `acceptance.lock.yaml`。只更新变化的 scenario，不全量重建无关模块。

自动生成代码必须使用生成标记：

```text
BEGIN ACCEPTANCE GENERATED: AC-LOGIN-001
...
END ACCEPTANCE GENERATED: AC-LOGIN-001
```

只允许覆盖生成区域。不要覆盖人工维护的 helper、fixture、测试辅助方法和项目已有测试逻辑。

## 执行安全与报告

默认只允许 test、local、sandbox 环境。

以下情况必须先询问用户：

```text
生产数据库
删除或覆盖数据
真实支付
真实短信
真实邮件
真实推送
外部收费 API
不可逆脚本
数据库迁移
引入新的测试依赖
大范围修改测试结构
```

报告写入 `.acceptance/units/<unit-id>/reports/`，状态只能是：

```text
pass
fail
skip
pending
uncertain
```

不要把 `skip`、`pending`、`uncertain` 当作通过。

## 最终回复要求

每次完成后，必须告诉用户：

```text
更新了哪个验收单元
验收文件是否被修正
新增或更新了哪些场景
本次增量 feature 预览是什么
用户是否已经确认
生成或更新了哪些资产
选择了什么执行方式，以及为什么
执行了哪些命令
pass / fail / skip / pending / uncertain 数量
还缺少哪些验收信息
```

如果还在等待用户确认，只输出验收文件变化和 feature 预览，不声称已经生成测试或完成验收。

## 最终原则

`acceptance.md` 负责定义验收标准。

`config.context` 负责提供项目自由执行上下文。

增量 `feature` 预览负责让用户确认验收语义。

当前代码负责暴露验证入口。

BDD/ATDD 资产负责表达和执行验收。

用户确认前，只维护验收标准。用户确认后，才生成验证逻辑。
