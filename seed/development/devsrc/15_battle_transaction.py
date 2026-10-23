# === VOYAGER_DEV_MODULE: battle_transaction ===
def battleprepare(payload:dict,base:Path=ROOT)->dict:
    """Compile authority-backed battle intent into an immutable mechanical snapshot.

    The caller may choose participants and tactics, but may not supply combat numbers.
    All mechanical values must be read from current STATE/sealed profiles and every
    equipment model must already exist in the WORLD/STATE combat catalog.
    """
    ensure_source_ready(base);state=read_json(base/'state.json');auth=validate_authority_set(base) or {}
    current_sid=str(auth.get('save_set_id') or '')
    requested_sid=str(payload.get('base_save_set_id') or current_sid)
    if not current_sid or requested_sid!=current_sid:raise EngineError(f'BATTLE_PREPARE_STALE_BASE:{requested_sid}!={current_sid}')
    cr=(((state.get('engine_runtime') or {}).get('combat_runtime') or {}));seq=int(cr.get('next_battle_sequence',1) or 1)
    battle_id=str(payload.get('battle_id') or f'BTL-{seq:06d}').strip()
    if not battle_id:raise EngineError('BATTLE_ID_REQUIRED')
    committed=(cr.get('battle_commits') or {}) if isinstance(cr,dict) else {}
    if battle_id in committed:raise EngineError(f'BATTLE_ALREADY_COMMITTED:{battle_id}')
    sides_in=payload.get('sides') or {}
    if not isinstance(sides_in,dict) or len(sides_in)!=2:raise EngineError('BATTLE_REQUIRES_TWO_SIDES')
    rr=load_runtime_rules(base);cfg=((rr.get('combat_evaluation') or {}).get('battle_resolution') or {})
    range_mods=cfg.get('range_modifiers') or {};range_band=str(payload.get('range_band') or 'medium')
    if range_band not in range_mods:raise EngineError(f'BATTLE_RANGE_BAND_INVALID:{range_band}')
    tactics=cfg.get('tactical_modifiers') or {'TACTIC_STANDARD':{'attack_modifier':1.0,'accuracy_modifier':1.0,'defense_modifier':1.0}}
    catalog=_combat_catalog(base,state);mechanical={};sources={};checks=[]
    sealed_profiles=((((state.get('engine_runtime') or {}).get('combat_runtime') or {}).get('sealed_profiles') or {}))
    for sid0,srec in sides_in.items():
        sid=str(sid0)
        if not isinstance(srec,dict):raise EngineError(f'BATTLE_SIDE_INVALID:{sid}')
        if BATTLE_DIRECT_NUMERIC_FIELDS & set(srec):raise EngineError(f'BATTLE_DIRECT_MECHANICAL_INPUT_FORBIDDEN:{sid}:{sorted(BATTLE_DIRECT_NUMERIC_FIELDS & set(srec))}')
        src=_battle_force_source(state,sid,srec.get('source') or {});sources[sid]={k:v for k,v in src.items() if k!='record'}
        if src.get('revision') is not None:checks.append({'path':src['authority_path']+'.revision','expected':src['revision']})
        tactic=str(srec.get('tactic_id') or 'TACTIC_STANDARD');tm=tactics.get(tactic)
        if not isinstance(tm,dict):raise EngineError(f'BATTLE_TACTIC_UNREGISTERED:{sid}:{tactic}')
        units_in=srec.get('units') or []
        if not isinstance(units_in,list) or not units_in:raise EngineError(f'BATTLE_UNITS_REQUIRED:{sid}')
        units=[];seen=set()
        for i,u0 in enumerate(units_in):
            if not isinstance(u0,dict):raise EngineError(f'BATTLE_UNIT_INVALID:{sid}:{i}')
            bad=BATTLE_DIRECT_NUMERIC_FIELDS & set(u0)
            if bad:raise EngineError(f'BATTLE_DIRECT_MECHANICAL_INPUT_FORBIDDEN:{sid}:{i}:{sorted(bad)}')
            uid=str(u0.get('unit_id') or u0.get('id') or f'{sid}-{i+1}')
            if uid in seen:raise EngineError(f'BATTLE_UNIT_ID_DUPLICATE:{sid}:{uid}')
            seen.add(uid);profile_id=str(u0.get('sealed_profile_id') or '').strip();unit_checks=[]
            if profile_id:
                prof=sealed_profiles.get(profile_id)
                if not isinstance(prof,dict) or prof.get('status','sealed')!='sealed':raise EngineError(f'BATTLE_PROFILE_UNKNOWN:{sid}:{uid}:{profile_id}')
                pv=prof.get('combat') or {}
                if not isinstance(pv,dict) or 'attack' not in pv or not ({'armor','hull'} & set(pv)):raise EngineError(f'BATTLE_PROFILE_INCOMPLETE:{profile_id}')
                vals={k:copy.deepcopy(v) for k,v in pv.items() if k in BATTLE_PROFILE_FIELDS};ap=str(u0.get('authority_path') or prof.get('authority_path') or '')
                prev=prof.get('source_revision');pap=str(prof.get('authority_path') or '')
                if pap and prev is not None:unit_checks.append({'path':pap+'.revision','expected':prev})
                eq=list(prof.get('equipment_models') or [])+list(u0.get('equipment_models') or [])
            else:
                vals,unit_checks=_battle_read_profile_from_fields(state,u0,sid,uid);ap=str(u0.get('authority_path') or '');eq=list(u0.get('equipment_models') or [])
            canon=[]
            for mid in eq:
                cm=_combat_model_id(catalog,str(mid))
                if cm not in canon:canon.append(cm)
            vals.setdefault('shield',0);vals.setdefault('ammo',0);vals.setdefault('ammo_salvo',0);vals.setdefault('retreat_threshold',float(cfg.get('default_retreat_threshold',0.25)));vals.setdefault('accuracy',1.0);vals.setdefault('evasion',0.0)
            reg_mid=u0.get('registry_equipment_model_id');reg_mid=_combat_model_id(catalog,str(reg_mid)) if reg_mid else None
            if reg_mid and reg_mid not in canon:canon.append(reg_mid)
            vals.update({'unit_id':uid,'authority_path':ap,'equipment_models':canon,'writeback_fields':copy.deepcopy(u0.get('writeback_fields') or {}),'authority_expected':copy.deepcopy(u0.get('authority_expected') or {}),'writeback_allow_create':bool(u0.get('writeback_allow_create',False)),'registry_equipment_model_id':reg_mid})
            units.append(vals);checks.extend(unit_checks)
        mechanical[sid]={'units':units,'attack_modifier':float(tm.get('attack_modifier',1.0)),'accuracy_modifier':float(tm.get('accuracy_modifier',1.0)),'defense_modifier':float(tm.get('defense_modifier',1.0)),'tactic_id':tactic}
    prepare_request=copy.deepcopy(payload);prepare_request['base_save_set_id']=current_sid;prepare_request['battle_id']=battle_id
    snap={'packet':BATTLE_SNAPSHOT_SCHEMA,'engine_version':ENGINE_VERSION,'battle_id':battle_id,'battle_sequence':seq,'base_save_set_id':current_sid,'game_time':state.get('game_time'),'range_band':range_band,'max_rounds':max(1,min(int(cfg.get('max_rounds_cap',100)),int(payload.get('max_rounds') or 20))),'sources':sources,'mechanical_sides':mechanical,'authority_checks':checks,'casualty_resolution_mode':str(cfg.get('personnel_casualty_resolution','semantic_sealed_commit_until_formula_registered')),'catalog_policy':'registered_models_only','prepare_request':prepare_request}
    snap['prepared_token']=_battle_snapshot_digest(snap)
    return snap


