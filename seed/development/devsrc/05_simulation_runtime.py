# === VOYAGER_DEV_MODULE: simulation_runtime ===
def _mechanical_multi_event_limit(runtime_rules: dict, default: int = 64) -> int:
    """Return the WORLD-configured per-advance mechanical Hazard safety cap.

    This is a safety cap, not a per-day event limit. Keep it bounded so malformed WORLD
    data cannot allocate an unbounded event batch.
    """
    rf=(runtime_rules.get("random_event_framework") or {}) if isinstance(runtime_rules,dict) else {}
    raw=rf.get("mechanical_multi_event_limit_per_advance",default)
    try: n=int(raw)
    except Exception: n=int(default)
    return max(1,min(n,4096))


_POLITICAL_HAZARD_ENTITY_COUNTS={
    "major_nation_significant_instability":3,
    "medium_nation_significant_instability":7,
    "small_nation_significant_instability":123,
}

def _political_hazard_excluded_entities(state:dict,family:str)->set:
    """Read the persistent crisis-chain exclusion list for one political Hazard family."""
    clocks=((((state.get("engine_runtime") or {}).get("long_horizon") or {}).get("hazard_clocks") or {}))
    out=set()
    for c in clocks.values():
        if not isinstance(c,dict) or str(c.get("profile_id") or "")!=str(family):continue
        basis=c.get("risk_multiplier_basis") or {}
        vals=basis.get("excluded_active_crisis_entities") or []
        if isinstance(vals,list):out.update(str(x) for x in vals if isinstance(x,str) and x.strip())
    return out

def _apply_mechanical_political_hazard_state(state:dict,event:dict)->list:
    """Persist auto-materialized political shocks as current world facts and exclusion state.

    A nation already in a crisis/transition chain must not be independently re-selected by
    the same Hazard family until an explicit later resolution removes that exclusion.
    """
    family=str(event.get("family") or "")
    if family not in _POLITICAL_HAZARD_ENTITY_COUNTS:return []
    payload=event.get("mechanical_payload") or {}; entity=payload.get("affected_entity")
    if not isinstance(entity,str) or not entity.strip():return []
    gt=str(event.get("time") or state.get("game_time") or "")
    ws=state.setdefault("world_state_overrides",{}).setdefault("organizations_and_politics",{})
    dyn=ws.setdefault("nation_dynamics",{})
    if not isinstance(dyn,dict):raise EngineError("POLITICAL_NATION_DYNAMICS_NOT_OBJECT")
    rec=dyn.setdefault(entity,{})
    if not isinstance(rec,dict):raise EngineError(f"POLITICAL_NATION_RECORD_NOT_OBJECT:{entity}")
    tier={
        "major_nation_significant_instability":"major_nation",
        "medium_nation_significant_instability":"medium_nation",
        "small_nation_significant_instability":"small_nation",
    }[family]
    rec.setdefault("tier",tier)
    rec["latest_random_political_event"]={
        "event_id":str(event.get("event_id") or ""),
        "game_time":gt,
        "family":family,
        "template_id":event.get("template_id"),
        "event":payload.get("event"),
        "trigger":payload.get("trigger"),
        "immediate_outcome":payload.get("immediate_outcome"),
        "status":"active_crisis_or_transition_chain",
        "source":"mechanical_hazard_v3",
    }
    clocks=((((state.get("engine_runtime") or {}).get("long_horizon") or {}).get("hazard_clocks") or {}))
    for c in clocks.values():
        if not isinstance(c,dict) or str(c.get("profile_id") or "")!=family:continue
        basis=c.setdefault("risk_multiplier_basis",{})
        if not isinstance(basis,dict):raise EngineError(f"POLITICAL_RISK_BASIS_NOT_OBJECT:{family}")
        excluded=basis.get("excluded_active_crisis_entities") or []
        if not isinstance(excluded,list):excluded=[]
        excluded=[str(x) for x in excluded if isinstance(x,str) and x.strip()]
        if entity not in excluded:excluded.append(entity)
        # Stable order keeps SAVESET diffs deterministic.
        excluded=sorted(set(excluded))
        baseline=int(basis.get("baseline_entity_count") or _POLITICAL_HAZARD_ENTITY_COUNTS[family])
        baseline=max(1,baseline); eligible=max(0,baseline-len(excluded))
        basis.update({
            "baseline_entity_count":baseline,
            "excluded_active_crisis_entities":excluded,
            "eligible_entity_count":eligible,
            "rule_id":"RULE-NATION-DYNAMIC-01",
            "last_exclusion_update":gt,
            "no_retroactive_replay":True,
        })
        c["risk_multiplier"]=eligible/baseline
    return [
        {"target":"STATE.world_state_overrides.organizations_and_politics.nation_dynamics","action":"persist_mechanical_political_crisis_chain"},
        {"target":"STATE.engine_runtime.long_horizon.hazard_clocks","action":"exclude_active_political_crisis_entity_from_repeat_start"},
    ]


def _hazard_cycle_history_coverage_errors(parent_state:dict,current_state:dict,new_events:list,world_text:str,runtime_rules:Optional[dict]=None)->list:
    """Hard-check that every newly consumed Hazard cycle has its exact event_id in new HISTORY.

    Historical pre-V3 gaps are not retroactively rejected; this only compares parent->child.
    """
    try: rules=runtime_rules if isinstance(runtime_rules,dict) else parse_world_runtime_rules(world_text)
    except Exception:return ["runtime_rules_unreadable"]
    rf=(rules.get("random_event_framework") or {}) if isinstance(rules,dict) else {}
    if rf.get("history_event_per_hazard_cycle_required") is not True:return []
    pc=((((parent_state.get("engine_runtime") or {}).get("long_horizon") or {}).get("hazard_clocks") or {}))
    cc=((((current_state.get("engine_runtime") or {}).get("long_horizon") or {}).get("hazard_clocks") or {}))
    ids=[str(e.get("event_id") or "") for e in (new_events or []) if isinstance(e,dict)]
    idset=set(ids); errs=[]
    for cid,p in pc.items():
        if not isinstance(p,dict):continue
        c=cc.get(cid)
        if not isinstance(c,dict):continue
        pcy=int(p.get("cycle",0) or 0); ccy=int(c.get("cycle",0) or 0)
        if ccy<pcy:
            errs.append(f"cycle_regression:{cid}:{pcy}->{ccy}");continue
        for cyc in range(pcy,ccy):
            eid=f"HZ-{cid}-{cyc}"
            if eid not in idset:errs.append(f"missing_history_event:{eid}")
            else:
                matches=[e for e in (new_events or []) if isinstance(e,dict) and str(e.get("event_id") or "")==eid]
                if len(matches)!=1:errs.append(f"history_event_count:{eid}:{len(matches)}")
                elif not (matches[0].get("random_event") is True or str(matches[0].get("type") or "").startswith("random_event")):
                    errs.append(f"history_event_not_marked_random:{eid}")
    return errs


def _random_event_framework_v3_runtime_rules() -> dict:
    return _registered_random_data()


def _expand_random_event_payload(payload:dict, state:dict, event:dict, runtime_rules:dict)->dict:
    """Resolve data-only choice/range fields into a stable complete mechanical payload."""
    out=copy.deepcopy(payload or {})
    seed=str(((state.get('engine_runtime') or {}).get('seed_anchor') or ''))
    eid=str(event.get('event_id') or '')
    choices=out.pop('choice_fields',None)
    if isinstance(choices,dict):
        for field,options in choices.items():
            if not isinstance(options,list) or not options:continue
            opts=list(options)
            if str(field)=='affected_entity' and str(event.get('family') or '') in _POLITICAL_HAZARD_ENTITY_COUNTS:
                excluded=_political_hazard_excluded_entities(state,str(event.get('family') or ''))
                filtered=[x for x in opts if str(x) not in excluded]
                if filtered:opts=filtered
            u=deterministic_unit(seed,'hazard_payload_choice',eid,str(field))
            idx=min(len(opts)-1,int(u*len(opts)))
            out[str(field)]=copy.deepcopy(opts[idx])
    # Numeric audit slot for annual small-nation model. It does not instantiate a new named country.
    rng=out.pop('small_nation_registry_index_range',None)
    if isinstance(rng,list) and len(rng)==2 and all(isinstance(x,int) for x in rng):
        lo,hi=sorted(rng);u=deterministic_unit(seed,'hazard_small_nation_slot',eid)
        out['small_nation_registry_index']=lo+min(hi-lo,int(u*(hi-lo+1)))
    # Actor pairs must not silently collapse to the same named state when a row uses the same pool twice.
    if out.get('actor_a') is not None and out.get('actor_b')==out.get('actor_a'):
        pools=(payload or {}).get('choice_fields') or {};opts=pools.get('actor_b') if isinstance(pools,dict) else None
        if isinstance(opts,list) and len(opts)>1:
            i=opts.index(out['actor_b']) if out['actor_b'] in opts else 0
            out['actor_b']=copy.deepcopy(opts[(i+1)%len(opts)])
    # Piracy/crime contacts automatically perform the sealed sensor-initiative baseline gate.
    klass=out.pop('contact_target_class',None)
    if klass:
        cfg=((runtime_rules.get('random_event_framework') or {}).get('contact_sensor_initiative') or {}) if isinstance(runtime_rules,dict) else {}
        out['sensor_initiative']=contact_sensor_initiative_gate(seed,eid,str(klass),cfg)
    return out

