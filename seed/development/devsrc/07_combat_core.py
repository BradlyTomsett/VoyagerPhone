# === VOYAGER_DEV_MODULE: combat_core ===
def combatcalc(base:Path,kind:str,payload:dict)->dict:
    ensure_source_ready(base);cfg=_combat_runtime_rules(base);kind=str(kind).lower()
    if not isinstance(payload,dict):raise EngineError("COMBAT_INPUT_OBJECT_REQUIRED")
    player_force=_strict_bool(payload.get("player_force",False),"PLAYER_FORCE") if "player_force" in payload else False
    if kind=="aircraft":
        ac=cfg.get("air_ground") or {};models=ac.get("models") or {};model=payload.get("model")
        if model:
            row=models.get(str(model));
            if not isinstance(row,dict):raise EngineError(f"COMBAT_AIRCRAFT_MODEL_UNKNOWN:{model}")
            base_a=_finite_num(row.get("a"),"BASE_A",0);k=_finite_num(row.get("k"),"K",0)
        else:
            base_a=_finite_num(payload.get("base_a"),"BASE_A",0);k=_finite_num(payload.get("k"),"K",0)
        perf=_factor(payload.get("performance_factor",1.0),"PERFORMANCE_FACTOR");integrity,repaired=_combat_integrity(payload,"INTEGRITY",player_force);age=_finite_num(payload.get("age_years",0),"AIRCRAFT_AGE_METADATA",0)
        a=base_a*perf*integrity;g=a*k;res={"kind":"aircraft","model":model,"base_a":base_a,"performance_factor":perf,"integrity":integrity,"repair_completed":repaired,"secondhand_discount_applied":False if player_force else None,"age_years":age,"age_factor":1.0,"age_decay_disabled":True,"A":a,"K":k,"G":g}
    elif kind=="ground":
        gc=cfg.get("ground") or {};weapon_coeff=gc.get("weapon_coefficients") or {};agecfg=gc.get("external_equipment_age") or {};personnel_base_fraction=_finite_num(gc.get("personnel_base_fraction",0.30),"PERSONNEL_BASE_FRACTION",0,1);weapon_contribution_fraction=_finite_num(gc.get("weapon_contribution_fraction",0.70),"WEAPON_CONTRIBUTION_FRACTION",0,1);standing=0.0;personnel_breakdown=[];robot_breakdown=[]
        for row in payload.get("personnel_groups",[]) or []:
            if not isinstance(row,dict):raise EngineError("COMBAT_PERSONNEL_GROUP_OBJECT_REQUIRED")
            n=_finite_num(row.get("count",1),"COUNT",0);basep=_finite_num(row.get("base",0),"PERSON_BASE",0);weapon=str(row.get("weapon","rifle"));w=weapon_coeff.get(weapon,row.get("weapon_coefficient"));w=_finite_num(w,"WEAPON_COEFFICIENT",0)
            weapon_struct={}
            for src,dst in [("weapon_age_years","age_years"),("weapon_self_origin","self_origin"),("weapon_integrity","integrity"),("weapon_performance_factor","performance_factor"),("weapon_overlife_story_usable","overlife_story_usable"),("weapon_repair_status","repair_status"),("weapon_refurbishment_status","refurbishment_status"),("weapon_condition_pct","condition_pct")]:
                if src in row:weapon_struct[dst]=row[src]
            for inherited_status in ("repair_status","refurbishment_status","maintenance_status"):
                if inherited_status in row and inherited_status not in weapon_struct:weapon_struct[inherited_status]=row[inherited_status]
            if "weapon_effective" in row:weapon_struct["effective"]=row["weapon_effective"]
            if player_force:weapon_struct.setdefault("player_force",True)
            e,edetail=_weapon_integrity_effective(weapon_struct,"WEAPON_",player_force)
            p_unarmored=basep*(personnel_base_fraction+weapon_contribution_fraction*w*e);p=p_unarmored;armor=row.get("armor") or {};armor_detail=None
            if armor:
                if not isinstance(armor,dict):raise EngineError("COMBAT_ARMOR_OBJECT_REQUIRED")
                bonus=_factor(armor.get("bonus",0.0),"ARMOR_BONUS");ae,armor_detail=_ground_item_effective(armor,agecfg,"ARMOR_",player_force=player_force);p*=1.0+bonus*ae
            standing+=n*p;personnel_breakdown.append({"count":n,"base":basep,"weapon":weapon,"weapon_coefficient":w,"weapon_effective":e,"weapon_detail":edetail,"unarmored_each":p_unarmored,"armor_detail":armor_detail,"effective_each":p,"subtotal":n*p})
        for row in payload.get("robots",[]) or []:
            if not isinstance(row,dict):raise EngineError("COMBAT_ROBOT_OBJECT_REQUIRED")
            n=_finite_num(row.get("count",1),"COUNT",0);nominal=_finite_num(row.get("nominal",0),"ROBOT_NOMINAL",0);e,detail=_ground_item_effective(row,agecfg,"ROBOT_",player_force=player_force);sub=n*nominal*e;standing+=sub;robot_breakdown.append({"count":n,"nominal":nominal,"effective":e,"detail":detail,"subtotal":sub})
        bv=gc.get("burst_values") or {};burst=0.0;burst_breakdown=[]
        for key,cfgkey in [("grenades","grenade"),("rockets","rocket"),("missiles","missile")]:
            x=payload.get(key) or {}
            if not isinstance(x,dict):raise EngineError(f"COMBAT_{key.upper()}_OBJECT_REQUIRED")
            count=_finite_num(x.get("count",0),"COUNT",0)
            if cfgkey=="grenade":eff,detail=_grenade_effective(x,gc.get("grenade") or {},player_force)
            else:eff,detail=_weapon_integrity_effective(x,f"{cfgkey.upper()}_",player_force)
            unit=_finite_num(bv.get(cfgkey),"BURST_VALUE",0);sub=count*unit*eff;burst+=sub;burst_breakdown.append({"type":cfgkey,"count":count,"unit_value":unit,"effective":eff,"detail":detail,"subtotal":sub})
        res={"kind":"ground","standing_combat_power":standing,"burst_pool":burst,"personnel_breakdown":personnel_breakdown,"robot_breakdown":robot_breakdown,"burst_breakdown":burst_breakdown}
    elif kind=="ship":
        sc=cfg.get("ship") or {}
        missing=[k for k in ("length_m","source_factor","hull_type","hull_age_years") if k not in payload]
        if missing:raise EngineError("COMBAT_SHIP_CORE_FIELDS_REQUIRED:"+",".join(missing))
        length=_finite_num(payload.get("length_m"),"LENGTH_M",0.01);source=_finite_num(payload.get("source_factor"),"SOURCE_FACTOR",0,1);ht=str(payload.get("hull_type"));htf=(sc.get("hull_type_factors") or {}).get(ht)
        if htf is None:raise EngineError(f"COMBAT_HULL_TYPE_UNKNOWN:{ht}")
        ext_top=_finite_num((sc.get("source_factors") or {}).get("external_top",0.7),"EXTERNAL_TOP_SOURCE_FACTOR",0,1)
        if source>ext_top+1e-12 and abs(source-1.0)>1e-12:raise EngineError(f"COMBAT_SHIP_SOURCE_FACTOR_INVALID:{source}")
        age=_finite_num(payload.get("hull_age_years"),"HULL_AGE_METADATA",0);ha=sc.get("hull_age") or {};haf=1.0;base_hull=100.0*(length/100.0)**2.5;hull_max=base_hull*_factor(htf,"HULL_TYPE_FACTOR")*source*haf
        detailed=any("integrity" in x for x in (payload.get("weapons",[]) or [])+(payload.get("shields",[]) or [])) or "hull_integrity" in payload
        if detailed and "overall_integrity" in payload and float(payload.get("overall_integrity",1.0))!=1.0:raise EngineError("COMBAT_SHIP_MIXED_INTEGRITY_FORBIDDEN")
        _hrow=dict(payload);_hrow["integrity"]=payload.get("hull_integrity",1.0);hull_integrity,hull_repaired=_combat_integrity(_hrow,"HULL_INTEGRITY",player_force);fire=0.0;burst=0.0;wb=sc.get("weapon_base") or {};weapon_breakdown=[]
        for row in payload.get("weapons",[]) or []:
            if not isinstance(row,dict):raise EngineError("COMBAT_WEAPON_OBJECT_REQUIRED")
            typ=str(row.get("type"));count=_finite_num(row.get("count",1),"COUNT",0);integ,repaired=_combat_integrity(row,"INTEGRITY",player_force);src=_finite_num(row.get("source_factor",source),"SOURCE_FACTOR",0,1)
            if src>ext_top+1e-12 and abs(src-1.0)>1e-12:raise EngineError(f"COMBAT_COMPONENT_SOURCE_FACTOR_INVALID:{src}")
            if "self_owned" in row:raise EngineError("COMBAT_SELF_OWNED_AMBIGUOUS_USE_SELF_ORIGIN")
            if "self_origin" in row:self_origin=_self_origin(row)
            else:self_origin=abs(src-1.0)<=1e-12
            if self_origin and abs(src-1.0)>1e-12:raise EngineError("COMBAT_SELF_ORIGIN_SOURCE_FACTOR_MISMATCH")
            if (not self_origin) and src>ext_top+1e-12:raise EngineError("COMBAT_EXTERNAL_ORIGIN_SOURCE_FACTOR_MISMATCH")
            wage=_finite_num(row.get("age_years"),"WEAPON_AGE_METADATA",0) if "age_years" in row else None
            af=1.0
            if typ=="missile":
                basev=_finite_num(wb.get("missile_cell",2.5),"MISSILE_CELL",0);fadd=count*basev*src*af*integ;badd=count*_finite_num(wb.get("missile_burst",50),"MISSILE_BURST",0)*src*af*integ;fire+=fadd;burst+=badd;weapon_breakdown.append({"type":typ,"count":count,"source_factor":src,"self_origin":self_origin,"age_years":wage,"age_factor":af,"age_decay_disabled":True,"integrity":integ,"repair_completed":repaired,"secondhand_discount_applied":False if player_force else None,"fire":fadd,"burst":badd});continue
            if typ=="point_defense":basev=_finite_num(wb.get("point_defense",5),"POINT_DEFENSE",0)
            else:
                calib=str(row.get("caliber","medium"));vals=wb.get(typ) or {};basev=vals.get(calib)
                if basev is None:raise EngineError(f"COMBAT_WEAPON_UNKNOWN:{typ}/{calib}")
                basev=_finite_num(basev,"WEAPON_BASE",0)
            fadd=count*basev*src*af*integ;fire+=fadd;weapon_breakdown.append({"type":typ,"caliber":row.get("caliber"),"count":count,"source_factor":src,"self_origin":self_origin,"age_years":wage,"age_factor":af,"age_decay_disabled":True,"integrity":integ,"repair_completed":repaired,"secondhand_discount_applied":False if player_force else None,"fire":fadd})
        shield_max=0.0;shield_current=0.0;sb=sc.get("shields") or {};sa=sc.get("shield_age") or {};specmodels=sc.get("specific_models") or {};shield_breakdown=[]
        for row in payload.get("shields",[]) or []:
            if not isinstance(row,dict):raise EngineError("COMBAT_SHIELD_OBJECT_REQUIRED")
            model=str(row.get("model")) if row.get("model") is not None else None;spec=specmodels.get(model) if model else None;cls=str(row.get("class")) if row.get("class") is not None else None
            if isinstance(spec,dict):
                spec_cls=str(spec.get("class"));
                if cls is not None and cls!=spec_cls:raise EngineError(f"COMBAT_SHIELD_MODEL_CLASS_MISMATCH:{model}:{cls}!={spec_cls}")
                cls=spec_cls
            if cls is None:raise EngineError("COMBAT_SHIELD_CLASS_REQUIRED")
            basev=sb.get(cls)
            if basev is None:raise EngineError(f"COMBAT_SHIELD_CLASS_UNKNOWN:{cls}")
            count=_finite_num(row.get("count",1),"COUNT",0);src=_finite_num(row.get("source_factor",source),"SOURCE_FACTOR",0,1)
            if src>ext_top+1e-12 and abs(src-1.0)>1e-12:raise EngineError(f"COMBAT_COMPONENT_SOURCE_FACTOR_INVALID:{src}")
            if "self_owned" in row:raise EngineError("COMBAT_SELF_OWNED_AMBIGUOUS_USE_SELF_ORIGIN")
            if "self_origin" in row:self_origin=_self_origin(row)
            else:self_origin=abs(src-1.0)<=1e-12
            if self_origin and abs(src-1.0)>1e-12:raise EngineError("COMBAT_SELF_ORIGIN_SOURCE_FACTOR_MISMATCH")
            if (not self_origin) and src>ext_top+1e-12:raise EngineError("COMBAT_EXTERNAL_ORIGIN_SOURCE_FACTOR_MISMATCH")
            sage=_finite_num(row.get("age_years",age),"SHIELD_AGE_METADATA",0);q,repaired=_combat_integrity(row,"INTEGRITY",player_force)
            af=1.0
            if "model_factor" in row:mf=_finite_num(row.get("model_factor"),"MODEL_FACTOR",0,1)
            elif isinstance(spec,dict):mf=_finite_num(spec.get("default_performance"),"MODEL_FACTOR",0,1)
            else:mf=1.0
            if isinstance(spec,dict) and isinstance(spec.get("performance_range"),list) and len(spec["performance_range"])==2:
                lo=float(spec["performance_range"][0]);hi=float(spec["performance_range"][1])
                if not lo<=mf<=hi:raise EngineError(f"COMBAT_SHIELD_MODEL_FACTOR_OUTSIDE_RANGE:{model}")
            mx=count*_finite_num(basev,"SHIELD_BASE",0)*src*af*mf;cur=mx*q;shield_max+=mx;shield_current+=cur;shield_breakdown.append({"model":model,"class":cls,"count":count,"source_factor":src,"self_origin":self_origin,"age_years":sage,"age_factor":af,"model_factor":mf,"integrity":q,"repair_completed":repaired,"max":mx,"current":cur})
        dmax=hull_max+shield_max;dcur=hull_max*hull_integrity+shield_current
        if not detailed:
            oi=_finite_num(payload.get("overall_integrity",1.0),"OVERALL_INTEGRITY",0,1);fire*=oi;burst*=oi;dcur=dmax*oi
        c=0.0 if fire<=0 or dcur<=0 else 2.0*fire*dcur/(fire+dcur)
        res={"kind":"ship","F":fire,"D_max":dmax,"D_current":dcur,"C":c,"missile_burst":burst,"hull_base":base_hull,"hull_age_factor":haf,"hull_age_decay_disabled":True,"hull_integrity":hull_integrity,"hull_repair_completed":hull_repaired,"hull_max":hull_max,"shield_max":shield_max,"weapon_breakdown":weapon_breakdown,"shield_breakdown":shield_breakdown}
    else:raise EngineError("COMBAT_KIND_INVALID")
    out={"engine_version":ENGINE_VERSION,"packet":"COMBAT_CALC_V2","status":"READY","game_time":read_json(base/"state.json").get("game_time"),"result":res,"authority":{"world_sha256":_authority_world_sha256(base),"state_sha256":sha256_file(base/"state.json")}}
    _combat_cache(base,kind,payload,out);return out