def _validate_battle_snapshot(snapshot:dict,base:Path=ROOT)->dict:
    if not isinstance(snapshot,dict) or snapshot.get('packet')!=BATTLE_SNAPSHOT_SCHEMA:raise EngineError('BATTLE_PREPARE_REQUIRED')
    token=str(snapshot.get('prepared_token') or '')
    if not token or token!=_battle_snapshot_digest(snapshot):raise EngineError('BATTLE_SNAPSHOT_TOKEN_INVALID')
    req=snapshot.get('prepare_request')
    if not isinstance(req,dict):raise EngineError('BATTLE_SNAPSHOT_PREPARE_REQUEST_REQUIRED')
    rebuilt=battleprepare(copy.deepcopy(req),base)
    if rebuilt.get('prepared_token')!=token:raise EngineError('BATTLE_SNAPSHOT_NOT_REPRODUCIBLE')
    auth=validate_authority_set(base) or {};sid=str(auth.get('save_set_id') or '')
    if snapshot.get('base_save_set_id')!=sid:raise EngineError(f'BATTLE_SNAPSHOT_STALE_BASE:{snapshot.get("base_save_set_id")}!={sid}')
    state=read_json(base/'state.json')
    cr=(((state.get('engine_runtime') or {}).get('combat_runtime') or {}));committed=cr.get('battle_commits') or {}
    if snapshot.get('battle_id') in committed:raise EngineError(f'BATTLE_ALREADY_COMMITTED:{snapshot.get("battle_id")}')
    for ck in snapshot.get('authority_checks') or []:
        pth=str(ck.get('path') or '')
        if not pth.startswith(('STATE.','state:')):raise EngineError(f'BATTLE_AUTHORITY_CHECK_PATH_INVALID:{pth}')
        try:cur=get_by_path(state,pth[6:])
        except KeyError:raise EngineError(f'BATTLE_AUTHORITY_CHECK_MISSING:{pth}')
        if cur!=ck.get('expected'):raise EngineError(f'BATTLE_AUTHORITY_CHANGED:{pth}:expected={ck.get("expected")!r}:actual={cur!r}')
    for sid0,src in (snapshot.get('sources') or {}).items():
        fid=src.get('force_id')
        if fid:
            force=_battle_force_registry(state).get(fid)
            if not isinstance(force,dict):raise EngineError(f'BATTLE_FORCE_UNKNOWN:{sid0}:{fid}')
            if int(force.get('revision',-1))!=int(src.get('revision',-2)):raise EngineError(f'BATTLE_FORCE_REVISION_MISMATCH:{sid0}:{fid}')
    return snapshot


def _battlecalc_mechanical(payload:dict,base:Path=ROOT)->dict:
    """Deterministic multi-round combat state machine over an already sealed snapshot.

    Each side may provide either one aggregate record or ``units`` with per-unit
    combat state. AI supplies tactical intent/special environment; the Engine
    owns repeatable range, hit, shield, armor/hull, ammo, retreat and loss math.
    """
    battle_id=str(payload.get('battle_id') or '').strip()
    if not battle_id:raise EngineError('BATTLE_ID_REQUIRED')
    sides_in=payload.get('sides') or {}
    if not isinstance(sides_in,dict) or len(sides_in)!=2:raise EngineError('BATTLE_REQUIRES_TWO_SIDES')
    try:
        rr=load_runtime_rules(base) if (base/'rules.json').is_file() and (base/'catalog.json').is_file() else {}
    except Exception:
        rr={}
    cfg=((rr.get('combat_evaluation') or {}).get('battle_resolution') or {}) if isinstance(rr,dict) else {}
    range_mods=cfg.get('range_modifiers') or {'long':0.75,'medium':1.0,'close':1.15}
    range_band=str(payload.get('range_band') or 'medium');range_mod=float(range_mods.get(range_band,1.0))
    base_hit=float(cfg.get('base_hit_probability',0.65));hit_floor=float(cfg.get('hit_probability_floor',0.05));hit_ceiling=float(cfg.get('hit_probability_ceiling',0.98))
    jitter_range=cfg.get('damage_jitter_range') or [0.85,1.15]
    jitter_lo=float(jitter_range[0]);jitter_hi=float(jitter_range[1]);default_retreat=float(cfg.get('default_retreat_threshold',0.25));default_ammo_dmg=float(cfg.get('default_ammo_damage_per_unit',1.0))
    rounds_cap=max(1,int(cfg.get('max_rounds_cap',100)));max_rounds=max(1,min(rounds_cap,int(payload.get('max_rounds') or 20)))
    ammo_damage=float(payload.get('ammo_damage_per_unit',default_ammo_dmg) or default_ammo_dmg)
    try:seed=str(((read_json(base/'state.json').get('engine_runtime') or {}).get('seed_anchor') or 'battle'))
    except Exception:seed='battle'

    def norm_unit(rec:dict,uid:str)->dict:
        armor=max(0.0,float(rec.get('armor') if rec.get('armor') is not None else rec.get('hull',100) or 0))
        return {'unit_id':uid,'attack':max(0.0,float(rec.get('attack') if rec.get('attack') is not None else rec.get('combat_power',0) or 0)),
                'shield':max(0.0,float(rec.get('shield') or 0)),'armor':armor,'initial_armor':armor,
                'ammo':max(0,int(rec.get('ammo') if rec.get('ammo') is not None else rec.get('missile_ammo',0) or 0)),
                'ammo_salvo':max(0,int(rec.get('ammo_salvo') or 0)),
                'retreat_threshold':max(0.0,min(1.0,float(rec.get('retreat_threshold',default_retreat)))),
                'accuracy':max(0.05,min(1.5,float(rec.get('accuracy',1.0)))),'evasion':max(0.0,min(0.9,float(rec.get('evasion',0.0)))),
                'attack_modifier':max(0.0,float(rec.get('attack_modifier',1.0))),'defense_modifier':max(0.05,float(rec.get('defense_modifier',1.0))),
                'retreated':False,'destroyed':armor<=0}

    state={}
    for sid,rec in sides_in.items():
        if not isinstance(rec,dict):raise EngineError('BATTLE_SIDE_INVALID')
        units={};raw_units=rec.get('units')
        if isinstance(raw_units,list) and raw_units:
            for i,u in enumerate(raw_units):
                if not isinstance(u,dict):raise EngineError(f'BATTLE_UNIT_INVALID:{sid}:{i}')
                uid=str(u.get('unit_id') or u.get('id') or f'{sid}-{i+1}')
                if uid in units:raise EngineError(f'BATTLE_UNIT_ID_DUPLICATE:{sid}:{uid}')
                units[uid]=norm_unit(u,uid)
        else:
            uid=f'{sid}-aggregate';units[uid]=norm_unit(rec,uid)
        state[str(sid)]={'units':units,'attack_modifier':max(0.0,float(rec.get('attack_modifier',1.0))),
                         'accuracy_modifier':max(0.05,float(rec.get('accuracy_modifier',1.0))),
                         'defense_modifier':max(0.05,float(rec.get('defense_modifier',1.0)))}
    ids=list(state);rounds=[];winner=None

    def active_units(sid:str)->list:
        return [u for u in state[sid]['units'].values() if u['armor']>0 and not u['retreated']]

    for rnd in range(1,max_rounds+1):
        before=copy.deepcopy(state);incoming={(sid,uid):0.0 for sid in ids for uid in state[sid]['units']};hits=[]
        for att_sid in ids:
            def_sid=ids[1-ids.index(att_sid)];defs=active_units(def_sid)
            if not defs:continue
            for a in active_units(att_sid):
                defs=active_units(def_sid)
                if not defs:break
                tu=deterministic_unit(seed,'battle_target',battle_id,rnd,att_sid,a['unit_id']);target=defs[min(len(defs)-1,int(tu*len(defs)))]
                use=min(a['ammo'],a['ammo_salvo']);a['ammo']-=use
                ammo_bonus=use*ammo_damage
                hp=max(hit_floor,min(hit_ceiling,base_hit*a['accuracy']*state[att_sid]['accuracy_modifier']*range_mod*(1.0-target['evasion'])))
                roll=deterministic_unit(seed,'battle_hit',battle_id,rnd,att_sid,a['unit_id'],target['unit_id']);hit=roll<hp;damage=0.0
                if hit:
                    ju=deterministic_unit(seed,'battle_damage',battle_id,rnd,att_sid,a['unit_id'],target['unit_id']);jitter=jitter_lo+(jitter_hi-jitter_lo)*ju
                    damage=((a['attack']*a['attack_modifier']*state[att_sid]['attack_modifier'])+ammo_bonus)*range_mod*jitter/(target['defense_modifier']*state[def_sid]['defense_modifier'])
                    incoming[(def_sid,target['unit_id'])]+=damage
                hits.append({'attacker_side':att_sid,'attacker_unit':a['unit_id'],'target_side':def_sid,'target_unit':target['unit_id'],'roll':round(roll,8),'hit_probability':round(hp,6),'hit':hit,'ammo_used':use,'raw_damage':round(damage,4)})
        damage_rows=[]
        for sid in ids:
            for uid,u in state[sid]['units'].items():
                dmg=incoming[(sid,uid)];absorbed=min(u['shield'],dmg);u['shield']-=absorbed;remain=max(0.0,dmg-absorbed);u['armor']=max(0.0,u['armor']-remain)
                if u['armor']<=0:u['destroyed']=True
                damage_rows.append({'side':sid,'unit_id':uid,'incoming':round(dmg,4),'shield_absorbed':round(absorbed,4),'armor_damage':round(remain,4)})
        retreats=[]
        for sid in ids:
            for uid,u in state[sid]['units'].items():
                if u['destroyed'] or u['retreated'] or u['initial_armor']<=0:continue
                if u['armor']/u['initial_armor']<=u['retreat_threshold']:
                    u['retreated']=True;retreats.append({'side':sid,'unit_id':uid})
        rounds.append({'round':rnd,'before':before,'hits':hits,'damage':damage_rows,'after':copy.deepcopy(state),'retreat_triggered':retreats})
        remaining={sid:len(active_units(sid)) for sid in ids}
        if remaining[ids[0]]==0 or remaining[ids[1]]==0:
            if remaining[ids[0]]==0 and remaining[ids[1]]==0:winner='disengaged_or_draw'
            else:winner=ids[0] if remaining[ids[0]]>0 else ids[1]
            break
    losses={}
    for sid in ids:
        us=list(state[sid]['units'].values());losses[sid]={'destroyed':sum(1 for u in us if u['destroyed']),'retreated':sum(1 for u in us if u['retreated'] and not u['destroyed']),'combat_capable_remaining':sum(1 for u in us if u['armor']>0 and not u['retreated']),'total_units':len(us),'ammo_remaining':sum(int(u['ammo']) for u in us)}
    return {'packet':'BATTLE_RESOLUTION_V2','engine_version':ENGINE_VERSION,'battle_id':battle_id,'range_band':range_band,'winner':winner or 'unresolved_after_max_rounds','rounds_fought':len(rounds),'losses':losses,'final_state':state,'rounds':rounds,'authority_written':False,'parameters':{'range_modifier':range_mod,'base_hit_probability':base_hit,'damage_jitter_range':[jitter_lo,jitter_hi],'ammo_damage_per_unit':ammo_damage},'note':'Mechanical resolution from BATTLE_SNAPSHOT_V2 only. Commit through battlecommit/battleapply transaction.'}

