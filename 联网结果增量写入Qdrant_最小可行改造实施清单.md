# 联网结果增量写入 Qdrant 最小可行改造实施清单

## 1. 目标

本清单用于指导当前项目把“联网研究”结果从**仅本地结果包落盘**，扩展为：

1. 继续保留 `generated_research/` 本地结果包，便于追溯与调试。
2. 将成功抓取的网页证据**增量写入独立 Qdrant collection**。
3. 在后续用户再次触发“联网 / 最新 / 从网上查 / 当前”类请求时，允许从该 collection 检索历史证据并参与回答或生成。

本方案遵循“最小可行改造”原则：

- 不改动当前主知识库构建模式 `main.py build --with-qdrant`。
- 不把联网结果混写到现有 `QDRANT_COLLECTION=crm_filters`。
- 不把临时网页内容写回 `knowledge_base/matlab_knowledge_index.json`。
- 先实现“可写入、可检索、可过滤、可降级”，再考虑复杂 rerank、跨会话共享策略和后台清理任务。

---

## 2. 当前现状

### 2.1 当前联网研究链路

- `agents/crm_agent.py:1163`：`CRMAgent._perform_web_research()` 调用 Web Research 工具。
- `tools/mcp_web_research/research_tool.py:142`：为本次联网研究创建 `bundle_dir`。
- `tools/mcp_web_research/research_tool.py:155`：写入 `query.json`。
- `tools/mcp_web_research/research_tool.py:178`：写入 `search_results.json`。
- `tools/mcp_web_research/research_tool.py:200`：写入 `fetched_sources.json`。
- `tools/mcp_web_research/research_tool.py:206`：写入 `evidence_summary.md`。
- `tools/mcp_web_research/research_tool.py:221`：写入 `modeling_brief.json`。
- `tools/mcp_web_research/research_tool.py:239`：写入 `result.json`。
- `tools/mcp_web_research/research_tool.py:487`：构造运行时 `docs`，供当前请求直接使用。

### 2.2 当前 Qdrant 写入链路

- `knowledge_base/builder.py:213`：`build_qdrant_index()` 是当前唯一主写入路径。
- `knowledge_base/builder.py:223`：构建前会先删 collection。
- `knowledge_base/builder.py:228`：重建 collection。
- `knowledge_base/builder.py:250`：执行 `upsert()`。

### 2.3 当前不能直接复用联网证据的原因

1. 联网研究结果只落本地结果包，不落 Qdrant。
2. `knowledge_base/rag_retriever.py` 的向量检索假设 Qdrant 命中的点都能在本地 `_doc_by_id` 找到；若只写 Qdrant 而不更新本地索引，会被过滤掉。
3. 现有主 collection 会被 `build --with-qdrant` 重建，因此联网证据不能混写到 `crm_filters`。

---

## 3. 目标改造后的数据流

建议最终形成两层落盘：

### 3.1 本地结果包层

保持不变，继续保存：

- `query.json`
- `search_results.json`
- `fetched_sources.json`
- `evidence_summary.md`
- `modeling_brief.json`
- `result.json`
- `sources/*.md`

### 3.2 Qdrant 证据层

新增独立 collection：

- `WEB_RESEARCH_QDRANT_COLLECTION=web_research_evidence`

存储对象不是最终摘要，而是**成功抓取网页的分块证据**。

每个 point 的 payload 统一包含以下字段：

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `source` | `str` | 固定值：`web_research` |
| `scope` | `str` | `session` 或 `global`，MVP 默认 `session` |
| `session_id` | `str` | 触发该研究的会话 ID |
| `query` | `str` | 原始研究 query |
| `title` | `str` | 搜索结果标题 |
| `url` | `str` | 原始来源 URL |
| `domain` | `str` | URL 域名 |
| `saved_path` | `str` | 本地保存的 `sources/*.md` 路径 |
| `chunk_index` | `int` | 第几个 chunk，从 1 开始 |
| `chunk_count` | `int` | 该 source 共切成多少块 |
| `content_hash` | `str` | 归一化正文 hash，用于幂等 |
| `fetched_at` | `str` | ISO 时间戳 |
| `expires_at` | `str` | ISO 时间戳，用于软 TTL |
| `text` | `str` | 当前 chunk 的原始文本 |