def _time_category(path:str, text:str, queued:bool=False)->str:
    p=path.lower(); raw=text.lower(); parts=raw.split("⟦t⟧",1); pre=parts[0];post=parts[1] if len(parts)>1 else ""
    if queued and ("activation" in p or "activation_condition" in p):return "activation_time"
    # Explicit future task clocks are deterministic scheduler candidates, not historical prose.
    # This prevents a valid-looking AI review ACK from accidentally skipping a settlement/review boundary.
    if any(k in p for k in ["next_review_at","next_settlement_at","unrest_end_sealed_at","scheduled_at","activation_at","effective_at"]):return "scheduled_timepoint"
    if any(k in p for k in ["deadline","due","expiry","until"]):return "deadline"
    if any(k in p for k in ["eta","expected_arrival","arrival_window","completion_window"]):return "eta"
    if any(k in p for k in ["window","decision_gate"]):return "decision_window"
    deadline_cues=["硬截止","截止","到期","最迟","观察窗至","观察窗口至","期限至","有效期至","若至"]
    eta_cues=["预计","返抵","抵达","到达","完工窗口","完工","eta","约"]
    dpos=max([pre.rfind(k) for k in deadline_cues]+[-1]); epos=max([pre.rfind(k) for k in eta_cues]+[-1])
    if dpos>=0 and dpos>epos:return "deadline"
    if epos>=0:return "eta"
    if any(k in post[:12] for k in ["返抵","抵达","到达","完工"]):return "eta"
    return "historical_reference"


