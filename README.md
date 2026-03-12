# RAG CRM Agent 项目说明

## 项目简介

本项目是一个面向 MATLAB 建模生成的对话式智能体系统，目标是把“自然语言建模需求”转换为可执行的 MATLAB `.m` 脚本。

当前系统具备两类核心能力：

1. 普通技术问答与多轮对话
2. 根据自然语言描述生成 MATLAB 建模脚本

项目内部融合了：

- `Ollama + DeepSeek`：负责对话、任务理解、规格推断与修复
- `Qdrant + Sentence Transformers`：负责向量检索
- `BM25 + 向量检索 + 重排`：负责混合召回
- `ModelSpec` 校验链路：负责结构化建模规格校验与修复
- MATLAB 代码生成器：负责输出 `.m` 文件到 `generated_models`

---

## 当前项目状态

当前项目更适合被理解为：

- **一个受知识库约束的建模生成系统**
- **不是完全开放域的物理建模器**

也就是说，当前生成效果仍然明显依赖：

1. 知识库中是否存在相关领域文档
2. 模型目录中是否存在对应模板或可近似模板
3. 检索排序是否能把正确候选放到前面

目前系统已经支持：

- 混合检索
- 多轮对话
- 基于规则 + LLM 的任务路由
- 基于 RAG 的 `ModelSpec` 生成
- 自动修复与兜底
- MATLAB 脚本落盘

当前系统尚未完全支持：

- 真正意义上的开放域建模自动生成
- 对未知领域的自由方程组装与稳定落地
- 多对象、多阶段复杂物理系统的通用代码生成

---

## 核心能力

### 1. 对话与任务理解

- 支持普通聊天与技术问答
- 支持识别建模请求、聊天请求、澄清请求
- 支持多轮上下文

### 2. RAG 检索增强

- 本地知识索引 + Qdrant 向量库双层结构
- 检索链路包含 BM25、向量召回和规则重排
- Qdrant 不可用时可降级到本地向量或纯词法检索

### 3. 建模规格生成

- 先检索候选知识，再推断结构化 `ModelSpec`
- 通过 JSON Schema 和语义规则进行校验
- 校验失败时尝试自动修复

### 4. MATLAB 代码生成

- 根据 `model_id + parameters` 生成 MATLAB 脚本
- 生成文件写入 `generated_models`
- 支持输出文件路径、模型名称和结构化结果

---

## 当前推荐运行方式

当前项目**推荐使用混合模式**运行：

- Docker 只启动基础设施：`redis`、`qdrant`、`ollama`、`ollama-init`
- Python 应用层使用本机 `rag_crm` Conda 环境运行

推荐原因：

1. 可以复用本机已配置好的 Python 依赖环境
2. 可以复用已下载的 Ollama 与向量模型缓存
3. 可以避开当前 Docker Python 基础镜像拉取失败问题
4. 更贴合当前开发与调试方式

推荐启动命令：

```powershell
docker compose up -d redis qdrant ollama ollama-init
python main.py build --with-qdrant
python main.py api
```

启动后访问：

- `http://127.0.0.1:8000/ui`

如果只想启动基础设施并手动调试应用，也可以分别执行：

```powershell
docker compose up -d redis qdrant ollama ollama-init
python main.py build --with-qdrant
python main.py api
```

---

## 目录概览

- `main.py`：项目主入口，支持 `build / run / test / api`
- `agents/`：智能体主链路、任务路由、规格构建、规格校验、代码生成
- `knowledge_base/`：知识库数据、检索器、索引构建器、MATLAB 模板生成器
- `api/`：FastAPI 服务与 HTTP 接口
- `config/`：项目配置加载
- `database/`：历史数据库模块与 CRM 数据结构
- `generated_models/`：MATLAB 生成结果输出目录
- `docker-compose.yml`：Docker 编排文件
- `.env`：本地配置文件

---

## 项目演进方向

当前项目下一阶段的重点方向包括：

1. 扩展知识库覆盖面，降低跨领域误匹配
2. 引入更强的开放域建模 IR（中间表示）
3. 从固定模板生成逐步演进到“模型家族 + 方程组装”
4. 增加“无法可靠匹配时先澄清”的保护机制
5. 增强 MATLAB 代码生成后的验证与修复闭环

---

## 文档索引

以下文档记录了当前项目的设计、部署、操作和后续改造方向：

- `项目架构说明.md`：项目总体架构、模块职责、运行链路说明
- `详细设计文档.md`：更完整的技术设计、组件划分和运行机制说明
- `部署说明.md`：Docker Compose 部署说明与环境配置说明
- `操作手册.md`：推荐使用流程、首次启动、日常使用、重建索引与排错手册
- `知识库.md`：知识库结构、容量、索引与检索机制说明
- `任务路由.md`：任务路由器的职责、规则和判定逻辑说明
- `上下文扩容.md`：上下文缓存与会话历史机制说明
- `中间表示.md`：IR（中间表示）的基础说明
- `开放模型中间表示草案.md`：适合本项目的开放域建模 IR 草案与 `ModelSpec` 映射建议
- `改造.md`：从当前闭集模板系统演进到开放域建模生成器的思路总结
- `汇报PPT提纲.md`：项目汇报用 PPT 提纲

---

## 适用场景

本项目适合：

- MATLAB 建模脚本自动生成原型验证
- RAG + LLM + 代码生成的一体化实验
- 面向特定领域知识库的对话式建模助手
- 后续扩展为半开放域建模平台的基础底座

不建议把当前版本直接视为：

- 通用工业级开放域建模平台
- 任意物理系统都能稳定正确生成的自动建模器

---

## 快速提示

- 如果 `python main.py build --with-qdrant` 报 `ConnectError`，通常说明 Qdrant 没启动
- 如果 `python main.py api` 无法连接 LLM，先检查 `ollama` 是否已启动，以及 `.env` 中 `OLLAMA_BASE_URL` 是否正确
- 如果某个领域总被错误映射到别的模板，优先检查知识库覆盖、检索候选和重排逻辑

