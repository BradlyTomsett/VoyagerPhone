# === VOYAGER_DEV_MODULE: query_layer ===
def _query_packet_v251(base:Path, topic:str, history_limit:int=5, task_limit:int=5, detail:str="compact")->dict:
    ready=ensure_source_ready(base)
    tasks=read_json(base/"tasks.json");world=_authority_world_text(base)
    state=None;state_index=None
    direct_alias_paths=_direct_state_alias_paths(topic)
    if direct_alias_paths and detail!="full":
        try:state_index=_state_semantic_index(base)
        except Exception:state_index=None
    variants=[]
    for v in _query_variants(topic)+_query_terms(topic):
        if v and v not in variants:variants.append(v)
    q=variants[0] if variants else "";all_tasks=tasks.get("active_tasks",[])+tasks.get("queued_tasks",[]);scored=[]
    direct_rule_ids=_direct_world_rule_ids(topic,base)
    combat_focus=bool(direct_rule_ids) and any(k in _normalize_search_text(topic) for k in ["战力","战斗力","火力","耐久","护盾","武装","舰体","对地","地面支援"]) and not any(k in _normalize_search_text(topic) for k in ["价格","市场","购买","出售","报价","库存","采购","交易"])
    for t in all_tasks:
        blob=_normalize_search_text(" ".join([str(t.get("task_id","")),str(t.get("title","")),str(t.get("status","")),str(t.get("phase","")),str(t.get("current_status","")),str(t.get("semantic_context","")),str(t.get("known_value","")),str(t.get("next_trigger","")),str(t.get("trigger_condition","")),str(t.get("task_data",{}))," ".join((t.get("retrieval_route") or {}).get("query_aliases") or [])," ".join(t.get("owner_ids",[]) or [])," ".join(t.get("location_ids",[]) or [])]))
        score=sum((4 if v==q else 1)*blob.count(v) for v in variants if v)
        if score:scored.append((score,t))
    scored.sort(key=lambda z:(z[0],z[1].get("priority","")=="high"),reverse=True)
    task_cap=0 if combat_focus else max(0,int(task_limit));matched_total=len(scored);matched_raw=[t for _,t in scored[:task_cap]];full=detail=="full"
    unresolved=[];state_values={};world_rules={};world_rule_meta={};terms=list(variants);rule_truncated=False
    def ensure_state():
        nonlocal state
        if state is None:state=read_json(base/"state.json")
        return state
    for pth in direct_alias_paths:
        try:
            if not full and isinstance(state_index,dict) and pth in (state_index.get("alias_values") or {}):state_values[pth]=_compact_value((state_index.get("alias_values") or {})[pth],3600)
            else:
                sv=get_state_path(ensure_state(),pth);state_values[pth]=sv if full else _compact_value(sv,3600)
        except KeyError:unresolved.append({"type":"state_alias_path","value":pth})
    requested_rule_ids=list(direct_rule_ids)
    for t in matched_raw:
        rr=t.get("retrieval_route") or {}
        for pth in rr.get("state_paths",[]) or []:
            if pth in state_values:continue
            try:
                st0=ensure_state();resolved_pth=resolve_state_ref(st0,pth)
                if not full and isinstance(state_index,dict) and resolved_pth in (state_index.get("alias_values") or {}):state_values[pth]=_compact_value((state_index.get("alias_values") or {})[resolved_pth],1200)
                else:
                    sv=get_by_path(st0,resolved_pth);state_values[pth]=sv if full else _compact_value(sv,1200)
            except KeyError:unresolved.append({"type":"state_path","task_id":t.get("task_id"),"value":pth})
        if not combat_focus:requested_rule_ids.extend(rr.get("world_rules",[]) or [])
        terms+=list(rr.get("history_tags",[]) or [])+list(t.get("owner_ids",[]) or [])+list(t.get("location_ids",[]) or [])
    dedup=[];seen=set()
    for rid in requested_rule_ids:
        if rid and rid not in seen:seen.add(rid);dedup.append(rid)
    requested_rule_ids=dedup;rule_request_total=len(requested_rule_ids);rule_cap=rule_request_total if full else min(rule_request_total,5);char_budget=None if full else 12000;used_chars=0
    for rid in requested_rule_ids[:rule_cap]:
        remaining=9000 if full else max(1,min(3600,(char_budget-used_chars) if char_budget is not None else 3600))
        if not full and char_budget is not None and used_chars>=char_budget:rule_truncated=True;break
        try:
            rec=resolve_rule_registry(base,rid)
            sec='### '+rec['effective_rule_id']+' '+str(rec.get('title') or '')+'\n'+json.dumps({k:rec.get(k) for k in ('lifecycle_status','implementation_status','version','scope','source_ref','resolved_parameters','semantic_notes')},ensure_ascii=False)
            sec=sec[:remaining]
            meta={'source':'rules.json:rule_registry','resolved_from':rid,'effective_rule_id':rec['effective_rule_id'],'truncated':len(sec)>=remaining}
            world_rules[rid]=sec;world_rule_meta[rid]=meta;used_chars+=len(sec);rule_truncated=rule_truncated or meta['truncated']
        except EngineError as ex:unresolved.append({'type':'world_rule','value':rid,'error':str(ex)})
    if len(world_rules)<rule_request_total and not unresolved:rule_truncated=True
    state_hits=[]
    entity_locator=_state_index_entity_hit(base,variants) if q else None
    if q and (not direct_alias_paths or entity_locator is not None):
        stobj=ensure_state()
        # Exact indexed entity queries jump directly to their object/row first.
        if entity_locator is not None:
            try:
                pth=entity_locator.get("path");state_hits.append({"path":pth,"value":_compact_value(get_by_path(stobj,pth),900)})
            except Exception:pass
        for rootkey in ["summary","key_personnel_current_roles","world_state_overrides","inventories","task_allocations","standing_authorizations","voyager_fleet","jinchuan_fleet","shadow_fleet","engine_runtime"]:
            if len(state_hits)>=8:break
            if rootkey in stobj:
                for v in variants:
                    state_hits.extend(_search_obj_hits(stobj[rootkey],v,rootkey,limit=max(0,8-len(state_hits)),max_chars=900))
                    if len(state_hits)>=8:break
    hist=_history_index_events(base,terms,history_limit,full) if q else []
    world_keyword_context=[]
    if q:
        lines=world.splitlines();hit_idx=[]
        for v in variants:
            hit_idx.extend(i for i,line in enumerate(lines) if v and v in _normalize_search_text(line))
        uniq=sorted(set(hit_idx))
        if combat_focus:
            focus_terms=["武装","护盾","激光","近防","炮","导弹","舰体","战力","耐久","火力"]
            uniq=sorted(uniq,key=lambda i:(-sum(1 for k in focus_terms if k in _normalize_search_text(lines[i])),i))
        for i in uniq[:2]:
            lo=max(0,i-1);hi=min(len(lines),i+3);world_keyword_context.append("\n".join(lines[lo:hi]))
    task_truncated=(matched_total>len(matched_raw)) if not combat_focus else False;truncated=task_truncated or rule_truncated
    evidence=bool(matched_raw or state_values or state_hits or hist or world_rules or world_keyword_context)
    status="NOT_FOUND" if not evidence else ("PARTIAL" if unresolved else ("TRUNCATED" if truncated else "COMPLETE"))
    task_payload=[]
    for t in matched_raw:
        if full:task_payload.append(t);continue
        rp = effective_runtime_policy(tasks, t)
        surface=_task_surface(t,ensure_state() if _task_uses_derived_view(t) else state,False)
        surface["runtime"]=_runtime_policy_compact(rp)
        task_payload.append(surface)
    return {
        "engine_version":ENGINE_VERSION,"packet":"QUERY_COMPACT_V5" if not full else "QUERY_FULL_V5","status":status,"topic":topic,
        "game_time":(state.get("game_time") if isinstance(state,dict) else (state_index or {}).get("game_time")),"summary":(state.get("summary") if isinstance(state,dict) else (state_index or {}).get("summary")),"source_ready":ready,
        "matched_task_total":matched_total,"returned_task_count":len(matched_raw),"suppressed_task_matches_for_combat_focus":matched_total if combat_focus else 0,"tasks":task_payload,
        "matched_rule_total":rule_request_total,"returned_rule_count":len(world_rules),"combat_focus":combat_focus,
        "resolved_state_paths":state_values,"state_hits":state_hits,"world_rule_sections":world_rules,"world_rule_meta":world_rule_meta,"world_keyword_context":world_keyword_context,
        "recent_relevant_events":hist,"unresolved":unresolved,"truncated":truncated,
        "runtime_indexes":{"history":"locator_only_v3_integrity","world":"rule_section_v1_integrity","state":"semantic_sidecar_v2","entities":"locator_sidecar_v1"},
        "note":"Compact evidence packet. Direct combat questions prioritize combat rules and current state over unrelated task-rule bundles. Compact rule payload is bounded; expand when PARTIAL/TRUNCATED or evidence is insufficient."
    }

