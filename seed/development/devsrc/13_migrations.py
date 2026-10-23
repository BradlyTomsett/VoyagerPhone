# === VOYAGER_DEV_MODULE: migrations ===
def _split_world_static_catalog_text(text:str)->tuple[str,dict]:
    rpat=re.compile(r'<!--\s*'+re.escape(RUNTIME_RULES_MARKER)+r'\s*(\{.*?\})\s*'+re.escape(RUNTIME_RULES_MARKER)+r'_END\s*-->',re.S)
    m=rpat.search(text)
    if not m:raise EngineError('WORLD_RUNTIME_RULES_BLOCK_MISSING')
    rr=strict_json_loads(m.group(1));existing=parse_world_static_catalog(text)
    catalog=copy.deepcopy(existing) if existing else {'schema':STATIC_CATALOG_SCHEMA,'catalog_revision':'V1','combat':{}}
    combat=catalog.setdefault('combat',{});ce=rr.setdefault('combat_evaluation',{})
    ship=ce.setdefault('ship',{});cship=combat.setdefault('ship',{})
    for k in ('weapon_base','shields','specific_models'):
        if k in ship:cship[k]=ship.pop(k)
    ground=ce.setdefault('ground',{});cground=combat.setdefault('ground',{})
    for k in ('powered_armor_nominal_bonus','combat_robot_nominal_g'):
        if k in ground:cground[k]=ground.pop(k)
    for k in ('engineering_robot_nominal_g','armored_vehicle_nominal_g'):
        src=ground.get(k)
        if isinstance(src,dict):
            moved={kk:vv for kk,vv in src.items() if not str(kk).startswith('external_')}
            remain={kk:vv for kk,vv in src.items() if str(kk).startswith('external_')}
            if moved:cground[k]=moved
            if remain:ground[k]=remain
            else:ground.pop(k,None)
    air=ce.setdefault('air_ground',{});cair=combat.setdefault('air_ground',{})
    if 'models' in air:cair['models']=air.pop('models')
    if 'reconnaissance_equipment' in rr:catalog['reconnaissance_equipment']=rr.pop('reconnaissance_equipment')
    catalog['model_counts']={
        'ship_specific_models':len(((cship.get('specific_models') or {}))),
        'ground_powered_armor':len(((cground.get('powered_armor_nominal_bonus') or {}))),
        'ground_combat_robots':len(((cground.get('combat_robot_nominal_g') or {}))),
        'aircraft_and_auxiliary':len(((cair.get('models') or {}))),
        'reconnaissance_equipment':len((catalog.get('reconnaissance_equipment') or {})),
    }
    rblob=json.dumps(rr,ensure_ascii=False,separators=(',',':'))
    text=text[:m.start()]+f'<!-- {RUNTIME_RULES_MARKER}\n{rblob}\n{RUNTIME_RULES_MARKER}_END -->'+text[m.end():]
    cpat=re.compile(r'<!--\s*'+re.escape(STATIC_CATALOG_MARKER)+r'\s*(\{.*?\})\s*'+re.escape(STATIC_CATALOG_MARKER)+r'_END\s*-->',re.S)
    cblob=json.dumps(catalog,ensure_ascii=False,separators=(',',':'))
    cm=cpat.search(text)
    block=f'<!-- {STATIC_CATALOG_MARKER}\n{cblob}\n{STATIC_CATALOG_MARKER}_END -->'
    if cm:text=text[:cm.start()]+block+text[cm.end():]
    else:
        rm=rpat.search(text)
        if not rm:raise EngineError('WORLD_RUNTIME_RULES_BLOCK_REWRITE_FAILED')
        text=text[:rm.end()]+"\n\n"+block+text[rm.end():]
    return text,catalog