def battlecalc(payload:dict,base:Path=ROOT)->dict:
    snap=_validate_battle_snapshot(payload,base);rr=load_runtime_rules(base);cfg=((rr.get('combat_evaluation') or {}).get('battle_resolution') or {})
    mech={'battle_id':snap['battle_id'],'range_band':snap['range_band'],'max_rounds':snap.get('max_rounds',20),'ammo_damage_per_unit':float(cfg.get('default_ammo_damage_per_unit',1.0)),'sides':copy.deepcopy(snap.get('mechanical_sides') or {})}
    result=_battlecalc_mechanical(mech,base);result['prepared_token']=snap.get('prepared_token');result['base_save_set_id']=snap.get('base_save_set_id');result['battle_sequence']=snap.get('battle_sequence');return result

def _battle_payload_unit_index(payload:dict)->dict:
    out={}
    sides=(payload.get('mechanical_sides') or payload.get('sides') or {})
    for sid,srec in sides.items():
        units=srec.get('units') if isinstance(srec,dict) else None
        if not isinstance(units,list) or not units:raise EngineError(f'BATTLE_APPLY_REQUIRES_EXPLICIT_UNITS:{sid}')
        for i,u in enumerate(units):
            if not isinstance(u,dict):raise EngineError(f'BATTLE_UNIT_INVALID:{sid}:{i}')
            uid=str(u.get('unit_id') or u.get('id') or f'{sid}-{i+1}');out[(str(sid),uid)]=u
    return out

def _battle_set_relative(obj:dict,path:str,value:Any,allow_create:bool=False)->None:
    parts=[x for x in str(path).split('.') if x]
    if not parts:raise EngineError('BATTLE_WRITEBACK_PATH_EMPTY')
    cur=obj
    for k in parts[:-1]:
        if not isinstance(cur,dict) or k not in cur or not isinstance(cur[k],dict):raise EngineError(f'BATTLE_WRITEBACK_PARENT_MISSING:{path}')
        cur=cur[k]
    key=parts[-1]
    if key not in cur and not allow_create:raise EngineError(f'BATTLE_WRITEBACK_TARGET_MISSING:{path}')
    cur[key]=copy.deepcopy(value)

def _battle_get_relative(obj:dict,path:str)->Any:
    return get_by_path(obj,str(path))

BATTLE_WRITEBACK_FIELDS={"shield","armor","ammo","destroyed","retreated","status"}
BATTLE_SENSITIVE_PATH_TOKENS={
    "funds","gold","grey","balance","bank","finance","financial","price","market","procurement","revenue","income","cost",
    "inventory","inventories","stock","quantity","qty","cargo","personnel","crew","location","navigation","owner","ownership",
    "title","claim","legal","political","reputation","research","task","contract","settlement","sale","purchase"
}
BATTLE_FIELD_PATTERNS={
    "shield": re.compile(r"(?:^|[._-])(?:shield|shields)(?:[._-]|$)",re.I),
    "armor": re.compile(r"(?:^|[._-])(?:armor|armour|hull|structure|structural)(?:[._-]|$)",re.I),
    "ammo": re.compile(r"(?:^|[._-])(?:ammo|ammunition|munition|missile_ammo|missiles_remaining)(?:[._-]|$)",re.I),
    "destroyed": re.compile(r"(?:^|[._-])(?:destroyed|is_destroyed|destroyed_flag)(?:[._-]|$)",re.I),
    "retreated": re.compile(r"(?:^|[._-])(?:retreated|is_retreated|withdrawn|disengaged)(?:[._-]|$)",re.I),
    "status": re.compile(r"(?:^|[._-])(?:combat_status|battle_status|mechanical_status|damage_status|combat_state)(?:[._-]|$)",re.I),
}

def _battle_path_tokens(path:str)->List[str]:
    return [x.lower() for x in re.split(r"[^A-Za-z0-9]+",str(path)) if x]

def _battle_validate_mapping(authority_path:str,std:str,rel:str)->None:
    if std not in BATTLE_WRITEBACK_FIELDS:
        raise EngineError(f"BATTLE_WRITEBACK_FIELD_UNSUPPORTED:{std}")
    full=f"{authority_path}.{rel}"
    toks=set(_battle_path_tokens(full))
    sensitive=sorted(toks & BATTLE_SENSITIVE_PATH_TOKENS)
    if sensitive:
        raise EngineError(f"BATTLE_WRITEBACK_SENSITIVE_PATH:{full}:{','.join(sensitive)}")
    pat=BATTLE_FIELD_PATTERNS[std]
    if not pat.search(str(rel)):
        raise EngineError(f"BATTLE_WRITEBACK_SEMANTIC_PATH_MISMATCH:{std}:{full}")

def _battle_validate_value_type(std:str,value:Any,target:str)->None:
    if std in {"shield","armor"}:
        if not isinstance(value,(int,float)) or isinstance(value,bool):
            raise EngineError(f"BATTLE_WRITEBACK_TYPE:{std}:{target}")
    elif std=="ammo":
        if not isinstance(value,int) or isinstance(value,bool) or value<0:
            raise EngineError(f"BATTLE_WRITEBACK_TYPE:{std}:{target}")
    elif std in {"destroyed","retreated"}:
        if not isinstance(value,bool):raise EngineError(f"BATTLE_WRITEBACK_TYPE:{std}:{target}")
    elif std=="status":
        if value not in {"destroyed","retreated","combat_capable"}:raise EngineError(f"BATTLE_WRITEBACK_TYPE:{std}:{target}")



