# KnowledgePilot V1.3.0 消融总结与发布验收

**V1.3 RC Test Gate: PASS**

检索模块和历史实验结果核验通过。初次 RC 发现的测试进程污染已通过最小隔离修复关闭：完整套件正常单次 Pytest 收集与执行为435 Passed / 0 Failed / 1 Skipped。用户已授权正式提交与v1.3.0 Annotated Tag；发布Commit与远端同步状态以Git实际引用为准。本文保留初次失败作为历史证据，不改写实验数据。

## 本版能力与实验背景

V1.3 提供 Evidence Collector、CaseEvidence 状态转换、RunReport Schema、RunProvenance 文件/Git/Python 观测、独占 JSON Writer、独立 Dense/BM25 编排、中文字符与技术标识符 Tokenizer，以及 Hybrid RRF 和故障降级。稳定 RAG Pipeline、Agent Loop、FastAPI 和 V1.2 评分器未改造。

BM25 用于补充 Dense 对精确技术标识符的匹配；Hybrid 保留语义和词面两路候选；RRF 根据名次融合，避免直接相加不同尺度分数。这些是设计动机，不是普遍效果提升的证明。

## 核验范围与统一配置

- 本轮直接读取四份原始 JSON，用冻结 Dataset 标签重算每条 Case 的 Hit/Recall/RR 及汇总，并复核候选文本 SHA-256。未重新运行模型，也未修改原报告。
- Dataset v1、Corpus corpus_v1；16 条 Retrieval Case，6 篇文档、19 个原始 Chunk；最终 Top-K=3。Corpus 文本、边界、document_id/chunk_index 不变。
- Dense：bge-m3:latest，1024 维，Chroma knowledge_pilot_docs/cosine；similarity=1-distance。原报告模型 digest 与 Manifest 一致。
- BM25：k1=1.2，b=0.75；IDF=ln(1+(N-df+0.5)/(df+0.5))。Tokenizer technical_identifier_cjk_unigram_bigram_v1/version1，小写技术标识符和 API 路径保留，连续中文生成字符 unigram 和相邻 bigram；不是中文词级分词。
- Hybrid：双路分别实际检索 Top-3 或 Top-5，再取融合 Top-3；RRF 常数60；缺失一路贡献0；按(document_id,chunk_index)去重。并列按document_id及数值chunk_index升序。
- 指标复用 rag_evaluator/rag_metrics；分母为评分成功且该指标非None的Case数；四份报告均16成功、0检索失败、0评分失败。两份Hybrid均16 full_hybrid、0降级、0空结果。
- Dense候选的similarity、BM25候选的score/bm25_okapi、Hybrid候选的score/rrf分别保留，原始排名和两路分项贡献可追溯。RRF不是cosine similarity。

## 指标与相对 Dense 差值

以下差值为绝对指标差（不是相对百分比）；完整精度保留在 JSON 中。
- **Dense**：Hit@3=1.000000；Mean Recall@3=0.822917；MRR@3=0.968750。
  相对Dense差值：+0.000000 / +0.000000 / +0.000000。
- **BM25**：Hit@3=0.937500；Mean Recall@3=0.732292；MRR@3=0.906250。
  相对Dense差值：-0.062500 / -0.090625 / -0.062500。
- **Hybrid RRF Depth-3**：Hit@3=1.000000；Mean Recall@3=0.794792；MRR@3=0.927083。
  相对Dense差值：+0.000000 / -0.028125 / -0.041667。
- **Hybrid RRF Depth-5**：Hit@3=1.000000；Mean Recall@3=0.794792；MRR@3=0.968750。
  相对Dense差值：+0.000000 / -0.028125 / +0.000000。

Dense 整体指标最好或持平。Hybrid Depth-5 的 Hit 和 MRR 与 Dense 持平，Mean Recall 低0.028125；Hybrid 未全面优于 Dense。建议保持现有 Dense 默认检索行为，Hybrid 继续作为独立、可配置实验策略，不据此切换生产默认。

## 完整16条Case对照

每条列出Query、冻结相关Chunk集合，以及四策略的实际排序和(Hit, Recall, RR)。本节未按收益筛选Case。

### rag_001
- Query：Top-K 表示什么
- 冻结相关标签：eval_rag:1, eval_rag:2, eval_tools:2。
- Dense：eval_rag:2 → eval_tools:2 → eval_engineering:2；(1, 0.666667, 1.000000)。
- BM25：eval_rag:1 → eval_rag:2 → eval_engineering:2；(1, 0.666667, 1.000000)。
- Hybrid RRF Depth-3：eval_rag:2 → eval_engineering:2 → eval_rag:1；(1, 0.666667, 1.000000)。
- Hybrid RRF Depth-5：eval_rag:2 → eval_rag:1 → eval_engineering:2；(1, 0.666667, 1.000000)。
- 收益/退化：BM25相对Dense：三项指标持平；Hybrid RRF Depth-3相对Dense：三项指标持平；Hybrid RRF Depth-5相对Dense：三项指标持平。

