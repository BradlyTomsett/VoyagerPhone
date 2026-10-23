# 第三批契约：步骤13—16

版本V14.47 / Engine 2.62.0 / Guard 2.20.0。Guard恢复协议复用，外置守卫与包内guard.py逐字一致。

## 场景、人物、焦点

`story_action`含action对象；`story_transaction`含actions数组（1—80项），每项有type。两者均走既有DOMAIN_COMMAND_V2与可信host/有效grant、父存档检查、永久命令回执和原子提交。每项的精确目标进入授权范围；不接收任意JSON patch或Python。一个事务可组合注册、场景、披露、决策、提案等动作，全部成功或全部不提交。

动作：entity_register、scene_create、scene_phase、scene_focus、fact_append、fact_correct、knowledge_disclose、evidence_link、decision_open、decision_resolve、narrative_commit、narrative_rewrite、consequence_resolve、experience_record、experience_revoke。全部严格检查字段，金额/战力/库存等机械变更不能夹带。

人物先用entity_registry稳定ID；新注册写story_runtime_v1.entities并派生同一实体系统路由，拒绝同名/同别名不同ID。登记故事人物不增加舰员或资产。新场景参与者只收已登记ID。

每个task_scene_bindings保留一个开放场景硬约束，可跨任务并行。无显式焦点返回FOCUS_REQUIRED及可见候选，不凭数组顺序选故事；关闭焦点后清空。巡逻适配器继续同步原槽位、决策与任务阶段，要求显式patrol_adapter目标，不自动调舰。普通后台经济任务沿用原调度器。

维护不创建场景、人物或任务；旧白眠终态、故事原事实与原披露不改。场景location_label为故事标签，不是舰队/人物已移动的机械凭据。

例：`{"type":"scene_focus","scene_id":"SCENE-ID"}`；`{"type":"decision_resolve","scene_id":"SCENE-ID","decision_id":"DECISION-ID","player_action":"先听完对方，再核对现场"}`。任意自然语言选择均可，不强制固定选项。实际命令仍需当前base_save_set_id和独立授权。

## 知识矩阵与输出

| 角色 | 读取边界 |
|---|---|
| player | 明确披露的事实；传闻/假设保持原epistemic；已获知的更正另列，不覆盖原传闻 |
| observer | 仅该observer ID的已披露事实；不读取舰队资产专用入口 |
| NPC | 自己取得的事实、自己的主观陈述；不共享模型全局上下文；诊断读取须GM环境 |
| GM | 显式诊断上下文；不作为玩家输出的默认回退 |

新知情记录包含learned_at/channel/basis_event_id/record_event_id。当前事务证据用`$current_transaction`占位，由引擎绑定实际事件ID，避免自引用hash循环。旧记录保留原披露时间、来源与source_ref。霍克既有observer:HAWKE经明确身份路由连到npc:PER-HAWK-MALEN-01；未证明的其他身份不猜测映射。

知识命令：`knowledgequery --scene-id ID [--viewer player]`。NPC/GM视图在CLI需相应GM诊断参数和环境。已闭场景补历史披露必须有原事件中的明确披露证据，缺证返回HISTORICAL_DISCLOSURE_EVIDENCE_INSUFFICIENT，不能把全部隐藏真相公开。

统一player_output_policy筛除GM私有字段；scenequery/index、query/querybatch、启动、assetquery、pricequery、commandcatalog及新storyprojection使用受限输出。资产入口不返回迁移证据大对象，价格入口拒绝私有来源选择器。`storyprojection`供新UI消费已验证的玩家视图，显示实际版本、时间、焦点与稳定引用。旧静态UI仍是历史材料；完整UI/原图同步留在第4批17—18。

## 有边界的叙事导演

NarrativeDirector.context/validate/report分别对应narrativecontext、narrativevalidate、narrativereport。上下文按焦点/人物/地点标签/已知事实/主观陈述/未决后果/近期桥段取材，超预算返回引用和分页说明。初次确定的新稳定事实只经授权提交，不在查询或AI草稿时写入。

