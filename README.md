# RAG CRM Agent

## 项目定位

RAG CRM Agent 是一个面向 MATLAB `.m` 脚本生成的对话式建模系统。

当前版本的准确定位不是“任意物理系统都能自动建模”的完全开放域生成器，而是一个：

- 带检索约束的建模生成系统
- 带澄清门控的生成式助手
- 带结构化 IR 的半开放域 MATLAB 建模平台

相比早期“命中 `model_id` 后直接套模板”的实现，当前主链路已经升级为：

`检索与候选判断 -> 澄清门控 -> OpenModelIR / ModelSpec -> AssemblyPlan -> block renderer -> MATLAB 脚本`

这意味着当前系统已经具备更强的 family 级别泛化能力，但生成能力仍然受 family schema、片段库与 block 库约束。

---

## 当前核心能力

### 1. 检索增强与候选门控

- 支持本地索引 + Qdrant 的混合检索
- 支持 `BM25 + 向量召回 + 重排融合`
- 支持候选 family / model 推断与生成前门控
- 在 `no_candidate`、`domain_conflict`、`ambiguous_family`、`low_confidence` 等场景下优先澄清，而不是盲目生成

### 2. 结构化生成链路

- 支持从用户自然语言抽取结构化生成信息
- 支持 `OpenModelIR`、`ModelSpec` 与兼容转换链路
- 支持对象级、family 级、slot 级澄清
- 支持结构化校验、语义校验、自动修复与兜底

### 3. MATLAB 代码生成

- 优先走 family assembler + block renderer 的组装式生成
- 仍保留旧模板生成器作为兼容与回退路径
- 生成结果会写入 `generated_models/`
- 返回脚本文本、输出文件路径、装配信息和校验结果

### 4. 质量与运行保障

- 支持静态校验与可选 MATLAB / Octave smoke 校验
- 支持 `memory` / `redis` 两种会话存储后端
- 提供健康检查接口，可查看当前检索链路是否真正处于混合检索状态
- 提供 Golden 回归脚本用于匹配质量验证

---

## 当前支持范围

当前主生成能力以 family 为核心，重点覆盖以下方向：

- 航空航天：`launch_dynamics`、`trajectory_ode`、`powered_ascent`、`reentry_dynamics`、`aircraft_point_mass`、`interceptor_guidance`
- 水下发射 / 航行：`underwater_launch`、`underwater_cruise`、`submarine_depth_control`
- 轨道：`orbital_dynamics`、`relative_orbit`、`orbit_transfer`
- 跟踪 / 融合：`tracking_estimation`、`sensor_fusion_tracking`、`bearing_only_tracking`
- 战场态势：`combat_attrition`、`battlefield_awareness`、`threat_assessment`、`salvo_engagement`

此外，知识目录中仍保留了一批传统模板式示例，例如控制、估计、信号处理、能源、机器人等 MATLAB/Simulink 示例模型，用于兼容与基础演示。

---

## 推荐运行方式

当前仓库最推荐的运行方式是：

### 混合部署

- Docker 只启动基础设施：`redis`、`qdrant`、`ollama`、`ollama-init`
- Python 应用层在本机 `rag_crm` 环境中运行

原因：

- 更贴合当前开发和调试方式
- 可以直接复用宿主机已安装的 Python 环境
- 可以复用宿主机已经缓存的 Ollama / Sentence Transformers 模型
- 可以避开 Python 基础镜像拉取失败或网络不稳定问题

### 快速启动

1. 启动基础设施

```powershell
docker compose up -d redis qdrant ollama ollama-init
```

2. 构建知识索引并写入 Qdrant

```powershell
powershell -ExecutionPolicy Bypass -File tools\run_in_rag_crm.ps1 main.py build --with-qdrant
```

3. 启动本机 API

```powershell
powershell -ExecutionPolicy Bypass -File tools\run_in_rag_crm.ps1 main.py api
```

4. 打开页面

- `http://127.0.0.1:8000/ui`

如果你已经手动激活了 `rag_crm` 环境，也可以直接执行：

```powershell
python main.py build --with-qdrant
python main.py api
```

### 可选：全 Docker 模式

仓库中的 `docker-compose.yml` 仍保留完整编排，可选一键启动：

```powershell
docker compose up -d --build
```

该模式会启动：`redis`、`qdrant`、`ollama`、`ollama-init`、`kb-build`、`app1`、`app2`。

---

## 常用接口