---

## 4. 新增配置项

修改文件：`config/settings.py`

### 4.1 `DEFAULTS` 新增字段

建议在 `DEFAULTS` 中新增以下 key：

```python
"WEB_RESEARCH_QDRANT_ENABLED": False,
"WEB_RESEARCH_QDRANT_COLLECTION": "web_research_evidence",
"WEB_RESEARCH_QDRANT_SCOPE": "session",
"WEB_RESEARCH_QDRANT_RETENTION_DAYS": 7,
"WEB_RESEARCH_QDRANT_MAX_CHUNK_CHARS": 1000,
"WEB_RESEARCH_QDRANT_CHUNK_OVERLAP": 120,
"WEB_RESEARCH_QDRANT_TOP_K": 6,
"WEB_RESEARCH_QDRANT_CLEANUP_ON_WRITE": True,
```

### 4.2 `Settings` / `FallbackSettings` 同步字段

在两套 `Settings` 定义中同步加入：

```python
WEB_RESEARCH_QDRANT_ENABLED: bool
WEB_RESEARCH_QDRANT_COLLECTION: str
WEB_RESEARCH_QDRANT_SCOPE: str
WEB_RESEARCH_QDRANT_RETENTION_DAYS: int
WEB_RESEARCH_QDRANT_MAX_CHUNK_CHARS: int
WEB_RESEARCH_QDRANT_CHUNK_OVERLAP: int
WEB_RESEARCH_QDRANT_TOP_K: int
WEB_RESEARCH_QDRANT_CLEANUP_ON_WRITE: bool
```

### 4.3 `.env` 建议示例

```env
WEB_RESEARCH_QDRANT_ENABLED=true
WEB_RESEARCH_QDRANT_COLLECTION=web_research_evidence
WEB_RESEARCH_QDRANT_SCOPE=session
WEB_RESEARCH_QDRANT_RETENTION_DAYS=7
WEB_RESEARCH_QDRANT_MAX_CHUNK_CHARS=1000
WEB_RESEARCH_QDRANT_CHUNK_OVERLAP=120
WEB_RESEARCH_QDRANT_TOP_K=6
WEB_RESEARCH_QDRANT_CLEANUP_ON_WRITE=true
```

---

## 5. 新增文件一：Qdrant 写入器

新增文件：`tools/mcp_web_research/qdrant_indexer.py`

### 5.1 新增类名

```python
class WebResearchQdrantIndexer:
```

### 5.2 类职责

负责把成功抓取的网页证据分块、向量化并写入独立 Qdrant collection。

### 5.3 建议构造函数

```python
def __init__(self) -> None:
```

初始化内容建议包括：

- 读取 `settings.WEB_RESEARCH_QDRANT_ENABLED`
- 读取 `settings.WEB_RESEARCH_QDRANT_COLLECTION`
- 读取 `settings.QDRANT_HOST` / `settings.QDRANT_PORT`
- 延迟初始化 `QdrantClient`
- 延迟初始化 `SentenceTransformer`
- 保存 `embedding_dim`

### 5.4 建议公开方法

#### 5.4.1 `index_sources`

```python
def index_sources(
    self,
    *,
    query: str,
    session_id: str,
    fetched_sources: list[dict[str, object]],
    scope: str | None = None,
) -> dict[str, object]:
```

职责：

- 过滤 `status == "success"` 的来源
- 将每个来源正文切块
- 生成 embeddings
- 幂等 upsert 到 `WEB_RESEARCH_QDRANT_COLLECTION`
- 按配置执行过期清理
- 返回结构化写入结果

返回字段建议固定为：

```python
{
    "enabled": bool,
    "status": "disabled" | "success" | "failed",
    "collection": str,
    "scope": str,
    "sources_total": int,
    "sources_indexed": int,
    "points_upserted": int,
    "cleanup_deleted": int,
    "error": str,
}
```

#### 5.4.2 `cleanup_expired`

```python
def cleanup_expired(self, *, now_iso: str | None = None) -> int:
```

职责：

- 删除 `expires_at < now` 的点
- 返回删除条数

