# === VOYAGER_DEV_MODULE: background_life ===
# Normal NPC routines can be reviewed without fabricating missing private biographies.
_BG_QUEUE_PREVIOUS=deterministic_event_queue
_BG_RESOLVE_PREVIOUS=_resolve_deterministic_event
_BG_STORY_SOURCE_PREVIOUS=_story_source_report
_BG_STORY_INTEGRITY_PREVIOUS=_story_integrity


def _lw_background_policy(state):
    bg=state.get('engine_runtime',{}).get('living_world_v1',{}).get('background_routine_v1')
    if not bg:return None
    p=bg.get('policy',{})
    if p.get('schema')!='BACKGROUND_ROUTINE_POLICY_V1' or bg.get('policy_sha256')!=_repair_digest(p) or p.get('authority')!='explicit_commander_upgrade_instruction' or p.get('allow_cash_movement') is not False or p.get('allow_location_change') is not False or p.get('allow_new_life_facts') is not False or p.get('interval_seconds')!=86400:raise EngineError('BACKGROUND_ROUTINE_POLICY_INVALID')
    return p


def _lw_background_eligible(state,eid,until=None):
    p=_lw_background_policy(state)
    if not p or p.get('status')!='active' or eid not in p['eligible_existing_entities']:return False
    rt=_lw_runtime(state);profile=rt['profiles'].get(eid,{})
    if eid in rt.get('player_characters',[]) or profile.get('major_review_required') or profile.get('risk_flags'):return False
    if _s3_entity(state,eid).get('status')=='dead':return False
    return True


def _lw_background_due(state):
    p=_lw_background_policy(state)
    if not p or p.get('status')!='active':return None
    rt=_lw_runtime(state);bg=rt['background_routine_v1']
    return parse_iso(bg.get('next_review_at') or rt.get('initial_review_at'))


def _lw_background_check_time(state,new_time):
    due=_lw_background_due(state)
    if due and due<new_time:raise EngineError('BACKGROUND_ROUTINE_DUE_USE_SHARED_SCHEDULER')


def _bg_queue(state,tasks,now,horizon):
    out=_BG_QUEUE_PREVIOUS(state,tasks,now,horizon);due=_lw_background_due(state)
    if due and due<=horizon:out.append({'time':max(now,due).isoformat(),'source':'npc_background_routine','resolver':'npc_background_routine_v1','task_id':None,'job_id':'NPC-BACKGROUND-DAILY'})
    return sorted(out,key=lambda r:(r['time'],r.get('source',''),r.get('task_id') or r.get('job_id') or ''))


def _bg_resolve(stage,state,tasks,event,when):
    if event.get('source')!='npc_background_routine':return _BG_RESOLVE_PREVIOUS(stage,state,tasks,event,when)
    rt=_lw_runtime(state);bg=rt['background_routine_v1'];policy=_lw_background_policy(state);iso=when.isoformat();due=_lw_background_due(state)
    if iso in bg['reviews']:return {'status':'ALREADY_APPLIED','cash_changed':False}
    if state['game_time']!=iso or due!=when:raise EngineError('BACKGROUND_ROUTINE_NOT_DUE')
    rows=[]
    for eid in policy['eligible_existing_entities']:
        if not _lw_background_eligible(state,eid):continue
        p=rt['profiles'][eid]
        rows.append({'entity_id':eid,'profile_revision':p['revision'],'basis_sha256':_repair_digest(p),
            'current_activity':_lw_routine(p,when),'full_profile_still_required_for_portrayal':not _lw_complete(p),
            'new_private_facts_created':False,'movement_created':False,'cash_changed':False})
    receipt={'schema':'BACKGROUND_ROUTINE_REVIEW_V1','scheduled_at':iso,'next_at':_roll_daily(when),'policy_sha256':bg['policy_sha256'],'rows':rows,'new_life_facts_created':False,'major_life_nodes_still_scheduled':True}
    eid='NPC-ROUTINE-'+iso.replace('-','').replace(':','');receipt['event_id']=eid
    bg['reviews'][iso]=receipt;bg['last_reviewed_at']=iso;bg['next_review_at']=receipt['next_at']
    _append_engine_history(stage/'events.jsonl',{'event_id':eid,'game_time':iso,'type':'npc_background_routine_review',
        'summary':'后台复核既有人物日常作息；未补造年龄、家庭、知情或人生事件，未调动资金和位置。',
        'source':'GAME ENGINE bounded background routine policy','authority_files':['state.json'],
        'changes':[{'target':'state:engine_runtime.living_world_v1.background_routine_v1','action':'review_existing_routines_without_new_facts'}],
        'background_routine_review':copy.deepcopy(receipt)})
    return {'status':'COMPLETE','event_id':eid,'scheduled_at':iso,'reviewed_people':len(rows),'cash_changed':False}


def _bg_story_integrity(state,tasks):
    out=_BG_STORY_INTEGRITY_PREVIOUS(state,tasks)
    try:
        p=_lw_background_policy(state)
        if p:
            bg=_lw_runtime(state)['background_routine_v1'];previous=None
            for iso,r in sorted(bg['reviews'].items()):
                if iso!=r['scheduled_at'] or r['next_at']!=_roll_daily(parse_iso(iso)) or r['policy_sha256']!=bg['policy_sha256'] or (previous and iso!=previous):raise EngineError('BACKGROUND_ROUTINE_REVIEW_SEQUENCE')
                if r['new_life_facts_created'] is not False or any(x['cash_changed'] or x['movement_created'] or x['new_private_facts_created'] for x in r['rows']):raise EngineError('BACKGROUND_ROUTINE_SCOPE')
                previous=r['next_at']
            if previous and bg['next_review_at']!=previous:raise EngineError('BACKGROUND_ROUTINE_CURSOR')
    except Exception as ex:out['errors'].append(str(ex))
    out['status']='FAIL' if out['errors'] else 'PASS';return out


def _bg_story_source(base):
    out=_BG_STORY_SOURCE_PREVIOUS(base);state=read_json_view(Path(base)/'state.json');p=_lw_background_policy(state)
    if p:
        grant=history_lookup(base,event_id=p['grant_event_id'])
        if not grant or grant.get('background_policy_sha256')!=_repair_digest(p):out['errors'].append('BACKGROUND_ROUTINE_GRANT_MISSING')
        for r in _lw_runtime(state)['background_routine_v1']['reviews'].values():
            ev=history_lookup(base,event_id=r['event_id'])
            if not ev or ev.get('background_routine_review')!=r:out['errors'].append('BACKGROUND_ROUTINE_RECEIPT_SOURCE')
    out['status']='FAIL' if out['errors'] else 'PASS';return out


deterministic_event_queue=_bg_queue
_resolve_deterministic_event=_bg_resolve
_story_integrity=_bg_story_integrity
_story_source_report=_bg_story_source
