# === VOYAGER_DEV_MODULE: health_and_upgrade ===
def engine_health_packet(base:Path=ROOT)->dict:
    ensure_source_ready(base);state=read_json(base/'state.json');tasks=read_json(base/'tasks.json');index_text=_manifest_protocol_text(base);perf=performance_packet(ROOT,20);hist=history_epoch_status(base);assets=asset_ledger_plan(base);arch=state_archive_plan(base)
    sizes={fn:(base/fn).stat().st_size for fn in AUTH_FILES if (base/fn).is_file()};now=parse_iso(state.get('game_time'));plan=routineplan_packet(base,(now+dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')) if now else {};reasons=[]
    if sizes.get('state.json',0)>STATE_ARCHIVE_SIZE_THRESHOLD:reasons.append('STATE_SIZE')
    if hist.get('activation_recommended'):reasons.append('HISTORY_EPOCH')
    if assets.get('activation_recommended'):reasons.append('ASSET_LEDGER')
    if (plan.get('ai_review_count') or 0)>5:reasons.append('AI_BARRIER_DENSITY')
    if len(tasks.get('active_tasks') or [])>100:reasons.append('TASK_COUNT')
    for row in perf.get('commands',[]):
        if row.get('command')=='query' and (row.get('avg_ms') or 0)>600:reasons.append('QUERY_LATENCY')
        if row.get('command')=='boot' and (row.get('avg_ms') or 0)>2000:reasons.append('BOOT_LATENCY')
    runtime_files={}
    rdir=ROOT/'.runtime'
    for name in ('history_index.json','world_index.json','state_semantic_index.json','derived_views.json','cache.db','performance.db'):
        p=rdir/name
        if p.is_file():runtime_files[name]=p.stat().st_size
    hidx=runtime_files.get('history_index.json',0);hbytes=sizes.get('events.jsonl',0);amp=(round(hidx/hbytes,4) if hbytes else None)
    widx=runtime_files.get('world_index.json',0);wbytes=sizes.get('WORLD.md',0);wamp=(round(widx/wbytes,4) if wbytes else None)
    cold=cold_start_packet(base);cold_bytes=len(json.dumps(cold,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
    stale=_stale_current_semantic_report(state,tasks,index_text);contracts=_query_contract_status(base);derived=_derived_state_footprint(state);ereg=_entity_registry_integrity_report(state);wreg=_world_rule_registry_integrity_report(_authority_world_text(base))
    derived_runtime=_derived_runtime_status(base,state)
    if stale.get('required') and stale.get('count'):reasons.append('STALE_CURRENT')
    if contracts.get('failure_count'):reasons.append('QUERY_CONTRACT')
    if cold_bytes>4096:reasons.append('COLD_PACKET_SIZE')
    if amp is not None and amp>0.8:reasons.append('HISTORY_INDEX_AMPLIFICATION')
    if derived_runtime.get('status')!='PASS':reasons.append('DERIVED_RUNTIME')
    return {'packet':'ENGINE_HEALTH_V6','engine_version':ENGINE_VERSION,'source_transport_capability':VPACK_TRANSPORT_FORMAT,'dev_build':{'format':DEV_MODULE_MANIFEST_FORMAT,'module_count':len(_dev_module_segments(Path(__file__).read_bytes()))},'authority_sizes':sizes,'runtime_cache_sizes':runtime_files,'history_index_amplification':amp,'world_rule_index_amplification':wamp,'cold_start_packet_bytes':cold_bytes,'active_tasks':len(tasks.get('active_tasks') or []),'next_24h_ai_reviews':plan.get('ai_review_count'),'query_contract':contracts,'stale_current':stale,'entity_registry':ereg,'world_rule_registry':wreg,'derived_state_footprint':derived,'derived_runtime':derived_runtime,'history':hist,'asset_ledger':assets,'state_archive_candidates':arch.get('candidate_count'),'upgrade_recommended':bool(reasons),'upgrade_reasons':sorted(set(reasons)),'automation_candidates':automation_candidate_packet(base,3).get('candidates',[])[:5]}

def _median_ms(vals:List[float])->float:
    vals=sorted(float(x) for x in vals);n=len(vals)
    return vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2.0

def _candidate_declared_guard(candidate:Path,root:Path)->Tuple[str,str,Path]:
    txt=candidate.read_text(encoding='utf-8')
    vm=re.search(r'^BUNDLED_GUARD_VERSION\s*=\s*["\']([^"\']+)["\']',txt,re.M);hm=re.search(r'^BUNDLED_GUARD_SHA256\s*=\s*["\']([0-9a-f]{64})["\']',txt,re.M)
    if not vm or not hm:raise EngineError('ENGINE_UPGRADE_CANDIDATE_GUARD_BINDING_MISSING')
    gv,gh=vm.group(1),hm.group(1);gp=root/f'SAVE_GUARD_v{gv}.py'
    if not gp.is_file() or sha256_file(gp)!=gh:raise EngineError(f'ENGINE_UPGRADE_CANDIDATE_GUARD_NOT_FOUND:{gv}:{gh}')
    return gv,gh,gp

def _rewrite_index_tool_binding_for_cold(index_text:str,engine_version:str,engine_hash:str,guard_hash:str,guard_version:str)->str:
    x=re.sub(r'^- `game_engine_version`：`[^`]+`$',f'- `game_engine_version`：`{engine_version}`',index_text,flags=re.M)
    x=re.sub(r'^- `game_engine_sha256`：`[0-9a-f]{64}`$',f'- `game_engine_sha256`：`{engine_hash}`',x,flags=re.M)
    x=re.sub(r'^- `save_guard_sha256`：`[0-9a-f]{64}`$',f'- `save_guard_sha256`：`{guard_hash}`',x,flags=re.M)
    x=re.sub(r'^### GAME ENGINE v[^ ]+ 工具绑定$',f'### GAME ENGINE v{engine_version} 工具绑定',x,flags=re.M)
    x=re.sub(r'`GAME_ENGINE_v[^`]+\.py`',f'`GAME_ENGINE_v{engine_version}.py`',x)
    x=re.sub(r'`SAVE_GUARD_v[^`]+\.py`',f'`SAVE_GUARD_v{guard_version}.py`',x)
    return x

def _cold_boot_upgrade_gate(root:Path,candidate:Path,stage:Path,candidate_module=None)->dict:
    txt=candidate.read_text(encoding='utf-8');m=re.search(r'^ENGINE_VERSION\s*=\s*["\']([^"\']+)["\']',txt,re.M)
    if not m:raise EngineError('ENGINE_UPGRADE_VERSION_MISSING')
    cv=m.group(1);gv,gh,gp=_candidate_declared_guard(candidate,root);eh=sha256_file(candidate)
    cold=root/f'.engine_upgrade_cold_{uuid.uuid4().hex[:10]}';cold.mkdir(parents=True,exist_ok=False)
    loaded=[]
    try:
        for fn in AUTH_FILES:shutil.copy2(stage/fn,cold/fn)
        idx=(cold/'INDEX.md').read_text(encoding='utf-8');parsed=parse_index_manifest(idx) or {};vv=parsed.get('version')
        version=version_text(vv) if isinstance(vv,tuple) else str(read_json(cold/'state.json').get('save_version') or 'V0.0')
        hashes={fn:sha256_file(cold/fn) for fn in SRC_ORDER};b=bundle_hash(hashes);sid=f'SAVESET-{version}-{b[:16]}'
        parent_sid=str(parsed.get('parent_save_set_id') or parsed.get('save_set_id') or 'COLD-BOOT-SYNTHETIC')
        idx=update_index_manifest(idx,version,hashes,b,sid,parent_sid,eh,gh);idx=_sync_index_world_revision(idx,(cold/'WORLD.md').read_text(encoding='utf-8'));idx=_rewrite_index_tool_binding_for_cold(idx,cv,eh,gh,gv)
        (cold/'INDEX.md').write_text(idx,encoding='utf-8',newline='\n');shutil.copy2(candidate,cold/f'GAME_ENGINE_v{cv}.py');shutil.copy2(gp,cold/f'SAVE_GUARD_v{gv}.py')
        visible=sorted(p.name for p in cold.iterdir() if p.is_file() and not p.name.startswith('.'))
        if len(visible)!=7:raise EngineError(f'ENGINE_UPGRADE_COLD_FILESET_NOT_SEVEN:{visible}')
        checks=[]
        ename,emod=_load_upgrade_module(cold/f'GAME_ENGINE_v{cv}.py',cold,'cold_engine');loaded.append(ename)
        sc,_=_upgrade_call('cold_sourcecheck',15,emod.project_source_check,cold,True);checks.append({'name':'sourcecheck_7','status':sc.get('status'),'detail':str(sc)[-800:]})
        if sc.get('status')!='PASS':raise EngineError('ENGINE_UPGRADE_COLD_BOOT_FAILED:sourcecheck_7')
        gname,gmod=_load_upgrade_module(cold/f'SAVE_GUARD_v{gv}.py',cold,'cold_guard');loaded.append(gname)
        import io
        from contextlib import redirect_stdout,redirect_stderr
        out=io.StringIO();err=io.StringIO()
        with redirect_stdout(out),redirect_stderr(err):grc,_=_upgrade_call('cold_guard',20,gmod.main,[])
        checks.append({'name':'guard','status':'PASS' if grc==0 else 'FAIL','detail':(out.getvalue()+err.getvalue())[-800:]})
        if grc!=0:raise EngineError('ENGINE_UPGRADE_COLD_BOOT_FAILED:guard:'+err.getvalue()[-1000:])
        wname,wmod=_load_upgrade_module(cold/'.game_engine.py',cold,'cold_work_engine');loaded.append(wname)
        boot,_=_upgrade_call('cold_boot',20,wmod.cold_start_packet,cold);expected_packet=str(getattr(wmod,'COLD_START_PACKET_SCHEMA',COLD_START_PACKET_SCHEMA));boot_ok=isinstance(boot,dict) and boot.get('packet')==expected_packet;checks.append({'name':'boot','status':'PASS' if boot_ok else 'FAIL','detail':str(boot)[-800:]})
        if not boot_ok:raise EngineError(f'ENGINE_UPGRADE_COLD_BOOT_FAILED:boot_packet:{(boot or {}).get("packet") if isinstance(boot,dict) else type(boot).__name__}!={expected_packet}')
        q,_=_upgrade_call('cold_query',15,wmod.query_packet,cold,'当前金币余额',5,5,'exact');q_ok=isinstance(q,dict) and q.get('status')=='COMPLETE';checks.append({'name':'query','status':'PASS' if q_ok else 'FAIL','detail':str(q)[-800:]})
        if not q_ok:raise EngineError('ENGINE_UPGRADE_COLD_BOOT_FAILED:exact_query')
        gt=parse_iso(read_json(cold/'state.json').get('game_time'));until=(gt+dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')
        rp,_=_upgrade_call('cold_routineplan',15,wmod.routineplan_packet,cold,until);rp_ok=isinstance(rp,dict) and bool(rp.get('safe_until'));checks.append({'name':'routineplan','status':'PASS' if rp_ok else 'FAIL','detail':str(rp)[-800:]})
        if not rp_ok:raise EngineError('ENGINE_UPGRADE_COLD_BOOT_FAILED:routineplan')
        if any(x.get('status')!='PASS' for x in checks):raise EngineError('ENGINE_UPGRADE_COLD_BOOT_FAILED:subcheck_status')
        return {'status':'PASS','initial_visible_files':visible,'checks':checks,'execution_model':'in_process_isolated_modules'}
    finally:
        for n in loaded:sys.modules.pop(n,None)
        try:writable_tree(cold);shutil.rmtree(cold,ignore_errors=True)
        except Exception:pass

def _upgrade_baseline_engine(root:Path)->Path:
    """Resolve the engine currently bound by authority, not merely this process.

    This matters when a fixed candidate temporarily orchestrates its own bootstrap:
    performance must still compare against the parent authority's engine.
    """
    try:
        idx=parse_index_manifest((root/'INDEX.md').read_text(encoding='utf-8')) or {}
        ver=str(idx.get('engine_version') or '').strip();expected=str(idx.get('engine_sha256') or '').strip()
        candidates=[]
        if ver:candidates.append(root/f'GAME_ENGINE_v{ver}.py')
        candidates.append(root/'.game_engine.py')
        try:
            snap=latest_valid_snapshot(root,verify_parent=True);tp=((snap.get('tools') or {}).get('engine') or {}).get('path')
            if tp:candidates.append(Path(tp))
            candidates.append(Path(snap['dir'])/'_tools'/'game_engine.py')
        except Exception:pass
        for q in candidates:
            q=Path(q)
            if q.is_file() and (not expected or sha256_file(q)==expected):return q.resolve()
    except Exception:pass
    return Path(__file__).resolve()

def _candidate_compatibility_preflight(root:Path,candidate:Path,stage_for_cold:Optional[Path]=None,candidate_module=None)->dict:
    own=False
    if candidate_module is None:
        cname,candidate_module=_load_upgrade_module(candidate,root,'candidate_preflight');own=True
    else:cname=None
    bpath=_upgrade_baseline_engine(root);bname,bmod=_load_upgrade_module(bpath,root,'baseline')
    try:
        checks=[];groups=snapshot_dirs_by_version(root,quarantine_partial=False);versions=sorted(groups,reverse=True)[:3]
        for v in versions:
            snaps=groups[v]
            if not snaps:continue
            p=snaps[0];res,_=_upgrade_call(f'recent_snapshot_{version_text(v)}',20,candidate_module.run_checks,p,full=True,require_manifest=False)
            checks.append({'version':version_text(v),'status':res.get('status'),'detail':str(res)[-600:]})
            if res.get('status')!='PASS':raise EngineError(f'ENGINE_UPGRADE_RECENT_SNAPSHOT_COMPAT_FAILED:{version_text(v)}')
        gt=parse_iso(read_json(root/'state.json').get('game_time'));until=(gt+dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')
        specs=[('query',lambda mod:mod.query_packet(root,'当前金币余额',5,5,'exact')),('routineplan',lambda mod:mod.routineplan_packet(root,until))]
        perf=[]
        for name,fn in specs:
            for label,mod in [('baseline',bmod),('candidate',candidate_module)]:
                _upgrade_call(f'perf_warmup_{name}_{label}',15,fn,mod)
            base_times=[];cand_times=[]
            for i in range(5):
                order=(('baseline',bmod,base_times),('candidate',candidate_module,cand_times)) if i%2==0 else (('candidate',candidate_module,cand_times),('baseline',bmod,base_times))
                for label,mod,bucket in order:
                    _,elapsed=_upgrade_call(f'perf_sample_{name}_{i}_{label}',15,fn,mod);bucket.append(elapsed)
            base_med=_median_ms(base_times);cand_med=_median_ms(cand_times);pair_deltas=[cand_times[i]-base_times[i] for i in range(5)];pair_ratios=[cand_times[i]/base_times[i] if base_times[i]>0 else 1.0 for i in range(5)];paired_delta=_median_ms(pair_deltas);paired_ratio=_median_ms(pair_ratios)
            row={'name':name,'status':'PASS','baseline_engine':bpath.name,'baseline_samples_ms':[round(x,2) for x in base_times],'candidate_samples_ms':[round(x,2) for x in cand_times],'baseline_median_ms':round(base_med,2),'candidate_median_ms':round(cand_med,2),'paired_delta_median_ms':round(paired_delta,2),'paired_ratio_median':round(paired_ratio,4),'absolute_limit_ms':5000,'relative_limit':1.20,'relative_absolute_floor_ms':100,'comparison':'median_of_5_alternating_pairwise_deltas_and_ratios','execution_model':'in_process_isolated_modules'};perf.append(row);checks.append(row)
            if cand_med>5000:raise EngineError(f'ENGINE_UPGRADE_PERFORMANCE_REGRESSION_ABSOLUTE:{name}:{cand_med:.0f}ms')
            if paired_ratio>1.20 and paired_delta>100:raise EngineError(f'ENGINE_UPGRADE_PERFORMANCE_REGRESSION_RELATIVE:{name}:paired_delta={paired_delta:.1f}:paired_ratio={paired_ratio:.3f}')
        cold=_cold_boot_upgrade_gate(root,candidate,stage_for_cold,candidate_module) if stage_for_cold is not None else None
        return {'status':'PASS','checks':checks,'performance':perf,'cold_boot_7file':cold,'execution_model':'in_process_isolated_modules'}
    finally:
        sys.modules.pop(bname,None)
        if own and cname:sys.modules.pop(cname,None)

def _v130_layer_engine_upgrade_packet_01(root:Path,candidate:Path,save_version:str,scope:str,migration_patch:Optional[Path]=None,make_export:bool=False)->dict:
    return _engine_upgrade_packet_v28(root,candidate,save_version,scope,migration_patch,make_export)

BATTLE_SNAPSHOT_SCHEMA="BATTLE_SNAPSHOT_V2"
COMBAT_RUNTIME_SCHEMA="COMBAT_RUNTIME_V2"
MAINTENANCE_RUNTIME_SCHEMA="MAINTENANCE_RUNTIME_V1"
MAINTENANCE_JOB_SCHEMA="MAINTENANCE_JOB_V1"
PLAYER_FLEET_REGISTRY_SCHEMA="PLAYER_FLEET_REGISTRY_V1"
REPLENISHMENT_PLAN_SCHEMA="REPLENISHMENT_PLAN_V1"
BATTLE_SOURCE_KINDS={"STATE_EXISTING","WORLD_BASELINE","SEALED_ENCOUNTER","INTEL_ESTIMATE"}
BATTLE_DIRECT_NUMERIC_FIELDS={"attack","combat_power","shield","armor","hull","ammo","missile_ammo","ammo_salvo","accuracy","evasion","attack_modifier","accuracy_modifier","defense_modifier","ammo_damage_per_unit"}
BATTLE_PROFILE_FIELDS={"attack","shield","armor","hull","ammo","ammo_salvo","retreat_threshold","accuracy","evasion"}


def _combat_catalog(base:Path,state:Optional[dict]=None)->dict:
    """Return the battle-time whitelist derived only from WORLD + sealed STATE registrations."""
    rr=load_runtime_rules(base)
    ce=rr.get('combat_evaluation') or {};ids=set();aliases={}
    def add(cid:str,*names:str):
        ids.add(cid)
        for n in names:
            if isinstance(n,str) and n:aliases[n]=cid
    ship=ce.get('ship') or {}
    for family,v in (ship.get('weapon_base') or {}).items():
        if isinstance(v,dict):
            for size in v:add(f'ship_weapon:{family}:{size}',family,size,f'{family}:{size}')
        else:add(f'ship_weapon:{family}',family)
    for k in (ship.get('shields') or {}):add(f'ship_shield:{k}',k)
    for k in (ship.get('specific_models') or {}):add(f'ship_model:{k}',k)
    ground=ce.get('ground') or {}
    for k in (ground.get('weapon_coefficients') or {}):add(f'ground_weapon:{k}',k)
    for k in (ground.get('burst_values') or {}):add(f'ground_burst:{k}',k)
    for k in (ground.get('powered_armor_nominal_bonus') or {}):add(f'powered_armor:{k}',k)
    for k in (ground.get('combat_robot_nominal_g') or {}):add(f'combat_robot:{k}',k)
    for k in (ground.get('engineering_robot_nominal_g') or {}):
        if not str(k).startswith('external_'):add(f'engineering_robot:{k}',k)
    for k in (ground.get('armored_vehicle_nominal_g') or {}):
        if not str(k).startswith('external_'):add(f'armored_vehicle:{k}',k)
    for k in (ce.get('air_ground') or {}).get('models',{}):add(f'aircraft:{k}',k)
    if state is None:
        try:state=read_json(base/'state.json')
        except Exception:state={}
    regs=((((state.get('engine_runtime') or {}).get('combat_runtime') or {}).get('registered_models') or {}))
    if isinstance(regs,dict):
        for mid,rec in regs.items():
            if isinstance(rec,dict) and rec.get('status','sealed')=='sealed':
                add(str(mid),str(rec.get('name') or ''))
    return {'schema':'COMBAT_CATALOG_V1','model_ids':ids,'aliases':aliases,'registered_state_models':regs}


def _combat_model_id(catalog:dict,raw:str)->str:
    x=str(raw or '').strip()
    if x in catalog.get('model_ids',set()):return x
    y=(catalog.get('aliases') or {}).get(x)
    if y:return y
    raise EngineError(f'BATTLE_MODEL_UNREGISTERED:{x}')


def _battle_snapshot_digest(snapshot:dict)->str:
    obj=copy.deepcopy(snapshot);obj.pop('prepared_token',None)
    return sha256_bytes(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))


def _battle_force_registry(state:dict)->dict:
    reg=state.get('external_force_registry') or {}
    if not isinstance(reg,dict):raise EngineError('EXTERNAL_FORCE_REGISTRY_INVALID')
    return reg


def _battle_force_source(state:dict,sid:str,src:dict)->dict:
    kind=str(src.get('kind') or '').strip()
    if kind not in BATTLE_SOURCE_KINDS:raise EngineError(f'BATTLE_SOURCE_KIND_INVALID:{sid}:{kind}')
    force_id=str(src.get('force_id') or '').strip()
    if force_id:
        reg=_battle_force_registry(state);force=reg.get(force_id)
        if not isinstance(force,dict):raise EngineError(f'BATTLE_FORCE_UNKNOWN:{sid}:{force_id}')
        rev=force.get('revision');given=src.get('revision')
        if given is None:raise EngineError(f'BATTLE_FORCE_REVISION_REQUIRED:{sid}:{force_id}')
        if int(given)!=int(rev):raise EngineError(f'BATTLE_FORCE_REVISION_MISMATCH:{sid}:{force_id}:{given}!={rev}')
        return {'kind':kind,'force_id':force_id,'revision':int(rev),'authority_path':f'STATE.external_force_registry.{force_id}','record':force}
    ap=str(src.get('authority_path') or '').strip()
    if not ap.startswith(('STATE.','state:')):raise EngineError(f'BATTLE_SOURCE_AUTHORITY_REQUIRED:{sid}')
    try:obj=get_by_path(state,ap[6:])
    except KeyError:raise EngineError(f'BATTLE_SOURCE_AUTHORITY_MISSING:{sid}:{ap}')
    if not isinstance(obj,dict):raise EngineError(f'BATTLE_SOURCE_AUTHORITY_OBJECT_REQUIRED:{sid}:{ap}')
    rev=obj.get('revision')
    given=src.get('revision')
    if rev is not None:
        if given is None:raise EngineError(f'BATTLE_SOURCE_REVISION_REQUIRED:{sid}:{ap}')
        if int(given)!=int(rev):raise EngineError(f'BATTLE_SOURCE_REVISION_MISMATCH:{sid}:{given}!={rev}')
    return {'kind':kind,'authority_path':ap,'revision':int(rev) if rev is not None else None,'record':obj}


def _battle_read_profile_from_fields(state:dict,unit:dict,sid:str,uid:str)->tuple[dict,list]:
    ap=str(unit.get('authority_path') or '').strip();fm=unit.get('field_map') or {}
    if not ap.startswith(('STATE.','state:')) or not isinstance(fm,dict):raise EngineError(f'BATTLE_PROFILE_SOURCE_REQUIRED:{sid}:{uid}')
    try:obj=get_by_path(state,ap[6:])
    except KeyError:raise EngineError(f'BATTLE_UNIT_AUTHORITY_MISSING:{sid}:{uid}:{ap}')
    if not isinstance(obj,dict):raise EngineError(f'BATTLE_UNIT_AUTHORITY_OBJECT_REQUIRED:{sid}:{uid}:{ap}')
    extra=set(fm)-BATTLE_PROFILE_FIELDS
    if extra:raise EngineError(f'BATTLE_FIELD_MAP_UNSUPPORTED:{sid}:{uid}:{sorted(extra)}')
    if 'attack' not in fm or not ({'armor','hull'} & set(fm)):raise EngineError(f'BATTLE_FIELD_MAP_ATTACK_ARMOR_REQUIRED:{sid}:{uid}')
    out={};checks=[]
    for std,rel0 in fm.items():
        rel=str(rel0 or '').strip()
        if not rel:raise EngineError(f'BATTLE_FIELD_MAP_PATH_EMPTY:{sid}:{uid}:{std}')
        try:v=get_by_path(obj,rel)
        except KeyError:raise EngineError(f'BATTLE_FIELD_MAP_PATH_MISSING:{sid}:{uid}:{ap}.{rel}')
        if not isinstance(v,(int,float)) or isinstance(v,bool):raise EngineError(f'BATTLE_FIELD_MAP_NUMERIC_REQUIRED:{sid}:{uid}:{std}')
        out[std]=v;checks.append({'path':f'{ap}.{rel}','expected':copy.deepcopy(v)})
    out.setdefault('shield',0);out.setdefault('ammo',0);out.setdefault('ammo_salvo',0);out.setdefault('retreat_threshold',0.25);out.setdefault('accuracy',1.0);out.setdefault('evasion',0.0)
    return out,checks


