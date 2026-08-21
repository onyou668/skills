---
name: bdd-atdd-acceptance-workflow-zh
description: "Use when 用户基于开发文档、口述条件或 Feature 维护 ATDD/BDD 验收，开发或修改业务行为后需要生成集成/E2E 验收代码、检查受影响验收、执行增量验收、分析失败或确认修复；也适用于新增边界条件、接口行为、状态流转、权限、DB/Redis/MQ/文件副作用和异步流程。"
---

# BDD/ATDD 验收工作流

## 定位

在 Agent 的 TDD 开发之外增加业务验收层：TDD 验证内部单元，Feature 驱动的集成/E2E 验收证明业务行为、跨模块流程和副作用符合预期。

实现方式可随语言、框架和项目结构变化，但不得降低 Feature 的验证要求。

## 核心模型

```text
开发文档 / 用户口述 / 直接编辑 Feature
             ↓
acceptance.md：自然语言 intake、来源、草稿和待确认问题
             ↓
Feature 变更预览与确认
             ↓
<unit>.feature：唯一正式业务验收标准
             ↓
代码影响、测试风格、入口和依赖发现
             ↓
真实验收测试代码 + acceptance-map.yaml
             ↓
创建 acceptance_id；一次运行创建 RUN-xxx
             ↓
一轮可执行多个受影响 unit / Scenario / Case
             ↓
运行总报告 → 各模块不可变报告 → latest.md 指针
             ↓
失败诊断 → 修复确认 → 同一验收新增运行 → 最终 accepted
```

`acceptance.md` 不是正式标准。Feature 确认后，测试生成、执行和失败判断只以 Feature 为准。代码只用于发现怎样验证，不能反向决定业务期望。

## 模块目录

每个 unit 表示业务模块、接口、业务流程、CLI、worker 或定时任务：

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

测试代码必须放入当前项目真实测试目录，不要藏在 `.acceptance`。不要生成 `compiled/`、`bindings.yaml`、lock、normalized、逐场景 plan Markdown 等重复产物。

## 验收与运行身份

用户每次新发起验收时创建唯一 `acceptance_id`。一次验收可以覆盖多个模块，并包含多次实际运行：

```text
Acceptance  一次完整验收闭环
Run         一次实际执行；同一验收内使用 RUN-001、RUN-002...
Unit        本轮实际选择的业务模块
Scenario    Feature 中的业务行为
Case        Examples 中的具体输入行
```

首次运行、失败诊断、确认修复和后续重跑共享同一 `acceptance_id`，每次执行新增 `run_id`。验收已经 `accepted` 后再次发起验证，或新增独立业务需求时创建新的 `acceptance_id`。

运行报告和模块报告生成后不可覆盖。`latest.md` 只保存最近模块报告、运行报告和验收总报告的相对路径；失败历史使用 `superseded_by` 关联后续运行，不得自动删除。

需要生成或执行资产时，阅读 [references/workflow-details.md](references/workflow-details.md)。

## 输入与同步

支持三种入口：

1. 开发文档、PRD、Issue 或 API 规范：提取验收条件到 `acceptance.md`。
2. 用户口述新增或修改：先写入 `acceptance.md`，再产生 Feature 增量预览。
3. 用户直接编辑 Feature：校验后计算变化 Scenario，不用 `acceptance.md` 覆盖它。

同步规则：

```text
文档新增条件        -> 追加 acceptance 草稿
文档修改已有条件    -> 输出 Feature 差异，等待确认
文档删除条件        -> 不自动删除 Feature，建议 deprecated
口述或手工条件      -> 后续文档同步不得覆盖
代码实现发生变化    -> 检查受影响 Feature，不自动修改业务期望
Feature 直接修改    -> Feature 优先，刷新测试映射
```

缺少错误码、金额、次数、时间窗口、状态值或可观察结果时，标记 `pending` / `uncertain`，不得编造。未确认内容不得进入 active Feature。

## Feature 规则

Feature 只表达业务 WHAT，不写 URL、JSON、SQL、函数名、mock、测试文件或命令。

