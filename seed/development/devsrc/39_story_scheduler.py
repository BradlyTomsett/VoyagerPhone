# === VOYAGER_DEV_MODULE: story_scheduler ===
_s3_previous_queue=deterministic_event_queue
_s3_previous_resolve=_resolve_deterministic_event
_s3_previous_ai=_next_ai_monitor_time
_s3_previous_catalog=domain_command_catalog
_s3_previous_precedes=_deterministic_event_precedes_barrier
_s3_previous_domain=domain_command_packet
TASK_AI_BARRIER_KINDS.update({'story_consequence_ai','story_consequence_authorization'})


def _s3_task_active(tasks,tid):
    return tid is None or any(t.get('task_id')==tid and t.get('status') not in ('cancelled','completed','closed') for t in tasks.get('active_tasks',[]))


def _s3_condition(state,condition):
    if condition=={'kind':'always'}:return True
    if not isinstance(condition,dict) or condition.get('kind')!='fact_known' or set(condition)!={'kind','scene_id','fact_id','viewer_id'}:raise EngineError('STORY_CONDITION_UNSUPPORTED')
    return condition['fact_id'] in _knowledge_known(state,condition['scene_id'],condition['viewer_id'])


def _s3_consequence_status(state,c):
    if c['status'] not in ('pending','waiting_ai','waiting_condition'):return c['status']
    now=parse_iso(state['game_time']);lo=parse_iso(c['not_before']);hi=parse_iso(c['not_after'])
    if now>hi:return 'EXPIRED_AWAITING_RECORD'
    if now<lo:return 'SCHEDULED'
    if not _s3_condition(state,c.get('condition',{'kind':'always'})):return 'WAITING_CONDITION'
    return 'WAITING_AI' if c.get('mode','needs_ai')=='needs_ai' else 'MECHANICAL_DUE'


