# === VOYAGER_DEV_MODULE: story_services ===
for _story_kind,_story_fields in {'story_action':('action',),'story_transaction':('actions',)}.items():
    DOMAIN_PUBLIC_KINDS.add(_story_kind);DOMAIN_COMMAND_KINDS.add(_story_kind);DOMAIN_REQUIRED_FIELDS[_story_kind]=_story_fields


def _story_scene_integrity(state,tasks):
    return _batch_c_scene_integrity(state,tasks)


def _story_post_validate(state,tasks,before_time):
    result=_batch_c_post(state,tasks,before_time);check=_story_integrity(state,tasks)
    if check['status']=='FAIL':raise EngineError('STORY_INTEGRITY:'+str(check['errors']))
    result['checks'].append('scene_focus_knowledge_narrative_contract');return result


def _story_source_report(base):
    state=read_json_view(Path(base)/'state.json');tasks=read_json_view(Path(base)/'tasks.json');out=_story_integrity(state,tasks)
    if out['status']=='LEGACY':return out
    # All new knowledge/causal/experience evidence is committed in ordinary history.
    _,events,_=read_history_view(Path(base)/'events.jsonl');ids={e['event_id'] for e in events};rt=_story_runtime(state);refs=[]
    for e in rt['entities'].values():refs.append(e['source_event_id'])
    for d in rt['decisions'].values():refs.append(d['source_event_id']);refs+=[d['cause_event_id']] if d.get('cause_event_id') else []
    for e in rt['evidence_links']:refs += [e['evidence_event_id'],e['record_event_id']]
    for f in rt['facts'].values():refs+=f['source_event_ids']
    for l in rt['learning_events']:refs+=[l['basis_event_id'],l['record_event_id']]
    for c in rt['consequences'].values():refs+=[c['cause_event_id'],c['created_by']];refs+=[c['resolution_event_id']] if c.get('resolution_event_id') else []
    for r in rt['proposals'].values():refs.append(r['source_event_id']);refs += [rev['source_event_id'] for rev in r['revisions']]
    if any(ref not in ids for ref in refs):out['errors'].append('STORY_EVENT_REFERENCE_MISSING')
    out['status']='FAIL' if out['errors'] else 'PASS';return out


def _story_run_checks(base,full=False,expected_version=None,require_manifest=True,parent_snapshot=None,validation_cache=None):
    out=_batch_c_run_checks(base,full,expected_version,require_manifest,parent_snapshot,validation_cache)
    try:
        check=_story_source_report(base);out['story']=check;out['errors']+=['STORY:'+e for e in check['errors']]
    except Exception as ex:out['errors'].append('STORY:'+str(ex))
    out['errors']=sorted(set(out['errors']));out['error_count']=len(out['errors']);out['status']='FAIL' if out['errors'] else 'PASS';return out


def _story_visible_query(base,topic,history_limit=5,detail='compact',audience='player',observer_id=None,gm_context=None):
    with SnapshotContext(base):
        ensure_source_ready(base)
        if audience=='player':topic=_experience_alias_topic(base,str(topic))
        if _normalize_search_text(str(topic)) in ('五项余额','五项账本','全部账户余额','潜伏灰币','潜伏本币','余火现金'):
            viewer=_scene_viewer(audience,observer_id,gm_context)
            if viewer.startswith('observer:'):raise EngineError('VISIBILITY_OBSERVER_ACCOUNT_DENIED')
            state=read_json_view(Path(base)/'state.json');balances=_five_account_balances(state);key={'潜伏灰币':'covert_grey','潜伏本币':'covert_copper','余火现金':'shop_copper'}.get(_normalize_search_text(str(topic)))
            return {'packet':'EXACT_ACCOUNT_PROJECTION_V1','status':'COMPLETE','save_set_id':read_json_view(Path(base)/'manifest.json')['save_set_id'],'game_time':state['game_time'],'value':balances[key] if key else balances,'source_ref':'state:engine_runtime.account_registry_v1'}
        if audience=='player' and _normalize_search_text(str(topic)) in ('当前场景','开放事件','当前开放事件'):
            state=read_json_view(Path(base)/'state.json');cur=_story_current_summary(state)
            if not cur['scene_id']:return {'packet':'SCENE_QUERY_V2','status':cur['status'],'save_set_id':read_json_view(Path(base)/'manifest.json')['save_set_id'],'value':cur}
        result=_batch_c_visible_query(base,topic,history_limit,detail,audience,observer_id,gm_context)
        return result if audience=='gm' else player_output_policy(result)