def _extract_times(obj:Any,path:str="",queued:bool=False,default_year:Optional[int]=None)->List[dict]:
    out=[]
    if isinstance(obj,dict):
        for k,v in obj.items():out.extend(_extract_times(v,f"{path}/{k}",queued,default_year))
    elif isinstance(obj,list):
        for i,v in enumerate(obj):out.extend(_extract_times(v,f"{path}/{i}",queued,default_year))
    elif isinstance(obj,str):
        occupied=[]
        for m in ABS_TIME_RE.finditer(obj):
            sec=m.group(3) or "00";iso=f"{m.group(1)}T{m.group(2)}:{sec}"
            lo=max(0,m.start()-45);hi=min(len(obj),m.end()+45);ctx=obj[lo:hi];cue=obj[max(0,m.start()-30):m.start()]+" ⟦T⟧ "+obj[m.end():min(len(obj),m.end()+12)];occupied.append((m.start(),m.end()))
            out.append({"path":path,"time":iso,"source_text":m.group(0),"context":ctx,"category":_time_category(path,cue,queued),"year_inferred":False})
        if default_year is not None:
            for m in SHORT_TIME_RE.finditer(obj):
                if any(not (m.end()<=a or m.start()>=b) for a,b in occupied):continue
                sec=m.group(3) or "00";iso=f"{default_year:04d}-{m.group(1)}T{m.group(2)}:{sec}"
                lo=max(0,m.start()-45);hi=min(len(obj),m.end()+45);ctx=obj[lo:hi];cue=obj[max(0,m.start()-30):m.start()]+" ⟦T⟧ "+obj[m.end():min(len(obj),m.end()+12)]
                out.append({"path":path,"time":iso,"source_text":m.group(0),"context":ctx,"category":_time_category(path,cue,queued),"year_inferred":True})
    return out