#### 5.4.3 `ensure_collection`

```python
def ensure_collection(self) -> None:
```

职责：

- 若 collection 不存在则创建
- 向量维度来自 embedding model
- `distance` 统一使用 `COSINE`

### 5.5 建议私有方法

#### 5.5.1 `_ensure_backend`

```python
def _ensure_backend(self) -> bool:
```

职责：

- 惰性初始化 `QdrantClient`
- 惰性初始化 `SentenceTransformer`
- 初始化失败时记录错误，返回 `False`

#### 5.5.2 `_chunk_text`

```python
def _chunk_text(self, text: str) -> list[str]:
```

职责：

- 参考 `knowledge_base/document_loader.py` 的切块思路
- 使用 `WEB_RESEARCH_QDRANT_MAX_CHUNK_CHARS`
- 使用 `WEB_RESEARCH_QDRANT_CHUNK_OVERLAP`

#### 5.5.3 `_normalize_text`

```python
def _normalize_text(self, text: str) -> str:
```

职责：

- 去除多余空白
- 统一换行
- 用于 hash 与幂等比较

#### 5.5.4 `_build_point_id`

```python
def _build_point_id(
    self,
    *,
    url: str,
    content_hash: str,
    chunk_index: int,
) -> int:
```

建议实现：

- 使用 `sha1(f"{url}\n{content_hash}\n{chunk_index}")`
- 取后 8 字节转为无符号 64 位整数
- 避免使用随机 UUID，保证重复写入时可覆盖旧点

#### 5.5.5 `_build_payload`

```python
def _build_payload(
    self,
    *,
    query: str,
    session_id: str,
    scope: str,
    source_item: dict[str, object],
    text: str,
    chunk_index: int,
    chunk_count: int,
    fetched_at: str,
    expires_at: str,
    content_hash: str,
) -> dict[str, object]:
```

职责：

- 统一生成 point payload
- 保证字段名固定，供检索端直接复用

#### 5.5.6 `_extract_indexable_text`

```python
def _extract_indexable_text(self, source_item: dict[str, object]) -> str:
```

职责：

- 优先读取 `source_item["text"]`
- 为空时退化到 `source_item["excerpt"]`
- 都为空则不写入

### 5.6 Qdrant point 的推荐 payload 结构

```python
{
    "source": "web_research",
    "scope": "session",
    "session_id": session_id,
    "query": query,
    "title": title,
    "url": url,
    "domain": domain,
    "saved_path": saved_path,
    "chunk_index": chunk_index,
    "chunk_count": chunk_count,
    "content_hash": content_hash,
    "fetched_at": fetched_at,
    "expires_at": expires_at,
    "text": chunk_text,
}
```

---

## 6. 新增文件二：历史联网证据检索器

新增文件：`knowledge_base/web_evidence_retriever.py`

### 6.1 新增类名

```python
class WebEvidenceRetriever:
```

### 6.2 类职责

负责从 `WEB_RESEARCH_QDRANT_COLLECTION` 中检索历史联网证据，并转换成当前 agent 可直接拼接的 `docs` 结构。

### 6.3 建议构造函数

```python
def __init__(self) -> None:
```

初始化内容建议包括：

- 读取 `WEB_RESEARCH_QDRANT_ENABLED`
- 读取 `WEB_RESEARCH_QDRANT_COLLECTION`
- 读取 `WEB_RESEARCH_QDRANT_TOP_K`
- 延迟初始化 `QdrantClient`
- 延迟初始化 `SentenceTransformer`

### 6.4 建议公开方法

#### 6.4.1 `retrieve`

```python
def retrieve(
    self,
    *,
    query: str,
    session_id: str,
    top_k: int | None = None,
) -> list[dict[str, object]]:
```

职责：

- 为 query 生成 embedding
- 在 `web_research_evidence` 中做向量查询
- 过滤过期点
- 默认仅取当前 `session_id`
- 将命中结果转换为标准 `docs`

返回的单条 doc 建议统一为：