### rag_002
- Query：KnowledgePilot 中，answer_with_rag() 的 threshold=0.4 是否也作用于 search_knowledge_base()？如果没有资料通过 Pipeline 阈值，会发生什么？
- 冻结相关标签：eval_rag:2, eval_tools:2。
- Dense：eval_rag:2 → eval_tools:2 → eval_rag:3；(1, 1.000000, 1.000000)。
- BM25：eval_rag:2 → eval_tools:2 → eval_memory:0；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-3：eval_rag:2 → eval_tools:2 → eval_memory:0；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-5：eval_rag:2 → eval_tools:2 → eval_memory:0；(1, 1.000000, 1.000000)。
- 收益/退化：BM25相对Dense：三项指标持平；Hybrid RRF Depth-3相对Dense：三项指标持平；Hybrid RRF Depth-5相对Dense：三项指标持平。

### rag_003
- Query：Tool Registry 的作用
- 冻结相关标签：eval_tools:0。
- Dense：eval_tools:0 → eval_agent:1 → eval_agent:3；(1, 1.000000, 1.000000)。
- BM25：eval_tools:0 → eval_agent:1 → eval_tools:1；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-3：eval_tools:0 → eval_agent:1 → eval_agent:3；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-5：eval_tools:0 → eval_agent:1 → eval_tools:2；(1, 1.000000, 1.000000)。
- 收益/退化：BM25相对Dense：三项指标持平；Hybrid RRF Depth-3相对Dense：三项指标持平；Hybrid RRF Depth-5相对Dense：三项指标持平。

### rag_004
- Query：/chat 为什么 stateless
- 冻结相关标签：eval_agent:3, eval_api:0, eval_api:1, eval_memory:0。
- Dense：eval_api:1 → eval_agent:3 → eval_api:2；(1, 0.500000, 1.000000)。
- BM25：eval_api:0 → eval_agent:3 → eval_api:1；(1, 0.750000, 1.000000)。
- Hybrid RRF Depth-3：eval_api:1 → eval_agent:3 → eval_api:0；(1, 0.750000, 1.000000)。
- Hybrid RRF Depth-5：eval_api:1 → eval_agent:3 → eval_api:0；(1, 0.750000, 1.000000)。
- 收益/退化：BM25相对Dense：recall +0.250000；Hybrid RRF Depth-3相对Dense：recall +0.250000；Hybrid RRF Depth-5相对Dense：recall +0.250000。

### rag_005
- Query：长期 Memory 与 messages 的区别
- 冻结相关标签：eval_agent:1, eval_agent:3, eval_api:0, eval_api:1, eval_memory:0。
- Dense：eval_memory:0 → eval_agent:3 → eval_agent:1；(1, 0.600000, 1.000000)。
- BM25：eval_memory:0 → eval_agent:3 → eval_agent:0；(1, 0.400000, 1.000000)。
- Hybrid RRF Depth-3：eval_memory:0 → eval_agent:3 → eval_agent:0；(1, 0.400000, 1.000000)。
- Hybrid RRF Depth-5：eval_memory:0 → eval_agent:3 → eval_agent:0；(1, 0.400000, 1.000000)。
- 收益/退化：BM25相对Dense：recall -0.200000；Hybrid RRF Depth-3相对Dense：recall -0.200000；Hybrid RRF Depth-5相对Dense：recall -0.200000。

### rag_006
- Query：Test 与 Evaluation 的区别
- 冻结相关标签：eval_engineering:0。
- Dense：eval_engineering:0 → eval_engineering:2 → eval_engineering:1；(1, 1.000000, 1.000000)。
- BM25：eval_engineering:0 → eval_engineering:1 → eval_engineering:2；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-3：eval_engineering:0 → eval_engineering:1 → eval_engineering:2；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-5：eval_engineering:0 → eval_engineering:1 → eval_engineering:2；(1, 1.000000, 1.000000)。
- 收益/退化：BM25相对Dense：三项指标持平；Hybrid RRF Depth-3相对Dense：三项指标持平；Hybrid RRF Depth-5相对Dense：三项指标持平。

