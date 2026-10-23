# === VOYAGER_DEV_MODULE: extension_interface ===
_s4_previous_main=main
_s4_previous_catalog=domain_command_catalog
_s4_previous_rules=_s3_rules
_S4_RULE_ENTRYPOINTS={'_money_units_currency':_money_units_currency,'_phase2_domain_authorization':_phase2_domain_authorization,'_risk_window_report':_risk_window_report,'calculate_price_quote':calculate_price_quote,'_domain_complete_task':_domain_complete_task,'_validate_world_process_rule':_validate_world_process_rule,'_knowledge_action':_knowledge_action,'_s3_receipt_effect':_s3_receipt_effect,'_settlement_inventory_delivery':_settlement_inventory_delivery}


def _s4_content_rules(base,state,tags,scene_type,actor,now,viewer,scene_id=None):
    rows=[];catalog=read_json_view(Path(base)/'catalog.json')
    for pid,pack in catalog.get('content_packages_v1',{}).get('packages',{}).items():
        binding=_scene_registry(state)['records'].get(scene_id,{}).get('content_binding',{})
        if binding.get('package_id')==pid:
            registry=_s4_content_registry(catalog);pack=registry['packages'][pid]['versions'][binding['version']]['package']
        if pack.get('schema')!=CONTENT_V2_SCHEMA or viewer!='gm' and pack['visibility']=='gm':continue
        for row in pack['definitions']:
            if row['kind']!='semantic_rule' or row['status']!='active' or viewer!='gm' and row['visibility']=='gm':continue
            data=row['data'];lo=parse_iso(data['valid_from']);hi=parse_iso(data['valid_until'])
            if lo and now<lo or hi and now>hi or '*' not in data['subjects'] and actor not in data['subjects'] or '*' not in data['scene_types'] and scene_type not in data['scene_types'] or not set(row['tags'])&set(tags):continue
            rows.append({'rule_id':row['id'],'version':pack['version'],'hard':False,'priority':row['priority'],'source_ref':{'package_id':pid,'version':pack['version'],'definition_id':row['id'],'package_sha256':pack['content_sha256']},'content':data['text'],'constraints':[],'authorization_requirement':'existing engine authorization unchanged','implementation':'semantic_only','instructions_are_data':True})
    return rows


def _s4_rules(state,rules,intent_tags,scene_type,actor,now,viewer='player',base=None,scene_id=None):
    selected=_s4_previous_rules(state,rules,intent_tags,scene_type,actor,now,viewer)
    # Snapshot/transaction ROOT is explicit via active context, never user package path.
    context=_snapshot_scope.get() or _stage2_tx_scope.get()
    base=Path(base) if base is not None else context.base if context is not None else ROOT
    optional=_s4_content_rules(base,state,intent_tags,scene_type,actor,now,viewer,scene_id)
    return selected+sorted(optional,key=lambda row:(-row['priority'],row['rule_id']))


def _s4_scene_context(base,state,sid,viewer):
    binding=_scene_registry(state)['records'][sid].get('content_binding')
    if not binding:return []
    ref={k:binding[k] for k in ('package_id','version','definition_id','package_sha256')}
    try:return [_s4_content_resolve(base,ref,viewer)]
    except EngineError:return []  # Hidden definition is never an implicit disclosure.


