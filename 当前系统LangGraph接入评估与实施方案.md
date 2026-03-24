# 当前系统 LangGraph 接入评估与实施方案

## 1. 结论

结论先行：**当前系统可以接入 LangGraph，而且接入收益主要集中在“编排层、状态恢复、可观测性和人工澄清中断恢复”，不是为了替换现有 MATLAB 生成能力本身。**

按当前仓库状态判断：

- **可以接入**：现有系统已经具备明显的多阶段工作流结构，适合映射为 `StateGraph`。
- **不建议一次性重写**：现有检索、IR、规格构建、校验、代码生成、DLL 构建能力已经成型，应该复用，避免把“框架迁移”做成“业务重写”。
- **最适合的改造范围**：把 `CRMAgent` 里的“流程控制”和“挂起/恢复逻辑”迁移到 LangGraph，把各业务模块保留为节点内部能力。

一句话建议：**建议接入 LangGraph，但采用“兼容旧入口 + 渐进迁移编排层”的方式推进。**

---

## 2. 当前系统现状与判断依据

### 2.1 当前系统还没有真正接入 LangGraph

从仓库和运行环境看，当前状态是：

- `environment.yml` 已安装 `langchain / langchain-core / langchain-community`，但**没有 `langgraph`**。
- 实际代码中没有发现 `langgraph` 的导入和图编排逻辑。
- 本地环境检测结果为：
  - `langgraph = False`
  - `langchain = True`

这说明当前系统不是 LangGraph 架构，而是**手写编排 + FastAPI + SessionStore + RAG + 本地工具链**架构。

### 2.2 当前主链路已经天然具备“图工作流”特征

当前主入口与核心链路如下：

- `api/server.py`
  - 通过 FastAPI 提供 `/api/chat` 与 `/api/query`
  - 在启动时创建全局 `CRMAgent`
- `agents/crm_agent.py`
  - 集中承担任务规划、检索、澄清挂起/恢复、规格构建、校验、生成、DLL 后处理、普通聊天回复
- `agents/session_store.py`
  - 承担历史消息和中间状态持久化
- `knowledge_base/rag_retriever.py`
  - 承担主知识库检索与建模匹配评估
- `knowledge_base/web_evidence_retriever.py`
  - 承担联网证据回收与补充
- `agents/task_planner.py`
  - 承担 chat / generation / clarify 等任务路由判断
- `agents/structured_generation_ir.py`
  - 承担结构化澄清、补槽、续接 IR
- `agents/model_spec_builder.py`
  - 承担 ModelSpec 构建
- `agents/model_spec_validator.py`
  - 承担规格校验与修复循环
- `agents/matlab_codegen.py`
  - 承担 MATLAB 文件生成
- `agents/tools.py`
  - 承担联网研究、动态库构建等工具封装

这些组件本身已经是“节点化”的，只是现在被集中塞在 `CRMAgent.chat()` 这个大方法里串起来。

### 2.3 当前已经存在显式的“挂起/恢复”需求

当前会话层已经手工维护了三类关键状态：

- `pending_generation_match`
- `pending_generation_ir`
- `last_generation_result`

这意味着系统已经不是单轮对话，而是一个带有：

- 分支
- 中断
- 恢复
- 多轮澄清
- 后续动作跟进

的状态机式工作流。

这类模式与 LangGraph 的以下能力天然匹配：

- `StateGraph`
- `checkpointer`
- `interrupt / resume`
- `thread_id` 驱动的可恢复执行

### 2.4 当前代码结构适合“只迁移编排层”

现有业务模块边界已经比较清楚：

- 检索是独立模块
- IR 构建是独立模块
- Spec 构建/校验是独立模块
- Codegen 是独立模块
- DLL 构建是独立工具链

因此，LangGraph 接入不需要从头重写业务逻辑，完全可以通过“节点包装”的方式接入。

---

## 3. 为什么当前系统适合接入 LangGraph

### 3.1 `CRMAgent.chat()` 已经是图，只是尚未显式化

当前 `chat()` 的实际流程大致是：

```text
接收请求
-> 读取会话状态
-> 判断是否为历史挂起恢复
-> 检索知识
-> 任务规划
-> 判断 chat / generation / clarify
-> generation match 评估
-> object/family/slot 澄清
-> spec 构建
-> spec 校验/修复
-> codegen
-> 可选 DLL 构建
-> 返回响应并持久化结果
```

