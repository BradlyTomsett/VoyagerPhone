# === VOYAGER_DEV_MODULE: legacy_migration ===
def _mobile_world_protocol(text):
    text=text.replace('V7.0-R17','V7.0-R18')
    additions='''
### RULE-MOBILE-SEVEN-FILE-01 七文件运行分工与短回复协议
- 适用条件：STATE.engine_runtime.mobile_contract.schema=MOBILE_SEVEN_FILE_V1。关于查询、暂停保存、冷启动的旧实现说明与本节冲突时，按本节执行；其他世界设定不因此变化。
- 唯一事实边界：WORLD稳定设定和内嵌机器规则；STATE当前状态；TASKS调度/授权/稳定引用；HISTORY追加历史；INDEX启动路由和manifest；当前Engine与Guard各一份。不得增加第八个项目来源。
- 先Guard --resume一次，再按问题调用query或querybatch。精确命中优先；compact中的TRUNCATED/PARTIAL不能宣称证据完整。只在缺口处调用evidence分页补取，禁止默认全文读取所有七文件。
- 引擎承担已有确定规则的时间、财务、进度、维修、随机检查和战斗数值；AI承担未知语义与副官叙事。没有执行工具不得声称已调用、已结算、已保存；执行环境不可用时暂停状态修改。
- 每次实际指令最多推进24小时；分段继续同一指令仍共享起始时间。过期机械任务先暴露核对屏障，不自动猜补旧账。无信号的外部等待任务不因时间流逝反复唤醒。
- 语义屏障在已知安全边界提交pending_turn；七文件携带待办窗口，session resume恢复。COMMITTED/PAUSED_COMMITTED仅说明运行环境已保存，不能证明手机版Project来源已经更新。换对话前用package生成同批七文件并替换项目来源；旧七文件仍只能恢复旧进度。
- reportframe --since-seq以HISTORY序号读取同一时刻多笔交易；按舰队给出收入、支出、净额。报告保留舰桥时间、全部独立舰队核心、随机事件、当前态势；普通回复只展开本轮变化与待决事项，重大作战增加可靠战力/武器/过程/分型号损失。叙事不得产生未提交的数字或战果。
- 常规科研销售从STATE目录筛选在售包、逐包价格与销量区间，新增商品无需复制TASKS清单；未获授权的新价格、实体或收益不能靠优化自动生成。迁移漏接目录只影响启用后的新轮次，不补历史两轮未知销量。
- 金额计算按币种定点：金币4位、灰币2位；正式舰桥余额均显示整数及千分位。游戏数值校验、随机种子和历史前缀完整性不能为提速关闭。
- 自动化建议只从尚未自动执行的近期重复事件提取；建议不自动改代码。升级仍必须通过编译、自检、兼容、隔离冷启动、性能与零时间提交门。
'''
    if '### RULE-MOBILE-SEVEN-FILE-01' not in text:text=text.rstrip()+'\n'+additions
    return text

