# MATLAB RAG 对话智能体详细设计文档

## 1. 文档目标
本文档用于定义当前项目的可落地技术方案，覆盖：
- 系统架构
- 核心模块设计
- 工具链与版本约束
- 部署方式
- 硬件要求
- 运维与扩展建议

适用项目：`D:\python\rag_crm_agent`

---

## 2. 系统定位与目标

### 2.1 业务目标
构建一个对话式 AI 智能体，能够：
- 进行普通技术问答
- 根据自然语言建模需求，自动生成 MATLAB `.m` 文件
- 通过 RAG 检索提高模型匹配与参数推断准确率

### 2.2 当前关键能力
- 单入口对话 API：`/api/chat`
- 混合检索：`BM25 + 向量检索(Qdrant/本地) + 重排`
- ModelSpec 强约束：`JSON Schema + 语义校验 + 自动修复循环`
- 代码生成落盘：`generated_models/*.m`

---

## 3. 总体架构

```text
Web UI (web_ui.html)
  -> FastAPI (api/server.py)
    -> Agent Orchestrator (agents/crm_agent.py)
      -> Task Planner (agents/task_planner.py)
      -> Hybrid Retriever (knowledge_base/rag_retriever.py)
      -> ModelSpec Builder (agents/model_spec_builder.py)
      -> ModelSpec Validator (agents/model_spec_validator.py)
      -> MATLAB Code Generator (agents/matlab_codegen.py)
      -> Legacy Template Fallback (agents/tools.py / knowledge_base/matlab_generator.py)
    -> JSON Response

Knowledge Layer:
  - Local index: knowledge_base/matlab_knowledge_index.json
  - Qdrant collection: crm_filters
  - Catalog data: knowledge_base/matlab_model_data.py

LLM Layer:
  - Ollama: http://localhost:11434
  - Model: deepseek-r1:7b
```
## 3.1 工具链
本节给出“完整可运行链路”所用工具与模块，不仅包含第三方软件，也包含本项目关键代码组件。

### 3.1.1 运行时与基础环境
- Python 3.10+（建议与 Conda 环境 `rag_crm` 一致）
- pip（依赖安装）
- Conda（环境隔离与解释器管理，可选但推荐）
- Windows PowerShell（当前项目默认命令行环境）

### 3.1.2 后端框架与基础库
- FastAPI：HTTP API 服务框架
- Uvicorn：ASGI 服务器
- Pydantic：请求/响应模型校验
- python-dotenv：`.env` 配置读取
- requests：调用 Ollama 与 Qdrant REST 接口
- jsonschema：ModelSpec JSON Schema 强校验

### 3.1.3 向量检索与知识库工具链
- qdrant-client：Qdrant 客户端（含兼容模式下 REST 回退）
- Qdrant Server：向量数据库服务（collection 默认 `crm_filters`）
- sentence-transformers：文本向量化
- torch：向量模型推理运行时
- 嵌入模型：`BAAI/bge-large-zh-v1.5`
- 本地知识索引：`knowledge_base/matlab_knowledge_index.json`

### 3.1.4 LLM 工具链
- Ollama：本地大模型推理服务（默认 `http://localhost:11434`）
- 模型：`deepseek-r1:7b`
- 调用接口：
1. `POST /api/chat`（主路径）
2. `POST /api/generate`（回退路径）

### 3.1.5 容器与服务编排（可选）
- Docker：运行 Ollama/Qdrant 容器（推荐本地开发使用）
- 端口约定：
1. Ollama：`11434`
2. Qdrant：`6333`

### 3.1.6 项目代码模块清单（核心）
- 入口与命令：
1. `main.py`（`build/run/test/api`）
- API 层：
1. `api/server.py`
- Agent 层：
1. `agents/crm_agent.py`
2. `agents/task_planner.py`
3. `agents/model_spec_builder.py`
4. `agents/model_spec_schema.py`
5. `agents/model_spec_validator.py`
6. `agents/matlab_codegen.py`
7. `agents/tools.py`（兼容模板工具）
- 知识库层：
1. `knowledge_base/rag_retriever.py`
2. `knowledge_base/builder.py`
3. `knowledge_base/matlab_model_data.py`
4. `knowledge_base/matlab_generator.py`
- 配置层：
1. `config/settings.py`
- 前端：
1. `web_ui.html`
- 产物目录：
1. `generated_models/`