- `GET /ui`：Web 聊天页面
- `GET /api/health`：健康检查
- `GET /api/models`：查看当前支持的模型目录
- `POST /api/chat`：主聊天接口
- `POST /api/query`：兼容接口，行为与聊天接口一致
- `GET /docs`：Swagger UI

健康检查推荐关注：

- `status`
- `session_store_backend`
- `retrieval.hybrid_effective`

如果 `retrieval.hybrid_effective` 为 `false`，通常说明当前没有真正跑在完整混合检索状态。

---

## 常用命令

### 构建知识库

```powershell
python main.py build
python main.py build --with-qdrant
```

### 启动 API

```powershell
python main.py api
```

### 本地交互模式

```powershell
python main.py run
```

### Golden 回归验证

```powershell
powershell -ExecutionPolicy Bypass -File tools\verify_golden.ps1
```

---

## 关键目录

- `main.py`：项目入口，支持 `build / run / test / api`
- `api/`：FastAPI 服务与 HTTP 接口
- `agents/`：主编排链路、任务规划、IR、规格校验、代码生成
- `agents/structured_generation/`：槽位抽取、schema 注册、澄清策略
- `knowledge_base/`：知识文档、索引构建、检索、装配规划、模板与 family 代码生成
- `knowledge_base/blocks/`：分领域 block 渲染规则
- `generated_models/`：生成出的 MATLAB 文件输出目录
- `tools/`：运行包装脚本、Golden 回归脚本等辅助工具
- `docker-compose.yml`：基础设施与全 Docker 模式编排
- `.env`：本地运行配置

---

## 当前设计边界

当前版本已经明显强于纯模板匹配系统，但仍有清晰边界：

- 仍然是半开放域，而不是完全开放域建模器
- 主要生成能力仍依赖 `family`、`fragment`、`block` 库
- 不具备“对任意未知物理系统自由拼装方程并稳定生成可执行 MATLAB 脚本”的能力
- 不受原生 block 支持的草稿片段，目前可能只能降级为兼容路径或注释化输出
- `database/` 中的 CRM 数据模块当前不属于主生成链路

如果请求超出支持范围，系统的正确行为应该是优先澄清或明确拒绝，而不是误生成错误脚本。

---

## 关键配置项

常用环境变量包括：

- `OLLAMA_BASE_URL`、`OLLAMA_MODEL`
- `QDRANT_HOST`、`QDRANT_PORT`、`QDRANT_COLLECTION`
- `EMBEDDING_MODEL`、`EMBEDDING_DEVICE`
- `RETRIEVAL_VECTOR_BACKEND`
- `RETRIEVAL_BM25_WEIGHT`、`RETRIEVAL_VECTOR_WEIGHT`、`RETRIEVAL_RERANK_BLEND`
- `RETRIEVAL_CANDIDATE_MULTIPLIER`
- `MODEL_SPEC_REPAIR_MAX_ROUNDS`
- `SESSION_STORE_BACKEND`
- `SESSION_HISTORY_SIZE`、`CHAT_HISTORY_WINDOW`、`FALLBACK_HISTORY_WINDOW`、`PLANNER_HISTORY_WINDOW`
- `SESSION_TTL_SEC`

部署侧额外常用：

- `PYTHON_BASE_IMAGE`
- `APP_IMAGE_NAME`
- `DOCKER_OLLAMA_HOME`
- `DOCKER_ST_CACHE_DIR`
- `FORCE_REBUILD_QDRANT`

---

## 文档索引

- `项目架构说明.md`：当前整体架构、分层职责与运行链路
- `详细设计文档.md`：实现级设计细节
- `部署说明.md`：部署方式、环境变量、启动与排错
- `操作手册.md`：日常使用、构建、重建索引与排错
- `知识库.md`：知识索引、文档组织与检索说明
- `任务路由.md`：任务规划与门控逻辑
- `中间表示.md`：IR 背景说明
- `开放模型中间表示草案.md`：开放域 IR 演进思路
- `强半开放域.md`：当前“强半开放域”定位说明
- `强半开放域验收清单_当前差距_最短改造路径.md`：当前差距与最短改造路径
- `阶段二_开放域IR_Planner_验收对照清单.md`：阶段性验收对照

---

## 一句话总结

当前版本已经不是简单的“模板检索 + 文本生成”，而是一个带检索、澄清、结构化 IR、family 装配和多层校验的半开放域 MATLAB 建模系统。