### rag_007
- Query：KnowledgePilot 的 Agent Loop 按什么顺序经过 Decision、Action 和 Observation，各阶段分别负责什么？trace 的单条工具记录有哪些字段、各字段表示什么，step 从几开始，同一 Decision 轮内多个 Tool Call 的 step 是否相同？
- 冻结相关标签：eval_agent:0, eval_agent:1, eval_agent:2, eval_agent:3, eval_api:1, eval_api:2, eval_memory:0, eval_rag:2, eval_tools:0, eval_tools:2。
- Dense：eval_agent:0 → eval_agent:3 → eval_agent:2；(1, 0.300000, 1.000000)。
- BM25：eval_agent:2 → eval_agent:3 → eval_agent:0；(1, 0.300000, 1.000000)。
- Hybrid RRF Depth-3：eval_agent:0 → eval_agent:2 → eval_agent:3；(1, 0.300000, 1.000000)。
- Hybrid RRF Depth-5：eval_agent:0 → eval_agent:2 → eval_agent:3；(1, 0.300000, 1.000000)。
- 收益/退化：BM25相对Dense：三项指标持平；Hybrid RRF Depth-3相对Dense：三项指标持平；Hybrid RRF Depth-5相对Dense：三项指标持平。

### rag_008
- Query：KnowledgePilot 的 TOOL_REGISTRY 如何把模型给出的工具名称映射到实际执行函数？工具执行出现可捕获异常时，Agent Loop 如何形成错误 Observation 并让模型继续决策？这与知识库 Tool 正常返回空列表有什么区别？
- 冻结相关标签：eval_agent:1, eval_tools:0。
- Dense：eval_agent:0 → eval_tools:0 → eval_agent:1；(1, 1.000000, 0.500000)。
- BM25：eval_agent:1 → eval_agent:0 → eval_tools:0；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-3：eval_agent:0 → eval_agent:1 → eval_tools:0；(1, 1.000000, 0.500000)。
- Hybrid RRF Depth-5：eval_agent:0 → eval_agent:1 → eval_tools:0；(1, 1.000000, 0.500000)。
- 收益/退化：BM25相对Dense：rr +0.500000；Hybrid RRF Depth-3相对Dense：三项指标持平；Hybrid RRF Depth-5相对Dense：三项指标持平。

### rag_009
- Query：底层 search() 的每条结果由哪三个部分组成？metadata 中 document_id、source、chunk_index 各表示什么？search_knowledge_base() 对外返回哪些字段，哪些检索分数和标识不再保留？
- 冻结相关标签：eval_agent:0, eval_agent:1, eval_engineering:1, eval_rag:1, eval_rag:2, eval_tools:2。
- Dense：eval_rag:1 → eval_tools:2 → eval_rag:2；(1, 0.500000, 1.000000)。
- BM25：eval_rag:2 → eval_rag:1 → eval_tools:2；(1, 0.500000, 1.000000)。
- Hybrid RRF Depth-3：eval_rag:1 → eval_rag:2 → eval_tools:2；(1, 0.500000, 1.000000)。
- Hybrid RRF Depth-5：eval_rag:1 → eval_rag:2 → eval_tools:2；(1, 0.500000, 1.000000)。
- 收益/退化：BM25相对Dense：三项指标持平；Hybrid RRF Depth-3相对Dense：三项指标持平；Hybrid RRF Depth-5相对Dense：三项指标持平。

### rag_010
- Query：Baseline 是什么，版本比较时为什么要固定 Evaluation Dataset、Corpus 和实验配置？当新版本整体指标提高却出现旧能力退化时，怎样用 Badcase 与 Ablation 分析 Regression，并保持哪些对照条件一致？
- 冻结相关标签：eval_engineering:0, eval_engineering:1, eval_engineering:2, eval_engineering:3, eval_rag:1。
- Dense：eval_engineering:1 → eval_engineering:2 → eval_engineering:0；(1, 0.600000, 1.000000)。
- BM25：eval_engineering:1 → eval_engineering:2 → eval_engineering:0；(1, 0.600000, 1.000000)。
- Hybrid RRF Depth-3：eval_engineering:1 → eval_engineering:2 → eval_engineering:0；(1, 0.600000, 1.000000)。
- Hybrid RRF Depth-5：eval_engineering:1 → eval_engineering:2 → eval_engineering:0；(1, 0.600000, 1.000000)。
- 收益/退化：BM25相对Dense：三项指标持平；Hybrid RRF Depth-3相对Dense：三项指标持平；Hybrid RRF Depth-5相对Dense：三项指标持平。

### rag_011
- Query：max_steps 是 Decision 轮数还是 Tool 次数
- 冻结相关标签：eval_agent:1, eval_agent:2。
- Dense：eval_agent:2 → eval_agent:1 → eval_agent:0；(1, 1.000000, 1.000000)。
- BM25：eval_agent:2 → eval_agent:0 → eval_agent:1；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-3：eval_agent:2 → eval_agent:0 → eval_agent:1；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-5：eval_agent:2 → eval_agent:0 → eval_agent:1；(1, 1.000000, 1.000000)。
- 收益/退化：BM25相对Dense：三项指标持平；Hybrid RRF Depth-3相对Dense：三项指标持平；Hybrid RRF Depth-5相对Dense：三项指标持平。