def rule_coverage(base=ROOT):
    with SnapshotContext(base):
        ensure_source_ready(base);rules=read_json(Path(base)/'rules.json');index=_s3_runtime(read_json(Path(base)/'state.json'))['rule_index'];rows=[]
        bindings={
          'RULE-FIXED-POINT-FINANCE-01':('hard_constraint','_money_units_currency','fixed integer currency and quantum checks','stage2_business:accounts_scale_transfer_budget_and_quantum'),
          'RULE-DOMAIN-COMMAND-01':('hard_constraint','_phase2_domain_authorization','DOMAIN_COMMAND payload; real actor/targets/budget/time','stage3_turns:fabricated_results_stale_proposals_and_real_authorization'),
          'RULE-LONG-HORIZON-RISK-01':('checked_semistructured','_risk_window_report','existing risk clock schema; gaps never replayed','stage2_business:scheduler_business_and_unknown_resolver_barriers'),
          'RULE-RESEARCH-DATA-UNIFORM-PRICE-45-01':('executable_parameter','calculate_price_quote','PRICE quote registry; no prose price','stage2_business:real_covert_grey_price_settlement_and_delivery'),
          'RULE-ECONOMY-01':('checked_semistructured','calculate_price_quote','registered price subset only','stage3_turns:priced_transaction_inventory_and_story_same_commit'),
          'RULE-TASK-LIFECYCLE-COMMANDER-01':('checked_semistructured','_domain_complete_task','typed task and real authorization','stage2_business:scheduler_business_and_unknown_resolver_barriers'),
          'RULE-ENGINE-AUTOMATION-01':('checked_semistructured','_validate_world_process_rule','typed resolver subset only','native_selftest'),
          'RULE-INTEL-KNOWLEDGE-01':('checked_semistructured','_knowledge_action','typed facts and explicit disclosure','stage3_turns:multi_role_context_cache_report_and_error_isolation'),
          'RULE-EVIDENCE-01':('checked_semistructured','_s3_receipt_effect','committed visible matching evidence only','stage3_turns:atomic_trade_learning_receipt_retry_and_rewrite'),
          'RULE-SUPPLY-INVENTORY-01':('checked_semistructured','_settlement_inventory_delivery','known supply SKU delivery subset','stage2_business:real_covert_grey_price_settlement_and_delivery')}
        for rid,row in rules['rule_registry']['rules'].items():
            known=bindings.get(rid);kind,entry,schema,test=known if known else ('semantic_only',None,None,None)
            if entry and not callable(_S4_RULE_ENTRYPOINTS.get(entry)):raise EngineError('RULE_COVERAGE_ENTRY_MISSING')
            rows.append({'rule_id':rid,'rule_version':row['version'],'type':kind,'entry':entry,'input_contract':schema,'test':test,'source_ref':row['source_ref'],'registry_implementation_status':row.get('implementation_status'),'context_entry':'prepare_turn/_s3_rules' if rid in index else 'explicit source retrieval; no automatic context coverage claimed','unsupported':'remaining prose/conditions require AI or explicit adjudication; classification does not promote original semantic text to executable'})
        catalog=read_json(Path(base)/'catalog.json')
        for pid,p in catalog.get('content_packages_v1',{}).get('packages',{}).items():
            if p.get('schema')!=CONTENT_V2_SCHEMA:continue
            for d in p['definitions']:
                if d['kind']=='semantic_rule':rows.append({'rule_id':d['id'],'rule_version':p['version'],'type':'semantic_only','entry':'_s4_content_rules','input_contract':'VOYAGER_CONTENT_PACKAGE_V2 semantic_rule','test':'stage4:content_rule_context','source_ref':{'package_id':pid,'version':p['version'],'package_sha256':p['content_sha256']},'unsupported':'no mechanical execution'})
        return {'packet':'RULE_COVERAGE_V1','base_identity':_s3_identity(base),'rows':rows,'counts':dict(collections.Counter(r['type'] for r in rows)),'classification_is_not_full_automation':True}


def _s4_catalog(base=ROOT):
    out=_s4_previous_catalog(base);out['queries']+=['contentpreview','contentresolve','memorylayers','memorysearch','memoryevidence','experiencev2','rulecoverage','servicecontracts'];out['extension_kinds']=sorted(ExtensionServices.handlers);return out


def service_contracts():
    return {'schema':'EXTENSION_SERVICES_V1','engine_version':ENGINE_VERSION,'ordered_dependencies':ExtensionServices.check_dependencies(ExtensionServices.dependencies),'dependencies':copy.deepcopy(ExtensionServices.dependencies),'contracts':ExtensionServices.contracts(),'registered_kinds':sorted(ExtensionServices.handlers),'ownership':'read results copied; transaction work objects mutable only inside native stage','authorization':'extension host-only operations still require actual host scope plus original actor/targets/budget checks','units':'gold/grey scale10000; grey quantum100; copper scale1; budgets never inferred from prose','idempotency':'native permanent command ID plus full payload digest; stale preview refuses new execution','errors':['CONTENT_UPGRADE_STALE_OR_TAMPERED_PLAN','CONTENT_USED_DEFINITION_CANNOT_DELETE','CONTENT_DEPENDENCY_CONFLICT','CONTENT_BREAKING_REQUIRES_EXPLICIT_RETAIN_MIGRATION','MEMORY_INDEX_SOURCE_MISMATCH','EXTENSION_REAL_HOST_REQUIRED'],'data_only_types':sorted(CONTENT_V2_KINDS),'mechanical_type_limits':'scene_family is consumed by content_scene_open; semantic_rule by context; equipment/location/organization are versioned definition lookup only; no inventory acquisition or canonical location discovery; RNG package requires explicit engine migration'}


