# 第二批实现契约（步骤08—12）

输入V14.45；输出V14.46 / Engine 2.61.0 / Guard 2.20.0。维护零时间。Guard恢复协议未变，外置文件与包内文件逐字相同。

## 08 账户与经济事务

`engine.py accountquery [--account fleet|covert|shop|whitesleep_bridge]`返回精确字符串、整数最小单位、预留与可用额。主账直接引用finance_runtime.funds_units；潜伏与余火独立记铜；白眠过桥账户关闭、余额0。16金币采购和11720铜收转付属于已完成历史，禁止重播。任务旧值330.49银登记为历史快照；当前店账24530铜。旧float仅为兼容显示，新现金通过整数主账及带哈希cash ledger。账户查询是精确金额显示接口。

`DOMAIN_COMMAND_V2 kind=game_session`必需session_id/game_action/account_id/currency；reserve还需正整数stake_units及heads/tails。仅reserve→play→settle或reserve→cancel。预留不扣现，settle一次入账，cancel不虚构退款；每步需独立有效授权。coinflip_v1不推进世界时间。客户端不能声明输赢或授予权限。

`settle_price`对purchase/sale/liquidation要求可信完成事件的inventory_delivery与请求相同。六类标准补给按库存路径、数量、单位原子交割；其他资产在有专用适配器前拒绝通用入口。service/wage仍验证已完成服务凭证。报价不是授权或收款事实。

UI示例ui/minigame-request.html仅生成待核验请求；旧赌桌和脚本逐字封存于evidence/legacy_gambling，旧settle_dice.py立即拒绝执行。

## 09 服务与开发入口

从20_cli实质迁出授权与事务实现到19a/19b；27负责账户/小游戏，28负责快照与历史定位，29负责记忆/内容，30组合服务并解析、编码新只读命令。保留现有兼容包装，未因legacy命名删除可用路径。

| 接口 | 实际实现 |
|---|---|
| SnapshotReader | SnapshotContext、history_lookup、精确账户查询 |
| TransactionService | 原生提交和共享Guard恢复，保留父版本检查及manifest提交点 |
| AuthorizationService | 有效grant或可信host intent |
| RuleResolver | 内容检索和已绑定机械随机表 |
| SceneService | 原场景状态机与终态校验 |
| Scheduler | 原autoadvance及风险窗口，不另造模拟器 |

SOURCE_MANIFEST提供导出、导入、捕获和确定加载顺序；MODULE_CONTRACTS.json提供关系清单。开发runtime执行模块前验证实际SHA，缺导出/导入立即失败。修改领域模块后显式refresh_manifest.py、build.py、维护发布；导入不会运行迁移。字节码/运行缓存不进入开发源清单。

## 10 快照与派生索引

每次读取共享一把读锁和一套真实内容摘要；入口和输出前均重新哈希组件、全部冷档与开发源，不信任mtime。state/tasks/rules/catalog按需解析并在请求内复用。语义成功证明绑定全部真实hash、校验器版本及本机随机key认证；active journal每次检查。check --full始终执行实际完整检查。

.runtime下语义证明、event_id/command_id定位和增量索引均非权威，不导出。损坏/删除/字节变化即重建；VOYAGER_DISABLE_DERIVED_CACHE=1关闭复用，结果等价。key不被描述为能抵抗同账户文件权限敌手的安全边界。

追加索引验证旧body前缀hash，补尾并修正元数据头长度变化引起的offset；冷记录仅解压目标段。CLI在关闭时真实字节检查通过后才输出。VOYAGER_METRICS=1显示核心解析/解压/哈希计数。性能报告说明样本量，不声称设备端或ChatGPT响应时延。

## 11 热、暖、冷记忆

热层保留当前事实、任务、未决承诺、人物结局、白眠终态和当前焦点。历史交接及白眠三个已闭历史附件先做不可变gzip复制、逐对象hash核验，再切换显式cold_archive引用。暖摘要包含来源快照、原对象hash、覆盖范围和历史证据性质；无原始事件凭证时source_event_ids留空。摘要可从原对象重建，不提升传闻为事实。

`memoryread <原始点路径>`给玩家引用与安全摘要；--audience gm还须开发者GM诊断环境，按hash取回精确对象。`historylookup --event-id ID`或--command-id ID供GM核对原事件。账务绕过摘要，直接用完成凭证与原历史。

输入2538条逻辑事件原字节全部保留，仅加1条零时间维护事件。扩展不可变冷历史段，热尾64条；输入冷档逐字不动。输入ZIP为完整回退基线；发生新业务后不能重放维护或覆盖资金。

## 12 内容包

content_packages/schema.json及validate_content_package规定命名空间、schema_version、语义版本、rule_version、精确依赖版本、来源、可见性、单位和定义ID。组织/地点/设备/场景族/semantic_only文本可仅安装JSON；设备定义不增加玩家资产。机械表只接受已注册核心resolver；未知机械实现/单位、ID冲突、conflict_key矛盾、可执行字段均拒绝。价格仍走价格权威。

core随机表为旧函数精确返回值的数据迁移，table_id/row_id/权重/排序不变；既有规则额外门控字段不动。完整示例包单独提供，未默认安装。`contentquery [--kind semantic_rule] [--topic 关键词]`检索；content_install走已授权原生事务。既有package ID不可覆盖；更新或撤回需显式版本迁移，保留历史定义，本批没有自动卸载入口。

## 保留边界

12:00—22:45风险缺口仍为明确接受的未模拟区间，READY_WITH_LIMITATIONS；不改last_evaluated、种子、cycle及累积量。环境未提供原生ChatGPT身份注入，沿用可信host API与人工TTY签名管道。原图仍需外部原始ZIP；未知journal写入者未被宣称已定位。多场景和剧情表现属于步骤13以后。
