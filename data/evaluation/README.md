# KnowledgePilot Evaluation Dataset V1

本目录固定 V1.2 Offline Evaluation 的输入与评分约定，不包含 Evaluator、Runner 或 Baseline 成绩。

## 正式文件与身份

cases_v1.json 固定24条Case，dataset_status=FROZEN、frozen=true、版本v1。corpus/ 固定六篇 UTF-8、无BOM、LF的TXT，Corpus版本corpus_v1。manifests/evaluation_v1.json记录六源文件、19块、正式Dataset和重建脚本的SHA-256；清单内path以项目根为基准；Dataset内document_map和version_manifest以Dataset所在的data/evaluation目录为基准，path_bases明确此区别。scripts/initialize_corpus_v1.py是一次性建库/验证入口；默认模式写入，只用于经授权的新空环境；--verify-only不入库。cases_draft.json和runtime/继续忽略。

正式document_id是六个文件stem：eval_rag、eval_agent、eval_tools、eval_api、eval_memory、eval_engineering。稳定Chunk身份为(document_id,chunk_index)，序号从0开始。按现有chunk_text()以500字符、100字符overlap切分，不按字节或token切分。

本机runtime曾以草稿初始化。其initialization_manifest保留当时DRAFT状态、草稿哈希、绝对source与执行历史；这不覆盖正式Dataset状态。此次freeze仅verify-only。验证会更新本机清单的reopen时间，正式数据身份不依赖该动态清单的文件哈希。旧清单未记录dataset_relative_path时，脚本仍验证当时cases_draft哈希；新初始化优先cases_v1并记录实际路径/状态/哈希。六源与19块的内容验证将正式输入与旧runtime关联。

## 字节与Git

源文件哈希按实际字节计算；Chunk哈希按现有load_text/chunk_text输出的UTF-8编码计算。正式文本均使用LF。当前本机core.autocrlf=true；本次不改全局配置。新副本应在首次checkout前禁用自动行尾转换，例如：

~~~powershell
git -c core.autocrlf=false clone <repository-url> KnowledgePilot
~~~

已有副本必须先验证六源和正式Dataset的SHA-256。遇到CRLF/BOM差异应停止并重新取得未经转换的正式输入，不能更新清单来迁就差异。这是重建前置条件。

.gitignore仅开放六个指定TXT、cases_v1.json、此README、指定脚本和指定正式清单。runtime、SQLite、索引二进制、草稿与其他开发data继续忽略。文件标记FROZEN不等于已经Git提交。

## 重建前置检查

1. 核心代码Git HEAD、初始化脚本及正式输入须与清单一致；本轮仅准备文件，尚未Git提交。
2. 复用已有依赖环境；参考Python 3.11.16、Chroma 1.5.9、requests 2.34.2、Ollama 0.40.2。项目要求Python >=3.11；优先复用参考3.11.16版本。
3. Ollama /api/tags中bge-m3:latest的digest须等于正式清单embedding.digest。标签会漂移，不能只检查模型名。脚本记录实际digest，使用者必须在建库前比对。
4. 先比对六源、19块、正式Dataset和脚本哈希，再建库。出现差异停止，不覆盖正式清单。
5. 在首次导入前设置独立CWD和绝对PYTHONPATH，使用新Python进程；禁止导入后切换CWD或重赋全局collection。
6. 不复用开发数据库。若目标runtime已有数据库、旧清单或非空Collection，停止核对，不删除/覆盖。当前环境已经入库，只运行verify-only。

下面仅用于经授权的全新环境，会创建目录并调用现有ingest_document；本轮没有运行。请在新副本项目根执行，并确保python指向项目已有环境：

~~~powershell
$projectRoot = (Resolve-Path '.').Path
$evaluationRuntime = Join-Path $projectRoot 'data/evaluation/runtime/corpus_v1'
New-Item -ItemType Directory -Path $evaluationRuntime -ErrorAction Stop
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:ANONYMIZED_TELEMETRY = 'False'
$initScript = Join-Path $projectRoot 'data/evaluation/scripts/initialize_corpus_v1.py'
Set-Location -LiteralPath $evaluationRuntime
python -B $initScript
~~~