PLAYER_CASUALTY_KEYS=("killed","wounded","missing","captured")


def _battle_player_outcome_plan(snapshot:dict,state:dict,outcomes:Optional[dict])->list:
    outcomes=outcomes or {};ledger=outcomes.get("player_casualty_ledger") or {}
    if not isinstance(ledger,dict):raise EngineError("BATTLE_PLAYER_CASUALTY_LEDGER_INVALID")
    fleets=(_player_fleet_registry(state).get("fleets") or {});plans=[]
    for sid,row in ledger.items():
        if not isinstance(row,dict):raise EngineError(f"BATTLE_PLAYER_CASUALTY_ROW_INVALID:{sid}")
        fleet_id=str(row.get("fleet_id") or "").strip();fr=fleets.get(fleet_id)
        if not isinstance(fr,dict):raise EngineError(f"BATTLE_PLAYER_FLEET_UNKNOWN:{sid}:{fleet_id}")
        src=((snapshot.get("sources") or {}).get(str(sid)) or {});ap=str(src.get("authority_path") or "")
        root=str(fr.get("authority_root") or "")
        if not root.startswith(("STATE.","state:")) or not ap.startswith(root):raise EngineError(f"BATTLE_PLAYER_SIDE_FLEET_AUTHORITY_MISMATCH:{sid}:{fleet_id}:{ap}")
        vals={k:int(row.get(k,0) or 0) for k in PLAYER_CASUALTY_KEYS}
        if any(v<0 for v in vals.values()):raise EngineError(f"BATTLE_PLAYER_CASUALTY_NEGATIVE:{sid}")
        ppath=str(fr.get("primary_personnel_path") or "")
        if not ppath.startswith(("STATE.","state:")):raise EngineError(f"PLAYER_FLEET_PERSONNEL_PATH_REQUIRED:{fleet_id}")
        try:cap=get_by_path(state,ppath[6:])
        except Exception:raise EngineError(f"PLAYER_FLEET_PERSONNEL_PATH_MISSING:{fleet_id}:{ppath}")
        if not isinstance(cap,int) or isinstance(cap,bool) or cap<0:raise EngineError(f"PLAYER_FLEET_PERSONNEL_COUNT_INVALID:{fleet_id}")
        if sum(vals.values())>cap:raise EngineError(f"BATTLE_PLAYER_CASUALTY_EXCEEDS_FLEET:{fleet_id}:{cap}")
        paths=[ppath]+[str(x) for x in (fr.get("personnel_mirror_paths") or [])]
        if len(paths)!=len(set(paths)):raise EngineError(f"PLAYER_FLEET_PERSONNEL_PATH_DUPLICATE:{fleet_id}")
        # Only killed are a permanent personnel-total decrement under current WORLD authority.
        # Wounded/missing/captured remain semantic status ledgers until a stronger rule exists.
        plans.append({"side":str(sid),"fleet_id":fleet_id,"casualties":vals,"permanent_removed":vals["killed"],"personnel_paths":paths,"pre_battle_personnel":cap})
    return plans


def _apply_battle_player_outcomes(state:dict,snapshot:dict,plans:list)->list:
    if not plans:return []
    reg=_player_fleet_registry(state);fleets=reg.get("fleets") or {};changes=[]
    for plan in plans:
        killed=int(plan.get("permanent_removed",0));fleet_id=plan["fleet_id"]
        for path in plan.get("personnel_paths") or []:
            try:cur=get_by_path(state,path[6:])
            except Exception:raise EngineError(f"PLAYER_FLEET_PERSONNEL_COMMIT_PATH_MISSING:{fleet_id}:{path}")
            if not isinstance(cur,int) or isinstance(cur,bool) or cur<killed:raise EngineError(f"PLAYER_FLEET_PERSONNEL_COMMIT_UNDERFLOW:{fleet_id}:{path}")
            parent,key=_dot_parent(state,path[6:]);parent[key]=cur-killed;changes.append({"target":path,"action":"battle_permanent_killed_decrement"})
        fr=fleets[fleet_id];cas=fr.setdefault("casualties_cumulative_since_registry",{})
        for k,v in plan["casualties"].items():cas[k]=int(cas.get(k,0) or 0)+int(v)
        fr["last_battle_id"]=snapshot.get("battle_id");fr["as_of"]=state.get("game_time")
        changes.append({"target":f"STATE.engine_runtime.player_fleet_registry.fleets.{fleet_id}.casualties_cumulative_since_registry","action":"append_player_casualty_ledger"})
        changes.append({"target":f"STATE.engine_runtime.player_fleet_registry.fleets.{fleet_id}.last_battle_id","action":"sync_last_battle_id"})
        changes.append({"target":f"STATE.engine_runtime.player_fleet_registry.fleets.{fleet_id}.as_of","action":"sync_battle_as_of"})
    return changes


def _battle_validate_maintenance_jobs(state:dict,snapshot:dict,player_plans:list,outcomes:Optional[dict])->list:
    raw=(outcomes or {}).get("maintenance_jobs") or []
    if not isinstance(raw,list):raise EngineError("BATTLE_MAINTENANCE_JOBS_INVALID")
    if not raw:return []
    now=parse_iso(state.get("game_time"))
    if now is None:raise EngineError("BATTLE_MAINTENANCE_GAME_TIME_INVALID")
    by_side={p["side"]:p for p in player_plans};normalized=[];tracked={}
    for r in raw:
        if not isinstance(r,dict):raise EngineError("BATTLE_MAINTENANCE_JOB_NOT_OBJECT")
        rr=copy.deepcopy(r);rr.setdefault("source_battle_id",snapshot.get("battle_id"))
        if str(rr.get("kind") or "").strip()=="repair":
            asset_class=str(rr.get("asset_class") or "").strip()
            if not asset_class:raise EngineError("BATTLE_REPAIR_ASSET_CLASS_REQUIRED")
            if asset_class in BATTLE_REPAIR_ELIGIBLE_ASSET_CLASSES:
                if rr.get("at_repair_position") is False:raise EngineError(f"BATTLE_REPAIR_NOT_AT_REPAIR_POSITION:{rr.get('job_id')}")
                rr["started_at"]=now.strftime("%Y-%m-%dT%H:%M:%S");rr["complete_at"]=(now+dt.timedelta(seconds=BATTLE_EQUIPMENT_REPAIR_SECONDS)).strftime("%Y-%m-%dT%H:%M:%S")
            elif asset_class not in BATTLE_REPAIR_EXCLUDED_ASSET_CLASSES:
                raise EngineError(f"BATTLE_REPAIR_ASSET_CLASS_UNKNOWN:{asset_class}")
        job=_normalize_maintenance_job(state,rr,now,snapshot.get("battle_id"))
        if job.get("kind")=="repair" and str(job.get("asset_class") or "") in BATTLE_REPAIR_ELIGIBLE_ASSET_CLASSES:
            job["policy"]={"rule":"BATTLE_EQUIPMENT_REPAIR_V2","fixed_seconds":BATTLE_EQUIPMENT_REPAIR_SECONDS,"extra_gold_cost":False,"parallel_queue":True,"damage_severity_independent":True}
        side=str(r.get("battle_side_id") or "").strip()
        if job["kind"]=="medical" and job.get("tracked_count",0)>0:
            if side not in by_side:raise EngineError(f"BATTLE_MEDICAL_JOB_PLAYER_SIDE_REQUIRED:{job['job_id']}")
            tracked[side]=tracked.get(side,0)+int(job["tracked_count"])
        job["battle_side_id"]=side or None;normalized.append(job)
    for side,n in tracked.items():
        wounded=int(by_side[side]["casualties"].get("wounded",0))
        if n>wounded:raise EngineError(f"BATTLE_MEDICAL_TRACKED_EXCEEDS_WOUNDED:{side}:{n}>{wounded}")
    return normalized


def _enqueue_normalized_maintenance_jobs(state:dict,jobs:list)->list:
    if not jobs:return []
    mr=_maintenance_runtime(state,create=True);added=[]
    for job in jobs:
        if _maintenance_job_exists(mr,str(job.get("job_id"))):raise EngineError(f"MAINTENANCE_JOB_DUPLICATE:{job.get('job_id')}")
        q="repair_queue" if job.get("kind")=="repair" else "medical_queue";mr[q].append(copy.deepcopy(job));added.append(copy.deepcopy(job))
    return added


