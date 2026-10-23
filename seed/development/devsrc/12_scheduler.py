# === VOYAGER_DEV_MODULE: scheduler ===
def routineplan_packet(base: Path, until: str) -> dict:
    ensure_source_ready(base);state=read_json(base/"state.json");tasks=read_json(base/"tasks.json");now=parse_iso(state.get("game_time"));target=parse_iso(until)
    if now is None or target is None or target<now:raise EngineError("ROUTINEPLAN_TIME_INVALID")
    target=_advance_cap(state,target)
    q=deterministic_event_queue(state,tasks,now,target);ai=_next_ai_monitor_time(tasks,now,target,state);rules=load_runtime_rules(base)
    # Fast path: one next event per hazard clock is sufficient to find the first
    # semantic barrier because materialization mode is fixed per event family.
    first=[e for e in next_long_horizon_candidates(state,rules) if parse_iso(e.get("time")) and now<parse_iso(e["time"])<=target]
    haz=[e for e in first if e.get("requires_simulation",True)];hz=min(haz,key=lambda e:e["time"]) if haz else None
    barriers=[]
    if ai:barriers.append({"time":ai["time"].strftime("%Y-%m-%dT%H:%M:%S"),"kind":ai["kind"],"task_id":ai.get("task_id"),"title":ai.get("title"),"watch_condition":ai.get("watch_condition"),"decision_gate":ai.get("decision_gate"),"resolution_required":ai.get("resolution_required"),"scheduled_time":ai.get("scheduled_time"),"reason":ai.get("reason"),"assessment":ai.get("assessment")})
    if hz:barriers.append({"time":hz["time"],"kind":"hazard","event":hz})
    barrier=min(barriers,key=lambda x:x["time"]) if barriers else None
    safe=barrier["time"] if barrier else target.strftime("%Y-%m-%dT%H:%M:%S");safe_dt=parse_iso(safe) or target
    executable=[x for x in q if (lambda _et: _et is not None and _deterministic_event_precedes_barrier(x,_et,safe_dt,barrier))(parse_iso(x.get("time")))]
    # Only enumerate repeated mechanical hazards when at least one such clock can
    # actually fire before the safe boundary. Most routine plans stay on fast path.
    mech_first=[e for e in first if not e.get("requires_simulation",True) and parse_iso(e.get("time"))<=safe_dt]
    mech=[]
    if mech_first:
        lh=preview_long_horizon(state,rules,safe_dt,max_events=_mechanical_multi_event_limit(rules));mech=[e for e in (lh.get("events") or []) if not e.get("requires_simulation",True) and parse_iso(e.get("time")) and now<parse_iso(e["time"])<=safe_dt]
    executable += [{"time":e["time"],"kind":"mechanical_hazard","family":e.get("family"),"event":e,"resolver":"random_event_table_v1"} for e in mech if e["time"] < safe or (not barrier and e["time"]<=safe)]
    executable.sort(key=lambda x:(x.get("time") or "",x.get("task_id") or x.get("family") or ""))
    return {"engine_version":ENGINE_VERSION,"packet":"ROUTINE_PLAN_V2","game_time":state.get("game_time"),"requested_until":until,"deterministic_events":executable,"semantic_barrier":barrier,"safe_until":safe,"ai_review_count":len(task_monitor_queue(tasks,now,target,state=state)),"mechanical_hazard_count":len([x for x in executable if x.get("kind")=="mechanical_hazard"]),"note":"Routine resolvers and table-driven mechanical hazards are engine-owned; only semantic barriers remain AI-owned."}


def _sync_current_checkpoints(state: dict, tasks: dict, version_hint: str, at_iso: str) -> None:
    """V10+: recovery checkpoints are runtime-derived and forbidden in authority.

    Guard/cold_start_packet rebuild the recovery view directly from current STATE/TASKS.
    Old snapshots remain readable, but any new commit removes these derived mirrors.
    """
    er=state.setdefault("engine_runtime",{})
    rec=er.get("recovery")
    if isinstance(rec,dict):rec.pop("current_checkpoint",None)
    trec=tasks.get("recovery")
    if isinstance(trec,dict):trec.pop("current_checkpoint",None)