def _materialize_hazard_event(event:dict,state:dict,runtime_rules:dict)->dict:
    """Turn a triggered family into a deterministic table row when WORLD permits it."""
    ev=copy.deepcopy(event);tables=(runtime_rules.get('random_event_tables') or {}) if isinstance(runtime_rules,dict) else {};table=tables.get(str(ev.get('family') or ''))
    if not isinstance(table,dict):return ev
    rows=table.get('rows') or []
    if not isinstance(rows,list) or not rows:return ev
    valid=[];total=0
    for row in rows:
        if not isinstance(row,dict):continue
        w=int(row.get('weight',1) or 1)
        if w<=0:continue
        total+=w;valid.append((total,row))
    if not valid:return ev
    seed=str(((state.get('engine_runtime') or {}).get('seed_anchor') or ''));u=deterministic_unit(seed,'hazard_table',str(ev.get('event_id') or ''),str(ev.get('family') or ''));pick=max(1,min(total,int(u*total)+1));row=next(r for cutoff,r in valid if pick<=cutoff)
    mode=str(row.get('mode') or table.get('mode') or 'semantic');ev['table_id']=str(table.get('table_id') or f"{ev.get('family')}_table");ev['template_id']=row.get('id');ev['mechanical_payload']=_expand_random_event_payload(copy.deepcopy(row.get('payload') or {}),state,ev,runtime_rules);ev['requires_simulation']=mode!='mechanical';ev['materialization_mode']=mode
    if mode=='mechanical': ev['mechanical_payload']['generated_without_ai_semantic_dependency']=True
    ev['note']='Engine table-materialized complete random event; no AI semantic generation required.' if mode=='mechanical' else 'Engine selected a deterministic event template; AI resolves only the semantic fields declared by WORLD.'
    return ev

def next_long_horizon_candidates(state: dict, runtime_rules: dict) -> List[dict]:
    """Return one exact, integer-second next trigger for each persistent clock."""
    er=state.get("engine_runtime") or {};lh=er.get("long_horizon") or {};clocks=lh.get("hazard_clocks") or {}
    profiles=(runtime_rules.get("hazard_profiles") or {}) if isinstance(runtime_rules,dict) else {};seed=str(er.get("seed_anchor") or "")
    now=parse_iso(state.get("game_time"));out=[]
    if not now or not seed:return out
    for clock_id,c in clocks.items():
        if not isinstance(c,dict):continue
        profile_id=str(c.get("profile_id") or "");profile=profiles.get(profile_id) or {}
        if not profile:continue
        cycle=int(c.get("cycle",0));cum=_clock_exposure_numerator(c);mult=float(c.get("risk_multiplier",1.0))
        rate_scaled=_effective_rate_scaled(profile,seed,clock_id,cycle,mult)
        if rate_scaled<=0:continue
        start=max(now,parse_iso(c.get("last_evaluated")) or now)
        cooldown=parse_iso(c.get("cooldown_until"))
        if cooldown and cooldown>start:start=cooldown
        threshold=_threshold_numerator(seed,clock_id,cycle);remain=max(0,threshold-cum)
        seconds_needed=0 if remain<=0 else (remain+rate_scaled-1)//rate_scaled
        # A valid very-low hazard rate can place the next trigger beyond Python's
        # representable datetime horizon (year 9999). Such an event is not reachable
        # by any valid game-time commit, so omit it from the actionable candidate list
        # instead of crashing query/turn/process with OverflowError.
        try:
            due=start+dt.timedelta(seconds=int(seconds_needed))
        except (OverflowError, ValueError):
            continue
        out.append(_materialize_hazard_event({"event_id":f"HZ-{clock_id}-{cycle}","family":profile_id,"time":due.strftime("%Y-%m-%dT%H:%M:%S"),"severity":profile.get("severity","notable"),"scope":profile.get("scope","world"),"requires_simulation":True,"note":"Next deterministic hazard candidate."},state,runtime_rules))
    return sorted(out,key=lambda x:x["time"])


def _effective_rate_scaled(profile: dict, seed_anchor: str, clock_id: str, cycle: int, multiplier: float) -> int:
    rate=max(0.0,_profile_annual_rate(profile,seed_anchor,clock_id,cycle)*max(0.0,float(multiplier)))
    return max(0,int(round(rate*HAZARD_RATE_SCALE)))


def _threshold_numerator(seed_anchor: str, clock_id: str, cycle: int) -> int:
    return max(1,int(round(_hazard_threshold(seed_anchor,clock_id,cycle)*HAZARD_DENOMINATOR)))


def _clock_exposure_numerator(clock: dict) -> int:
    n=clock.get("cumulative_hazard_numerator")
    if isinstance(n,int) and not isinstance(n,bool) and n>=0:return n
    x=clock.get("cumulative_hazard",0.0)
    if isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(float(x)) and float(x)>=0:
        return max(0,int(round(float(x)*HAZARD_DENOMINATOR)))
    return 0


def _exposure_float(numerator: int) -> float:
    return float(numerator)/float(HAZARD_DENOMINATOR)


def _advance_single_hazard_clock(original: dict, profile: dict, seed: str, clock_id: str,
                                now: dt.datetime, target: dt.datetime, event_limit: int = 100000) -> Tuple[List[dict],dict,bool]:
    """Advance one persistent hazard clock without losing cooldown or exposure.

    Returns (events, updated_clock, truncated). A truncated result stops at the last
    returned event and never silently consumes an unreturned trigger.
    """
    c=copy.deepcopy(original)
    cycle=int(c.get("cycle",0));cum=_clock_exposure_numerator(c);mult=float(c.get("risk_multiplier",1.0))
    cursor=max(filter(None,(parse_iso(c.get("evaluation_cursor")),parse_iso(c.get("last_evaluated")))))
    if cursor<now:raise EngineError("HAZARD_UNCOVERED_INTERVAL:"+clock_id)
    cooldown=parse_iso(c.get("cooldown_until"))
    if cooldown and cooldown<=cursor:cooldown=None
    events=[];truncated=False
    while cursor<target:
        if cooldown and cursor<cooldown:
            cursor=min(target,cooldown)
            if cursor>=cooldown:cooldown=None
            if cursor>=target:break
        rate_scaled=_effective_rate_scaled(profile,seed,clock_id,cycle,mult)
        if rate_scaled<=0:
            cursor=target;break
        threshold=_threshold_numerator(seed,clock_id,cycle);remain=max(0,threshold-cum)
        seconds_needed=0 if remain<=0 else (remain+rate_scaled-1)//rate_scaled
        available=int((target-cursor).total_seconds())
        if seconds_needed>available:
            cum += available*rate_scaled;cursor=target;break
        if len(events)>=event_limit:
            truncated=True;break
        cum += int(seconds_needed)*rate_scaled
        due=cursor+dt.timedelta(seconds=int(seconds_needed));overshoot=max(0,cum-threshold)
        events.append({"event_id":f"HZ-{clock_id}-{cycle}","family":c.get("profile_id"),"time":due.strftime("%Y-%m-%dT%H:%M:%S"),"severity":profile.get("severity","notable"),"scope":profile.get("scope","world"),"requires_simulation":True,"note":"Engine determined only that this event family triggers; AI must generate the concrete event from WORLD/STATE causality."})
        cursor=due;cycle+=1;cum=overshoot
        cooldown_days=float(profile.get("cooldown_days",0) or 0)
        cooldown=(due+dt.timedelta(days=cooldown_days)) if cooldown_days>0 else None
    c["cycle"]=cycle;c["cumulative_hazard_numerator"]=int(cum);c["cumulative_hazard"]=round(_exposure_float(cum),12)
    c["last_evaluated"]=cursor.strftime("%Y-%m-%dT%H:%M:%S");c["cooldown_until"]=cooldown.strftime("%Y-%m-%dT%H:%M:%S") if cooldown else None
    return events,c,truncated


