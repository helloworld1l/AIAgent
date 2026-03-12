# 项目操作手册

本文档用于说明当前项目在 Docker Compose 一键部署模式下的使用方法，覆盖：

- 首次启动
- 日常使用
- 重建索引
- 排错
- 常用命令速查

适用项目目录：`D:\python\rag_crm_agent`

---

## 1. 当前运行架构

当前项目推荐使用仓库内的 `docker-compose.yml` 进行一键启动。

启动链路如下：

1. `redis` 启动：用于多实例共享会话历史。
2. `qdrant` 启动：用于向量检索。
3. `ollama` 启动：用于本地大模型推理。
4. `ollama-init` 执行：检查 `deepseek-r1:7b` 是否存在，不存在则自动拉取。
5. `kb-build` 执行：检查 Qdrant collection 是否存在，不存在则自动执行 `python main.py build --with-qdrant`。
6. `app1` / `app2` 启动：两个 API 实例，对外提供 Web UI 和接口服务。

默认访问地址：

- `http://127.0.0.1:8000/ui`：实例 1
- `http://127.0.0.1:8001/ui`：实例 2
- `http://127.0.0.1:11434`：Ollama API
- `http://127.0.0.1:6333/collections`：Qdrant API

---

## 2. 首次启动

### 2.1 启动前检查

请先确认：

1. 已安装并启动 `Docker Desktop`
2. 项目根目录下 `.env` 中的缓存路径正确
3. 如果本机网络无法访问 Docker Hub，需要提前准备可访问的 Python 基础镜像

当前默认缓存路径为：

- `DOCKER_OLLAMA_HOME=C:/Users/Lenovo/.ollama`
- `DOCKER_ST_CACHE_DIR=C:/Users/Lenovo/.cache/torch/sentence_transformers`
- `PYTHON_BASE_IMAGE=python:3.10-slim`

说明：

- `DOCKER_OLLAMA_HOME` 必须指向 `.ollama` 根目录，而不是只指向 `manifests/.../deepseek-r1/7b`
- `DOCKER_ST_CACHE_DIR` 建议指向 `sentence_transformers` 根目录，这样容器能直接复用已下载的模型缓存
- 如果 Docker Hub 网络不可达，可以把 `PYTHON_BASE_IMAGE` 改成公司私有仓库、镜像代理地址，或先离线导入后再使用

### 2.2 首次启动命令

在项目根目录执行：

```powershell
docker compose up -d --build
```

### 2.3 查看初始化过程

首次启动建议打开日志观察：

```powershell
docker compose logs -f ollama-init kb-build app1 app2
```

首次启动时可能耗时较长，原因通常是：

- Ollama 首次拉取模型
- Sentence Transformers 首次加载缓存
- Qdrant 首次建 collection

如果启动时在 `FROM python:3.10-slim` 阶段报错，通常说明 Docker 无法访问 Docker Hub，而不是项目代码本身有问题。

如果本机缓存目录中已经有模型，一般会明显更快。

### 2.4 启动成功后的检查

执行：

```powershell
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8001/api/health
curl http://127.0.0.1:6333/collections
```

成功时通常表现为：

- `app1/app2` 的返回中 `session_store_backend=redis`
- Qdrant 能返回 collection 列表

---

## 3. 日常使用

### 3.1 启动服务

日常启动：

```powershell
docker compose up -d
```

如果你修改了代码、镜像依赖或配置，建议改用：

```powershell
docker compose up -d --build
```

### 3.2 查看服务状态

```powershell
docker compose ps
```

### 3.3 查看运行日志

查看应用日志：

```powershell
docker compose logs -f app1 app2
```

查看全部关键服务日志：

```powershell
docker compose logs -f qdrant ollama kb-build app1 app2
```

### 3.4 访问系统

浏览器访问：

- `http://127.0.0.1:8000/ui`
- `http://127.0.0.1:8001/ui`

你可以直接输入：

- 普通问答，例如：`什么是卡尔曼滤波？`
- 建模请求，例如：`生成一个PID闭环模型，kp=1.5, ki=0.8, kd=0.02`

系统内部会自动执行：

1. 检索知识库
2. 调用 Ollama
3. 如果识别为建模任务，则执行规格构建、校验、代码生成
4. 返回结果给前端

### 3.5 常规停止

停止服务但保留数据：

```powershell
docker compose down
```

停止并清理数据卷：

```powershell
docker compose down -v
```

说明：

- `down` 会停止容器，但保留 Redis/Qdrant/生成文件等卷数据
- `down -v` 会删除卷，适合彻底重置环境

---

## 4. 重建索引

### 4.1 什么时候需要重建

以下情况建议重建知识库或 Qdrant 索引：

1. 你修改了 `knowledge_base/docs`
2. 你修改了知识数据或检索逻辑
3. 你更换了嵌入模型
4. 你希望刷新 Qdrant collection

### 4.2 当前默认行为

当前 `kb-build` 的逻辑是：