这已经是标准的有向图工作流，只是目前用 `if/elif` 和会话状态 key 在手工维护。

### 3.2 LangGraph 正好解决当前系统最痛的几个点

如果系统继续往生产化走，当前最值得引入 LangGraph 的点主要有四类：

1. **澄清中断与恢复更标准**
   - 现在是手工维护 `pending_generation_*`
   - 迁移后可收敛为 `interrupt()` + `Command(resume=...)`

2. **状态持久化更统一**
   - 现在历史与中间状态分散在 `SessionStore`
   - 迁移后可逐步把流程状态统一进 graph state + checkpointer

3. **可观测性更强**
   - 现在 trace 主要靠业务层日志和手工字段
   - 迁移后可直接围绕 graph node、edge、checkpoint 做调试与回放

4. **复杂分支更容易继续演进**
   - 当前已有聊天、生成、联网研究、动态库构建、澄清恢复等多条分支
   - 后续再加人工审批、异步任务、流式返回时，图式编排比继续堆 `if/elif` 更稳

---

## 4. 接入 LangGraph 前后的职责边界

### 4.1 应该迁移到 LangGraph 的内容

建议迁移到 LangGraph 的是**流程层**：

- 请求进入后的节点调度
- 条件路由
- 澄清中断与恢复
- 校验失败后的修复循环
- 生成成功后的后续分支
- 运行状态持久化

### 4.2 不应该重写的内容

以下模块建议尽量原样复用：

- `knowledge_base/rag_retriever.py`
- `knowledge_base/web_evidence_retriever.py`
- `agents/task_planner.py`
- `agents/structured_generation_ir.py`
- `agents/model_spec_builder.py`
- `agents/model_spec_validator.py`
- `agents/matlab_codegen.py`
- `agents/tools.py`

原因很简单：

- 这些模块解决的是业务问题
- LangGraph 解决的是编排问题

不要把“接入图框架”误做成“重写业务逻辑”。

---

## 5. 需要做的改动清单

## 5.1 依赖与环境改动

最小必需改动：

- 在依赖中新增 `langgraph`

建议的持久化策略：

- **PoC / 本地开发**：优先用 SQLite checkpointer
- **现有部署兼容阶段**：继续保留 `SessionStore`，LangGraph 只接流程状态
- **生产阶段**：可选 Redis 或 Postgres checkpointer

建议同步修改：

- `environment.yml`
- `requirements.txt`

同时建议补齐一组配置项，例如：

- `LANGGRAPH_ENABLED=false`
- `LANGGRAPH_CHECKPOINTER=sqlite`
- `LANGGRAPH_SQLITE_PATH=.langgraph/checkpoints.db`
- `LANGGRAPH_THREAD_ID_SOURCE=session_id`
- `LANGGRAPH_STREAMING_ENABLED=false`

### 5.2 新增工作流目录

建议新增目录：

```text
agents/workflows/
  __init__.py
  state.py
  nodes.py
  routes.py
  checkpointer.py
  graph.py
  service.py
```

建议职责如下：

- `state.py`
  - 定义 graph state schema
- `nodes.py`
  - 把现有业务模块包装为 graph node
- `routes.py`
  - 定义条件边与分支函数
- `checkpointer.py`
  - 统一管理 checkpointer 初始化
- `graph.py`
  - 构建并编译 `StateGraph`
- `service.py`
  - 提供给 `CRMAgent` / API 层调用的统一入口

### 5.3 `CRMAgent` 的改动

建议把 `agents/crm_agent.py` 从“总编排器”改成“兼容 facade”。

改造后它只保留三类职责：

- 把 HTTP 入参转成 graph input
- 调用 graph 服务并拿回结果
- 对外维持当前接口兼容，避免 API 一次性大改

建议削薄的内容：

- 主流程 `if/elif` 调度
- `pending_generation_*` 手工恢复逻辑
- 复杂的分支拼接逻辑

建议保留的内容：

- 兼容旧方法签名
- 少量响应格式整理
- 兼容期内的回退开关

### 5.4 `SessionStore` 的改动

当前不建议第一阶段就废掉 `SessionStore`。

建议分两阶段：

#### 阶段 A：兼容保留