```python
{
    "id": f"web_qdrant_{point_id}",
    "score": round(score, 4),
    "text": f"web_source: {title}; url: {url}; content: {text[:1800]}",
    "payload": {
        "source": "web_research_qdrant",
        "model_id": "",
        "template_family": "",
        "title": title,
        "url": url,
        "domain": domain,
        "saved_path": saved_path,
        "session_id": session_id,
        "scope": scope,
        "collection": collection,
        "chunk_index": chunk_index,
        "content_hash": content_hash,
    },
}
```

### 6.5 建议私有方法

#### 6.5.1 `_ensure_backend`

```python
def _ensure_backend(self) -> bool:
```

#### 6.5.2 `_build_filter`

```python
def _build_filter(self, *, session_id: str):
```

过滤规则建议：

- `expires_at >= now`
- `source == "web_research"`
- `scope == "session"` 时必须匹配 `session_id`
- 如后续启用 `global`，可扩展为：`(scope == "global") OR (scope == "session" AND session_id == 当前会话)`

#### 6.5.3 `_payload_to_doc`

```python
def _payload_to_doc(self, *, point_id: object, score: float, payload: dict[str, object]) -> dict[str, object]:
```

职责：

- 把 Qdrant payload 还原为运行时 doc
- 保持与 `tools/mcp_web_research/research_tool.py:487` 产出的结构兼容

---

## 7. 修改文件一：`tools/mcp_web_research/research_tool.py`

### 7.1 `WebResearchToolchain.__init__`

新增属性：

```python
self.qdrant_indexer = WebResearchQdrantIndexer()
```

### 7.2 在成功抓取后追加 Qdrant 写入

建议插入位置：

- 在 `fetched_sources` 和 `evidence_docs` 构造完成之后
- 在 `result` / `modeling_brief` 写盘之前

建议新增代码逻辑：

```python
qdrant_index_result = self.qdrant_indexer.index_sources(
    query=normalized_query,
    session_id=session_id,
    fetched_sources=fetched_sources,
)
```

### 7.3 `result` 新增字段

建议在返回结果中增加统一嵌套对象：

```python
"qdrant_index": {
    "enabled": bool,
    "status": "disabled" | "success" | "failed",
    "collection": str,
    "scope": str,
    "sources_total": int,
    "sources_indexed": int,
    "points_upserted": int,
    "cleanup_deleted": int,
    "error": str,
}
```

这样：

- `result.json` 可直接追踪是否写入成功
- API 层可直接透出
- 失败可降级，不中断主流程

### 7.4 `modeling_brief.json` 新增字段

建议新增：

```python
"qdrant_index": {
    "status": str,
    "collection": str,
    "scope": str,
    "points_upserted": int,
}
```

### 7.5 异常处理要求

- Qdrant 写入失败时，联网研究主流程仍返回 `status="success"`
- 但 `qdrant_index.status` 必须为 `failed`
- `qdrant_index.error` 必须记录异常文本

---

## 8. 修改文件二：`agents/crm_agent.py`

### 8.1 在 `CRMAgent.__init__` 中新增依赖

建议新增：

```python
self.web_evidence_retriever = WebEvidenceRetriever()
```

### 8.2 新增方法：读取历史联网证据

```python
def _retrieve_persisted_web_evidence(self, text: str, session_id: str) -> list[dict[str, object]]:
```

职责：

- 调用 `self.web_evidence_retriever.retrieve(query=text, session_id=session_id)`
- 捕获异常并降级为空列表

### 8.3 替换当前简单合并逻辑

当前只有：

```python
def _merge_web_research_docs(self, base_docs, research_result):
```

建议保留该方法，但再新增更通用方法：

```python
def _merge_runtime_docs(self, *doc_groups: list[dict[str, object]]) -> list[dict[str, object]]:
```

职责：

- 按优先级合并多组 docs
- 去重规则优先用 `payload.url`，其次 `id`
- 合并顺序固定为：
  1. 当前请求刚抓到的 `research_result["docs"]`
  2. Qdrant 历史联网证据
  3. 原始本地知识库检索结果

### 8.4 修改两个接入点

#### 8.4.1 聊天链路

位置：`agents/crm_agent.py:550` 附近

建议流程：