def _sync_engine_upgrade_world_protocol(stage:Path,candidate_version:str)->dict:
    """Synchronize machine-facing WORLD contracts for the current Engine generation."""
    p=stage/'WORLD.md'
    if not p.is_file():return {'changed':False,'reason':'WORLD_NOT_PRESENT'}
    before=p.read_text(encoding='utf-8');text=before
    text=re.sub(r'^(> \*\*设定修订号\*\*：)V7\.0-R5$',r'\g<1>V7.0-R6',text,count=1,flags=re.M)
    text=re.sub(r'^### RULE-ENGINE-AUTOMATION-01 GAME ENGINE v[^\n]+确定性自动化、任务分类与事件驱动$','### RULE-ENGINE-AUTOMATION-01 GAME ENGINE确定性自动化、任务分类与事件驱动',text,count=1,flags=re.M)
    text=text.replace('权威任务对象使用`TASK_OBJECT_V3`','权威任务对象使用`TASK_OBJECT_V4`')
    text=text.replace('`COLD_START_PACKET_V2`、stable refs','`COLD_START_PACKET_V5`、stable refs')
    old_re=r'- AI不得直接覆盖权威工具。`engineupgrade`至少执行：版本严格递增、Python编译、selftest、最近3个SAVESET读取兼容、候选迁移完整校验、当前Engine与候选进行\*\*5组交替配对exact query/routineplan采样，并以组内耗时差/比率中位数比较\*\*，并在只含五个权威来源\+候选Engine\+绑定Guard的全新隔离目录内真实执行`sourcecheck → Guard → boot → exact query → routineplan`；最后才允许纯升级零游戏时间和新SAVESET提交。.*$'
    new_upgrade='- AI不得直接覆盖权威工具。`engineupgrade`至少执行：版本严格递增、Python编译、selftest、最近3个SAVESET读取兼容、候选迁移完整校验、当前Engine与候选进行**5组交替配对exact query/routineplan采样，并以组内耗时差/比率中位数比较**，并在只含五个权威来源+候选Engine+绑定Guard的全新隔离目录内执行`sourcecheck → Guard/Resume → exact query → routineplan`；最后才允许纯升级零游戏时间和新SAVESET提交。升级硬门在一个受控Python进程内以**独立模块命名空间+固定VOYAGER_ROOT**调用baseline/candidate/Guard函数，并用父Engine `ITIMER_REAL` deadline对长门fail-closed；不得为每个兼容/性能/冷启动样本反复启动Python解释器。PUBLISH后仍必须用真实外部CLI执行一次八组件新对话验收。'
    text=re.sub(old_re,new_upgrade,text,count=1,flags=re.M)

    def replace_rule(src:str,rule_id:str,block:str)->str:
        pat=re.compile(r'^### '+re.escape(rule_id)+r'[^\n]*\n.*?(?=^### |^## |\Z)',re.M|re.S)
        b=block.strip()+"\n\n"
        if pat.search(src):return pat.sub(b,src,count=1)
        return src.rstrip()+"\n\n"+b

    text=replace_rule(text,'RULE-PROGRESS-RULE-01','''### RULE-PROGRESS-RULE-01 通用固定速率进度解释器
- `PROGRESS_RULE_V1`适用于已明确封板`target + rate_per_second + minimum + maximum`的科研、探索、训练、建设、解码、数据恢复等持续机械进度；从启用`CONTINUOUS_PROGRESS_CONTRACT_V1`的存档起，active任务一旦保存明确的数值`*_progress_pct/*_completion_pct`且尚未完成，就必须由`progress_rule_v1`负责机械进度，`requires_ai_review=false`，并保存`last_reviewed_at`作为速率积分起点。
- 连续数值进度的canonical target必须落在STATE；TASKS只通过stable ref/view_rule读取当前事实，active任务不得再把未完成的`*_progress_pct/*_completion_pct`作为第二份current镜像保存在`task_data`。缺少封板速率、上下限或时钟起点时必须fail-closed，Engine不得从已完成百分比、经过时长或剧情文字反推速度。
- 调度器不得仅依赖人工填写`next_review_at`：合法`progress_rule_v1`任务至少在本次时间推进终点自动结算，并优先在显式复核点、repeat周期、下一milestone或上下界处结算，因此不会再出现“时间已经推进但进度数值停住”的静默遗漏。
- 数据损坏、敌袭、未知系统启动、科研含义等真正语义异常必须建立独立AI watcher（可用`WATCH_CONDITION_V1`）；不得让AI watcher同时承担固定速率数值增长。milestone若需要生成新的语义事实，只能形成Semantic Barrier，不能由进度解释器自由生成。''')

    text=replace_rule(text,'RULE-EXTERNAL-COMBAT-EQUIPMENT-AUTOGEN-01','''### RULE-EXTERNAL-COMBAT-EQUIPMENT-AUTOGEN-01 外部同类新型号注册与战斗调用边界
- **战斗现场禁止新型号物化。** `battleprepare`只能调用已经注册进WORLD运行时目录或`STATE.engine_runtime.combat_runtime.registered_models`的型号；`new_model_creation=false`。未知武器/载具/机器人不得为了完成一场战斗临时生成。
- 新型号仍可在正常世界演化中出现，但其**首次持续性事实**必须来自明确的科研、军工、市场、采购、缴获鉴定、指挥官设定或其他已发生事件，并在进入任何战斗前完成型号注册、来源记录与专项值封板。
- 型号只能落入现有合法装备类别；不得在战斗现场创造新的武器类别。单兵枪械类别仍仅限步枪/手枪/霰弹枪，单兵重武器仍仅限手雷/一次性火箭筒/单兵导弹，其他既有舰载/机器人/航空类别按对应RULE执行。
- 合法的新型号数值生成继续服从既有优先级与外部同类≤我方70%硬上限；已有系列代际锚点可用于**战斗前的型号注册事件**，但不得把规则推导模板解释为型号已经存在。
- 型号名义值与具体批次成色、舰龄、损伤分离；已注册专项值后后续直接复用，不重复乘来源系数。''')

    text=replace_rule(text,'RULE-COMBAT-MISSING-DETAILS-SEAL-01','''### RULE-COMBAT-MISSING-DETAILS-SEAL-01 战斗缺失资料的权威封板
- AI不得为即将发生的战斗直接补造敌方资产、人数、装备型号、攻击力、防护值或库存数量。
- 缺失机械资料只能由Engine从以下来源物化：当前STATE已有实体、WORLD稳定基线、已经写入STATE的sealed encounter/profile、或带来源与置信度的INTEL_ESTIMATE；任何资产数量仍受对应当前力量池与revision约束。
- 已知兵力规模但缺具体型号时，只能使用该势力已经注册且有库存依据的型号/合法封板模板；不存在合法来源时保持未知并形成Semantic Barrier，不得为了让`battlecalc`运行而补数。
- 每个首次成为持续性事实的封板资料必须带authority path/source event/revision，并在后续战斗复用；不得重掷。产权、国家身份、重大政治后果等仍属于语义/指挥官决策门。''')

    text=replace_rule(text,'RULE-COMBAT-ENGINE-STATE-01','''### RULE-COMBAT-ENGINE-STATE-01 战斗三阶段机械状态机
- 战斗固定使用`battleprepare → battlecalc → battlecommit`。`battleprepare`只接受战术意图、来源引用、单位authority字段映射和已注册型号；**禁止直接输入attack/shield/armor/hull/ammo/accuracy/evasion或任意自由倍率**。Engine从当前权威STATE/已封板profile重新构建`BATTLE_SNAPSHOT_V2`。
- 每个战斗side必须声明`STATE_EXISTING / WORLD_BASELINE / SEALED_ENCOUNTER / INTEL_ESTIMATE`之一，并能解析到现有authority或`STATE.external_force_registry`。外部持续力量必须携带匹配的force revision；不存在的组织/部队/舰船不得进入计算。
- `battlecalc`只接受可由其`prepare_request`从当前authority**重新生成并完全复现**的快照，按WORLD固定seed和`BATTLE_RESOLUTION_V2`计算距离、命中、护盾、装甲/船体、弹药、撤退、毁损与机械胜负。未注册战术只有`TACTIC_STANDARD`；需要额外战术倍率时必须先在WORLD明确注册，AI不能自定数字。
- `battlecommit`是唯一正式战后提交点：机械写回、外部力量池减员/装备扣减、玩家阵亡永久人员扣减与汇总镜像、维修/医疗任务入队、同舰队补充计划、force revision、待鉴定战利品、battle sequence与HISTORY在**同一事务**完成；任一子步骤失败则整个SAVESET不产生。`battle_id`已提交时硬拒绝重复结算。
- 人员伤亡若WORLD尚无确定性伤亡公式，则使用`semantic_sealed_commit_until_formula_registered`：AI/战报可给出一次封板的伤亡分类，但Engine必须检查分类总量不超过战前权威数量。玩家舰队当前只把**阵亡**作为永久人员总数扣减；负伤可进入`MAINTENANCE_RUNTIME_V1`医疗队列，失踪/被俘等在缺乏更强规则前仅保留状态账，不擅自永久删人。
- 战利品默认只进入`pending_loot`，在产权/证物/鉴定完成前不得计入库存或资金。战后同舰队舰载补充继续服从`RULE-SAME-FLEET-SHIPBOARD-REPLENISH-01`；禁止跨舰队自动抽调或因缺编自动采购。
- 对无法由已注册机械字段表达的未知武器效应、特殊遗迹、剧情性投降条件等，必须停在Semantic Barrier。''')

    if 'RULE-COMBAT-FORCE-CONTINUITY-01' not in text:
        text += '''\n\n### RULE-COMBAT-FORCE-CONTINUITY-01 外部战斗力量连续账
- `STATE.external_force_registry`是持续性外部武装力量的当前机械账；每个force拥有单调递增`revision`、`as_of`、人员/装备当前量或情报估计范围及累计伤亡。
- 每次战斗只能从当前revision调用兵力；战后`battlecommit`扣减并产生下一revision。下一次战斗必须从新revision继续，禁止恢复到旧人数/库存。
- 招募、补充、生产、军援、缴获入编等可以增加力量，但必须由独立已发生事件形成新的revision；不得在下一场战斗开始时隐式补回。
- 已知量使用confirmed；只有情报本身是范围时才使用estimate_range。任何扣减不得使confirmed为负或突破估计上界。
'''
    _auto_old='- `AUTOMATION_RULE_V1`是通用确定性自动化层，允许的机械原语为`set / increment / append / transfer / consume / schedule / compare_set / emit_history`；`SETTLEMENT_RULE_V1`把固定日结的金额来源、STATE/TASKS更新、下一触发和财务账户改为WORLD/TASKS数据规则。规则只能操作当前事实和HISTORY事件，不得自行生成剧情事实。'
    _auto_new='- `AUTOMATION_RULE_V1`是通用确定性自动化层，允许的机械原语为`set / increment / append / transfer / consume / schedule / compare_set / emit_history`；循环automation可用声明式`self_updates`、`status_template/next_trigger_template`同步业务时间戳与任务镜像。`SETTLEMENT_RULE_V1`把固定日结的金额来源、STATE/TASKS更新、下一触发和财务账户改为WORLD/TASKS数据规则；`deterministic_unit_sales`若历史逐包子账不完整，必须显式声明authoritative cumulative/current-round/time targets，禁止用不完整子账倒写当前累计。规则只能操作当前事实和HISTORY事件，不得自行生成剧情事实。'
    if _auto_old in text:text=text.replace(_auto_old,_auto_new,1)
    _watch_old='- `WATCH_CONDITION_V1`允许watcher用最多16个canonical STATE路径或`ref:<KEY>`生成确定性SHA-256状态指纹；只有当前指纹不同于`baseline_digest`时才形成AI语义复核门。无变化的时间推进不得周期性唤醒AI；路径无法解析时fail-safe为AI复核。watch条件只决定是否需要语义复核，不自行解释状态变化。'
    _watch_line='- `WATCH_CONDITION_V1`允许watcher用最多16个canonical STATE路径或`ref:<KEY>`生成确定性SHA-256状态指纹；只有当前指纹不同于`baseline_digest`时才形成AI语义复核门。`routineplan/process`、Turn Session与`autoadvance`都必须使用当前STATE重新计算该指纹，不得因缺少STATE参数把watcher静默视为未触发。无变化的时间推进不得周期性唤醒AI；路径无法解析时fail-safe为AI复核。触发后Engine只报告`current_digest`与变更屏障，不自行解释或自动确认变化；AI完成语义复核后，继续推进前必须通过权威TASKS补丁把`baseline_digest`重置为已复核的`current_digest`，或明确替换/关闭该watcher。'
    _watch_anchor='- `AUTOMATION_RULE_V1`是通用确定性自动化层'
    if _watch_old in text:text=text.replace(_watch_old,_watch_line,1)
    elif _watch_line not in text and _watch_anchor in text:
        lines=text.splitlines();i=next((j for j,x in enumerate(lines) if x.startswith(_watch_anchor)),None)
        if i is not None:lines.insert(i+1,_watch_line);text='\n'.join(lines)+('\n' if before.endswith('\n') else '')

    text=replace_rule(text,'RULE-ENGINE-MAINTENANCE-01','''### RULE-ENGINE-MAINTENANCE-01 维修、医疗与同舰队补充的Engine运行时
- `STATE.engine_runtime.maintenance_runtime`是维修/医疗机械节点与待补充缺编的当前运行时队列；`repair_queue`与`medical_queue`只保存active任务，完成后移入`completed_jobs`，权威历史仍追加HISTORY。
- 单次维修/治疗`complete_at`必须在正式开始后且不超过30个游戏日；Engine不得生成赶工费、加速费，舰队内部医疗不得自动扣金币或医疗包。维修项目可并行，不能为了排队人为串行延长。
- `routineplan`、`autoadvance`与Turn Session把TASKS确定性节点和维修/医疗runtime节点合并排序，并在**每个机械节点后重新规划**。因此上一节点新产生的维修完成、医疗出院、日结等必须在同一轮继续被发现。
- 维修完成写回只能使用已封板、白名单化的completion action并执行compare-and-set；若目标或设计源在等待期间发生变化，整项completion action不部分执行，任务转入`blocked_jobs`并在该时刻形成Semantic Barrier。
- `STATE.engine_runtime.player_fleet_registry`只保存稳定authority路径/库存绑定等机器路由元数据，不另存一套人员或库存事实。玩家阵亡由`battlecommit`通过该registry同步primary personnel与summary镜像；负伤恢复通过医疗队列追踪，不自动补员。
- 战后舰载装备自动补充只允许使用registry显式登记的**同舰队、同型号、公共可用库存**绑定。Engine不得扫描名称相似的旧version字段猜库存，不得跨舰队抽取，不得自动采购；没有canonical绑定或同舰队库存时记录`pending_replenishment`并保持缺编。兼容型号替代只有在以后存在明确机器兼容表时才允许自动执行。''')

    if 'RULE-STATE-CANONICAL-REF-01' not in text:
        text += '''\n\n### RULE-STATE-CANONICAL-REF-01 当前态稳定引用与版本路径退役
- 当前动态事实只保留一个canonical对象；版本号属于事件/revision，不属于长期字段路径。新增任务不得继续绑定`*_current_vNNN`式路径。
- TASKS可使用`ref:<KEY>`稳定引用，由`STATE.engine_runtime.state_refs`解析到当前canonical路径；Engine读取、校验、归档均先解析stable ref。
- 旧版本current镜像与continuation/current_bridge属于迁移历史或可重建缓存，完成引用迁移后必须归档HISTORY并从当前STATE/TASKS删除，不得继续双写。
'''

    text=text.replace('- TASKS可使用`ref:<KEY>`稳定引用，由`STATE.engine_runtime.state_refs`解析到当前canonical路径；Engine读取、校验、归档均先解析stable ref。','- TASKS/Engine可使用`ref:<KEY>`稳定引用，由`STATE.engine_runtime.state_refs`解析到当前canonical路径；Engine读取、校验、查询和归档均先解析stable ref。')
    _canon_tail='- 旧版本current镜像与continuation/current_bridge属于迁移历史或可重建缓存，完成引用迁移后必须归档HISTORY并从当前STATE/TASKS删除，不得继续双写。'
    if '已被更大当前对象吸收的旧`*_current_vNNN`不得改名成第二个current' not in text and _canon_tail in text:
        text=text.replace(_canon_tail,'- 已被更大当前对象吸收的旧`*_current_vNNN`不得改名成第二个current；仍需查询的封板细节应嵌入当前父对象的明确子组件，旧顶层路径完整归档HISTORY后删除。\n'+_canon_tail,1)

    text=replace_rule(text,'RULE-NARRATIVE-STATE-DERIVED-CACHE-01','''### RULE-NARRATIVE-STATE-DERIVED-CACHE-01 STATE剧情摘要派生缓存（V9.46退役）
- V9.46起`STATE.narrative_state`不再属于当前STATE允许结构。该缓存曾用于早期大存档冷启动，但维护成本会产生陈旧剧情线和失效authority引用，现已由`SAVE_GUARD --resume`返回的`COLD_START_PACKET_V5`、`STATE.engine_runtime.state_refs`和active TASKS按需精确查询替代。
- 新对话不得寻找、重建或优先读取`narrative_state`；需要剧情上下文时从当前active TASKS/stable refs取得当前态，并仅在确需历史原因时精确检索HISTORY。
- V9.45及更早SAVESET中的`narrative_state`仅为升级迁移兼容可读的非权威旧缓存，不得覆盖结构化当前事实，也不得复制进V9.46及以后新SAVESET。''')
    text=replace_rule(text,'RULE-PLAYER-VESSEL-LOCATION-AUTHORITY-01',"""### RULE-PLAYER-VESSEL-LOCATION-AUTHORITY-01 我方舰艇当前位置单一权威与按舰查询
- **远航者舰艇当前位置唯一权威**：`STATE.voyager_fleet.current_location_partition`。`vessel_roster`只负责身份/舰级/编号；`named_vessels`不得再保存`location/current_location/current_location_status/location_id/location_name`或`at_*`式状态来复制当前位置。未列入deployment/transit的远航者现役舰，按分区计入远航者基地。
- **暗影现役机动舰位置唯一权威**：`STATE.shadow_fleet.current_location`；逐舰`location/current_location/location_id`若保留必须与该分区一致，不得覆盖舰队分区。
- 金川舰艇继续使用各舰结构化`location_id/status`作为当前位置事实。
- Engine必须支持按我方正式舰名精确查询当前位置，并从上述canonical路径派生；历史航线、旧任务地点、返航说明不得覆盖当前分区。
- V9.54及以后`PLAYER_VESSEL_LOCATION_AUTHORITY`在full check中硬校验；旧SAVESET仅为迁移兼容可读。""")
    text=replace_rule(text,'RULE-CURRENT-TEMPORAL-HYGIENE-01',"""### RULE-CURRENT-TEMPORAL-HYGIENE-01 当前对象日期别名与过期计划字段
- V9.54及以后，当前态不得再使用`*_current_YYYYMMDD`/`*current-YYYYMMDD`式日期后缀对象作为长期current；历史日期快照必须进入HISTORY，持续事实使用无日期canonical键。
- 带current语义的对象中，已早于当前游戏时间的`next_*`计划字段不得继续作为当前计划镜像；若其业务已被后续事件/任务monitor取代，应归档旧字段而不是让AI继续读取过期时间。明确标记`legacy/historical`的历史子账除外。
- active/queued任务若runtime monitor已有当前`next_review_at`，`task_data.next_*`不得继续保留早于当前游戏时间的重复镜像。
- `DATED_CURRENT_ALIAS_HYGIENE`、`CURRENT_STATE_TEMPORAL_HYGIENE`与`ACTIVE_TASK_TEMPORAL_MIRROR_HYGIENE`自V9.54起作为保存硬门；旧SAVESET仅迁移兼容可读。""")

    text=replace_rule(text,'RULE-CALDER-552-LEGACY-PROFILE-01',"""### RULE-CALDER-552-LEGACY-PROFILE-01 卡尔德552项历史别名重定向规则
- “卡尔德552项产业”仅作为历史查询别名，统一解析到`MULTINATIONAL_INDUSTRY_CURRENT`当前总账。
- 旧组成、采购和已完成投资筛选的完整证据仅存于显式证据查询才读取的冷归档；当前态不保留第二套产业明细或独立调度器。
- 查询旧名称不得生成虚构单项、平均单项参数或第二次结算；资产数和金币/灰币日净收益均从当前state权威字段读取。""")
    text=replace_rule(text,'RULE-ENTITY-LIFECYCLE-01',f"""### RULE-ENTITY-LIFECYCLE-01 实体合并/退役与canonical重定向
- V10.133起`STATE.entity_lifecycle`使用`{ENTITY_LIFECYCLE_SCHEMA}`登记会影响当前查询的实体生命周期。持续实体使用稳定`entity_id`；改名、合并、解散、摧毁不得靠删除名称后让旧对象自行复活。
- `status=merged`必须提供`successor_id`并最终解析到`status=active`实体；原实体完整末态/合并前资料进入HISTORY，current层只保留生命周期记录和必要别名，不再保留第二套活动对象。
- active/queued TASKS的机器STATE路径、query_order、view_rule及明确`target/organization/threat_org`字段不得指向merged/retired/dissolved/destroyed实体；current容器不得继续以其canonical_name/alias作为活动键。违反时`ENTITY_LIFECYCLE_INTEGRITY`拒绝保存。
- 查询旧名称时Engine先解析生命周期；若已合并，返回successor及其current路径。历史文本仍可保留旧名，不能据此重新生成独立current实体。
- 合并前后力量数字不得自动相加。只有明确事件证明人员/装备在当前时点仍连续归属successor时，才能更新successor当前力量；否则旧数字只作为历史资料归档。""")
    text=replace_rule(text,'RULE-ENTITY-REGISTRY-01',f"""### RULE-ENTITY-REGISTRY-01 稳定实体ID与权威路由注册表
- V10.283起`STATE.entity_registry`使用`{ENTITY_REGISTRY_SCHEMA}`。它只保存`entity_id/type/name/alias/status/state_path/source_ref/successor_id`等身份与路由元数据，**禁止复制舰数、人员、资金、库存、战力、位置数值等动态CURRENT事实**。
- 三支玩家舰队、`entity_lifecycle`实体和已经实例化的自治实体由Engine在同一事务内自动同步到注册表；未来新实体应优先获得稳定ID，再由剧情/机械对象引用ID或stable path。
- `state_path`只指向canonical authority；实体改名使用alias，合并使用successor_id，销毁/退役使用status，禁止通过另造第二个current对象表达身份变化。
- 查询实体身份时Engine先走Entity Registry；需要动态详情再沿`state_path`按需读取，不默认全文扫描STATE。`ENTITY_REGISTRY_INTEGRITY`自V10.283起为保存硬门。""")
    text=replace_rule(text,'RULE-WORLD-RULE-REGISTRY-01',"""### RULE-WORLD-RULE-REGISTRY-01 WORLD规则注册表与locator-only缓存
- WORLD正文仍是规则唯一权威，不创建第二份规则正文数据库。Engine从`### RULE-/SOP-...`标题构建`WORLD_RULE_REGISTRY_V2`运行时注册表，只保存rule_id、字符locator、section hash、标题和依赖rule_id。
- `.runtime/world_index.json`属于可删除缓存；必须同时绑定WORLD SHA、Engine版本和sidecar完整性摘要。缓存损坏、旧格式或locator/hash不匹配时从WORLD自动重建。
- 规则ID标题不得重复。规则正文检索先按locator读取并校验section hash，失败才回退精确规则提取；不得把截断规则当作完整规则证据。
- 新规则以稳定rule_id引用其他规则；依赖图只作检索/诊断，不改变WORLD正文的权威顺序与语义。""")
    text=replace_rule(text,'RULE-DERIVED-RUNTIME-VIEW-01',f"""### RULE-DERIVED-RUNTIME-VIEW-01 可重建派生视图与STATE去重
- V10.285起可由canonical/已封板STATE输入确定性重建的重复展示表优先迁出权威STATE，进入`{DERIVED_RUNTIME_SCHEMA}`运行时sidecar；sidecar永远不是游戏事实源，删除或损坏后必须可从source paths即时重建。
- 每个派生视图必须绑定输入内容SHA-256。输入变化即自动失效旧缓存，不允许旧derived view反向覆盖canonical STATE。
- 第一批迁出的`voyager_ship_combat_power`由`vessel_roster + class_counts + class_combat_power_snapshot`逐舰展开。迁移前Engine必须证明旧`ship_combat_power_snapshot_current`与重建结果语义完全等价，否则拒绝升级。
- `class_combat_power_snapshot`和各舰队`ground_power_snapshot`暂不因本规则自动删除；只有建立独立确定性重建器并通过等价门后才能迁出。""")
    text=replace_rule(text,'RULE-PROJECT-VPACK-TRANSPORT-01',f"""### RULE-PROJECT-VPACK-TRANSPORT-01 Project两文件运输层
- `{VPACK_TRANSPORT_FORMAT}`只是Project来源运输容器，不改变五个游戏权威文件、SAVESET身份或包内Engine/Guard信任绑定。
- 两文件模式外层固定入口可使用`SAVE_GUARD_v2.4.1.py`兼容文件名，以保持Project既有冷启动指令；该文件只负责验证唯一VPACK、原子物化其精确七文件内容，然后委托INDEX绑定的真实SAVE_GUARD。
- VPACK（外部默认.zip，兼容旧.vpack）成员必须逐文件SHA-256匹配PACK manifest，并且INDEX内部四源hash、bundle、save_set_id及Engine/Guard hash必须再次闭合；任一不一致在写入运行根前fail-closed。
- 正式游戏保存仍写标准SAVESET/A-B事务。换新对话前由Engine `packtransport`从最新committed SAVESET重新生成两文件来源；本地运行时保存不等于Project来源已同步。""")
    text=replace_rule(text,'RULE-ENGINE-SINGLEFILE-BUILD-01',f"""### RULE-ENGINE-SINGLEFILE-BUILD-01 Engine开发模块化与单文件发行
- 正式Project/SAVESET始终只绑定一个`GAME_ENGINE_vX.Y.Z.py`，运行时不得为了模块化额外依赖Project中的Python模块。
- Engine提供`devsplit/devbundle`开发工具：按稳定`VOYAGER_DEV_MODULE`边界把单文件无损拆成开发模块；未修改模块重新bundle必须得到逐字节相同Engine。
- 模块目录只属于`.runtime/devsrc`开发缓存，不是Project来源、游戏权威或运行依赖；候选Engine必须重新bundle为单文件并通过compile/selftest/engineupgrade门后才能进入正式SAVESET。
- 模块编辑不得绕过Engine升级的兼容、性能、八组件冷启动和事务提交门。""")
    text=_normalize_current_hygiene_world_lines(text)

    text=text.replace('- **自动维护**：舰艇人员补充、武装人员换装动力甲、机器人/航空器损失或补充、实际舰载装备调拨后，必须同步更新`STATE.<fleet>.ground_power_snapshot`中对应舰的数值；未来战前审计直接调用该快照作为有机基线，再叠加本次实际投入。','- **自动维护**：舰艇人员补充、机器人/航空器损失或补充、实际舰载装备调拨后，必须同步逐舰current实装与舰队聚合表；`ground_power_snapshot`只是可选可重建报告缓存。存在时必须与current实装一致，过期时应失效/删除而不是阻塞权威资产更新；未来战前审计从canonical实装即时计算有机基线。')
    text=text.replace('- 逐舰常备地面战力快照属于动态派生数据，统一保存在各舰队STATE的`ground_power_snapshot`；WORLD只保存计算原则。','- 逐舰常备地面战力可由Engine从current实装即时派生；若STATE保留`ground_power_snapshot`仅作报告/加速缓存，可随时删除并重建，不属于战斗权威输入。WORLD只保存计算原则。')
    text=replace_rule(text,'RULE-SHIPBOARD-ASSET-CROSSPATH-01','### RULE-SHIPBOARD-ASSET-CROSSPATH-01 舰载装备跨路径一致性硬门\n- **权威优先级**：指挥官最新明确更正 > 逐舰当前实装字段（`current_embarked_assets`、`current_combat_robot_count`、`current_armored_vehicles`等） > 最新调拨/验收事件 > 舰队聚合表 > `ground_power_snapshot`等派生快照 > planned计划字段。派生快照不得反向覆盖当前实装。\n- **变更触发局部校验**：涉及暗影舰队逐舰实装、舰队装备聚合或地面战力缓存的结构化变更，在写盘前先执行`SHIPBOARD_ASSET_CROSSPATH`局部硬校验；不一致立即拒绝该事务。\n- **保存前全局校验**：每次正式保存必须核对逐舰战斗机器人数量/型号与舰队机器人聚合；`ground_power_snapshot`若存在，还必须逐舰核对机器人/装甲车辆及`as_of`。缓存缺失本身不构成错误。\n- **快照可选**：`ground_power_snapshot`是可删除、可重建、非权威的派生缓存，只用于报告/加速读取。过期时优先失效/删除，禁止为了保住旧快照反向修改canonical实装；战斗准备不得仅依赖该缓存。\n- **AI介入边界**：校验和拒绝保存完全由Engine自动执行；只有多个canonical权威路径自身互相冲突、无法机械判断哪条记录应保留时，才进入AI/指挥官审计。')
    text=replace_rule(text,'RULE-CURRENT-EMBARKED-ASSET-AUTHORITY-01','### RULE-CURRENT-EMBARKED-ASSET-AUTHORITY-01 当前舰载装备单一优先级与派生缓存失效规则\n- 舰艇当前实际搭载的战斗机器人、无人机/航空器、动力甲、装甲车辆及其他可移动战斗装备，必须优先读取 `STATE.<fleet>.vessels.<vessel_id>.current_embarked_assets` 或同舰明确的最新 `current_*` 实装字段；`planned_*`、历史任务摘要和派生战力缓存只可作为计划/追溯信息，不得覆盖更新的当前实装。\n- **当前事实优先级固定为**：指挥官最新明确更正 > 同舰current实装字段 > 同舰最新调拨/验收HISTORY > 舰队聚合当前装备表 > 可选派生战力缓存 > planned/旧设计。若高低层冲突，必须按高层纠正；不得选择旧快照作为“更保守”答案。\n- 每次实际调拨/补充/损失/归还，必须在同一权威事务中同步：①接收舰逐舰current实装；②来源库存/原舰扣减；③舰队聚合装备表；④HISTORY。任何战力派生缓存若保留，可在同事务重建；无法可靠重建时必须失效/删除，不得阻塞canonical资产更新。\n- 派生快照若存在必须保存`as_of`并与current实装一致；缺失本身不是错误。舰队聚合表是逐舰current实装的派生汇总，不是独立事实源。')
    text=replace_rule(text,'RULE-SHADOW-SHIP-COMBAT-SNAPSHOT-01','### RULE-SHADOW-SHIP-COMBAT-SNAPSHOT-01 暗影舰队舰战机械输入规则\n- 本规则只规定当前战斗机械输入来源，不保存某一时点舰数或总战力。\n- V9.48起退役旧`STATE.shadow_fleet.combat_power_current`：该8362-10-06派生缓存早于V8.95舰载无人机/机器人统一标准化，不能继续作为当前舰战C来源。\n- 当前暗影舰战必须从逐舰canonical舰体/固定武装/护盾/当前作战航空实装及`combat_damage_reconciliation_current`中可证明的机械字段生成`battleprepare`权威profile；已注册且仍有效的单舰封板值可以作为明确字段来源。\n- 若某舰当前逐舰航空分配、固定系统状态或其他必要机械字段不足以重建精确战斗profile，Engine/AI必须把该单位停在输入缺口/Semantic Barrier，禁止从已退役旧cache补数或凭空估计。\n- 舰载战斗机器人属于地面G，不计舰战C；历史战力表需要追溯时从HISTORY精确读取，不得复制回current。')
    text=replace_rule(text,'RULE-THREE-FLEET-COMBAT-INDEX-01','### RULE-THREE-FLEET-COMBAT-INDEX-01 三舰队舰战战力统一调用索引\n- 远航者：优先使用当前舰级/逐舰已注册机械profile与`STATE.voyager_fleet.class_combat_power_snapshot`中仍与当前固定设计一致的字段。\n- 金川：读取当前逐舰/舰队机械profile；`STATE.jinchuan_fleet.combat_power_snapshot`仅在与当前实装/战损一致时作为派生加速层。\n- 暗影：禁止读取已退役的`shadow_fleet.combat_power_current`；必须由逐舰canonical实装、固定系统和战损reconciliation生成/校验`battleprepare`输入。\n- 任一舰队若当前机械字段不足，必须显式报告缺口并停止该单位战斗封板，不得用旧派生快照或历史总值填空。')
    text=replace_rule(text,'RULE-TASK-DERIVED-VIEW-01',f"""### RULE-TASK-DERIVED-VIEW-01 TASK_OBJECT_V4与派生任务视图
- V10起active/queued TASKS使用`TASK_OBJECT_V4`。`current_status`与`next_trigger`属于展示层，不得作为持久current镜像写入任务对象。
- 每个任务必须声明`view_rule.schema={DERIVED_VIEW_RULE_SCHEMA}`；Engine在query、冷启动、舰桥汇报时从canonical STATE/stable refs、任务phase、monitor与必要的`semantic_context/trigger_condition`即时生成`derived_view`。
- 机械事实不得复制进`semantic_context`；只有无法由结构化STATE推导的语义性上下文/触发条件才可保留为任务自有文本。
- Resolver更新phase、task_data、monitor和canonical STATE即可；不得为了展示重新长出`current_status/next_trigger`。""")
    text=replace_rule(text,'RULE-TRANSACTION-CHANGESET-01',f"""### RULE-TRANSACTION-CHANGESET-01 事务真实diff自动审计
- V10起正式SAVE提交使用`{TRANSACTION_CHANGESET_SCHEMA}`：Engine比较父SAVESET与staging中的WORLD/STATE/TASKS实际差异，并检查本次新增HISTORY事件的`changes.target`覆盖。
- Resolver仍应写有意义的业务HISTORY摘要与财务分类，但若遗漏实际发生的非财务authority路径，Engine自动追加`transaction_changeset`事件补齐真实diff；不得靠手写声明掩盖未发生的变更。
- 财务守恒、非法额外authority声明、HISTORY append-only及所有现有硬门仍独立校验；changeset不是绕过审计的白名单。""")
    text=replace_rule(text,'RULE-RUNTIME-GAME-FACT-SEPARATION-01',"""### RULE-RUNTIME-GAME-FACT-SEPARATION-01 运行工具元数据与游戏事实分离
- V10起Engine版本目标、升级验证记录、自动化注册表、恢复checkpoint等纯工具/缓存元数据不再写入STATE/TASKS，也不因纯Engine升级向游戏HISTORY追加伪“发生事件”。
- 当前Engine/Guard版本与哈希由INDEX manifest、SAVESET envelope/COMMIT和工具文件本身绑定；STATE/TASKS只保存会影响游戏世界或机械运行的当前事实。
- 本阶段仍保持SAVESET对Engine/Guard的可信绑定与回滚语义；未来若完全拆分GAME_SAVE_ID/RUNTIME_BUILD_ID，必须另经Guard信任模型专项升级，不得隐式放宽。""")
    text=replace_rule(text,'RULE-COLD-START-V3-01',f"""### RULE-COLD-START-V3-01 最小冷启动包与恢复缓存退役
- 新聊天唯一入口仍为`SAVE_GUARD --resume`，输出`{COLD_START_PACKET_SCHEMA}`。
- V3默认只提供舰队核心、资金、紧凑位置摘要、TASK_OBJECT_V4派生任务摘要、下一机械节点/语义屏障、开放决策门和战斗/维修队列计数；详细对象按exact查询补取。
- `STATE.engine_runtime.recovery.current_checkpoint`与`TASKS.recovery.current_checkpoint`自V10退役，不得作为权威镜像保存或参与冷启动优先级。""")
    text=replace_rule(text,'RULE-TURN-SESSION-01',f"""### RULE-TURN-SESSION-01 事务化Turn Session、恢复检查点与自动提交
- 普通多节点时间推进统一使用`session start/advance/apply`；Turn Session在临时staging中运行并在每个机械节点后重规划。达到Session最终目标时Engine**自动生成下一版本SAVESET并commit**，不得把`READY_TO_COMMIT`作为玩家可见完成态返回。
- 遇到AI语义节点、玩家决策门、授权边界或不可逆重大承诺时，Session暂停并创建`{TURN_RECOVERY_CHECKPOINT_FORMAT}`：复制当时五个staged权威文件与父标记、逐文件SHA-256绑定，并把checkpoint id写入受完整性保护的`{TURN_SESSION_META_FORMAT}`。AI/玩家处理后继续同一Session。
- 语义补丁`session apply`完成后必须立即刷新recovery checkpoint，确保已经对玩家确认的语义事实至少存在于可恢复检查点。checkpoint属于`.runtime`事务恢复基础设施，不是正式SAVESET，也不得写回STATE/TASKS作为游戏事实。
- 正式commit失败时Session进入`COMMIT_FAILED`，自动保留`commit_failure` checkpoint并禁止继续advance；只能重试`session commit`或明确abort。不得在未提交状态上继续推进后续回合。
- `session recover`只允许从同一当前父SAVESET、完整性/文件哈希全部通过的checkpoint重建专属staging；父SAVESET已变化则fail-closed。
- Turn Session元数据与checkpoint路径必须绑定session id、专属目录、父SAVESET与`.PARENT.json`；任何meta篡改、路径越界、符号链接、父标记变化或父SAVESET过期都必须fail-closed。
- 普通COMMIT成功后自动生成完整ZIP和匹配Guard并验证空目录冷启动；查询、预览和内部机械节点不单独打包。""")
    text=replace_rule(text,'RULE-AUTOSAVE-POLICY-01',f"""### RULE-AUTOSAVE-POLICY-01 AUTOSAVE_POLICY_V1 与NO_UNSAVED_PLAYER_VISIBLE_STATE
- **NO_UNSAVED_PLAYER_VISIBLE_STATE**：任何已经作为确定事实返回给玩家的游戏状态变化，必须处于正式committed SAVESET，或处于通过完整性校验的`{TURN_RECOVERY_CHECKPOINT_FORMAT}`。Engine不得返回“本回合完成但尚待手动保存”的状态。
- 每个完整玩家推进事务结束时自动SAVESET；同一事务内多个机械节点只写Turn Session journal/staging，不为每个节点创建完整SAVESET。纯查询、资料查看、计划讨论、`routineplan/turn preview`不得产生新SAVESET。
- 每个确定性机械事件写入小型`TURN_SESSION_JOURNAL_V1`运行日志；该journal用于诊断/恢复线索但不是游戏权威。只有语义屏障/语义补丁/commit失败需要复制完整recovery checkpoint。
- `autoadvance`只是Turn Session兼容包装：无屏障则自动commit；遇到屏障不得再丢弃已执行的确定性推进，而是返回session id与recovery checkpoint。
- 保存失败必须停止推进并报告最后安全SAVESET与checkpoint；保存重试成功后才可宣布该回合完成。普通autosave只做增量HISTORY、STATE/TASKS变更、既有一致性硬门与原子SAVESET，不捆绑Engine迁移、WORLD清洗、STATE全量归档或Project发布。""")
    text=replace_rule(text,'RULE-WORLD-PROCESS-01',f"""### RULE-WORLD-PROCESS-01 封板背景世界状态机
- `{WORLD_PROCESS_RULE_SCHEMA}`只允许执行显式登记的机械条件与`AUTOMATION_RULE_V1`动作；条件、阈值、动作和循环周期均必须在规则中封板。
- Engine不得从剧情文本推导兵力增长、控制区变化、政治选择、概率或隐藏公式；缺少明确机械规则时保持`external_wait`或Semantic Barrier。
- 世界过程命中某个transition时可机械更新canonical STATE并写HISTORY；新的独特剧情事实、NPC动机和政治含义仍由AI封板。""")
    text=replace_rule(text,'RULE-PROGRESS-RULE-01',f"""### RULE-PROGRESS-RULE-01 通用固定速率进度解释器
- `{PROGRESS_RULE_SCHEMA}`适用于已明确封板`target + rate_per_second + bounds`的科研、探索、训练、建设、解码等持续机械进度。
- Engine只按时间差和固定速率推进数值并执行显式milestone机械动作；没有封板速率/上下限时禁止自行估算。
- milestone若需要生成新科研发现、遗迹含义、政治结果或其他语义事实，只能形成Semantic Barrier，不能由进度解释器自由生成。""")
    _random_rule_block='''### RULE-RANDOM-EVENT-FRAMEWORK-02 舰队与世界随机事件框架 V3
- 长期随机体系固定为12个Hazard族：全球小规模武装冲突、三大国/中型国/小国显著动荡、深空遭遇、海盗与犯罪接触、打捞发现、科研异常、市场事件、矿业事件、情报机会、极低频大型事件。`operational_hazard_families`必须与这12族一致；已有Clock的cycle、累计暴露和seed不重掷。
- **同一游戏日允许发生多个随机事件。** 事件按各自Hazard Clock独立累计与触发，不设置“每日最多1次”的全局上限；Engine在一次推进中按时间顺序物化全部已越阈值事件（受防事件风暴的机械上限保护）。
- **情报机会 `intelligence_opportunity`频率提高2倍**：从9–21次/年调整为**18–42次/年**，冷却仍为7天；只提高当前时刻以后的风险积累速度，不追溯补掷、不重置cycle、不重抽已有阈值。
- **自动物化，不依赖AI语义生成**：全球小规模冲突、三类国家政治动荡、海盗/犯罪接触、科研异常、市场事件、矿业事件、情报机会均使用WORLD数据表由Engine按seed直接选择事件模板、对象/类别、参数与即时状态，并直接写入HISTORY；AI只负责报告解释和玩家后续主动行动，不再负责生成这些事件本身。
- 海盗/犯罪接触在机械物化时自动执行`RULE-CONTACT-SENSOR-INITIATIVE-01`先发现门，并保存判定结果；事件本身不自动开火、不自动交易。
- 科研异常只生成符合连续人类文明技术上限的可观察异常，不自动奖励，不得无因生成未知文明遗迹或超当代失落科技。
- 市场事件扩展为清算、二手军械挂牌、旧舰拍卖、债权人急售、资源价格涨跌、卖方临时折价、军需库存积压、新型号上市导致旧型号折价、战争风险溢价、大公司退出、需求变化、货运价差、融资收紧、保险费变化等；市场事件只创造真实机会/情报，不自动成交。
- 矿业随机池删除普通产量/设备效率的正负波动，也不生成随机机械故障；改为富矿脉、储量上/下修、地质空洞、稀有伴生矿、非法采矿、产权纠纷、人工结构和明确开采事故等事件。
- 深空与打捞子表扩容并降低“模糊迹线/休眠残骸”的合计权重，避免低信息事件长期重复；需要人物身份、求救、产权或处置选择的深空/打捞事件仍可形成Semantic Barrier。
- 极低频大型事件继续保留Semantic Barrier，因为其可能产生不可逆重大后果；二手物品2%隐藏问题门、人员随机关闭、一般技术事故随机关闭等既有规则保持不变。
- 每一个Hazard cycle一旦增加，必须对应一个稳定`event_id`并写入HISTORY；父子SAVESET提交硬门逐cycle核对，缺失/重复/未标记为随机事件均拒绝保存。\n- 三类国家政治Hazard机械物化时必须排除已处于危机/过渡链的国家；新触发事件同事务写入`STATE.world_state_overrides.organizations_and_politics.nation_dynamics`并更新对应Hazard Clock排除清单/风险乘数，直到后续明确危机解决事务解除排除。'''
    text=replace_rule(text,'RULE-RANDOM-EVENT-FRAMEWORK-02',_random_rule_block)
    text=text.replace('- GAME ENGINE只判定“某事件族在某时刻达到触发条件”，不生成具体国家、人物动机、阴谋内容、战斗结果或剧情细节；具体内容由AI结合WORLD、STATE、HISTORY和当时因果生成。','- GAME ENGINE负责Hazard触发时刻；对`random_event_tables`中标记为`mechanical`的事件，Engine同时按seed物化具体模板、对象与结构化参数并写入HISTORY。仅标记为`semantic`的深空/打捞/极低频重大事件才由AI结合WORLD、STATE、HISTORY补全声明的语义字段；战斗结果和不可逆重大政治后果仍不得由普通随机表直接改写。')
    text=replace_rule(text,'RULE-AUTHORITY-COMPONENT-ROLES-01','''### RULE-AUTHORITY-COMPONENT-ROLES-01 权威组件职责分离
- 移动端继续维持五权威文件+Engine+Guard的七文件协议，但职责不再混写：`WORLD`只保存规则、稳定模板/目录与必要语义设定；`STATE`只保存当前事实、关系、随机状态和Engine运行账；`TASKS`只保存计划、触发器、授权门与待履行事项；`HISTORY`只保存事件、时点效果与审计来源；`INDEX`只保存协议、绑定与路由。
- WORLD机器区块进一步分为`VOYAGER_RUNTIME_RULES_V1`与`VOYAGER_STATIC_CATALOG_V1`。规则区块保存公式、条件、优先级与约束；目录区块保存稳定装备/型号模板。Engine读取时可合并为兼容视图，但两个区块不得重复独立维护同一字段。
- 当前资金、位置、库存、人物状态、任务状态不得写回WORLD；稳定装备基线不得因为一次当前持有量变化复制进STATE成为第二个模板。派生汇总可以缓存，但必须可由上述权威重建并由校验门约束。''')
    text=replace_rule(text,'RULE-FIXED-POINT-FINANCE-01','''### RULE-FIXED-POINT-FINANCE-01 四位小数固定点资金权威
- 当前金币/灰币机械余额以`STATE.engine_runtime.finance_runtime.funds_units`为唯一算术权威，比例固定为1单位=0.0001货币；`STATE.summary.funds`只作为兼容查询视图，由Engine同步并在full check逐币种核对。
- 入账、扣款、日结、销售累计和领域资金命令不得使用二进制float直接累加；必须先换算固定点整数，再执行加减/乘法量化。余额不得为负。
- 启用固定点权威后，通用PATCH与AUTOMATION禁止直接写`summary.funds`或`finance_runtime`；需要业务资金变化时使用确定性结算器或`DOMAIN_COMMAND_V1 adjust_funds`，并携带原因及必要授权。
- 历史价格、参考估值和不参与当前余额运算的旧记录无需全量重写；只要未来发生机械运算，就必须走固定点函数。''')
    text=replace_rule(text,'RULE-DOMAIN-COMMAND-01','''### RULE-DOMAIN-COMMAND-01 完整领域命令与幂等事务
- AI对常见确定性业务动作优先提交`DOMAIN_COMMAND_V1`，而不是分别修改多个JSON字段。当前注册命令包括资金调整、库存数量转移、远航者舰艇部署/归建、到期维修/医疗完成；每个命令同时处理预条件、关联字段、HISTORY和提交。
- 每个命令必须携带稳定`command_id`与`base_save_set_id`。相同`command_id`+相同payload重复提交返回既有回执，不重复扣款、转物资、调舰或完成维修；同ID不同payload硬拒绝。旧base且未命中过去回执时视为并发陈旧命令并拒绝。
- 负向资金变化必须有指挥官授权或明确standing authorization；维修完成继续执行compare-and-set冲突门。领域命令不得越过未知剧情事实、产权争议或玩家决策门。''')
    text=replace_rule(text,'RULE-ASSET-SEMANTIC-MAP-01','''### RULE-ASSET-SEMANTIC-MAP-01 资产账本语义映射门
- 资产账本迁移不得再把`inventories`中的任意数值叶子视为数量。`purchase_gold/price/cost/combat_power/pct/rate/year/time/value`等金额、性能、比例和元数据必须排除。
- `ASSET_SEMANTIC_MAP_V1`把每个候选数量路径分类为`quantity / non_quantity / ambiguous`并说明判定依据。只有quantity映射覆盖所有拟迁移行且ambiguous=0时，`assetledgermigrate`才可启用；数量阈值本身不构成迁移安全证明。
- 未达到完整语义覆盖时继续使用现有inventory权威，不得为了性能强行激活双账。''')

    pat=re.compile(r'<!--\s*'+re.escape(RUNTIME_RULES_MARKER)+r'\s*(\{.*?\})\s*'+re.escape(RUNTIME_RULES_MARKER)+r'_END\s*-->',re.S)
    m=pat.search(text)
    if m:
        rr=strict_json_loads(m.group(1));ce=rr.setdefault('combat_evaluation',{});br=ce.setdefault('battle_resolution',{})
        br['schema']='BATTLE_RESOLUTION_V2';br['snapshot_schema']=BATTLE_SNAPSHOT_SCHEMA;br['commit_schema']='BATTLE_COMMIT_V2';br['maintenance_runtime_schema']=MAINTENANCE_RUNTIME_SCHEMA;br['player_fleet_registry_schema']=PLAYER_FLEET_REGISTRY_SCHEMA
        br['allow_direct_mechanical_input']=False;br['registered_models_only']=True;br['new_model_creation_during_battle']=False
        br['source_kinds']=sorted(BATTLE_SOURCE_KINDS);br['tactical_modifiers']={'TACTIC_STANDARD':{'attack_modifier':1.0,'accuracy_modifier':1.0,'defense_modifier':1.0}}
        br['personnel_casualty_resolution']='semantic_sealed_commit_until_formula_registered';br['external_force_revision_required']=True;br['battle_id_idempotent']=True;br['loot_default']='pending_identification_and_ownership'
        ta=rr.setdefault('task_architecture',{});ta.update({'task_object_schema':TASK_OBJECT_SCHEMA,'derived_view_schema':DERIVED_VIEW_RULE_SCHEMA,'transaction_changeset_schema':TRANSACTION_CHANGESET_SCHEMA,'world_process_schema':WORLD_PROCESS_RULE_SCHEMA,'progress_rule_schema':PROGRESS_RULE_SCHEMA,'cold_start_packet':COLD_START_PACKET_SCHEMA})
        rev3=_random_event_framework_v3_runtime_rules();rf=rr.setdefault('random_event_framework',{});rf.update(rev3.get('framework') or {})
        hp=rr.setdefault('hazard_profiles',{});intel=hp.setdefault('intelligence_opportunity',{});intel['annual_rate_range']=[18.0,42.0]
        rr.setdefault('random_event_tables',{}).update(copy.deepcopy(rev3.get('tables') or {}))
        blob=json.dumps(rr,ensure_ascii=False,indent=2,sort_keys=False)
        text=text[:m.start()]+f'<!-- {RUNTIME_RULES_MARKER}\n{blob}\n{RUNTIME_RULES_MARKER}_END -->'+text[m.end():]

    if SHIPBOARD_ASSET_CROSSPATH_RULE_ID not in text:
        text += "\n\n### RULE-SHIPBOARD-ASSET-CROSSPATH-01 舰载装备跨路径一致性硬门\n\n- **权威优先级**：指挥官最新明确更正 > 逐舰当前实装字段（`current_embarked_assets`、`current_combat_robot_count`、`current_armored_vehicles`等） > 最新调拨/验收事件 > 舰队聚合表 > `ground_power_snapshot`等派生快照 > planned计划字段。派生快照不得反向覆盖当前实装。\n- **变更触发局部校验**：涉及暗影舰队逐舰实装、舰队装备聚合或地面战力快照的结构化变更，在写盘前先执行`SHIPBOARD_ASSET_CROSSPATH`局部硬校验；不一致立即拒绝该事务。\n- **保存前全局校验**：每次正式保存均自动核对逐舰战斗机器人数量/型号、舰队机器人聚合、逐舰地面战力快照中的机器人数量，以及逐舰装甲车辆与快照；任一冲突均拒绝提交并输出舰名与冲突字段。\n- **快照降级**：`ground_power_snapshot`属于可重建的派生缓存，只用于报告/加速读取；其`as_of`不得早于最新逐舰装备变更时间。\n- **AI介入边界**：校验和拒绝保存完全由Engine自动执行；只有多个权威路径自身互相冲突、无法机械判断哪条记录应保留时，才进入AI/指挥官审计。\n"
    text=replace_rule(text,'RULE-JINCHUAN-RESOURCE-NETWORK-CURRENT-01',"""### RULE-JINCHUAN-RESOURCE-NETWORK-CURRENT-01 金川资源网络current同步契约
- `STATE.world_state_overrides.mining_and_industry.jinchuan_resource_network_current`是金川矿业/固定打捞的当前查询镜像，不是独立财务事实源；其矿数、固定打捞数、统一日产与业务时间戳必须由当前金川任务和Engine确定性resolver同步。
- 建设节点在正式改变产能时必须同事务更新`as_of / mining_base_count / fixed_salvage_base_count / unified_daily_gold / unified_daily_grey`；日结`jinchuan_daily_settlement_v1`还必须同步`last_settlement_at / next_settlement_at`并在HISTORY覆盖该current对象。
- `jinchuan_fleet.latest_daily_financial_settlement`保存最近一次已入账结果；`JINCHUAN_RESOURCE_NETWORK_CURRENT`保存当前网络能力/账期查询面。两者不得长期落后或互相覆盖。""")
    text=replace_rule(text,'RULE-ENGINE-EXACT-CACHE-COHERENCE-01',"""### RULE-ENGINE-EXACT-CACHE-COHERENCE-01 查询sidecar与权威一致性
- `.runtime`查询sidecar全部是可删除、可重建的非权威提示，损坏不得改变任何权威答案。活动ROOT的`state_semantic_sidecar_v2`同时绑定当前Engine版本、完整STATE文件stat、当前SAVESET身份与自身完整性摘要；重建时另记录精确STATE SHA-256。任一绑定/完整性失配均自动重建，正常exact热命中仍无需重新哈希/解析整个STATE。
- `history_index.json`只保存HISTORY搜索blob与raw/Epoch locator，`world_index.json`保存WORLD规则片段，因此除绑定对应权威源SHA外还必须绑定当前Engine版本并验证sidecar自身完整性摘要；缓存内容被篡改、截断或跨Engine陈旧时自动从`events.jsonl`/`WORLD.md`重建。
- SAVESET提交后的第一次exact查询必须直接得到新STATE值，禁止出现“新save_set_id + 旧alias value”的混合结果，不要求用户手动`cachebuild`。显式`query --base`必须直接读取该base权威文件或使用该base自己的局部索引，不得借用或污染活动ROOT sidecar。SQLite `cache.db`与`performance.db`均属可删除运行缓存；数据库损坏时Engine必须自动丢弃并重建，诊断/`enginehealth`不得因非权威SQLite损坏而失败。Guard的`.runtime/LATEST.json`同样只是快速指针；缺失、陈旧或非法时不得阻止冷启动，成功选择权威SAVESET后必须自动修复该指针。""")
    text=replace_rule(text,'RULE-RUNTIME-ENGINE-FILE-HYGIENE-01',"""### RULE-RUNTIME-ENGINE-FILE-HYGIENE-01 严格八组件运行根的Engine文件卫生
- Guard绑定当前SAVESET后，根目录若残留版本低于当前绑定版本的`GAME_ENGINE_vX.Y.Z.py`，只把该非权威旧工具副本移入`.runtime/work/retired_engines`。
- 高于当前绑定版本的候选Engine不得自动移动；同版本不同哈希仍按绑定规则fail-closed。
- 该整理不修改8个核心保存文件中的当前权威内容，不改变SAVESET。""")
    text,catalog_sync=_split_world_static_catalog_text(text)
    if text==before:return {'changed':False,'world_revision':_world_revision_from_text(text),'static_catalog':catalog_sync.get('model_counts')}
    p.write_text(text,encoding='utf-8',newline='\n')
    return {'changed':True,'world_revision':_world_revision_from_text(text),'sha256':sha256_file(p),'static_catalog':catalog_sync.get('model_counts')}