- 如果目标 collection 已存在，则跳过重建
- 如果 collection 不存在，则自动执行 `python main.py build --with-qdrant`

这样可以避免每次 `docker compose up` 都清空并重建索引。

### 4.3 强制重建索引

如果你需要强制重建，请先设置环境变量：

```powershell
$env:FORCE_REBUILD_QDRANT='1'
docker compose up -d --build kb-build
```

重建完成后建议重启应用实例：

```powershell
docker compose restart app1 app2
```

### 4.4 完全重置后重建

如果你想彻底清空环境再重建：

```powershell
docker compose down -v
docker compose up -d --build
```

这会删除并重建：

- Redis 数据
- Qdrant 数据
- 生成文件卷

---

## 5. 排错手册

### 5.1 `ollama-init` 一直拉模型

常见原因：

- `DOCKER_OLLAMA_HOME` 没指向 `.ollama` 根目录
- 只挂载了 `manifests/.../deepseek-r1/7b`，但没有 `blobs`

排查建议：

```powershell
docker compose logs -f ollama-init
```

确认 `.env` 中：

```powershell
DOCKER_OLLAMA_HOME=C:/Users/Lenovo/.ollama
```

### 5.2 向量模型重复下载

常见原因：

- `DOCKER_ST_CACHE_DIR` 没有指向 `sentence_transformers` 根目录
- 挂载路径错误，容器内没有读到已存在缓存

建议检查 `.env`：

```powershell
DOCKER_ST_CACHE_DIR=C:/Users/Lenovo/.cache/torch/sentence_transformers
```

### 5.3 `kb-build` 没有成功建库

排查步骤：

```powershell
docker compose logs -f kb-build
curl http://127.0.0.1:6333/collections
```

重点检查：

- Qdrant 是否正常启动
- `QDRANT_COLLECTION` 是否配置正确
- 嵌入模型是否能正常加载

### 5.4 `app1/app2` 无法启动

排查步骤：

```powershell
docker compose ps
docker compose logs -f app1 app2
```

重点检查：

- `kb-build` 是否成功退出
- `ollama-init` 是否成功退出
- API 端口是否被占用

### 5.5 端口冲突

当前默认会使用这些端口：

- `8000`
- `8001`
- `11434`
- `6333`

如果有冲突，请先关闭占用进程，或修改 `docker-compose.yml` 端口映射。

### 5.6 验证 Compose 配置是否正确

在修改 `.env` 或 `docker-compose.yml` 后，可以先执行：

```powershell
docker compose config
```

这个命令可以帮助你确认：

- 变量是否正确展开
- 挂载路径是否正确生效
- 服务依赖关系是否正确

### 5.7 `python:3.10-slim` 拉取失败

你看到类似下面的错误时：

```text
failed to fetch anonymous token
auth.docker.io/token
connectex: A connection attempt failed
```

说明是 Docker 访问 Docker Hub 失败。

当前项目里这一步发生在应用镜像构建阶段，因为 `Dockerfile` 需要基于 Python 基础镜像构建 `app1/app2/kb-build`。

处理方式有三种：

1. 修改 `.env` 中的 `PYTHON_BASE_IMAGE` 为你能访问的镜像源地址
2. 在其他能联网的机器上先拉取并导出 `python:3.10-slim`，再拷回本机 `docker load`
3. 使用公司内部 Docker Registry，并把 `PYTHON_BASE_IMAGE` 指向内部地址

如果你已经把本机导入的镜像重新打了标签，也可以直接把 `.env` 中的 `PYTHON_BASE_IMAGE` 改成那个本地标签。

---

## 6. 常用命令速查

### 6.1 首次启动

```powershell
docker compose up -d --build
```

### 6.2 查看初始化日志

```powershell
docker compose logs -f ollama-init kb-build app1 app2
```

### 6.3 日常启动

```powershell
docker compose up -d
```

### 6.4 重建镜像并启动

```powershell
docker compose up -d --build
```

### 6.5 强制重建 Qdrant 索引

```powershell
$env:FORCE_REBUILD_QDRANT='1'
docker compose up -d --build kb-build
docker compose restart app1 app2
```

### 6.6 查看应用日志

```powershell
docker compose logs -f app1 app2
```

### 6.7 查看全部服务状态

```powershell
docker compose ps
```

### 6.8 停止服务

```powershell
docker compose down
```

### 6.9 停止并清理卷数据

```powershell
docker compose down -v
```

### 6.10 校验 Compose 配置

```powershell
docker compose config
```

---

## 7. 本地非 Docker 模式（可选）

虽然当前推荐使用 Docker Compose，但项目仍保留本地入口。

### 7.1 本地构建知识库

```powershell
python main.py build --with-qdrant
```

### 7.2 本地启动 API

```powershell
python main.py api
```

### 7.3 本地交互模式

```powershell
python main.py run
```

说明：

- 本地模式适合开发调试
- 正式使用仍建议优先采用 Compose 模式，以保持依赖、缓存、模型和服务的一致性