### rag_012
- Query：Tool Result 写回 Agent messages 时，role、tool_name、content 分别代表什么？
- 冻结相关标签：eval_agent:1。
- Dense：eval_agent:1 → eval_agent:0 → eval_agent:3；(1, 1.000000, 1.000000)。
- BM25：eval_agent:1 → eval_agent:3 → eval_tools:0；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-3：eval_agent:1 → eval_agent:3 → eval_agent:0；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-5：eval_agent:1 → eval_agent:3 → eval_agent:0；(1, 1.000000, 1.000000)。
- 收益/退化：BM25相对Dense：三项指标持平；Hybrid RRF Depth-3相对Dense：三项指标持平；Hybrid RRF Depth-5相对Dense：三项指标持平。

### rag_013
- Query：trace 单条工具记录有哪些字段
- 冻结相关标签：eval_agent:2, eval_agent:3。
- Dense：eval_agent:3 → eval_rag:1 → eval_agent:2；(1, 1.000000, 1.000000)。
- BM25：eval_api:2 → eval_agent:3 → eval_memory:0；(1, 0.500000, 0.500000)。
- Hybrid RRF Depth-3：eval_agent:3 → eval_api:2 → eval_rag:1；(1, 0.500000, 1.000000)。
- Hybrid RRF Depth-5：eval_agent:3 → eval_api:2 → eval_rag:1；(1, 0.500000, 1.000000)。
- 收益/退化：BM25相对Dense：recall -0.500000，rr -0.500000；Hybrid RRF Depth-3相对Dense：recall -0.500000；Hybrid RRF Depth-5相对Dense：recall -0.500000。

### rag_014
- Query：distance 如何转换为 similarity
- 冻结相关标签：eval_rag:1。
- Dense：eval_rag:1 → eval_rag:0 → eval_rag:2；(1, 1.000000, 1.000000)。
- BM25：eval_api:0 → eval_agent:0 → eval_rag:0；(0, 0.000000, 0.000000)。
- Hybrid RRF Depth-3：eval_rag:0 → eval_api:0 → eval_rag:1；(1, 1.000000, 0.333333)。
- Hybrid RRF Depth-5：eval_rag:1 → eval_rag:0 → eval_api:0；(1, 1.000000, 1.000000)。
- 收益/退化：BM25相对Dense：hit -1.000000，recall -1.000000，rr -1.000000；Hybrid RRF Depth-3相对Dense：rr -0.666667；Hybrid RRF Depth-5相对Dense：三项指标持平。

### rag_015
- Query：update_document 更新失败为什么可能丢失旧 Chunk
- 冻结相关标签：eval_engineering:3。
- Dense：eval_engineering:3 → eval_rag:1 → eval_engineering:2；(1, 1.000000, 1.000000)。
- BM25：eval_engineering:3 → eval_engineering:2 → eval_engineering:1；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-3：eval_engineering:3 → eval_engineering:2 → eval_rag:1；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-5：eval_engineering:3 → eval_engineering:2 → eval_engineering:1；(1, 1.000000, 1.000000)。
- 收益/退化：BM25相对Dense：三项指标持平；Hybrid RRF Depth-3相对Dense：三项指标持平；Hybrid RRF Depth-5相对Dense：三项指标持平。

### rag_016
- Query：Hit Rate、Recall、MRR 分别衡量什么
- 冻结相关标签：eval_rag:2, eval_rag:3。
- Dense：eval_rag:3 → eval_rag:2 → eval_engineering:2；(1, 1.000000, 1.000000)。
- BM25：eval_rag:3 → eval_engineering:0 → eval_rag:2；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-3：eval_rag:3 → eval_rag:2 → eval_engineering:0；(1, 1.000000, 1.000000)。
- Hybrid RRF Depth-5：eval_rag:3 → eval_rag:2 → eval_engineering:2；(1, 1.000000, 1.000000)。
- 收益/退化：BM25相对Dense：三项指标持平；Hybrid RRF Depth-3相对Dense：三项指标持平；Hybrid RRF Depth-5相对Dense：三项指标持平。

## 关键Case的真实排名及贡献