def _battle_replenishment_plan(snapshot:dict,result:dict,state:dict,outcomes:Optional[dict])->list:
    """Validate same-fleet exact-model replenishment with explicit inventory accounting routes.

    A destroyed installed asset is a permanent ownership loss.  For an exact replacement
    the installed/allocation counts are net unchanged, but canonical total_owned and
    same-fleet available both fall by one.  When stock is unavailable, Engine may also
    decrement installed/allocation only when an explicit installed_asset_binding maps the
    shipboard aggregate to the canonical allocation ledger.  Missing routes become a
    pending accounting/replenishment record; Engine never guesses legacy paths.
    """
    reqs=(outcomes or {}).get("replenishment_requests") or []
    if not isinstance(reqs,list):raise EngineError("BATTLE_REPLENISHMENT_REQUESTS_INVALID")
    fleets=(_player_fleet_registry(state).get("fleets") or {});plans=[];seen=set()
    for r in reqs:
        if not isinstance(r,dict):raise EngineError("BATTLE_REPLENISHMENT_REQUEST_NOT_OBJECT")
        sid=str(r.get("side") or "");uid=str(r.get("unit_id") or "");key=(sid,uid)
        if not sid or not uid or key in seen:raise EngineError(f"BATTLE_REPLENISHMENT_UNIT_INVALID:{sid}:{uid}")
        seen.add(key);fleet_id=str(r.get("fleet_id") or "");fr=fleets.get(fleet_id)
        if not isinstance(fr,dict):raise EngineError(f"BATTLE_REPLENISHMENT_FLEET_UNKNOWN:{fleet_id}")
        src=((snapshot.get("sources") or {}).get(sid) or {});root=str(fr.get("authority_root") or "")
        if not str(src.get("authority_path") or "").startswith(root):raise EngineError(f"BATTLE_REPLENISHMENT_SIDE_FLEET_MISMATCH:{sid}:{fleet_id}")
        unit=next((u for u in ((((snapshot.get("mechanical_sides") or {}).get(sid) or {}).get("units") or [])) if isinstance(u,dict) and str(u.get("unit_id"))==uid),None)
        fin=((((result.get("final_state") or {}).get(sid) or {}).get("units") or {}).get(uid))
        if not isinstance(unit,dict) or not isinstance(fin,dict) or not fin.get("destroyed"):raise EngineError(f"BATTLE_REPLENISHMENT_REQUIRES_DESTROYED_UNIT:{sid}:{uid}")
        model_id=str(r.get("model_id") or unit.get("equipment_model_id") or unit.get("registry_equipment_model_id") or "")
        unit_mid=str(unit.get("equipment_model_id") or unit.get("registry_equipment_model_id") or "")
        if not model_id or model_id!=unit_mid:raise EngineError(f"BATTLE_REPLENISHMENT_MODEL_MISMATCH:{sid}:{uid}:{model_id}!={unit_mid}")
        binding=((fr.get("inventory_bindings") or {}).get(model_id)) if isinstance(fr.get("inventory_bindings") or {},dict) else None
        if not isinstance(binding,dict):
            plans.append({"side":sid,"unit_id":uid,"fleet_id":fleet_id,"model_id":model_id,"status":"pending_no_canonical_inventory_binding","auto_purchase":False,"cross_fleet":False,"asset_loss_accounting":"pending_explicit_binding"});continue
        ap=str(binding.get("available_path") or "");tp=str(binding.get("total_owned_path") or "")
        if not ap.startswith(("STATE.","state:")):raise EngineError(f"BATTLE_REPLENISHMENT_BINDING_PATH_INVALID:{fleet_id}:{model_id}")
        try:avail=get_by_path(state,ap[6:])
        except Exception:raise EngineError(f"BATTLE_REPLENISHMENT_BINDING_MISSING:{fleet_id}:{model_id}:{ap}")
        if not isinstance(avail,int) or isinstance(avail,bool) or avail<0:raise EngineError(f"BATTLE_REPLENISHMENT_AVAILABLE_INVALID:{fleet_id}:{model_id}")
        # A permanent destroyed asset cannot be accounted safely without an explicit total-owned route.
        if not tp.startswith(("STATE.","state:")):
            plans.append({"side":sid,"unit_id":uid,"fleet_id":fleet_id,"model_id":model_id,"status":"pending_inventory_total_binding_required","available_path":ap,"available":avail,"auto_purchase":False,"cross_fleet":False,"asset_loss_accounting":"pending_explicit_total_owned_binding"});continue
        try:total=get_by_path(state,tp[6:])
        except Exception:raise EngineError(f"BATTLE_REPLENISHMENT_TOTAL_BINDING_MISSING:{fleet_id}:{model_id}:{tp}")
        if not isinstance(total,int) or isinstance(total,bool) or total<=0:raise EngineError(f"BATTLE_REPLENISHMENT_TOTAL_INVALID:{fleet_id}:{model_id}")
        # available and total_owned must be siblings in the same explicitly registered canonical inventory object.
        if ap.rsplit('.',1)[0]!=tp.rsplit('.',1)[0]:raise EngineError(f"BATTLE_REPLENISHMENT_BINDING_OBJECT_MISMATCH:{fleet_id}:{model_id}")
        installed=str(r.get("installed_quantity_path") or "")
        allowed_prefixes=[str(x) for x in (fr.get("installed_quantity_prefixes") or [])]
        if not installed.startswith(("STATE.","state:")) or not any(installed.startswith(x) for x in allowed_prefixes):
            plans.append({"side":sid,"unit_id":uid,"fleet_id":fleet_id,"model_id":model_id,"status":"pending_installed_binding_required","available_path":ap,"total_owned_path":tp,"available":avail,"total_owned":total,"auto_purchase":False,"cross_fleet":False,"asset_loss_accounting":"pending_installed_route"});continue
        try:installed_qty=get_by_path(state,installed[6:])
        except Exception:raise EngineError(f"BATTLE_REPLENISHMENT_INSTALLED_PATH_MISSING:{installed}")
        if not isinstance(installed_qty,int) or isinstance(installed_qty,bool) or installed_qty<=0:raise EngineError(f"BATTLE_REPLENISHMENT_INSTALLED_QTY_INVALID:{installed}")
        if avail>0:
            plans.append({"side":sid,"unit_id":uid,"fleet_id":fleet_id,"model_id":model_id,"status":"exact_model_replenish","available_path":ap,"total_owned_path":tp,"installed_path":installed,"available_before":avail,"total_owned_before":total,"installed_before":installed_qty,"auto_purchase":False,"cross_fleet":False,"asset_loss_accounting":"automatic_total_owned_loss"});continue
        # No stock: the destroyed installed asset must leave both the installed aggregate and
        # the canonical allocated ledger.  This is allowed only with an explicit route binding.
        ibs=fr.get("installed_asset_bindings") or {};ib=ibs.get(installed) if isinstance(ibs,dict) else None
        if not isinstance(ib,dict):
            plans.append({"side":sid,"unit_id":uid,"fleet_id":fleet_id,"model_id":model_id,"status":"pending_no_same_fleet_stock_accounting_binding_required","available_path":ap,"total_owned_path":tp,"installed_path":installed,"available":avail,"total_owned":total,"installed_before":installed_qty,"auto_purchase":False,"cross_fleet":False,"asset_loss_accounting":"pending_allocation_route"});continue
        if str(ib.get("model_id") or "")!=model_id:raise EngineError(f"BATTLE_REPLENISHMENT_INSTALLED_MODEL_BINDING_MISMATCH:{fleet_id}:{installed}")
        allocp=str(ib.get("allocation_path") or "")
        if not allocp.startswith(("STATE.","state:")):raise EngineError(f"BATTLE_REPLENISHMENT_ALLOCATION_BINDING_INVALID:{fleet_id}:{installed}")
        invroot=ap.rsplit('.',1)[0]
        if not allocp.startswith(invroot+'.allocated.'):raise EngineError(f"BATTLE_REPLENISHMENT_ALLOCATION_OBJECT_MISMATCH:{fleet_id}:{installed}")
        try:allocq=get_by_path(state,allocp[6:])
        except Exception:raise EngineError(f"BATTLE_REPLENISHMENT_ALLOCATION_PATH_MISSING:{allocp}")
        if not isinstance(allocq,int) or isinstance(allocq,bool) or allocq<=0:raise EngineError(f"BATTLE_REPLENISHMENT_ALLOCATION_QTY_INVALID:{allocp}")
        plans.append({"side":sid,"unit_id":uid,"fleet_id":fleet_id,"model_id":model_id,"status":"pending_no_same_fleet_stock","available_path":ap,"total_owned_path":tp,"installed_path":installed,"allocation_path":allocp,"available_before":avail,"total_owned_before":total,"installed_before":installed_qty,"allocation_before":allocq,"auto_purchase":False,"cross_fleet":False,"asset_loss_accounting":"automatic_total_allocated_installed_loss"})
    return plans


