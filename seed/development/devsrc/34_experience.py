# === VOYAGER_DEV_MODULE: experience ===
EXPERIENCE_POLICY_VERSION='derived_context_strategy_v1'
EXPERIENCE_TYPES={'intent_alias','source_success','failure_category','pattern_feedback','explicit_preference'}
EXPERIENCE_PUBLIC_TOPICS={'当前金币余额','当前任务','当前场景','暗影舰队位置'}


def _experience_action(stage,state,action):
    ctx=_story_event_context();typ=action['type'];rt=experience_packet(stage);existing={r['entry_id']:r for r in rt.get('records',[])}
    pending=ctx.setdefault('experience_pending',[]);revoked=set(rt.get('revoked_ids',[]))
    for r in pending:
        if r.get('op')=='record':existing[r['entry']['entry_id']]=r['entry']
        elif r.get('op')=='revoke':existing.pop(r['entry_id'],None);revoked.add(r['entry_id'])
    if typ=='experience_revoke':
        eid=_story_id(action['entry_id'])
        if eid not in existing:raise EngineError('EXPERIENCE_ENTRY_NOT_FOUND')
        obj={'op':'revoke','entry_id':eid,'reason':_story_text(action['reason'],300)}
    else:
        entry=copy.deepcopy(action['entry']);required={'entry_id','object_type','value','instruction_ref'}
        if set(entry)!=required or entry['object_type'] not in EXPERIENCE_TYPES:raise EngineError('EXPERIENCE_WHITELIST')
        eid=_story_id(entry['entry_id'])
        if eid in existing or eid in revoked:raise EngineError('EXPERIENCE_ENTRY_EXISTS')
        host=_host_intent_scope.get()
        if not host or ctx['outer'].get('authorization')!='host_intent' or host.get('evidence_ref')!=entry['instruction_ref']:raise EngineError('EXPERIENCE_EXPLICIT_HOST_INSTRUCTION_REQUIRED')
        value=entry['value'];kind=entry['object_type']
        if kind=='intent_alias':
            if not isinstance(value,dict) or set(value)!={'alias','canonical_topic'} or value['canonical_topic'] not in EXPERIENCE_PUBLIC_TOPICS:raise EngineError('EXPERIENCE_ALIAS_TARGET_NOT_PUBLIC')
            _story_text(value['alias'],80)
            if value['alias'] in EXPERIENCE_PUBLIC_TOPICS or _exact_alias_key(value['alias']) or _query_intent_key(value['alias'])[0] is not None:raise EngineError('EXPERIENCE_BUILTIN_QUERY_PROTECTED')
        elif kind=='explicit_preference':
            if not isinstance(value,dict) or set(value)!={'genre','pace'} or value['pace'] not in ('slow','balanced','fast') or value['genre'] not in ('rescue','ordinary_life','discovery','investigation','social','adventure'):raise EngineError('EXPERIENCE_PREFERENCE_SCHEMA')
        elif kind=='source_success':
            if not isinstance(value,dict) or set(value)!={'topic','source_ref'} or value['topic'] not in EXPERIENCE_PUBLIC_TOPICS or value['source_ref'] not in ('state:summary.funds','tasks:active_tasks','state:shadow_fleet.current_location','state:engine_runtime.scene_registry_v1'):raise EngineError('EXPERIENCE_SOURCE_WHITELIST')
            routes={'当前金币余额':'state:summary.funds','当前任务':'tasks:active_tasks','当前场景':'state:engine_runtime.scene_registry_v1','暗影舰队位置':'state:shadow_fleet.current_location'}
            if value['source_ref']!=routes[value['topic']]:raise EngineError('EXPERIENCE_SOURCE_TOPIC_MISMATCH')
        elif kind=='failure_category':
            if value not in ('ambiguous_intent','missing_source','authorization_missing','stale_base','repeated_scene'):raise EngineError('EXPERIENCE_FAILURE_CATEGORY')
        elif kind=='pattern_feedback':
            if not isinstance(value,dict) or set(value)!={'tag','rating'} or value['rating'] not in ('repetitive','useful') or not re.fullmatch(r'[A-Za-z0-9_:-]{1,80}',value['tag']):raise EngineError('EXPERIENCE_PATTERN_SCHEMA')
        obj={'op':'record','entry':{**entry,'recorded_at':state['game_time'],'source_event_id':ctx['event_id'],'origin':'explicit_user_instruction_not_inferred_from_npc'}}
    pending.append(obj)
    return {'action':typ,'experience_object':obj,'changes':[{'target':'events:experience_v1','action':'append_rebuildable_experience_audit'}]}