def _extract_thresholds(obj:Any,path:str="")->List[dict]:
    out=[]
    if isinstance(obj,dict):
        for k,v in obj.items():
            kp=f"{path}/{k}"
            lk=str(k).lower()
            if any(s in lk for s in ["threshold","deadline","window","eta","return_deadline","activation_condition"]):
                out.append({"path":kp,"value":v})
            out.extend(_extract_thresholds(v,kp))
    elif isinstance(obj,list):
        for i,v in enumerate(obj):out.extend(_extract_thresholds(v,f"{path}/{i}"))
    return out



def _review_source_identity(base: Path) -> str:
    auth=validate_authority_set(base)
    if auth:return str(auth.get("save_set_id") or _authority_fingerprint(base))
    return "FP-"+_authority_fingerprint(base)[:32]


def _review_contract(base: Path, state: dict, reviews: List[dict], now: dt.datetime,
                     target: Optional[dt.datetime], known_events: List[dict]) -> dict:
    if not reviews: return {}
    ceiling=now+dt.timedelta(seconds=TASK_REVIEW_MAX_WINDOW_SECONDS)
    if target is not None:ceiling=min(ceiling,target)
    for ev in known_events:
        tt=parse_iso(ev.get("time")) if isinstance(ev,dict) and ev.get("time") else None
        if tt is not None and tt>=now:ceiling=min(ceiling,tt)
    task_ids=sorted(str(r.get("task_id")) for r in reviews if r.get("task_id"))
    sid=_review_source_identity(base);base_time=state.get("game_time");max_iso=ceiling.strftime("%Y-%m-%dT%H:%M:%S")
    raw="|".join([REVIEW_ACK_FORMAT,sid,str(base_time),max_iso,",".join(task_ids)])
    token=sha256_bytes(raw.encode("utf-8"))
    return {
        "format":REVIEW_ACK_FORMAT,"contract_token":token,"base_save_set_id":sid,"base_game_time":base_time,
        "task_ids":task_ids,"max_review_through":max_iso,"reviewed_through":None,"semantic_events":[],
        "instruction":"AI reviews exactly these tasks from base_game_time through no later than max_review_through. If a semantic state-changing event occurs earlier, set reviewed_through to that earliest event time and include only simultaneous earliest semantic_events. Otherwise set reviewed_through=max_review_through. This ACK is runtime-only and is never a Project authority file."
    }


