# 一键 Docker Compose 部署

## 1. 当前编排包含的服务

- `redis`：多实例共享会话存储。
- `qdrant`：向量库服务。
- `ollama`：本地大模型推理服务。
- `ollama-init`：首次启动时自动拉取 `deepseek-r1:7b`。
- `kb-build`：等待 Qdrant 就绪后自动检查 collection；不存在时执行 `python main.py build --with-qdrant`。
- `app1` / `app2`：两个 API 实例，分别对外暴露 `8000` / `8001`。

默认情况下，应用容器会直接连接 Compose 内部的 `redis`、`qdrant`、`ollama`，不再依赖宿主机手动启动这些服务。

另外，Compose 现在支持把宿主机已经下载好的模型/缓存目录直接挂进容器，避免重复下载。
同时，应用基础镜像也支持通过 `.env` 中的 `PYTHON_BASE_IMAGE` 覆盖，便于切换到可访问的镜像源或本地私有仓库。

## 2. 一键启动

在项目根目录执行：

```powershell
docker compose up -d --build
```

如果当前网络无法访问 Docker Hub，可先在 `.env` 中改：

```powershell
PYTHON_BASE_IMAGE=你的可访问镜像地址
```

例如改成公司私有仓库或你本机能访问的镜像代理地址，然后再次执行：

```powershell
docker compose up -d --build
```

首次启动会比较久，因为会自动完成两件事：

- 下载 Ollama 模型 `deepseek-r1:7b`
- 下载向量化模型 `BAAI/bge-large-zh-v1.5` 并写入 Qdrant

如果你已经在宿主机下载过：

- `C:/Users/Lenovo/.ollama`
- `C:/Users/Lenovo/.cache/torch/sentence_transformers`

那么容器会直接复用，不会重复全量下载。

建议同时查看初始化日志：

```powershell
docker compose logs -f ollama-init kb-build app1 app2
```

说明：

- 如果 Qdrant 中已存在目标 collection，`kb-build` 会跳过重建，避免每次 `up` 都清空索引。
- 如果你希望强制重建 Qdrant 索引，可在启动前设置 `FORCE_REBUILD_QDRANT=1`。
- `ollama-init` 会先检查模型是否已存在；存在则跳过 `pull`。
- Ollama 目录必须挂载到 `.ollama` 根目录，而不是只挂 `manifests/.../deepseek-r1/7b`，因为运行时还需要 `blobs`。

## 3. 启动完成后的访问地址

- `http://127.0.0.1:8000/ui` -> 实例 1
- `http://127.0.0.1:8001/ui` -> 实例 2
- `http://127.0.0.1:11434` -> Ollama API
- `http://127.0.0.1:6333/collections` -> Qdrant API

## 4. 健康检查

```powershell
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8001/api/health
curl http://127.0.0.1:6333/collections
```

正常情况下：

- `app1/app2` 返回中的 `session_store_backend` 应为 `redis`
- Qdrant 应能返回 collection 列表

## 5. 常用配置项

- `OLLAMA_MODEL`：默认 `deepseek-r1:7b`
- `QDRANT_COLLECTION`：默认 `crm_filters`
- `DOCKER_OLLAMA_HOME`：默认 `C:/Users/Lenovo/.ollama`
- `DOCKER_ST_CACHE_DIR`：默认 `C:/Users/Lenovo/.cache/torch/sentence_transformers`
- `PYTHON_BASE_IMAGE`：默认 `python:3.10-slim`，可改为可访问的基础镜像地址
- `APP_IMAGE_NAME`：默认 `rag-crm-agent:local`
- `FORCE_REBUILD_QDRANT`：默认 `0`，设为 `1` 时强制重建 Qdrant collection
- `SESSION_HISTORY_SIZE`：默认 `50`
- `CHAT_HISTORY_WINDOW`：默认 `12`
- `FALLBACK_HISTORY_WINDOW`：默认 `6`
- `SESSION_TTL_SEC`：默认 `604800`

## 6. 可选：切回外部服务

如果你后续仍想复用宿主机手动启动的 Ollama 或 Qdrant，可以在启动前覆盖：

```powershell
$env:DOCKER_OLLAMA_BASE_URL = 'http://host.docker.internal:11434'
$env:DOCKER_QDRANT_HOST = 'host.docker.internal'
docker compose up -d --build
```

如果你想改成本机其他缓存目录，也可以直接改项目根目录 `.env` 中这两个变量：

```powershell
DOCKER_OLLAMA_HOME=C:/your/path/.ollama
DOCKER_ST_CACHE_DIR=C:/your/path/sentence_transformers
```

如果你也想复用宿主机 Redis：

```powershell
$env:DOCKER_REDIS_HOST = 'host.docker.internal'
docker compose up -d --build
```

## 7. 停止与清理

```powershell
docker compose down
```

如果还要删除 Redis / Qdrant / Ollama / 生成文件的数据卷：

```powershell
docker compose down -v
```