def _s4_extension_audit(base):
    errors=[]
    try:
        _,events,_=read_history_view(Path(base)/'events.jsonl')
        for event in events:
            obj=(event.get('domain_effect') or {}).get('experience_v2_object')
            if not obj:continue
            command=event['domain_effect'].get('command_payload',{})
            if event.get('authorization',{}).get('authority')!='host_intent' or command.get('kind') not in ('experience_probe','experience_control') or _domain_payload_digest(command)!=event.get('payload_sha256') or obj['viewer']!=command['viewer'] or obj['scope']!=command['scope']:raise EngineError('EXPERIENCE_SOURCE_CONTRACT')
            if obj['op']=='observation':
                if command['kind']!='experience_probe' or obj['observation']['input_sha256']!=_repair_digest(command['probe']['input']) or obj['observation']['type']!=command['probe']['kind'] or obj['observation']['seconds']<0 or obj['observation']['body_bytes']<0:raise EngineError('EXPERIENCE_OBSERVATION_CONTRACT')
            elif command['kind']!='experience_control' or obj['op']!=command['control']['op'] or obj['instruction_ref']!=event['authorization'].get('evidence_ref'):raise EngineError('EXPERIENCE_PREFERENCE_SOURCE')
    except Exception as ex:errors.append(str(ex).split(':')[0])
    return errors


def _s4_main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv);cmd=args[0] if args else '';own={'contentpreview','contentresolve','memorylayers','memorysearch','memoryevidence','experiencev2','rulecoverage','servicecontracts'}
    if cmd not in own:return _s4_previous_main(args)
    try:
        p=argparse.ArgumentParser();p.add_argument('--base',default=str(ROOT));p.add_argument('--input');p.add_argument('--viewer',default='player');p.add_argument('--query',default='');p.add_argument('--entity-id');p.add_argument('--scene-id');p.add_argument('--layer',default='all');p.add_argument('--since');p.add_argument('--until');p.add_argument('--offset',type=int,default=0);p.add_argument('--limit',type=int,default=20);p.add_argument('--ref');ns=p.parse_args(args[1:]);base=Path(ns.base);_s3_viewer(ns.viewer)
        with SnapshotContext(base):
            ensure_source_ready(base)
            if cmd=='contentpreview':
                if ns.viewer!='gm':raise EngineError('CONTENT_PREVIEW_GM_REQUIRED')
                out=content_upgrade_preview(base,_cli_json_input(ns.input,'CONTENT_PACKAGE'))
            elif cmd=='contentresolve':out=content_resolve(base,_cli_json_input(ns.input,'DEFINITION_REF'),ns.viewer)
            elif cmd=='memorylayers':out=memory_layers(base,ns.viewer)
            elif cmd=='memorysearch':out=memory_search(base,ns.viewer,ns.query,ns.entity_id,ns.scene_id,ns.layer,ns.since,ns.until,ns.offset,ns.limit)
            elif cmd=='memoryevidence':out=memory_evidence(base,ns.ref,ns.viewer)
            elif cmd=='experiencev2':out=experience_v2(base,ns.viewer)
            elif cmd=='rulecoverage':
                if ns.viewer!='gm':raise EngineError('RULE_COVERAGE_GM_REQUIRED')
                out=rule_coverage(base)
            else:out=service_contracts()
        print(json.dumps(out,ensure_ascii=False,separators=(',',':'),default=str));return 0
    except Exception as ex:print(json.dumps({'status':'FAIL','code':str(ex).split(':')[0]},ensure_ascii=False));return 1


_s3_rules=_s4_rules
domain_command_catalog=_s4_catalog
main=_s4_main