1. 若 `request_web_research=True`，先执行 `_perform_web_research()`。
2. 再执行 `_retrieve_persisted_web_evidence()`。
3. 使用 `_merge_runtime_docs()` 得到 `effective_retrieved_docs`。

#### 8.4.2 生成链路

位置：`agents/crm_agent.py:675` 附近

建议同样改为：

1. `research_result = _perform_web_research(...)`
2. `persisted_web_docs = _retrieve_persisted_web_evidence(...)`
3. `effective_retrieved_docs = _merge_runtime_docs(...)`

### 8.5 返回数据新增字段

建议在 API 返回的 `data` 中新增：

```python
"persisted_web_evidence_count": int,
"web_research_qdrant_index": dict,
```

对应含义：

- `persisted_web_evidence_count`：本次从 Qdrant 历史证据库取回的条数
- `web_research_qdrant_index`：本次联网研究写入状态，直接透传 `research_result["qdrant_index"]`

---

## 9. 是否修改 `knowledge_base/rag_retriever.py`

### 9.1 本轮 MVP 结论

**不建议在本轮直接把历史联网证据并入 `knowledge_base/rag_retriever.py` 主检索器。**

原因：

1. 当前主检索器依赖 `_doc_by_id`，强绑定本地文档表。
2. 直接把 Qdrant 外部点塞进该链路，需要改动的兼容逻辑更多。
3. MVP 只需增加一个独立的 `WebEvidenceRetriever`，在 `CRMAgent` 层进行 merge 即可完成闭环。

### 9.2 后续可选增强

后续若需要统一融合检索，再考虑：

- 在 `knowledge_base/rag_retriever.py` 中引入多源检索接口
- 将 `web_research_evidence` 作为辅助召回源
- 在 rerank 层加入 freshness 权重

---

## 10. 测试文件改造清单

### 10.1 新增测试：`tests/test_web_research_qdrant_indexer.py`

建议覆盖：

#### 用例一：禁用时正常降级

```python
def test_index_sources_returns_disabled_when_feature_off(self) -> None:
```

断言：

- `status == "disabled"`
- `points_upserted == 0`
- 不抛异常

#### 用例二：稳定 point id

```python
def test_build_point_id_is_stable_for_same_url_and_chunk(self) -> None:
```

断言：

- 同 URL、同内容 hash、同 chunk index 生成同一个 point id

#### 用例三：正确切块并生成 payload

```python
def test_index_sources_builds_expected_payload_fields(self) -> None:
```

断言 payload 至少包含：

- `source`
- `scope`
- `session_id`
- `query`
- `url`
- `saved_path`
- `chunk_index`
- `chunk_count`
- `content_hash`
- `fetched_at`
- `expires_at`
- `text`

### 10.2 新增测试：`tests/test_web_evidence_retriever.py`

建议覆盖：

#### 用例一：按 `session_id` 过滤

```python
def test_retrieve_filters_by_session_id(self) -> None:
```

#### 用例二：结果转换为标准 `docs`

```python
def test_payload_to_doc_returns_agent_compatible_shape(self) -> None:
```

#### 用例三：过期数据不返回

```python
def test_retrieve_skips_expired_points(self) -> None:
```

### 10.3 修改测试：`tests/test_web_research_mcp.py`

新增断言：

```python
self.assertIn("qdrant_index", result)
self.assertIn(result["qdrant_index"]["status"], {"disabled", "success", "failed"})
```

### 10.4 修改测试：`tests/test_crm_agent_chat_web_research.py`

新增用例：

```python
def test_chat_explicit_web_research_merges_current_then_persisted_then_kb(self) -> None:
```

断言 merge 顺序：

1. 当前联网实时证据
2. 历史 Qdrant 证据
3. 原始知识库结果

---

## 11. 具体实施顺序

建议按以下顺序开发，避免返工：

### 第 1 步：加配置

- 修改 `config/settings.py`
- 补 `.env` 示例

交付判定：

- 本地可读取新增配置字段

### 第 2 步：完成写入器

- 新增 `tools/mcp_web_research/qdrant_indexer.py`
- 完成：初始化、建 collection、切块、幂等 point id、upsert、cleanup

交付判定：

- 单元测试可验证 `index_sources()` 返回结构正确