def _apply_battle_replenishment(state:dict,snapshot:dict,plans:list)->list:
    if not plans:return []
    mr=_maintenance_runtime(state,create=True);changes=[]
    for plan in plans:
        status=plan.get("status")
        if status=="exact_model_replenish":
            ap=plan["available_path"];tp=plan["total_owned_path"]
            av=get_by_path(state,ap[6:]);tot=get_by_path(state,tp[6:])
            if av!=plan["available_before"] or tot!=plan["total_owned_before"]:raise EngineError(f"BATTLE_REPLENISHMENT_AUTHORITY_CHANGED:{plan['fleet_id']}:{plan['model_id']}")
            if av<=0 or tot<=0:raise EngineError(f"BATTLE_REPLENISHMENT_ACCOUNTING_UNDERFLOW:{plan['fleet_id']}:{plan['model_id']}")
            # Destroyed installed asset permanently leaves ownership (-1 total_owned).
            # Exact same-model public stock then fills the slot (-1 available).  Installed
            # and allocated aggregates are net unchanged, so no duplicate asset is created.
            tpar,tkey=_dot_parent(state,tp[6:]);tpar[tkey]=tot-1
            apar,akey=_dot_parent(state,ap[6:]);apar[akey]=av-1
            changes.append({"target":tp,"action":"battle_destroyed_installed_asset_total_owned_decrement"})
            changes.append({"target":ap,"action":"same_fleet_exact_model_replenish_consume_one"})
        elif status=="pending_no_same_fleet_stock" and plan.get("asset_loss_accounting")=="automatic_total_allocated_installed_loss":
            tp=plan["total_owned_path"];ip=plan["installed_path"];alp=plan["allocation_path"]
            tot=get_by_path(state,tp[6:]);iq=get_by_path(state,ip[6:]);aq=get_by_path(state,alp[6:])
            if tot!=plan["total_owned_before"] or iq!=plan["installed_before"] or aq!=plan["allocation_before"]:raise EngineError(f"BATTLE_REPLENISHMENT_AUTHORITY_CHANGED:{plan['fleet_id']}:{plan['model_id']}")
            if tot<=0 or iq<=0 or aq<=0:raise EngineError(f"BATTLE_REPLENISHMENT_ACCOUNTING_UNDERFLOW:{plan['fleet_id']}:{plan['model_id']}")
            tpar,tkey=_dot_parent(state,tp[6:]);tpar[tkey]=tot-1
            ipar,ikey=_dot_parent(state,ip[6:]);ipar[ikey]=iq-1
            apar,akey=_dot_parent(state,alp[6:]);apar[akey]=aq-1
            changes.append({"target":tp,"action":"battle_destroyed_installed_asset_total_owned_decrement"})
            changes.append({"target":ip,"action":"battle_destroyed_asset_installed_decrement_no_stock"})
            changes.append({"target":alp,"action":"battle_destroyed_asset_allocation_decrement_no_stock"})
            rec=copy.deepcopy(plan);rec["battle_id"]=snapshot.get("battle_id");rec["recorded_at_game_time"]=state.get("game_time");mr["pending_replenishment"].append(rec)
            changes.append({"target":"STATE.engine_runtime.maintenance_runtime.pending_replenishment","action":"record_understrength_without_cross_fleet_or_purchase"})
        else:
            rec=copy.deepcopy(plan);rec["battle_id"]=snapshot.get("battle_id");rec["recorded_at_game_time"]=state.get("game_time");mr["pending_replenishment"].append(rec)
            changes.append({"target":"STATE.engine_runtime.maintenance_runtime.pending_replenishment","action":"record_understrength_or_accounting_route_required_without_guessing"})
    return changes


def _battle_force_outcome_plan(snapshot:dict,result:dict,state:dict,outcomes:Optional[dict])->list:
    outcomes=outcomes or {};ledger=outcomes.get('casualty_ledger') or {}
    if not isinstance(ledger,dict):raise EngineError('BATTLE_CASUALTY_LEDGER_INVALID')
    plans=[]
    for sid,src in (snapshot.get('sources') or {}).items():
        fid=src.get('force_id')
        if not fid:continue
        force=(_battle_force_registry(state).get(fid) or {})
        if not isinstance(force,dict):raise EngineError(f'BATTLE_FORCE_UNKNOWN:{sid}:{fid}')
        row=ledger.get(sid) or {}
        if not isinstance(row,dict):raise EngineError(f'BATTLE_CASUALTY_ROW_INVALID:{sid}')
        vals={k:int(row.get(k,0) or 0) for k in ('killed','captured','deserted_or_confirmed_left','wounded','escaped_still_member')}
        if any(v<0 for v in vals.values()):raise EngineError(f'BATTLE_CASUALTY_NEGATIVE:{sid}')
        removed=vals['killed']+vals['captured']+vals['deserted_or_confirmed_left']
        pers=force.get('personnel') or {}
        if not isinstance(pers,dict):raise EngineError(f'BATTLE_FORCE_PERSONNEL_LEDGER_REQUIRED:{fid}')
        confirmed=pers.get('confirmed');rng=pers.get('estimate_range')
        cap=None
        if isinstance(confirmed,int) and not isinstance(confirmed,bool):cap=confirmed
        elif isinstance(rng,list) and len(rng)==2 and all(isinstance(x,int) and not isinstance(x,bool) for x in rng):cap=max(rng)
        if cap is None:raise EngineError(f'BATTLE_FORCE_PERSONNEL_BOUND_REQUIRED:{fid}')
        if removed+vals['wounded']+vals['escaped_still_member']>cap:raise EngineError(f'BATTLE_CASUALTY_EXCEEDS_FORCE:{fid}:{cap}')
        eq_losses={}
        for u in (((snapshot.get('mechanical_sides') or {}).get(sid) or {}).get('units') or []):
            if not isinstance(u,dict):continue
            mid=u.get('registry_equipment_model_id')
            if not mid:continue
            cm=str(mid)
            fin=(((result.get('final_state') or {}).get(sid) or {}).get('units') or {}).get(str(u.get('unit_id')))
            if isinstance(fin,dict) and fin.get('destroyed'):eq_losses[cm]=eq_losses.get(cm,0)+1
        plans.append({'side':sid,'force_id':fid,'expected_revision':int(src.get('revision')),'casualties':vals,'removed':removed,'equipment_destroyed':eq_losses})
    pending=outcomes.get('pending_loot') or []
    if not isinstance(pending,list) or not all(isinstance(x,dict) for x in pending):raise EngineError('BATTLE_PENDING_LOOT_INVALID')
    return plans