def _validate_review_ack(path: Path, contract: dict, now: dt.datetime) -> dict:
    obj=strict_json_load(path)
    if obj.get("format")!=REVIEW_ACK_FORMAT:raise EngineError("TASK_REVIEW_ACK_FORMAT_INVALID")
    for k in ["contract_token","base_save_set_id","base_game_time","max_review_through"]:
        if obj.get(k)!=contract.get(k):raise EngineError(f"TASK_REVIEW_ACK_{k.upper()}_MISMATCH")
    ids=obj.get("task_ids")
    if not isinstance(ids,list) or sorted(ids)!=contract.get("task_ids") or len(ids)!=len(set(ids)):
        raise EngineError("TASK_REVIEW_ACK_TASK_SET_MISMATCH")
    rt=parse_iso(obj.get("reviewed_through"));mx=parse_iso(contract.get("max_review_through"))
    if rt is None or mx is None or rt<now or rt>mx:raise EngineError("TASK_REVIEW_ACK_REVIEWED_THROUGH_OUT_OF_RANGE")
    sem=obj.get("semantic_events") or []
    if not isinstance(sem,list) or len(sem)>64:raise EngineError("TASK_REVIEW_ACK_SEMANTIC_EVENTS_INVALID")
    # Contract semantics are strict: an early review stop is only valid when the
    # ACK identifies the simultaneous earliest semantic boundary that caused it.
    if not sem and rt!=mx:raise EngineError("TASK_REVIEW_ACK_EARLY_STOP_REQUIRES_SEMANTIC_EVENT")
    out=[];allowed=set(ids);seen_event_ids=set()
    for i,e in enumerate(sem):
        if not isinstance(e,dict):raise EngineError(f"TASK_REVIEW_ACK_EVENT_INVALID:{i}")
        tid=e.get("task_id");et=parse_iso(e.get("time"));sev=e.get("severity");typ=e.get("event_type")
        if tid not in allowed:raise EngineError(f"TASK_REVIEW_ACK_EVENT_TASK_INVALID:{i}")
        if et is None or et!=rt:raise EngineError(f"TASK_REVIEW_ACK_EVENT_TIME_MUST_EQUAL_REVIEWED_THROUGH:{i}")
        if sev not in {"routine","notable","important","critical"}:raise EngineError(f"TASK_REVIEW_ACK_EVENT_SEVERITY_INVALID:{i}")
        if not isinstance(typ,str) or not typ.strip():raise EngineError(f"TASK_REVIEW_ACK_EVENT_TYPE_INVALID:{i}")
        if "requires_player_decision" in e and not isinstance(e.get("requires_player_decision"),bool):raise EngineError(f"TASK_REVIEW_ACK_EVENT_DECISION_FLAG_INVALID:{i}")
        rpd=e.get("requires_player_decision",False)
        eid=f"TM-{tid}-{sha256_bytes((contract['contract_token']+'|'+str(tid)+'|'+e['time']+'|'+typ).encode())[:12]}"
        if eid in seen_event_ids:raise EngineError(f"TASK_REVIEW_ACK_EVENT_DUPLICATE:{i}")
        seen_event_ids.add(eid)
        out.append({"event_id":eid,"source_task_id":tid,"title":e.get("title"),"time":e["time"],"event_type":typ,"severity":sev,"requires_simulation":True,"requires_player_decision":rpd,"source":"task_monitor_review","note":"AI-declared earliest semantic boundary within a validated Task Review contract; concrete authoritative changes must still be committed through Safe Apply/transact."})
    return {"reviewed_through":rt,"semantic_events":out,"raw":obj}


def _earliest_causal_event(events: List[dict], now: Optional[dt.datetime], horizon: Optional[dt.datetime]) -> Optional[dict]:
    candidates=[]
    for ev in events:
        if not isinstance(ev,dict) or not ev.get("requires_simulation"):continue
        tt=parse_iso(ev.get("time")) if ev.get("time") else None
        if tt is None:continue
        if now is not None and tt<now:continue
        if horizon is not None and tt>horizon:continue
        candidates.append(ev)
    return min(candidates,key=lambda x:(x.get("time") or "9999",x.get("event_id") or "")) if candidates else None


def _event_should_interrupt(severity: str, mode: str, severity_rules: dict, explicit_level: Optional[str], task_policy: Optional[dict] = None) -> bool:
    # A user's explicit per-turn threshold is the highest-precedence runtime instruction.
    if explicit_level is not None:return _severity_rank(severity)>=_severity_rank(explicit_level)
    # Task-local policy can narrow/widen the default for task-sourced events.
    if isinstance(task_policy,dict):
        key="hard_interrupt_severity" if mode=="until" else "minimum_interrupt_severity"
        level=task_policy.get(key)
        if level in {"routine","notable","important","critical"}:return _severity_rank(severity)>=_severity_rank(level)
    cfg=severity_rules.get(str(severity),{}) if isinstance(severity_rules,dict) else {}
    if mode=="until":
        if isinstance(cfg,dict) and "hard_endpoint_interrupt" in cfg:return bool(cfg.get("hard_endpoint_interrupt"))
        return str(severity)=="critical"
    if isinstance(cfg,dict) and "event_mode_interrupt" in cfg:return bool(cfg.get("event_mode_interrupt"))
    return _severity_rank(severity)>=_severity_rank("important")


