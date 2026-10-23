# V14.56 开发者扩展指南

Engine2.67.0、Guard2.21.0协议4；48开发模块，发布保持独立engine.py。正式升级只追加零效果维护记录，state/tasks/rules/catalog字节不变。

## 服务与依赖

实际边界由40_extension_services.ExtensionServices注册：apply/targets/cost从同一注册表分发，回退到第三阶段之前的原领域实现；第三阶段三类命令显式注册。不会给每个新kind再加一层全局包装。原授权、journal、fsync、manifest、恢复、永久幂等仍归旧服务。39之前历史层逐条审计：原55个_v130_layer_定义中，component_source_check_04与02的函数体AST完全相同，04保留名称并改为02的兼容别名，剩余54个定义保留。精确源码及AST摘要见evidence/stage4_merged_wrapper_proof.json；dependency_inventory.json列出调用/别名/捕获关系。没有根据函数名相似批量删除。

servicecontracts输出DAG、单位、可变所有权、错误和实际注册kind；SOURCE_MANIFEST的service_dependencies由builder/runtime在执行模块前校验。旧代码的晚绑定图可能有函数调用环，不等于初始化环；现有全局尚未全部消除。新模块顺序显式，未实现会减少独立引擎编译量的按需模块加载，不据拆文件声称更快。

## 纯数据包

例子在examples/content_v2，依次1.0.0、1.1.0、1.2.0。contentpreview --viewer gm --input @package.json生成包含完整base_identity、内容摘要、依赖、增加/变化/删除/弃用、破坏性项目、旧实例和限定迁移的计划。通过实际授权的content_upgrade提交原package和原plan。等待期间源改变必须重新预览；同版本不同摘要拒绝。当前依赖语法为逗号相交的==、>=、<=、>、<精确三段版本，检查正向/反向依赖和环；同命名空间不同包、重复ID、相同conflict_key均拒绝，人工修包解决冲突。

每包有namespace/version/schema_version/content_sha256/compatibility/source/migration_notes。摘要为除content_sha256外整个JSON规范序列化(sort_keys、UTF8、无空格)的SHA256。禁止code/python/exec/eval/script/write_path和价格字段；字符串只作资料，不执行。只有核心引擎迁移能修改封存random_tables，不能重置随机周期。

实际支持范围：scene_family通过content_scene_open消费，语义规则通过prepare_turn按tags/对象/有效期消费；equipment/location/organization支持严格schema和contentresolve版本读取，属于定义，不注册价格、资产、实际位置或所有权。新机械能力必须由开发者新增代码级validator、resolver、targets/cost/schema与回归，再构建引擎，不能在包里上传代码。

definition_ref固定package_id/version/definition_id/package_sha256。content_scene_open携带原scene_open动作并走原位置、参与者、可见性、玩法和授权；场景保存版本绑定。旧场景与旧定义不因升级变化。旧装备、已承诺价格、任务和随机序列不被内容包触碰。旧版本完整保留；有实例的定义不能删除，改为deprecated保留读取。新实例只能消费当前active且未弃用定义。

破坏性kind/unit/主版本变动必须为相关定义声明retain_version迁移，from_version指向已存在的原快照；唯一迁移类型只保留版本，不允许任意存档字段改写。业务实例迁移不在本版本支持范围，需新增受控代码方案。缺方案/坏迁移拒绝；所有写入位于native隔离工作副本并一次发布。卸载/降级不开放：不能用旧ZIP抹掉新事实；提交前可弃计划，提交后保留旧读取并前向修复。

## 记忆与经验

memorylayers划分热状态/可检索知识/已关闭场景冷知识；memorysearch支持viewer/entity/scene/query/time/分页，角色过滤发生在建索引前，按整个实际manifest和viewer绑定。派生HMAC缓存损坏、缺失、不可写安全重建；源记录、旧路径重定向、冷档和历史从未删除。memoryevidence fact/...仅返回该角色已知事实与其事件定位摘要；原完整事件与legacy:旧路径只允许GM诊断。来源摘要为精确投影，不把全知历史压缩后公开。

原experience显式反馈兼容保留。新experience_probe只能运行真实proposal_validation或memory_retrieval并记录真实状态码、输入/结果摘要、秒数和字节，不能接受调用者自报成功。experience_control的preference/revoke/enable/disable需真实host指令且instruction_ref一致，保留原反馈；推测偏好不支持。观察最多7游戏日、偏好最多30日、scope限retrieval/conversation/proposal；观测环境绑定Engine/rules/内容摘要。

策略只看最近64条观察，同一输入摘要不重复计票，至少两条不同失败证据才给最多3条交互提示，成功校验反例重置失败序列；每条事实最多向前移动2个位置。明确偏好优先；撤销保留事件，disable或VOYAGER_EXPERIENCE=0关闭机器策略仍执行全部安全检查。prepare返回strategy摘要，提交的decision_record记录策略版本、输入证据摘要和有限影响。retrieval/proposal scope可通过ObservedExperienceService.strategy（兼容类ExperienceService.strategy_v2）供宿主查询；自动prepare使用conversation scope。没有自动改代码、安装包、改变机械校验、资金单位、授权或RNG的路径。

## 扩展验证

修改devsrc，更新SOURCE_MANIFEST的显式captures/imports/exports/顺序与摘要，使用原build.py。运行开发/发布等价、第三阶段关键回归、连续内容升级、坏迁移、知识隔离、经验固定评估和规模基准。所有演示安装/交易/生成仅在新副本。ChatGPT实际生成质量未评估时必须NOT_RUN；固定台词/合成NPC不能冒充真实模型改善。