def _apply_battle_force_outcomes(state:dict,snapshot:dict,result:dict,plans:list,outcomes:Optional[dict])->list:
    changes=[];reg=_battle_force_registry(state)
    for plan in plans:
        fid=plan['force_id'];force=reg[fid]
        if int(force.get('revision',-1))!=plan['expected_revision']:raise EngineError(f'BATTLE_FORCE_REVISION_MISMATCH_COMMIT:{fid}')
        pers=force.setdefault('personnel',{});removed=plan['removed']
        if isinstance(pers.get('confirmed'),int) and not isinstance(pers.get('confirmed'),bool):pers['confirmed']=max(0,int(pers['confirmed'])-removed)
        elif isinstance(pers.get('estimate_range'),list) and len(pers['estimate_range'])==2:
            lo,hi=[int(x) for x in pers['estimate_range']];pers['estimate_range']=[max(0,lo-removed),max(0,hi-removed)]
        cas=force.setdefault('casualties_cumulative',{})
        for k,v in plan['casualties'].items():cas[k]=int(cas.get(k,0) or 0)+v
        eq=force.setdefault('equipment',{})
        for mid,n in plan['equipment_destroyed'].items():
            rec=eq.get(mid)
            if not isinstance(rec,dict):raise EngineError(f'BATTLE_FORCE_EQUIPMENT_MODEL_NOT_IN_FORCE:{fid}:{mid}')
            if isinstance(rec.get('confirmed'),int):
                if rec['confirmed']<n:raise EngineError(f'BATTLE_FORCE_EQUIPMENT_UNDERFLOW:{fid}:{mid}')
                rec['confirmed']-=n
            elif isinstance(rec.get('estimate_range'),list) and len(rec['estimate_range'])==2:
                lo,hi=[int(x) for x in rec['estimate_range']];rec['estimate_range']=[max(0,lo-n),max(0,hi-n)]
            else:raise EngineError(f'BATTLE_FORCE_EQUIPMENT_BOUND_REQUIRED:{fid}:{mid}')
        force['revision']=int(force.get('revision',0))+1;force['as_of']=state.get('game_time');force['last_battle_id']=snapshot.get('battle_id')
        changes.append({'target':f'STATE.external_force_registry.{fid}','action':'battle_force_revision_commit'})
    cr=state.setdefault('engine_runtime',{}).setdefault('combat_runtime',{});cr.setdefault('schema',COMBAT_RUNTIME_SCHEMA)
    loot=(outcomes or {}).get('pending_loot') or []
    if loot:
        q=cr.setdefault('pending_loot',[])
        for row in loot:
            q.append({'battle_id':snapshot.get('battle_id'),'status':'pending_identification_and_ownership','claim':copy.deepcopy(row),'recorded_at_game_time':state.get('game_time')})
        changes.append({'target':'STATE.engine_runtime.combat_runtime.pending_loot','action':'append_uncredited_battle_loot_claims'})
    return changes


def battle_apply(root:Path,payload:dict,version:Optional[str],scope:str,dry_run:bool=False,commit_outcomes:Optional[dict]=None)->dict:
    guard(root,restore=True,restore_tool_files=False);parent=latest_valid_snapshot(root,verify_parent=True)
    expected_sid=str(payload.get('base_save_set_id') or '').strip()
    if not expected_sid:raise EngineError('BATTLE_APPLY_BASE_SAVE_SET_ID_REQUIRED')
    if expected_sid!=parent.get('save_set_id'):raise EngineError(f'BATTLE_APPLY_STALE_BASE:{expected_sid}!={parent.get("save_set_id")}')
    result=battlecalc(payload,root);raw_index=_battle_payload_unit_index(payload);write_plan=[]
    source_state=read_json(root/'state.json');force_plans=_battle_force_outcome_plan(payload,result,source_state,commit_outcomes);player_plans=_battle_player_outcome_plan(payload,source_state,commit_outcomes);maintenance_jobs=_battle_validate_maintenance_jobs(source_state,payload,player_plans,commit_outcomes);replenishment_plans=_battle_replenishment_plan(payload,result,source_state,commit_outcomes);seen_authority=set();seen_targets=set()
    for (sid,uid),raw in raw_index.items():
        ap=str(raw.get('authority_path') or '').strip();wb=raw.get('writeback_fields') or {};srcmeta=((payload.get('sources') or {}).get(sid) or {})
        if not isinstance(wb,dict):raise EngineError(f'BATTLE_APPLY_MAPPING_INVALID:{sid}:{uid}')
        if not wb:
            if srcmeta.get('force_id'):continue
            raise EngineError(f'BATTLE_APPLY_MAPPING_REQUIRED:{sid}:{uid}')
        if not ap.startswith(('STATE.','state:')):raise EngineError(f'BATTLE_APPLY_AUTHORITY_PATH_REQUIRED:{sid}:{uid}')
        # A battle unit must map to one distinct authority object. This prevents two simulated
        # units from racing over the same ship/squad record in a single transaction.
        if ap in seen_authority:raise EngineError(f'BATTLE_APPLY_AUTHORITY_OBJECT_DUPLICATE:{ap}')
        seen_authority.add(ap)
        if set(wb)-BATTLE_WRITEBACK_FIELDS:raise EngineError(f'BATTLE_WRITEBACK_FIELDS_INVALID:{sorted(set(wb)-BATTLE_WRITEBACK_FIELDS)}')
        try:obj=get_by_path(source_state,ap[6:])
        except Exception:raise EngineError(f'BATTLE_APPLY_AUTHORITY_PATH_MISSING:{ap}')
        if not isinstance(obj,dict):raise EngineError(f'BATTLE_APPLY_AUTHORITY_OBJECT_REQUIRED:{ap}')
        final=((result.get('final_state') or {}).get(sid) or {}).get('units',{}).get(uid)
        if not isinstance(final,dict):raise EngineError(f'BATTLE_APPLY_RESULT_UNIT_MISSING:{sid}:{uid}')
        initial={'shield':max(0.0,float(raw.get('shield') or 0)),'armor':max(0.0,float(raw.get('armor') if raw.get('armor') is not None else raw.get('hull',100) or 0)),'ammo':max(0,int(raw.get('ammo') if raw.get('ammo') is not None else raw.get('missile_ammo',0) or 0))}
        explicit_expected=raw.get('authority_expected') or {}
        if not isinstance(explicit_expected,dict):raise EngineError(f'BATTLE_APPLY_EXPECTED_INVALID:{sid}:{uid}')
        values={'shield':final.get('shield'),'armor':final.get('armor'),'ammo':final.get('ammo'),'destroyed':bool(final.get('destroyed')),'retreated':bool(final.get('retreated')),'status':'destroyed' if final.get('destroyed') else ('retreated' if final.get('retreated') else 'combat_capable')}
        allow_create=bool(raw.get('writeback_allow_create',False))
        for std,rel0 in wb.items():
            rel=str(rel0 or '').strip()
            if not rel:raise EngineError(f'BATTLE_WRITEBACK_PATH_EMPTY:{std}:{ap}')
            _battle_validate_mapping(ap,std,rel)
            target=f'{ap}.{rel}'
            if target in seen_targets:raise EngineError(f'BATTLE_WRITEBACK_TARGET_DUPLICATE:{target}')
            seen_targets.add(target)
            _battle_validate_value_type(std,values[std],target)
            try:cur=_battle_get_relative(obj,rel);exists=True
            except Exception:
                exists=False;cur=None
            if not exists:
                if not allow_create:raise EngineError(f'BATTLE_WRITEBACK_TARGET_MISSING:{target}')
                # Creation is permitted only for an already-semantic, whitelisted field path.
                continue
            if std in {'shield','armor','ammo'}:
                exp=explicit_expected.get(std,initial[std])
            else:
                if std not in explicit_expected:
                    raise EngineError(f'BATTLE_APPLY_EXPECT_REQUIRED:{std}:{target}')
                exp=explicit_expected[std]
            if isinstance(cur,(int,float)) and not isinstance(cur,bool) and isinstance(exp,(int,float)) and not isinstance(exp,bool):
                if abs(float(cur)-float(exp))>1e-9:raise EngineError(f'BATTLE_APPLY_EXPECT_MISMATCH:{target}:expected={exp}:actual={cur}')
            elif cur!=exp:raise EngineError(f'BATTLE_APPLY_EXPECT_MISMATCH:{target}:expected={exp!r}:actual={cur!r}')
        write_plan.append({'side':sid,'unit_id':uid,'authority_path':ap,'writeback_fields':copy.deepcopy(wb),'values':values,'allow_create':allow_create})
    if dry_run:return {'packet':'BATTLE_APPLY_V4','status':'DRY_RUN','battle':result,'write_plan':write_plan,'force_outcome_plan':force_plans,'player_outcome_plan':player_plans,'maintenance_jobs':maintenance_jobs,'replenishment_plan':replenishment_plans,'saved':False,'base_save_set_id':expected_sid}
    if not version:raise EngineError('BATTLE_APPLY_VERSION_REQUIRED')
    info=create_stage(root,'battleapply');stage=Path(info['staging'])
    try:
        state=read_json(stage/'state.json');changes=[]
        cr=state.setdefault('engine_runtime',{}).setdefault('combat_runtime',{});cr.setdefault('schema',COMBAT_RUNTIME_SCHEMA);cr.setdefault('next_battle_sequence',1);commits=cr.setdefault('battle_commits',{})
        bid=str(result.get('battle_id'));seq=int(payload.get('battle_sequence') or 0)
        if bid in commits:raise EngineError(f'BATTLE_ALREADY_COMMITTED:{bid}')
        if seq!=int(cr.get('next_battle_sequence',1)):raise EngineError(f'BATTLE_SEQUENCE_MISMATCH:{seq}!={cr.get("next_battle_sequence")}')
        for row in write_plan:
            obj=get_by_path(state,row['authority_path'][6:])
            for std,rel in row['writeback_fields'].items():
                _battle_set_relative(obj,str(rel),row['values'][std],row['allow_create']);changes.append({'target':f"{row['authority_path']}.{rel}",'action':f'battle_writeback_{std}'})
        changes.extend(_apply_battle_force_outcomes(state,payload,result,force_plans,commit_outcomes))
        changes.extend(_apply_battle_player_outcomes(state,payload,player_plans))
        changes.extend(_apply_battle_replenishment(state,payload,replenishment_plans))
        added_maintenance=_enqueue_normalized_maintenance_jobs(state,maintenance_jobs)
        if added_maintenance:changes.append({'target':'STATE.engine_runtime.maintenance_runtime','action':f'enqueue_{len(added_maintenance)}_battle_maintenance_jobs'})
        result_hash=sha256_bytes(json.dumps({k:v for k,v in result.items() if k!='rounds'},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))
        commits[bid]={'battle_sequence':seq,'prepared_token':payload.get('prepared_token'),'base_save_set_id':expected_sid,'result_sha256':result_hash,'committed_at_game_time':state.get('game_time')};cr['last_committed_battle_id']=bid;cr['next_battle_sequence']=seq+1
        changes.append({'target':'STATE.engine_runtime.combat_runtime','action':'commit_battle_idempotency_and_sequence'})
        _write_authority_json(stage/'state.json',state);gt=str(state.get('game_time') or '');compact_result={k:v for k,v in result.items() if k!='rounds'}
        input_digest=sha256_bytes(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))
        _append_engine_history(stage/'events.jsonl',{'event_id':f'EVT-BATTLE-{result.get("battle_id")}-{gt.replace("-","").replace(":","").replace("T","-")}','game_time':gt,'type':'battle_mechanical_resolution','summary':f'GAME ENGINE v{ENGINE_VERSION}完成战斗{result.get("battle_id")}机械状态机并事务写回{len(write_plan)}个单位；胜负={result.get("winner")}，回合={result.get("rounds_fought")}。','changes':changes,'source':f'GAME ENGINE v{ENGINE_VERSION} BATTLE_COMMIT_V2','authority_files':['state.json'],'battle_input_sha256':input_digest,'battle_input':copy.deepcopy(payload),'mechanical_resolution':compact_result,'base_save_set_id':expected_sid,'zero_time':True})
        saved=atomic_save(stage,version,scope,root,False,False);result['authority_written']=True;result['save_set_id']=saved.get('save_set_id') if isinstance(saved,dict) else None
        return {'packet':'BATTLE_APPLY_V4','status':'SAVED','battle':result,'write_plan':write_plan,'force_outcome_plan':force_plans,'player_outcome_plan':player_plans,'maintenance_jobs':maintenance_jobs,'replenishment_plan':replenishment_plans,'save':saved}
    except Exception:
        try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
        except Exception:pass
        raise