def preview_long_horizon(state: dict, runtime_rules: dict, until: Optional[dt.datetime] = None, max_events: int = 24) -> dict:
    """Preview persistent low-frequency hazards without silently dropping overflow events.

    If more than max_events would occur before target, the packet is TRUNCATED at a
    safe processed_until. Resolve/save that chunk and rebuild before continuing.
    """
    er=state.get("engine_runtime") or {};lh=er.get("long_horizon") or {};clocks=lh.get("hazard_clocks") or {}
    profiles=(runtime_rules.get("hazard_profiles") or {}) if isinstance(runtime_rules,dict) else {};seed=str(er.get("seed_anchor") or "")
    now=parse_iso(state.get("game_time"))
    if not now or not seed:return {"status":"UNAVAILABLE","reason":"engine_runtime seed/game_time missing","events":[],"clock_updates":{}}
    risk=_risk_window_report(state)
    if risk["status"]=="FAIL":raise EngineError("HAZARD_UNCOVERED_INTERVAL:"+",".join(risk["errors"]))
    target=until or now
    if target<now:raise EngineError("LONG_HORIZON_TARGET_BEFORE_GAME_TIME")
    if not isinstance(max_events,int) or isinstance(max_events,bool) or max_events<1:raise EngineError("LONG_HORIZON_MAX_EVENTS_INVALID")
    probes=[]
    for clock_id,original in clocks.items():
        if not isinstance(original,dict):continue
        profile=profiles.get(str(original.get("profile_id") or "")) or {}
        if not profile:continue
        evs,upd,tr=_advance_single_hazard_clock(original,profile,seed,clock_id,now,target,event_limit=max_events+1)
        probes.append((clock_id,evs,upd,tr))
    merged=sorted([e for _,evs,_,_ in probes for e in evs],key=lambda x:(x["time"],x["event_id"]))
    overflow=len(merged)>max_events or any(tr for *_,tr in probes)
    effective_target=target
    if overflow:
        if len(merged)<max_events:raise EngineError("LONG_HORIZON_OVERFLOW_WITHOUT_CUTOFF")
        effective_target=parse_iso(merged[max_events-1]["time"])
        if effective_target is None:raise EngineError("LONG_HORIZON_CUTOFF_INVALID")
    events=[];updates={};safety_limit=max(100000,max_events*16)
    for clock_id,original in clocks.items():
        if not isinstance(original,dict):continue
        profile=profiles.get(str(original.get("profile_id") or "")) or {}
        if not profile:continue
        evs,upd,tr=_advance_single_hazard_clock(original,profile,seed,clock_id,now,effective_target,event_limit=safety_limit)
        if tr:raise EngineError(f"HAZARD_EVENT_STORM:{clock_id}")
        events.extend(evs);updates[clock_id]=upd
    events.sort(key=lambda x:(x["time"],x["event_id"]))
    events=[_materialize_hazard_event(e,state,runtime_rules) for e in events]
    return {
        "status": "TRUNCATED" if overflow else "READY",
        "requested_until": target.strftime("%Y-%m-%dT%H:%M:%S"),
        "until": effective_target.strftime("%Y-%m-%dT%H:%M:%S"),
        "processed_until": effective_target.strftime("%Y-%m-%dT%H:%M:%S"),
        "events": events,
        "clock_updates": updates,
        "truncated": overflow,
        "continuation_required": overflow,
        "method": "integer_fixed_point_cumulative_hazard_with_deterministic_thresholds_v2",
    }


def latent_process_candidates(state: dict, until: Optional[dt.datetime] = None) -> List[dict]:
    """Schedule reevaluation points for already-existing long-lived causal processes."""
    now=parse_iso(state.get("game_time"));out=[]
    if now is None:return out
    lh=((state.get("engine_runtime") or {}).get("long_horizon") or {})
    for proc in lh.get("latent_processes") or []:
        if not isinstance(proc,dict):continue
        if str(proc.get("status","active")).lower() not in {"active","latent","monitoring"}:continue
        when=parse_iso(proc.get("next_evaluation"))
        if when is None:continue
        if when<now:when=now
        if until is not None and when>until:continue
        pid=str(proc.get("process_id") or "")
        out.append({
            "event_id": f"LP-{pid}-{sha256_bytes(when.strftime('%Y-%m-%dT%H:%M:%S').encode())[:10]}",
            "process_id": pid,
            "family": proc.get("family"),
            "stage": proc.get("stage"),
            "time": when.strftime("%Y-%m-%dT%H:%M:%S"),
            "severity": proc.get("severity", "notable"),
            "scope": proc.get("scope", "world"),
            "visibility": proc.get("visibility", "hidden"),
            "requires_simulation": True,
            "source": "latent_process",
            "note": "Scheduled reevaluation of an existing causal process; AI must resolve it from current causality and update stage/next_evaluation.",
        })
    return sorted(out,key=lambda x:(x["time"],x["event_id"]))


def _task_compact(t: dict, full: bool = False, state: Optional[dict] = None) -> dict:
    if full:return _task_surface(t,state,True)
    out=_task_surface(t,state,False)
    if isinstance(t,dict) and t.get("runtime_policy") is not None:out["runtime_policy"]=_compact_value(t.get("runtime_policy"),2200)
    for k in ("owner_ids","location_ids"):
        if isinstance(t,dict) and k in t:out[k]=_compact_value(t.get(k),600)
    return out


def _runtime_policy_compact(rp: dict) -> dict:
    if not isinstance(rp,dict):return {}
    keys=["profile","execution_mode","minimum_interrupt_severity","hard_interrupt_severity","scheduled_event_severity","monitor"]
    out={k:rp.get(k) for k in keys if k in rp}
    if isinstance(out.get("monitor"),dict):
        out["monitor"]={k:out["monitor"].get(k) for k in ["mode","requires_ai_review","review_on_time_advance","last_reviewed_at","next_review_at","hard_deadline","event_driven","watch_condition"] if k in out["monitor"]}
    return out



def _history_compact(e: dict, full: bool = False) -> dict:
    if full:return e
    keys=["seq","event_id","game_time","time_context","type","summary","details","entities","locations","confidence","tags"]
    out={k:e.get(k) for k in keys if k in e}
    if isinstance(out.get("details"),list) and len(out["details"])>4: out["details"]=out["details"][:4]+["...[truncated]"]
    return out


def _severity_rank(x: str) -> int:
    return {"routine":0,"notable":1,"important":2,"critical":3}.get(str(x),2)


def _runtime_policy_severity(
    t: dict,
    default: str = "important",
    tasks_doc: Optional[dict] = None,
) -> str:
    rp = effective_runtime_policy(tasks_doc or {}, t) if tasks_doc is not None else (t.get("runtime_policy") or {})
    return str(rp.get("scheduled_event_severity") or default)


def _json_pointer_tokens(path: str) -> List[str]:
    if not isinstance(path,str) or not path.startswith("/"):
        raise EngineError(f"PATCH_PATH_MUST_BE_JSON_POINTER: {path!r}")
    if path=="/": return []
    return [x.replace("~1","/").replace("~0","~") for x in path[1:].split("/")]


def _parse_list_index(token: str, path: str) -> int:
    # JSON-pointer array traversal is deliberately canonical: no negative, signed,
    # or ambiguous leading-zero indices. This prevents /list/-1 from silently
    # addressing the last element during Safe Apply traversal.
    if not isinstance(token,str) or not re.fullmatch(r"0|[1-9]\d*",token):
        raise EngineError(f"PATCH_LIST_INDEX_INVALID: {path}")
    return int(token)

def _pointer_parent(obj: Any, path: str) -> Tuple[Any,str]:
    toks=_json_pointer_tokens(path)
    if not toks: raise EngineError("PATCH_ROOT_REPLACEMENT_FORBIDDEN")
    cur=obj
    for tok in toks[:-1]:
        if isinstance(cur,dict):
            if tok not in cur: raise EngineError(f"PATCH_PATH_MISSING: {path}")
            cur=cur[tok]
        elif isinstance(cur,list):
            i=_parse_list_index(tok,path)
            if i>=len(cur):raise EngineError(f"PATCH_LIST_INDEX_INVALID: {path}")
            cur=cur[i]
        else:raise EngineError(f"PATCH_PATH_NOT_CONTAINER: {path}")
    return cur,toks[-1]