def _sync_engine_upgrade_index_protocol(stage:Path,candidate_version:str,save_version:str)->dict:
    p=stage/"INDEX.md"
    if not p.is_file():return {"changed":False,"reason":"INDEX_NOT_PRESENT"}
    before=p.read_text(encoding="utf-8");text=before
    text=re.sub(r'^- `active_pointer_format`：.*\n?', '', text, flags=re.M)
    text=re.sub(r'^- `active_slot`：.*\n?', '', text, flags=re.M)
    text=re.sub(r'^- `save_storage_format`：.*\n?', '', text, flags=re.M)
    text=re.sub(r'^> \*\*当前游戏时间\*\*：.*\n?', '', text, flags=re.M)
    text=re.sub(r'^# 远航者舰队 V\d+\.\d+ — INDEX\.md$',f'# 远航者舰队 {save_version} — INDEX.md',text,count=1,flags=re.M)
    sec2=f'''## 2. 新对话冷启动与机器路由
1. **唯一入口**：运行 `SAVE_GUARD_v{BUNDLED_GUARD_VERSION}.py --resume`，只接受其返回的`COLD_START_PACKET_V5`作为首轮当前态。
2. `COLD_START_PACKET_V5`只携带舰队核心、资金所需核心、位置计数、任务计数、下一确定性事件、当前语义/决策门与机械阻塞；长期watcher详情、外部势力revision和历史背景按需调用Query Intent Registry V3。
3. 常用查询优先`query/querybatch`：`当前任务`、`下一确定事件`、`<舰队>当前状态`、`当前库存`、`当前资金`、`舰队核心`均必须返回`QUERY_INTENT_V3 status=COMPLETE`。
4. INDEX只保存协议、路由与manifest，不保存游戏时间、余额、部署、任务结果或continuity checkpoint。
5. 若Project启用VPACK两文件运输，外层`SAVE_GUARD_v2.4.1.py`只是兼容入口；真正恢复仍由VPACK内INDEX绑定的SAVE_GUARD与GAME_ENGINE执行。
6. 常见确定性业务动作优先使用`domaincommand`的`DOMAIN_COMMAND_V1`；资金权威采用`FIXED_POINT_FINANCE_V1`固定点整数，WORLD机器区块按`runtime rules / static catalog`职责分离。
7. `assetledgerplan`只给规模与语义覆盖报告；存在任何`ambiguous`路径时不得迁移，`--force`也不能绕过。
'''
    text=re.sub(r'^## 2\. .*?(?=^## 3\.)',sec2+'\n',text,count=1,flags=re.M|re.S)
    sec3='''## 3. 恢复原则\n- 当前事实只从STATE/TASKS和Engine派生视图读取；HISTORY只回答历史原因。\n- 旧continuity/current_bridge/recovery checkpoint与聊天记忆不得覆盖当前权威。\n- Project来源替换必须整批同一SAVESET；是否已同步到Project不由Engine臆测。\n'''
    text=re.sub(r'^## 3\. .*?(?=^## 4\.)',sec3+'\n',text,count=1,flags=re.M|re.S)
    text=re.sub(r'Engine \d+\.\d+\.\d+使用`exact/compact/context/full`',f'Engine {candidate_version}使用`exact/compact/context/full`',text,count=1)
    text=text.replace('多节点时间推进优先`session start/advance/apply/commit`；`routineplan`负责预览安全边界，`autoadvance`仅用于不存在中途语义处理需求的便捷单次路径。确定性Resolver和表驱动机械Hazard在同一Turn Session内执行，启用MOBILE_SEVEN_FILE_V1后，语义屏障提交安全边界与pending_turn；resume恢复同一指令窗口。','多节点时间推进优先`session start/advance/apply/commit`；`routineplan`负责预览安全边界，`autoadvance`用于不存在中途语义处理需求的便捷单次路径。**Turn Session与autoadvance均在每个确定性节点后重新读取TASKS与Engine运行时机械队列并重新计算语义/Hazard屏障**，因此新产生的日结、维修、医疗等节点不会被初始队列冻结；启用MOBILE_SEVEN_FILE_V1后，语义屏障提交安全边界与pending_turn；resume恢复同一指令窗口。')
    text=re.sub(r'^3\. 普通查询优先 .*$', '3. 普通查询优先Query Intent Registry V3支持的`query --detail compact`。同轮多问题可用`querybatch --topics <JSON数组>`；多节点时间推进默认 `session start --until <time>`；`AUTOSAVE_POLICY_V1`在Session目标完成时自动commit下一SAVESET，语义屏障提交安全边界与pending_turn，返回PAUSED_COMMITTED。`routineplan`仅预览，纯查询/预览不保存；`autoadvance`是同一Turn Session机制的便捷包装。', text, count=1, flags=re.M)
    text=re.sub(r'^4\. AI语义节点仍使用.*$', '4. AI语义节点仍使用`turn/process`与Task Review Contract/ACK；Review ACK不是权威文件。遇到语义屏障时Turn Session必须先建立`TURN_RECOVERY_CHECKPOINT_V1`再返回；语义补丁后刷新checkpoint。Session最终目标到达自动COMMIT；commit失败进入`COMMIT_FAILED`并禁止继续推进，只允许重试保存或abort。', text, count=1, flags=re.M)
    text=re.sub(r'^- 卡尔德552项产业使用`CALDER_AVERAGE_PORTFOLIO_V1`：.*$', '- 当前商业经营权威对象为`MULTINATIONAL_INDUSTRY_CURRENT`；卡尔德552项仅为历史别名，旧明细转入冷证据归档，查询统一返回当前总账且不得虚拟生成单项。', text, count=1, flags=re.M)
    if text==before:return {"changed":False}
    p.write_text(text,encoding="utf-8",newline="\n");return {"changed":True,"sha256":sha256_file(p)}

