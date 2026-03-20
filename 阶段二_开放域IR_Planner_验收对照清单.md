# 阶段二：开放域 IR + Planner 验收对照清单

## 1. 结论

- 当前系统可判断为：**基本达到“阶段二：开放域 IR + Planner”验收标准**。
- 更准确地说，当前能力属于：**已支持 family 范围内的开放域 IR + Planner**，而不是“任意开放域、任意新 family”的完全开放域系统。
- 按路线图中的 3 条验收项逐项核对，结果为：**2 条已达成，1 条已达成但带明确边界**。

## 2. 验收项对照表

| 验收项 | 路线图标准 | 当前状态 | 代码 / 验证证据 | 结论 |
| --- | --- | --- | --- | --- |
| 未命中既有 `model_id` 的问题，系统仍可生成结构化 IR | 即使未直接命中既有模板模型，也能先产出结构化 `OpenModelIR`，而不是只能退回闭集 `model_id` 模式 | **已达成（有边界）** | `agents/structured_generation_ir.py:84` 的 `begin_collection` 先按 `family` 进入结构化收集；`agents/structured_generation_ir.py:195` 的 `_build_ir` 会构建完整 IR，即使 `model_id` 可为空；`agents/open_model_ir_validator.py:58` 对 `model_generation` 的硬要求是 `family`，不是既有 `model_id`；本地最小验证中，手工构造 `top_family=launch_dynamics`、`top_candidate={}` 时，IR 成功生成，且 `model_id=''` | **通过** |
| 对中等复杂度问题，可输出合理的实体 / 状态 / 方程骨架 | IR 中应包含可继续规划的实体、状态变量、方程骨架、片段信息，而不只是参数表 | **已达成** | `agents/structured_generation_ir.py:227` 生成 `domain`；`agents/structured_generation_ir.py:228` 生成 `entities`；`agents/structured_generation_ir.py:229` 生成 `physics`；`agents/structured_generation_ir.py:404` 会写入 `state_variables`、`equation_fragments`、`state_equations`；`agents/structured_generation_ir.py:437` 生成 `codegen` 骨架；本地最小验证中，`launch_dynamics` 可输出实体、状态变量 `['h','v','a','m']` 与状态方程骨架 | **通过** |
| 可复用 family 的问题继续走现有稳定链路 | 对已能归入既有 `family` 的问题，系统应复用现有稳定 family 渲染链路，而不是另起不稳定旁路 | **已达成** | `agents/open_model_ir_compat.py:37` 将开放域 IR 转成兼容 `ModelSpec`；`agents/open_model_ir_compat.py:108` 会把开放域请求映射到 family 默认兼容 `model_id`；`knowledge_base/model_planner.py:57` 进入 `ModelPlanner.plan_from_ir`；`knowledge_base/assembly_plan.py:41` 定义 `AssemblyPlan`；`agents/matlab_codegen.py:64` 对带 `_generation_ir` 的 spec 走 family renderer；本地最小验证中，在补齐槽位后，`to_assembly_plan` 成功返回 `template_family=launch_dynamics`、`model_id=rocket_launch_1d` | **通过** |

## 3. 已达成点清单

| 已达成点 | 说明 | 证据 |
| --- | --- | --- |
| `OpenModelIR` 已落为代码级 schema | 已有显式结构化 IR，而非只在文档层面描述 | `agents/open_model_ir_schema.py:186` |
| `OpenModelIRBuilder` 已落地 | 可将 payload 规范化为 `OpenModelIR` | `agents/open_model_ir_builder.py:10` |
| `OpenModelIRValidator` 已落地 | 可校验 family、一致性、片段合法性等 | `agents/open_model_ir_validator.py:13` |
| `ModelPlanner` 已落地 | 已可从 IR 生成 `AssemblyPlan` | `knowledge_base/model_planner.py:19` |
| `AssemblyPlan` 中间层已落地 | 已有独立的 IR -> block assembly 规划结构 | `knowledge_base/assembly_plan.py:41` |
| `OpenModelIR -> ModelSpec` 兼容链路已落地 | 已能接回现有稳定 codegen 主链路 | `agents/open_model_ir_compat.py:37` |
| `OpenModelIR -> AssemblyPlan -> MATLAB` 直通链路已落地 | 已可直接走 planner 与 family renderer | `agents/open_model_ir_compat.py:96`、`knowledge_base/model_family_codegen.py:595` |
| family 级 schema + slot extractor + clarify policy 已落地 | 已不是单纯“按单模型配置”收集参数 | `agents/structured_generation_ir.py:1`、`agents/structured_generation/schema_registry.py:1` |