def _migrate_mobile_seven(stage):
    state=read_json(stage/'state.json');tasks=read_json(stage/'tasks.json')
    if _mobile_contract(state):return {'changed':False}
    gt=state['game_time'];now=parse_iso(gt);archives={};changes=[];er=state.setdefault('engine_runtime',{})
    er['mobile_contract']={'schema':MOBILE_CONTRACT_SCHEMA,'activated_at':gt,'single_advance_max_hours':24,'money_decimal_places':copy.deepcopy(MONEY_DECIMAL_PLACES),'source_sync':'user_replaces_seven_project_sources','watch_signal_policy':'canonical_state_change_without_periodic_polling'}
    for k in ('gold','grey'):state['summary']['funds'][k]=_money_currency(state['summary']['funds'][k],k)
    reg=er['player_fleet_registry']['fleets']
    for fid,name,sp in [('voyager','远航者舰队','summary.ships.voyager'),('jinchuan','金川舰队','summary.ships.jinchuan'),('shadow','暗影舰队','summary.ships.shadow_active')]:reg[fid].update({'display_name':name,'primary_ship_count_path':'STATE.'+sp})
    program=state['world_state_overrides']['markets_and_procurement']['research_data_sales_program'];catalog=program['packages']
    sales=next(t for t in tasks['active_tasks'] if t['task_id']=='TSK-MKT-RESEARCH-DATA-SALES');td=sales['task_data'];archives['research_task_before']=copy.deepcopy(sales)
    for pid,rec in catalog.items():
        rec['sales_range']=copy.deepcopy(td['sales_ranges'].get(pid,[8,16]));rec['mechanical_sales_from']=gt
        rec['sales_range_basis']='preserved_existing_rule' if pid in td['sales_ranges'] else 'prospective_catalog_repair_default_8_16_no_backfill'
    rule=sales['runtime_policy']['settlement_rule'];cfg=rule['deterministic_unit_sales']
    cfg.update({'catalog_source':'STATE.world_state_overrides.markets_and_procurement.research_data_sales_program.packages','eligible_statuses':['on_sale','active_nonexclusive_digital_backup'],'round_note':'GAME ENGINE：按当前在售目录逐包结算去敏数字备份，不出售实物或独占授权。'})
    for k in ('items','ranges','unit_price'):cfg.pop(k,None)
    for k in ('packages','sales_ranges','catalog_package_count','price_gold_per_copy','last_sales_at','next_sales_at','last_sales_copies','last_sales_gold','cumulative_copies_confirmed','cumulative_gold_confirmed'):td.pop(k,None)
    for k in ('status_template','history_summary_template'):rule[k]=rule[k].replace('33类','{item_count}类')
    rule.pop('round_note',None)
    sales['autonomy']='王静可按STATE当前在售目录及逐包价格向合法机构重复销售去敏数字备份；沃克复核内容、保留原件/实物。实物、独占授权、保密核心技术与未去敏信息不得出售。'
    sales['decision_gate']='任何实物出售、独占买断、改变当前统一45金币定价需重新请示。'
    sales['semantic_context']='从STATE在售目录派生包数、单价、销售规则；03-12/03-13历史未确认轮次保持待核实，禁止补款。'
    td['catalog_source']=cfg['catalog_source']
    sales['retrieval_route']['query_aliases']=['科研销售','科研数据销售','卖资料']
    for k in ('as_of','last_sales_copies','last_sales_gold'):
        if k in program:archives.setdefault('research_stale_fields',{})[k]=program.pop(k)
    watchers=[]
    for task in tasks['active_tasks']:
        mon=task['runtime_policy']['monitor']
        if mon.get('mode')=='external_wait' and mon.get('event_driven') and not mon.get('watch_condition'):
            paths=(task.get('retrieval_route') or {}).get('state_paths') or []
            for p in paths:get_state_path(state,p)
            if not paths:raise EngineError('MIGRATION_WATCH_SOURCES_MISSING:'+task['task_id'])
            cond={'schema':'WATCH_CONDITION_V1','operator':'fingerprint_changed','sources':paths}
            cond['baseline_digest']=_watch_condition_digest(state,cond);mon['watch_condition']=cond;mon['requires_ai_review']=True;watchers.append(task['task_id'])
    # Existing two watchers retain their reviewed baselines, including any real pending signal.
    t7=next(t for t in tasks['active_tasks'] if t['task_id']=='TSK-JINCHUAN-T7-SALVAGE-CONSTRUCTION')
    obj=state['world_state_overrides']['mining_and_industry']['t7_salvage_zones_current'];archives['t7_before']={'state':copy.deepcopy(obj),'task':copy.deepcopy(t7)}
    start=parse_iso(obj['construction_started_at']);hours=obj['construction_hours_total'];progress=min(100.,max(0.,(now-start).total_seconds()/(hours*3600)*100))
    obj['progress_pct']=progress;obj['as_of']=gt
    mon=t7['runtime_policy']['monitor'];mon.update({'last_reviewed_at':gt,'requires_ai_review':False,'resolver':'progress_rule_v1'})
    path='STATE.world_state_overrides.mining_and_industry.t7_salvage_zones_current'
    mi=next(i for i,t in enumerate(tasks['active_tasks']) if t['task_id']=='TSK-MIN-OPERATIONS')
    # Completion uses stable task-id routing, never a positional list index.
    actions=[{'op':'set','target':path+'.status','value':'three_permanent_salvage_zones_operational'},{'op':'set','target':path+'.as_of','value':obj['estimated_complete']}]
    for zid in obj['zones']:actions.append({'op':'set','target':path+'.zones.'+zid+'.status','value':'operational'})
    for k,inc in [('daily_gold',obj['post_completion_unified_increment']['gold']),('daily_grey',obj['post_completion_unified_increment']['grey']),('fixed_salvage_bases',3)]:actions.append({'op':'increment','target':'TASKS.task:TSK-MIN-OPERATIONS.task_data.'+k,'value':inc})
    actions.extend([{'op':'increment','target':'STATE.world_state_overrides.mining_and_industry.jinchuan_resource_network_current.'+k,'value':inc} for k,inc in [('unified_daily_gold',326000),('unified_daily_grey',445000),('fixed_salvage_base_count',3)]])
    t7['runtime_policy']['progress_rule']={'schema':'PROGRESS_RULE_V1','target':path+'.progress_pct','rate_per_second':100/(hours*3600),'minimum':0,'maximum':100,'close_on_completion':True,'milestones':[{'threshold':100,'actions':actions}]}
    t7['phase']='construction_time_derived';t7['semantic_context']='引擎按已确认起点和288小时总工期派生进度；完工一次性加入金川未来日结产能，完工时不直接入账。'
    t7['view_rule']={'schema':'DERIVED_VIEW_RULE_V1','status_sources':[path[6:]],'next_source':'runtime_policy.monitor.next_review_at'}
    for k in ('current_status','next_trigger'):t7.pop(k,None)
    tasks['automation_schema'].update({'mobile_contract':MOBILE_CONTRACT_SCHEMA,'session_policy':'persist_safe_boundary_and_pending_turn_on_semantic_barrier','query_batch_schema':'QUERY_BATCH_V1','report_cursor_schema':'HISTORY_SEQ_CURSOR_V1'})
    w=(stage/'WORLD.md').read_text('utf-8')
    for heading in ('WORLD-V1096-CHENGGANG7-AND-INVENTORY-DELTA','WORLD-V1099-CURRENT-DELTA'):
        m=re.search(r'(?ms)^### '+heading+r'\n.*?(?=^### |\Z)',w)
        if m:archives[heading]=m.group(0);w=w[:m.start()]+w[m.end():]
    # Exact historical section survives in HISTORY; permanent geography remains searchable in WORLD.
    w+='\n### SETTING-CHENGGANG7-STABLE 澄港-7稳定地理与制度\n- 澄港-7为转运、维修、精炼与远程补给自治站；主环直径约42km，永久增压可用楼面约612km2，外港/工业管制区约1,430km2。站务议会与港务合作社联合自治，48席议会选7人执行委员会，4年周期；合作社参与港口基础设施与预算联合审计。人口、预算、警备数量与局势查STATE；旧8363-02-22快照见HISTORY归档。\n'
    machine=parse_world_runtime_rules(w)
    force=machine.get('force_generation',{}).get('future_random_force_composition',{})
    if 'attack_uav_multiplier' in force:archives['obsolete_attack_uav_multiplier']=force.pop('attack_uav_multiplier')
    force.pop('armed_uav_policy',None);force['battlefield_uav_policy']={'schema':'NPC_BATTLEFIELD_UAV_RATIO_V2','robots_per_uav_min':30,'robots_per_uav_max':60,'count_scope':'combined_armed_strike_plus_recon_battlefield_uavs','zero_allowed_for_small_forces':True,'player_force_exempt':True,'player_force_uses_actual_counts':True,'exceptions_require_explicit_source':True,'existing_sealed_counts_override':True,'enforcement':'generation_constraint_and_validateforce_preflight'}
    machine['mobile_operating_contract']={'schema':MOBILE_CONTRACT_SCHEMA,'max_advance_hours':24,'money_decimal_places':copy.deepcopy(MONEY_DECIMAL_PLACES),'catalog_sales_source':cfg['catalog_source'],'rule_implementation':{'RULE-GAME-ADVANCE-LIMIT-DEFAULT-24H-01':'engine:session+planner+commit_check','RULE-RESEARCH-DATA-UNIFORM-PRICE-45-01':'catalog+authorized_price_validation','RULE-MOBILE-SEVEN-FILE-01':'engine+AI_report_and_source_upload_protocol','NPC_BATTLEFIELD_UAV_RATIO_V2':'validateforce_generation_preflight; combined armed+recon; player actual counts; existing forces preserved'}}
    w=re.sub(r'<!-- VOYAGER_RUNTIME_RULES_V1\s*.*?\s*VOYAGER_RUNTIME_RULES_V1_END -->',lambda m:'<!-- VOYAGER_RUNTIME_RULES_V1\n'+json.dumps(machine,ensure_ascii=False,separators=(',',':'))+'\nVOYAGER_RUNTIME_RULES_V1_END -->',w,count=1,flags=re.S)
    w=_mobile_world_protocol(w);(stage/'WORLD.md').write_text(w,encoding='utf-8',newline='\n')
    checkpoint=state['world_state_overrides'].pop('current_continuity_checkpoint',None)
    if checkpoint:archives['old_continuity_checkpoint']=checkpoint
    wso=state['world_state_overrides']
    archives['economic_query_mirrors']={'mining_multinational':copy.deepcopy(wso['mining_and_industry']['multinational_industry_current']),'organizations':copy.deepcopy(wso['organizations_current']['controlled_economic_organizations'])}
    wso['mining_and_industry']['multinational_industry_current']={'canonical_ref':'ref:MULTINATIONAL_INDUSTRY_CURRENT','role':'routing_only'}
    org=wso['organizations_current']['controlled_economic_organizations']
    org['多国产业运营']={'canonical_ref':'ref:MULTINATIONAL_INDUSTRY_CURRENT','role':'routing_only'}
    org['金川矿业体系']={'canonical_ref':'ref:JINCHUAN_RESOURCE_NETWORK_CURRENT','role':'routing_only','reporting_note':'M-22高纯硅酸盐完全并入统一结算，不单列。'}
    ip=stage/'INDEX.md'
    if ip.is_file():
        idx=ip.read_text('utf-8').replace('V7.0-R4','V7.0-R5').replace('V7.0-R17','V7.0-R18')
        idx=re.sub(r'^- 当前商业经营权威对象为.*$', '- 商业经营当前资产数与收益统一读取`ref:MULTINATIONAL_INDUSTRY_CURRENT`；卡尔德552项仅为已封板子组件，不另设日结。',idx,flags=re.M)
        idx+='\n## 机器调用补充\n- 一轮多个查询：`querybatch --topics \'["当前金币余额","科研销售"]\'`。TRUNCATED/PARTIAL按返回路径用evidence或context补缺口，不默认全文重读。\n- 汇报游标：`reportframe --since-seq <本轮开始序号> --since <本轮开始时间>`；金币整数显示，后端4位；新增舰队注册计数路径后自动加入核心栏。\n- `PAUSED_COMMITTED`：安全边界和pending_turn已提交；`session resume`返回可应用语义补丁的session id，再apply/advance。不要把屏障描述成已处理。\n- 正式COMMIT自动生成可交接的同批完整ZIP与匹配Guard；引擎不能确认手机Project来源是否已同步。新对话依赖实际上传的最新一批。\n'
        ip.write_text(idx,encoding='utf-8',newline='\n')
    _write_authority_json(stage/'state.json',state);_write_authority_json(stage/'tasks.json',tasks)
    _append_engine_history(stage/'events.jsonl',{'event_id':'MIGRATION-MOBILE-SEVEN-83630401','game_time':gt,'type':'architecture_migration','summary':'七文件零时间迁移：目录销售单源、11个等待任务补信号、施工进度按已确认工期派生、历史快照归档；无补款、无新随机判定。','source':f'GAME ENGINE v{ENGINE_VERSION} migration','authority_files':['state.json','tasks.json','WORLD.md'],'changes':[{'target':'STATE.engine_runtime','action':'activate_mobile_contract'},{'target':'STATE.summary.funds','action':'normalize_decimal_representation'},{'target':'STATE.world_state_overrides','action':'migrate_current_authority_and_archive'},{'target':'TASKS.active_tasks','action':'data_driven_scheduling'},{'target':'TASKS.automation_schema','action':'activate_mobile_contract'},{'target':'WORLD','action':'purify_and_align_machine_rules'}],'migration_evidence':archives,'watchers_added':watchers,'no_game_time_advance':True,'no_historical_finance_backfill':True})
    return {'changed':True,'watchers_added':len(watchers),'catalog_entries':len(catalog),'history_event_appended':True}