def _atomic_replace_bytes(path: Path, data: bytes) -> None:
    tmp=path.with_name(f".{path.name}.apply.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        tmp.write_bytes(data);os.replace(tmp,path)
    finally:
        try:
            if tmp.exists():tmp.unlink()
        except OSError:pass


def _native_stage_root_for_patch(staging: Path) -> Path:
    """Resolve only the two locations made by create_stage, never an arbitrary parent."""
    stage=Path(staging).resolve()
    if not stage.name.startswith('.stage_') or not (stage/'.PARENT.json').is_file():
        raise EngineError('PATCH_REQUIRES_ENGINE_STAGING')
    parent=stage.parent
    if parent.name=='staging' and parent.parent.name=='.runtime':
        root=parent.parent.parent
        if stage.parent!=root/'.runtime'/'staging':raise EngineError('PATCH_STAGING_PATH_INVALID')
    else:
        root=parent
        if stage.parent!=root:raise EngineError('PATCH_STAGING_PATH_INVALID')
    if not (root/'manifest.json').is_file():raise EngineError('PATCH_PARENT_AUTHORITY_MISSING')
    return root.resolve()


def _stage_parent_snapshot_for_apply(staging: Path) -> Optional[dict]:
    try:
        marker=strict_json_load(staging/".PARENT.json");sid=marker.get("parent_save_set_id");root=_native_stage_root_for_patch(staging) if COMPONENT_MODE else staging.parent
        if COMPONENT_MODE:
            current=latest_valid_snapshot(root,verify_parent=True)
            if current.get('save_set_id')!=sid:raise EngineError('STAGING_PARENT_CHANGED_DURING_PATCH')
            return current
        pp=snapshot_path_from_sid(root,sid)
        return validate_game_snapshot(pp,verify_parent=True,root=root) if pp else None
    except Exception:return None


def _validate_patch_history_event(e: dict, seq: int, state_time: Optional[str]) -> None:
    required={"event_id","game_time","type","summary","changes","source"};missing=sorted(required-set(e))
    if missing:raise EngineError(f"PATCH_HISTORY_EVENT_MISSING:{missing}")
    if e.get("seq")!=seq:raise EngineError(f"PATCH_HISTORY_SEQ_EXPECTED_{seq}")
    if not isinstance(e.get("event_id"),str) or not e["event_id"].strip():raise EngineError("PATCH_HISTORY_EVENT_ID_REQUIRED")
    for k in ("type","summary","source"):
        if not isinstance(e.get(k),str) or not e[k].strip():raise EngineError(f"PATCH_HISTORY_{k.upper()}_REQUIRED")
    if not isinstance(e.get("changes"),(dict,list)):raise EngineError("PATCH_HISTORY_CHANGES_STRUCTURED_REQUIRED")
    et=parse_iso(e.get("game_time"));st=parse_iso(state_time)
    if et is None:raise EngineError("PATCH_HISTORY_GAME_TIME_INVALID")
    if st and et>st:raise EngineError("PATCH_HISTORY_GAME_TIME_AFTER_STATE")
    if "authority_files" in e:
        af=e.get("authority_files");allowed={"WORLD.md","state.json","tasks.json"}
        if not isinstance(af,list) or not all(isinstance(x,str) and x in allowed for x in af) or len(af)!=len(set(af)):raise EngineError("PATCH_HISTORY_AUTHORITY_FILES_INVALID")


def _v130_layer_apply_patch_01(staging: Path, patch_path: Path) -> dict:
    """Apply a structured patch transactionally to an engine-created staging set.

    Authority roots and ad-hoc directories are rejected. On any operation or
    post-check failure, STATE/TASKS/HISTORY are restored byte-for-byte.
    """
    staging=staging.resolve()
    if not staging.is_dir():raise EngineError("PATCH_STAGING_NOT_FOUND")
    if not staging.name.startswith(".stage_") or not (staging/".PARENT.json").is_file():raise EngineError("PATCH_REQUIRES_ENGINE_STAGING")
    root=_native_stage_root_for_patch(staging) if COMPONENT_MODE else staging.parent
    latest=latest_valid_snapshot(root,verify_parent=True);validate_stage_parent(staging,root,latest)
    patch=strict_json_load(patch_path)
    if patch.get("format")!=PATCH_FORMAT or not isinstance(patch.get("operations"),list):raise EngineError("PATCH_FORMAT_INVALID")
    originals={fn:(staging/fn).read_bytes() for fn in ("state.json","tasks.json","events.jsonl")}
    objs={fn:read_json(staging/fn) for fn in ("state.json","tasks.json")};hist_meta,hist_events,_=read_history_raw(staging/"events.jsonl")
    hist_existing_count=len(hist_events);hist_physical_raw=_history_physical_nonmeta_lines(staging/"events.jsonl")
    changed=[];appended=[];new_event_refs=[]
    for n,op in enumerate(patch["operations"]):
        if not isinstance(op,dict): raise EngineError(f"PATCH_OPERATION_NOT_OBJECT:{n}")
        kind=op.get("op")
        if kind=="history_append":
            e=copy.deepcopy(op.get("event"))
            if not isinstance(e,dict):raise EngineError(f"PATCH_HISTORY_EVENT_INVALID:{n}")
            seq=_history_expected_next_seq(hist_events);e.setdefault("seq",seq)
            if e.get("seq")!=seq:raise EngineError(f"PATCH_HISTORY_SEQ_EXPECTED_{seq}")
            if not isinstance(e.get("event_id"),str) or not e.get("event_id").strip():raise EngineError("PATCH_HISTORY_EVENT_ID_REQUIRED")
            if any(x.get("event_id")==e["event_id"] for x in hist_events):raise EngineError("PATCH_HISTORY_EVENT_ID_DUPLICATE")
            hist_events.append(e);new_event_refs.append(e);appended.append(e["event_id"]);continue
        fn=op.get("file")
        if fn not in objs:raise EngineError(f"PATCH_FILE_FORBIDDEN:{fn}")
        obj=objs[fn];path=op.get("path")
        if fn=='state.json' and _finance_runtime(objs['state.json'],create=False) is not None:
            sp=str(path or '')
            if sp.startswith('/summary/funds') or sp.startswith('/engine_runtime/finance_runtime'):
                raise EngineError('PATCH_FINANCE_DIRECT_WRITE_FORBIDDEN_USE_DOMAIN_COMMAND')
        parent,key=_pointer_parent(obj,path)
        if isinstance(parent,list):
            idx=_parse_list_index(key,path)
            exists=idx<len(parent);old=parent[idx] if exists else None
        else:exists=key in parent;old=parent.get(key)
        if "expect" in op and old!=op.get("expect"):raise EngineError(f"PATCH_EXPECT_MISMATCH:{fn}:{path}")
        if kind=="set":
            if isinstance(parent,list):
                if not exists:raise EngineError(f"PATCH_LIST_INDEX_MISSING:{path}")
                parent[idx]=copy.deepcopy(op.get("value"))
            else:
                if not exists and op.get("allow_create") is not True:raise EngineError(f"PATCH_SET_MISSING_REQUIRES_ALLOW_CREATE:{fn}:{path}")
                parent[key]=copy.deepcopy(op.get("value"))
        elif kind=="increment":
            if not isinstance(old,(int,float)) or isinstance(old,bool) or not isinstance(op.get("value"),(int,float)) or isinstance(op.get("value"),bool):raise EngineError(f"PATCH_INCREMENT_NUMERIC_REQUIRED:{fn}:{path}")
            nv=old+op["value"]
            if not math.isfinite(float(nv)):raise EngineError("PATCH_INCREMENT_NONFINITE")
            if isinstance(parent,list):parent[idx]=nv
            else:parent[key]=nv
        elif kind=="append":
            if not isinstance(old,list):raise EngineError(f"PATCH_APPEND_LIST_REQUIRED:{fn}:{path}")
            old.append(copy.deepcopy(op.get("value")))
        elif kind=="delete":
            if not exists:raise EngineError(f"PATCH_DELETE_MISSING:{fn}:{path}")
            if isinstance(parent,list):parent.pop(idx)
            else:del parent[key]
        else:raise EngineError(f"PATCH_OPERATION_UNKNOWN:{kind}")
        changed.append({"file":fn,"path":path,"op":kind})
    # Change-triggered local shipboard-asset cross-path gate. This runs before serialization
    # so an equipment transfer can fail fast; the normal PATCH_POSTCHECK remains the full gate.
    _asset_paths=("/shadow_fleet/vessels","/shadow_fleet/mobile_combat_assets_current","/shadow_fleet/ground_power_snapshot","/shadow_fleet/yanhuai4_support_force_current")
    _asset_touched=any(x.get("file")=="state.json" and any(str(x.get("path") or "").startswith(p) for p in _asset_paths) for x in changed)
    if _asset_touched:
        _wt=_authority_world_text(staging)
        if SHIPBOARD_ASSET_CROSSPATH_RULE_ID in _wt:
            _local_asset=shadow_shipboard_asset_crosspath_report(objs["state.json"])
            if _local_asset.get("status")!="PASS":raise EngineError("SHIPBOARD_ASSET_CROSSPATH_LOCAL: "+json.dumps(_local_asset.get("errors",[])[:40],ensure_ascii=False))

    # Validate new event timestamps against the final, not operation-order-dependent, state time.
    for e in new_event_refs:_validate_patch_history_event(e,int(e["seq"]),objs["state.json"].get("game_time"))
    payloads={"state.json":_authority_json_bytes(objs["state.json"]),"tasks.json":_authority_json_bytes(objs["tasks.json"])}
    if appended:
        # Preserve all pre-existing HISTORY event lines byte-for-byte.
        # Only metadata.next_seq and newly appended records may change.
        hist_meta["next_seq"] = _history_expected_next_seq(hist_events)
        meta_raw = json.dumps(hist_meta, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        new_raw = [json.dumps(e, ensure_ascii=False, separators=(",", ":")).encode("utf-8") for e in hist_events[hist_existing_count:]]
        payloads["events.jsonl"] = _history_replace_metadata_bytes(originals["events.jsonl"],hist_meta,new_raw)
    parent_snapshot=_stage_parent_snapshot_for_apply(staging)
    try:
        for fn,data in payloads.items():_atomic_replace_bytes(staging/fn,data)
        qc=run_checks(staging,full=False,require_manifest=False,parent_snapshot=parent_snapshot)
        if qc.get("status")!="PASS":raise EngineError("PATCH_POSTCHECK_FAILED: "+"; ".join(qc.get("errors",[])))
        for fn,data in payloads.items():
            if (staging/fn).read_bytes()!=data:
                raise EngineError('PATCH_POSTCHECK_MUTATED_STAGE:'+fn)
    except Exception:
        rollback_errors=[]
        for fn,data in originals.items():
            try:_atomic_replace_bytes(staging/fn,data)
            except Exception as exc:rollback_errors.append(f"{fn}:{exc}")
        if rollback_errors:raise EngineError("PATCH_ROLLBACK_FAILED: "+";".join(rollback_errors))
        raise
    return {"status":"APPLIED","format":PATCH_FORMAT,"changed":changed,"history_appended":appended,"postcheck":qc,"transactional":True}


def _process_horizon(state: dict, runtime_rules: dict, target: dt.datetime) -> Tuple[dict,dt.datetime,List[dict],Optional[dict]]:
    """Return a causally safe long-horizon preview.

    Existing latent processes are hard replanning barriers for `process`: their
    reevaluation can change world state/risk multipliers, so deterministic clocks
    must not be committed past the earliest such point using pre-event state.
    """
    preview=preview_long_horizon(state,runtime_rules,target)
    safe=parse_iso(preview.get("processed_until")) or target
    latent=latent_process_candidates(state,safe)
    barrier=latent[0] if latent else None
    bt=parse_iso(barrier.get("time")) if barrier else None
    if bt is not None and bt<safe:
        preview=preview_long_horizon(state,runtime_rules,bt)
        safe=parse_iso(preview.get("processed_until")) or bt
        latent=latent_process_candidates(state,safe)
        barrier=latent[0] if latent else barrier
    return preview,safe,latent,barrier


def process_packet(base: Path, until: str, review_ack_path: Optional[Path] = None) -> dict:
    """Build a commit-ready deterministic process frame using the same causal planner as turn.

    This intentionally delegates semantic-review and causal-barrier selection to
    turn_packet so `turn` and `process` cannot drift into different time semantics.
    """
    target=parse_iso(until)
    if not target:raise EngineError("PROCESS_UNTIL_INVALID_ISO_TIME")
    tp=turn_packet(base,mode="until",until=until,detail="full",review_ack_path=review_ack_path)
    state=read_json(base/"state.json");now=parse_iso(state.get("game_time"))
    if tp.get("phase")=="AI_REVIEW_REQUIRED":
        return {
            "engine_version":ENGINE_VERSION,"packet":"PROCESS_FRAME_V4","phase":"AI_REVIEW_REQUIRED",
            "game_time":state.get("game_time"),"source_ready":tp.get("source_ready"),
            "long_horizon":tp.get("long_horizon"),"latent_process_events":[],
            "causal_replan_barrier":None,"causal_replan_barriers":[],"safe_until":state.get("game_time"),
            "task_review_required":True,"task_review_queue":tp.get("task_review_queue") or [],
            "task_review_contract":tp.get("task_review_contract"),"state_patch_hints":[],"requires_history":False,
            "required_time_sync":["No time/hazard commit before Task Monitor review ACK"],
            "note":"Stage-1 planning only. AI must review the exact contract window and return a valid Review ACK; then rerun process/turn with that ACK."
        }
    safe_iso=tp.get("planning_horizon") or state.get("game_time")
    safe=parse_iso(safe_iso) or now
    lh=tp.get("long_horizon") or {}
    hints=[
        {"file":"state.json","path":"/game_time","value":safe_iso},
        {"file":"tasks.json","path":"/game_time","value":safe_iso},
        {"file":"state.json","path":"/engine_runtime/last_evaluated_game_time","value":safe_iso},
        {"file":"state.json","path":"/engine_runtime/long_horizon/hazard_clocks","value":lh.get("clock_updates") or {}},
    ]
    if isinstance(state.get("voyage_day"),int) and not isinstance(state.get("voyage_day"),bool) and now and safe:
        hints.append({"file":"state.json","path":"/voyage_day","value":state["voyage_day"]+max(0,(safe.date()-now.date()).days),"derivation":"calendar_day_delta"})
    return {
        "engine_version":ENGINE_VERSION,"packet":"PROCESS_FRAME_V4","phase":"DETERMINISTIC_PLAN_READY",
        "game_time":state.get("game_time"),"source_ready":tp.get("source_ready"),"long_horizon":lh,
        "candidate_events":tp.get("candidate_events") or [],"causal_replan_barrier":tp.get("causal_replan_barrier"),
        "causal_replan_barriers":tp.get("causal_replan_barriers") or [],"next_interrupt_candidate":tp.get("next_interrupt_candidate"),"safe_until":safe_iso,
        "task_review_required":False,"task_review_queue":[],"task_review_contract":tp.get("task_review_contract"),
        "review_ack_applied":tp.get("review_ack_applied",False),"state_patch_hints":hints,
        "requires_history":safe_iso!=state.get("game_time"),
        "continuation_required":bool(tp.get("continuation_required")),
        "required_time_sync":["STATE.game_time","TASKS.game_time","STATE.engine_runtime.last_evaluated_game_time","each hazard_clock.last_evaluated","due Task Monitor.last_reviewed_at"],
        "note":"Deterministic updates are bounded by the earliest causal simulation barrier; resolve that barrier before planning beyond it."
    }

def extract_rule_section(world_text:str, rule_id:str, max_chars:int=5000)->Optional[str]:
    pos=world_text.find(rule_id)
    if pos<0:return None
    # Section bounded by nearest markdown heading of same/higher level when practical.
    start=world_text.rfind("\n### ",0,pos)
    if start<0:start=world_text.rfind("\n## ",0,pos)
    if start<0:start=max(0,pos-600)
    else:start+=1
    m=re.search(r"\n#{2,3} ",world_text[pos+1:])
    end=(pos+1+m.start()) if m else min(len(world_text),start+max_chars)
    return world_text[start:min(end,start+max_chars)].strip()


def _normalize_search_text(text:str)->str:
    x=str(text or "").lower().replace("–","-").replace("—","-").replace("－","-")
    # Legacy user input using Greek sigma is accepted as a query alias, but stored game text is Latin Sigma.
    x=x.replace(chr(0x03A3).lower(),"sigma").replace(chr(0x03C3),"sigma")
    x=re.sub(r"\bsigma\s*[-_ ]?\s*(?=\d)","sigma-",x)
    x=re.sub(r"\s+"," ",x).strip()
    return x


def _event_matches(e:dict, terms:List[str])->bool:
    if not terms:return False
    blob=_normalize_search_text(json.dumps(e,ensure_ascii=False))
    return any(_normalize_search_text(t) in blob for t in terms if t)



MONITOR_MODES={"scheduled","on_advance","external_wait","continuous","manual"}
TERMINAL_LATENT_STATUSES={"resolved","closed"}
TERMINAL_CLAIM_STATUSES={"resolved","invalidated","superseded","expired","stale"}


def _merge_policy(base: dict, override: dict) -> dict:
    out=copy.deepcopy(base) if isinstance(base,dict) else {}
    if isinstance(override,dict):
        for k,v in override.items():
            if isinstance(v,dict) and isinstance(out.get(k),dict):
                out[k]=_merge_policy(out[k],v)
            else:out[k]=copy.deepcopy(v)
    return out


def effective_runtime_policy(tasks_doc: dict, task: dict) -> dict:
    """Resolve TASK_POLICY_V2 profiles while retaining read compatibility with V1 snapshots."""
    rp=task.get("runtime_policy") or {}
    if not isinstance(rp,dict):return {}
    if rp.get("schema")=="TASK_POLICY_V2":
        profiles=tasks_doc.get("runtime_profiles") or {};profile=str(rp.get("profile") or "")
        eff=_merge_policy(profiles.get(profile) or {},rp.get("overrides") or {})
        eff["schema"]="TASK_POLICY_V2";eff["profile"]=profile
        if isinstance(rp.get("monitor"),dict):eff["monitor"]=copy.deepcopy(rp["monitor"])
        return eff
    # V1 snapshots remain readable so old SAVESETs stay valid recovery parents.
    return copy.deepcopy(rp)


def _task_monitor(tasks_doc: dict, task: dict) -> dict:
    rp=effective_runtime_policy(tasks_doc,task);mon=rp.get("monitor") or {}
    return mon if isinstance(mon,dict) else {}


def _watch_condition_digest(state: dict, condition: dict) -> str:
    sources=condition.get("sources") or []
    payload=[]
    for src in sources:
        rp=resolve_state_ref(state,str(src));payload.append({"source":str(src),"path":rp,"value":get_by_path(state,rp)})
    raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return sha256_bytes(raw.encode("utf-8"))


def _watch_condition_status(state: Optional[dict], task: dict) -> dict:
    mon=((task.get("runtime_policy") or {}).get("monitor") or {}) if isinstance(task,dict) else {}
    cond=mon.get("watch_condition")
    if not isinstance(cond,dict):return {"configured":False,"triggered":False}
    if state is None:return {"configured":True,"triggered":False,"status":"STATE_REQUIRED"}
    try:
        cur=_watch_condition_digest(state,cond);base=str(cond.get("baseline_digest") or "")
        return {"configured":True,"triggered":bool(base and cur!=base),"status":"CHANGED" if base and cur!=base else "UNCHANGED","current_digest":cur,"baseline_digest":base,"sources":list(cond.get("sources") or [])}
    except Exception as exc:
        # Broken watcher routing is safer as an AI barrier than as a silent skip.
        return {"configured":True,"triggered":True,"status":"UNRESOLVED","error":f"{type(exc).__name__}:{exc}"}


def task_monitor_queue(tasks_doc: dict, now: Optional[dt.datetime], horizon: Optional[dt.datetime], include_manual: bool=False, state: Optional[dict]=None) -> List[dict]:
    out=[]
    for t in tasks_doc.get("active_tasks",[]) or []:
        rp=effective_runtime_policy(tasks_doc,t);mon=rp.get("monitor") or {};mode=str(mon.get("mode") or "manual")
        if mode not in MONITOR_MODES:continue
        next_at=parse_iso(mon.get("next_review_at")) if mon.get("next_review_at") else None
        due=False;watch=_watch_condition_status(state,t)
        if watch.get("configured"):
            due=bool(watch.get("triggered"))
        elif mode in {"on_advance","external_wait","continuous"}:due=bool(mon.get("review_on_time_advance",True))
        elif mode=="scheduled":
            # A future scheduled review is not "due now" merely because event mode has no hard horizon.
            # It becomes an AI-review item only when already due at `now`, or when an explicit horizon
            # extends past the scheduled review time. An event exactly at the horizon is the causal
            # simulation barrier itself and must not be pulled into the pre-barrier Review Contract.
            # This keeps event-mode stage 1 ACKs consumable by `process --until <planning_horizon>`.
            due=bool(next_at and ((now is not None and next_at<=now) or (horizon is not None and next_at<horizon)))
        elif mode=="manual":due=include_manual
        if not due:continue
        if not bool(mon.get("requires_ai_review",True)):
            continue
        out.append({
            "task_id":t.get("task_id"),"title":t.get("title"),"priority":t.get("priority"),"mode":mode,
            "requires_ai_review":True,"review_on_time_advance":bool(mon.get("review_on_time_advance",False)),
            "last_reviewed_at":mon.get("last_reviewed_at"),"next_review_at":mon.get("next_review_at"),"hard_deadline":mon.get("hard_deadline"),
            "resolver":mon.get("resolver"),"event_driven":bool(mon.get("event_driven",False)),"watch_condition":_compact_value(watch,520) if watch.get("configured") else None,
            "trigger":_compact_value(t.get("trigger_condition") or t.get("next_trigger"),240)
        })
    return out


def _runtime_sidecar(name: str) -> Path:
    d=ROOT/".runtime";d.mkdir(parents=True,exist_ok=True);return d/name


def _history_index_integrity(obj: dict) -> str:
    """Self-check the runtime-only logical HISTORY sidecar."""
    payload=copy.deepcopy(obj);payload.pop("integrity_sha256",None)
    return sha256_bytes(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8"))

def _history_index_cache_intact(obj: Any) -> bool:
    return isinstance(obj,dict) and isinstance(obj.get("integrity_sha256"),str) and obj.get("integrity_sha256")==_history_index_integrity(obj)

def _history_detail_search_items(value: Any, limit: int = 4) -> List[str]:
    """Normalize heterogeneous HISTORY.details for search indexing.

    Older events legitimately use dict/scalar details while newer events often use
    lists.  Runtime indexing must never assume sliceability of the authority value.
    """
    if value is None:
        return []
    if isinstance(value, list):
        items=value[:max(0,int(limit))]
    elif isinstance(value, dict):
        # Preserve a compact deterministic representation rather than iterating only keys.
        items=[json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))]
    else:
        items=[value]
    return [str(x) for x in items]


def _history_index(base: Path) -> dict:
    """Locator-only logical HISTORY index.

    V3 never duplicates complete event objects. Raw records are addressed by byte
    offset/length; compacted Epoch records are addressed by physical line plus item
    index.  The sidecar stays disposable and source-SHA/Engine/integrity bound.
    """
    hp=base/'events.jsonl';hh=sha256_file(hp);cache=_runtime_sidecar('history_index.json') if base.resolve()==ROOT.resolve() else None
    # The locator index is derived from both the hot records and immutable cold
    # payloads. Verify their actual bytes before accepting a cached search result.
    manifest=_component_manifest_read(base);cold_parts=[]
    for rel,entry in sorted(_component_cold_archives(manifest).items()):
        if 'seq_start' not in entry:continue
        source=base/rel
        if not source.is_file():raise EngineError('HISTORY_ARCHIVE_MISSING:'+rel)
        digest=sha256_file(source)
        if digest!=entry.get('file_sha256'):raise EngineError('HISTORY_ARCHIVE_HASH_MISMATCH:'+rel)
        cold_parts.append(rel+':'+digest)
    cold_sig=sha256_bytes('\n'.join(cold_parts).encode())
    if cache and cache.is_file():
        try:
            obj=strict_json_load(cache)
            if obj.get('format')=='VOYAGER_HISTORY_INDEX_V3' and obj.get('engine_version')==ENGINE_VERSION and obj.get('history_sha256')==hh and obj.get('cold_signature')==cold_sig and _history_index_cache_intact(obj):return obj
        except Exception:pass
    records=[];term_map={}
    def add_event(rec,locator):
        vals=[]
        for k in ['event_id','type','source_task_id','source']:
            if rec.get(k):vals.append(str(rec.get(k)))
        for k in ['entities','locations','tags']:
            v=rec.get(k) or []
            if isinstance(v,list):vals.extend(str(x) for x in v)
        blob=_normalize_search_text(' '.join(vals+[str(rec.get('summary',''))]+_history_detail_search_items(rec.get('details'),4)))
        ridx=len(records);records.append({'blob':blob,'seq':rec.get('seq'),'game_time':rec.get('game_time'),'event_id':rec.get('event_id'),'type':rec.get('type'),'locator':locator})
        for val in vals:
            nv=_normalize_search_text(val)
            if nv:term_map.setdefault(nv,[]).append(ridx)
    with hp.open('rb') as f:
        line_no=0
        while True:
            offset=f.tell();raw=f.readline()
            if not raw:break
            line_no+=1
            if not raw.strip():continue
            rec=strict_json_loads(raw.decode('utf-8'))
            if rec.get('record_type')=='metadata':continue
            if rec.get('record_type')=='history_epoch':
                # Full validation checks this metadata against the decompressed
                # events. Search can build its disposable locator index cheaply.
                indexed=rec.get('search_index')
                if isinstance(indexed,list) and len(indexed)==int(rec.get('event_count') or -1):
                    for item,e in enumerate(indexed):add_event(e,{'kind':'epoch','offset':offset,'length':len(raw),'item':item})
                else:
                    ee,_rr=_decode_history_epoch_record(rec,line_no,base)
                    for item,e in enumerate(ee):add_event(e,{'kind':'epoch','offset':offset,'length':len(raw),'item':item})
            elif 'seq' in rec:add_event(rec,{'kind':'raw','offset':offset,'length':len(raw)})
            else:raise EngineError(f'HISTORY_INDEX_UNKNOWN_RECORD:{line_no}')
    obj={'format':'VOYAGER_HISTORY_INDEX_V3','engine_version':ENGINE_VERSION,'history_sha256':hh,'cold_signature':cold_sig,'records':records,'term_map':term_map,'event_count':len(records),'index_mode':'locator_only_v3'}
    obj['integrity_sha256']=_history_index_integrity(obj)
    if cache:
        try:
            tmp=cache.with_name(f'.{cache.name}.{os.getpid()}.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')),encoding='utf-8');os.replace(tmp,cache)
        except Exception:pass
    return obj