### 3.1.7 数据与存储相关模块（项目内现存）
- `database/crm_db.py`
- `database/models.py`
- `database/schema.sql`
- `crm_database.db`

说明：数据库模块属于项目历史能力，当前 MATLAB 对话生成主链路不强依赖该数据库。

---

## 4. 核心模块设计

## 4.1 前端层
文件：`web_ui.html`

职责：
- 输入用户问题
- 调用 `/api/chat`
- 显示文本回复与脚本预览
- 调用 `/api/health`、`/api/models` 进行状态展示

关键特性：
- 会话窗口与输入框分区布局
- 推荐建模语句快捷按钮
- 错误与兜底提示展示

## 4.2 API 层
文件：`api/server.py`

核心接口：
- `GET /api/health`：健康检查
- `GET /api/models`：支持模型列表
- `POST /api/chat`：统一对话入口
- `POST /api/query`：兼容入口

职责：
- 请求参数校验
- Agent 懒初始化
- 返回统一结构化 JSON

## 4.3 Agent 编排层
文件：`agents/crm_agent.py`

主流程：
1. 识别系统命令（`/new`、`/models`）
2. 统一检索知识证据
3. `task_planner` 判定任务类型（chat / matlab_generation）
4. 建模链路：规格构建 -> 校验/修复 -> 代码生成
5. 对话链路：RAG context 注入 Ollama
6. 写入会话缓存（默认 50 条，支持 memory/redis 后端）

输出增强字段：
- `planner`
- `retrieved_knowledge`
- `schema_validation`
- `repair_trace`
- `auto_repaired_by_llm`
- `auto_recovered_by_heuristic`

## 4.4 混合检索层（重点）
文件：`knowledge_base/rag_retriever.py`

检索策略：
1. BM25 召回（词项匹配）
2. 向量召回
3. 重排融合（关键词/别名/模型ID/文本重叠）

向量后端优先级：
1. Qdrant（优先）
2. Local Embedding（Qdrant不可用时回退）
3. None（向量模型不可用）

兼容能力：
- 对 Qdrant client/server schema mismatch 自动走 REST 兼容模式

## 4.5 规格构建与校验层
文件：
- `agents/model_spec_schema.py`
- `agents/model_spec_builder.py`
- `agents/model_spec_validator.py`

设计要点：
- 统一 `ModelSpec JSON Schema`
- LLM 输出必须为 JSON
- 校验失败触发自动修复循环（可配置轮次）
- 若修复仍失败，退回启发式规格

## 4.6 MATLAB 代码生成层
文件：
- `agents/matlab_codegen.py`
- `knowledge_base/matlab_generator.py`

流程：
1. 接收通过校验的规格
2. 渲染对应模型脚本
3. 生成文件名并写入 `generated_models/`
4. 返回脚本与路径

---

## 5. 数据模型设计

## 5.1 知识文档结构（本地索引/Qdrant payload）
```json
{
  "id": 123,
  "text": "可检索正文",
  "payload": {
    "type": "model|example|...",
    "model_id": "rocket_launch_1d",
    "name": "1D Rocket Launch Dynamics",
    "category": "aerospace",
    "description": "...",
    "keywords": ["火箭", "推力", "弹道"],
    "default_params": {}
  }
}
```

## 5.2 ModelSpec 结构
强约束字段：
- `task_goal`
- `model_id`
- `assumptions`
- `parameters`
- `simulation_plan.stop_time`
- `required_outputs`
- `missing_info`

---

## 6. 工具链与版本

