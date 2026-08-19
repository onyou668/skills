---
name: bdd-atdd-acceptance-workflow-zh
description: "Use when 用户需要维护 BDD/ATDD 验收规则、根据 acceptance.md/spec/口头条件生成或刷新 feature、execution_plan_preview、验收脚本、本地执行命令或验收报告；适用于本地代码验收、HTTP、CLI、脚本、DB、Redis、MQ、文件、异步任务和主流语言项目。"
---

# BDD/ATDD 验收工作流

## 核心原则

一切以 `acceptance.md` 验收文件为准。

`acceptance.md` 定义业务应该怎样。当前代码只决定应该怎样验证。

不要从当前代码反推业务期望值。代码只能用于发现执行入口、技术栈、测试框架、路由、函数、脚本、数据库表、队列、文件、副作用和断言方式。

不要绕过 `acceptance.md` 直接从 spec、口头描述或当前代码生成测试。

本 Skill 默认验证当前仓库、当前分支、当前代码的本地行为。业务入口可以是 HTTP API、脚本、CLI、worker、MQ、定时任务或外部 HTTP 调用逻辑，但验收执行入口必须是当前仓库内可本地调用的代码入口。

核心目标：基于已有代码逻辑和 `acceptance.md` 验收规则，生成结构化本地验收执行计划。`execution_plan_preview` 必须用 `input / execute / assert` 描述怎样生成验收代码。

需要生成或更新实际验收资产时，阅读 [references/workflow-details.md](references/workflow-details.md)。

优先复用内置脚本执行确定性步骤：

```text
scripts/acceptance_detect.py
scripts/acceptance_sync.py
scripts/acceptance_compile.py
scripts/acceptance_run.py
```

## 必须要求

```text
必须以 acceptance.md 作为唯一验收标准源头。
必须先把 spec、口头新增、手动变更同步到 acceptance.md。
必须校验 acceptance.md 格式，并主动修正可安全修正的格式问题。
必须把缺失业务期望的场景标记为 pending 或 uncertain。
必须在生成验证逻辑前输出本次增量 feature 预览。
必须在确认前只读扫描当前相关代码，用于识别业务入口、本地验收入口、输入输出结构和已有测试风格。
必须输出标准 Gherkin feature 预览和结构化 execution_plan_preview。
必须等待用户明确确认 feature 预览和 execution_plan_preview。
必须在用户确认后只生成验收相关资产，不修改生产业务代码。
必须在生成验收资产后询问用户是否继续执行验收。
必须等待用户明确确认执行后再运行验收命令。
必须根据当前代码实际本地入口选择验收方式。
必须记录验收方式选择原因。
必须优先复用项目已有测试体系和执行入口。
必须只更新受影响的 unit 和 scenario。
必须只覆盖 generated block，不覆盖人工代码。
必须批量执行验收，单个 scenario 失败、报错或超时不得中断整批验收。
必须在执行后生成报告，并给出未通过原因、证据和建议修改位置。
必须区分 pass、fail、skip、pending、uncertain、error、timeout。
必须在初始化 .acceptance/config.yaml 时保持 context 为空，除非用户明确提供项目验收执行上下文。
必须在涉及生产资源、外部付费服务、真实短信邮件、删除数据、新依赖、大范围改动时再次请求用户确认。
```

## 必须禁止

