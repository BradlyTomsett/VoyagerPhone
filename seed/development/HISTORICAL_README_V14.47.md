# 最新交付：V14.47 第三批

先读BATCH_C_V14.47_HANDOFF.md及BATCH_C_V14.47_CONTRACTS.md。旧批次审计仅供其原版本参考；不自动重放迁移、剧情或资金记录。

# 最新交付：V14.46 第二批

本版先读 [BATCH_B_V14.46_HANDOFF.md](BATCH_B_V14.46_HANDOFF.md) 和 [BATCH_B_V14.46_CONTRACTS.md](BATCH_B_V14.46_CONTRACTS.md)。旧交接与旧迁移脚本仅供对应版本历史核验，禁止重复入账。

# 当前交付：V14.45 / Engine 2.60.0 / Guard 2.20.0

第一批步骤00—07的当前说明见 `BATCH_A_V14.45_HANDOFF.md`。构建清单为28个模块，以devsrc/SOURCE_MANIFEST.json为准。
当前风险历史含指挥官已认可的未模拟窗口，因此就绪状态为READY_WITH_LIMITATIONS。
下面保留旧开发说明作为历史参考，旧audit结果不代表本候选已验收。

# 远航者开发源码 V14.19

`devsrc/*.py` 是唯一可编辑的引擎源码。`engine.py` 是带 `GENERATED FILE` 标记的发布构建产物；不要直接修改它。`guard.py` 是配套引导器。运行端使用 ZIP + Guard，无须安装开发模块或第三方依赖。

## 模块与依赖

`devsrc/SOURCE_MANIFEST.json` 按初始化顺序列出 25 个模块，各项明确列出导出符号、跨模块导入符号和源码摘要。`devsrc/runtime.py` 在独立命名空间执行模块，并通过这份导入/导出契约保留旧版晚绑定函数与初始化顺序。`build.py` 验证摘要并生成相同顺序的单文件运行引擎。新模块源内容可由开发入口直接运行，发布时被内联为单文件，以免手机端安装模块。

| 位置 | 职责 |
| --- | --- |
| prelude, authority_storage, text_policy_core | 公共数据结构、权威文件与规则基础解析 |
| save_transactions, turn_session_runtime, delivery_packaging | 事务提交、检查点恢复、交付 |
| query_layer, mobile_read_cache, scene_visibility, bootstrap | 历史索引、查询、可见性与启动读取 |
| finance_domain, domain_commands, battle_transaction, scene_commands | 财务、资产与业务命令；写入仍走统一授权和事务入口 |
| scheduler, mechanics_hazards, simulation_runtime, combat_core | 已有时间、任务与机械规则 |
| migrations, legacy_migration, p2_contracts | 明确触发的迁移与协议兼容 |
| development_tooling, selftest_and_diagnostics, health_and_upgrade, cli | 开发检查、公开入口和兼容命令 |

`SOURCE_MANIFEST.json` 的符号表是跨模块契约。更新业务时编辑对应模块；改变公开行为先确认 `cli`、授权和事务调用。不要只移动函数定义：别名在初始化时绑定，调用时又可能使用最终实现。现有 `devsplit/devbundle` 公开命令仍保留为旧接口适配，但不再是开发编辑入口。多层历史实现尚有保留：它们会被动态注册或自测引用，本批未在证据不足时删除。

## 构建与验收

在包含 `development/` 的目录执行：

```
python3 development/refresh_manifest.py
python3 development/build.py --output engine.py
VOYAGER_ROOT=/绝对路径/当前存档 python3 development/devsrc/runtime.py query 当前金币余额
python3 engine.py --version-info
```

首次迁移采用引擎 `engineupgrade --candidate` 统一入口，绑定同目录匹配 Guard。完成后用 `guard --resume`、`check --full`、`refcheck`、普通查询、授权拒绝、预览、真实事务、重复请求、恢复与场景可见性回归。不得以构建或导入成功代替业务回归。生成内容不写入构建时间或本机路径；相同源码摘要生成相同引擎 SHA-256。

完整源码 ZIP 的 `development/` 成员由 manifest 逐文件 SHA-256 绑定。Guard 解包前验证，运行时不加载这些成员；交付后的新对话应从最新 ZIP 的 `development/` 继续编辑、构建，再走 Engine/Guard 版本绑定升级。


## V14.21 价格执行稳定化

开发源码共26个模块。16a_pricing_domain位于finance_domain之后；发布engine.py仅由build.py构建。

