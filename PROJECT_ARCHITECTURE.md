# 对话式 AI 智能体项目架构说明

## 1. 项目目标与当前形态
本项目当前是一个**对话式 AI 智能体助手**，支持两类核心能力：

1. 普通多轮对话（本地 Ollama 大模型驱动）
2. MATLAB 建模脚本生成（根据自然语言描述生成 `.m` 文件）

前端提供聊天 UI，后端提供 API，智能体根据意图决定是“普通问答”还是“触发 MATLAB 代码生成工具”。

---

## 2. 总体架构

```text
Web UI (web_ui.html)
   -> FastAPI (api/server.py)
      -> Agent Core (agents/crm_agent.py)
         -> Unified Task Planner (agents/task_planner.py)
         -> Ollama Chat API (本地大模型)
         -> RAG Retriever (knowledge_base/rag_retriever.py)
         -> ModelSpec Builder (agents/model_spec_builder.py)
         -> ModelSpec Validator (agents/model_spec_validator.py)
         -> MATLAB CodeGen (agents/matlab_codegen.py -> knowledge_base/matlab_generator.py)
      -> Response JSON
   -> 前端渲染文字回复 / 脚本预览
```

### 关键目录
- `api/`：HTTP 接口层（FastAPI）
- `agents/`：智能体逻辑层（对话决策、上下文、RAG编排、规格校验、代码生成）
- `knowledge_base/`：模型知识库、RAG检索数据、模板渲染引擎
- `generated_models/`：生成后的 `.m` 文件落地目录
- `web_ui.html`：前端聊天页面
- `config/settings.py`：配置加载（含 `.env` 读取）

---

## 3. 工具链与运行依赖

### 后端框架与服务
- `FastAPI`：接口服务
- `uvicorn`：ASGI 运行
- `requests`：调用 Ollama HTTP API

### 本地大模型
- `Ollama`
- 模型：`deepseek-r1:7b`
- 接口：
  - `POST /api/chat`
  - `POST /api/generate`（兜底）

### MATLAB 生成相关
- 知识条目：`knowledge_base/matlab_model_data.py`
- RAG 检索器：`knowledge_base/rag_retriever.py`
- ModelSpec 构建：`agents/model_spec_builder.py`
- ModelSpec 校验：`agents/model_spec_validator.py`
- 代码生成：`agents/matlab_codegen.py`
- 模板渲染与落盘：`knowledge_base/matlab_generator.py`

### 可选向量检索链路
- `qdrant-client`
- `sentence-transformers`
- `build --with-qdrant` 用于预构建向量库
- 运行时检索支持 `BM25 + 向量 + 重排`（Qdrant优先，失败自动降级）

---

## 4. 前端输入到后端输出的完整流程

## 4.1 前端请求发起
页面：`/ui`（`web_ui.html`）  
前端调用：
- `POST /api/chat`（主入口）
- `GET /api/models`（模板列表）
- `GET /api/health`（健康状态）

请求体示例：
```json
{
  "message": "生成一个PID闭环Simulink模型，kp=1.5, ki=0.8, kd=0.02",
  "user_id": "web_user",
  "session_id": "web_xxx"
}
```

## 4.2 API 层处理
`api/server.py` 接收请求后：
1. 校验参数
2. 保证 Agent 实例可用（懒初始化）
3. 调用 `agent.chat(...)`
4. 返回统一结构：
```json
{
  "success": true,
  "message": "...",
  "data": { ... }
}
```

## 4.3 Agent 层处理
`agents/crm_agent.py` 的 `chat()` 流程：
1. 识别系统命令（`/new`, `/models`）
2. 统一 RAG 检索（先召回知识证据）
3. `task_planner` 根据“用户输入 + 证据 + 最近历史”判断任务类型
   - `matlab_generation`
   - `chat`
   - `clarify`（预留）
4. 若为建模任务：调用 RAG 生成链路  
5. 若为聊天任务：带检索证据增强对话回答  
6. 维护会话上下文缓存并返回结构化数据