def _s3_consequence_action(stage,state,tasks,action,proposal):
    typ=action['type'];story=_story_runtime(state);ctx=_story_event_context();now=state['game_time'];sid=action['scene_id'];cid=_story_id(action['consequence_id'])
    _story_record(state,sid,True)
    if typ=='consequence_schedule':
        required={'type','scene_id','consequence_id','subject_id','effect_type','cause_event_id','not_before','not_after','visible_to','text','mode','condition','task_id','effect'}
        _s3_fields(action,required)
        if cid in story['consequences']:raise EngineError('STORY_CONSEQUENCE_ID_EXISTS')
        _s3_entity(state,action['subject_id'],True)
        lo=parse_iso(action['not_before']);hi=parse_iso(action['not_after']);at=parse_iso(now)
        if lo is None or hi is None or not at<=lo<=hi:raise EngineError('STORY_CONSEQUENCE_WINDOW_INVALID')
        if action['mode'] not in ('needs_ai','mechanical') or action['effect_type'] not in ('social_response','pending_reply','scene_hook'):raise EngineError('STORY_CONSEQUENCE_MODE')
        _story_text(action['text'],2000);_s3_condition(state,action['condition'])
        knowledge_actor=(proposal or {}).get('actor_id') or (ctx['outer'].get('actor_id') if ctx['outer'].get('actor_id') in _s3_runtime(state)['npcs'] else None)
        if knowledge_actor and action['condition'].get('kind')=='fact_known' and (action['condition']['viewer_id']!='npc:'+knowledge_actor or action['condition']['scene_id']!=sid):raise EngineError('STORY_CONDITION_OTHER_ROLE_KNOWLEDGE_DENIED')
        if not _s3_task_active(tasks,action['task_id']):raise EngineError('STORY_CONSEQUENCE_TASK_NOT_ACTIVE')
        if not isinstance(action['visible_to'],list) or not action['visible_to']:raise EngineError('STORY_CONSEQUENCE_VISIBILITY')
        for viewer in action['visible_to']:_knowledge_viewer(viewer,True)
        cause=ctx['event_id'] if action['cause_event_id']=='$current_transaction' else action['cause_event_id']
        if cause!=ctx['event_id'] and not history_lookup(stage,event_id=cause):raise EngineError('STORY_CONSEQUENCE_CAUSE_MISSING')
        effect=action['effect'];_s3_fields(effect,{'kind'},{'entity_id','goal_id','fact_id','viewer_id'})
        if action['mode']=='needs_ai':
            if effect!={'kind':'await_ai'}:raise EngineError('STORY_AI_NODE_CANNOT_PRECOMMIT_UNSUPPORTED_EFFECT')
        else:
            env=_host_intent_scope.get();grant=state.get('standing_authorizations',{}).get(ctx['authorization_ref'],{}).get('machine_grant',{})
            until=parse_iso((env or {}).get('valid_until') or grant.get('valid_until'))
            if until is None or hi>until:raise EngineError('STORY_SCHEDULE_FUTURE_AUTHORIZATION_REQUIRED')
            if effect['kind']=='goal_activate':
                _s3_fields(effect,{'kind','entity_id','goal_id'})
                if effect['entity_id']!=action['subject_id'] or effect['goal_id'] not in _s3_runtime(state)['npcs'][effect['entity_id']]['goals']:raise EngineError('STORY_SCHEDULE_GOAL_REFERENCE')
            elif effect['kind']=='learn_fact':
                _s3_fields(effect,{'kind','fact_id','viewer_id'})
                if not proposal or effect['fact_id'] not in _knowledge_known(state,sid,'npc:'+proposal['actor_id']):raise EngineError('STORY_SCHEDULE_KNOWLEDGE_SOURCE_REQUIRED')
                if effect['viewer_id'].startswith('npc:') and effect['viewer_id'][4:] not in _story_record(state,sid)['participants']:raise EngineError('STORY_SCHEDULE_RECIPIENT_NOT_PRESENT')
            else:raise EngineError('STORY_MECHANICAL_CONSEQUENCE_UNSUPPORTED')
        row={k:copy.deepcopy(v) for k,v in action.items() if k!='type'}
        row.update(schema='STORY_CONSEQUENCE_V2',scene_id=sid,status='pending',cause_event_id=cause,created_by=ctx['event_id'],created_at=now,authorization_ref=ctx['authorization_ref'],authorized_payload_sha256=_domain_payload_digest(ctx['outer']),next_check_at=action['not_before'])
        story['consequences'][cid]=row;_s3_runtime(state)['npcs'][action['subject_id']]['commitment_refs'].append({'consequence_id':cid,'source_event_id':ctx['event_id']})
    else:
        _s3_fields(action,{'type','scene_id','consequence_id','status','reason'})
        c=story['consequences'].get(cid)
        if not c or c['scene_id']!=sid or c['status'] not in ('pending','waiting_ai','waiting_condition'):raise EngineError('STORY_CONSEQUENCE_NOT_PENDING')
        status=action['status'];_story_text(action['reason'],500);at=parse_iso(now)
        if status not in ('delivered','cancelled','expired','waiting_ai'):raise EngineError('STORY_CONSEQUENCE_RESOLUTION_INVALID')
        if status=='delivered' and (not parse_iso(c['not_before'])<=at<=parse_iso(c['not_after']) or not _s3_condition(state,c.get('condition',{'kind':'always'})) or not _s3_task_active(tasks,c.get('task_id'))):raise EngineError('STORY_CONSEQUENCE_DELIVERY_PRECONDITION')
        if status=='expired' and at<=parse_iso(c['not_after']):raise EngineError('STORY_CONSEQUENCE_NOT_EXPIRED')
        c.update(status=status,resolved_at=now,resolution_event_id=ctx['event_id'],resolution_reason=action['reason'],next_check_at=None)
    return {'action':typ,'consequence_id':cid,'status':story['consequences'][cid]['status'],'changes':[{'target':'state:engine_runtime.story_runtime_v1.consequences.'+cid,'action':typ}]}