def turn_packet(base:Path, mode:str="event", until:Optional[str]=None, interrupt_level:Optional[str]=None,
                detail:str="compact", review_ack_path:Optional[Path]=None)->dict:
    ready=ensure_source_ready(base);state=read_json(base/"state.json");tasks=read_json(base/"tasks.json");world=_authority_world_text(base);now=parse_iso(state.get("game_time"))
    if mode not in {"event","until","preview"}:raise EngineError("TURN_MODE_INVALID")
    target=parse_iso(until) if until else None
    requested_target=target;target=_advance_cap(state,target if target else (now+dt.timedelta(hours=24) if now and _mobile_contract(state) else None))
    if mode=="until" and requested_target is None:raise EngineError("TURN_UNTIL_REQUIRED")
    if target and now and target<now:raise EngineError("TURN_UNTIL_BEFORE_GAME_TIME")
    if interrupt_level is not None and interrupt_level not in {"routine","notable","important","critical"}:raise EngineError("TURN_INTERRUPT_LEVEL_INVALID")
    explicit_interrupt_level=interrupt_level;rules=load_runtime_rules(base);severity_rules=(rules.get("event_severity") or {}) if isinstance(rules,dict) else {};reported_level=interrupt_level or ("important" if mode in {"event","preview"} else "critical")
    future=[];historical=[];task_by_id={};effective_policy={};full=detail=="full"
    def classify_points(t,queued=False):
        pts=_extract_times(t,"",queued,now.year if now else None);seen=set();out=[]
        for x in pts:
            when=parse_iso(x["time"]);rel="unknown"
            if when and now and x.get("year_inferred"):
                candidates=[]
                for yy in [now.year-1,now.year,now.year+1]:
                    if yy<1 or yy>9999:continue
                    try:candidates.append(when.replace(year=yy))
                    except ValueError:pass
                if candidates:when=min(candidates,key=lambda z:abs((z-now).total_seconds()));x["time"]=when.strftime("%Y-%m-%dT%H:%M:%S")
            if when and now:rel="past" if when<now else ("now" if when==now else "future");x["seconds_from_now"]=(when-now).total_seconds()
            x.update({"task_id":t.get("task_id"),"title":t.get("title"),"relation":rel});key=(x.get("task_id"),x.get("time"),x.get("path"),x.get("category"))
            if key in seen:continue
            seen.add(key);out.append(x)
            if rel in {"future","now"} and x.get("category")!="historical_reference":future.append(x)
            else:historical.append(x)
        return out
    full_active=[];full_queued=[]
    for t in tasks.get("active_tasks",[]):
        tid=t.get("task_id");task_by_id[tid]=t;effective_policy[tid]=effective_runtime_policy(tasks,t);pts=classify_points(t,False)
        if full:
            _surf=_task_surface(t,state,False);_surf.update({"runtime_policy":effective_policy[tid],"retrieval_route":t.get("retrieval_route"),"timepoints":pts,"decision_gate":t.get("decision_gate"),"autonomy":t.get("autonomy")});full_active.append(_surf)
    for t in tasks.get("queued_tasks",[]):
        tid=t.get("task_id");task_by_id[tid]=t;effective_policy[tid]=effective_runtime_policy(tasks,t);pts=classify_points(t,True)
        if full:full_queued.append({"task_id":tid,"title":t.get("title"),"priority":t.get("priority"),"status":t.get("status"),"phase":t.get("phase"),"activation_condition":t.get("activation_condition"),"runtime_policy":effective_policy[tid],"retrieval_route":t.get("retrieval_route"),"timepoints":pts})
    uniq={}
    for x in future:
        key=(x["task_id"],x["time"],x["category"])
        if key not in uniq:
            task=task_by_id.get(x["task_id"]) or {};sev=str((effective_policy.get(x["task_id"]) or {}).get("scheduled_event_severity") or "routine")
            if x.get("category") in {"deadline","decision_window"} and _severity_rank(sev)<_severity_rank("notable"):sev="notable"
            mon=_task_monitor(tasks,task); resolver=str(mon.get("resolver") or "")
            deterministic=bool(mon.get("requires_ai_review") is False and resolver in DETERMINISTIC_RESOLVERS)
            uniq[key]={"event_id":f"TP-{x['task_id']}-{sha256_bytes((x['time']+x['category']).encode())[:10]}","source_task_id":x["task_id"],"title":x.get("title"),"time":x["time"],"event_type":x["category"],"severity":sev,"requires_simulation":not deterministic,"deterministic_resolver":resolver if deterministic else None,"source":"task_timepoint","paths":[x.get("path")],"contexts":[x.get("context")]}
        elif x.get("path") not in uniq[key]["paths"]:uniq[key]["paths"].append(x.get("path"))
    task_events=list(uniq.values())
    if now is not None:task_events+=_story_preview_events(state,tasks,now,target or now+dt.timedelta(days=30))
    mhorizon=target if target is not None else (now+dt.timedelta(days=30) if now else None)
    maintenance_events=[]
    if now is not None and mhorizon is not None:
        for ev in maintenance_event_queue(state,now,mhorizon):
            maintenance_events.append({'event_id':f"MAINT-{ev.get('job_id')}",'source_job_id':ev.get('job_id'),'title':ev.get('title'),'time':ev.get('time'),'event_type':'maintenance_completion','severity':'routine','requires_simulation':False,'deterministic_resolver':'maintenance_completion_v1','source':'maintenance_runtime','maintenance_kind':ev.get('maintenance_kind')})
    reviews=task_monitor_queue(tasks,now,target,state=state);next_hazards=next_long_horizon_candidates(state,rules);latent_all=latent_process_candidates(state,target if target else None)
    known_events=task_events+maintenance_events+[{**ev,"source":"long_horizon"} for ev in next_hazards]+latent_all
    contract=_review_contract(base,state,reviews,now,target,known_events) if reviews and now else {}
    ack=None;semantic_events=[];review_ack_applied=False
    if review_ack_path is not None:
        if not reviews:raise EngineError("TASK_REVIEW_ACK_UNEXPECTED_NO_DUE_REVIEWS")
        ack=_validate_review_ack(Path(review_ack_path),contract,now);semantic_events=ack["semantic_events"];review_ack_applied=True
    if reviews and not review_ack_applied:
        effective_target=parse_iso(contract.get("max_review_through")) if contract else now
        lh={"status":"DEFERRED_UNTIL_TASK_REVIEW","requested_until":target.strftime("%Y-%m-%dT%H:%M:%S") if target else None,"processed_until":state.get("game_time"),"events":next_hazards,"clock_updates":{},"truncated":False,"continuation_required":False,"method":"stage1_review_contract"}
        latent=latent_process_candidates(state,effective_target) if effective_target else []
        def decorate_stage1(events):
            arr=sorted(events,key=lambda x:(x.get("time") or "9999",x.get("event_id") or ""))
            if effective_target is not None:arr=[x for x in arr if parse_iso(x.get("time")) is not None and parse_iso(x["time"])<=effective_target]
            for ev in arr:
                tp=effective_policy.get(ev.get("source_task_id")) if ev.get("source_task_id") else None
                ev["interrupt"]=_event_should_interrupt(ev.get("severity"),mode,severity_rules,explicit_interrupt_level,tp)
            return arr
        timeline=decorate_stage1(task_events+maintenance_events+[{**ev,"source":"long_horizon"} for ev in next_hazards]+latent)
        public_lh=lh if full else {"status":lh["status"],"requested_until":lh["requested_until"],"processed_until":lh["processed_until"],"truncated":False,"continuation_required":False,"method":lh["method"],"event_count":len(next_hazards)}
        out = {
            "engine_version": ENGINE_VERSION,
            "packet": "TURN_FRAME_V4",
            "phase": "AI_REVIEW_REQUIRED",
            "game_time": state.get("game_time"),
            "voyage_day": state.get("voyage_day"),
            "summary": state.get("summary"),
            "source_ready": ready,
            "advance_request": {
                "mode": mode,
                "original_until":requested_target.isoformat() if requested_target else None,"clamped_to_24h":requested_target is not None and target!=requested_target,
                "hard_end": target.strftime("%Y-%m-%dT%H:%M:%S") if target else None,
                "interrupt_level": reported_level,
                "interrupt_source": "explicit" if explicit_interrupt_level else "world_default",
            },
            "planning_horizon": effective_target.strftime("%Y-%m-%dT%H:%M:%S") if effective_target else state.get("game_time"),
            "planning_status": "AI_REVIEW_REQUIRED",
            "continuation_required": False,
            "active_task_count": len(tasks.get("active_tasks", [])),
            "queued_task_count": len(tasks.get("queued_tasks", [])),
            "ai_review_required": True,
            "task_review_queue": reviews,
            "task_review_contract": contract,
            "review_ack_applied": False,
            "candidate_events": timeline,
            "causal_replan_barrier": None,
            "causal_replan_barriers": [],
            "next_interrupt_candidate": next((x for x in timeline if x.get("interrupt")), None),
            "historical_time_reference_count": len(historical),
            "long_horizon": public_lh,
            "random_event_check_required": True,
            "precommit_rule": "Do not advance authoritative time until the exact Task Review contract has a valid runtime ACK and stage-2 deterministic planning has been rebuilt.",
            "note": "Stage 1 only. AI reviews the bounded contract window; Review ACK is runtime-only and does not itself mutate authority files.",
        }
        if full:out.update({"active_tasks":full_active,"queued_tasks":full_queued,"historical_time_references":historical[:50]})
        return out

    # Stage 2 or no-review path. A validated ACK caps deterministic planning to the
    # interval actually reviewed by AI. Any requires_simulation event is a causal
    # barrier regardless of whether it interrupts the player.
    planning_cap=ack["reviewed_through"] if ack is not None else target
    all_next=task_events+maintenance_events+semantic_events+[{**ev,"source":"long_horizon"} for ev in next_hazards]+latent_all
    causal=_earliest_causal_event(all_next,now,planning_cap)
    causal_time=parse_iso(causal.get("time")) if causal else None
    effective_target=causal_time if causal_time is not None else planning_cap
    if effective_target is not None:
        clock_count=len((((state.get("engine_runtime") or {}).get("long_horizon") or {}).get("hazard_clocks") or {}))
        lh=preview_long_horizon(state,rules,effective_target,max_events=max(24,clock_count+4))
        effective_target=parse_iso(lh.get("processed_until")) or effective_target
    else:
        lh={"status":"READY","until":None,"processed_until":None,"events":next_hazards,"clock_updates":{},"truncated":False,"continuation_required":False,"method":"next_candidate_per_clock"}
    latent=latent_process_candidates(state,effective_target) if effective_target else latent_all
    timeline_events=task_events+maintenance_events+semantic_events+[{**ev,"source":"long_horizon"} for ev in lh.get("events",[])]+latent
    def decorate(events: List[dict], horizon: Optional[dt.datetime]) -> Tuple[List[dict],Optional[dict]]:
        arr=sorted(events,key=lambda x:(x.get("time") or "9999",x.get("event_id") or ""))
        if horizon is not None:arr=[x for x in arr if not x.get("time") or (parse_iso(x["time"]) is not None and parse_iso(x["time"])<=horizon)]
        for ev in arr:
            tp=effective_policy.get(ev.get("source_task_id")) if ev.get("source_task_id") else None
            ev["interrupt"]=bool(ev.get("requires_player_decision")) or _event_should_interrupt(ev.get("severity"),mode,severity_rules,explicit_interrupt_level,tp)
        return arr,next((x for x in arr if x.get("interrupt")),None)
    timeline,next_interrupt=decorate(timeline_events,effective_target)
    causal_barrier=_earliest_causal_event(timeline,now,effective_target)
    # Safety clamp if a non-simulation interrupt ever appears earlier than the causal cap.
    stop_time=parse_iso(next_interrupt.get("time")) if next_interrupt else None
    if stop_time and (effective_target is None or stop_time<effective_target):
        effective_target = stop_time
        clock_count = len((((state.get("engine_runtime") or {}).get("long_horizon") or {}).get("hazard_clocks") or {}))
        lh = preview_long_horizon(state, rules, effective_target, max_events=max(24, clock_count + 4))
        latent = latent_process_candidates(state, effective_target)
        timeline, next_interrupt = decorate(
            task_events + maintenance_events + semantic_events + [{**ev, "source": "long_horizon"} for ev in lh.get("events", [])] + latent,
            effective_target,
        )
        causal_barrier = _earliest_causal_event(timeline, now, effective_target)
    causal_barriers=[]
    if causal_barrier and causal_barrier.get("time"):
        causal_barriers=[x for x in timeline if isinstance(x,dict) and x.get("requires_simulation") and x.get("time")==causal_barrier.get("time")]
    mechanical_cont=bool(lh.get("continuation_required"))
    target_cont=bool(target is not None and effective_target is not None and effective_target<target)
    review_window_cont=bool(ack is not None and mode in {"event","preview"} and causal_barrier is None and effective_target==ack["reviewed_through"])
    causal_cont=bool(causal_barrier is not None and not (next_interrupt and next_interrupt.get("time")==causal_barrier.get("time")))
    continuation=mechanical_cont or target_cont or review_window_cont or causal_cont
    if next_interrupt and causal_barrier and next_interrupt.get("time")==causal_barrier.get("time"):planning_status="STOP_CANDIDATE"
    elif causal_barrier:planning_status="CAUSAL_REPLAN_REQUIRED"
    elif review_window_cont:planning_status="QUIET_REVIEW_CHUNK"
    elif mechanical_cont:planning_status="TRUNCATED_LONG_HORIZON"
    else:planning_status="READY"
    public_lh=lh if full else {k:lh.get(k) for k in ["status","requested_until","processed_until","until","truncated","continuation_required","method"] if k in lh}
    if not full:public_lh["event_count"]=len(lh.get("events",[]) or [])
    out = {
        "engine_version": ENGINE_VERSION,
        "packet": "TURN_FRAME_V4",
        "phase": "DETERMINISTIC_PLAN_READY",
        "game_time": state.get("game_time"),
        "voyage_day": state.get("voyage_day"),
        "summary": state.get("summary"),
        "source_ready": ready,
        "advance_request": {
            "mode": mode,
            "original_until":requested_target.isoformat() if requested_target else None,"clamped_to_24h":requested_target is not None and target!=requested_target,
                "hard_end": target.strftime("%Y-%m-%dT%H:%M:%S") if target else None,
            "interrupt_level": reported_level,
            "interrupt_source": "explicit" if explicit_interrupt_level else "world_default",
        },
        "planning_horizon": effective_target.strftime("%Y-%m-%dT%H:%M:%S") if effective_target else None,
        "planning_status": planning_status,
        "continuation_required": continuation,
        "active_task_count": len(tasks.get("active_tasks", [])),
        "queued_task_count": len(tasks.get("queued_tasks", [])),
        "ai_review_required": False,
        "task_review_queue": [],
        "task_review_contract": contract or None,
        "review_ack_applied": review_ack_applied,
        "semantic_review_events": semantic_events,
        "candidate_events": timeline,
        "causal_replan_barrier": causal_barrier,
        "causal_replan_barriers": causal_barriers,
        "next_interrupt_candidate": next_interrupt,
        "historical_time_reference_count": len(historical),
        "long_horizon": public_lh,
        "random_event_check_required": True,
        "precommit_rule": "Advance/save only to planning_horizon; if a causal_replan_barrier exists, resolve and commit it before planning beyond that time. Due Task Monitor.last_reviewed_at must equal the actual committed game_time.",
        "note": "Stage 2 uses a validated Task Review ACK when semantic monitors were due. Every requires_simulation event is a causal replanning barrier even when it does not interrupt the player.",
    }
    if full:out.update({"active_tasks":full_active,"queued_tasks":full_queued,"historical_time_references":historical[:50]})
    return out