def _history_event_from_locator(path:Path,locator:dict)->dict:
    with path.open('rb') as f:
        f.seek(int(locator.get('offset',-1)));raw=f.read(int(locator.get('length',0)))
    rec=strict_json_loads(raw.decode('utf-8'))
    kind=locator.get('kind')
    if kind=='raw':return rec
    if kind=='epoch':
        ee,_=_decode_history_epoch_record(rec,0,path.parent);i=int(locator.get('item',-1))
        if i<0 or i>=len(ee):raise EngineError('HISTORY_INDEX_EPOCH_ITEM_INVALID')
        return ee[i]
    raise EngineError('HISTORY_INDEX_LOCATOR_INVALID')

def _history_index_events(base: Path, terms: List[str], limit: int, full: bool=False) -> List[dict]:
    idx=_history_index(base);records=idx.get('records',[]);wanted=set();norm=[_normalize_search_text(x) for x in terms if x]
    for term in norm:wanted.update(idx.get('term_map',{}).get(term,[]))
    if not wanted:
        for i,r in enumerate(records):
            blob=r.get('blob','')
            if any(term and term in blob for term in norm):wanted.add(i)
    cap=max(0,int(limit))
    if cap==0:return []
    picks=sorted(wanted)[-cap:];out=[];hp=base/'events.jsonl'
    for i in picks:
        e=_history_event_from_locator(hp,records[i].get('locator') or {})
        out.append(_history_compact(e,full))
    return out