### rag_004
- Hybrid RRF Depth-3 #1 eval_api:1：Dense rank=1, similarity=0.6399756669998169；BM25 rank=3, score=3.209018296425552；RRF=0.016393442623+0.015873015873=0.032266458496。
- Hybrid RRF Depth-3 #2 eval_agent:3：Dense rank=2, similarity=0.5377079844474792；BM25 rank=2, score=3.9798627709781176；RRF=0.016129032258+0.016129032258=0.032258064516。
- Hybrid RRF Depth-3 #3 eval_api:0：Dense rank=None, similarity=None；BM25 rank=1, score=4.0527989016963195；RRF=0.000000000000+0.016393442623=0.016393442623。
- Hybrid RRF Depth-5 #1 eval_api:1：Dense rank=1, similarity=0.6399756669998169；BM25 rank=3, score=3.209018296425552；RRF=0.016393442623+0.015873015873=0.032266458496。
- Hybrid RRF Depth-5 #2 eval_agent:3：Dense rank=2, similarity=0.5377079844474792；BM25 rank=2, score=3.9798627709781176；RRF=0.016129032258+0.016129032258=0.032258064516。
- Hybrid RRF Depth-5 #3 eval_api:0：Dense rank=4, similarity=0.48423582315444946；BM25 rank=1, score=4.0527989016963195；RRF=0.015625000000+0.016393442623=0.032018442623。
- 解释：Hybrid用相关eval_api:0替代Dense第三位的eval_api:2；相关数从2/4增为3/4，Recall 0.50→0.75。Depth5中eval_api:0由Dense#4与BM25#1共同贡献。

### rag_005
- Hybrid RRF Depth-3 #1 eval_memory:0：Dense rank=1, similarity=0.6816750764846802；BM25 rank=1, score=13.258618720029041；RRF=0.016393442623+0.016393442623=0.032786885246。
- Hybrid RRF Depth-3 #2 eval_agent:3：Dense rank=2, similarity=0.5865995287895203；BM25 rank=2, score=13.20302661156014；RRF=0.016129032258+0.016129032258=0.032258064516。
- Hybrid RRF Depth-3 #3 eval_agent:0：Dense rank=None, similarity=None；BM25 rank=3, score=3.111697207655304；RRF=0.000000000000+0.015873015873=0.015873015873。
- Hybrid RRF Depth-5 #1 eval_memory:0：Dense rank=1, similarity=0.6816750764846802；BM25 rank=1, score=13.258618720029041；RRF=0.016393442623+0.016393442623=0.032786885246。
- Hybrid RRF Depth-5 #2 eval_agent:3：Dense rank=2, similarity=0.5865995287895203；BM25 rank=2, score=13.20302661156014；RRF=0.016129032258+0.016129032258=0.032258064516。
- Hybrid RRF Depth-5 #3 eval_agent:0：Dense rank=4, similarity=0.47713470458984375；BM25 rank=3, score=3.111697207655304；RRF=0.015625000000+0.015873015873=0.031498015873。
- 解释：Dense候选eval_agent:1属于相关集合，Hybrid用不相关eval_agent:0替换它；相关数从3/5降为2/5，Recall 0.60→0.40。

### rag_008
- Hybrid RRF Depth-3 #1 eval_agent:0：Dense rank=1, similarity=0.7516965866088867；BM25 rank=2, score=62.949155445011115；RRF=0.016393442623+0.016129032258=0.032522474881。
- Hybrid RRF Depth-3 #2 eval_agent:1：Dense rank=3, similarity=0.7113566398620605；BM25 rank=1, score=78.19045824160924；RRF=0.015873015873+0.016393442623=0.032266458496。
- Hybrid RRF Depth-3 #3 eval_tools:0：Dense rank=2, similarity=0.7129530906677246；BM25 rank=3, score=54.7332542716206；RRF=0.016129032258+0.015873015873=0.032002048131。
- Hybrid RRF Depth-5 #1 eval_agent:0：Dense rank=1, similarity=0.7516965866088867；BM25 rank=2, score=62.949155445011115；RRF=0.016393442623+0.016129032258=0.032522474881。
- Hybrid RRF Depth-5 #2 eval_agent:1：Dense rank=3, similarity=0.7113566398620605；BM25 rank=1, score=78.19045824160924；RRF=0.015873015873+0.016393442623=0.032266458496。
- Hybrid RRF Depth-5 #3 eval_tools:0：Dense rank=2, similarity=0.7129530906677246；BM25 rank=3, score=54.7332542716206；RRF=0.016129032258+0.015873015873=0.032002048131。
- 解释：eval_agent:0为Dense#1+BM25#2，RRF 0.032522474881；相关eval_agent:1为Dense#3+BM25#1，RRF 0.032266458496。BM25原本将相关Chunk排第一，但融合后仍是第二，RR从BM25的1降至0.5。