### 第 3 步：接入 Web Research 工具链

- 修改 `tools/mcp_web_research/research_tool.py`
- 把 `qdrant_index` 写入 `result.json` 和 `modeling_brief.json`

交付判定：

- 一次联网研究结束后，本地 `result.json` 可看到 `qdrant_index`

### 第 4 步：完成历史证据检索器

- 新增 `knowledge_base/web_evidence_retriever.py`
- 完成：embedding、Qdrant query、session 过滤、doc 转换

交付判定：

- 给定 mock hit，可转换成标准 `docs`

### 第 5 步：接入 `CRMAgent`

- 修改 `agents/crm_agent.py`
- 在 `request_web_research=True` 时，合并：当前证据、历史证据、本地知识库

交付判定：

- 聊天链路与生成链路都可拿到历史联网证据

### 第 6 步：补测试

- 新增 2 个测试文件
- 修改 2 个现有测试文件

交付判定：

- 新老链路不回归

---

## 12. 返回对象字段定义建议

### 12.1 `research_result` 新增字段

建议统一为：

```python
{
    "status": "success",
    "query": str,
    "bundle_dir": str,
    "summary_path": str,
    "brief_path": str,
    "provider": str,
    "provider_config": str,
    "search_attempts": list,
    "search_providers_used": list,
    "search_results": list,
    "sources": list,
    "docs": list,
    "summary": str,
    "qdrant_index": {
        "enabled": bool,
        "status": str,
        "collection": str,
        "scope": str,
        "sources_total": int,
        "sources_indexed": int,
        "points_upserted": int,
        "cleanup_deleted": int,
        "error": str,
    },
}
```

### 12.2 `CRMAgent.chat()` / 生成返回的 `data` 建议新增字段

```python
{
    "request_web_research": bool,
    "web_research_status": str,
    "web_research_bundle_dir": str,
    "web_research_summary_path": str,
    "web_research_brief_path": str,
    "web_research_sources": list,
    "web_research_qdrant_index": dict,
    "persisted_web_evidence_count": int,
}
```

---

## 13. MVP 范围内明确不做的事情

本轮不做：

1. 不把联网证据混入 `crm_filters`。
2. 不修改 `main.py build --with-qdrant` 的主知识库构建行为。
3. 不引入复杂的多路 reranker。
4. 不做后台定时清理任务，只做“写入时顺手清理”。
5. 不做全局共享知识的人工审核流程。

---

## 14. 风险与规避

### 风险一：Qdrant 写入失败影响主流程

规避方式：

- 所有写入逻辑必须降级
- `qdrant_index.status=failed`，但联网研究主状态仍可为 `success`

### 风险二：历史网页污染当前回答

规避方式：

- MVP 默认 `scope=session`
- 只在 `request_web_research=True` 时启用历史证据检索

### 风险三：重复抓取导致点无限增长

规避方式：

- 使用稳定 point id
- 使用 `content_hash`
- 写入时执行 `cleanup_expired()`

---

## 15. 建议的最终文件改动列表

### 新增文件

- `tools/mcp_web_research/qdrant_indexer.py`
- `knowledge_base/web_evidence_retriever.py`
- `tests/test_web_research_qdrant_indexer.py`
- `tests/test_web_evidence_retriever.py`

### 修改文件

- `config/settings.py`
- `tools/mcp_web_research/research_tool.py`
- `agents/crm_agent.py`
- `tests/test_web_research_mcp.py`
- `tests/test_crm_agent_chat_web_research.py`
- `README.md`

---

## 16. 开工优先级建议

如果按“最快形成闭环”排序，建议优先级如下：

1. `config/settings.py`
2. `tools/mcp_web_research/qdrant_indexer.py`
3. `tools/mcp_web_research/research_tool.py`
4. `knowledge_base/web_evidence_retriever.py`
5. `agents/crm_agent.py`
6. `tests/*`
7. `README.md`

---

## 17. 一句话总结

最小可行方案的核心是：**保留当前 `generated_research/` 结果包不变，新增独立 `web_research_evidence` collection 保存网页证据分块，再通过独立 `WebEvidenceRetriever` 在 `CRMAgent` 层做增量合并。**