def _world_index_integrity(obj: dict) -> str:
    """Self-check the runtime-only locator registry for WORLD rules."""
    payload=copy.deepcopy(obj);payload.pop("integrity_sha256",None)
    return sha256_bytes(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8"))

def _world_index_cache_intact(obj: Any) -> bool:
    return isinstance(obj,dict) and isinstance(obj.get("integrity_sha256"),str) and obj.get("integrity_sha256")==_world_index_integrity(obj)

def _world_rule_locator_rows(text:str)->Tuple[dict,List[dict]]:
    matches=list(re.finditer(r'(?m)^###\s+((?:RULE|SOP)-[A-Z0-9][A-Z0-9-]*)\b[^\n]*',text));reg={};dups=[]
    for i,m in enumerate(matches):
        rid=m.group(1);end=matches[i+1].start() if i+1<len(matches) else len(text);raw=text[m.start():end].rstrip();deps=sorted(set(re.findall(r'\b(?:RULE|SOP)-[A-Z0-9][A-Z0-9-]*\b',raw))-{rid})
        row={"start":m.start(),"end":end,"heading":m.group(0).strip(),"section_sha256":sha256_bytes(raw.encode("utf-8")),"dependencies":deps}
        if rid in reg:dups.append({"rule_id":rid,"first":reg[rid].get("start"),"duplicate":m.start()})
        else:reg[rid]=row
    return reg,dups

def _world_rule_registry_integrity_report(world_text:str)->dict:
    reg,dups=_world_rule_locator_rows(world_text);refs=sorted(set(re.findall(r'\b(?:RULE|SOP)-[A-Z0-9][A-Z0-9-]*\b',world_text)));missing=[x for x in refs if x not in reg]
    return {"schema":"WORLD_RULE_REGISTRY_V2","rule_count":len(reg),"duplicate_heading_count":len(dups),"reference_without_heading_count":len(missing),"duplicates":dups[:50],"reference_without_heading":missing[:100],"count":len(dups)}

def _world_index(base: Path, world_text: Optional[str]=None) -> dict:
    wh=_authority_world_sha256(base);cache=_runtime_sidecar("world_index.json") if base.resolve()==ROOT.resolve() else None
    if cache and cache.is_file():
        try:
            obj=strict_json_load(cache)
            if obj.get("format")=="VOYAGER_WORLD_RULE_REGISTRY_V2" and obj.get("engine_version")==ENGINE_VERSION and obj.get("world_sha256")==wh and _world_index_cache_intact(obj):return obj
        except Exception:pass
    text=world_text if world_text is not None else _authority_world_text(base)
    registry,dups=_world_rule_locator_rows(text)
    if dups:raise EngineError("WORLD_RULE_DUPLICATE_HEADING:"+json.dumps(dups[:20],ensure_ascii=False))
    obj={"format":"VOYAGER_WORLD_RULE_REGISTRY_V2","engine_version":ENGINE_VERSION,"world_sha256":wh,"rule_count":len(registry),"registry":registry}
    obj["integrity_sha256"]=_world_index_integrity(obj)
    if cache:
        try:
            tmp=cache.with_name(f".{cache.name}.{os.getpid()}.tmp");tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(",",":")),encoding="utf-8");os.replace(tmp,cache)
        except Exception:pass
    return obj