def _story_cold_start_expanded(base=ROOT):
    packet=_batch_c_cold_start(base);state=read_json_view(Path(base)/'state.json');packet['scene_focus']=_story_current_summary(state);packet['narrative_context_query']='narrativecontext';packet['director']='bounded proposal layer; explicit authorized commits only'
    coverage=scheduler_coverage_packet(base)
    packet['execution_coverage']={'status':coverage['status'],'next_blocker':coverage['next_blocker'],'query':'schedulercoverage'}
    packet['current_guide']=read_json_view(Path(base)/'manifest.json').get('current_guide')
    return player_output_policy(packet)


def _story_cold_start(base=ROOT):
    full=_story_cold_start_expanded(base)
    ready=full.get('readiness') or {}
    if ready.get('status')=='BLOCKED':return full
    core=copy.deepcopy(full['fleet_core'])
    for fid,row in list(core.items()):
        if isinstance(row,dict) and 'ships' in row:core[fid]={k:row[k] for k in ('ships','personnel','complete') if k in row}
    coverage=full['execution_coverage'];block=coverage.get('next_blocker')
    brief={k:full[k] for k in ('packet','engine_version','save_set_id','game_time','player_location','next_deterministic_event','next_semantic_barrier','active_summary','pending_decisions','pending_turn','current_scene') if k in full}
    brief['fleet_core']=core
    brief['presentation_version']='compact_v1'
    brief['voyage_day']=read_json_view(Path(base)/'state.json').get('voyage_day')
    brief['readiness']={'status':ready.get('status'),'errors':ready.get('errors',[]),'historical_gaps':'acknowledged_unsimulated_no_replay' if (ready.get('layers',{}).get('runtime_clock',{}).get('acknowledged_gaps')) else None,'details':'readiness'}
    brief['execution_coverage']={'status':coverage['status'],'next_blocker':{k:block.get(k) for k in ('time','task_id','kind','reason')} if block else None,'details':'businessquery / schedulercoverage'}
    brief['current_guide']=(full.get('current_guide') or {}).get('path')
    brief['resume_cursor']={k:full.get('resume_cursor',{}).get(k) for k in ('status','task_id','event_id','pending_gate')}
    brief['command_contract']={'invoke':'invoke','catalog':'commandcatalog','authorization':'verified standing grant or trusted host'}
    brief['next_layers']=['startupfull','startup --layer navigation','startup --layer focus']
    brief['context_budget_bytes']=3500;brief['budget_exceeded']=False;brief['context_bytes']=0
    # Count the final compact JSON including its own accounting fields.
    for _ in range(5):
        n=len(json.dumps(brief,ensure_ascii=False,separators=(',',':')).encode())
        if brief['context_bytes']==n:break
        brief['context_bytes']=n
    brief['budget_exceeded']=brief['context_bytes']>3500
    brief['context_bytes']=len(json.dumps(brief,ensure_ascii=False,separators=(',',':')).encode())
    return player_output_policy(brief)


