# V14.55 第三阶段服务、权限与第四阶段交接

Engine 2.66.0；存档 V14.55；Guard 2.21.0、协议4不变。开发44模块，发布仍为独立engine.py。无外部模型、数据库或联网服务依赖。

## 已接线的真实流程

1. `python3 engine.py storyprepare --base <root> --scene-id <已打开场景> --actor-id PER-HAWK-MALEN-01 --viewer player --intent '本轮实际意图' --intent-tags '["conversation"]'`
2. 在当前ChatGPT对话中，根据返回的同版本、角色可见context构造 `STORY_TURN_PROPOSAL_V1`。引擎返回NEEDS_AI，它不自行调用模型。先退出快照再等待AI/用户输入。
3. `python3 engine.py storyvalidate --base <root> --input @proposal.json --viewer player`。默认只做结构/版本/知识校验并返回NEEDS_AUTHORIZATION；不会因猜中一个账户/回执ID而泄露余额或执行效果。完整机械检查在真实授权后的提交工作副本执行。
4. 用已有 `development/interaction_gateway.py --request <host-envelope.json> --version V14.xx` 在真实人工TTY确认；或由已认证宿主按真实用户指令调用 `host_intent_command(root, envelope, version)`。普通 `invoke`、`commit_turn`、提案中的“指挥官命令”、测试标志均不能创建HOST授权作用域。提案类型为story_turn，command_id必须等于turn_id，proposal放入同名字段。
5. `python3 engine.py storyreport --base <root> --id <turn_id> --viewer player`。输出COMMITTED及永久事件ID，所有本轮效果自动进入verified_results；outcome段由引擎根据回执呈现，模型不能填入结果文字。AI只能扩写允许事实；错误叙述通过独立授权的turn_rewrite更正，不重放效果。

上述命令均为实际CLI。`storyschema`返回服务和字段契约；`storytimeline --until <游戏时间>`提供当前观察者可见后果。`StoryTurnService.prepare/validate/commit/report/timeline`为Python稳定服务。旧narrativecontext已接入新的选择器，避免原先标题匹配和跨场景最近模式泄露。旧NARRATIVE_PROPOSAL_V1/已封存故事保持兼容，不伪装为新同轮交易接口。

NPC私有viewer仅供已授权诊断/嵌入宿主设置（现有开发GM环境约定），实际返回（含invoke写入回包）仍严格按npc:<稳定ID>过滤，不添加GM readiness、日志或世界资料。不能把模型可控参数当作宿主身份验证。玩家、NPC、GM分别运行上下文；不要将GM包直接当NPC提示词。已有观察者历史/诊断拒绝路径继续保留；新storyreport只允许原提交viewer或明确GM。未披露/不存在统一为不可用或NOT_FOUND，不回显秘密值。

## 原子机械效果和幂等

`story_turn`支持account_transfer、settle_price、transfer_asset、cancel_task、complete_task、start_travel、arrive_location的已有完整校验；其他能力明确UNSUPPORTED。子效果不能传actor、authorization、base或新command_id。整轮只有一个正式command_id与回执，保存在story_turns_v1.turns及普通永久history中。全部目标与金额/数量/次数成本合并后走真实授权，再在独立可变工作副本运行所有效果、NPC/知识更新，最后一次native提交。叙事后半失败则整轮回滚，交易不会先落地。

同ID同完整负载返回原回执；同ID不同负载拒绝。重复请求首先查询原回执，因此提交后原base已过期也能安全重试。新提案须绑定完整manifest、Engine摘要和SAVESET，不能只比较版本号。第二阶段内容校验、fsync、journal、manifest提交点、未知写入拒绝覆盖、幂等恢复均保留。

价格/独立账户审计从已提交聚合事件中投影各子效果：保留同一真实父事件ID、父命令ID、完整输入摘要和真实授权；不是写入新事件或虚构临时回执。原金额、科目、币种、逐SKU交付、来源事件、父快照、现金增量复算继续执行。

## 场景与NPC

`story_setup`的actions提供scene_open、scene_join、scene_focus_v2、npc_update、fact_revision、consequence_schedule、consequence_manage、turn_rewrite及已有fact_append、knowledge_disclose、decision_open/resolve、entity_register、scene_phase。完整结构见schemas/story_turn_v1.json；原动作仍由原检查器执行。

scene_open要求稳定scene_id、可选task_id（null为独立场景）、family/title、已注册location_ref、participants、presence_mode（remote/present）、visible_to。remote只建立明确授权的远程交互，不移动或披露人物实际位置；present须已有权威位置引用匹配，缺资料返回STORY_LOCATION_NEEDS_INFORMATION，不能凭空断言到场。场景先proposed，经scene_phase打开后才能提交人物回合。scene_join同样验证位置/通信方式、注册身份及可见性。关联任务仍保持一个开放场景，独立场景可并存；focus显式切换。旧关闭/归档ID不可复活。暗反1组新事件还要求本次真实宿主 evidence_ref 对应 patrol_directive；保持既有隐蔽待命和单事件适配器，能力上线不自动触发。