每个 Scenario 必须有稳定 `@AC-...` 标签或标题中的 AC ID，并包含 Given / When / Then。多组边界优先使用 Scenario Outline，Examples 必须提供稳定 `case_id`。

每个 active Scenario 必须覆盖适用的：

```text
positive / negative / boundary / permission / state-transition
side-effect / forbidden-side-effect / idempotency / concurrency
async / timeout / retry / rollback / external-dependency
```

每条 Then 必须能映射到实际测试断言。BDD 不要求项目安装专用 Runner：已有 Godog、pytest-bdd、Cucumber 等就复用；没有时使用项目现有测试框架生成普通集成/E2E 测试。

## 手动与自动模式

默认 `manual`：

```text
自动识别验收影响
-> 展示 Feature 与生成映射预览
-> 等待用户确认更新
-> 生成测试后再次等待执行确认
```

用户明确要求 `auto` 后，Agent 可以自行确认并增量更新 acceptance、Feature、测试代码和映射。执行验收需要用户同时明确授权执行，或明确说“全自动更新并执行”。

auto 不包含修复授权。已有失败运行时，只有用户确认诊断和修复范围后，才能在同一 `acceptance_id` 下创建下一次 Run。

即使 auto 模式，以下情况也必须退回人工确认：需求不明确、Feature 冲突、影响范围无法确定、新依赖、数据库迁移、生产资源、真实支付/短信/邮件、收费 API、不可逆操作或修复范围扩大。

## 影响分析与增量选择

每次开发变更先从固定基线读取 Git diff，再按以下证据计算：

```text
变更文件和符号
+ 路由与调用链
+ 共享依赖
+ acceptance-map 反向映射
= affected units / scenarios / cases
```

仓库存在 `.codegraph/` 时，先用 CodeGraph 分析符号和调用链。

默认只生成和执行受影响 Case：

```text
Case 映射明确      -> 只选该 Case
只能定位 Scenario  -> 选该 Scenario 的全部 Case
只能定位 unit      -> 选该 unit 的 active Scenario
共享代码变化       -> 选所有被调用链影响的 unit / Scenario
无法确定           -> uncertain，询问用户；禁止退化成全量
```

未受影响内容是 `not_selected`，不是 skip。禁止默认运行 `go test ./...`、裸 `pytest`、`npm test`、`mvn test`、`cargo test` 等全仓命令。只有用户明确要求模块或项目全量验收时才允许扩大范围。

修复后必须重新计算影响范围。旧 pass 对应的 Feature 变化、测试 stale，或其模块因共享代码再次被选中时，该结果变为 stale；不得把不同代码状态下的通过结果直接拼成整体验收通过。

## 项目风格与语言适配

测试生成优先级：

1. 同模块、同验收层级的已有测试。
2. 同模块其他测试。
3. 仓库内同语言、同框架的集成测试。
4. 项目测试配置、依赖和 CI 实际命令。
5. 都不存在时，采用对应语言和框架的主流方式。

记录 `style_evidence`。保持目录、package/namespace、命名、fixture、setup/teardown、断言库、测试容器、异步等待和 selector 风格一致。

保持风格不得降低测试层级。Feature 要求 HTTP、DB、Redis、MQ 或完整流程时，不能退化成只调用纯函数的单元测试。新增测试框架或依赖前必须确认。

语言只影响适配器和代码写法，不影响统一验收协议。尚无可靠适配器时标记 pending，不能生成看似合理但不可执行的代码。

## 真实依赖策略

`.acceptance/config.yaml` 的 `context` 是自由文本，不要求固定字段。Agent 必须按语义解释依赖模式。

```text
context 明确全局 mock            -> 允许全局 mock
context 只允许某依赖 mock         -> 只有该依赖允许 mock
context 未明确授权 mock
+ 项目存在可用 local/test/sandbox 配置 -> 必须真实中间件
真实配置不可用                    -> environment error / pending，禁止降级 mock
```

真实模式必须从真实业务入口执行，使用真实测试 DB、Redis、Kafka/MQ、对象存储等，并验证最终状态、副作用和无副作用。使用 run ID、测试 schema/事务、key prefix、topic/consumer group 隔离并清理数据。