### rag_013
- Hybrid RRF Depth-3 #1 eval_agent:3：Dense rank=1, similarity=0.664677619934082；BM25 rank=2, score=9.588858631217185；RRF=0.016393442623+0.016129032258=0.032522474881。
- Hybrid RRF Depth-3 #2 eval_api:2：Dense rank=None, similarity=None；BM25 rank=1, score=12.700697114060102；RRF=0.000000000000+0.016393442623=0.016393442623。
- Hybrid RRF Depth-3 #3 eval_rag:1：Dense rank=2, similarity=0.5801288485527039；BM25 rank=None, score=None；RRF=0.016129032258+0.000000000000=0.016129032258。
- Hybrid RRF Depth-5 #1 eval_agent:3：Dense rank=1, similarity=0.664677619934082；BM25 rank=2, score=9.588858631217185；RRF=0.016393442623+0.016129032258=0.032522474881。
- Hybrid RRF Depth-5 #2 eval_api:2：Dense rank=None, similarity=None；BM25 rank=1, score=12.700697114060102；RRF=0.000000000000+0.016393442623=0.016393442623。
- Hybrid RRF Depth-5 #3 eval_rag:1：Dense rank=2, similarity=0.5801288485527039；BM25 rank=None, score=None；RRF=0.016129032258+0.000000000000=0.016129032258。
- 解释：相关集合包括eval_agent:3与eval_agent:2。BM25#1的非相关eval_api:2以单路0.016393442623进入融合第二位；Dense#2非相关eval_rag:1以0.016129032258进入第三位，超过相关eval_agent:2（Dense#3，0.015873015873）。Depth5两路交集没有给该相关块增加贡献，Recall从1降至0.5。

### rag_014
- Hybrid RRF Depth-3 #1 eval_rag:0：Dense rank=2, similarity=0.5232535004615784；BM25 rank=3, score=6.32725289525962；RRF=0.016129032258+0.015873015873=0.032002048131。
- Hybrid RRF Depth-3 #2 eval_api:0：Dense rank=None, similarity=None；BM25 rank=1, score=10.395114438434792；RRF=0.000000000000+0.016393442623=0.016393442623。
- Hybrid RRF Depth-3 #3 eval_rag:1：Dense rank=1, similarity=0.5722239017486572；BM25 rank=None, score=None；RRF=0.016393442623+0.000000000000=0.016393442623。
- Hybrid RRF Depth-5 #1 eval_rag:1：Dense rank=1, similarity=0.5722239017486572；BM25 rank=4, score=5.767099141552622；RRF=0.016393442623+0.015625000000=0.032018442623。
- Hybrid RRF Depth-5 #2 eval_rag:0：Dense rank=2, similarity=0.5232535004615784；BM25 rank=3, score=6.32725289525962；RRF=0.016129032258+0.015873015873=0.032002048131。
- Hybrid RRF Depth-5 #3 eval_api:0：Dense rank=None, similarity=None；BM25 rank=1, score=10.395114438434792；RRF=0.000000000000+0.016393442623=0.016393442623。
- 解释：Depth3中目标eval_rag:1只获得Dense#1的0.016393442623，与BM25#1非相关eval_api:0并列，确定性document_id排序使eval_api在前，目标最终第三。Depth5纳入BM25#4：目标1/61+1/64=0.032018442623，略高于eval_rag:0的1/62+1/63=0.032002048131，目标恢复第一。

## 归档与运行溯源

四份报告合计716654字节，适合完整归档。检查未发现凭据字段或可识别密钥/用户主目录模式；保留了通用本地项目绝对source路径D:\AI_develop\KnowledgePilot，未脱敏或改写任何原报告字节。

[机器可读归档清单](v1.3_reports/archive_index.json)包含原始/副本路径、完整SHA-256、字节数、Schema、真实Run ID、配置、Provenance及源码漂移说明。原始文件仍在Git忽略的数据目录；文档归档目录不受忽略，未修改.gitignore。

- [dense_v13_k3_20261020T075936_904246Z.json](v1.3_reports/dense_v13_k3_20261020T075936_904246Z.json)
  原始路径：`data/evaluation/reports/dense_v13_k3_20261020T075936_904246Z.json`；Run ID：`dense-v13-20261020T075939-138374Z`。
  SHA-256：`e167a0b53bd31624bb7acb300e37aa9cfe6f21fe85bb8ef97d10a487e5e36d9b`；71689字节；副本逐字节和哈希均一致。

- [bm25_v13_k3_20261020T082317_766419Z.json](v1.3_reports/bm25_v13_k3_20261020T082317_766419Z.json)
  原始路径：`data/evaluation/reports/bm25_v13_k3_20261020T082317_766419Z.json`；Run ID：`bm25-v13-20261020T082320-212628Z`。
  SHA-256：`7cc185b6de6084036c3d15c08c6ab677a7b52b7384c298b9556a21ac45d1ebcb`；76885字节；副本逐字节和哈希均一致。