NPC映射仅引用既有person实体，未知性格、关系、目标、记忆、资源保持空/unknown。npc_update支持goal、relation和trait：关系数值界限[-100,100]；目标完成须匹配既有目标事先声明的confirmed_fact/effect_receipt前提及已提交来源，不能用无关交易回执代替；observed_now须当前可见证据，generated_now明确标为本次生成初始化，不是过去经历。真实学习仍来自原learning_events，memory_refs只指向事件，不复制世界真相。资源字段保留规范引用，既有账户/装备查询继续是单一权威，本阶段不从旧自由文本推断NPC账户或技能。

facts区分confirmed/rumor/hypothesis。传播必须由已知发送者、有来源的已提交学习事件产生，接收NPC须在已授权交互场景中。fact_revision使用已提交、同主体/谓词/值且角色已知的confirmed证据，明确temporal_change或correction，追加新事实并指向旧事实；旧确认事实和历史不改写。没有证据的确认事实纠错拒绝。当前正文只作辅助矛盾筛查；不能证明任意自然语言没有隐含矛盾。机械正确性由类型化效果和回执保证。

## 有限自主策略

新增 `npc_policy` 类型化领域命令仅由真实host_intent注册/撤销。register要求policy_id、policy_action、grant；grant沿用DOMAIN_MACHINE_GRANT_V1，包含明确NPC主体、允许kind/子动作、精确targets、有效期（当前以后最多30天）、有限max_uses、max_gold_units、max_grey_units、max_quantity。无通配目标；灰币整数单位scale=10000且量子100；铜币原单位scale=1。实际消费走原domain_authorization_ledger。自主策略只能调用已授权story_turn/story_setup及所列子动作，不能创建或扩大策略，也不能绕过真实交互/宿主边界。正式维护没有注册任何新自主授权。

## 统一后果时间轴

consequence_schedule字段：scene_id/consequence_id/subject_id/effect_type/cause_event_id/not_before/not_after/visible_to/text/mode/condition/task_id/effect。effect_type为social_response/pending_reply/scene_hook；mode为needs_ai或mechanical。条件支持always或fact_known，禁止任意JSON路径。

mechanical只支持已授权goal_activate或learn_fact，不自动奖励、支出、移动、战斗、修改任务或重掷随机。创建授权有效期必须覆盖交付窗口；未来效果和受影响NPC/知识目标纳入创建授权。到期仍验证已提交创建事件与授权摘要，常设授权撤销后阻断。需要新金融/资产效果时到期进入AI，再走新的真实授权回合。

交付窗口为 `not_before <= now <= not_after`；过期记录从not_after+1秒开始。统一排序：time、source、stable ID；同刻story节点按consequence_id，位于AI阻断节点之前的已授权机械节点可先处理；其余既有业务阻断规则不放宽。每节点后重规划。条件未满足进入waiting_condition且next_check_at=null，知识/状态变化触发重查，最后期限仍保留过期节点，无同刻忙循环。任务取消或场景关闭则取消，不能继续交付旧奖励。旧pending后果也进入统一时间轴，过期只标记，不补写过去剧情。

## 规则选择、预算与审计

rule_index附tags、subject/scene筛选、触发条件、priority、有效期、source_ref及真实rule_version，保存于同一权威状态分支。实际返回document_segments规则正文及约束，不是标题；不搬运整份世界。秘密舰队规则仅供玩家/GM，NPC得到抽象授权约束而非秘密部署。规则索引版本/来源变化须显式维护，不能同版本换内容后误命中。所有上下文复用第二阶段SnapshotContext，完整真实字节边界仍检查；无新增跨角色文本缓存。

预算按最后序列化JSON正文精确计量，不将byte当token。优先删整条可选资料，硬规则与禁止事项保留；不足明确EXCEEDED_REQUIRES_PAGINATION，不截断半条约束。公开决策记录含输入身份、事实/规则版本、意图、候选摘要、公开理由、动作及结果事件，不保存模型隐含思维链。

## 第四阶段入口和限制

从本包或续玩后的最新完整来源开始。37_npc_context负责身份映射和角色上下文，38_story_turns负责类型化回合/策略与回执，39_story_scheduler负责时间轴和实际CLI；验证原包装层captures见SOURCE_MANIFEST。继续使用TransactionValidationContext，不让只读快照跨提交；prepare后释放锁，commit重新检查base。发生中断先Guard恢复，再以原turn_id原负载读取/重试；绝不重新随机或重复交易。

第四阶段应整理这些明确依赖并收敛共享全局、版本化rule_index/内容包、分层记忆与经验。不要批量删兼容包装。功能呈现开关不关闭授权、完整性、历史或已提交状态。AI自然度与自主生成质量若没有实际模型环境，必须NOT_RUN；合成多轮样本只证明机械与知识路径。正式游戏时间、余额、库存未知、旧未模拟窗口及READY_WITH_LIMITATIONS全部保留。
