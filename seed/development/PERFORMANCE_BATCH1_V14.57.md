# V14.57 第一批性能维护

父版本V14.56 / Engine 2.67.0；新Engine 2.68.0。Guard 2.21.0 / 协议4原字节不变。四个权威JSON、旧逻辑事件及物理历史字节守恒，仅追加一条零时间、无changes的维护记录。第二批未开展。

## 修改位置与所有权

`30_runtime_services`最终将`_history_read_verified`绑定到`_snapshot_history_read`；`_batch_b_history_read`保留原验证器，epoch解码经晚绑定服务。此次修改真实最终调用点。

* `10_selftest_and_diagnostics`：next_seq和追加批次只读ID、seq及元数据，改用共享只读视图。批次持有独立小元数据、ID集合、下一个序号和新事件bytes；原始读取的同一份bytes用于解析及替换绑定。锁、原文件SHA核验、重复ID拒绝、嵌套回滚、finally清理与持久替换保留。
* `26_reliable_runtime`：history层只读逻辑事件、数量、ID、next_seq。维持错误分类、连续性和metadata尾部验证。
* `02_authority_storage`、`28_snapshot_service`、`36_performance_context`：归档以实际读取bytes计算摘要，并将该bytes交给解码器。archive_ref通过JSON真实键发现，涵盖合法转义键，依赖清单按历史内容缓存。无作用域read_history_view也冻结返回值；公共read_history_raw继续返回独立可变结果。内部视图是所有权契约，并不是对任意Python恶意基类调用的代码沙箱。

## 提交验证与展示

run_checks(full=True)不是READY。它的accounts/content/memory/story/business输出来自readiness使用的同一纯验证器和相同参数，因此可直接复用；风险时钟、执行覆盖、恢复状态及其余层仍由真实readiness验证器补齐。完整记录各层状态、错误、限制、版本、检查选项、根路径及验证前后实际文件摘要。

暂存证明只能在原atomic_save完成manifest提交点、postcheck、receipt与cleanup并返回committed后，且实际发布manifest/组件/归档摘要仍相同，升级为published。发布目录必须有在该目录实际执行的sourcecheck证明，绑定开发材料、目录形状、权限与symlink链；暂存目录证明不能替代它。recovery journal、Guard完整性/协议、开发材料、最终身份和读取前后稳定性仍在当前边界核验。

内部证据仅由真实验证器运行产生，事务退出清理；命令JSON、提案、SAVED或full字段不能自报证明。缺失、无效或过期证据回到原可靠验证路径；真实损坏和恢复未完成仍阻塞。READY_WITH_LIMITATIONS和全部限制保留。

提交成功后的展示异常保留committed、原command_id与receipt并标FULL_FALLBACK，不换ID重做。跨版本结果标RESULT_VERSION_ALREADY_ADVANCED，不混入新版本报告。NPC先确定角色范围再投影一次；CLI已有身份/manifest/engine匹配的compact_v2时只做快照边界与最终JSON预算核验。

## 纯静态检查

沿用原编译入口，扩展为最多32项的进程内纯结果缓存。键含实际源码SHA、检查规则版本、Python实现/cache_tag/完整版本、解释器优化、编译flags/dont_inherit/optimize。只缓存编译成功；失败重新产生当前文件路径的异常。AST缓存纯结构结果，返回独立副本并附当前engine_path；解析错误不缓存，结构失败按内容隔离。源码、规则或解释器条件变化重新检查，合法修复不被旧失败阻挡。

未新增跨进程静态文件、pickle或可执行字节码缓存。磁盘不可写不会影响这些内存缓存。25_consistency_repair的Guard装载核对同一份源码bytes后直接编译执行，不加载独立pyc，也不在冷启动期间生成根目录__pycache__。Guard仍独立编译、执行协议核验subprocess；升级、builder和开发加载器的必要独立检查保留。独立CLI进程之间不共享静态缓存。

## 构建、诊断与验收

SOURCE_MANIFEST的imports/exports/captures与摘要经refresh_manifest.py更新，engine.py由build.py生成。独立完整审核也拥有SnapshotContext以复用该请求内已验证数据，不新增持久证明层。VOYAGER_DISABLE_VALIDATION_REUSE=1禁用验证/静态命中，VOYAGER_DISABLE_DERIVED_CACHE=1禁用原派生磁盘缓存，均不关闭验证。

原历史测试完整保留；本次新增当前父版本验收、性能脚本和forward版本案例，仅替换新案例中的旧版本迁移夹具，业务断言不变。所有交易、对白、推进、故障仅在SYNTHETIC副本。真实模型未调用，生成质量NOT_RUN。详细原始样本、源码摘要、故障结果与剩余瓶颈见同批验证报告。