```text
禁止绕过 acceptance.md 直接从 spec 生成测试。
禁止绕过 acceptance.md 直接根据用户口头描述生成测试。
禁止在用户确认 feature 预览和 execution_plan_preview 前生成测试代码、bindings.yaml 或 BDD step definitions。
禁止在用户确认执行前执行验收命令。
禁止从当前代码反推业务期望。
禁止因为当前实现如此就认为验收标准正确。
禁止在验收文件缺少错误码、金额、次数、时间窗口等关键信息时编造期望值。
禁止脱离当前项目代码套固定模板。
禁止按语言固定选择验收方式。
禁止默认所有场景都是 HTTP。
禁止默认所有场景都是单元测试。
禁止把 HTTP 业务入口误判为远程 HTTP 验收。
禁止默认请求远程 HTTP 服务。
禁止默认连接远程数据库、Redis、MQ、对象存储或外部 API。
禁止默认调用真实第三方服务、真实短信、真实邮件、真实支付。
禁止凭空创造当前仓库不存在的脚本、runner、service、helper、CLI 参数或测试入口。
禁止为了让验收通过而修改 handler、service、model、repository、配置加载、业务规则等生产代码。
禁止默认引入新的 BDD/测试框架。
禁止全量重建无关模块的验收资产。
禁止覆盖人工维护的 helper、fixture、测试辅助代码。
禁止把 skip、pending、uncertain、error、timeout 当作通过。
禁止把 AGENTS.md 里的全局规则、Skill 安全规则、CodeGraph 可用性、AI 推断结果或默认提示写入 config.context。
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
只读扫描当前相关代码
        ↓
识别 business_entrypoint 与本地 validation_entrypoint
        ↓
生成标准 Gherkin 增量 feature 预览
        ↓
生成结构化 execution_plan_preview(input / execute / assert)
        ↓
等待用户确认 feature + execution_plan_preview
        ↓
只生成验收资产：bindings / 测试脚本 / compiled / plan
        ↓
询问用户是否执行验收
        ↓
用户确认后批量执行验收
        ↓
不中断收集所有结果
        ↓
生成报告、未通过原因、证据和修改建议
```