_query_packet_legacy=_query_packet_v251
def _query_has_truncated_evidence(value):
    """Recognize the actual compact-value markers, not natural-language ellipses."""
    if isinstance(value,dict):
        if value.get('_truncated') is True or value.get('truncated') is True or value.get('_truncated_items',0):return True
        if value.get('format')==ROW_REGISTRY_FORMAT and 'row_count' in value and 'rows' not in value:return True
        return any(_query_has_truncated_evidence(v) for v in value.values())
    if isinstance(value,list):return any(_query_has_truncated_evidence(v) for v in value)
    return isinstance(value,str) and value.endswith('...[truncated]')





def _derived_voyager_ship_combat_sources(state:dict)->dict:
    vf=state.get('voyager_fleet') or {}
    return {
        'class_counts':copy.deepcopy(vf.get('class_counts') or []),
        'class_combat_power_snapshot':copy.deepcopy(vf.get('class_combat_power_snapshot') or {}),
        'vessel_roster':copy.deepcopy(vf.get('vessel_roster') or []),
    }

def _derived_voyager_ship_combat_source_hash(state:dict)->str:
    raw=json.dumps(_derived_voyager_ship_combat_sources(state),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()

def _build_voyager_ship_combat_derived(state:dict)->dict:
    """Build the per-vessel combat view from bounded canonical/registered inputs.

    The per-vessel table is intentionally not authority.  Class-level sealed combat values
    remain in STATE until a later migration can rebuild those values directly from WORLD.
    """
    vf=state.get('voyager_fleet') or {}
    class_counts=vf.get('class_counts') or []
    class_snap=vf.get('class_combat_power_snapshot') or {}
    roster=vf.get('vessel_roster') or []
    if not isinstance(class_counts,list) or not isinstance(class_snap,dict) or not isinstance(roster,list):
        raise EngineError('DERIVED_VOYAGER_SHIP_COMBAT_SOURCE_INVALID')
    by_id={str(x.get('class_id')):str(x.get('name')) for x in class_counts if isinstance(x,dict) and x.get('class_id') and x.get('name')}
    classes=class_snap.get('classes') or {}
    if not isinstance(classes,dict):raise EngineError('DERIVED_VOYAGER_SHIP_COMBAT_CLASSES_INVALID')
    ships={}
    for row in roster:
        if not isinstance(row,dict):raise EngineError('DERIVED_VOYAGER_SHIP_COMBAT_ROSTER_ROW_INVALID')
        vid=str(row.get('vessel_id') or '');name=str(row.get('name') or '');cid=str(row.get('class_id') or '')
        cname=by_id.get(cid);c=classes.get(cname) if cname else None
        if not vid or not name or not cid or not cname or not isinstance(c,dict):
            raise EngineError(f'DERIVED_VOYAGER_SHIP_COMBAT_ROUTE_MISSING:{vid}:{name}:{cid}:{cname}')
        for key in ('C_base','fixed_air_A','C_final'):
            if key not in c:raise EngineError(f'DERIVED_VOYAGER_SHIP_COMBAT_CLASS_FIELD_MISSING:{cname}:{key}')
        ships[name]={'vessel_id':vid,'class_id':cid,'class_name':cname,'C_base':c['C_base'],'fixed_air_A':c['fixed_air_A'],'C_final':c['C_final'],'age_policy':'A_hull=1.00; commander-owned no age combat degradation'}
    cbase=round(sum(float(x['C_base']) for x in ships.values()),2)
    air=round(sum(float(x['fixed_air_A']) for x in ships.values()),2)
    cfinal=round(sum(float(x['C_final']) for x in ships.values()),2)
    # Preserve exact legacy view semantics while making provenance explicit outside authority.
    out={'as_of':class_snap.get('as_of'),'ship_count':len(ships),'rule':'RULE-COMBAT-01 + RULE-AIR-GROUND-COMBAT-01; self-owned A_hull=1.00','inventory_exclusion':'C_final只含舰船本体固定武器/护盾与固定舰载作战航空；陆战队、地面机器人/车辆不计舰战C。','ships':ships,'fleet_total_C_base':cbase,'fleet_total_fixed_air_A':int(air) if float(air).is_integer() else air,'fleet_total_C':cfinal,'call_policy':'以后按参战舰名直接从本表抽取C；仅固定装备/固定航空/护盾/永久战损变化触发重算。'}
    return out

def _voyager_ship_combat_equivalent(a:dict,b:dict)->bool:
    """Semantic equality for the retired persisted view, tolerant only of numeric encoding."""
    if not isinstance(a,dict) or not isinstance(b,dict):return False
    scalar=('as_of','ship_count','rule','inventory_exclusion','call_policy')
    if any(a.get(k)!=b.get(k) for k in scalar):return False
    for k in ('fleet_total_C_base','fleet_total_fixed_air_A','fleet_total_C'):
        try:
            if abs(float(a.get(k))-float(b.get(k)))>1e-9:return False
        except Exception:return False
    sa=a.get('ships') or {};sb=b.get('ships') or {}
    if set(sa)!=set(sb):return False
    for name in sa:
        x,y=sa[name],sb[name]
        if not isinstance(x,dict) or not isinstance(y,dict):return False
        for k in ('vessel_id','class_id','class_name','age_policy'):
            if x.get(k)!=y.get(k):return False
        for k in ('C_base','fixed_air_A','C_final'):
            try:
                if abs(float(x.get(k))-float(y.get(k)))>1e-9:return False
            except Exception:return False
    return True

def _derived_view_cache_path(base:Path)->Path:
    return base/'.runtime'/'derived_views.json'

def _derived_view_cache_read(base:Path,key:str,source_hash:str)->Optional[dict]:
    p=_derived_view_cache_path(base)
    try:
        if not p.is_file():return None
        obj=read_json(p)
        if obj.get('schema')!=DERIVED_RUNTIME_SCHEMA or obj.get('engine_version')!=ENGINE_VERSION:return None
        row=(obj.get('views') or {}).get(key)
        if not isinstance(row,dict) or row.get('source_sha256')!=source_hash:return None
        val=row.get('value')
        return copy.deepcopy(val) if isinstance(val,dict) else None
    except Exception:return None

def _derived_view_cache_write(base:Path,key:str,source_hash:str,value:dict)->None:
    # Sidecar only. Failure to cache must never make a game fact unavailable.
    try:
        p=_derived_view_cache_path(base);p.parent.mkdir(parents=True,exist_ok=True)
        obj={'schema':DERIVED_RUNTIME_SCHEMA,'engine_version':ENGINE_VERSION,'views':{}}
        if p.is_file():
            try:
                old=read_json(p)
                if old.get('schema')==DERIVED_RUNTIME_SCHEMA and old.get('engine_version')==ENGINE_VERSION:obj=old
            except Exception:pass
        obj.setdefault('views',{})[key]={'source_sha256':source_hash,'built_at_game_time':value.get('as_of'),'value':copy.deepcopy(value)}
        tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')),encoding='utf-8');os.replace(tmp,p)
    except Exception:pass

def _voyager_ship_combat_view(base:Path,state:Optional[dict]=None)->dict:
    state=state if isinstance(state,dict) else read_json(base/'state.json')
    source_hash=_derived_voyager_ship_combat_source_hash(state);key='voyager_ship_combat_power'
    value=_derived_view_cache_read(base,key,source_hash)
    cache_hit=value is not None
    if value is None:
        value=_build_voyager_ship_combat_derived(state);_derived_view_cache_write(base,key,source_hash,value)
    return {'schema':DERIVED_RUNTIME_SCHEMA,'view_id':key,'authority':'derived_from_state','source_paths':['STATE.voyager_fleet.vessel_roster','STATE.voyager_fleet.class_counts','STATE.voyager_fleet.class_combat_power_snapshot'],'source_sha256':source_hash,'cache_hit':cache_hit,'value':value}

def _derived_runtime_status(base:Path,state:Optional[dict]=None)->dict:
    state=state if isinstance(state,dict) else read_json(base/'state.json')
    rows=[]
    try:
        v=_voyager_ship_combat_view(base,state);val=v.get('value') or {}
        rows.append({'view_id':v.get('view_id'),'status':'PASS','source_sha256':v.get('source_sha256'),'cache_hit':v.get('cache_hit'),'row_count':len(val.get('ships') or {}),'bytes':len(json.dumps(val,ensure_ascii=False,separators=(',',':')).encode('utf-8'))})
    except Exception as ex:rows.append({'view_id':'voyager_ship_combat_power','status':'FAIL','error':str(ex)})
    return {'schema':DERIVED_RUNTIME_SCHEMA,'status':'PASS' if all(x.get('status')=='PASS' for x in rows) else 'FAIL','views':rows}

QUERY_INTENT_REGISTRY_SCHEMA='QUERY_INTENT_REGISTRY_V3'

def _intent_task_row(task:dict)->dict:
    mon=((task.get('runtime_policy') or {}).get('monitor') or {})
    return {'task_id':task.get('task_id') or task.get('id'),'title':task.get('title'),'phase':task.get('phase'),'priority':task.get('priority'),'mode':mon.get('mode'),'next_review_at':mon.get('next_review_at'),'resolver':mon.get('resolver'),'requires_ai_review':bool(mon.get('requires_ai_review'))}

def _intent_fleet_status(state:dict,fleet:str)->dict:
    # Intent views are deliberately bounded by schema rather than by byte truncation.
    # A QUERY_INTENT_V2 result marked COMPLETE must never hide nested truncation markers.
    core=_mobile_fleet_core(state).get(fleet) or {};loc=_cold_fleet_location_summary(state).get(fleet) or {}
    out={'fleet':fleet,'display_name':core.get('display_name'),'ships':core.get('ships'),'personnel':core.get('personnel'),'location':copy.deepcopy(loc)}
    if fleet=='shadow':
        sf=state.get('shadow_fleet') or {};out['qrf']=copy.deepcopy(sf.get('quick_reaction_force_current') or {});out['homeport']=((sf.get('current_location') or {}).get('homeport'))
    elif fleet=='jinchuan':
        jf=state.get('jinchuan_fleet') or {};out['latest_settlement']=copy.deepcopy(jf.get('latest_daily_financial_settlement') or {})
    return out

def _intent_inventory_overview(state:dict,fleet:Optional[str]=None)->dict:
    # These are already compact canonical/current inventory authorities.  Return them whole;
    # broad historical ledgers remain available through ordinary query/evidence routing.
    inv=state.get('inventories') or {};core=_mobile_fleet_core(state);out={'scope':fleet or 'all','authority':'derived_from_canonical_state'}
    supplies=((inv.get('supply_inventory') or {}).get('fleets') or {})
    if fleet in (None,'voyager'):
        out['voyager']={'ships':(core.get('voyager') or {}).get('ships'),'personnel':(core.get('voyager') or {}).get('personnel'),'weapon_inventory':copy.deepcopy(inv.get('current_voyager_weapon_inventory_net') or {}),'supply_inventory':copy.deepcopy(supplies.get('voyager') or {})}
    if fleet in (None,'jinchuan'):
        out['jinchuan']={'ships':(core.get('jinchuan') or {}).get('ships'),'personnel':(core.get('jinchuan') or {}).get('personnel'),'supply_inventory':copy.deepcopy(supplies.get('jinchuan') or {})}
    if fleet in (None,'shadow'):
        sf=state.get('shadow_fleet') or {};out['shadow']={'ships':(core.get('shadow') or {}).get('ships'),'personnel':(core.get('shadow') or {}).get('personnel'),'public_inventory':copy.deepcopy(sf.get('public_inventory_current') or {}),'external_armory':copy.deepcopy(sf.get('external_weapon_inventory_current') or {})}
    return out

def _v1403_previous__query_intent_key(topic:str)->tuple[Optional[str],Optional[str]]:
    q=_normalize_search_text(topic)
    explicit=re.search(r'intent:([a-z_]+)(?::([a-z_]+))?',q,re.I)
    if explicit:return explicit.group(1).lower(),(explicit.group(2).lower() if explicit.group(2) else None)
    fleet=None
    if '远航者' in q:fleet='voyager'
    elif '金川' in q:fleet='jinchuan'
    elif '暗影' in q:fleet='shadow'
    if any(x in q for x in ['当前任务','活动任务','执行任务','任务列表']):return 'active_tasks',None
    if any(x in q for x in ['待执行任务','排队任务','queuedtask']):return 'queued_tasks',None
    if any(x in q for x in ['下一确定事件','下一确定性事件','下一个确定性节点','下一机械事件','nextevent']):return 'next_event',None
    if any(x in q for x in ['待履行事项','持续事项','承诺事项','观察事项','合规事项']):return 'obligations',None
    if any(x in q for x in ['决策门','待决事项','需要我决定']):return 'decision_gates',None
    if fleet and any(x in q for x in ['当前状态','舰队状态','状态概览']):return 'fleet_status',fleet
    if fleet and any(x in q for x in ['当前位置','舰队位置','位置']):return 'fleet_location',fleet
    if any(x in q for x in ['库存概览','当前库存','库存总览']):return 'inventory',fleet
    if any(x in q for x in ['资金概览','当前资金','资金余额','金币和灰币']):return 'finance',None
    if any(x in q for x in ['舰队核心','三舰队核心']):return 'core',None
    if '远航者' in q and any(x in q for x in ['逐舰战力','舰战明细','逐舰舰战','单舰战力']):return 'voyager_ship_combat',None
    return None,None


def _intent_required_missing(intent:str,arg:Optional[str],value:Any)->List[str]:
    if value is None:return ['value']
    def has(path:str)->bool:
        cur=value
        for k in path.split('.'):
            if not isinstance(cur,dict) or k not in cur:return False
            cur=cur[k]
        return cur is not None
    req=[]
    if intent=='fleet_location':
        req={'voyager':['as_of','base.ships','deployments','transit.ships'],'jinchuan':['as_of','commercial_guard_sites','development_groups','status'],'shadow':['as_of','homeport','base.ships','deployments']} .get(arg or '',[])
    elif intent in {'active_tasks','queued_tasks','decision_gates','obligations'}:
        return [] if isinstance(value,list) else ['value:list']
    elif intent=='finance':req=['gold','grey']
    elif intent=='core':req=['fleet_core','locations']
    elif intent=='fleet_status':req=['fleet','display_name','ships','personnel','location']
    return [p for p in req if not has(p)]

def _v130_layer_query_intent_packet_01(base:Path,topic:str)->Optional[dict]:
    intent,arg=_query_intent_key(topic)
    if not intent:return None
    ready=ensure_source_ready(base);state=read_json_view(base/'state.json');tasks=read_json_view(base/'tasks.json');now=parse_iso(state.get('game_time'))
    value=None
    if intent=='core':value={'fleet_core':_mobile_fleet_core(state),'locations':_cold_fleet_location_summary(state)}
    elif intent=='finance':value=copy.deepcopy((state.get('summary') or {}).get('funds') or {})
    elif intent=='active_tasks':value=[_intent_task_row(t) for t in (tasks.get('active_tasks') or []) if isinstance(t,dict)]
    elif intent=='queued_tasks':value=[_intent_task_row(t) for t in (tasks.get('queued_tasks') or []) if isinstance(t,dict)]
    elif intent=='next_event':
        until=(now+dt.timedelta(days=3650)).strftime('%Y-%m-%dT%H:%M:%S') if now else state.get('game_time');plan=routineplan_packet(base,until);ev=(plan.get('deterministic_events') or []);value=ev[0] if ev else None
    elif intent=='decision_gates':value=_cold_start_review_surfaces(state,tasks,now)[1]
    elif intent=='obligations':value=_active_obligation_rows(tasks,state)
    elif intent=='fleet_status':value=_intent_fleet_status(state,arg or '')
    elif intent=='fleet_location':value=_cold_fleet_location_summary(state).get(arg or '')
    elif intent=='inventory':value=_intent_inventory_overview(state,arg)
    elif intent=='voyager_ship_combat':value=_voyager_ship_combat_view(base,state)
    else:return None
    value=copy.deepcopy(value)
    missing=_intent_required_missing(intent,arg,value);status='NOT_FOUND' if value is None else ('PARTIAL' if missing else 'COMPLETE')
    return {'packet':'QUERY_INTENT_V3','registry':QUERY_INTENT_REGISTRY_SCHEMA,'engine_version':ENGINE_VERSION,'save_set_id':ready.get('save_set_id'),'game_time':state.get('game_time'),'topic':topic,'intent':intent,'argument':arg,'status':status,'required_fields_ok':not missing,'missing_fields':missing,'value':value,'truncated':False}

def _v1403_previous_query_packet(base:Path,topic:str,history_limit:int=5,task_limit:int=5,detail:str="compact")->dict:
    intent=query_intent_packet(base,topic)
    if intent:return intent
    ent=_exact_entity_registry_query(base,topic)
    if ent:return ent
    ex=_exact_query(base,topic)
    if ex:return ex
    if detail=='exact':return {'packet':'EXACT_QUERY_V1','engine_version':ENGINE_VERSION,'topic':topic,'status':'NO_EXACT_ALIAS'}
    out=_query_packet_legacy(base,topic,history_limit=min(history_limit,2) if detail=='compact' else history_limit,task_limit=min(task_limit,3) if detail=='compact' else task_limit,detail='full' if detail=='full' else 'compact')
    out['save_set_id']=(out.get('source_ready') or {}).get('save_set_id')
    inherited_truncation=bool(out.get('truncated')) or _query_has_truncated_evidence({k:out.get(k) for k in ('tasks','resolved_state_paths','state_hits','world_rule_sections','world_rule_meta','world_keyword_context','recent_relevant_events')})
    if inherited_truncation:
        out['truncated']=True
        if out.get('status')=='COMPLETE':out['status']='TRUNCATED'
    if detail!='compact':return out
    clipped=[]
    def bounded(v,limit,where):
        raw=json.dumps(v,ensure_ascii=False,separators=(',',':'))
        if len(raw)<=limit:return v
        clipped.append(where)
        return {'excerpt':raw[:limit],'truncated':True,'total_chars':len(raw),'expand':where}
    state={p:bounded(v,650,'STATE:'+p) for p,v in list((out.get('resolved_state_paths') or {}).items())[:4]}
    if len(out.get('resolved_state_paths') or {})>4:clipped.append('query --detail context')
    rules={p:bounded(v,2400,'WORLD:'+p) for p,v in list((out.get('world_rule_sections') or {}).items())[:2]}
    if len(out.get('world_rule_sections') or {})>2:clipped.append('query --detail context')
    hits=(out.get('state_hits') or [])[:2]
    if len(out.get('state_hits') or [])>2:clipped.append('query --detail context')
    row={'packet':'COMPACT_QUERY_V3','engine_version':ENGINE_VERSION,'topic':topic,'save_set_id':out.get('save_set_id'),'game_time':out.get('game_time'),'status':out.get('status'),'tasks':[bounded(t,700,'TASKS:'+str(t.get('task_id'))) for t in (out.get('tasks') or [])[:3]],'state':state,'state_hits':hits,'world_rules':rules,'world_rule_meta':out.get('world_rule_meta') or {},'history':[{k:h.get(k) for k in ('seq','event_id','game_time','type','summary') if h.get(k) is not None} for h in (out.get('recent_relevant_events') or [])[:2]],'unresolved':out.get('unresolved') or [],'truncated':bool(clipped or out.get('truncated')),'expansion_targets':clipped}
    if not rules:row['world_keyword_context']=[bounded(v,900,'query --detail context') for v in (out.get('world_keyword_context') or [])[:1]]
    if clipped and row['status'] not in ('NOT_FOUND','PARTIAL'):row['status']='TRUNCATED'
    # Legacy compact sources may themselves contain bounded excerpts.
    if clipped or inherited_truncation or _query_has_truncated_evidence(row):
        row['truncated']=True
        if row['status']=='COMPLETE':row['status']='TRUNCATED'
    row['expansion']='Use evidence --source STATE|WORLD --path <path-or-rule-id> with offset paging; context for task details. Do not infer omitted facts.'
    return row


def _legacy_finance_event_candidate(e:dict)->bool:
    """Return True for a pre-structured-ledger event that may change funds.

    This deliberately errs on the side of marking historical finance coverage
    partial instead of presenting a false zero. It never invents an amount.
    """
    if not isinstance(e,dict) or e.get("finance") is not None:return False
    changes=e.get("changes") or []
    if isinstance(changes,list):
        for c in changes:
            if not isinstance(c,dict):continue
            target=str(c.get("target") or "").lower()
            if "state.summary.funds" in target or target.endswith(".funds") or ".funds." in target:return True
    typ=str(e.get("type") or "").lower()
    finance_type_terms=("economic","settlement","market_sale","sale","purchase","procurement","trade","revenue","income","expense","acquisition")
    return any(k in typ for k in finance_type_terms)


def reportframe_packet(base:Path, since:Optional[str]=None,since_seq:Optional[int]=None)->dict:
    ready=ensure_source_ready(base);state=read_json(base/"state.json");tasks=read_json(base/"tasks.json");events,history_summary=_stage2_report_history(base,since or state.get("last_report_game_time") or state.get("game_time"),since_seq)
    if since_seq is not None and (isinstance(since_seq,bool) or since_seq<0 or since_seq>history_summary['through_seq']):raise EngineError('REPORT_CURSOR_INVALID')
    start=since or state.get("last_report_game_time") or state.get("game_time");sdt=parse_iso(start);edt=parse_iso(state.get("game_time"));entries=[];gold=0.0;grey=0.0;by_fleet={};by_account={};random_events=[];legacy_unstructured=[]
    structured_times=[]
    for e in events:
        if e.get("finance") is not None:
            et0=parse_iso(e.get("game_time"))
            if et0 is not None:structured_times.append(et0)
        et=parse_iso(e.get("game_time"))
        if et is None or (edt and et>edt):continue
        if since_seq is not None:
            if int(e.get('seq') or 0)<=since_seq:continue
        elif sdt and et<=sdt:continue
        fin=e.get("finance")
        if fin is not None:
            items=fin if isinstance(fin,list) else [fin]
            for x in items:
                if not isinstance(x,dict):continue
                g=float(x.get("gold",0) or 0);r=float(x.get("grey",0) or 0);fleet=str(x.get("fleet") or "global");account=str(x.get("account") or "unspecified")
                gold+=g;grey+=r;by_fleet.setdefault(fleet,{"gold":0.0,"grey":0.0});by_fleet[fleet]["gold"]+=g;by_fleet[fleet]["grey"]+=r;by_account.setdefault(account,{"gold":0.0,"grey":0.0});by_account[account]["gold"]+=g;by_account[account]["grey"]+=r
                entries.append({"event_id":e.get("event_id"),"game_time":e.get("game_time"),"account":account,"fleet":fleet,"gold":g,"grey":r,"summary":e.get("summary")})
        elif _legacy_finance_event_candidate(e):
            legacy_unstructured.append({"event_id":e.get("event_id"),"game_time":e.get("game_time"),"type":e.get("type"),"summary":e.get("summary")})
        typ=str(e.get("type") or "").lower()
        if "hazard" in typ or "random" in typ or e.get("random_event") is True:random_events.append({"event_id":e.get("event_id"),"game_time":e.get("game_time"),"type":e.get("type"),"summary":e.get("summary")})
    sm=state.get("summary") or {}
    core={"voyager":{"ships":((sm.get("ships") or {}).get("voyager")),"personnel":((sm.get("personnel") or {}).get("voyager"))},"jinchuan":{"ships":((sm.get("ships") or {}).get("jinchuan")),"personnel":((sm.get("personnel") or {}).get("jinchuan"))},"shadow":{"ships":((sm.get("ships") or {}).get("shadow_active")),"personnel":((sm.get("personnel") or {}).get("shadow"))},"gold":((sm.get("funds") or {}).get("gold")),"grey":((sm.get("funds") or {}).get("grey"))}
    core=_mobile_fleet_core(state)
    coverage_status="PARTIAL_LEGACY_UNSTRUCTURED" if legacy_unstructured else "COMPLETE"
    structured_start=history_summary["structured_start"]
    finance={
        "coverage_status":coverage_status,
        "gold_delta":gold if not legacy_unstructured else None,
        "grey_delta":grey if not legacy_unstructured else None,
        "structured_gold_subtotal":gold,
        "structured_grey_subtotal":grey,
        "by_fleet":by_fleet,
        "by_account":by_account,
        "entries":entries,
        "structured_coverage":"V7+ history finance ledger",
        "structured_coverage_start":structured_start,
        "legacy_unstructured_event_count":len(legacy_unstructured),
        "legacy_unstructured_events":legacy_unstructured[:24],
    }
    if legacy_unstructured:
        finance["warning"]="Requested interval contains pre-structured-ledger finance events. gold_delta/grey_delta are intentionally null; structured_*_subtotal includes only events with explicit finance records. Use listed legacy event evidence for historical reconstruction instead of treating missing amounts as zero."
    gross={}
    for item in entries:
        row=gross.setdefault(item['fleet'],{k:{'income':0.0,'expense':0.0,'net':0.0} for k in ('gold','grey')})
        for k in ('gold','grey'):
            amount=item[k];side='income' if amount>=0 else 'expense'
            row[k][side]=_money_add4(row[k][side],abs(amount));row[k]['net']=_money_add4(row[k]['net'],amount)
    finance['by_fleet_gross']=gross
    cursor={'schema':'HISTORY_SEQ_CURSOR_V1','save_set_id':ready.get('save_set_id'),'since_seq':since_seq,'through_seq':history_summary['through_seq'],'same_time_events_covered':since_seq is not None}
    return {"engine_version":ENGINE_VERSION,"packet":"REPORT_FRAME_V2","event_cursor":cursor,"random_check":{"time_advanced":bool(sdt and edt and edt>sdt),'status':'NO_NEW_CHECK_ZERO_TIME' if sdt==edt else ('EVENTS_RECORDED' if random_events else 'NO_RECORDED_RANDOM_EVENT'),'note':'Only a validated committed turn authorizes a no-event assertion for an advanced interval; queries do not roll randomness.'},"status":"READY_WITH_PARTIAL_FINANCE" if legacy_unstructured else "READY","source_ready":ready,"header":{"game_time":state.get("game_time"),"voyage_day":state.get("voyage_day"),"since":start},"fleet_core":core,"finance":finance,"random_events":random_events,"active_task_count":len(tasks.get("active_tasks") or []),"queued_task_count":len(tasks.get("queued_tasks") or []),"format_rule":"WORLD:RULE-PROGRESS-REPORT-FLEET-01"}

def _combat_runtime_rules(base:Path)->dict:
    rules=load_runtime_rules(base);cfg=rules.get("combat_evaluation") if isinstance(rules,dict) else None
    if not isinstance(cfg,dict):raise EngineError("COMBAT_RULES_MISSING_IN_WORLD")
    return cfg


def _finite_num(v:Any,name:str,minimum:Optional[float]=None,maximum:Optional[float]=None)->float:
    if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(float(v)):raise EngineError(f"COMBAT_{name}_NUMERIC_REQUIRED")
    x=float(v)
    if minimum is not None and x<minimum:raise EngineError(f"COMBAT_{name}_BELOW_MIN")
    if maximum is not None and x>maximum:raise EngineError(f"COMBAT_{name}_ABOVE_MAX")
    return x


def _factor(v:Any,name:str="FACTOR")->float:return _finite_num(v,name,0.0)


def _age_linear(age:float,grace:float,decline:float,floor:float)->float:
    return max(float(floor),1.0-float(decline)*max(0.0,float(age)-float(grace)))


def _combat_cache(base:Path,kind:str,payload:dict,result:dict)->None:
    if base.resolve()!=ROOT.resolve():return
    try:
        d=ROOT/".runtime";d.mkdir(parents=True,exist_ok=True);p=d/"combat_cache_v1.json"
        key=hashlib.sha256(json.dumps({"kind":kind,"payload":payload},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        obj={"format":"VOYAGER_COMBAT_CACHE_V1","engine_version":ENGINE_VERSION,"world_sha256":_authority_world_sha256(base),"state_sha256":sha256_file(base/"state.json"),"key":key,"kind":kind,"result":result}
        tmp=p.with_name(f".{p.name}.{os.getpid()}.tmp");tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");os.replace(tmp,p)
    except Exception:pass


def _validate_combat_runtime_config(cfg:Any)->List[str]:
    errors=[]
    if not isinstance(cfg,dict):return ["WORLD combat_evaluation runtime block invalid"]
    try:
        for ck in ["ship","ground","air_ground"]:
            if not isinstance(cfg.get(ck),dict):errors.append(f"WORLD combat_evaluation.{ck} invalid")
        sc=cfg.get("ship") or {};gc=cfg.get("ground") or {};ac=cfg.get("air_ground") or {}
        sf=sc.get("source_factors") or {}
        if set(sf)!={"self","external_top","external_regular"}:errors.append("WORLD combat source_factors invalid")
        else:
            for k,v in sf.items():_finite_num(v,f"CFG_SOURCE_{k}",0,1)
            if abs(float(sf.get("self",0))-1.0)>1e-12:errors.append("WORLD combat self source factor must equal 1.0")
        if set(sc.get("hull_type_factors") or {})!={"warship","military","civilian"}:errors.append("WORLD combat hull_type_factors invalid")
        else:
            for k,v in (sc.get("hull_type_factors") or {}).items():_finite_num(v,f"CFG_HULL_{k}",0,1)
        for name,block in [("hull_age",sc.get("hull_age") or {}),("weapon_age",sc.get("weapon_age") or {}),("shield_age",sc.get("shield_age") or {})]:
            _finite_num(block.get("grace_years"),f"CFG_{name}_GRACE",0);_finite_num(block.get("decline_per_year"),f"CFG_{name}_DECLINE",0);_finite_num(block.get("floor"),f"CFG_{name}_FLOOR",0,1)
        for name,block in [("weapon_age",sc.get("weapon_age") or {}),("shield_age",sc.get("shield_age") or {})]:
            flag=block.get("self_origin_no_age_decay",block.get("self_owned_no_age_decay"))
            if flag is not True:errors.append(f"WORLD combat {name}.self_origin_no_age_decay must be true")
        wpol=sc.get("weapon_condition_policy") or {}
        if wpol.get("age_decay_enabled") is not False or wpol.get("ship_age_fallback_enabled") is not False or wpol.get("status_modifier")!="integrity_only":errors.append("WORLD combat weapon condition policy must disable all age decay and use integrity_only")
        if (sc.get("weapon_age") or {}).get("all_origin_no_age_decay") is not True:errors.append("WORLD combat weapon_age.all_origin_no_age_decay must be true")
        wb=sc.get("weapon_base") or {}
        for typ in ["laser","plasma","electromagnetic"]:
            vals=wb.get(typ) or {}
            if set(vals)!={"small","medium","heavy"}:errors.append(f"WORLD combat weapon_base {typ} invalid")
            else:
                for k,v in vals.items():_finite_num(v,f"CFG_WEAPON_{typ}_{k}",0)
        _finite_num(wb.get("point_defense"),"CFG_POINT_DEFENSE",0);_finite_num(wb.get("missile_cell"),"CFG_MISSILE_CELL",0);_finite_num(wb.get("missile_burst"),"CFG_MISSILE_BURST",0)
        if set(sc.get("shields") or {})!={"light","medium","heavy"}:errors.append("WORLD combat shields invalid")
        else:
            for k,v in (sc.get("shields") or {}).items():_finite_num(v,f"CFG_SHIELD_{k}",0)
        for model,row in (sc.get("specific_models") or {}).items():
            if not isinstance(row,dict):errors.append(f"WORLD combat specific model {model} invalid");continue
            if row.get("class") not in (sc.get("shields") or {}):errors.append(f"WORLD combat specific model {model} class invalid")
            rr=row.get("performance_range")
            if not isinstance(rr,list) or len(rr)!=2:errors.append(f"WORLD combat specific model {model} performance_range invalid")
            else:
                lo=_finite_num(rr[0],f"CFG_MODEL_{model}_LO",0,1);hi=_finite_num(rr[1],f"CFG_MODEL_{model}_HI",0,1)
                if lo>hi:errors.append(f"WORLD combat specific model {model} performance_range reversed")
                d=_finite_num(row.get("default_performance"),f"CFG_MODEL_{model}_DEFAULT",0,1)
                if not lo<=d<=hi:errors.append(f"WORLD combat specific model {model} default outside range")
        if set(gc.get("weapon_coefficients") or {})!={"rifle","shotgun","pistol"}:errors.append("WORLD ground weapon coefficients invalid")
        else:
            for k,v in (gc.get("weapon_coefficients") or {}).items():_finite_num(v,f"CFG_GROUND_WEAPON_{k}",0)
        ge=gc.get("external_equipment_age") or {};_finite_num(ge.get("grace_years",0),"CFG_GROUND_AGE_GRACE",0);_finite_num(ge.get("service_life_years",0),"CFG_GROUND_AGE_LIFE",0);_finite_num(ge.get("decline_per_year",0),"CFG_GROUND_AGE_DECLINE",0);_finite_num(ge.get("overlife_story_performance",1.0),"CFG_GROUND_OVERLIFE",0,1)
        if ge.get("age_decay_enabled") is not False:errors.append("WORLD ground equipment age decay must be disabled")
        if ge.get("retirement_in_combatcalc_enabled") is not False:errors.append("WORLD ground equipment age retirement in combatcalc must be disabled")
        if ge.get("all_origin_no_age_decay") is not True:errors.append("WORLD ground equipment all_origin_no_age_decay must be true")
        ground_self_flag=gc.get("self_origin_equipment_no_age_decay",gc.get("self_owned_equipment_no_age_decay"))
        if ground_self_flag is not True:errors.append("WORLD ground self_origin_equipment_no_age_decay must be true")
        gg=gc.get("grenade") or {};_finite_num(gg.get("self_service_life_years"),"CFG_GRENADE_SELF_LIFE",0);egr=_finite_num(gg.get("external_grace_years"),"CFG_GRENADE_EXT_GRACE",0);elife=_finite_num(gg.get("external_service_life_years"),"CFG_GRENADE_EXT_LIFE",0);_finite_num(gg.get("external_decline_per_year"),"CFG_GRENADE_EXT_DECLINE",0)
        grenade_self_flag=gg.get("self_origin_no_age_decay_before_retirement",gg.get("self_no_age_decay_before_retirement"))
        if grenade_self_flag is not True:errors.append("WORLD grenade self_origin_no_age_decay_before_retirement must be true")
        if elife<egr:errors.append("WORLD grenade external service life shorter than grace")
        for k in ["grenade","rocket","missile"]:_finite_num((gc.get("burst_values") or {}).get(k),f"CFG_BURST_{k}",0)
        models=ac.get("models")
        if not isinstance(models,dict) or not models:errors.append("WORLD air_ground models invalid")
        else:
            for model,row in models.items():
                if not isinstance(row,dict):errors.append(f"WORLD air_ground model {model} invalid");continue
                _finite_num(row.get("a"),f"CFG_AIR_{model}_A",0);_finite_num(row.get("k"),f"CFG_AIR_{model}_K",0)
        for k,v in (ac.get("category_k") or {}).items():_finite_num(v,f"CFG_AIR_CATEGORY_{k}",0)
    except EngineError as exc:errors.append(f"WORLD combat_evaluation numeric validation: {exc}")
    except Exception as exc:errors.append(f"WORLD combat_evaluation validation exception:{exc}")
    return errors


def _strict_bool(v:Any,name:str)->bool:
    if not isinstance(v,bool):raise EngineError(f"COMBAT_{name}_BOOLEAN_REQUIRED")
    return v


def _self_origin(row:dict,key:str="self_origin")->bool:
    if "self_owned" in row:raise EngineError("COMBAT_SELF_OWNED_AMBIGUOUS_USE_SELF_ORIGIN")
    return _strict_bool(row.get(key,False),key.upper()) if key in row else False


def _ground_external_age_factor(age:float,cfg:dict,overlife_story_usable:bool=False)->float:
    """Compatibility helper: equipment age is metadata only and never changes combat performance."""
    _finite_num(age,"GROUND_AGE_METADATA",0)
    return 1.0


def _player_force_row(row:dict, inherited:bool=False)->bool:
    if not isinstance(row,dict):return bool(inherited)
    if "player_force" in row:return _strict_bool(row.get("player_force"),"PLAYER_FORCE")
    return bool(inherited)


def _repair_complete_status(row:dict)->bool:
    """Explicit completed repair/refurbishment state. Historical secondhand condition never counts as current damage after completion."""
    if not isinstance(row,dict):return False
    for k in ("repair_completed","refurbishment_completed","repair_accepted","refurbishment_accepted"):
        if k in row and row.get(k) is True:return True
    vals=[]
    for k in ("repair_status","refurbishment_status","maintenance_status","status"):
        if isinstance(row.get(k),str):vals.append(row.get(k).strip().lower())
    complete_tokens=("completed_100pct","repair_complete","repair_completed","repaired","refurbishment_complete","refurbishment_completed","refurbished_accepted","accepted_available","维修完成","修复完成","翻新完成","验收完成","已修复","已翻新")
    negative_tokens=("in_progress","pending","not_yet","await","维修中","修复中","待维修","未完成")
    for v in vals:
        if any(x in v for x in negative_tokens):continue
        if any(x in v for x in complete_tokens):return True
    return False


def _combat_integrity(row:dict,name:str,player_force:bool=False,default:float=1.0)->Tuple[float,bool]:
    pf=_player_force_row(row,player_force)
    repaired=pf and _repair_complete_status(row)
    if repaired:return 1.0,True
    if "condition_pct" in row:
        q=_finite_num(row.get("condition_pct"),name+"_CONDITION_PCT",0,100)/100.0
        if "integrity" in row:
            qi=_finite_num(row.get("integrity"),name,0,1)
            if abs(q-qi)>1e-9:raise EngineError(f"COMBAT_{name}_CONDITION_INTEGRITY_MISMATCH")
        return q,False
    return _finite_num(row.get("integrity",default),name,0,1),False


def _ground_item_effective(row:dict,cfg:dict,prefix:str="",legacy_key:str="effective",player_force:bool=False)->Tuple[float,dict]:
    structured_keys={"age_years","self_origin","integrity","performance_factor","overlife_story_usable"}
    if legacy_key in row:
        if any(k in row for k in structured_keys):raise EngineError(f"COMBAT_{prefix}MIXED_EFFECTIVE_INPUT_FORBIDDEN")
        if _player_force_row(row,player_force) and _repair_complete_status(row):return 1.0,{"mode":"repair_completed_full","effective":1.0,"integrity":1.0,"repair_completed":True}
        e=_factor(row.get(legacy_key),f"{prefix}EFFECTIVE");return e,{"mode":"direct_effective","effective":e}
    self_origin=_self_origin(row);age=_finite_num(row.get("age_years",0),f"{prefix}AGE_METADATA",0);integrity,repaired=_combat_integrity(row,f"{prefix}INTEGRITY",player_force);perf=_factor(row.get("performance_factor",1.0),f"{prefix}PERFORMANCE_FACTOR")
    over=_strict_bool(row.get("overlife_story_usable",False),f"{prefix}OVERLIFE_STORY_USABLE") if "overlife_story_usable" in row else False
    pf=_player_force_row(row,player_force);af=1.0
    e=perf*integrity
    return e,{"mode":"structured","self_origin":self_origin,"player_force":pf,"repair_completed":repaired,"age_years":age,"age_factor":af,"age_decay_disabled":True,"performance_factor":perf,"integrity":integrity,"effective":e,"overlife_story_usable":over}


def _weapon_integrity_effective(row:dict,prefix:str="WEAPON_",player_force:bool=False)->Tuple[float,dict]:
    """Weapon combat-state modifier: integrity only. Age/service time are metadata, never combat decay."""
    if not isinstance(row,dict):raise EngineError(f"COMBAT_{prefix}OBJECT_REQUIRED")
    if "effective" in row:
        if any(k in row for k in ["integrity","age_years","performance_factor","self_origin","overlife_story_usable"]):raise EngineError(f"COMBAT_{prefix}MIXED_EFFECTIVE_INPUT_FORBIDDEN")
        if _player_force_row(row,player_force) and _repair_complete_status(row):q=1.0;return q,{"mode":"repair_completed_full","integrity":q,"effective":q,"age_factor":1.0,"age_decay_disabled":True,"repair_completed":True}
        q=_finite_num(row.get("effective"),f"{prefix}INTEGRITY",0,1)
        return q,{"mode":"direct_integrity","integrity":q,"effective":q,"age_factor":1.0,"age_decay_disabled":True}
    q,repaired=_combat_integrity(row,f"{prefix}INTEGRITY",player_force)
    age=None
    if "age_years" in row:age=_finite_num(row.get("age_years"),f"{prefix}AGE_METADATA",0)
    if "performance_factor" in row and abs(_factor(row.get("performance_factor"),f"{prefix}PERFORMANCE_FACTOR")-1.0)>1e-12:
        raise EngineError(f"COMBAT_{prefix}PERFORMANCE_FACTOR_FORBIDDEN_IN_STATUS_USE_MODEL_OR_SOURCE_FACTOR")
    return q,{"mode":"structured","integrity":q,"effective":q,"age_years":age,"age_factor":1.0,"age_decay_disabled":True,"player_force":_player_force_row(row,player_force),"repair_completed":repaired,"secondhand_discount_applied":False}


def _grenade_effective(row:dict,cfg:dict,player_force:bool=False)->Tuple[float,dict]:
    return _weapon_integrity_effective(row,"GRENADE_",player_force)


