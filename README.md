› 如何扩展Qdrant,使其内容更丰富，使对话检索更容易命中某个方向的知识


• 可以从这 6 个层面扩展，效果最直接：

  1. 扩充入库文档类型（不只 model + example）

  - 增加：theory（原理）、equation（方程）、param_guide（参数范围）、failure_case（常见错误）、repair_case（修复示例）、
    code_pattern（代码片段）。
  - 同一模型拆成多条小文档（200-500字）比一条大文档更容易命中。

  2. 丰富 payload 元数据（用于定向过滤）

  - 建议字段：model_id, doc_type, domain, intent, tags, difficulty, language, quality_score, version。
  - 检索时先按 domain/intent 过滤，再做向量检索，命中率会明显提高。

  3. 做“同义词/别名”扩展

  - 比如“火箭发射/弹道/推力飞行/上升段”映射到同一方向。
  - 在查询前做 query expansion，再送 Qdrant + BM25。

  4. 增加“需求 -> ModelSpec -> .m脚本”三元组样本

  - 把真实对话样本沉淀为高质量知识条目，特别是你关心的方向（如火箭、控制、滤波）。
  - 这类样本对生成任务最有效。

  5. 引入重排时的方向偏置

  - 你已有重排层，可加“方向加权”：若规划器判定 aerospace，对该方向文档加分。
  - 这样可避免被通用控制模型抢走 Top1。

  6. 建立评测集并闭环优化

  - 准备 50-100 条测试问题，标注期望 model_id。
  - 持续看 Hit@1 / Recall@5，只要某方向低于阈值就补该方向数据。

  你这个项目里，优先改这3处最有效：

  - matlab_model_data.py 扩模型知识字段
  - builder.py 生成多类型文档并写入Qdrant payload
  - rag_retriever.py 加 filter + 方向加权 rerank

  做完后重建：

  1. python main.py build --with-qdrant
  2. python main.py api