已初始化环境，在项目根打开新的终端后只验证：

~~~powershell
$projectRoot = (Resolve-Path '.').Path
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:ANONYMIZED_TELEMETRY = 'False'
$initScript = Join-Path $projectRoot 'data/evaluation/scripts/initialize_corpus_v1.py'
Set-Location -LiteralPath (Join-Path $projectRoot 'data/evaluation/runtime/corpus_v1')
python -B $initScript --verify-only
~~~

脚本从自身位置推导项目根。首次导入绑定runtime/corpus_v1/data/vector_store，Collection=knowledge_pilot_docs，cosine。本轮未在另一副本实测从零重建，因为禁止重新入库。

source metadata是本机入库时的绝对路径，换环境会变化。跨环境身份使用相对源路径、document_id、chunk_index与内容哈希，不使用绝对source。向量二进制字节及排名完全一致不作保证。

## 稳定机器字段与评分v1

Case顶层required_facts是fact_id到事实正文的映射；coverage_by_chunk列出全部19块的document_id、chunk_index、covered_facts。partial_support不覆盖完整事实。required_fact_contexts的同名范围与事实正文共同构成完整定义；无context则没有额外限制。rag_010的same_vector_model只适用于阈值过滤启用/关闭对照，不泛指改变向量模型的实验。

顶层scoring_policy是正式入口，版本v1。review.multi_chunk_check仅为原审核副本；review.history、review_policy_history、scoring_policy_history均不作为当前评分入口。允许多个完整证据组合，示例组合不是唯一正确组合。

普通Recall@K保留所有真实Relevant，按不同(document_id,chunk_index)计数。MRR在记录的Top-K中取首个Relevant的排名倒数（从1开始），未命中记0。普通Recall/MRR平均只包含正例retrieval；No-answer排除且不补零，单独评拒答/任务成功。

Multi-Chunk同时保留Recall、Fact Coverage、Evidence Sufficient。Fact Coverage为Top-K的covered_facts去重并集大小除以required_facts数；partial_support不计入。全部事实覆盖时Evidence Sufficient=1。相同事实仅计一次；不得删真实Relevant提高Recall。

数值exact仅接受完整ASCII数值，先strip，再有限Decimal精确比较。12与12.0等价，允许科学计数；拒绝NaN/Infinity、解释、单位、围栏、内部空白、逗号、下划线。使用numeric_answers.fullmatch_pattern，不从长文本提取数字。自然语言Case保留manual/contains。

Tool Attempt以trace[*].tool记尝试，包括失败与未注册工具名；Tool Execution Success还须实际执行成功并符合参数/返回契约。Required Tool Coverage为必需工具尝试命中比例，All Required Tools Hit要求全部必需名称被尝试，两者均不能证明执行成功。

Task Success由答案及必要行为共同判断：必需工具成功完成任务相关操作、禁止工具未尝试，允许失败后重试成功。completed不证明任务成功。缺失/非法trace是RUN_ERROR，不能伪造空trace；合法空trace保留。非空知识库候选不证明No-answer有答案，工具失败不是无答案证据。

Hard Negative仅为正文核验的语义负例候选，排名难度尚未实测。本版没有完整Agent评测、评分器或Baseline成绩。

## 本轮verify-only的物理文件变化

本轮verify-only未调用ingest/add/upsert，也未生成新Embedding；正文、metadata、19块SHA和6文档/19记录均一致，原开发库文件与数量不变。但打开隔离PersistentClient后，隔离SQLite及部分HNSW文件SHA发生变化，全部5个数据库文件mtime变化。因此verify-only只保证脚本不重新入库，不能称为物理文件零写入。正式清单runtime_artifact_observation记录前后哈希；本轮未追踪原生存储层的具体写入调用，也未修复Core或还原数据库。若今后要求字节级只读，需要另行设计。