def validate_force_generation_packet(payload,base=ROOT):
    ready=ensure_source_ready(base)
    if payload.get('player_force') is True:return {'packet':'FORCE_GENERATION_CHECK_V2','status':'PLAYER_ACTUAL_COUNTS_REQUIRED','save_set_id':ready.get('save_set_id'),'rule':'NPC_BATTLEFIELD_UAV_RATIO_V2','scope':'player forces are never ratio-capped; use actual authoritative UAV counts'}
    robots=payload.get('combat_robots');armed=payload.get('armed_uav',0);recon=payload.get('recon_uav',0)
    if any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in (robots,armed,recon)):raise EngineError('FORCE_COUNTS_REQUIRE_NONNEGATIVE_INTEGERS')
    total=armed+recon;low=robots//60;high=robots//30
    valid=low<=total<=high or (robots<30 and total==0)
    return {'packet':'FORCE_GENERATION_CHECK_V2','status':'PASS' if valid else 'REQUIRES_EXPLICIT_EXCEPTION','save_set_id':ready.get('save_set_id'),'combat_robots':robots,'armed_uav':armed,'recon_uav':recon,'battlefield_uav_total':total,'ordinary_combined_uav_range':[low,high],'rule':'NPC_BATTLEFIELD_UAV_RATIO_V2','scope':'new ordinary NPC force generation only; combined armed+recon battlefield UAVs; no mutation or retroactive reduction','exception_claim':payload.get('exception_source'),'exception_accepted':False}