- [hybrid_rrf_v13_depth3_k3_20261020T093101_130584Z.json](v1.3_reports/hybrid_rrf_v13_depth3_k3_20261020T093101_130584Z.json)
  原始路径：`data/evaluation/reports/hybrid_rrf_v13_depth3_k3_20261020T093101_130584Z.json`；Run ID：`hybrid-rrf-depth3-20261020T093101_130584Z`。
  SHA-256：`4fafd44156aa539865ad5a9ae48ab5c9d3eb9ade00d176f7b5f41e9ef56709ef`；239917字节；副本逐字节和哈希均一致。

- [hybrid_rrf_v13_depth5_k3_20261020T093108_710661Z.json](v1.3_reports/hybrid_rrf_v13_depth5_k3_20261020T093108_710661Z.json)
  原始路径：`data/evaluation/reports/hybrid_rrf_v13_depth5_k3_20261020T093108_710661Z.json`；Run ID：`hybrid-rrf-depth5-20261020T093108_710661Z`。
  SHA-256：`9ebdb8855fcb139cee3820f2c8f318d750d8122aeacca35b25a3a7871fd3754d`；328163字节；副本逐字节和哈希均一致。

四份报告Schema均为retrieval_run_report_v1，Dataset/Manifest/六篇Corpus文件身份与当前冻结文件一致；Git记录HEAD=7eca62c15e9de044e3e6fef84b41da069e078881，dirty=true，observation_errors为空。模型digest=7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab。BM25不调用Embedding，报告未记录模型身份是“不适用”，不能补造。

历史源码差异：Dense和BM25运行时的run_report.py哈希为ed8e37d62918ab76a565b97b75aa90e8566b948cefcb6659cac5d4c3b09326a0，当前为8f4c0ad9b1c807b937b6badc7bd1d7270882f8affd644a9c570e0b62a62ae974。仅逆向移除Hybrid阶段新增的Case联合类型和两个导入，重建字节哈希即与历史一致，组装逻辑未变。未把历史Provenance改成当前哈希。其余历史源码哈希及两份Hybrid所有源码哈希一致。

## 复现说明

先准备本项目真实源码和冻结Dataset/Corpus/Manifest，并取得与Hybrid报告中frozen_runtime_files哈希一致的独立冻结Runtime。数据库未归档进Git，不得通过重新Ingest替代原19个Chunk。运行前按归档Provenance验证文件身份，确认Ollama提供同digest的bge-m3:latest及现有依赖（Python3.11.16、Chroma1.5.9、requests2.34.2；测试环境pytest9.1.1）。不要自动安装或升级。

从项目根目录运行以下命令会生成新的时间戳报告，不能要求覆盖本次原始证据：

```powershell
Set-Location 'D:\AI_develop\KnowledgePilot'
$pythonExe = 'D:\Anaconda\envs\knowledge-pilot\python.exe'
$env:PYTHONPATH = 'D:\AI_develop\KnowledgePilot\src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:ANONYMIZED_TELEMETRY = 'False'
& $pythonExe -B scripts/run_dense_baseline_v13.py
& $pythonExe -B scripts/run_bm25_baseline_v13.py
& $pythonExe -B scripts/run_hybrid_baseline_v13.py
```

三个脚本均通过临时副本隔离正常入口；Hybrid脚本逐个重新检索depth3与depth5，而非复用历史Top3。不要直接调用隐藏的worker/runtime-copy参数。复现前后核对冻结文件与历史报告SHA-256；得分/排序可核验，延迟不保证重复。

## RC 初次检查（历史）与测试门禁修复

- 单进程收集整个tests：434 passed / 1 failed / 1 skipped，7个子测试通过。失败：tests/evaluation/test_agent_report.py:273，test_build_does_not_import_model_database_or_registry。
- 原因：tests/test_agent_loop.py:5在收集时导入ollama_client，并连带加载registry/chroma_store；报告构建测试假设它们从未进入sys.modules，产生跨测试模块污染。该运行的Chroma仅初始化于项目外临时CWD，原库未打开。
- 分进程完整覆盖：Evaluation 396 passed；Agent/API/Tools/RAG等39 passed / 1 skipped；合计435 passed / 0 failed / 1 skipped，7个子测试通过。不能把分进程通过写成单进程测试已修复。
- 跳过：test_search_returns_three_content_source_results，需要KNOWLEDGE_PILOT_RUN_INTEGRATION=1和真实Ollama/Chroma。本轮未启用，不能报告通过。原有真实检索证据来自上述四份已存JSON。
- 两条第三方弃用警告来自Starlette/httpx/anyio；不安装新依赖解决。
- **历史封版阻塞（已关闭）**：初次默认完整测试命令有上述失败。最小修复范围为该报告隔离测试/测试进程边界：在干净子进程执行构建和禁止导入断言，保留原断言标准，再重跑完整测试。不需要改检索算法、稳定Runner或冻结数据。初次检查按“发现阻塞即停止封版流程”未修复；随后用户单独授权测试隔离修复。

