# RAG CRM Agent

## 项目简介

RAG CRM Agent 是一个面向 MATLAB `.m` 脚本生成的对话式建模系统。

当前版本的准确定位不是“任意物理系统都能自动建模”的完全开放域生成器，而是一个：

- 带检索约束的建模生成系统
- 带澄清门控的生成式助手
- 带结构化 IR 的半开放域 MATLAB 建模平台

当前主链路已经统一为：

```text
用户请求
  -> 检索与候选识别
  -> 任务规划
  -> 生成匹配评估与澄清门控
  -> StructuredGenerationIR / OpenModelIR
  -> ModelSpec 兼容层
  -> AssemblyPlan
  -> family assembler + block renderer
  -> MATLAB 脚本落盘与校验
```

如果用户明确要求导出 DLL / 动态库，系统还会在脚本生成成功后进入本地 MCP 构建链。

## 文档分工

为避免说明重复和表述漂移，当前三份核心文档按以下方式分工：

| 文档 | 主要职责 | 适合什么时候看 |
| --- | --- | --- |
| `README.md` | 项目简介、快速启动、常用命令、文档导航 | 第一次进入仓库、快速上手 |
| `项目架构说明.md` | 宏观分层、核心数据流、模块职责、部署形态、架构边界 | 想先理解系统“整体怎么工作” |
| `详细设计文档.md` | 面向实现的模块设计、状态管理、IR、校验、构建链、接口返回 | 要改代码、补文档、做设计评审 |

因此：

- `README.md` 不再展开实现级细节
- `项目架构说明.md` 不再承担快速启动手册角色
- `详细设计文档.md` 不再重复写一遍上手说明和宏观架构概览

## 快速启动

### 推荐模式：混合部署

当前最推荐的运行方式是：

- Docker 只启动基础设施：`redis`、`qdrant`、`ollama`、`ollama-init`
- Python 应用层在本机 `rag_crm` 环境中运行

### 启动步骤

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

## 常用接口

- `GET /ui`：Web 聊天页面
- `GET /api/health`：健康检查
- `GET /api/models`：查看当前支持的模型目录
- `POST /api/chat`：主聊天接口
- `POST /api/query`：兼容接口，行为与聊天接口一致
- `GET /docs`：Swagger UI

健康检查建议关注：

- `status`
- `session_store_backend`
- `retrieval.hybrid_effective`

如果 `retrieval.hybrid_effective` 为 `false`，通常说明当前没有真正跑在完整混合检索状态。

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

## 核心目录

- `main.py`：项目入口，支持 `build / run / test / api`
- `api/`：FastAPI 服务与 HTTP 接口
- `agents/`：主编排链路、任务规划、IR、规格校验、代码生成
- `agents/structured_generation/`：槽位抽取、schema 注册、澄清策略
- `knowledge_base/`：知识文档、索引构建、检索、装配规划、family 代码生成
- `knowledge_base/blocks/`：分领域 block 渲染规则
- `generated_models/`：生成出的 MATLAB 文件输出目录
- `generated_builds/`：本地动态库构建作业目录
- `tools/`：运行包装脚本、Golden 回归、本地 MCP 构建工具等

## 当前支持范围

当前主生成能力以 family 为核心，重点覆盖以下方向：

- 航空航天：`launch_dynamics`、`trajectory_ode`、`powered_ascent`、`reentry_dynamics`、`aircraft_point_mass`、`interceptor_guidance`
- 水下发射 / 航行：`underwater_launch`、`underwater_cruise`、`submarine_depth_control`
- 轨道：`orbital_dynamics`、`relative_orbit`、`orbit_transfer`
- 跟踪 / 融合：`tracking_estimation`、`sensor_fusion_tracking`、`bearing_only_tracking`
- 战场态势：`combat_attrition`、`battlefield_awareness`、`threat_assessment`、`salvo_engagement`

支持范围的宏观说明以 `项目架构说明.md` 为主；实现约束和组件细节以 `详细设计文档.md` 为主。

## 当前边界