def _selftest_mobile_seven(record,base):
    def check(name,fn):
        try:record('mobile_'+name,bool(fn()))
        except Exception as exc:record('mobile_'+name,False,str(exc))
    check('decimal_four_places',lambda:_money_add4(.1,.2)==.3 and _money4(1.23455)==1.2346)
    check('batch_array_cli',lambda:_cli_json_input('["gold","grey"]','QUERY_BATCH')==['gold','grey'])
    state={'game_time':'8363-01-01T00:00:00','engine_runtime':{'mobile_contract':{'schema':MOBILE_CONTRACT_SCHEMA}}};now=parse_iso(state['game_time'])
    check('hard_time_cap',lambda:_advance_cap(state,now+dt.timedelta(hours=49))==now+dt.timedelta(hours=24))
    state['game_time']=(now+dt.timedelta(hours=20)).isoformat()
    check('resume_shared_cap',lambda:_advance_cap(state,now+dt.timedelta(hours=49),now.isoformat())==now+dt.timedelta(hours=24))
    active={'version':(10,1),'save_set_id':'A'};uploaded={'version':(10,2),'save_set_id':'B','index':{'parent_save_set_id':'A'}}
    check('new_source_precedes_cache',lambda:_select_root_import(uploaded,active))
    def fork_closed():
        try:_select_root_import({'version':(10,1),'save_set_id':'B'},active)
        except ForkError:return True
        return False
    check('same_version_fork_closed',fork_closed)
    tt={'active_tasks':[{'task_id':'T','runtime_policy':{'monitor':{'resolver':'settlement_rule_v1','requires_ai_review':False,'next_review_at':now.isoformat()}}}]}
    check('equal_now_due',lambda:len(deterministic_task_queue(tt,now,now+dt.timedelta(hours=1)))==1)
    tt['active_tasks'][0]['runtime_policy']['monitor']['next_review_at']=(now-dt.timedelta(seconds=1)).isoformat()
    check('overdue_visible',lambda:_next_ai_monitor_time(tt,now,now+dt.timedelta(hours=1))['kind']=='task_overdue_reconciliation')
    cs={'catalog':{'P':{'status':'on_sale','sales_range':[1,1],'price_gold_per_copy':45}}};cfg={'catalog_source':'STATE.catalog'}
    check('catalog_source',lambda:_catalog_sales_inputs(cfg,cs,now)[0]==['P'])
    cs['catalog']['Q']={'status':'on_sale','sales_range':[2,2],'price_gold_per_copy':45}
    check('catalog_extends_without_task_list',lambda:len(_catalog_sales_inputs(cfg,cs,now)[0])==2)
    cs['catalog']['Q']['sales_range']=[3,2]
    def invalid_range():
        try:_catalog_sales_inputs(cfg,cs,now)
        except EngineError:return True
        return False
    check('invalid_catalog_range_closed',invalid_range)
    def stable_task_action():
        tasks={'active_tasks':[{'task_id':'X','n':1}]}
        _apply_automation_action({'op':'increment','target':'TASKS.task:X.n','value':2},{},tasks)
        return tasks['active_tasks'][0]['n']==3
    check('stable_task_id_automation',stable_task_action)
    def string_compare():
        obj={'x':None};_apply_automation_action({'op':'compare_set','target':'STATE.x','compare':'eq','threshold':None,'value':'ok'},obj,{})
        return obj['x']=='ok'
    check('compare_set_lazy_operator',string_compare)
    def compact_evidence():
        q=query_packet(base,'舰载护盾',detail='compact')
        return bool(q.get('world_rules')) and bool(q.get('save_set_id')) and q.get('status') in ('COMPLETE','TRUNCATED','PARTIAL')
    check('compact_retains_rules_and_identity',compact_evidence)
    check('exact_alias_in_context',lambda:query_packet(base,'当前金币余额',detail='context').get('status')=='COMPLETE')
    for _topic in ('当前任务','下一确定事件','远航者舰队当前状态','远航者舰队当前位置','金川舰队当前状态','暗影舰队当前状态','当前库存','当前资金','舰队核心'):
        check('query_intent_'+hashlib.sha256(_topic.encode('utf-8')).hexdigest()[:8],lambda _t=_topic:(lambda q:q.get('status')=='COMPLETE' and q.get('packet')=='QUERY_INTENT_V3' and not q.get('truncated'))(query_packet(base,_t,detail='compact')))
    check('fleet_location_contract_detail',lambda:(lambda q:isinstance((q.get('value') or {}).get('deployments'),dict) and q.get('status')=='COMPLETE')(query_packet(base,'远航者舰队当前位置',detail='compact')))
    _stq=read_json(base/'state.json') if (base/'state.json').is_file() else {};_ereg=((_stq.get('entity_registry') or {}).get('entities') or {})
    if 'PER-LIA-SOREN' in _ereg:
        check('lia_medical_entity_query',lambda:(lambda q:q.get('status')=='COMPLETE' and q.get('current_state')=='aboard_medical_observation_and_rehabilitation')(_exact_entity_registry_query(base,'莉娅的医疗观察状态') or {}))
        check('obligation_query_contract',lambda:(lambda q:q.get('status')=='COMPLETE' and any(x.get('task_id')=='TSK-MED-LIA-SOREN-OBSERVATION' for x in (q.get('value') or [])))(query_packet(base,'待履行事项',detail='compact')))
    check('nested_truncation_marker',lambda:_query_has_truncated_evidence({'hits':[{'value':{'_truncated':True}}]}))
    check('string_truncation_marker',lambda:_query_has_truncated_evidence('cut...[truncated]'))
    check('list_truncation_marker',lambda:_query_has_truncated_evidence([{'_truncated_items':4}]))
    check('ellipsis_is_not_truncation',lambda:not _query_has_truncated_evidence({'summary':'星舰驶向远方…'}))
    check('mutation_output_budget',lambda:len(json.dumps(_public_mobile_packet({'status':'COMMITTED','save':{'save_set_id':'S','precheck':{'large':'x'*10000},'warnings':[]}},'session')))<1500)