- `SessionStore` 继续保存聊天历史
- LangGraph checkpointer 保存 graph execution state
- `thread_id = session_id`

#### 阶段 B：逐步收敛

- 把 `pending_generation_match` / `pending_generation_ir` 合并进 graph state
- `last_generation_result` 可逐步迁移到 graph state 或结果存储层
- `SessionStore` 最终只保留聊天历史，或者也进一步合并

### 5.5 API 层改动

`api/server.py` 建议最小改造，不建议直接推翻当前 FastAPI API。

建议变更：

- `/api/chat` 仍保留
- `/api/query` 仍保留
- 内部实现从 `CRMAgent.chat()` 逐步切换为 `workflow_service.invoke()`
- `session_id` 直接映射为 LangGraph `thread_id`

如果后续接流式输出，可再新增：

- `/api/chat/stream`

建议扩展健康检查返回：

- `langgraph_enabled`
- `langgraph_checkpointer_backend`
- `langgraph_thread_id_source`
- `langgraph_resume_supported`

---

## 6. 推荐的 LangGraph 目标结构

## 6.1 推荐的 State 结构

建议先定义一个清晰但不过度复杂的 state：

```python
class CRMGraphState(TypedDict, total=False):
    session_id: str
    thread_id: str
    user_id: str
    user_message: str
    request_web_research: bool
    request_dynamic_library: bool

    recent_history: list[dict]
    retrieved_docs: list[dict]
    planner: dict
    match_assessment: dict
    generation_ir: dict
    spec: dict
    validation: dict
    schema_validation: dict
    repair_trace: list[dict]

    research_result: dict
    persisted_web_docs: list[dict]
    generated: dict
    dll_result: dict
    last_generation_result: dict

    clarify_stage: str
    final_message: str
    final_data: dict
    error: str
    status: str
```

这个 state 已经足够覆盖当前链路，不需要一开始就做得很重。

## 6.2 推荐的节点划分

建议第一版图把当前链路拆成这些节点：

1. `load_context`
2. `resume_or_reset`
3. `retrieve_knowledge`
4. `plan_task`
5. `route_task`
6. `perform_web_research`
7. `assess_generation_match`
8. `route_generation_gate`
9. `collect_generation_ir`
10. `interrupt_for_clarification`
11. `build_model_spec`
12. `validate_model_spec`
13. `repair_model_spec`
14. `generate_matlab`
15. `build_dynamic_library`
16. `build_chat_reply`
17. `build_generation_reply`
18. `persist_result`

## 6.3 推荐的条件边

建议至少有这些路由：

- 普通聊天 → `build_chat_reply`
- 生成请求但需要 object/family 澄清 → `interrupt_for_clarification`
- 生成请求且需要 slot 补充 → `interrupt_for_clarification`
- 规格校验失败且还有修复次数 → `repair_model_spec`
- 修复后继续回到 `validate_model_spec`
- 生成成功且请求 DLL → `build_dynamic_library`
- 生成成功且无需 DLL → `build_generation_reply`

## 6.4 推荐的工作流形态

建议保留两个核心 loop：

1. **clarify loop**
   - `collect_generation_ir -> interrupt_for_clarification -> resume -> collect_generation_ir`

2. **repair loop**
   - `validate_model_spec -> repair_model_spec -> validate_model_spec`

这两个 loop 正是当前手工状态机最复杂、也最适合交给 LangGraph 管理的部分。

---

## 7. 推荐的迁移路径

## 7.1 Phase 0：最小接入验证

目标：验证 LangGraph 能否不破坏现有系统地接入。

改动建议：

- 增加 `langgraph` 依赖
- 新建 `agents/workflows/` 骨架
- 先只做“chat + generation 的空壳图”
- `CRMAgent` 增加开关：
  - `LANGGRAPH_ENABLED=false` 时走旧链路
  - `LANGGRAPH_ENABLED=true` 时走新图入口

验收标准：

- API 不变
- 普通聊天能走图入口并返回结果
- 不影响现有旧链路回退

## 7.2 Phase 1：迁移主生成链路

目标：把 generation 主链路迁入图，但先不强制收敛所有历史状态。

改动建议：

- 把 `retrieve -> planner -> match -> IR -> spec -> validate -> codegen` 迁入图
- 澄清仍允许兼容旧的 `SessionStore` 字段
- DLL 分支作为可选后置节点挂入图