def battle_commit(root:Path,commit_payload:dict,version:Optional[str],scope:str,dry_run:bool=False)->dict:
    snap=commit_payload.get("snapshot")
    if not isinstance(snap,dict):raise EngineError("BATTLE_COMMIT_SNAPSHOT_REQUIRED")
    outcomes={k:copy.deepcopy(v) for k,v in commit_payload.items() if k!="snapshot"}
    r=battle_apply(root,snap,version,scope,dry_run,commit_outcomes=outcomes)
    r["packet"]="BATTLE_COMMIT_V2"
    return r



def maintenance_status_packet(base:Path=ROOT)->dict:
    ensure_source_ready(base);state=read_json(base/"state.json");mr=_maintenance_runtime(state,create=False);now=parse_iso(state.get("game_time"));rows=[]
    for qname in ("repair_queue","medical_queue"):
        for j in mr.get(qname,[]) or []:
            if isinstance(j,dict):rows.append({"job_id":j.get("job_id"),"kind":j.get("kind"),"fleet_id":j.get("fleet_id"),"target_id":j.get("target_id"),"started_at":j.get("started_at"),"complete_at":j.get("complete_at"),"status":j.get("status"),"tracked_count":j.get("tracked_count",0)})
    rows.sort(key=lambda x:(x.get("complete_at") or "",x.get("job_id") or ""))
    return {"packet":"MAINTENANCE_STATUS_V1","engine_version":ENGINE_VERSION,"game_time":state.get("game_time"),"active_jobs":rows,"active_count":len(rows),"blocked_count":len(mr.get("blocked_jobs") or {}),"completed_count":len(mr.get("completed_jobs") or {}),"pending_replenishment_count":len(mr.get("pending_replenishment") or []),"next_completion":rows[0] if rows else None}


def maintenance_enqueue(root:Path,payload:dict,version:Optional[str],scope:str,dry_run:bool=False)->dict:
    guard(root,restore=True,restore_tool_files=False);state0=read_json(root/"state.json");now=parse_iso(state0.get("game_time"))
    if now is None:raise EngineError("MAINTENANCE_GAME_TIME_INVALID")
    jobs=payload.get("jobs") if isinstance(payload,dict) else None
    if not isinstance(jobs,list) or not jobs:raise EngineError("MAINTENANCE_JOBS_REQUIRED")
    probe=copy.deepcopy(state0);added=_enqueue_maintenance_jobs(probe,jobs,now,payload.get("source_battle_id") if isinstance(payload,dict) else None)
    if dry_run:return {"packet":"MAINTENANCE_ENQUEUE_V1","status":"DRY_RUN","jobs":added,"saved":False}
    if not version:raise EngineError("MAINTENANCE_VERSION_REQUIRED")
    info=create_stage(root,"maintenance_enqueue");stage=Path(info["staging"])
    try:
        state=read_json(stage/"state.json");added=_enqueue_maintenance_jobs(state,jobs,now,payload.get("source_battle_id") if isinstance(payload,dict) else None);gt=str(state.get("game_time") or "")
        _write_authority_json(stage/"state.json",state)
        _append_engine_history(stage/"events.jsonl",{"event_id":f"EVT-MAINT-ENQUEUE-{gt.replace('-','').replace(':','').replace('T','-')}-{sha256_bytes(json.dumps([x['job_id'] for x in added],sort_keys=True).encode())[:10]}","game_time":gt,"type":"maintenance_jobs_enqueued","summary":f"GAME ENGINE v{ENGINE_VERSION}封板并登记{len(added)}个维修/医疗机械完成节点；单次工期均不超过30天，不自动产生赶工费或医疗包消耗。","changes":[{"target":"STATE.engine_runtime.maintenance_runtime","action":f"enqueue_{len(added)}_jobs"}],"source":f"GAME ENGINE v{ENGINE_VERSION} {MAINTENANCE_RUNTIME_SCHEMA}","authority_files":["state.json"],"zero_time":True})
        saved=atomic_save(stage,version,scope,root,False,False);return {"packet":"MAINTENANCE_ENQUEUE_V1","status":"SAVED","jobs":added,"save":saved}
    except Exception:
        try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
        except Exception:pass
        raise

# Mobile seven-file operating contract. Runtime indexes remain disposable.
MOBILE_CONTRACT_SCHEMA = 'MOBILE_SEVEN_FILE_V1'

def _mobile_contract(state):
    return ((state.get('engine_runtime') or {}).get('mobile_contract') or {}).get('schema') == MOBILE_CONTRACT_SCHEMA