RAG 生成链路（最小可运行版）：
1. `MatlabRAGRetriever` 执行混合检索：`BM25召回 + 向量召回 + 重排融合`
2. `ModelSpecBuilder` 基于“用户输入 + 证据”生成 `ModelSpec`
3. `ModelSpecValidator` 执行 `JSON Schema强约束校验 + 语义校验 + 自动修复循环`
4. `MatlabCodeGenerator` 生成并保存 `.m` 文件
5. 返回文件路径、脚本、ModelSpec、检索证据和校验信息

## 4.4 响应渲染
前端收到响应后：
- 渲染 `message`
- 若 `data.script` 存在，展示脚本卡片
- 若 `data.used_fallback=true`，展示兜底提示

---

## 5. 智能体是如何工作的

## 5.1 上下文缓存机制
- 缓存粒度：按 `session_id`
- 会话存储：支持 `memory` / `redis` 两种后端
- 会话上限：每个会话最多 `50` 条消息（约 25 轮）
- 喂给 LLM：最近 `12` 条消息（约 6 轮）
- 超时重试/生成兜底：最近 `6` 条消息（约 3 轮）
- `/new` 可清空当前会话缓存
- `memory` 后端不落盘，重启服务后清空
- `redis` 后端可跨实例共享，并按 TTL 自动过期

## 5.2 大模型调用策略
主调用：`/api/chat`  
配置重点：
- `think: false`（避免只返回 thinking 而 content 为空）
- `num_predict` 可配置（控制输出长度与时延）
- `timeout` 可配置（避免慢响应误判失败）

兜底策略：
1. `/api/chat` 首次失败/超时
2. 自动短上下文重试
3. 仍失败则尝试 `/api/generate`
4. 仍失败则返回本地 fallback 提示

## 5.3 MATLAB 生成策略
当识别到“生成/构建 + 模型关键词”时：
1. 从 RAG 知识库检索 Top-K 证据
2. 由 LLM + 证据推导 `ModelSpec`
3. 进行 `JSON Schema` 校验和语义校验（参数完整性、状态空间维度等）
4. 若失败，执行自动修复循环（LLM修复 -> 再校验，最多N轮）
5. 仍失败再回退启发式规格兜底
6. 通过后按规格渲染 `.m` 脚本
7. 写入 `generated_models/`
8. 返回文件路径、脚本内容、规格与证据

补充：
- 已支持 `rocket_launch_1d`（一维火箭发射动力学）模型
- 支持“解释类问题”和“建模类问题”在统一入口下自动分流

---

## 6. 关键接口说明

### `POST /api/chat`
- 主聊天接口（推荐）
- 自动处理普通对话与 MATLAB 生成请求

### `POST /api/query`
- 兼容接口（语义同 chat）
- 入参字段名为 `question`

### `GET /api/models`
- 返回当前支持的 MATLAB 模板

### `GET /api/health`
- 服务与智能体状态检查

### `GET /ui`
- 前端页面

---

## 7. 结果输出与落地

普通对话输出：
- `message`（自然语言）
- `data.query_type = "chat"`

MATLAB 生成输出：
- `data.query_type = "matlab_generation"`
- `generated_file`
- `generated_file_path`
- `script`
- `parsed_params`
- `model_spec`
- `validation`
- `retrieved_knowledge`

物理文件落地：
- 路径：`generated_models/*.m`

---

## 8. 当前已知运行前提

1. 需要本地 Ollama 可访问（默认 `http://localhost:11434`）
2. 模型存在：`deepseek-r1:7b`
3. 后端启动：`python main.py api`
4. 前端访问：`http://127.0.0.1:8000/ui`

---

## 9. 建议的后续演进方向

1. 为 Redis 会话增加鉴权、监控与细粒度限流  
2. 流式输出（SSE/WebSocket）提升对话体验  
3. 模板版本管理与参数校验器  
4. 增加“生成说明文档 + 代码”双产物模式  
5. 引入审计日志（用户输入、工具调用、耗时、失败原因）