def _public_mobile_packet(result,command):
    if command=='boot' and isinstance(result,dict) and result.get('packet')==COLD_START_PACKET_SCHEMA:
        return result
    if not isinstance(result,dict) or command not in {'session','autoadvance','transact','save'}:return result
    if result.get('status') not in {'COMMITTED','PAUSED_COMMITTED','SAVED','RESUMED_AWAITING_PATCH','SESSION_PATCHED'}:return result
    source=result.get('save') or result.get('save_result') or result
    commit={k:source[k] for k in ('status','version','save_set_id','parent_save_set_id','engine_version','bundle_sha256','snapshot_dir','warnings') if k in source}
    result_keys=('status','session_id','staging','processed_until','pending_turn','semantic_barrier','next_action','report_frame','player_visible_state','recovery_checkpoint','unexecuted_reason')
    out={k:result[k] for k in result_keys if k in result}
    if 'deterministic_events_executed' in result:
        out['deterministic_events_executed']=[{k:r.get(k) for k in ('task_id','job_id','resolver','status','scheduled_time','elapsed_ms','rule_sha256') if k in r} for r in result['deterministic_events_executed'] if isinstance(r,dict)]
    if commit.get('save_set_id'):out['commit']=commit
    if result.get('apply'):
        out['apply']={k:result['apply'].get(k) for k in ('status','changed','history_appended')}
    package=source.get('project_package')
    if package:out['project_package']={k:package.get(k) for k in ('status','save_set_id','directory','zip','files')}
    out['source_sync']=_source_transport_sync_status(ROOT,commit.get('save_set_id') or source.get('save_set_id'))
    out['details']='Use --verbose-result for full validation/diff diagnostics; compact output omits no commit warnings.'
    return out