第一次确认前，允许只读代码发现，禁止生成执行层。第一次确认后，只能生成验收资产，禁止修改业务代码。第二次确认后，才执行验收命令。

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
        execution_plan.preview.yaml
        execution_plan.preview.json
        bindings.json
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
```

`context` 是项目级自由文本说明，不要求结构化，可以为空。

初始化 `.acceptance/config.yaml` 时，`context` 必须保持为空，除非用户明确提供项目验收执行上下文。

不要把 `AGENTS.md` 中已有的全局规则、Skill 安全规则、CodeGraph 可用性、AI 推断结果或默认提示写入 `context`。

如果用户填写了 `context`，必须在生成或执行验收逻辑前优先读取并尽量遵守。`context` 只描述项目执行上下文，不覆盖 `acceptance.md` 中的业务验收标准。

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

`acceptance.md` 有有效新增、修改、废弃后，必须先输出增量 feature 预览和 execution_plan_preview。

feature 预览必须使用标准 Gherkin 语法：

```text
必须包含 Feature:
必须使用 Scenario: 或 Scenario Outline:
必须使用 Given / When / Then / And / But
Scenario Outline 使用 <变量> 时必须提供 Examples:
Examples 表头必须覆盖所有 <变量>
多行文本必须使用 Doc String
表格必须使用 Gherkin Data Table
默认使用英文 Gherkin 关键字，步骤文本可以是中文
禁止在 feature 中混入 YAML、JSON、Markdown 标题、bindings、测试函数名或执行计划
```

feature 只表达业务验收语义和用户可理解的业务触发方式。详细 JSON 参数、响应结构、DB/Redis/MQ/文件断言、测试函数名和命令预览必须放入 `execution_plan_preview`。

只输出本次变化的 Scenario，除非用户要求全量输出。

`execution_plan_preview` 必须是结构化 YAML 或 JSON，并且每个 case 必须包含：

```text
input    请求 JSON、命令参数、fixture、环境变量、消息体或脚本输入
execute  本地执行方式、当前仓库代码入口、mock/fake/fixture、超时和命令预览
assert   响应、输出、副作用、无副作用、错误码、状态变化、DB/Redis/MQ/文件校验
```

执行计划必须包含 `code_evidence`，说明业务入口、参数、响应、测试 helper、脚本或 runner 是从当前代码哪里发现的。

执行计划必须覆盖正反用例。除非 `acceptance.md` 明确只验一个方向，否则必须列出 positive、negative、boundary 和 side-effect 用例；缺失或不确定的用例必须标记为 `uncertain`。

输出后必须暂停，并询问用户确认：

```text
请确认以上 Feature 和 Execution Plan Preview 是否符合你的验收预期。
确认后我只生成验收代码、bindings 和 compiled assets，不修改业务代码。
生成完成后我会再询问是否执行验收。
```

用户未确认前，不允许生成验证逻辑。

## 新需求开发流程

新需求分两个阶段。

阶段一：开发前或开发中：

```text
spec / 用户描述 -> acceptance.md -> 必要的只读代码发现 -> 增量 feature 预览 -> execution_plan_preview -> 等待用户确认
```

这个阶段只确定要验收什么和后续怎样本地验收，不生成最终验证代码。

阶段二：开发完成后：

只有用户明确表示功能或模块开发完成，或要求根据当前代码生成验证逻辑，才进入验收资产生成阶段。进入阶段二后，仍然必须先刷新只读代码发现、feature 预览和 execution_plan_preview，并等待用户确认。确认后只生成 bindings、测试代码和执行命令；生成完成后再次询问是否执行验收。

## 执行计划预览

生成验证逻辑前，必须输出 execution_plan_preview。它是后续生成验收代码的直接输入，不是随意说明。

计划必须包含：

```text
code_evidence：当前代码证据
business_entrypoint：用户视角入口
validation_entrypoint：当前仓库本地代码入口
case_coverage：positive / negative / boundary / side-effect 覆盖
cases[].input：JSON、参数、fixture、env、消息体
cases[].execute：本地调用方式、mock/fake、命令预览、超时
cases[].assert：响应、输出、副作用和无副作用断言
generated_assets_preview：确认后将生成或更新哪些验收资产
command_preview：确认生成后建议执行的本地命令
execution_policy：禁止修改业务代码、二次确认后执行、批量不中断
```

如果计划涉及新依赖、大范围测试结构改动、生产资源、外部真实服务或不可逆操作，必须再次等待用户确认。普通低风险验收资产生成可以在用户确认 feature 和 execution_plan_preview 后继续执行。

## 脚本入口

使用 `scripts/acceptance_detect.py` 识别项目语言、子模块、测试框架、BDD 工具、本地测试风格、配置上下文、可能的 HTTP 路由和本地脚本入口。

使用 `scripts/acceptance_sync.py` 初始化验收目录、从 spec 或口头条件维护 `acceptance.md`，并输出增量 feature 预览。该脚本不生成验证逻辑。

未确认时，使用 `scripts/acceptance_compile.py` 输出标准 Gherkin feature 预览和结构化 execution_plan_preview，但不写入执行资产。

用户确认 feature 和 execution_plan_preview 后，使用 `scripts/acceptance_compile.py --confirmed` 生成 `feature.feature`、`bindings.yaml`、`compiled/*`、`acceptance.lock.yaml` 和安全的生成计划脚手架。

生成完成后必须询问用户是否执行。用户确认执行后，使用 `scripts/acceptance_run.py` 根据 `compiled/bindings.json` 批量执行已绑定命令并写入报告。没有明确命令或状态为 `pending`/`uncertain` 的场景不得当作通过。

## 代码感知生成

生成 feature 和 execution_plan_preview 前，必须只读扫描当前项目真实代码。用户确认后，可以继续读取代码细节用于生成验收资产，但仍禁止修改业务代码。

不要按语言固定选择测试工具。不要默认所有场景都是 HTTP。不要默认所有场景都是单元测试。

验收方式由以下因素决定：

```text
验收场景要验证什么
当前代码实际暴露的业务入口是什么
当前仓库可本地调用的 validation_entrypoint 是什么
输入结构是什么：JSON、DTO、CLI 参数、env、fixture、消息体
输出结构是什么：HTTP status、业务 code、JSON data、stdout/stderr、DB/Redis/MQ/文件副作用
项目已有测试框架是什么
项目已有测试 helper、fake、mock、fixture 风格是什么
哪种方式最接近真实业务路径
哪种方式最稳定、最小侵入、适合 CI
是否需要 DB / Redis / MQ / 文件 / 日志副作用断言
是否需要异步轮询
```

验收功能入口只能是本地代码入口。如果无法找到当前仓库内可本地调用的入口，必须标记 `pending`，说明缺少什么入口，不能改用远程环境凑验收。

如果项目存在 `.codegraph/`，优先使用 CodeGraph 理解模块、符号、路由和调用链。

## 验收方式选择

```text
HTTP/API 业务入口，且验收目标是当前代码本地逻辑 => 优先使用本地 handler/router/test client，例如 Go httptest、Python test client、Node supertest、Java MockMvc、Rust 本地 router
验收关注核心函数、规则、计算、边界判断 => 使用本地单元测试或模块级测试
验收关注完整业务流程、事务或多组件副作用 => 使用本地集成测试、sqlmock、临时 DB、fake Redis/MQ 或 test container
验收对象是 CLI、脚本、批处理任务 => 使用当前仓库已存在脚本或 runner，在本地 test/sandbox fixture 中执行，并断言 exit code、stdout、stderr 和副作用
验收对象是 worker、消费者、异步任务 => 触发当前仓库本地 worker/consumer/job 入口，并用 DB/Redis/MQ/日志/文件轮询断言
验收对象是外部 HTTP 请求逻辑 => 使用本地 fake server、mock transport 或 recorded fixture，断言 method/path/header/body/query 和响应处理，禁止默认请求真实第三方
项目已有 BDD 框架，且场景适合 Given/When/Then 执行 => 可以生成 BDD step binding
项目没有 BDD runner，且引入成本高 => 只生成 feature 作为 BDD 文档，执行层使用项目已有测试方式
```

语言只影响候选工具集合，场景和代码结构决定最终验收方式。候选工具和详细格式见 [references/workflow-details.md](references/workflow-details.md)。

业务入口不等于验收执行方式。`POST /api/auth/login` 是业务入口；Go 项目中的本地验收入口可以是 `AuthHandler.Login`、Gin router、service 或邮箱校验函数。

## 增量更新与生成区域

每次运行时，对比 `acceptance.md` 和 `acceptance.lock.yaml`。只更新变化的 scenario，不全量重建无关模块。

验收生成阶段只能新增或更新验收相关资产。验收相关资产包括 `.acceptance/*`、`feature.feature`、`bindings.yaml`、`compiled/*`、`generated/*`、`fixtures/*`、`reports/*`，以及项目测试目录中的 acceptance 测试文件。

禁止在验收生成阶段修改生产业务代码，包括 handler、service、model、repository、配置加载、业务规则、迁移和真实外部服务代码。验收失败后只能输出原因、证据和建议；用户明确发起修复任务后，才能进入独立业务代码修改。

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
error
timeout
```

不要把 `skip`、`pending`、`uncertain`、`error`、`timeout` 当作通过。

批量执行时，单个 scenario 失败、报错、panic、命令非零退出或超时，都必须记录该 scenario 状态并继续执行后续 scenario。全部执行结束后统一输出报告。

验收执行命令只有整体状态为 `pass` 时才能返回 0。存在 `fail`、`pending`、`uncertain`、`skip`、`error` 或 `timeout` 时，必须返回非 0，避免 CI 或用户误判为通过。

报告必须包含：

```text
总览：pass / fail / skip / pending / uncertain / error / timeout 数量
逐场景结果：scenario ID、标题、验收方式、执行命令、状态
失败证据：HTTP status、业务 code、响应 body、stdout/stderr、DB/Redis/MQ/文件断言结果
未通过原因：实际结果和 acceptance.md / feature / execution_plan_preview 期望的差异
建议修改：建议修改哪类业务代码或配置，为什么
风险提示：是否可能是验收脚本问题、环境问题、数据问题或业务实现缺失
```

## 最终回复要求

每次完成后，必须告诉用户：

```text
更新了哪个验收单元
验收文件是否被修正
新增或更新了哪些场景
本次增量 feature 预览是什么
execution_plan_preview 是什么
用户是否已经确认 feature + execution_plan_preview
生成或更新了哪些资产
选择了什么执行方式，以及为什么
是否已经二次确认执行
执行了哪些命令；若未执行，说明正在等待执行确认
pass / fail / skip / pending / uncertain / error / timeout 数量
未通过原因、证据和建议修改位置
还缺少哪些验收信息
```

如果还在等待第一次确认，只输出验收文件变化、feature 预览和 execution_plan_preview，不声称已经生成测试或完成验收。

如果验收资产已经生成但等待执行确认，只报告生成结果和命令预览，不声称验收通过。

## 最终原则

`acceptance.md` 负责定义验收标准。

`config.context` 负责提供项目自由执行上下文。

增量 `feature` 预览负责让用户确认验收语义。

当前代码负责提供本地业务入口、validation_entrypoint 和代码证据。

`execution_plan_preview` 负责把验收标准和当前代码映射成 input / execute / assert。

BDD/ATDD 资产负责表达和执行验收。

第一次确认前，只读代码发现并预览 feature + execution_plan_preview。第一次确认后，只生成验收资产。第二次确认后，才执行验收。验收失败后只报告差异和建议，不修改业务代码。