## 6.1 Python 依赖（requirements.txt）
- `fastapi==0.104.1`
- `uvicorn[standard]==0.24.0`
- `python-dotenv==1.0.0`
- `qdrant-client==1.7.1`
- `sentence-transformers==2.2.2`
- `requests==2.31.0`
- `torch==2.7.0`
- `jsonschema==4.23.0`

## 6.2 外部服务
- Ollama（本地LLM服务）
- DeepSeek 模型：`deepseek-r1:7b`
- Qdrant（向量数据库）

## 6.3 运行时配置（.env）
关键项：
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `QDRANT_HOST`
- `QDRANT_PORT`
- `QDRANT_COLLECTION`
- `RETRIEVAL_VECTOR_BACKEND`
- `RETRIEVAL_BM25_WEIGHT`
- `RETRIEVAL_VECTOR_WEIGHT`
- `RETRIEVAL_RERANK_BLEND`
- `MODEL_SPEC_REPAIR_MAX_ROUNDS`

---

## 7. 硬件要求

## 7.1 最低可运行（开发调试）
- CPU：4 核
- 内存：16 GB
- 磁盘：30 GB 可用空间
- GPU：可无（纯CPU可运行，但推理慢）

适用场景：
- 本地功能开发
- 小规模单用户测试

## 7.2 推荐配置（稳定开发/演示）
- CPU：8 核以上
- 内存：32 GB
- 磁盘：80 GB NVMe
- GPU：NVIDIA 12 GB 显存以上（建议）

适用场景：
- 本地多轮对话+频繁建模生成
- Qdrant + 向量模型稳定运行

## 7.3 生产建议（多用户）
- CPU：16 核以上
- 内存：64 GB
- 磁盘：200 GB NVMe
- GPU：24 GB 显存以上（或多卡）
- 网络：千兆内网

适用场景：
- 并发请求
- 低延迟与高稳定性要求

---

## 8. 部署与运行

## 8.1 本地启动步骤
1. 安装依赖
```bash
pip install -r requirements.txt
```

2. 构建知识库
```bash
python main.py build
python main.py build --with-qdrant
```

3. 启动 API
```bash
python main.py api
```

4. 访问前端
```text
http://127.0.0.1:8000/ui
```

## 8.2 健康检查与验证
```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/models
```

---

## 9. 性能与可用性设计

## 9.1 超时与重试
- Ollama 对话请求带超时
- `/api/chat` 失败后自动降级 `/api/generate`
- 仍失败则给结构化兜底提示

## 9.2 降级策略
- Qdrant不可用 -> Local向量
- 向量不可用 -> BM25
- LLM规格失败 -> 自动修复循环
- 修复失败 -> 启发式规格
- 仍失败 -> 明确错误返回

## 9.3 观测性
关键日志点：
- 向量后端选择（qdrant/local/none）
- Qdrant 检索请求成功率
- 规格修复轮次和失败原因
- 生成文件成功率

---

## 10. 安全与风险

主要风险：
- 第三方依赖版本兼容（qdrant-client / pydantic / huggingface_hub）
- LLM输出非结构化导致规格不合法
- 用户输入含不完整参数引发生成失败

控制策略：
- 强制 JSON Schema
- 自动修复循环与启发式兜底
- 版本锁定与兼容补丁

---

## 11. 扩展路线（Qdrant内容增强）

建议迭代方向：
1. 增加文档类型：`theory/equation/param_guide/failure_case`
2. 增强 payload：`domain/intent/tags/quality_score/version`
3. 增加 query expansion（同义词和别名词典）
4. 引入评测集（Hit@1/Recall@5）持续优化
5. 增加 rerank 学习型模型（可选）

---

## 12. 验收标准

满足以下条件视为通过：
1. `/api/chat` 普通对话与建模任务均返回 200
2. 建模任务可落地生成 `.m` 文件
3. 日志可见混合检索链路被调用
4. `schema_validation.valid=true` 或有明确修复轨迹
5. Qdrant不可用时系统可降级且不崩溃