def _sync_successful_engine_upgrade_metadata(stage:Path,candidate_version:str,save_version:str)->dict:
    """Synchronize tool-facing protocol without creating game-state upgrade mirrors.

    V10 separates runtime build identity from game facts.  Engine/Guard versions live in
    INDEX/COMMIT and the tool files themselves; STATE/TASKS no longer receive per-upgrade
    engine targets, validation records or recovery checkpoints, and HISTORY no longer gets
    a synthetic engine-upgrade event when no game fact changed.
    """
    for fn in AUTH_FILES:
        if (stage/fn).is_file():(stage/fn).chmod(0o600)
    state=read_json(stage/'state.json');tasks=read_json(stage/'tasks.json')
    source_save_version=str(tasks.get('save_version') or '')
    progress_contract=_activate_continuous_progress_contract(tasks,source_save_version)
    world_sync=_sync_engine_upgrade_world_protocol(stage,candidate_version);index_sync=_sync_engine_upgrade_index_protocol(stage,candidate_version,save_version)
    gt=str(state.get('game_time') or tasks.get('game_time') or '')
    if parse_iso(gt) is None:raise EngineError('ENGINE_UPGRADE_METADATA_GAME_TIME_INVALID')
    er=state.setdefault('engine_runtime',{})
    entity_registry_sync=_sync_entity_registry(state)
    entity_registry_check=_entity_registry_integrity_report(state)
    if entity_registry_check.get('count'):raise EngineError('ENTITY_REGISTRY_MIGRATION_FAILED:'+json.dumps(entity_registry_check,ensure_ascii=False))
    removed=[]
    # V10.280+: remove derived CURRENT mirrors from authority when they are safely reconstructable.
    inv=state.get('inventories') or {}
    if isinstance(inv,dict) and 'current_fleet_inventory_display' in inv:
        inv.pop('current_fleet_inventory_display',None);removed.append('STATE.inventories.current_fleet_inventory_display')
    refs=er.get('state_refs') or {}
    if isinstance(refs,dict) and refs.get('FLEET_INVENTORY_DISPLAY_CURRENT'):
        refs.pop('FLEET_INVENTORY_DISPLAY_CURRENT',None);removed.append('STATE.engine_runtime.state_refs.FLEET_INVENTORY_DISPLAY_CURRENT')
    vf=state.get('voyager_fleet') or {}
    if isinstance(vf,dict) and isinstance(vf.get('ship_combat_power_snapshot_current'),dict):
        rebuilt=_build_voyager_ship_combat_derived(state);persisted=vf.get('ship_combat_power_snapshot_current')
        if not _voyager_ship_combat_equivalent(persisted,rebuilt):raise EngineError('DERIVED_VIEW_MIGRATION_MISMATCH:STATE.voyager_fleet.ship_combat_power_snapshot_current')
        vf.pop('ship_combat_power_snapshot_current',None);removed.append('STATE.voyager_fleet.ship_combat_power_snapshot_current')
    for key in ('engine_maintenance','automation'):
        if key in er:removed.append('STATE.engine_runtime.'+key);er.pop(key,None)
    rec=er.get('recovery')
    if isinstance(rec,dict) and 'current_checkpoint' in rec:rec.pop('current_checkpoint',None);removed.append('STATE.engine_runtime.recovery.current_checkpoint')
    trec=tasks.get('recovery')
    if isinstance(trec,dict) and 'current_checkpoint' in trec:trec.pop('current_checkpoint',None);removed.append('TASKS.recovery.current_checkpoint')
    auto=tasks.get('automation_schema')
    if isinstance(auto,dict) and 'engine_version' in auto:auto.pop('engine_version',None);removed.append('TASKS.automation_schema.engine_version')
    finance_sync=_finance_activate(state)
    domain_existed=_domain_runtime(state,create=False) is not None
    dr=_domain_runtime(state,create=True)
    er['authority_component_roles']={'schema':'AUTHORITY_COMPONENT_ROLES_V1','WORLD':'rules_and_static_catalog','STATE':'current_facts_and_runtime_ledgers','TASKS':'plans_triggers_authorization_outstanding','HISTORY':'events_effects_audit','INDEX':'protocol_binding_routing'}
    mc=er.get('mobile_contract')
    if isinstance(mc,dict):
        mc['money_authority_schema']=MONEY_MODEL_SCHEMA;mc['domain_command_schema']=DOMAIN_COMMAND_SCHEMA;mc['world_static_catalog_schema']=STATIC_CATALOG_SCHEMA;mc['asset_semantic_map_schema']=ASSET_SEMANTIC_MAP_SCHEMA
    domain_sync={'schema':DOMAIN_COMMAND_RUNTIME_SCHEMA,'activated':not domain_existed,'receipt_count':len(dr.get('order') or [])}
    _write_authority_json(stage/'state.json',state);_write_authority_json(stage/'tasks.json',tasks)
    mobile={'changed':False,'status':'LEGACY_MIGRATION_EXPLICIT_ONLY'}
    if _mobile_contract(read_json(stage/'state.json')):
        wp=stage/'WORLD.md';wt=wp.read_text('utf-8')
        wt=re.sub(r'<!-- VOYAGER_RUNTIME_RULES_V1\s*(.*?)\s*VOYAGER_RUNTIME_RULES_V1_END -->',lambda m:'<!-- VOYAGER_RUNTIME_RULES_V1\n'+json.dumps(strict_json_loads(m.group(1)),ensure_ascii=False,separators=(',',':'))+'\nVOYAGER_RUNTIME_RULES_V1_END -->',wt,count=1,flags=re.S)
        wp.write_text(wt,encoding='utf-8',newline='\n')

    if _mobile_contract(read_json(stage/'state.json')):
        ip=stage/'INDEX.md'
        if ip.is_file():
            text=ip.read_text('utf-8')
            text=re.sub(r'^- 当前商业经营权威对象为.*$', '- 商业经营当前资产数与收益统一读取`ref:MULTINATIONAL_INDUSTRY_CURRENT`；卡尔德552项仅为已封板子组件，不另设日结。',text,flags=re.M)
            ip.write_text(text,encoding='utf-8',newline='\n')
    arch_changed=bool(finance_sync.get('activated') or domain_sync.get('activated') or world_sync.get('changed'))
    if arch_changed:
        event_id=f'EVT-ARCH-V1232-{sha256_bytes((str(candidate_version)+str(save_version)+gt).encode())[:12]}'
        _append_engine_history(stage/'events.jsonl',{'event_id':event_id,'game_time':gt,'type':'system','subtype':'architecture_zero_time_migration','summary':f'GAME ENGINE v{candidate_version}完成零游戏时间架构迁移：固定点资金权威、领域命令幂等账、WORLD规则/静态目录职责分离与资产语义迁移门启用。','changes':[{'target':'STATE.engine_runtime.finance_runtime','action':'activate_fixed_point_finance_authority'},{'target':'STATE.engine_runtime.domain_command_runtime','action':'activate_idempotency_runtime'},{'target':'STATE.engine_runtime.authority_component_roles','action':'declare_component_roles'},{'target':'WORLD.VOYAGER_RUNTIME_RULES_V1','action':'separate_executable_rules'},{'target':'WORLD.VOYAGER_STATIC_CATALOG_V1','action':'separate_static_catalog'}],'source':f'GAME ENGINE v{candidate_version} architecture migration','authority_files':['state.json','WORLD.md'],'zero_time':True})
    return {'mobile_migration':mobile,'candidate_version':str(candidate_version),'save_version':str(save_version),'game_time':gt,'profile':'authority_roles_domain_finance_v1','world_protocol_sync':world_sync,'index_protocol_sync':index_sync,'continuous_progress_contract':progress_contract,'entity_registry_sync':entity_registry_sync,'fixed_point_finance_sync':finance_sync,'domain_command_runtime_sync':domain_sync,'removed_runtime_mirrors':removed,'history_event_appended':arch_changed}