def _story_main(argv=None):
    import io,contextlib
    args=list(sys.argv[1:] if argv is None else argv);cmd=args[0] if args else ''
    own={'knowledgequery','narrativecontext','narrativevalidate','narrativereport','experience','storyprojection','sceneindex','scenequery','assetquery','commandcatalog','pricequery','businessquery','schedulercoverage','startupfull'}
    base=Path(args[args.index('--base')+1]) if '--base' in args else ROOT
    if cmd not in own:return _batch_c_main(args)
    try:
        parser=argparse.ArgumentParser();parser.add_argument('--base',default=str(base));parser.add_argument('--audience',choices=['player','observer','gm'],default='player');parser.add_argument('--observer-id');parser.add_argument('--gm-context')
        if cmd in ('knowledgequery','narrativecontext'):parser.add_argument('--scene-id');parser.add_argument('--viewer',default='player')
        if cmd=='narrativecontext':parser.add_argument('--budget',type=int,default=12000)
        if cmd=='narrativevalidate':parser.add_argument('--input',required=True)
        if cmd=='pricequery':parser.add_argument('--input',default='{}')
        if cmd=='narrativereport':parser.add_argument('--id',required=True)
        if cmd=='scenequery':parser.add_argument('--id',required=True)
        if cmd=='sceneindex':parser.add_argument('--offset',type=int,default=0);parser.add_argument('--limit',type=int,default=20)
        if cmd=='businessquery':parser.add_argument('--task-id',default='TSK-YUHUO-OPERATIONS')
        if cmd=='assetquery':parser.add_argument('--id');parser.add_argument('--legacy-path')
        ns=parser.parse_args(args[1:]);viewer=_scene_viewer(ns.audience,ns.observer_id,ns.gm_context)
        with SnapshotContext(base):
            ensure_source_ready(base)
            if cmd in ('knowledgequery','narrativecontext') and ns.viewer!='player' and viewer!='gm' and ns.viewer!=viewer:raise EngineError('KNOWLEDGE_REQUESTED_VIEWER_NOT_AUTHORIZED')
            if cmd=='assetquery' and viewer.startswith('observer:'):raise EngineError('VISIBILITY_OBSERVER_ASSET_DENIED')
            if cmd in ('businessquery','schedulercoverage','startupfull') and viewer.startswith('observer:'):raise EngineError('VISIBILITY_OBSERVER_BUSINESS_DENIED')
            if cmd=='startupfull':out=_story_cold_start_expanded(base)
            elif cmd=='businessquery':out=business_query_packet(base,ns.task_id)
            elif cmd=='schedulercoverage':out=scheduler_coverage_packet(base)
            elif cmd=='knowledgequery':
                if not ns.scene_id:raise EngineError('KNOWLEDGE_SCENE_REQUIRED')
                out=knowledge_packet(base,ns.scene_id,ns.viewer)
            elif cmd=='narrativecontext':out=narrative_context_packet(base,ns.scene_id,ns.viewer,ns.budget)
            elif cmd=='narrativevalidate':out=validate_narrative_proposal(base,_cli_json_input(ns.input,'NARRATIVE_PROPOSAL'))
            elif cmd=='narrativereport':out=narrative_report_packet(base,ns.id)
            elif cmd=='experience':out=experience_packet(base)
            elif cmd=='storyprojection':out=story_projection_packet(base)
            elif cmd=='sceneindex':out=scene_index_packet(base,ns.offset,ns.limit,ns.audience,ns.observer_id,ns.gm_context)
            elif cmd=='scenequery':out=scene_query_packet(base,ns.id,ns.audience,ns.observer_id,ns.gm_context)
            elif cmd=='assetquery':out=_batch_c_asset_query(base,ns.id,ns.legacy_path) if viewer=='gm' else asset_query_packet(base,ns.id,ns.legacy_path)
            elif cmd=='commandcatalog':out=domain_command_catalog(base)
            elif cmd=='pricequery':out=price_query_packet(base,_cli_json_input(ns.input,'PRICE_QUERY'))
        print(json.dumps(out,ensure_ascii=False));return 0
    except Exception as ex:print(json.dumps({'status':'FAIL','error':str(ex)},ensure_ascii=False));return 1

_apply_domain_command=_story_actions_apply
_domain_command_targets=_story_targets
_domain_authorization_cost=_story_cost
_entity_registry_expected=_story_entity_expected
_phase2_domain_post_mutation_validate=_story_post_validate
_scene_integrity_report=_story_scene_integrity
_scene_current_summary=_story_current_summary
scene_query_packet=_story_scene_query
scene_index_packet=_story_scene_index
visible_query_packet=_story_visible_query
asset_query_packet=_story_asset_query
price_query_packet=_story_price_query
domain_command_catalog=_story_catalog
cold_start_packet=_story_cold_start
run_checks=_story_run_checks
main=_story_main


def story_projection_packet(base=ROOT):
    with SnapshotContext(base):
        ready=ensure_source_ready(base);state=read_json_view(Path(base)/'state.json');focus=_story_current_summary(state)
        return player_output_policy({'packet':'PLAYER_STORY_PROJECTION_V1','save_set_id':ready['save_set_id'],'game_time':state['game_time'],'version':ENGINE_VERSION,'focus':focus,'scene':scene_query_packet(base,focus['scene_id']) if focus['scene_id'] else None,'narrative_context_query':'narrativecontext','source':'verified player projection; static old UI is historical'})


class StorySceneService:
    apply=staticmethod(_story_actions_apply)
    query=staticmethod(_story_scene_query)
    index=staticmethod(_story_scene_index)
    player_projection=staticmethod(story_projection_packet)

class KnowledgeView:
    read=staticmethod(knowledge_packet)
    player_filter=staticmethod(player_output_policy)

class NarrativeDirector:
    context=staticmethod(narrative_context_packet)
    validate=staticmethod(validate_narrative_proposal)
    report=staticmethod(narrative_report_packet)

class ExperienceService:
    view=staticmethod(experience_packet)
    strategy=staticmethod(_experience_strategy)