def json_diff_paths(a:Any,b:Any,prefix:str="",limit:int=200)->Tuple[List[str],bool]:
    out=[]; truncated=False
    def rec(x,y,p):
        nonlocal truncated
        if len(out)>=limit:
            truncated=True;return
        if type(x)!=type(y):out.append(f"{p}: type {type(x).__name__}->{type(y).__name__}");return
        if isinstance(x,dict):
            keys=sorted(set(x)|set(y))
            for k in keys:
                if len(out)>=limit:truncated=True;return
                np=f"{p}/{k}"
                if k not in x:out.append(f"{np}: +")
                elif k not in y:out.append(f"{np}: -")
                else:rec(x[k],y[k],np)
        elif isinstance(x,list):
            if len(x)!=len(y):out.append(f"{p}: len {len(x)}->{len(y)}")
            for i,(xx,yy) in enumerate(zip(x,y)):
                if len(out)>=limit:truncated=True;return
                rec(xx,yy,f"{p}/{i}")
        elif x!=y:out.append(f"{p}: {x!r}->{y!r}")
    rec(a,b,prefix or "")
    return out,truncated


def diff_dirs(a:Path,b:Path,limit:int=200)->dict:
    remaining=limit; changes={}; truncated=False
    for fn in AUTH_FILES:
        pa=a/fn;pb=b/fn
        if not pa.is_file() or not pb.is_file():
            changes[fn]={"status":"missing","from":pa.is_file(),"to":pb.is_file()};continue
        if sha256_file(pa)==sha256_file(pb):
            changes[fn]={"status":"unchanged"};continue
        if fn in {"state.json","tasks.json"}:
            arr,tr=json_diff_paths(read_json(pa),read_json(pb),limit=max(0,remaining)); remaining-=len(arr); truncated=truncated or tr
            changes[fn]={"status":"changed","paths":arr,"truncated":tr}
        elif fn=="events.jsonl":
            _,ea,ra=read_history_raw(pa);_,eb,rb=read_history_raw(pb)
            prefix=0
            for x,y in zip(ra,rb):
                if x==y:prefix+=1
                else:break
            changes[fn]={"status":"changed","events_from":len(ea),"events_to":len(eb),"identical_prefix_events":prefix,"append_only":prefix==len(ea) and len(eb)>=len(ea)}
        else:
            ta=pa.read_text(encoding="utf-8").splitlines();tb=pb.read_text(encoding="utf-8").splitlines()
            changes[fn]={"status":"changed","lines_from":len(ta),"lines_to":len(tb),"sha_from":sha256_file(pa),"sha_to":sha256_file(pb)}
        if remaining<=0:truncated=True
    return {"from":str(a),"to":str(b),"limit":limit,"truncated":truncated,"changes":changes}