当前版本已经明显强于纯模板匹配系统，但仍有清晰边界：

- 仍然是半开放域，而不是完全开放域建模器
- 主要生成能力仍依赖 `family`、`fragment`、`block` 库
- `database/` 中的 CRM 模块当前不属于在线主生成链路
- 动态库构建主要通过本地工具链触发，而不是独立 HTTP 构建服务

如果请求超出支持范围，系统的正确行为应该是优先澄清或明确拒绝，而不是误生成错误脚本。

## 联网研究 MVP

- 当前版本新增了一个独立的 web research MCP：`tools/mcp_web_research/`
- 当用户请求中明确出现“联网 / 网上 / 搜索 / 从网上”等标记时，生成链会先执行：`联网检索 -> 抓取网页 -> 落盘到 generated_research/ -> 将证据交给现有 ModelSpec 生成链`
- 研究结果会保存 `query.json`、`search_results.json`、`fetched_sources.json`、`evidence_summary.md`、`modeling_brief.json` 以及逐页提取内容
- 这是一个补充证据层，不会绕过当前 `family / fragment / block` 约束；对于完全超出支持范围的问题，系统仍应优先澄清或拒绝

常用环境变量：

- `WEB_RESEARCH_ENABLED=true|false`
- `WEB_SEARCH_PROVIDER=auto|bing_rss|duckduckgo_html`（推荐 `auto`，会优先尝试 `bing_rss`，失败后回退到 `duckduckgo_html`）
- `WEB_SEARCH_MAX_RESULTS=5`
- `WEB_FETCH_MAX_SOURCES=3`
- `WEB_FETCH_TIMEOUT_SEC=12`
- `WEB_CONNECT_TIMEOUT_SEC=12`（默认跟随 `WEB_FETCH_TIMEOUT_SEC`，用于控制建连超时）
- `WEB_REQUESTS_VERIFY_SSL=true|false`（是否校验证书；企业代理环境建议优先配置 CA，而不是关闭校验）
- `WEB_REQUESTS_CA_BUNDLE=/path/to/corp-ca.pem`（web research 专用 CA 路径，也兼容标准 `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE`）
- `WEB_REQUESTS_HTTP_PROXY=http://proxy-host:port`
- `WEB_REQUESTS_HTTPS_PROXY=http://proxy-host:port`
- `WEB_REQUESTS_NO_PROXY=localhost,127.0.0.1,...`
- `WEB_REQUESTS_TRUST_ENV=true|false`（是否继续信任标准环境变量 `HTTP_PROXY` / `HTTPS_PROXY` / `REQUESTS_CA_BUNDLE`）
- `WEB_FETCH_MAX_CHARS=12000`
- `WEB_RESEARCH_DIR=generated_research`

如果运行在企业网络 / HTTPS 检查环境，推荐优先这样配置：

```powershell
$env:WEB_REQUESTS_CA_BUNDLE = 'C:\certs\corp-root.pem'
$env:WEB_REQUESTS_HTTPS_PROXY = 'http://proxy.company.local:8080'
$env:WEB_REQUESTS_HTTP_PROXY = 'http://proxy.company.local:8080'
```

只有在临时排障时，才建议短时间使用：

```powershell
$env:WEB_REQUESTS_VERIFY_SSL = 'false'
```

## 继续阅读

- `项目架构说明.md`：整体分层、运行链路、模块职责、部署形态、架构边界
- `详细设计文档.md`：实现级设计细节、状态机、IR、校验、MCP 构建链
- `直出C_Cpp_DLL最小改造方案.md`：从统一 IR 直接生成 `C/C++ -> DLL` 的最小改造路径
- `部署说明.md`：部署方式、环境变量、启动与排错
- `操作手册.md`：日常使用、构建、重建索引与排错
- `当前项目RAG调用链时序图.md`：RAG 主链路时序说明

## 一句话总结

当前版本已经不是简单的“模板检索 + 文本生成”，而是一个带检索、澄清、结构化 IR、family 装配、多层校验和可选本地动态库构建链的半开放域 MATLAB 建模系统。