def _world_rule_from_index(base: Path, world_text: str, rid: str, max_chars: int) -> Tuple[Optional[str],dict]:
    loc=None
    try:loc=(_world_index(base,world_text).get("registry") or {}).get(rid)
    except Exception:loc=None
    raw=None
    if isinstance(loc,dict):
        try:
            a=int(loc.get("start"));b=int(loc.get("end"));candidate=world_text[a:b].rstrip()
            if sha256_bytes(candidate.encode("utf-8"))==loc.get("section_sha256") and re.match(r'^###\s+'+re.escape(rid)+r'\b',candidate):raw=candidate
        except Exception:raw=None
    if raw is None:raw=extract_rule_section(world_text,rid,max_chars=1000000)
    if raw is None:return None,{"chars_total":0,"chars_returned":0,"truncated":False}
    raw=str(raw).strip();cap=max(1,int(max_chars));cut=raw[:cap].rstrip();tr=len(raw)>len(cut)
    return cut,{"chars_total":len(raw),"chars_returned":len(cut),"truncated":tr,"registry":"WORLD_RULE_REGISTRY_V2"}


QUERY_SYNONYM_PAIRS = [
    ("战斗力","战力"),("舰船","舰艇"),("舰艇","战舰"),("陆战","地面战斗"),
    ("空战","航空战斗"),("对地","地面支援"),("无人机","无人航空器"),
]

SHIP_COMBAT_MARKERS = ["舰船","舰艇","军舰","战舰","护卫舰","驱逐舰","舰队","辅助舰","支援舰","补给舰","维修舰","维修船","工程维修船","科考舰","科考船","科研舰","侦察舰","运输舰","秦锋","长戟","守护者","铁卫","刀剑","母巢","影刃","窃听者","探索者","西湖","巨钳","哨兵"]
GROUND_COMBAT_MARKERS = ["陆战","地面战斗","陆战队","步兵","机器人","动力甲","外骨骼","手雷","火箭筒","单兵导弹",
                         "步枪","霰弹枪","手枪","卫士","堡垒","先锋"]
AIR_COMBAT_MARKERS = ["空战","航空战斗","对地","地面支援","无人机","战斗机","穿梭机","登陆艇","彩虹","雷电","猎隼","夜鹰","大力神","蓝鲸","蜂鸟","玄武"]

def _query_variants(topic: str) -> List[str]:
    q=_normalize_search_text(topic);vals=[]
    def add(x:str):
        x=_normalize_search_text(x)
        if x and x not in vals: vals.append(x)
    add(q)
    if q:
        short=q
        for token in ["请问","帮我","查一下","查询","现在","目前","怎么样","情况如何","情况","在干什么","干什么","是什么"]:
            short=short.replace(token,"")
        short=re.sub(r"[?？!！,，。;；:：\s]+","",short).strip();add(short)
        # Add an entity-focused variant so questions like “秦锋号综合战斗力” or “S-3护盾性能”
        # can hit STATE while the full phrase still routes to the correct WORLD rule.
        entityish=short
        for token in ["综合战斗力","地面支援","军用舰体","地面战斗","战斗力","战力","综合","性能","状态","情况","护盾","武装","装备","配置","舰体","火力","耐久","空战","陆战","对地","多少","怎么","如何","评估","评价"]:
            entityish=entityish.replace(token,"")
        entityish=entityish.strip();
        if len(entityish)>=2:add(entityish)
        # Bounded synonym closure: enough for natural Chinese rule queries without a fuzzy-search dependency.
        frontier=list(vals)
        for _ in range(2):
            nxt=[]
            for cur in frontier:
                for a,b in QUERY_SYNONYM_PAIRS:
                    if a in cur:
                        cand=cur.replace(a,b);add(cand);nxt.append(cand)
                    if b in cur:
                        cand=cur.replace(b,a);add(cand);nxt.append(cand)
            frontier=nxt[:24]
    return vals[:32]

def _direct_world_rule_ids(topic:str, base:Path) -> List[str]:
    q=_normalize_search_text(topic);out=[]
    available=resolve_rule_registry(base)['rules']
    # Explicit RULE/SOP identifiers always win.
    for rid in re.findall(r"\b(?:RULE|SOP)-[A-Z0-9][A-Z0-9-]*\b",str(topic or "").upper()):
        if rid not in out: out.append(rid)
    combat=any(k in q for k in ["战力","战斗力","火力","耐久","护盾","武装","舰体"])
    if (combat and any(k in q for k in SHIP_COMBAT_MARKERS)) or "护盾" in q: out.append("RULE-COMBAT-01")
    if combat and any(k in q for k in GROUND_COMBAT_MARKERS): out.append("RULE-GROUND-COMBAT-01")
    if (combat or "对地" in q or "地面支援" in q) and any(k in q for k in AIR_COMBAT_MARKERS): out.append("RULE-AIR-GROUND-COMBAT-01")
    # De-duplicate while preserving priority.
    seen=set();return [x for x in out if x in available and not (x in seen or seen.add(x))]