def _load_upgrade_module(path:Path, module_root:Path, label:str):
    """Load an Engine/Guard into a unique module namespace with ROOT fixed at import."""
    path=Path(path).resolve();module_root=Path(module_root).resolve()
    name=f'_voyager_upgrade_{re.sub(r"[^A-Za-z0-9_]","_",label)}_{uuid.uuid4().hex[:10]}'
    old=os.environ.get('VOYAGER_ROOT')
    try:
        os.environ['VOYAGER_ROOT']=str(module_root)
        spec=importlib.util.spec_from_file_location(name,str(path))
        if spec is None or spec.loader is None:raise EngineError(f'ENGINE_UPGRADE_MODULE_SPEC_FAILED:{label}:{path}')
        mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    except Exception as ex:
        sys.modules.pop(name,None)
        if isinstance(ex,EngineError):raise
        raise EngineError(f'ENGINE_UPGRADE_MODULE_LOAD_FAILED:{label}:{type(ex).__name__}:{ex}')
    finally:
        if old is None:os.environ.pop('VOYAGER_ROOT',None)
        else:os.environ['VOYAGER_ROOT']=old
    return name,mod

@contextmanager
def _upgrade_deadline(seconds:float,label:str):
    """Hard parent-Engine deadline for an in-process upgrade gate (POSIX/main thread)."""
    if seconds is None or seconds<=0 or not hasattr(signal,'setitimer'):
        yield;return
    old_handler=signal.getsignal(signal.SIGALRM);old_timer=signal.getitimer(signal.ITIMER_REAL)
    def _expired(signum,frame):raise EngineError(f'ENGINE_UPGRADE_GATE_TIMEOUT:{label}:{seconds}s')
    signal.signal(signal.SIGALRM,_expired);signal.setitimer(signal.ITIMER_REAL,float(seconds))
    try:yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,old_handler)
        if old_timer and old_timer[0]>0:signal.setitimer(signal.ITIMER_REAL,*old_timer)

def _upgrade_call(label:str,seconds:float,fn,*args,**kwargs):
    t0=time.perf_counter()
    with _upgrade_deadline(seconds,label):result=fn(*args,**kwargs)
    return result,(time.perf_counter()-t0)*1000.0

def _engine_upgrade_packet_v28(root: Path, candidate: Path, save_version: str, scope: str, migration_patch: Optional[Path]=None, make_export: bool=False) -> dict:
    """Controlled upgrade gate without repeated Python subprocess creation."""
    guard(root,restore=True,restore_tool_files=False);parent=latest_valid_snapshot(root,verify_parent=True)
    text=candidate.read_text(encoding='utf-8');compile(text,str(candidate),'exec')
    if 'ENGINE_MAGIC = "VOYAGER_FLEET_GAME_ENGINE"' not in text and "ENGINE_MAGIC='VOYAGER_FLEET_GAME_ENGINE'" not in text:raise EngineError('ENGINE_UPGRADE_MAGIC_MISSING')
    m=re.search(r'^ENGINE_VERSION\s*=\s*["\']([^"\']+)["\']',text,re.M)
    if not m:raise EngineError('ENGINE_UPGRADE_VERSION_MISSING')
    cv=m.group(1);pv=str((parent.get('index') or {}).get('engine_version') or ENGINE_VERSION)
    if semver_tuple(cv)<=semver_tuple(pv):raise EngineError(f'ENGINE_UPGRADE_VERSION_NOT_NEWER:{cv}<={pv}')
    # Lock candidate identity before any save/Guard cleanup can quarantine or rename the
    # temporary build artifact. A successful commit must never be reported as failure
    # merely because the candidate path no longer exists after activation.
    candidate_hash=sha256_file(candidate)
    cname,cmod=_load_upgrade_module(candidate,root,'candidate')
    try:
        st,_=_upgrade_call('candidate_selftest',45,cmod.selftest,root)
        if not isinstance(st,dict) or st.get('status')!='PASS':raise EngineError('ENGINE_UPGRADE_SELFTEST_FAILED:'+json.dumps(st,ensure_ascii=False)[-2000:])
        stage_info=create_stage(root,'engine_upgrade');stage=Path(stage_info['staging']);before_time=read_json(stage/'state.json').get('game_time')
        if migration_patch is not None:apply_patch(stage,migration_patch)
        metadata_sync=cmod._sync_successful_engine_upgrade_metadata(stage,cv,save_version)
        after_time=read_json(stage/'state.json').get('game_time')
        if after_time!=before_time:raise EngineError('ENGINE_UPGRADE_MUST_NOT_ADVANCE_GAME_TIME')
        pre=_candidate_compatibility_preflight(root,candidate,stage,candidate_module=cmod)
        cp,_=_upgrade_call('candidate_stage_full_check',30,cmod.run_checks,stage,full=True,require_manifest=False)
        if not isinstance(cp,dict) or cp.get('status')!='PASS':raise EngineError('ENGINE_UPGRADE_CANDIDATE_CHECK_FAILED:'+json.dumps(cp,ensure_ascii=False)[-3000:])
        sv,_=_upgrade_call('candidate_commit_save',60,cmod.atomic_save,stage,save_version,scope,root,make_export,False)
        if not isinstance(sv,dict) or sv.get('status')!='COMMITTED':raise EngineError('ENGINE_UPGRADE_SAVE_FAILED:'+json.dumps(sv,ensure_ascii=False)[-4000:])
        return {'status':'UPGRADED','from_engine':pv,'to_engine':cv,'candidate_sha256':candidate_hash,'candidate_selftest':'PASS','compatibility_preflight':pre,'metadata_sync':metadata_sync,'save_result':sv}
    finally:
        sys.modules.pop(cname,None)


# ---------------------------------------------------------------------------
# v2.8 long-term scaling and self-improvement layer.
# ---------------------------------------------------------------------------
PERF_DB_SCHEMA="ENGINE_PERFORMANCE_V1"
HISTORY_EPOCH_EVENT_THRESHOLD=3000
HISTORY_EPOCH_BYTE_THRESHOLD=5*1024*1024
ASSET_LEDGER_ENTITY_THRESHOLD=1500
STATE_ARCHIVE_SIZE_THRESHOLD=1500*1024

def _performance_db_path(root:Path=ROOT)->Path:return root/".runtime"/"performance.db"

def _performance_connect(root:Path=ROOT):
    p=_performance_db_path(root);p.parent.mkdir(parents=True,exist_ok=True);reset=False;last=None
    for attempt in range(2):
        con=None
        try:
            con=sqlite3.connect(str(p));con.execute("CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY,ts TEXT,engine TEXT,command TEXT,duration_ms REAL,peak_rss_kb INTEGER,output_chars INTEGER,save_set_id TEXT)");return con,reset
        except sqlite3.DatabaseError as ex:
            last=ex
            try:
                if con is not None:con.close()
            except Exception:pass
            if attempt==0:
                _reset_runtime_sqlite_files(p);reset=True;continue
            raise
    raise last if last is not None else EngineError("PERFORMANCE_DB_OPEN_FAILED")

def _perf_record(command:str,started:float,result:Any)->None:
    try:
        dur=(time.perf_counter()-started)*1000.0;rss=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss);out_len=len(json.dumps(result,ensure_ascii=False,separators=(",",":"))) if result is not None else 0
        con,_reset=_performance_connect(ROOT);rc=_read_runtime_cache_safe() or {};con.execute("INSERT INTO samples(ts,engine,command,duration_ms,peak_rss_kb,output_chars,save_set_id) VALUES(?,?,?,?,?,?,?)",(dt.datetime.now(dt.timezone.utc).isoformat(),ENGINE_VERSION,command,dur,rss,out_len,str(rc.get("save_set_id") or "")));con.commit();con.close()
    except Exception:pass