def autoadvance(root: Path, until: str, version: str, scope: str, make_export: bool=False, make_project: bool=False) -> dict:
    """Compatibility convenience wrapper over AUTOSAVE_POLICY_V1 Turn Sessions.

    Completed intervals commit automatically.  If a semantic/hazard barrier appears,
    deterministic progress is retained in an integrity-bound recovery checkpoint instead
    of being discarded.  The caller then resumes the returned session id after semantic work.
    """
    if root.resolve()!=ROOT.resolve():raise EngineError("AUTOADVANCE_ROOT_MUST_MATCH_ENGINE_ROOT")
    before=read_json(root/"state.json").get("game_time")
    res=turn_session("start",until=until,version=version,scope=scope,publish=make_project)
    if res.get("status")=="COMMITTED":
        return {"status":"SAVED","engine_version":ENGINE_VERSION,"processed_until":((res.get("save") or {}).get("game_time") or until),"requested_until":until,"save":res.get("save"),"session_id":res.get("session_id"),"autosave":True,"autosave_policy":AUTOSAVE_POLICY_SCHEMA,"player_visible_state":"COMMITTED","legacy_export_requested":bool(make_export)}
    if res.get("status")=="BARRIER":
        return {"status":"AI_REQUIRED","engine_version":ENGINE_VERSION,"game_time":before,"processed_until":res.get("processed_until"),"requested_until":until,"semantic_barrier":res.get("semantic_barrier"),"deterministic_events_executed":res.get("deterministic_events_executed") or [],"saved":False,"session_id":res.get("session_id"),"recovery_checkpoint":res.get("recovery_checkpoint"),"rollback":None,"player_visible_state":"RECOVERABLE_CHECKPOINT","autosave_policy":AUTOSAVE_POLICY_SCHEMA,"replanning":"after_each_deterministic_resolver","legacy_export_requested":bool(make_export)}
    return res


ENGINE_UPGRADE_METADATA_PROFILE="engineupgrade_full_gate_v5"


def _normalize_current_hygiene_world_lines(text:str)->str:
    """Keep the three canonical current-hygiene contract lines exactly once.

    This is intentionally a pure text normalizer so engineupgrade metadata sync cannot
    accumulate duplicate policy lines across generations.
    """
    zero='- **V9.43及以后零回潮硬门**：正式STATE不得再出现`*_current_vNNN`键；`VERSIONED_CURRENT_ZERO_POLICY`在full check中直接拒绝新SAVESET。V9.42及更早旧SAVESET仅为升级迁移兼容可读，不代表允许在新提交中继续保留该路径。'
    semantic='- **V9.46及以后当前语义卫生硬门**：STATE/TASKS当前层不得保存指向`*_current_vNNN`的字符串引用；active/queued任务不得再使用顶层`current_note`复制当前态；`STATE.narrative_state`已退役，冷启动统一使用`Guard --resume`生成的`COLD_START_PACKET_V5`、stable refs与active TASKS精确查询。旧SAVESET仅在升级迁移阶段兼容读取。'
    broad='- **V9.48及以后广义current零回潮硬门**：除`*_current_vNNN`外，任何键名或STATE/TASKS路径片段只要同时具有current语义并以`_vNN`旧版本后缀结束（例如`current_*_vNNN`、`current_vNNN`、`supplemental_current_*_vNNN`），均视为陈旧当前别名并由`CURRENT_SEMANTIC_HYGIENE`拒绝新SAVESET；V9.47及更早仅兼容迁移读取。'
    runtime='- **V9.50及以后active任务路径稳定化硬门**：active/queued TASKS的`retrieval_route.state_paths`及Engine实际解引用的机器STATE路径不得绑定任何`*_vNNN`版本化对象；持续当前事实必须使用无版本canonical路径或`ref:<KEY>` stable ref。任务ID、schema名、历史phase可保留版本标签。V9.49及更早仅兼容迁移读取。'
    wanted={zero,semantic,broad,runtime}
    had_nl=text.endswith('\n')
    lines=[ln for ln in text.splitlines() if ln not in wanted]
    anchor='- 当前动态事实只保留一个canonical对象；版本号属于事件/revision，不属于长期字段路径。新增任务不得继续绑定`*_current_vNNN`式路径。'
    try:
        i=lines.index(anchor)+1
    except ValueError:
        # The canonical-ref rule should always exist after replace_rule. Fail closed
        # rather than silently appending policy text to an unrelated section.
        raise EngineError('WORLD_CANONICAL_REF_ANCHOR_MISSING')
    lines[i:i]=[zero,semantic,broad,runtime]
    out='\n'.join(lines)
    return out+('\n' if had_nl else '')