def _s3_pending_nodes(state,tasks,now,horizon):
    rows=[]
    for cid,c in state.get('engine_runtime',{}).get('story_runtime_v1',{}).get('consequences',{}).items():
        if c['status'] not in ('pending','waiting_ai','waiting_condition'):continue
        lo=parse_iso(c['not_before']);hi=parse_iso(c['not_after']);expiry=hi+dt.timedelta(seconds=1)
        rec=_story_record(state,c['scene_id']);condition=_s3_condition(state,c.get('condition',{'kind':'always'}))
        if rec['phase']=='closed' or not _s3_task_active(tasks,c.get('task_id')):when=now;action='cancel'
        elif now>hi:when=now;action='expire'
        elif now<lo:when=lo;action='evaluate'
        elif not condition:
            if c['status']=='waiting_condition':when=expiry;action='expire'
            else:when=now;action='defer'
        elif c.get('mode','needs_ai')=='needs_ai':when=now;action='ai'
        else:when=now;action='deliver'
        if when>horizon:continue
        if action=='evaluate':
            if condition:action='ai' if c.get('mode','needs_ai')=='needs_ai' else 'deliver'
            else:action='defer'
        if action=='deliver' and c.get('schema')=='STORY_CONSEQUENCE_V2':
            grant=state.get('standing_authorizations',{}).get(c['authorization_ref'])
            if grant is not None and (grant.get('status')!='active' or grant.get('revoked') or not parse_iso(grant.get('machine_grant',{}).get('valid_until')) or parse_iso(grant['machine_grant']['valid_until'])<when):action='authorization'
        rows.append({'time':when.isoformat(),'source':'story_consequence','consequence_id':cid,'job_id':cid,'resolver':'story_consequence_v2','action':action,'title':'已授权剧情后果节点','task_id':None})
    return sorted(rows,key=lambda x:(x['time'],x['consequence_id'],x['action']))


def _s3_queue(state,tasks,now,horizon):
    rows=_s3_previous_queue(state,tasks,now,horizon)
    rows += [r for r in _s3_pending_nodes(state,tasks,now,horizon) if r['action'] not in ('ai','authorization')]
    return sorted(rows,key=lambda x:(x.get('time',''),x.get('source',''),x.get('task_id') or x.get('job_id') or ''))


def _s3_precedes(event,event_time,hard,barrier):
    if event.get('source')=='story_consequence' and event_time==hard and (barrier or {}).get('kind') in ('story_consequence_ai','story_consequence_authorization'):
        return event['consequence_id']<(barrier.get('event') or {}).get('consequence_id','')
    return _s3_previous_precedes(event,event_time,hard,barrier)


def _s3_next_ai(tasks,now,horizon,state=None):
    prior=_s3_previous_ai(tasks,now,horizon,state)
    if state is None or not state.get('engine_runtime',{}).get('story_turns_v1'):return prior
    candidates=[prior] if prior else []
    for row in _s3_pending_nodes(state,tasks,now,horizon):
        if row['action'] in ('ai','authorization'):candidates.append({'time':parse_iso(row['time']),'kind':'story_consequence_ai' if row['action']=='ai' else 'story_consequence_authorization','title':row['title'],'event':{'consequence_id':row['consequence_id'],'query':'storyprepare / storytimeline'},'resolution_required':'NEEDS_AI / NEEDS_AUTHORIZATION: explicit authorized turn or consequence management; no implicit delivery'})
    return min(candidates,key=lambda r:(r['time'],r.get('task_id') or '',r.get('event',{}).get('consequence_id',''))) if candidates else None