def performance_packet(root:Path=ROOT,limit:int=50)->dict:
    p=_performance_db_path(root)
    if not p.is_file():return {"packet":"PERFORMANCE_V1","status":"EMPTY","engine_version":ENGINE_VERSION,"commands":[],"latest":[]}
    con,reset=_performance_connect(root)
    try:
        rows=con.execute("SELECT command,count(*),avg(duration_ms),max(duration_ms),avg(output_chars),max(peak_rss_kb) FROM samples GROUP BY command ORDER BY command").fetchall();latest=con.execute("SELECT ts,command,duration_ms,peak_rss_kb,output_chars FROM samples ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
    finally:con.close()
    return {"packet":"PERFORMANCE_V1","status":"RESET_CORRUPT" if reset else "READY","engine_version":ENGINE_VERSION,"commands":[{"command":r[0],"count":r[1],"avg_ms":round(r[2],2),"max_ms":round(r[3],2),"avg_output_chars":round(r[4],1),"max_rss_kb":r[5]} for r in rows],"latest":[{"ts":x[0],"command":x[1],"duration_ms":round(x[2],2),"rss_kb":x[3],"output_chars":x[4]} for x in latest]}

def _count_inventory_entities(obj:Any)->int:
    n=0
    def rec(x):
        nonlocal n
        if isinstance(x,dict):
            for k,v in x.items():
                if isinstance(v,(int,float)) and not isinstance(v,bool) and v>0:n+=1
                elif isinstance(v,(dict,list)):rec(v)
        elif isinstance(x,list):
            for v in x:rec(v)
    rec(obj);return n

def _history_epoch_physical_count(path:Path)->int:
    n=0
    for raw in path.read_bytes().splitlines():
        if not raw.strip():continue
        try:rec=strict_json_loads(raw.decode('utf-8'))
        except Exception:continue
        if rec.get('record_type')=='history_epoch':n+=1
    return n

def history_epoch_status(base:Path=ROOT)->dict:
    ensure_source_ready(base);path=base/'events.jsonl';size=path.stat().st_size;meta,events,_=read_history_raw(path);count=len(events)
    physical=_history_physical_nonmeta_lines(path);epochs=0;raw_count=0;raw_bytes=0
    for raw in physical:
        rec=strict_json_loads(raw.decode('utf-8'))
        if rec.get('record_type')=='history_epoch':epochs+=1
        else:raw_count+=1;raw_bytes+=len(raw)+1
    activate=((count>=HISTORY_EPOCH_EVENT_THRESHOLD or size>=HISTORY_EPOCH_BYTE_THRESHOLD) if not epochs else
              (raw_count>HISTORY_EPOCH_KEEP_RECENT or (raw_count>HISTORY_EPOCH_MIN_RECENT and raw_bytes>HISTORY_EPOCH_RECENT_BYTE_BUDGET)))
    applied=epochs>0
    status=('COMPRESSED_RECOMPACTION_RECOMMENDED' if applied and activate else ('COMPRESSED' if applied else ('RECOMMENDED_NOT_APPLIED' if activate else 'RAW_BELOW_THRESHOLD')))
    return {"packet":"HISTORY_EPOCH_STATUS_V2","event_count":count,"physical_bytes":size,"physical_epoch_records":epochs,"raw_recent_event_count":raw_count,"raw_recent_bytes":raw_bytes,"threshold_events":HISTORY_EPOCH_EVENT_THRESHOLD,"threshold_bytes":HISTORY_EPOCH_BYTE_THRESHOLD,"activation_recommended":activate,"compression_recommended":activate,"compression_applied":applied,"compression_status":status,"keep_recent_raw_events":HISTORY_EPOCH_KEEP_RECENT,"recent_raw_byte_budget":HISTORY_EPOCH_RECENT_BYTE_BUDGET,"schema":HISTORY_EPOCH_SCHEMA,"policy":"Recommendation and application are separate facts. Compaction preserves every logical event byte; the recent raw window is bounded by both event count and uncompressed-byte budget, with a small minimum tail."}

def _store_history_epoch_archive(root:Path,rec:dict)->Tuple[dict,dict]:
    """Store one verified, content-addressed cold segment; caller owns a staging copy."""
    rec=copy.deepcopy(rec)
    rel=f"archives/history_{rec['seq_start']:06d}_{rec['seq_end']:06d}_{rec['compressed_sha256'][:12]}.json.gz"
    payload={'schema':'VOYAGER_HISTORY_PAYLOAD_V2','codec':rec['codec'],
             **{key:rec[key] for key in ('seq_start','seq_end','event_count','compressed_sha256','compressed_bytes','uncompressed_sha256','uncompressed_bytes','events_sha256')},
             'payload_b64':rec.pop('payload_b64')}
    ph=sha256_bytes(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
    wrapper={'schema':'VOYAGER_COLD_ARCHIVE_V1','payload_sha256':ph,'payload':payload}
    encoded=gzip.compress(json.dumps(wrapper,ensure_ascii=False,separators=(',',':')).encode(),compresslevel=6,mtime=0)
    dest=Path(root)/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        if dest.is_symlink() or dest.read_bytes()!=encoded:raise EngineError('HISTORY_ARCHIVE_CONTENT_CONFLICT:'+rel)
    else:_atomic_replace_bytes(dest,encoded)
    rec['archive_ref']=rel
    _decode_history_epoch_record(rec,0,root)
    key=f"HISTORY_{rec['seq_start']:06d}_{rec['seq_end']:06d}"
    row={'schema':'VOYAGER_COLD_ARCHIVE_V1','archive_id':key,'path':rel,
         'file_sha256':sha256_bytes(encoded),'payload_sha256':ph,
         **{field:rec[field] for field in ('codec','seq_start','seq_end','event_count','events_sha256','compressed_sha256','compressed_bytes','uncompressed_sha256','uncompressed_bytes')},
         'load_policy':'on_demand_history_locator'}
    return rec,row

def _compact_history_file_to_epochs(path:Path,keep_recent:int=HISTORY_EPOCH_KEEP_RECENT,force:bool=False)->dict:
    """Archive aging hot events without rewriting any existing cold reference."""
    before=path.stat().st_size;meta,logical,original_raw=read_history_raw(path)
    physical=_history_physical_nonmeta_lines(path);prefix=[];hot=[];seen_hot=False
    for raw in physical:
        rec=strict_json_loads(raw.decode('utf-8'))
        if rec.get('record_type')=='history_epoch':
            if seen_hot:raise EngineError('HISTORY_EPOCH_AFTER_HOT_RECORD')
            prefix.append(raw)
        else:seen_hot=True;hot.append(raw)
    hot_bytes=sum(len(x)+1 for x in hot)
    if not force and len(hot)<=HISTORY_EPOCH_KEEP_RECENT and hot_bytes<=HISTORY_EPOCH_RECENT_BYTE_BUDGET:
        return {'status':'BELOW_THRESHOLD','logical_events':len(logical),'before_bytes':before,'after_bytes':before,'epoch_records':len(prefix)}
    keep=0;recent_bytes=0
    for raw in reversed(hot):
        if keep>=max(1,int(keep_recent)):break
        if keep>=HISTORY_EPOCH_MIN_RECENT and recent_bytes+len(raw)+1>HISTORY_EPOCH_RECENT_BYTE_BUDGET:break
        recent_bytes+=len(raw)+1;keep+=1
    aging=hot[:len(hot)-keep];recent=hot[len(hot)-keep:]
    if not aging:return {'status':'NOOP','logical_events':len(logical),'before_bytes':before,'after_bytes':before,'epoch_records':len(prefix)}
    manifest=_component_manifest_read(path.parent);archives=copy.deepcopy(manifest.get('cold_archives') or {})
    new_lines=[];chunk=[];chunk_bytes=0
    def flush():
        nonlocal chunk,chunk_bytes
        if not chunk:return
        rec=_make_history_epoch_record(chunk,len(prefix)+len(new_lines)+1)
        rec,row=_store_history_epoch_archive(path.parent,rec);key=row['archive_id']
        if key in archives and archives[key]!=row:raise EngineError('HISTORY_ARCHIVE_ID_CONFLICT:'+key)
        archives[key]=row;new_lines.append(json.dumps(rec,ensure_ascii=False,separators=(',',':')).encode())
        chunk=[];chunk_bytes=0
    for raw in aging:
        if chunk and (len(chunk)>=HISTORY_EPOCH_CHUNK_EVENTS or chunk_bytes+len(raw)+1>HISTORY_EPOCH_CHUNK_UNCOMPRESSED_BYTES):flush()
        chunk.append(raw);chunk_bytes+=len(raw)+1
    flush()
    # Both files are staging data. The original manifest remains the commit point.
    candidate=b'\n'.join([json.dumps(meta,ensure_ascii=False,separators=(',',':')).encode()]+prefix+new_lines+recent)+b'\n'
    _atomic_replace_bytes(path,candidate)
    updated=copy.deepcopy(manifest);updated['cold_archives']=archives
    (path.parent/'manifest.json').write_text(json.dumps(updated,ensure_ascii=False,separators=(',',':'))+'\n')
    if read_history_raw(path)[2]!=original_raw:raise EngineError('HISTORY_TIER_LOGICAL_ROUNDTRIP_MISMATCH')
    return {'status':'COMPACTED','logical_events':len(logical),'compressed_event_count':len(aging),'raw_recent_event_count':len(recent),'epoch_records':len(prefix)+len(new_lines),'new_cold_segments':len(new_lines),'before_bytes':before,'after_bytes':path.stat().st_size,'saved_bytes':before-path.stat().st_size}

def history_epoch_apply(root:Path=ROOT,version:Optional[str]=None,scope:str='HISTORY Epoch threshold compaction',dry_run:bool=False,force:bool=False)->dict:
    status=history_epoch_status(root)
    if dry_run or (not force and not status.get('activation_recommended')):
        return {'packet':'HISTORY_EPOCH_APPLY_V1','status':'DRY_RUN' if dry_run else 'BELOW_THRESHOLD','threshold_status':status,'saved':False}
    if not version:raise EngineError('HISTORY_EPOCH_VERSION_REQUIRED')
    info=create_stage(root,'history_epoch');stage=Path(info['staging'])
    try:
        result=_compact_history_file_to_epochs(stage/'events.jsonl',HISTORY_EPOCH_KEEP_RECENT,force=True)
        if result.get('status')!='COMPACTED':
            shutil.rmtree(stage,ignore_errors=True)
            return {'packet':'HISTORY_EPOCH_APPLY_V1','status':'NOOP','saved':False,'compaction':result}
        gt=str(read_json(stage/'state.json').get('game_time') or '')
        _append_engine_history(stage/'events.jsonl',{'event_id':f'EVT-HISTORY-EPOCH-{gt.replace("-","").replace(":","").replace("T","-")}-{sha256_file(stage/"events.jsonl")[:10]}','game_time':gt,'type':'history_epoch_compaction','summary':f'GAME ENGINE v{ENGINE_VERSION}在阈值触发后将旧HISTORY逻辑事件压缩为同文件可验证Epoch记录；8个核心保存文件自包含与逻辑append-only保持不变。','changes':[{'target':'events.jsonl','action':'physical_epoch_compaction_logical_stream_unchanged'}],'source':f'GAME ENGINE v{ENGINE_VERSION} HISTORY_EPOCH_V1','authority_files':[],'zero_time':True,'epoch_result':result})
        saved=atomic_save(stage,version,scope,root,False,False)
        return {'packet':'HISTORY_EPOCH_APPLY_V1','status':'SAVED','compaction':result,'save':saved}
    except Exception:
        try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
        except Exception:pass
        raise

def _asset_path_owner_status(path:List[str])->Tuple[str,str]:
    owner=next((seg for seg in reversed(path) if seg in {'voyager','jinchuan','shadow'}),'unspecified')
    status=next((seg for seg in reversed(path) if seg in {'available','reserve','reserved','deployed','damaged','pending_refurbishment','stored','active','installed'}),'current')
    return owner,status

_ASSET_PHYSICAL_UNITS={'架','艘','台','个','箱','套','枚','支','辆','罐','包','桶','吨','千克','公斤','kg','t','人','份','组','具','件','颗','门','发','枚/日','unit','units','pcs','piece','pieces'}
_ASSET_MONEY_UNITS={'金币','灰币','gold','grey','gray','credit','credits','currency'}
_ASSET_NONQUANTITY_COMPOUNDS=('purchase_gold','purchase_grey','value_gold','value_grey','combat_power','power_g')
_ASSET_NONQUANTITY_WORDS={'price','cost','revenue','profit','income','expense','power','pct','percent','ratio','rate','year','age','time','timestamp','duration','distance','range','speed','mass','weight','volume','capacity','efficiency','multiplier','bonus','factor','score','level','tier','serial','revision','version','seed','threshold','cooldown','chance','probability','nominal','burst','length','width','height','each','watts','w','g'}
_ASSET_NONQUANTITY_CJK=('金额','价格','成本','收益','收入','利润','战力','功率','比例','概率','年份','时间','时长','距离','速度','质量','重量','容量','效率','倍率','等级','版本','阈值','冷却')
_ASSET_QUANTITY_KEYS={'qty','quantity','count','available','reserve','reserved','deployed','stored','active','remaining','original','owned','total_owned','stock','units','allocated','damaged','pending_refurbishment','installed','unassigned','missiles','ammunition','ammo'}
_ASSET_QUANTITY_CONTEXT={'reserved','reserve','reserved_after_safety_acceptance','weapons_defense','captured_ship_armament_identification','allocation','allocations','loadout','installed','stock','inventory','quantities','counts'}
_ASSET_NONQUANTITY_PREFIXES=('nominal_','length_','width_','height_','price_','cost_','value_','combat_','power_','rate_','ratio_','pct_','percent_')

def _asset_numeric_classification(path:List[str],key:str,parent:dict)->Tuple[str,str,Optional[str]]:
    """Conservatively classify an inventory numeric leaf.

    Unknown model-name leaves are deliberately ambiguous.  Migration safety comes from
    refusing authority activation until every prospective quantity has an explicit,
    reviewable semantic classification; numeric shape alone is never enough.
    """
    kl=str(key).strip().lower();parts=set(re.findall(r'[a-z]+|[0-9]+',kl))
    unit=parent.get('unit') if isinstance(parent,dict) else None
    if key=='value' and unit is not None:
        us=str(unit).strip().lower()
        if us in {x.lower() for x in _ASSET_MONEY_UNITS}:return 'non_quantity','structured monetary value',str(unit)
        if us in {x.lower() for x in _ASSET_PHYSICAL_UNITS}:return 'quantity','structured physical quantity',str(unit)
        return 'ambiguous','structured value has unregistered unit',str(unit)
    if kl.startswith(_ASSET_NONQUANTITY_PREFIXES) or any(tok in kl for tok in _ASSET_NONQUANTITY_COMPOUNDS) or bool(parts & _ASSET_NONQUANTITY_WORDS) or any(tok in str(key) for tok in _ASSET_NONQUANTITY_CJK):return 'non_quantity','metadata/price/performance token',None
    if kl in _ASSET_QUANTITY_KEYS or kl.endswith('_count') or kl.endswith('_qty') or kl.endswith('_quantity') or kl.endswith('_owned'):
        return 'quantity','explicit quantity field name',None
    path_tokens={str(x).strip().lower() for x in path}
    if path_tokens & _ASSET_QUANTITY_CONTEXT:
        return 'quantity','registered quantity container path',None
    return 'ambiguous','numeric leaf lacks registered quantity semantics',None

def _asset_semantic_map(inv:Any)->dict:
    entries=[]
    def rec(x,path):
        if isinstance(x,dict):
            # A structured {value,unit} object is classified as one semantic leaf.
            if isinstance(x.get('value'),(int,float)) and not isinstance(x.get('value'),bool):
                cls,reason,unit=_asset_numeric_classification(path,'value',x);qty=x.get('value');owner,status=_asset_path_owner_status(path)
                entries.append({'path':'inventories.'+'.'.join(path+['value']),'classification':cls,'reason':reason,'value':qty,'unit':unit,'asset_type_id':str(path[-1] if path else 'asset'),'owner_id':owner,'status':status})
                for k,v in x.items():
                    if k in {'value','unit'}:continue
                    if isinstance(v,(dict,list)):rec(v,path+[str(k)])
                return
            for k,v in x.items():
                if isinstance(v,(dict,list)):rec(v,path+[str(k)])
                elif isinstance(v,(int,float)) and not isinstance(v,bool):
                    cls,reason,unit=_asset_numeric_classification(path,str(k),x);owner,status=_asset_path_owner_status(path+[str(k)])
                    entries.append({'path':'inventories.'+'.'.join(path+[str(k)]),'classification':cls,'reason':reason,'value':v,'unit':unit,'asset_type_id':str(k),'owner_id':owner,'status':status})
        elif isinstance(x,list):
            for i,v in enumerate(x):
                if isinstance(v,(dict,list)):rec(v,path+[str(i)])
    rec(inv,[]);entries.sort(key=lambda r:r['path'])
    counts={k:sum(1 for r in entries if r['classification']==k) for k in ('quantity','non_quantity','ambiguous')}
    return {'schema':ASSET_SEMANTIC_MAP_SCHEMA,'counts':counts,'entry_count':len(entries),'entries':entries,'ambiguous_examples':[{'path':r['path'],'value':r['value'],'reason':r['reason']} for r in entries if r['classification']=='ambiguous'][:40]}

def _inventory_quantity_rows(inv:Any,require_complete:bool=True)->List[dict]:
    sm=_asset_semantic_map(inv)
    if require_complete and sm['counts']['ambiguous']:
        raise EngineError(f'ASSET_LEDGER_SEMANTIC_MAP_INCOMPLETE:ambiguous={sm["counts"]["ambiguous"]}')
    rows=[]
    for r in sm['entries']:
        if r['classification']!='quantity':continue
        rows.append({'asset_type_id':r['asset_type_id'],'owner_id':r['owner_id'],'location_id':'unspecified','status':r['status'],'qty':r['value'],'unit':r.get('unit'),'legacy_path':r['path']})
    rows.sort(key=lambda r:r['legacy_path']);return rows

def _build_asset_ledger(state:dict,activated_at:Optional[str]=None)->dict:
    inv=state.get('inventories') or {};semantic=_asset_semantic_map(inv)
    if semantic['counts']['ambiguous']:
        raise EngineError(f'ASSET_LEDGER_SEMANTIC_MAP_INCOMPLETE:ambiguous={semantic["counts"]["ambiguous"]}')
    rows=_inventory_quantity_rows(inv,require_complete=False);rows_payload=json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    return {'schema':'ASSET_LEDGER_V1','semantic_map_schema':ASSET_SEMANTIC_MAP_SCHEMA,'authority_mode':'canonical_ledger_with_legacy_write_adapter','activated_at':activated_at or state.get('game_time'),'row_count':len(rows),'fields':['asset_type_id','owner_id','location_id','status','qty','unit','legacy_path'],'legacy_inventory_sha256':sha256_bytes(json.dumps(inv,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')),'rows_sha256':sha256_bytes(rows_payload),'rows':rows,'policy':'Ledger activation requires ASSET_SEMANTIC_MAP_V1 with zero ambiguous leaves. inventories remains a legacy read/write adapter until all readers are retired; every COMMIT reconciles only after semantic completeness is preserved.'}

def _sync_active_asset_ledger(state:dict)->dict:
    old=state.get('asset_ledger_v1')
    if not isinstance(old,dict) or old.get('schema')!='ASSET_LEDGER_V1':return {'active':False,'changed':False}
    # V12.49 batch-ledger mode is intentionally sparse: only fully proven rows migrate;
    # auditable exclusions remain authoritative legacy fields. Never rebuild it through
    # the older flat inventory classifier adapter.
    if old.get('ledger_format')=='ASSET_LEDGER_BATCH_REGISTRY_V2':
        return {'active':True,'changed':False,'asset_count':len(old.get('assets') or {}),'batch_mode':True}
    fresh=_build_asset_ledger(state,str(old.get('activated_at') or state.get('game_time') or ''))
    changed=(old.get('rows_sha256')!=fresh.get('rows_sha256') or old.get('legacy_inventory_sha256')!=fresh.get('legacy_inventory_sha256') or old.get('row_count')!=fresh.get('row_count'))
    state['asset_ledger_v1']=fresh;state['inventory_authority_mode']='ASSET_LEDGER_V1_CANONICAL_WITH_LEGACY_WRITE_ADAPTER'
    return {'active':True,'changed':changed,'row_count':fresh.get('row_count'),'rows_sha256':fresh.get('rows_sha256')}

def _validate_active_asset_ledger(state:dict)->Optional[str]:
    led=state.get('asset_ledger_v1')
    if not isinstance(led,dict):return None
    if led.get('schema')!='ASSET_LEDGER_V1':return 'unknown asset ledger schema'
    if led.get('ledger_format')=='ASSET_LEDGER_BATCH_REGISTRY_V2':
        if led.get('semantic_map_schema')!=ASSET_SEMANTIC_MAP_SCHEMA:return 'asset ledger semantic map schema missing/old'
        if led.get('mapping_registry_schema')!=ASSET_MAPPING_REGISTRY_SCHEMA:return 'asset ledger mapping registry schema missing/old'
        assets=led.get('assets');batches=led.get('batches')
        if not isinstance(assets,dict) or not isinstance(batches,dict):return 'batch ledger assets/batches missing'
        mapping=((state.get('engine_runtime') or {}).get('asset_mapping_registry') or {})
        if mapping.get('schema')==ASSET_MAPPING_REGISTRY_SCHEMA and led.get('authority_mode')=='ledger_canonical_legacy_read_only':
            rows=mapping.get('migrated_entries') or []
            if len(rows)!=mapping.get('migrated_entry_count') or len(rows)+len(mapping.get('excluded_entries') or [])!=mapping.get('entry_count'):return 'ledger mapping registry count mismatch'
            for row in rows:
                aid=str(row.get('asset_id') or '');path=str(row.get('source_path') or '');role=str(row.get('field_role') or 'quantity')
                rec=assets.get(aid)
                if not isinstance(rec,dict) or path not in (rec.get('source_paths') or []):return 'ledger mapping target missing:'+path
                if any(rec.get(k)!=row.get(k) for k in ('owner_ref','location_ref','container_ref')):return 'ledger mapping owner/location/container conflict:'+path
                if row.get('unit') is not None and rec.get('unit')!=row.get('unit'):return 'ledger mapping unit conflict:'+path
                if not rec.get('asset_type_id'):return 'ledger mapping type missing:'+path
                try:mirror=get_by_path(state,path)
                except Exception:return 'ledger compatibility source missing:'+path
                if mirror!=(rec.get('fields') or {}).get(role):return 'ledger compatibility projection mismatch:'+path
        for aid,rec in assets.items():
            if not isinstance(rec,dict) or str(rec.get('asset_id'))!=str(aid):return 'batch ledger asset key/id mismatch:'+str(aid)
            if not rec.get('owner_ref') or not rec.get('location_ref') or not rec.get('container_ref'):return 'batch ledger mapped asset missing owner/location/container:'+str(aid)
            for role,val in (rec.get('fields') or {}).items():
                if isinstance(val,(int,float)) and not isinstance(val,bool) and val<0:return 'batch ledger negative quantity:'+str(aid)+':'+str(role)
            for src in rec.get('source_paths') or []:
                try:get_by_path(state,str(src))
                except Exception:return 'batch ledger source path missing:'+str(src)
        return None
    if led.get('semantic_map_schema')!=ASSET_SEMANTIC_MAP_SCHEMA:return 'asset ledger semantic map schema missing/old'
    try:fresh=_build_asset_ledger(state,str(led.get('activated_at') or state.get('game_time') or ''))
    except EngineError as ex:return str(ex)
    for k in ('row_count','rows_sha256','legacy_inventory_sha256'):
        if led.get(k)!=fresh.get(k):return f'{k} stored={led.get(k)} expected={fresh.get(k)}'
    if led.get('rows')!=fresh.get('rows'):return 'rows differ from compatibility inventory projection'
    return None

def _sync_active_asset_ledger_in_stage(staging:Path)->dict:
    p=staging/'state.json';state=read_json(p);res=_sync_active_asset_ledger(state)
    if res.get('active'):_write_authority_json(p,state)
    return res

def _v130_layer_asset_ledger_plan_01(base:Path=ROOT)->dict:
    ensure_source_ready(base);state=read_json(base/'state.json');inv=state.get('inventories',{});numeric_count=_count_inventory_entities(inv);semantic=_asset_semantic_map(inv);rows=_inventory_quantity_rows(inv,require_complete=False)
    counts=semantic['counts'];threshold_reached=numeric_count>=ASSET_LEDGER_ENTITY_THRESHOLD;complete=counts['ambiguous']==0;active=isinstance(state.get('asset_ledger_v1'),dict) and state.get('asset_ledger_v1',{}).get('schema')=='ASSET_LEDGER_V1'
    return {'packet':'ASSET_LEDGER_PLAN_V3','inventory_numeric_entries':numeric_count,'semantic_map_schema':ASSET_SEMANTIC_MAP_SCHEMA,'semantic_counts':counts,'prospective_ledger_rows':len(rows),'ambiguous_examples':semantic['ambiguous_examples'],'activation_threshold':ASSET_LEDGER_ENTITY_THRESHOLD,'threshold_reached':threshold_reached,'semantic_complete':complete,'activation_recommended':threshold_reached and complete and not active,'already_active':active,'schema':'ASSET_LEDGER_V1','future_fields':['asset_type_id','owner_id','location_id','status','qty'],'policy':'Threshold is only a scale signal. Ledger authority may activate only when ASSET_SEMANTIC_MAP_V1 classifies every numeric inventory leaf and ambiguous=0; --force never bypasses semantic ambiguity.'}

def _v130_layer_asset_ledger_migrate_01(root:Path=ROOT,version:Optional[str]=None,scope:str='ASSET_LEDGER_V1 semantic migration',dry_run:bool=False,force:bool=False)->dict:
    plan=asset_ledger_plan(root)
    if plan.get('already_active'):return {'packet':'ASSET_LEDGER_MIGRATE_V2','status':'ALREADY_ACTIVE','plan':plan,'saved':False}
    if not plan.get('semantic_complete'):
        if dry_run:return {'packet':'ASSET_LEDGER_MIGRATE_V2','status':'BLOCKED_AMBIGUOUS','plan':plan,'saved':False}
        raise EngineError(f'ASSET_LEDGER_SEMANTIC_MAP_INCOMPLETE:ambiguous={plan.get("semantic_counts",{}).get("ambiguous")}; force_cannot_bypass')
    if dry_run or (not force and not plan.get('threshold_reached')):
        return {'packet':'ASSET_LEDGER_MIGRATE_V2','status':'DRY_RUN' if dry_run else 'BELOW_THRESHOLD','plan':plan,'saved':False}
    if not version:raise EngineError('ASSET_LEDGER_VERSION_REQUIRED')
    info=create_stage(root,'asset_ledger');stage=Path(info['staging'])
    try:
        state=read_json(stage/'state.json');ledger=_build_asset_ledger(state,str(state.get('game_time') or ''));state['asset_ledger_v1']=ledger;state['inventory_authority_mode']='ASSET_LEDGER_V1_CANONICAL_WITH_LEGACY_WRITE_ADAPTER';gt=str(state.get('game_time') or '')
        _write_authority_json(stage/'state.json',state)
        _append_engine_history(stage/'events.jsonl',{'event_id':f'EVT-ASSET-LEDGER-{gt.replace("-","").replace(":","").replace("T","-")}-{ledger["rows_sha256"][:10]}','game_time':gt,'type':'asset_ledger_migration','summary':f'GAME ENGINE v{ENGINE_VERSION}在ASSET_SEMANTIC_MAP_V1零歧义门通过后建立ASSET_LEDGER_V1：{ledger["row_count"]}条数量资产。','changes':[{'target':'STATE.asset_ledger_v1','action':'create_semantically_verified_asset_ledger'},{'target':'STATE.inventory_authority_mode','action':'set_ledger_authority'}],'source':f'GAME ENGINE v{ENGINE_VERSION} ASSET_LEDGER_MIGRATE_V2','authority_files':['state.json'],'zero_time':True})
        saved=atomic_save(stage,version,scope,root,False,False)
        return {'packet':'ASSET_LEDGER_MIGRATE_V2','status':'SAVED','row_count':ledger['row_count'],'rows_sha256':ledger['rows_sha256'],'save':saved}
    except Exception:
        try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
        except Exception:pass
        raise

VERSIONED_CURRENT_ZERO_POLICY_MIN_VERSION=(9,43)
VERSIONED_CURRENT_KEY_RE=re.compile(r'^(?P<base>.+)_current_v(?P<version>\d+)$')

def _versioned_current_zero_policy_report(state:dict)->dict:
    paths=[]
    def walk(x:Any,path:str='STATE'):
        if isinstance(x,dict):
            for k,v in x.items():
                kp=f'{path}.{k}'
                if VERSIONED_CURRENT_KEY_RE.fullmatch(str(k)):
                    paths.append(kp)
                walk(v,kp)
        elif isinstance(x,list):
            for i,v in enumerate(x):walk(v,f'{path}[{i}]')
    walk(state)
    try:ver=parse_version(str(state.get('save_version') or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=VERSIONED_CURRENT_ZERO_POLICY_MIN_VERSION
    return {'required':required,'minimum_version':version_text(VERSIONED_CURRENT_ZERO_POLICY_MIN_VERSION),'save_version':state.get('save_version'),'count':len(paths),'paths':paths[:100]}

def _legacy_current_version_rank(raw:str)->Tuple[int,int]:
    # Historical field suffixes encode V<major>.<minor> without a dot (v95=V9.5,
    # v8145=V8.145). Current authority only contains one-digit major V6-V9 legacy keys.
    z=str(raw or '')
    if not z.isdigit() or len(z)<2:return (0,int(z or 0))
    return (int(z[0]),int(z[1:] or '0'))


CURRENT_SEMANTIC_HYGIENE_MIN_VERSION=(9,46)
BROAD_CURRENT_VERSION_HYGIENE_MIN_VERSION=(9,48)
CURRENT_VERSIONED_REF_RE=re.compile(r'_current_v\d+')
BROAD_CURRENT_VERSION_KEY_RE=re.compile(r'(?i)^.*current.*_v\d{2,}$')
BROAD_CURRENT_VERSION_PATH_RE=re.compile(r'(?i)(?:^|[./])[^./]*current[^./]*_v\d{2,}(?=$|[./])')

def _current_semantic_hygiene_report(state:dict,tasks:dict)->dict:
    """Reject stale current-cache surfaces while keeping older SAVESETs migration-readable."""
    narrow_refs=[];broad_refs=[];broad_keys=[]
    def scan(x,path):
        if isinstance(x,dict):
            for k,v in x.items():
                kp=f'{path}.{k}'
                if BROAD_CURRENT_VERSION_KEY_RE.fullmatch(str(k)):
                    broad_keys.append({'path':kp,'key':str(k)})
                scan(v,kp)
        elif isinstance(x,list):
            for i,v in enumerate(x):scan(v,f'{path}[{i}]')
        elif isinstance(x,str):
            if CURRENT_VERSIONED_REF_RE.search(x):
                narrow_refs.append({'path':path,'value':x[:240]})
            if BROAD_CURRENT_VERSION_PATH_RE.search(x):
                broad_refs.append({'path':path,'value':x[:240]})
    scan(state,'STATE');scan(tasks,'TASKS')
    notes=[]
    if isinstance(tasks,dict):
        for bucket in ('active_tasks','queued_tasks'):
            rows=tasks.get(bucket) or []
            if not isinstance(rows,list):continue
            for i,t in enumerate(rows):
                if isinstance(t,dict) and 'current_note' in t:
                    notes.append({'path':f'TASKS.{bucket}[{i}].current_note','task_id':t.get('task_id'),'value':str(t.get('current_note'))[:240]})
    narrative_present=isinstance(state,dict) and 'narrative_state' in state
    retired_current_caches=[]
    if isinstance(state,dict) and isinstance((state.get('shadow_fleet') or {}).get('combat_power_current'),dict):
        retired_current_caches.append('STATE.shadow_fleet.combat_power_current')
    try:ver=parse_version(str(state.get('save_version') or ('V99.99' if state.get('manifest_ref') else 'V0.0')))
    except Exception:ver=(0,0)
    required=ver>=CURRENT_SEMANTIC_HYGIENE_MIN_VERSION
    broad_required=ver>=BROAD_CURRENT_VERSION_HYGIENE_MIN_VERSION
    base_count=len(narrow_refs)+len(notes)+(1 if narrative_present else 0)
    broad_count=len(broad_keys)+len(broad_refs)+len(retired_current_caches)
    return {
        'required':required,'minimum_version':version_text(CURRENT_SEMANTIC_HYGIENE_MIN_VERSION),
        'broad_required':broad_required,'broad_minimum_version':version_text(BROAD_CURRENT_VERSION_HYGIENE_MIN_VERSION),
        'save_version':state.get('save_version') if isinstance(state,dict) else None,
        'versioned_current_string_ref_count':len(narrow_refs),'versioned_current_string_refs':narrow_refs[:100],
        'broad_versioned_current_key_count':len(broad_keys),'broad_versioned_current_keys':broad_keys[:100],
        'broad_versioned_current_string_ref_count':len(broad_refs),'broad_versioned_current_string_refs':broad_refs[:100],
        'active_or_queued_current_note_count':len(notes),'active_or_queued_current_notes':notes[:100],
        'narrative_state_present':narrative_present,'retired_current_cache_count':len(retired_current_caches),'retired_current_caches':retired_current_caches,'base_count':base_count,'broad_count':broad_count,
        'count':base_count+(broad_count if broad_required else 0),
    }


def versioned_current_plan(base:Path=ROOT)->dict:
    """Inventory and classify legacy version-suffixed current-state objects.

    This is advisory only.  It deliberately refuses to infer that an old-looking object
    is obsolete merely from age.  High-confidence rows require mechanical evidence such
    as a terminal state, an unreferenced derived cache, an exact canonical duplicate, or
    a same-base older version with a newer version present.  Semantic migrations still
    require a transaction that preserves full removed values in HISTORY.
    """
    ensure_source_ready(base);state=read_json(base/'state.json');tasks=read_json(base/'tasks.json')
    task_blob=json.dumps(tasks,ensure_ascii=False,separators=(',',':'))
    refs=((state.get('engine_runtime') or {}).get('state_refs') or {})
    ref_paths={str(v):str(k) for k,v in refs.items() if isinstance(v,str)}
    rows=[];groups={}
    def walk(x,path=''):
        if not isinstance(x,dict):return
        for k,v in x.items():
            p=f'{path}.{k}' if path else k;m=VERSIONED_CURRENT_KEY_RE.match(str(k))
            if m:
                base_key=m.group('base')+'_current';parent_path=path
                canonical=f'{parent_path}.{base_key}' if parent_path else base_key
                row={'path':'STATE.'+p,'state_path':p,'leaf':k,'base_key':base_key,'version_suffix':int(m.group('version')),'version_rank':list(_legacy_current_version_rank(m.group('version'))),'version_text':f"V{m.group('version')[0]}.{m.group('version')[1:] or '0'}",'canonical_candidate':'STATE.'+canonical,'bytes':len(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode('utf-8'))}
                if isinstance(v,dict):
                    row['as_of']=v.get('as_of') or v.get('updated_at') or v.get('last_updated_at');row['status']=v.get('status')
                row['task_text_reference']=str(k) in task_blob or p in task_blob
                row['stable_ref']=ref_paths.get(p)
                par=x;row['canonical_exists']=base_key in par
                row['canonical_exact_duplicate']=bool(base_key in par and par.get(base_key)==v)
                rows.append(row);groups.setdefault((parent_path,base_key),[]).append(row)
            if isinstance(v,dict):walk(v,p)
            elif isinstance(v,list):
                for i,z in enumerate(v):
                    if isinstance(z,dict):walk(z,f'{p}[{i}]')
    walk(state)
    derived_tokens=('combat_power','display','snapshot','summary','cache')
    for r in rows:
        chain=sorted([z for z in rows if z['canonical_candidate']==r['canonical_candidate']],key=lambda z:tuple(z['version_rank']))
        r['same_base_versions']=[z['version_text'] for z in chain]
        is_latest=not chain or tuple(r['version_rank'])==tuple(chain[-1]['version_rank']);r['latest_in_same_base_chain']=is_latest
        st=str(r.get('status') or '').lower();terminal=(st in {'completed','complete','resolved','closed','cancelled','archived','expired','stopped'} or st.startswith(('completed_','resolved_','closed_','cancelled_','archived_','expired_','stopped_')))
        derived=any(tok in str(r['leaf']).lower() for tok in derived_tokens)
        reasons=[];classification='semantic_review';confidence='low'
        if r['canonical_exact_duplicate'] and not r['task_text_reference']:
            classification='archive_exact_duplicate';confidence='high';reasons.append('exact_duplicate_of_existing_canonical')
        elif terminal and not r['task_text_reference'] and not r.get('stable_ref'):
            classification='archive_terminal';confidence='high';reasons.append('terminal_status')
        elif derived and not r['task_text_reference'] and not r.get('stable_ref'):
            classification='archive_derived_cache';confidence='high';reasons.append('unreferenced_derived_cache')
        elif len(chain)>1 and not is_latest and not r['task_text_reference'] and not r.get('stable_ref'):
            classification='superseded_same_base_version';confidence='medium';reasons.append('newer_same_base_version_exists')
        elif is_latest and not r['task_text_reference'] and not r.get('stable_ref'):
            classification='canonicalize_or_archive_after_semantic_check';confidence='medium';reasons.append('unreferenced_latest_versioned_current')
        if r['task_text_reference']:reasons.append('task_reference_protect')
        if r.get('stable_ref'):reasons.append('stable_ref_protect')
        r['classification']=classification;r['confidence']=confidence;r['reasons']=reasons
    rank={'high':0,'medium':1,'low':2};rows.sort(key=lambda r:(rank.get(r['confidence'],9),r['canonical_candidate'],tuple(r['version_rank'])))
    return {'packet':'VERSIONED_CURRENT_PLAN_V1','engine_version':ENGINE_VERSION,'state_bytes':(base/'state.json').stat().st_size,'count':len(rows),'high_confidence_count':sum(r['confidence']=='high' for r in rows),'medium_confidence_count':sum(r['confidence']=='medium' for r in rows),'rows':rows,'auto_apply':False,'policy':'Advisory classifier only. Age alone never authorizes deletion. Any removal/rename must be a zero-time transaction with full removed payload archived to HISTORY and authority coverage checks.'}

def state_archive_plan(base:Path=ROOT)->dict:
    """Reference-aware semantic archive discovery for STATE.

    High-confidence candidates are large objects that look terminal/historical and are
    not referenced by active task retrieval routes. This remains a plan: deletion must
    happen transactionally with a HISTORY final-state record.
    """
    ensure_source_ready(base);state=read_json(base/"state.json");tasks=read_json(base/"tasks.json");cands=[]
    terminal={"resolved","closed","completed","complete","cancelled","archived","terminal","sold","delivered","destroyed","expired"}
    active_refs=set()
    for task in tasks.get('active_tasks',[]) or []:
        rr=task.get('retrieval_route') or {}
        for pth in rr.get('state_paths',[]) or []:
            if isinstance(pth,str) and pth.strip():
                try:active_refs.add(resolve_state_ref(state,pth.strip()))
                except KeyError:active_refs.add(pth.strip())
    current_tokens=('current','latest','active','ongoing','pending','open','next','available','inventory','balance','summary','recovery','runtime')
    history_tokens=('history','historical','archive','archived','completed','completion','result','resolved','closed','legacy','former','previous','sold','delivered','ended')
    def referenced(path:str)->bool:
        raw=path[6:] if path.startswith(('STATE.','state:')) else path
        raw=re.sub(r'\[\d+\]','',raw)
        return any(raw==r or raw.startswith(r+'.') or r.startswith(raw+'.') for r in active_refs)
    def nested_current_signal(obj:Any,depth:int=0)->bool:
        if depth>6:return False
        if isinstance(obj,dict):
            st=str(obj.get('status') or obj.get('phase') or '').lower()
            if st.startswith(('active','pending','waiting','ongoing','monitoring','operational','deployed','in_service','awaiting')):return True
            for k,v in obj.items():
                kl=str(k).lower()
                if kl.startswith('next_') and v not in (None,'',False,0):return True
                if isinstance(v,(dict,list)) and nested_current_signal(v,depth+1):return True
        elif isinstance(obj,list):
            return any(nested_current_signal(v,depth+1) for v in obj if isinstance(v,(dict,list)))
        return False
    def rec(x,path,depth=0):
        if depth>10:return
        if isinstance(x,dict):
            raw_len=len(json.dumps(x,ensure_ascii=False,separators=(",",":")))
            st=str(x.get("status") or x.get("phase") or "").lower();leaf=path.rsplit('.',1)[-1].lower()
            signals=[];guards=[]
            terminal_prefix=any(st.startswith(p) for p in ('completed_','resolved_','closed_','sold_','delivered_','destroyed_','archived_','expired_'))
            if st in terminal or terminal_prefix:signals.append('terminal_status')
            historical_leaf=any(tok in leaf for tok in history_tokens)
            if historical_leaf:signals.append('historical_path_name')
            if any(k in x for k in ('completed_at','resolved_at','closed_at','sold_at','delivered_at','ended_at')):signals.append('terminal_timestamp')
            if historical_leaf and any(x.get(k) for k in ('as_of','boarded_at','reported_at','result_at')):signals.append('historical_snapshot_timestamp')
            fullp=path.lower()
            if any(tok in fullp for tok in current_tokens):guards.append('current_path_name')
            _st=str(x.get('status') or '').lower()
            if _st.startswith('active') or 'operational' in _st or 'deployed' in _st or _st in {'ongoing','pending','open','monitoring','in_service'}:guards.append('active_status')
            if any(k in x for k in ('next_review_at','next_settlement_at','next_trigger','eta')) and any(x.get(k) for k in ('next_review_at','next_settlement_at','next_trigger','eta')):guards.append('future_trigger')
            if referenced(path):guards.append('active_task_reference')
            if nested_current_signal(x):guards.append('nested_current_signal')
            confidence='none'
            if raw_len>800 and signals and not guards:
                confidence='high' if ('terminal_status' in signals or 'terminal_timestamp' in signals or len(signals)>=2) else 'medium'
            elif raw_len>1600 and len(signals)>=2 and 'active_task_reference' not in guards:confidence='medium'
            if confidence!='none':cands.append({"path":path,"status":st or None,"bytes":raw_len,"confidence":confidence,"history_signals":signals,"current_guards":guards})
            for k,v in x.items():
                if isinstance(v,(dict,list)):rec(v,f"{path}.{k}" if path else k,depth+1)
        elif isinstance(x,list):
            for i,v in enumerate(x):
                if isinstance(v,(dict,list)):rec(v,f"{path}[{i}]",depth+1)
    rec(state,"STATE");rank={'high':0,'medium':1};cands.sort(key=lambda x:(rank.get(x['confidence'],9),-x['bytes']))
    return {"packet":"STATE_ARCHIVE_PLAN_V3","state_bytes": (base/"state.json").stat().st_size,"active_state_path_references":len(active_refs),"candidate_count":len(cands),"high_confidence_count":sum(1 for x in cands if x['confidence']=='high'),"candidates":cands[:50],"auto_delete":False,"auto_apply_high_confidence":True,"policy":"statearchive can transactionally archive high-confidence candidates after first copying their final snapshot to HISTORY; medium candidates remain advisory; active task references and current/future signals are protected."}


def _state_archive_prune_descendants(rows:List[dict])->Tuple[List[dict],List[dict]]:
    """Keep only minimal root paths when a selected archive object contains selected descendants."""
    ordered=sorted((copy.deepcopy(x) for x in rows if isinstance(x,dict) and x.get('path')),key=lambda x:(str(x['path']).count('.'),len(str(x['path'])),str(x['path'])))
    roots=[];suppressed=[]
    for row in ordered:
        p=str(row['path'])
        parent=next((r for r in roots if p.startswith(str(r['path'])+'.')),None)
        if parent is not None:
            rr=copy.deepcopy(row);rr['covered_by_parent']=str(parent['path']);suppressed.append(rr)
        else:roots.append(row)
    return roots,suppressed


def state_archive_apply(root:Path=ROOT,version:Optional[str]=None,scope:str='STATE semantic archive',dry_run:bool=False)->dict:
    """Transactionally archive only high-confidence unreferenced STATE objects.

    Medium-confidence candidates remain advisory. Every removed object is copied in
    full into HISTORY before authority is committed, so the operation is reversible
    from the append-only historical record.
    """
    plan=state_archive_plan(root);raw_selected=[x for x in plan.get('candidates',[]) if x.get('confidence')=='high'];selected,suppressed=_state_archive_prune_descendants(raw_selected)
    if dry_run or not selected:
        return {'status':'DRY_RUN' if dry_run else 'NOOP','packet':'STATE_ARCHIVE_APPLY_V1','selected':selected,'selected_count':len(selected),'suppressed_descendants':suppressed,'suppressed_count':len(suppressed),'saved':False,'policy':'high-confidence only; parent selections subsume descendants; medium remains manual'}
    if not version:raise EngineError('STATE_ARCHIVE_VERSION_REQUIRED')
    info=create_stage(root,'statearchive');stage=Path(info['staging'])
    try:
        state=read_json(stage/'state.json');archived={};changes=[]
        for row in selected:
            path=str(row.get('path') or '')
            if not path.startswith(('STATE.','state:')) or '[' in path:raise EngineError(f'STATE_ARCHIVE_PATH_UNSUPPORTED:{path}')
            par,key=_dot_parent(state,path[6:])
            if key not in par:raise EngineError(f'STATE_ARCHIVE_PATH_MISSING:{path}')
            archived[path]=copy.deepcopy(par[key]);del par[key];changes.append({'target':path,'action':'archive_to_history_then_remove'})
        gt=str(state.get('game_time') or read_json(stage/'tasks.json').get('game_time') or '')
        digest=sha256_bytes('|'.join(sorted(archived)).encode('utf-8'))[:12]
        _append_engine_history(stage/'events.jsonl',{'event_id':f'EVT-STATE-ARCHIVE-{gt.replace("-","").replace(":","").replace("T","-")}-{digest}','game_time':gt,'type':'state_semantic_archive','summary':f'GAME ENGINE v{ENGINE_VERSION}事务归档{len(archived)}个high-confidence纯历史STATE对象；完整原值已先写入HISTORY。','changes':changes,'source':f'GAME ENGINE v{ENGINE_VERSION} STATE_ARCHIVE_APPLY_V1','authority_files':['state.json'],'archived_state_objects':archived,'zero_time':True})
        _write_authority_json(stage/'state.json',state)
        saved=atomic_save(stage,version,scope,root,False,False)
        return {'status':'SAVED','packet':'STATE_ARCHIVE_APPLY_V1','selected_count':len(selected),'suppressed_descendants':suppressed,'suppressed_count':len(suppressed),'archived_paths':sorted(archived),'save':saved}
    except Exception:
        try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
        except Exception:pass
        raise



# V10 WORLD purification: archive only exact, high-confidence dynamic historical
# subsections. Permanent RULE-* sections and mixed sections are deliberately
# excluded. This registry is explicit so version-number heuristics can never
# delete a future rule accidentally.
WORLD_PURIFY_V1_HEADINGS=(
    "暗影快反部队V8.90重装",
    "白峡和平与灰烬新增兵源",
    "弦月三日大会战结局",
    "暗影舰队舰载无人机/机器人统一升级与库存归位",
    "暗影三账口径V8.95",
    "WORLD-SEALED-V896-83621105 当前轮封板事实索引",
    "V8.100军火招标与待入库封板",
    "V8.100远航者基地与沃克研究封板",
    "V8.100弦月/岩槐/苇桥反恐态势",
    "V8.101灰烬吸收“灰链”残余",
    "V8.101赤猎旅吸收跨境极端邪教",
    "V8.101弦月四线反恐战况",
    "V8.102苇桥-2战时动员、军购与佣兵合同",
    "V8.102苇桥-2“核心环保卫战”与援军抵达",
    "V8.102弦月自治星人道、经济与治安危机",
    "V8.102灰烬新一轮扩军与自由港军用品仓突袭",
    "V8.102八大恐怖组织当前军事实力估计",
    "V8.102玩家舰队进度与经济日结",
    "V9.25 HISTORICAL CURRENT OVERRIDE（已由STATE V9.27当前镜像取代）｜8363-01-02 06:40",
)


def _world_markdown_h3_sections(text:str)->list:
    lines=text.splitlines(keepends=True);starts=[];offset=0
    for i,line in enumerate(lines):
        if line.startswith('### ') and not line.startswith('#### '):starts.append((i,offset,line[4:].strip()))
        offset+=len(line)
    out=[]
    prefix=[];acc=0
    for x in lines:prefix.append(acc);acc+=len(x)
    for li,start,title in starts:
        end=len(text)
        for j in range(li+1,len(lines)):
            if (lines[j].startswith('### ') and not lines[j].startswith('#### ')) or (lines[j].startswith('## ') and not lines[j].startswith('### ')):
                end=prefix[j];break
        out.append({'title':title,'start':start,'end':end,'text':text[start:end]})
    return out


def _v130_layer_world_purify_plan_01(base:Path=ROOT)->dict:
    ensure_source_ready(base);wp=base/'WORLD.md';text=wp.read_text(encoding='utf-8');sections=_world_markdown_h3_sections(text);by={x['title']:x for x in sections};rows=[];missing=[]
    for title in WORLD_PURIFY_V1_HEADINGS:
        sec=by.get(title)
        if sec is None:missing.append(title);continue
        rows.append({'title':title,'bytes':len(sec['text'].encode('utf-8')),'sha256':sha256_bytes(sec['text'].encode('utf-8')),'contains_rule_heading':bool(re.search(r'(?m)^####?\s+RULE-',sec['text']))})
    return {'packet':'WORLD_PURIFY_PLAN_V1','schema':WORLD_PURIFY_SCHEMA,'world_bytes':wp.stat().st_size,'candidate_count':len(rows),'candidate_bytes':sum(x['bytes'] for x in rows),'missing_count':len(missing),'missing':missing,'candidates':rows,'safe_to_apply':len(rows)>0 and not missing and not any(x['contains_rule_heading'] for x in rows),'policy':'explicit exact-heading registry only; RULE-* and mixed sections are never selected by version heuristics'}


def _v130_layer__world_purify_stage_01(stage:Path)->dict:
    wp=stage/'WORLD.md';text=wp.read_text(encoding='utf-8');sections=_world_markdown_h3_sections(text);by={x['title']:x for x in sections};missing=[x for x in WORLD_PURIFY_V1_HEADINGS if x not in by]
    if missing:raise EngineError('WORLD_PURIFY_SECTION_MISSING:'+','.join(missing))
    chosen=[by[x] for x in WORLD_PURIFY_V1_HEADINGS]
    for sec in chosen:
        if re.search(r'(?m)^####?\s+RULE-',sec['text']):raise EngineError('WORLD_PURIFY_RULE_SECTION_SELECTED:'+sec['title'])
    before_rules=set(re.findall(r'(?m)^###\s+(RULE-[A-Z0-9_-]+)',text));new=text
    for sec in sorted(chosen,key=lambda x:x['start'],reverse=True):new=new[:sec['start']]+new[sec['end']:]
    new=re.sub(r'\n{4,}','\n\n\n',new);after_rules=set(re.findall(r'(?m)^###\s+(RULE-[A-Z0-9_-]+)',new))
    if before_rules!=after_rules:raise EngineError(f'WORLD_PURIFY_RULE_SET_CHANGED:lost={sorted(before_rules-after_rules)}:added={sorted(after_rules-before_rules)}')
    remain=[x for x in WORLD_PURIFY_V1_HEADINGS if ('### '+x) in new]
    if remain:raise EngineError('WORLD_PURIFY_SECTION_REMAINED:'+','.join(remain))
    archived={x['title']:x['text'] for x in chosen};gt=str(read_json(stage/'state.json').get('game_time') or read_json(stage/'tasks.json').get('game_time') or '')
    digest=sha256_bytes(json.dumps(sorted(archived),ensure_ascii=False,separators=(',',':')).encode('utf-8'))[:12]
    event={'event_id':f'EVT-WORLD-PURIFY-{gt.replace("-","").replace(":","").replace("T","-")}-{digest}','game_time':gt,'type':'world_historical_snapshot_archive','summary':f'GAME ENGINE v{ENGINE_VERSION}将{len(chosen)}个已被更强current事实取代的WORLD动态历史小节完整归档至HISTORY；RULE-*永久规则与混合段未删除。','changes':[{'target':f'WORLD.section:{x["title"]}','action':'archive_to_history_then_remove'} for x in chosen],'source':f'GAME ENGINE v{ENGINE_VERSION} WORLD_PURIFY_V1','authority_files':['WORLD.md'],'zero_time':True,'archived_world_sections':archived,'policy':'exact_heading_high_confidence_dynamic_history_only'}
    _append_engine_history(stage/'events.jsonl',event);wp.write_text(new,encoding='utf-8')
    return {'packet':'WORLD_PURIFY_STAGE_V1','archived_count':len(chosen),'archived_bytes':sum(len(x['text'].encode('utf-8')) for x in chosen),'world_bytes_before':len(text.encode('utf-8')),'world_bytes_after':len(new.encode('utf-8')),'event_id':event['event_id'],'rule_count':len(after_rules),'archived_titles':list(WORLD_PURIFY_V1_HEADINGS)}


def _v130_layer_world_purify_apply_01(root:Path=ROOT,version:Optional[str]=None,scope:str='WORLD historical snapshot purification',dry_run:bool=False)->dict:
    plan=world_purify_plan(root)
    if dry_run:return {'status':'DRY_RUN','packet':'WORLD_PURIFY_APPLY_V1','plan':plan,'saved':False}
    if plan.get('candidate_count')==0:return {'status':'NOOP','packet':'WORLD_PURIFY_APPLY_V1','plan':plan,'saved':False}
    if not plan.get('safe_to_apply'):raise EngineError('WORLD_PURIFY_PLAN_NOT_SAFE')
    if not version:raise EngineError('WORLD_PURIFY_VERSION_REQUIRED')
    info=create_stage(root,'worldpurify');stage=Path(info['staging'])
    try:
        detail=_world_purify_stage(stage);chk=run_checks(stage,full=True,require_manifest=False)
        if chk.get('status')!='PASS':raise EngineError('WORLD_PURIFY_POSTCHECK_FAILED:'+json.dumps(chk,ensure_ascii=False)[-1200:])
        saved=atomic_save(stage,version,scope,root,False,False)
        return {'status':'SAVED','packet':'WORLD_PURIFY_APPLY_V1','plan':plan,'detail':detail,'save':saved}
    except Exception:
        try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
        except Exception:pass
        raise

TASK_COMPACT_HISTORY_KEY_TOKENS=("_result","result_","completed_","_completed","resolved_","_resolved","closed_","_closed","previous_","legacy_","reply_history","review_history","round_history","breakthrough_history","arrival_history","departure_history")
TASK_COMPACT_CURRENT_KEY_TOKENS=("current","next_","active","remaining","authority","status","pending","history_archive_event_id")
TASK_COMPACT_TERMINAL_STATUS={"resolved","closed","completed","complete","cancelled","archived","sold","delivered","destroyed","expired"}

def _task_compactable_keys(task:dict)->List[dict]:
    td=task.get('task_data') or {};rows=[]
    if not isinstance(td,dict):return rows
    for k,v in td.items():
        kl=str(k).lower();vs=len(json.dumps(v,ensure_ascii=False,separators=(',',':')))
        if any(x in kl for x in TASK_COMPACT_CURRENT_KEY_TOKENS):continue
        name_signal=any(x in kl for x in TASK_COMPACT_HISTORY_KEY_TOKENS)
        status_signal=isinstance(v,dict) and str(v.get('status') or v.get('phase') or '').lower() in TASK_COMPACT_TERMINAL_STATUS
        timestamp_signal=isinstance(v,dict) and any(v.get(x) for x in ('completed_at','resolved_at','closed_at','sold_at','delivered_at','ended_at'))
        if vs>80 and (name_signal or (status_signal and timestamp_signal)):
            rows.append({'key':k,'bytes':vs,'signals':sorted([x for x,ok in [('history_key',name_signal),('terminal_status',status_signal),('terminal_timestamp',timestamp_signal)] if ok])})
    return sorted(rows,key=lambda x:-x['bytes'])

def task_compact_plan(base:Path=ROOT)->dict:
    ensure_source_ready(base);tasks=read_json(base/'tasks.json');rows=[]
    for bucket in ('active_tasks','queued_tasks'):
        for task in tasks.get(bucket,[]) or []:
            if not isinstance(task,dict):continue
            td=task.get('task_data') or {};size=len(json.dumps(task,ensure_ascii=False,separators=(',',':')));td_size=len(json.dumps(td,ensure_ascii=False,separators=(',',':')));keys=_task_compactable_keys(task)
            if keys:
                rows.append({'task_id':task.get('task_id'),'title':task.get('title'),'bucket':bucket,'bytes':size,'task_data_bytes':td_size,'history_like_bytes':sum(x['bytes'] for x in keys),'history_like_keys':keys})
    rows.sort(key=lambda x:-x['history_like_bytes'])
    return {'packet':'TASK_COMPACT_PLAN_V2','task_count':sum(len(tasks.get(x,[]) or []) for x in ('active_tasks','queued_tasks')),'candidate_count':len(rows),'candidates':rows,'auto_apply_safe_keys':True,'policy':'Only high-confidence historical task_data keys are compacted. Removed values are copied in full to HISTORY in the same transaction; current/next/active/pending/authorization/status fields are hard-protected.'}

def _compact_tasks_in_stage(stage:Path,reason:str='precommit_auto')->dict:
    tasks=read_json(stage/'tasks.json');removed={};changes=[]
    for bucket in ('active_tasks','queued_tasks'):
        for task in tasks.get(bucket,[]) or []:
            if not isinstance(task,dict):continue
            td=task.get('task_data')
            if not isinstance(td,dict):continue
            keys=_task_compactable_keys(task)
            if not keys:continue
            tid=str(task.get('task_id') or '<unknown>');entry={}
            for row in keys:
                key=row['key'];entry[key]=copy.deepcopy(td[key]);del td[key];changes.append({'target':f'TASKS.{bucket}.{tid}.task_data.{key}','action':'archive_to_history_then_remove'})
            if entry:removed[tid]={'bucket':bucket,'title':task.get('title'),'task_data':entry}
    if not removed:return {'packet':'TASK_COMPACT_APPLY_V2','status':'NOOP','removed_task_count':0,'removed_key_count':0}
    gt=str(tasks.get('game_time') or read_json(stage/'state.json').get('game_time') or '');digest=sha256_bytes(json.dumps(removed,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))[:12]
    _append_engine_history(stage/'events.jsonl',{'event_id':f'EVT-TASK-COMPACT-{gt.replace("-","").replace(":","").replace("T","-")}-{digest}','game_time':gt,'type':'task_history_compaction','summary':f'GAME ENGINE v{ENGINE_VERSION}自动瘦身TASKS：{len(removed)}个任务的高置信历史字段已完整迁入HISTORY。','changes':changes,'source':f'GAME ENGINE v{ENGINE_VERSION} TASK_COMPACT_APPLY_V2/{reason}','authority_files':['tasks.json'],'archived_task_data':removed,'zero_time':True})
    _write_authority_json(stage/'tasks.json',tasks)
    return {'packet':'TASK_COMPACT_APPLY_V2','status':'APPLIED','removed_task_count':len(removed),'removed_key_count':sum(len(x['task_data']) for x in removed.values()),'task_ids':sorted(removed)}

def task_compact_apply(root:Path=ROOT,version:Optional[str]=None,scope:str='TASKS automatic historical compaction',dry_run:bool=False)->dict:
    plan=task_compact_plan(root)
    if dry_run or not plan.get('candidate_count'):
        return {'packet':'TASK_COMPACT_APPLY_V2','status':'DRY_RUN' if dry_run else 'NOOP','plan':plan,'saved':False}
    if not version:raise EngineError('TASK_COMPACT_VERSION_REQUIRED')
    info=create_stage(root,'taskcompact');stage=Path(info['staging'])
    try:
        applied=_compact_tasks_in_stage(stage,'explicit_command')
        saved=atomic_save(stage,version,scope,root,False,False)
        return {'packet':'TASK_COMPACT_APPLY_V2','status':'SAVED','applied':applied,'save':saved}
    except Exception:
        try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
        except Exception:pass
        raise

def _derived_state_footprint(state:dict)->dict:
    rows=[]
    def walk(x,path='STATE'):
        if isinstance(x,dict):
            for k,v in x.items():
                p=f'{path}.{k}';lk=str(k).lower()
                if any(tok in lk for tok in ('snapshot','display')) and not any(tok in p.lower() for tok in ('histor','archive')):
                    try:size=len(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
                    except Exception:size=0
                    rows.append({'path':p,'bytes':size})
                walk(v,p)
        elif isinstance(x,list):
            for i,v in enumerate(x):walk(v,f'{path}[{i}]')
    walk(state);rows.sort(key=lambda r:r['bytes'],reverse=True)
    return {'bytes':sum(x['bytes'] for x in rows),'count':len(rows),'largest':rows[:8]}

def _query_contract_status(base:Path)->dict:
    topics=['当前任务','下一确定事件','远航者舰队当前状态','远航者舰队当前位置','金川舰队当前状态','暗影舰队当前状态','当前库存','当前资金','舰队核心','待履行事项','远航者逐舰战力']+(['灭灯会实体'] if isinstance((read_json(base/'state.json') if (base/'state.json').is_file() else {}).get('entity_registry'),dict) else [])
    rows=[]
    for topic in topics:
        try:q=query_packet(base,topic,detail='compact');rows.append({'topic':topic,'status':q.get('status'),'packet':q.get('packet'),'truncated':bool(q.get('truncated')),'nested_truncated':_query_has_truncated_evidence(q.get('value'))})
        except Exception as ex:rows.append({'topic':topic,'status':'ERROR','error':str(ex)})
    failed=[x for x in rows if x.get('status')!='COMPLETE' or x.get('truncated') or x.get('nested_truncated')]
    return {'schema':'QUERY_CONTRACT_V3','checks':rows,'failure_count':len(failed),'failed':failed}