禁止 mock 当前被验收的业务入口或生产逻辑。即使存在凭证，真实支付、短信、邮件、推送和收费第三方仍需单独确认。

## 测试生成与映射

用户确认 Feature 与生成预览后，Agent 必须读取当前代码并生成真实可执行测试代码，不能只生成计划文档。

每个 Scenario / Case 在 `acceptance-map.yaml` 中至少记录：

```text
scenario_id / case_id / test_level
style_evidence
business_entrypoint / validation_entrypoint
dependency_resolution
test_file / test_symbol
exact command / discovery command
Then -> assertion mapping
selected / selection_reason / stale
contract_revision / latest_acceptance_id / latest_run_id / latest_report
```

生成代码使用 Scenario ID 标记，只覆盖明确生成区域；复用并保护人工 helper、fixture 和测试逻辑。

## 执行门禁

执行前必须证明：

1. 测试文件存在。
2. 测试框架通过 scoped discovery 找到精确 symbol / case。
3. 命令只覆盖选中范围。
4. Feature 或测试映射未 stale。
5. mock 使用得到 context 明确授权。
6. 真实依赖可用并完成隔离。
7. 每条 Then 都有断言。
8. acceptance_id、run_id、Feature/map/context 指纹和代码状态已记录。

命令退出 0 但没有发现或执行测试时必须记 pending，不能记 pass。单个 Case 失败或超时不得中断同批其他选中 Case。

只有本轮所有选中 Case 通过时，Run 才是 `incremental_pass`。只有本次验收范围内所有模块对当前 Feature 和影响分析都有有效 pass 时，Acceptance 才是 `accepted`。

## 失败诊断与修复闭环

失败先分类：`business_code`、`acceptance_test`、`environment`、`test_data` 或 `feature_uncertain`。

报告必须给出：Feature 预期、实际证据、路由到异常符号的调用链、真实文件和行号、当前异常代码逻辑、根因与可信度、正确修复逻辑、计划修改文件、影响范围和重跑命令。

报告完成后停在 `awaiting_fix_confirmation`。未经确认不得修改生产代码。

用户确认“修复并继续验收”后，只在报告列出的范围内修复；不得修改 Feature 迎合实现。每轮修复后重新计算影响范围，在同一 `acceptance_id` 下新增 Run 并执行受影响验收，持续到通过。根因变化、范围扩大、新依赖、迁移或危险操作必须重新确认。

## 安全边界

验收生成阶段只能修改 Feature、模块映射、报告和项目测试代码，禁止修改生产代码。修复阶段必须有单独确认。

默认仅允许 local/test/sandbox。不得自动连接生产数据库、执行不可逆脚本或调用真实付费服务。

## 脚本

```text
acceptance_detect.py   项目语言、测试风格、路由和中间件配置证据
acceptance_sync.py     文档/口述条件进入 acceptance.md intake
acceptance_compile.py  Feature 与生成预览；确认后写正式 Feature 和模块映射
acceptance_feature.py  校验直接编辑的 Feature 并刷新受影响映射
acceptance_map.py      登记真实测试路径、symbol、selector 和增量选择
acceptance_run.py      一次运行多个 unit，维护 Acceptance/Run/模块报告和 latest 指针
```

优先运行脚本完成确定性操作；测试代码仍由 Agent 根据当前项目真实代码与风格生成。

## 完成标准

一个场景只有在以下条件全部满足时才算接受：Feature 已确认、所有边界 Case 已映射、测试真实存在且可发现、依赖策略合规、所有 Then 有断言、受影响 Case 全部通过且报告有可复核证据。

整次验收只有在验收范围内每个模块的最新有效结果都对应当前 Feature、当前 map 和最终影响分析，并且不存在 fail、pending、uncertain、error、timeout 或 stale 时，才能标记 `accepted`。

最终回复必须明确：acceptance_id、run_id、更新的 unit 和 Feature、受影响与未选择范围、各级报告路径、生成的测试文件/符号、真实依赖模式、执行命令、结果证据、失败诊断、是否等待修复确认，以及本轮是 incremental_pass 还是整次验收 accepted。