def _s3_resolve(stage,state,tasks,event,when):
    if event.get('source')!='story_consequence':return _s3_previous_resolve(stage,state,tasks,event,when)
    cid=event['consequence_id'];c=_story_runtime(state)['consequences'][cid]
    if c['status'] not in ('pending','waiting_ai','waiting_condition'):raise EngineError('STORY_CONSEQUENCE_ALREADY_TERMINAL')
    # Re-evaluate the node against the actual new world; never trust an old plan.
    fresh=next((r for r in _s3_pending_nodes(state,tasks,when,when) if r['consequence_id']==cid),None)
    if not fresh or fresh['action']=='ai':raise EngineError('STORY_CONSEQUENCE_PLAN_INVALIDATED')
    action=fresh['action'];event_id='STORY-NODE-'+cid+'-'+sha256_bytes((c['created_by']+when.isoformat()+action).encode())[:12]
    if action=='defer':c.update(status='waiting_condition',next_check_at=None,waiting_condition=copy.deepcopy(c.get('condition',{'kind':'always'})))
    elif action in ('cancel','expire'):c.update(status='cancelled' if action=='cancel' else 'expired',resolved_at=when.isoformat(),resolution_event_id=event_id,next_check_at=None)
    elif action=='deliver':
        creation=history_lookup(stage,event_id=c['created_by']) or _lw_inflight_creation(c['created_by'])
        if not creation or creation.get('payload_sha256')!=c.get('authorized_payload_sha256') or creation.get('authorization',{}).get('status')!='verified':raise EngineError('STORY_SCHEDULE_COMMITTED_AUTHORIZATION_REQUIRED')
        if creation['authorization'].get('authority')=='standing_authorization':
            grant=state.get('standing_authorizations',{}).get(c['authorization_ref'],{})
            if grant.get('status')!='active' or grant.get('revoked'):raise EngineError('STORY_SCHEDULE_AUTHORIZATION_REVOKED')
        effect=c['effect']
        if effect['kind']=='goal_activate':
            npc=_s3_runtime(state)['npcs'][effect['entity_id']];goal=npc['goals'][effect['goal_id']]
            if goal['status']!='pending':raise EngineError('STORY_SCHEDULE_GOAL_NOT_PENDING')
            goal.update(status='active',source_event_id=event_id,updated_at=when.isoformat());npc['revision']+=1;npc['last_event_id']=event_id
        elif effect['kind']=='learn_fact':
            viewer=effect['viewer_id'];fid=effect['fact_id']
            if fid not in _knowledge_known(state,c['scene_id'],viewer):
                token=_story_scope.set({'event_id':event_id,'command_id':event_id,'authorization_ref':c['authorization_ref'],'outer':{},'stage':Path(stage)})
                try:_knowledge_action(stage,state,tasks,{'type':'knowledge_disclose','scene_id':c['scene_id'],'fact_id':fid,'viewer_id':viewer,'channel':'reported','basis_event_id':c['created_by']})
                finally:_story_scope.reset(token)
                if viewer.startswith('npc:'):
                    npc=_s3_runtime(state)['npcs'][viewer[4:]];npc['memory_refs'].append({'scene_id':c['scene_id'],'fact_id':fid,'source_event_id':event_id});npc['revision']+=1;npc['last_event_id']=event_id
        else:raise EngineError('STORY_SCHEDULE_EFFECT_NOT_SUPPORTED')
        c.update(status='delivered',resolved_at=when.isoformat(),resolution_event_id=event_id,next_check_at=None)
    else:raise EngineError('STORY_SCHEDULE_NODE_ACTION_INVALID')
    changes=[{'target':'state:engine_runtime.story_runtime_v1.consequences.'+cid,'action':action}]
    if action=='deliver':changes.append({'target':'state:engine_runtime.story_turns_v1','action':'deliver_previously_authorized_nonfinancial_effect'})
    _append_engine_history(Path(stage)/'events.jsonl',{'event_id':event_id,'game_time':when.isoformat(),'type':'story_consequence_resolution','summary':'剧情后果调度；不生成奖励、交易、移动或随机判定。','changes':changes,'authority_files':['state.json'],'source':'GAME ENGINE '+ENGINE_VERSION,'consequence_id':cid,'cause_event_id':c['cause_event_id'],'authorization_event_id':c['created_by'],'outcome':c['status']})
    return {'status':'COMMITTED','event_id':event_id,'consequence_id':cid,'outcome':c['status'],'changes':changes}


def _story_preview_events(state,tasks,now,horizon):
    return [{'event_id':'STORY-DUE-'+row['consequence_id'],'source':'story_consequence','source_job_id':row['consequence_id'],'title':row['title'],'time':row['time'],'event_type':'story_consequence','severity':'important' if row['action'] in ('ai','authorization') else 'routine','requires_simulation':row['action'] in ('ai','authorization'),'deterministic_resolver':None if row['action'] in ('ai','authorization') else 'story_consequence_v2'} for row in _s3_pending_nodes(state,tasks,now,horizon)]


def _s3_consequence_integrity(state,tasks):
    errors=[]
    for cid,c in _story_runtime(state)['consequences'].items():
        if c.get('schema')!='STORY_CONSEQUENCE_V2':continue
        try:
            if cid!=c['consequence_id'] or c['status'] not in ('pending','waiting_ai','waiting_condition','delivered','expired','cancelled'):raise EngineError('STORY_CONSEQUENCE_CONTRACT')
            lo=parse_iso(c['not_before']);hi=parse_iso(c['not_after'])
            if not lo or not hi or lo>hi or not c.get('created_by') or not c.get('authorized_payload_sha256'):raise EngineError('STORY_CONSEQUENCE_BINDING')
            _s3_condition(state,c['condition']);_s3_entity(state,c['subject_id'],True)
            if c['status']=='delivered' and not lo<=parse_iso(c['resolved_at'])<=hi:raise EngineError('STORY_CONSEQUENCE_DELIVERY_WINDOW')
            if c['status']=='expired' and parse_iso(c['resolved_at'])<=hi:raise EngineError('STORY_CONSEQUENCE_EXPIRY_WINDOW')
        except Exception as ex:errors.append(str(ex))
    return errors


