# MATLAB RAG 对话智能体：汇报PPT精简提纲（10页内）

## 第1页 项目背景与目标
- 背景：传统 MATLAB 建模依赖人工经验，需求理解和脚本落地效率低
- 目标：构建“对话输入 -> 自动生成 `.m` 文件”的智能体系统
- 核心价值：降低建模门槛、提升交付速度、沉淀可复用知识
- 建议图示：问题痛点到目标能力的对照图

## 第2页 方案总览（一句话架构）
- 一句话：`Web UI + FastAPI + Agent + 混合RAG + Ollama + MATLAB CodeGen`
- 输入：自然语言建模需求
- 输出：结构化回复 + 可执行 `.m` 文件
- 特点：统一对话入口、自动路由、可追踪可降级
- 建议图示：端到端流程图

## 第3页 系统架构分层
- 表现层：`web_ui.html`
- 服务层：`api/server.py`
- 智能体层：`agents/crm_agent.py`
- 知识与检索层：`knowledge_base/*` + Qdrant
- 生成层：`matlab_codegen -> matlab_generator`
- 建议图示：分层架构框图（5层）

## 第4页 核心链路：从输入到输出
- Step1：前端调用 `POST /api/chat`
- Step2：Agent 检索知识并做任务规划（chat / matlab_generation）
- Step3：建模任务进入 `ModelSpec` 生成与校验
- Step4：通过后渲染并落盘 `.m`
- Step5：返回脚本、文件路径、检索证据、修复轨迹
- 建议图示：时序图

## 第5页 混合检索设计（命中率核心）
- 召回：BM25（关键词）+ 向量检索（Qdrant）
- 融合：权重融合 + 规则重排（关键词/别名/model_id）
- 降级：Qdrant不可用 -> local向量 -> BM25
- 结果：提高“方向性问题”命中能力
- 建议图示：三段检索漏斗图

## 第6页 ModelSpec 强约束与自动修复
- 统一 JSON Schema 强约束，避免“自由文本”不可执行
- 双重校验：Schema校验 + 语义校验（参数/维度/范围）
- 自动修复循环：LLM修复 -> 再校验（可配置轮次）
- 兜底：启发式规格，保证可用性
- 建议图示：闭环校验流程图

## 第7页 工具链与运行环境
- 核心：Python、FastAPI、Uvicorn、Requests
- 检索：Qdrant、Sentence-Transformers、Torch
- LLM：Ollama + deepseek-r1:7b
- 配置：`.env`（模型、Qdrant、检索权重、修复轮次）
- 建议图示：技术栈清单图

## 第8页 硬件与部署建议
- 最低：4核CPU / 16GB RAM / 无GPU可运行
- 推荐：8核+ / 32GB / 12GB显存GPU
- 生产：16核+ / 64GB / 24GB显存GPU
- 部署流程：安装依赖 -> 构建索引 -> 启动API -> UI访问
- 建议图示：配置分级表（最低/推荐/生产）

## 第9页 当前效果与示例结果
- 示例输入：“生成一个火箭发射模型”
- 示例输出：`rocket_launch_1d_*.m` 文件成功生成
- 日志证据：Qdrant `points/search 200`、`POST /api/chat 200`
- 可观测字段：`planner`、`retrieved_knowledge`、`repair_trace`
- 建议图示：输入-输出对比截图

## 第10页 风险、规划与落地计划
- 风险：依赖版本兼容、知识覆盖不足、LLM不稳定输出
- 对策：兼容模式、知识扩充、评测集回归
- 下一步：
1. 扩展Qdrant文档类型与领域标签
2. 建立检索评测集（Hit@1/Recall@5）
3. 引入重排模型与监控看板
- 建议图示：里程碑路线图（短中期）

---

## 附：汇报时可直接引用的指标建议
- 生成成功率（`.m` 文件落地成功占比）
- 首次命中率（Top1 模型匹配正确率）
- 平均响应时延（聊天/建模分别统计）
- 自动修复触发率与修复成功率