def experience_packet(base=ROOT):
    base=Path(base);ensure_source_ready(base);binding={'schema':'EXPERIENCE_DERIVED_V1','history_sha256':sha256_file(base/'events.jsonl'),'engine':ENGINE_VERSION,'policy':EXPERIENCE_POLICY_VERSION};cached=_derived_read(base,'experience_v1.json',binding)
    if cached is None:
        _,events,_=read_history_view(base/'events.jsonl');records={};revoked=set()
        for ev in events:
            if ev.get('subtype')!='domain_command_commit' or ev.get('authorization',{}).get('status')!='verified':continue
            for result in ev.get('domain_effect',{}).get('results',[]):
                obj=result.get('experience_object')
                if not obj:continue
                if obj['op']=='record':records[obj['entry']['entry_id']]=obj['entry']
                elif obj['op']=='revoke':revoked.add(obj['entry_id'])
        cached={'records':[r for eid,r in records.items() if eid not in revoked],'revoked_ids':sorted(revoked)};_derived_write(base,'experience_v1.json',binding,cached)
    enabled=os.environ.get('VOYAGER_EXPERIENCE','1')!='0'
    return {'packet':'EXPERIENCE_VIEW_V1','status':'ENABLED' if enabled else 'DISABLED','policy_version':EXPERIENCE_POLICY_VERSION,'authority':'verified history receipts; runtime file is deletable derived statistics','records':copy.deepcopy(cached['records']) if enabled else [],'revoked_ids':cached['revoked_ids'],'mechanical_effects':False,'rules_self_modification':False}


def _experience_strategy(view,family,recent_tags=None):
    records=view['records'];preferences=[r['value'] for r in records if r['object_type']=='explicit_preference'];avoid=[r['value']['tag'] for r in records if r['object_type']=='pattern_feedback' and r['value']['rating']=='repetitive']
    recent_tags=list(recent_tags or []) if view['status']=='ENABLED' else []
    genres=['rescue','ordinary_life','discovery','social','investigation','adventure'];ranked=sorted(genres,key=lambda g:(g in avoid,recent_tags.count(g),genres.index(g)))
    if preferences:
        genre=preferences[-1]['genre'];ranked=[genre]+[g for g in ranked if g!=genre]
    return {'version':EXPERIENCE_POLICY_VERSION,'enabled':view['status']=='ENABLED','preferred_pace':preferences[-1]['pace'] if preferences else 'balanced','suggested_families':ranked,'avoid_repeating_tags':avoid,'temporary_recent_pattern_counts':{g:recent_tags.count(g) for g in genres},'mechanical_policy':'unchanged; no money/combat/authorization/hazard parameter influenced'}


def _experience_alias_topic(base,topic):
    if os.environ.get('VOYAGER_EXPERIENCE','1')=='0' or topic in EXPERIENCE_PUBLIC_TOPICS or _exact_alias_key(topic) or _query_intent_key(topic)[0] is not None:return topic
    rows=experience_packet(base)['records']
    for row in reversed(rows):
        if row['object_type']=='intent_alias' and _normalize_search_text(row['value']['alias'])==_normalize_search_text(topic):return row['value']['canonical_topic']
    return topic