QUERY_STATE_ALIASES = [
    (["金川资源网络","金川矿业网络","金川矿业日产","金川资源日产"], "ref:JINCHUAN_RESOURCE_NETWORK_CURRENT"),
    (["金川日结","金川最近日结","金川财务结算","金川最近财务结算"], "jinchuan_fleet.latest_daily_financial_settlement"),
    (["卡尔德552项产业","卡尔德产业","552项产业","产业日结","产业收入","Calder 552 industries","Calder's 552 industries","Calder industries"], "ref:MULTINATIONAL_INDUSTRY_CURRENT"),
    (["远航者武器汇总","远航者步枪汇总","远航者武器库存汇总"], "ref:VOYAGER_WEAPON_INVENTORY_CURRENT"),
    (["暗影拘押网络","暗影监狱","S-B5拘押"], "ref:SHADOW_DETENTION_NETWORK_CURRENT"),
    (["待验收武器","待交付武器","武器待验收"], "ref:WEAPON_INVENTORY_PENDING_CURRENT"),
    (["购入星图","未探索星图","购买星图"], "ref:PURCHASED_STAR_CHARTS_CURRENT"),
    (["天坑-5","天坑5"], "ref:TIANKENG5_CURRENT"),
    (["卡尔德补给","补给套利","补给贸易"], "world_state_overrides.markets_and_procurement.calder_supply_arbitrage_current"),
    (["暗影舰队","暗影当前状态"], "shadow_fleet"),
    (["暗影位置","暗影舰位置","暗影舰队位置"], "shadow_fleet.current_location"),
    (["暗影基地","S-B5"], "world_state_overrides.fleet_and_logistics.shadow_base_current"),
    (["远航者舰队","远航者当前状态"], "voyager_fleet"),
    (["金川舰队","金川当前状态"], "jinchuan_fleet"),
    (["金币","灰币","资金","余额"], "summary.funds"),
    (["舰队核心","舰数","人员数"], "summary"),
    (["库存","公共库存","装备库存"], "inventories"),
    (["白峡和平","白峡协议","白峡和平进程"], "world_state_overrides.organizations_and_politics.nation_dynamics.白峡共和国"),
    (["科研资料销售","兽环资料","镜棺资料","数据销售"], "world_state_overrides.markets_and_procurement.research_data_sales_program"),
]

def _query_terms(topic:str)->List[str]:
    raw=_normalize_search_text(topic); out=[]
    def add(x):
        x=_normalize_search_text(x)
        for token in ["请问","帮我","查一下","查询","现在","目前","怎么样","情况如何","情况","多少","如何","告诉我","列出","显示"]:x=x.replace(token,"")
        x=re.sub(r"[?？!！,，。;；:：\\s]+","",x).strip()
        if len(x)>=2 and x not in out:out.append(x)
    add(raw)
    parts=[raw]
    for sep in ["，",",","；",";","。","?","？","以及","还有","同时","并且","和"]:
        parts=[p2 for p in parts for p2 in p.split(sep)]
    for p in parts:add(p)
    # Useful entity/core noun fragments for natural multi-intent Chinese questions.
    for token in ["卡尔德产业","产业收入","补给套利","暗影舰队","远航者舰队","金川舰队","白峡和平","科研资料销售","金币","灰币","库存"]:
        if token in raw:add(token)
    return out[:40]

def _direct_state_alias_paths(topic:str)->List[str]:
    q=_normalize_search_text(topic);out=[]
    for aliases,path in QUERY_STATE_ALIASES:
        if any(_normalize_search_text(a) in q for a in aliases):out.append(path)
    seen=set();return [p for p in out if not (p in seen or seen.add(p))]

def _state_sidecar_integrity(obj: dict) -> str:
    """Self-check a runtime-only STATE sidecar without rehashing STATE on hot reads."""
    payload=copy.deepcopy(obj);payload.pop("integrity_sha256",None)
    return sha256_bytes(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8"))

def _state_semantic_index(base: Path) -> dict:
    """Runtime-only compact index for hot mobile queries.

    The authority remains state.json.  A hot sidecar hit is bound to Engine version,
    the full cheap file-stat record, current SAVESET identity, and a self-integrity
    digest.  Rebuilds still bind the exact STATE SHA-256.  Therefore corruption or a
    stale sidecar cannot change query answers, while normal hot reads avoid hashing
    and reparsing the full STATE document on every process invocation.
    """
    sp=base/"state.json";stat_sig=_stat_record(sp)
    cache=_runtime_sidecar("state_semantic_index.json") if base.resolve()==ROOT.resolve() else None
    expected_sid=None
    if cache:
        try:
            rc=strict_json_load(_runtime_cache_path(ROOT))
            if _runtime_session_cache_intact(rc) and rc.get("format")==RUNTIME_SCHEMA and rc.get("engine_version")==ENGINE_VERSION and rc.get("authority_stats")==_authority_stat_signature(ROOT):
                expected_sid=str(rc.get("save_set_id") or "") or None
        except Exception:
            pass
    if cache and cache.is_file():
        try:
            obj=strict_json_load(cache)
            intact=(isinstance(obj.get("integrity_sha256"),str) and obj.get("integrity_sha256")==_state_sidecar_integrity(obj))
            sid_ok=(expected_sid is None or obj.get("save_set_id")==expected_sid)
            if obj.get("format")=="VOYAGER_STATE_SEMANTIC_INDEX_V2" and obj.get("engine_version")==ENGINE_VERSION and obj.get("state_stat")==stat_sig and sid_ok and intact:
                return obj
        except Exception:
            pass
    sh=sha256_file(sp);state=read_json(sp); alias_values={}
    for _,path in QUERY_STATE_ALIASES:
        if path in alias_values:continue
        try:
            rp=resolve_state_ref(state,path);val=_compact_value(get_by_path(state,rp),3200);alias_values[path]=val;alias_values.setdefault(rp,val)
        except KeyError:pass
    # Small locator-only entity index. Legacy Calder labels use direct aliases and never synthesize per-item rows.
    entities={}
    try:
        vessels=(state.get("shadow_fleet") or {}).get("vessels") or {}
        for vid,rec in vessels.items():
            if not isinstance(rec,dict):continue
            loc={"kind":"shadow_vessel","path":f"shadow_fleet.vessels.{vid}","vessel_id":vid,"name":rec.get("name")}
            for token in (vid,rec.get("name")):
                nt=_normalize_search_text(str(token or ""))
                if nt:entities[nt]=loc
    except Exception:pass
    try:
        inst=get_by_path(state,"world_state_overrides.autonomous_entity_registry.instantiated")
        if isinstance(inst,dict):
            for eid,rec in inst.items():
                if not isinstance(rec,dict):continue
                loc={"kind":"autonomous_entity","path":f"world_state_overrides.autonomous_entity_registry.instantiated.{eid}","entity_id":eid,"name":rec.get("name")}
                for token in (eid,rec.get("name")):
                    nt=_normalize_search_text(str(token or ""))
                    if nt:entities[nt]=loc
    except Exception:pass
    exact_paths={"summary.funds.gold","summary.funds.grey","game_time","summary.ships.voyager","summary.ships.jinchuan","summary.ships.shadow_active","world_state_overrides.mining_and_industry.jinchuan_resource_network_current","jinchuan_fleet.latest_daily_financial_settlement"}
    exact_alias_values={}
    for ep in exact_paths:
        try:exact_alias_values[ep]=get_by_path(state,ep)
        except KeyError:pass
    if expected_sid is None:
        try:expected_sid=str((validate_authority_set(base) or {}).get("save_set_id") or "") or None
        except Exception:expected_sid=None
    obj={"format":"VOYAGER_STATE_SEMANTIC_INDEX_V2","engine_version":ENGINE_VERSION,"save_set_id":expected_sid,"state_sha256":sh,"state_stat":stat_sig,"game_time":state.get("game_time"),"summary":state.get("summary"),"alias_values":alias_values,"exact_alias_values":exact_alias_values,"entity_lookup":entities}
    obj["integrity_sha256"]=_state_sidecar_integrity(obj)
    if cache:
        try:
            tmp=cache.with_name(f".{cache.name}.{os.getpid()}.tmp");tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(",",":")),encoding="utf-8");os.replace(tmp,cache)
        except Exception:pass
    return obj

def _state_index_entity_hit(base: Path, variants: List[str]) -> Optional[dict]:
    try:idx=_state_semantic_index(base)
    except Exception:return None
    lookup=idx.get("entity_lookup") or {}
    for v in variants:
        nv=_normalize_search_text(v)
        if nv in lookup:return lookup[nv]
    # No virtual Calder assets: old names resolve only to the consolidated account.
    return None

def runtime_archive_plan(base: Path) -> dict:
    ready=ensure_source_ready(base);state=read_json(base/"state.json");er=state.get("engine_runtime") or {};lh=er.get("long_horizon") or {};kl=er.get("knowledge_layer") or {}
    latent=[p for p in (lh.get("latent_processes") or []) if isinstance(p,dict) and str(p.get("status","")).lower() in TERMINAL_LATENT_STATUSES]
    claims=[c for c in (kl.get("claims") or []) if isinstance(c,dict) and str(c.get("status","")).lower() in TERMINAL_CLAIM_STATUSES]
    return {
        "engine_version": ENGINE_VERSION,
        "status": "READY",
        "source_ready": ready,
        "latent_processes": _compact_value(latent, 6000),
        "knowledge_claims": _compact_value(claims, 6000),
        "candidate_count": len(latent) + len(claims),
        "policy": "Archive terminal runtime entries by appending a HISTORY event that preserves the final state, then delete only those terminal entries from STATE in the same transact patch. Engine never invents the archival narrative.",
    }