def _s3_source_report(base):
    out=_s3_previous_source_report(base);state=read_json(Path(base)/'state.json');rt=state.get('engine_runtime',{}).get('story_turns_v1')
    if not rt:return out
    refs=[]
    for row in rt['turns'].values():
        refs.append(row['source_event_id']);refs += [r['source_event_id'] for r in row.get('revisions',[])]
        event=history_lookup(base,event_id=row['source_event_id']) or {};effect=event.get('domain_effect') or {};command=effect.get('command_payload') or {}
        if event.get('domain_kind')!='story_turn' or command.get('proposal')!=row['proposal'] or command.get('command_id')!=row['turn_id'] or command.get('kind')!='story_turn' or _domain_payload_digest(command)!=event.get('payload_sha256') or effect.get('mechanical_effects')!=row['mechanical_effects'] or effect.get('verified_effects')!=row['verified_effects'] or event.get('authorization',{}).get('status')!='verified':out['errors'].append('STORY_TURN_SOURCE_RECEIPT_BINDING')
        for revision in row.get('revisions',[]):
            if revision.get('unchanged_effects_sha256')!=_repair_digest(row['mechanical_effects']):out['errors'].append('STORY_REWRITE_EFFECTS_CHANGED')
    for npc in rt['npcs'].values():
        if npc['last_event_id']:refs.append(npc['last_event_id'])
        for row in npc['traits']+list(npc['goals'].values())+list(npc['relations'].values())+npc['memory_refs']+npc['commitment_refs']:refs.append(row['source_event_id'])
    for rec in _scene_registry(state)['records'].values():
        if rec.get('source_event_id'):refs.append(rec['source_event_id'])
        refs += [r['source_event_id'] for r in rec.get('join_events',[])]
    for grant in state.get('standing_authorizations',{}).values():
        if grant.get('source')=='verified explicit human/host policy, no implicit NPC authority':
            refs.append(grant['source_event_id'])
            if grant.get('revoked_by'):refs.append(grant['revoked_by'])
    for c in _story_runtime(state)['consequences'].values():
        if c.get('schema')!='STORY_CONSEQUENCE_V2':continue
        event=history_lookup(base,event_id=c['created_by']) or {};command=(event.get('domain_effect') or {}).get('command_payload') or {}
        if event.get('payload_sha256')!=c['authorized_payload_sha256'] or event.get('authorization',{}).get('status')!='verified' or command.get('kind') not in ('story_turn','story_setup') or _domain_payload_digest(command)!=event.get('payload_sha256'):
            out['errors'].append('STORY_SCHEDULE_SOURCE_AUTHORIZATION_BINDING');continue
        action=next((a for a in _s3_updates(command) if a.get('type')=='consequence_schedule' and a.get('consequence_id')==c['consequence_id']),None)
        if not action:out['errors'].append('STORY_SCHEDULE_SOURCE_ACTION_MISSING');continue
        for key,value in action.items():
            if key=='type':continue
            if key=='cause_event_id' and value=='$current_transaction':value=c['created_by']
            if c.get(key)!=value:out['errors'].append('STORY_SCHEDULE_SOURCE_EFFECT_MISMATCH')
    for ref in set(refs):
        if not history_lookup(base,event_id=ref):out['errors'].append('STORY_NEW_STATE_EVIDENCE_MISSING')
    out['errors']+=_s3_consequence_integrity(state,read_json(Path(base)/'tasks.json'))
    out['errors']+=_s4_extension_audit(base)
    out['status']='FAIL' if out['errors'] else 'PASS';return out