当前修复：仅test_build_does_not_import_model_database_or_registry进入干净Python子进程；显式源码路径、临时CWD、30秒超时，检查报告导入前/后与构建后的三个禁止模块，非零退出使父测试失败并保留stdout/stderr。目标测试独立1通过；与Agent测试按两种顺序各10通过。负向注入真实禁止导入能正确触发失败。没有清空主进程sys.modules、删除断言或新增Skip/XFail。

当前完整单进程结果：435 passed / 0 failed / 1 skipped，7个子测试通过。原有真实集成测试仍需显式启用，未将跳过写成通过。第三方两条弃用警告保留，不为此升级依赖。

完整安全测试复现（须在项目外独立临时工作目录，避免导入时Chroma写入原项目）：

```powershell
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('kp-rc-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
Set-Location -LiteralPath $testRoot
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:KNOWLEDGE_PILOT_RUN_INTEGRATION = '0'
& $pythonExe -B -m pytest -q -ra -p no:cacheprovider D:\AI_develop\KnowledgePilot\tests
```

以上为完整套件单次正常Pytest收集与执行；只有导入契约测试内部使用子进程，不把整个套件拆分规避。

## 局限性与非阻塞技术债

- 字符unigram/bigram会把“如何”“转换为”重复贡献高IDF词项；rag_014的BM25排序已展示词面噪声。没有jieba或词级分词，不把该实现宣传为中文词级分词。
- 16条固定Case不足以证明普遍优势。Dense/Hybrid Hit@3已100%，存在天花板；Recall与MRR仍揭示退化。
- 运行顺序、模型预热及统计边界不同，延迟不可直接横比。Depth3先运行，首条6245.650ms；Depth5在预热后运行。没有重复随机顺序性能实验。
- 降级、双路异常、正常空结果、评分异常、写入失败由合成测试验证；未执行真实故障注入。
- Dense/BM25旧编排捕获Exception较宽；Hybrid只捕获显式RetrievalError并保留阶段。BM25脚本仍有既有cast(list[CaseEvidence], records)，当前RunReport联合已能表达BM25CaseEvidence，属后续局部清理，不影响运行和旧报告。
- run_report.py/run_provenance.py有遗留placeholder/TODO学习注释，但相关函数有真实实现，未发现V1.3运行路径的NotImplementedError。JSON Writer不提供fsync/断电级持久性保证。
- 正式发布更新pyproject.toml/README为1.3.0；HTTP API版本仍为1.1.0，表示未变的API契约，不将其随独立评测版本无理由更改。
- jieba、Reranker及更大数据集属于可选后续实验，本版未实现。

## 历史冻结保护记录与正式发布范围

初次RC总结阶段只修改本说明并新增文档归档/清单。全部137个既有受检文件（含data/src/scripts/tests/docs及.git/index、.gitignore、pyproject.toml、requirements.txt）已于写入完成后再次核对；137个既有文件中只有本说明发生变化，其余136个原文件全部一致；新增5个归档/清单文件。V1.2 Dataset/Corpus/Manifest、历史报告、冻结Runtime、开发库和四份V1.3原报告必须字节不变。

实验与RC检查基线为main@7eca62c15e9de044e3e6fef84b41da069e078881。正式发布按精确路径纳入V1.3模块、脚本、测试、文档/归档，以及已验收的CaseEvidence最终工作区版本；不纳入docs/interview、任何Chroma数据库或缓存。v1.2.0保持原指向。归档JSON使用.gitattributes的-text规则保留原字节，新增评测源码/脚本同样保留字节以支持已记录的源码身份核验。BM25已验收源码保留原有EOF空行；仅该文件配置whitespace=-blank-at-eof，不为消除格式提示改写历史源码身份，其他空白检查保留。

已有真实功能：四组检索证据、真实文件身份与哈希、RRF融合及独占JSON持久化。仅经合成验证：异常降级、故障阶段、正常空结果、评分/写入失败路径。完整测试隔离问题已修复并复测，Dense保持默认，Hybrid保留为实验策略。v1.3.0用于标识正式发布Commit；历史实验Provenance继续记录当时dirty工作区及源码哈希，不伪造为发布后重跑。

**V1.3 RC Test Gate: PASS**