NARRATIVE_PROPOSAL_V1严格含：schema、base_save_set_id、scene_id、audience、intent_ref、basis_refs、draft_text、new_facts、claims、action_requests、consequence_requests、required_unknowns、narrative_tags。basis_refs支持当前已知fact/scene/fact-ID、已公开claim/proposal/index及已登记rule:ID。隐藏事实或NPC不知道的依据不能被提案借用。

new_facts限定appearance/atmosphere/goal/social_reaction/statement/intent/route_hint等故事谓词，并明确来源、epistemic及known_by。claims独立保存为rumor/hypothesis，不进入世界真相，后续上下文保留陈述者和来源事件。人物私有依据ID不在玩家叙事报告中输出。

action_requests只引用已经提交、effect_sha256匹配的命令回执，绝不因为一段文学描写重新支付或掷骰。未执行的硬动作需另走正式领域命令。草稿中的常见已付款/到账/到达/击毁和数值资源宣称会拒绝，硬结果单列verified_results。自由文本校验不是通用语义证明：模型仍须按已知事实写作，必要时人工重写；不能声称能自动识别所有隐喻或矛盾。

后果只支持social_response/pending_reply/scene_hook，记录cause_event_id、主体、场景、可见者、最早/最晚时间、所需新授权及状态。到时不自动执行；consequence_resolve需精确授权且当前时间在窗口内，已兑现不能再兑现。禁止借故事后果生成资金、装备或战斗结果。

narrative_rewrite只加文本修订，保留原提案和效果摘要，不重做世界动作。VOYAGER_DIRECTOR=0关闭新提案层，既有引擎、事实、人物及已提交选择仍可读取和运行。没有额外外部LLM服务、虚构平台签名或运行时改写Python；ChatGPT按上下文生成提案，再走现有可信授权路径。

## 可解释、可撤销的经验

白名单：intent_alias、source_success、failure_category、pattern_feedback、explicit_preference。每项必须有稳定entry_id与可信host当前明确指令的instruction_ref。不会从单次NPC行为推断永久偏好。偏好、工具错误、世界事实分开。

已知内置查询不能被别名覆盖，来源与主题必须匹配白名单。新别名只映射到公开、已知的标准主题。近期已提交桥段产生临时频率惩罚，不改变永久偏好；明确题材/节奏偏好及重复反馈只调整上下文建议顺序，不改变金额、战力、授权或Hazard种子。

`experience`从已验证历史回执重建统计；.runtime/experience_v1.json非权威、可删除、损坏可重建。experience_revoke追加撤销证据，保留原审计；已撤销ID不能复用。VOYAGER_EXPERIENCE=0关闭策略与别名复用。内置余额查询无需读取学习日志或解压全历史。

显式开发命令`python development/experience_review.py --base <source>`对重复失败产生只读修改建议，要求查原事件并增加回归；不会自动改代码或经济规则。

## 可复现检查及回退

新增测试：test_batch_c.py（3类剧情及完整流程）、test_batch_c_final.py（最终集成/开发真实写入）、test_batch_c_faults.py（故事人物与场景的部分写入恢复/未知字节保护）、test_batch_c_policy.py（旧知情身份路由/私有视图/内置查询与性能）。用VOYAGER_TEST_SOURCE指定源码，用各测试脚本说明的输出变量指定独立目录；所有写入均创建隔离世界。test_batch_c的输入保护使用包内batch_c_baseline_contract.json，不依赖临时目录或旧源码fixture。

旧batch_a/b审计与测试只适用于其原版本，不替代本候选证据。development/audit/batch_c保存实际执行结果；三类质量样本是隔离演示，非当前游戏剧情。硬约束通过与软文学评价分列，不将手工示例评价冒充自动文学质量证明。

回退保留V14.46完整ZIP与匹配Guard；没有新业务前可用原版本。发生新剧情或交易后必须兼容迁移，不能直接丢弃新事实。12:00—22:45未模拟风险缺口、原图外部依赖、原生平台身份注入不足及未知journal写入者边界均继续保留。