def story_timeline(base,viewer='player',until=None):
    _s3_viewer(viewer)
    with SnapshotContext(base):
        ensure_source_ready(base);state=read_json(Path(base)/'state.json');tasks=read_json(Path(base)/'tasks.json');now=parse_iso(state['game_time']);horizon=parse_iso(until) if until else now+dt.timedelta(days=1)
        if horizon is None or horizon<now:raise EngineError('STORY_TIMELINE_WINDOW')
        rows=[]
        for row in _s3_pending_nodes(state,tasks,now,horizon):
            c=_story_runtime(state)['consequences'][row['consequence_id']]
            if viewer=='gm' or viewer in c['visible_to']:rows.append({k:v for k,v in row.items() if k not in ('resolver','task_id')})
        return {'packet':'STORY_TIMELINE_V1','base_identity':_s3_identity(base),'viewer':viewer,'rows':rows,'window_semantics':'not_before <= delivery <= not_after; expire at not_after + 1 second','ordering':'time, source, stable consequence ID','condition_wait':'event-driven recheck on knowledge/state change; deadline still scheduled'}


def story_schema_packet():
    return {'packet':'STORY_SCHEMAS_V1','proposal_schema':STORY_TURN_SCHEMA,'proposal_required':['elapsed_seconds','schema','turn_id','base_identity','scene_id','actor_id','viewer','player_intent','intent_tags','basis_refs','segments','effects','updates','consequences','claims','public_reason','candidates'],'segment_required':['mode','speaker_id','text','basis_refs','receipt_refs'],'segment_modes':['description','dialogue','quote','rumor','hypothesis','outcome'],'claim_required':['receipt_ref','expected_effect'],'mechanical_kinds':sorted(STORY_MECHANICAL_KINDS),'update_kinds':sorted(STORY_UPDATE_KINDS),'authorization':'real existing standing grant including child action kinds and budgets, or authenticated host envelope; never self-approved proposal','services':['prepare_turn','validate_proposal','commit_turn','turn_report','story_timeline'],'model_status':'NEEDS_AI','schema_files':'development/schemas/story_turn_v1.json and STAGE3_API_V14.55.md'}


def _s3_catalog(base=ROOT):
    out=_s3_previous_catalog(base);out['queries']+=['storyprepare','storyvalidate','storyreport','storytimeline','storyschema'];out['story_turn_contract']=story_schema_packet();return out


def _s3_domain_packet(base,payload,version,scope,dry_run=False,**kwargs):
    # An authorized NPC write must not acquire commander diagnostics merely
    # because the old write presenter used a player default. This also covers
    # standalone child kinds legitimately permitted by a finite existing grant.
    requested=payload.get('proposal',{}).get('viewer') if payload.get('kind')=='story_turn' else None
    with TransactionValidationContext(base):
        state=read_json(Path(base)/'state.json');npc_actor=payload.get('actor_id') in state.get('engine_runtime',{}).get('story_turns_v1',{}).get('npcs',{})
        viewer=requested if isinstance(requested,str) and requested.startswith('npc:') else 'npc:'+payload['actor_id'] if npc_actor else None
        presentation=kwargs.get('presentation',_stage2_presentation_scope.get())
        if viewer is not None:kwargs['presentation']='full'
        result=_s3_previous_domain(base,payload,version,scope,dry_run,**kwargs)
        if payload.get('kind')=='story_turn' and requested!='gm':result=_lw_clock_projection(result,requested or viewer or 'player')
        if viewer is None:return result
        receipt=result.get('receipt') or {}
        out={'packet':'STORY_TURN_COMMIT_RESULT_V1','viewer':viewer,'status':result.get('status'),'committed':result.get('committed',False),'command_id':payload.get('command_id'),'save_set_id':result.get('save_set_id'),'receipt':{k:receipt[k] for k in ('command_id','event_id','payload_sha256','parent_save_set_id','applied_at') if k in receipt},'saved':result.get('saved',result.get('status')=='SAVED')}
        try:
            effect=result.get('effect') or receipt.get('effect') or {}
            out['effects']={k:copy.deepcopy(v) for k,v in effect.items() if k!='command_payload'}
            if payload.get('kind')=='story_turn' and not dry_run:out['report']=turn_report(base,payload['command_id'],viewer)
            return _stage2_present_write(_stage2_finalize_size(out,_stage2_budget_scope.get()),base,presentation)
        except Exception:
            # Never revert to the private player packet after a committed NPC
            # operation, and never relabel a successful commit as uncommitted.
            out.pop('effects',None);out.pop('report',None);out['presentation_status']='SCOPED_RECEIPT_ONLY';out['retry_action']='read original receipt; do not redo effects';return out