## 4. 未完全达成点 / 边界清单

| 未完全达成点 | 当前情况 | 影响 | 证据 |
| --- | --- | --- | --- |
| 仍不是“任意开放域” | 只有命中受支持 `family` 时，才会进入开放域 IR 主链路 | 当前更准确表述应为“family 范围内开放域” | `agents/structured_generation_ir.py:519`、`knowledge_base/model_planner.py:50` |
| 上游匹配仍可能在低置信度场景拦截 | `no_candidate`、`low_confidence`、`ambiguous_family` 等会阻止进入 IR 构建 | 对“完全未命中且无稳定 family”的问题，系统仍会先澄清或拒绝 | `knowledge_base/rag_retriever.py:1785` |
| 旧 `ModelSpecValidator` 仍是闭集校验器 | 未知 `model_id` 会被直接判错 | 真正开放的是 `OpenModelIR + compat` 链路，不是旧 `ModelSpec` 链路本身 | `agents/model_spec_validator.py:153` |
| 独立 JSON Schema 文件未见落盘 | 代码中有 `OPEN_MODEL_IR_JSON_SCHEMA`，但仓库中未看到 `schemas/open_model_ir.schema.json` 文件 | 阶段二核心能力已在代码中可用，但与路线图“单独 schema 文件交付”仍有差距 | `agents/open_model_ir_schema.py:253` |
| 草案 fragment 目前主要以 `comment_only` 占位 | planner 支持 draft fragment，但默认以注释占位保留 | 能表达开放域草案，但未必都能原生渲染为 MATLAB 逻辑块 | `knowledge_base/model_planner.py:44`、`knowledge_base/model_planner.py:215` |
| 不完整 IR 不能直接下游规划 | 若 `missing_info` 未补齐，planner 会返回 incomplete error | 说明系统仍依赖“先澄清、再规划”的收集闭环 | `knowledge_base/model_planner.py:67` |

## 5. 对阶段二状态的最终判断

| 判断项 | 结论 |
| --- | --- |
| 是否已进入“开放域 IR + Planner”阶段 | **是** |
| 是否已满足路线图阶段二三条验收项 | **是，但第 1 条应标注为“有边界地达成”** |
| 是否已达到“任意开放域、任意新模型族” | **否** |
| 当前最准确阶段表述 | **已进入可用的 family 范围开放域 IR + Planner 阶段** |

## 6. 本次判断依据

- 依据路线图中的阶段二定义与验收项：`开放域升级实施路线图.md:50`
- 依据主链路入口与 IR 构建逻辑：`agents/crm_agent.py:321`、`agents/structured_generation_ir.py:84`
- 依据开放域 IR schema / builder / validator：`agents/open_model_ir_schema.py:186`、`agents/open_model_ir_builder.py:10`、`agents/open_model_ir_validator.py:13`
- 依据 planner / assembly / renderer：`knowledge_base/model_planner.py:19`、`knowledge_base/assembly_plan.py:41`、`knowledge_base/model_family_codegen.py:595`
- 依据兼容回落链路：`agents/open_model_ir_compat.py:37`
- 依据本地最小验证：
  - 在 `model_id` 为空、但 `top_family=launch_dynamics` 的条件下，成功生成结构化 IR
  - 在补齐关键槽位后，成功生成 `AssemblyPlan`
  - 兼容 `model_id` 被自动映射为 family 默认模型 `rocket_launch_1d`

