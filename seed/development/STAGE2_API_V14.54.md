# V14.54 第二阶段接口与验证依赖

Engine 2.65.0，Engine/Guard 协议4；Guard 2.21.0实现不变。运行仍为单文件 engine.py。本文所列服务均已接入实际CLI和开发加载器。维护不授权新游戏行动。

## 一轮默认读取

`python3 engine.py roundcontext --base <root>`

默认批量：五项余额、任务、当前场景。可用 `--topics '["五项余额","任务","当前场景"]'` 指定1～8个主题，调用既有可见性过滤；不搬入完整state/rules/history。所有主题在同一 SnapshotContext/SAVESET 内生成。

`querybatch`保留；`turn --mode preview`、`routineplan`、`reportframe`及普通读取CLI均共享快照。服务方法 `turn_packet`、`routineplan_packet`、`reportframe_packet`也在快照内运行。嵌套同根读取复用作用域。

## 输出版本

默认CLI为 presentation_version=compact_v2；旧业务字段保持原值，仅将readiness/source_ready重复诊断容器替换为READINESS_COMPACT_V1，并附source_context。完整兼容投影：`--presentation full`。`readiness`、`startupfull`、`diagnostics`为明确展开入口，不精简其诊断数据。Python只读服务保留旧完整投影；`compact_packet`和`round_context_packet`显式提供紧凑投影。高层`turn_session`与`domain_command_packet`默认返回compact_v2，`presentation="full"`保留旧完整输出；session/invoke/hostinvoke等CLI支持`--presentation full`。写完后才在原独占锁内创建新的读取快照，绝不让只读快照跨提交。可选展示失败保留原提交结果并标记FULL_FALLBACK，不能诱导业务重试。

source_context含SAVESET、游戏时间、viewer、完整性状态、版本绑定diagnostic_ref。限制始终保留READY_WITH_LIMITATIONS、历史未模拟窗口、下一经营/语义阻断及错误、能力状态；业务中的未知值不裁剪。

`diagnostics --ref '<完整diagnostic_ref JSON>'`验证SAVESET、完整manifest摘要、engine摘要及viewer。版本或观察者不匹配拒绝；观察者不能读完整诊断；其批量/单项查询即便请求full或被拒绝，也只返回就绪状态与权限摘要，不携带指挥官的经营边界、账户缺项或历史时钟明细。不得把过期引用当新版本成功。

`--budget-bytes`范围512～1048576，默认16384；startup/boot保留原3500字节上限和第一阶段必要摘要，附同版本诊断引用，用户更小的预算仍生效。context_bytes精确计入最终紧凑JSON正文所有字段（不包含末尾换行）；字节不等于token，不报告伪token估计。可选重复诊断先移出。剩余业务硬约束超预算时保留完整合法JSON并标记budget_exceeded和EXCEEDED_REQUIRES_PAGINATION；调用方缩小主题或按既有分页接口取下一页，不得把该包当成已满足预算。full不强制压缩。

## 写事务与第三阶段调用约定

`with TransactionService.context(root) as context:`持有root独占锁。`turn_session`、`domain_command_packet`、`atomic_save`、`TransactionService.commit`已实际接入；嵌套同根写复用作用域和已有锁深度。交互等待时退出作用域，不能跨轮持锁。

context记录parent、working、target的SAVESET/manifest或完整依赖身份、检查结果及精确field_changes路径。写工作状态仍由现有加载器创建独立可变对象，绝不把只读快照当可写状态。提交和journal/fsync/manifest提交点/回执协议不变；中断后先由Guard恢复，再从新版本读取或用相同command_id和相同负载重试。相同ID不同负载仍拒绝。

事务内proofs仅存内存，退出清空。`VOYAGER_DISABLE_VALIDATION_REUSE=1`可禁用新复用走完整慢路径，供审计/对照；不禁用任何旧检查。`check --full`保留既有全部业务、父前缀、授权、定价、经营、场景、版本检查。

第三阶段prepare阶段使用`SnapshotReader.open(root)`或round_context，保存基础SAVESET。生成提案期间退出读取。commit阶段重新进入事务并通过既有类型化命令/可信宿主授权提交；基础版本过期须重新准备。永久回执仍用history_lookup(command_id=...)；不要重复掷随机或重复扣款。缓存仅是同不可变字节的证明，不是授权凭证。

## 验证依赖表（全部旧检查保留）

| 检查/证明 | 真实依赖与选项 | 执行阶段/失效 |
|---|---|---|
| Snapshot readiness | 完整manifest、所有组件、冷档、已物化开发文件实际SHA256、Engine版本；原HMAC派生缓存协议 | 读取开始/结束真实内容核对；每次检查恢复意图；变化、丢失或缓存故障慢路径 |
| component_source_check原完整实现（含protocol/reference/current/domain链） | 规范绝对root、全部上述真实字节、symlink状态、可见顶层文件形状、两个恢复journal实际字节、strict_fileset、Engine/Python版本 | 同作用域同完整依赖仅复用PASS；变化前后再校验，失败不记成功；首次和失效调用旧完整实现 |
| run_checks全套 | state/tasks/rules/catalog/history/tool/schema、full/expected_version/require_manifest及父快照、授权/账户/定价/经营/场景规则 | 每次照旧执行，不缓存整个run_checks；只复用不变历史段/编译和完整组件证明 |
| 冷历史解码 | 完整epoch记录摘要、真实压缩文件SHA256、Engine/Python/编译模式 | 事务/请求内每个相同段解码一次；换段内容/记录/版本立即失效；原payload/codec/range/seq/search_index摘要检查全保留 |
| 历史集合 | 实际events字节、每个被引用冷段真实SHA256、规范路径、validate_metadata、Engine版本 | 尾部变化重新解析热尾与验证next_seq/序号/ID；既有parent物理前缀与完整raw前缀检查不变 |
| 工具可编译证明 | 实际源码SHA256、Engine/Python版本、optimize；显式dont_inherit编译 | 同作用域成功证明复用；源码变化重新compile；不从磁盘加载成功标志或代码对象 |
| 经营/账本/授权/权限 | 原类型化命令、父状态、规则、事件凭证、余额单位、actor/target/时窗/额度 | 所有旧校验仍在run_checks/domain执行；不缓存按viewer过滤后的结果，不跨角色共享文本 |
| 零区间汇报摘要 | 完整快照绑定、history语义验证；结构化流水最早时间/through_seq | 首次完整建立摘要；热读取同快照可免解码；跨版本/冷档/开发变化失效。历史非结构化缺口仍PARTIAL，不变零 |
| 会话可变工作缓存 | state/tasks/rules/catalog真实SHA256+stage路径 | 替代原stat键；同size/mtime变化必须重新加载 |

内部read_history_view的共享事件/原始行是递归只读容器，metadata为私有副本。外部read_history_raw仍深拷贝，修改其返回值不会污染下一次读取；需要修改历史的导入/迁移代码保留可变接口。不可通过修改内部只读对象来运行游戏。

## 范围与回退

不更换存储后端、压缩格式，不删历史、开发证据、图源索引，不实施第三阶段NPC改造。V14.53现存经营缺资料、SKU未知、历史未模拟限制继续保留。仅未续玩时可以回退原V14.53；续玩后不得用旧ZIP覆盖新进度。