def _s3_narrative_context(base=ROOT,scene_id=None,viewer='player',budget_bytes=12000):
    # Retire the old title/substring selector and its global recent-pattern list.
    return prepare_turn(base,scene_id,viewer=viewer,player_intent='当前场景续接',budget_bytes=budget_bytes)


def _s3_main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv);cmd=args[0] if args else ''
    own={'storyprepare','storyvalidate','storyreport','storytimeline','storyschema'}
    if cmd not in own:return _s3_previous_main(args)
    try:
        parser=argparse.ArgumentParser();parser.add_argument('--base',default=str(ROOT));parser.add_argument('--viewer',default='player');parser.add_argument('--scene-id');parser.add_argument('--actor-id');parser.add_argument('--intent',default='继续当前交互');parser.add_argument('--intent-tags');parser.add_argument('--budget-bytes',type=int,default=16384);parser.add_argument('--input');parser.add_argument('--id');parser.add_argument('--until')
        ns=parser.parse_args(args[1:]);_s3_viewer(ns.viewer)
        # Every read buffers its output until the SnapshotContext exit validates
        # the actual byte set. No compact/full GM diagnostics are attached.
        with SnapshotContext(Path(ns.base)):
            ensure_source_ready(Path(ns.base))
            if cmd=='storyschema':out=story_schema_packet()
            elif cmd=='storyprepare':out=prepare_turn(Path(ns.base),ns.scene_id,ns.actor_id,ns.viewer,ns.intent,json.loads(ns.intent_tags) if ns.intent_tags else None,ns.budget_bytes)
            elif cmd=='storyvalidate':
                proposal=_cli_json_input(ns.input,'STORY_PROPOSAL')
                if proposal.get('viewer')!=ns.viewer:raise EngineError('STORY_VALIDATION_VIEWER_MISMATCH')
                out=validate_proposal(Path(ns.base),proposal)
            elif cmd=='storyreport':out=turn_report(Path(ns.base),ns.id,ns.viewer)
            else:out=story_timeline(Path(ns.base),ns.viewer,ns.until)
        print(json.dumps(out,ensure_ascii=False,separators=(',',':'),default=str));return 0
    except Exception as ex:
        # Only stable codes; never echo a hidden path, fact, grant or payload.
        print(json.dumps({'status':'FAIL','code':str(ex).split(':')[0]},ensure_ascii=False));return 1


deterministic_event_queue=_s3_queue
_resolve_deterministic_event=_s3_resolve
_next_ai_monitor_time=_s3_next_ai
_deterministic_event_precedes_barrier=_s3_precedes
_story_source_report=_s3_source_report
domain_command_catalog=_s3_catalog
domain_command_packet=_s3_domain_packet
narrative_context_packet=_s3_narrative_context
main=_s3_main


class StoryTurnService:
    prepare=staticmethod(prepare_turn)
    validate=staticmethod(validate_proposal)
    commit=staticmethod(commit_turn)
    report=staticmethod(turn_report)
    timeline=staticmethod(story_timeline)

NarrativeDirector.context=staticmethod(narrative_context_packet)



def submit_round(base,envelope,version,dry_run=False):
    command=envelope.get('command',{});proposal=command.get('proposal',{})
    if command.get('kind')!='story_turn':raise EngineError('ROUND_REQUIRES_STORY_TURN')
    viewer=proposal.get('viewer');_s3_viewer(viewer)
    with TransactionValidationContext(base):
        result=host_intent_command(base,envelope,version,dry_run)
        if not dry_run and result.get('status') in ('SAVED','ALREADY_APPLIED') and 'report' not in result:
            try:result['report']=turn_report(base,command['command_id'],viewer)
            except Exception as ex:
                result['presentation_status']='COMMITTED_REPORT_REQUIRES_REREAD';result['presentation_error']=str(ex);result['retry_action']='read original receipt with same command_id; do not redo effects'
        return _stage2_finalize_size(result,_stage2_budget_scope.get())


class RoundService:
    prepare=staticmethod(prepare_turn)
    submit=staticmethod(submit_round)