验收标准：

- 成功生成 `.m` 文件
- 校验失败可回环修复
- DLL 构建分支不破坏主链路

## 7.3 Phase 2：迁移中断恢复

目标：把最关键的人工澄清挂起/恢复改成 LangGraph 原生机制。

改动建议：

- object/family/slot 澄清改成 `interrupt()`
- API 收到用户补充时，用 `Command(resume=...)` 继续执行
- `thread_id` 固定映射到 `session_id`
- `pending_generation_match` / `pending_generation_ir` 逐步退役

验收标准：

- 重启服务后，澄清状态可继续
- 用户补充参数后可准确恢复到中断前节点
- 不再依赖手工拼装挂起状态

## 7.4 Phase 3：增强可观测与运维能力

目标：把 LangGraph 的工程收益真正落地。

改动建议：

- 健康检查暴露 graph/checkpointer 信息
- 返回 `checkpoint_id` 或 `graph_run_id`
- 对关键节点增加统一日志和耗时统计
- 如果需要，再补充流式输出接口

验收标准：

- 能判断当前请求走的是旧链路还是图链路
- 能定位失败在图的哪个节点
- 能看见恢复点和最终收口点

---

## 8. 建议新增和修改的文件

## 8.1 建议新增

- `agents/workflows/__init__.py`
- `agents/workflows/state.py`
- `agents/workflows/nodes.py`
- `agents/workflows/routes.py`
- `agents/workflows/checkpointer.py`
- `agents/workflows/graph.py`
- `agents/workflows/service.py`
- `tests/test_langgraph_workflow.py`
- `tests/test_langgraph_interrupt_resume.py`

## 8.2 建议修改

- `environment.yml`
- `requirements.txt`
- `config/settings.py`
- `agents/crm_agent.py`
- `api/server.py`

## 8.3 明确不建议大改

- `knowledge_base/rag_retriever.py`
- `knowledge_base/web_evidence_retriever.py`
- `agents/structured_generation_ir.py`
- `agents/model_spec_builder.py`
- `agents/model_spec_validator.py`
- `agents/matlab_codegen.py`
- `agents/tools.py`

---

## 9. 风险与注意事项

### 9.1 不要同时维护两套复杂状态太久

兼容期内允许：

- `SessionStore` 保存历史
- LangGraph 保存流程状态

但不建议长期双写所有中间状态，否则会出现：

- 状态漂移
- 恢复点不一致
- 调试困难

### 9.2 不要把 LangGraph 当成业务能力替代品

LangGraph 不是用来替换：

- RAG 检索能力
- MATLAB 代码生成能力
- 规格校验能力

它的价值在于：

- 让这些能力之间的编排关系更清晰、更稳、更可恢复

### 9.3 先统一依赖声明

当前仓库存在一个需要顺手收敛的小问题：

- `environment.yml` 里有 `langchain*`
- `requirements.txt` 里没有对应声明

如果要正式接 LangGraph，建议把依赖策略统一，否则后续部署环境容易出现“本地能跑、容器不一致”的问题。

---

## 10. 最终建议

如果目标只是继续扩知识库和模板族，LangGraph 不是必须马上上。

但如果目标包括以下任意几项：

- 多轮澄清稳定恢复
- 服务重启后继续执行
- 复杂分支继续增长
- 更标准的状态机编排
- 更强的追踪和调试能力

那么当前系统已经到了**适合接入 LangGraph**的阶段。

对这个仓库的最优策略不是“大重构”，而是：

1. **先加图层，不动业务层**
2. **先兼容旧入口，再逐步切主链路**
3. **先解决中断恢复，再追求流式和高级特性**

最终落地建议：**采用分阶段接入，优先改造 `CRMAgent` 的编排逻辑和挂起/恢复逻辑，保留现有 RAG、IR、Spec、Codegen 与 DLL 工具链不动。**

---

## 11. 参考资料

- LangGraph Overview  
  https://docs.langchain.com/oss/python/langgraph/overview
- LangGraph Persistence  
  https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph Human-in-the-loop / Interrupts  
  https://docs.langchain.com/oss/python/langgraph/interrupts
- LangGraph Checkpointer Integrations  
  https://docs.langchain.com/oss/python/integrations/checkpointers