只读接口：`pricequery --input <JSON>`、`pricequote --input <JSON>`。请求必须有item_id或price_id、quantity、unit、currency；地区、渠道、配置须符合该锚点。也可用已登记别名source_ref查价。缺依据返回NEEDS_EVIDENCE；参考区间未确认单价返回PROVISIONAL；来源变更后的旧报价返回STALE。

正式议价marketoffer必须带price_context和currency；报价验证不授权交易。invoke的settle_price仅处理已经确认完成的交易现金腿，须有原有machine_grant、明确账户及confirmed_price_settlement事件；实物交付和处置权仍按既有资产规则执行。price_evidence_register和price_policy_update分别登记已有规则的范围证据、授权科研政策更新。禁用商业命令未开放。

session可自动登记既有缺价规则允许的同规格参照；新经济数值通过economic_effects绑定quote或quote_request；不得直改余额、授权和价格权威。实际外部参照必须留存retrieved_price_reference事件（可核实URL、检索时间、规格、单位、美元报价和购买力参照）；模型记忆不能作为检索来源。真实同类性、例外真实性、组织规模和处置权仍需语义判断。

验收：`python3 development/tests/test_pricing.py .`。所有测试交易、政策变更和场景披露使用独立一次性存档副本。测试结果写到父目录；不在玩家存档上试验交易。


## 一致性修复入口（第 2 步）

本轮新增模块的加载顺序、摘要、导入与导出以 `devsrc/SOURCE_MANIFEST.json` 为准。
`captures` 在新模块执行前捕获旧公开绑定，保留旧 CLI 包装；发布引擎仍由原 build.py 生成。

修复 CLI 需要原有显式 GM 开发诊断环境：`VOYAGER_DEVELOPER_MODE=1` 和
`VOYAGER_DIAGNOSTIC_CONTEXT=gm`。这不授予任何游戏交易或推进权限。
先运行 `engine.py repairplan --base <根目录>`，把完整 JSON 结果保存到根目录之外；
复核后用 `engine.py repairapply --base <根目录> --plan <计划文件>` 执行。
计划绑定所有实际组件、工具、冷归档和开发成员摘要；执行前完整重新推导并精确比较。
拒绝任意补丁、过期计划、未验证归档及证据冲突。无变更计划返回 NO_CHANGE，不追加事件。
完整业务审计的失败独立保留；计划存在或修复提交成功均不表示整份存档通过业务审计。

允许自动修复的范围为：已验证完整逻辑历史的 next_seq；已入账凭据、注册任务与
现有金额和数量完全一致时的派生时间镜像；注册价格镜像到唯一现存嵌套字段或其
注册固定价格 value_ref 的引用迁移；注册事件与任务 current_event_stage 的镜像。
生命周期 status、事件处理 phase 和任务处理 phase 含义不同，不要求字符串相等。
未证明的时间、结算、风险时钟、随机历史、数量、归属、价格和授权不能自动补齐。

修复复用原有锁和持久写入，在 `.runtime/consistency_repairs` 中保存父/目标快照、
计划和审计结果，以 manifest 为提交点。Guard 启动先恢复活动修复日志；也可显式
调用 `repairrecover`。提交点前恢复父快照，提交点后保留目标。发现未知第三方写入、
损坏快照或开发/工具绑定变化时拒绝覆盖。活动日志未恢复期间普通读取和提交拒绝加载。
不得删除整个 `.runtime`。已有历史行、冷归档、原授权与随机运行时保持不变；仅通过
原事件追加器记录一条零时间、小体积修复审计，不写整份 before/after 状态。

运行针对性回归：`python3 development/tests/step2_consistency.py`。
它只在新副本执行交易式修复、历史追加和故障注入，测试标识由权威数据或测试摘要派生。
可用 VOYAGER_STEP2_TEST_SOURCE、VOYAGER_STEP2_TEST_OUTPUT、VOYAGER_STEP2_FIXED_INPUTS
指定来源、独立输出目录及固定输入记录。输入记录只是基线，不参与修复判断。

修复运行同样不加载或要求开发目录。提供完整源码包时会验证实际 development 成员；
未部署这些成员时，只保留 manifest 中的声明绑定，并明确报告开发成员未物化，
工具能力来自当前单文件引擎和匹配 Guard 的真实字节/协议验证。恢复日志绑定这一
读取范围；恢复期间开发目录突然出现、消失或改变会拒绝覆盖。完整源码导出仍需要
声明的开发成员都存在，不能把未物化声明当成已经验证过的源码包。


## V14.43 (latest)
See `CONTINUE_V14_43.md` for 8363-12-02 22:45 complete current handoff. Old V14.42 guide is historical, not current.
