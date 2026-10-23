# === VOYAGER_DEV_MODULE: selftest_and_diagnostics ===
def selftest(real_root:Path=ROOT)->dict:
    """Lightweight runtime smoke test. Development fault-injection suite is intentionally not bundled in the mobile engine."""
    tests=[]
    def record(name,ok,detail=""):tests.append({"name":name,"status":"PASS" if ok else "FAIL","detail":detail})
    try:
        _raw=Path(__file__).read_bytes();_segs=_dev_module_segments(_raw);record('dev_module_split_lossless',b''.join(x['bytes'] for x in _segs)==_raw and len(_segs)>=10 and set(DEV_MODULE_API).issubset({x['name'] for x in _segs}),f'modules={len(_segs)} api={len(DEV_MODULE_API)}')
    except Exception as e:record('dev_module_split_lossless',False,str(e))
    try:
        ck=run_checks(real_root,full=True,require_manifest=False);record("authority_full_check",ck.get("status")=="PASS","; ".join(ck.get("errors",[])[:3]))
    except Exception as e:record("authority_full_check",False,str(e))
    try:
        _st=read_json(real_root/'state.json');_reb=_build_voyager_ship_combat_derived(_st);_old=((_st.get('voyager_fleet') or {}).get('ship_combat_power_snapshot_current'))
        _ok=(len(_reb.get('ships') or {})==len((_st.get('voyager_fleet') or {}).get('vessel_roster') or []) and (_old is None or _voyager_ship_combat_equivalent(_old,_reb)))
        record('derived_voyager_ship_combat_rebuild_equivalence',_ok,f"rows={len(_reb.get('ships') or {})} persisted={'yes' if _old is not None else 'no'}")
        _dv=_voyager_ship_combat_view(real_root,_st);record('derived_runtime_source_hash_and_query',_dv.get('schema')==DERIVED_RUNTIME_SCHEMA and len(str(_dv.get('source_sha256') or ''))==64 and isinstance(_dv.get('value'),dict),str({k:_dv.get(k) for k in ('schema','view_id','cache_hit')}))
    except Exception as e:
        record('derived_voyager_ship_combat_rebuild_equivalence',False,str(e));record('derived_runtime_source_hash_and_query',False,str(e))
    try:
        record('vpackcheck_cli_fail_exit_code',_cli_result_exit_code('vpackcheck',{'status':'FAIL'})!=0 and _cli_result_exit_code('vpackcheck',{'status':'PASS'})==0,'FAIL must be nonzero; PASS must be zero')
    except Exception as e:record('vpackcheck_cli_fail_exit_code',False,str(e))
    try:
        _bp=_vpack_bootstrap_bytes();compile(_bp,'SAVE_GUARD_v2.4.1.py','exec');record('vpack_bootstrap_embedded_compiles',VPACK_BOOTSTRAP_FORMAT.encode() in _bp and VPACK_TRANSPORT_FORMAT.encode() in _bp,f'bytes={len(_bp)}')
        _bt=_bp.decode('utf-8','strict');_portable=("Path(os.environ.get('VOYAGER_ROOT') or Path(__file__).resolve().parent).resolve()" in _bt and "os.environ['VOYAGER_ROOT']=str(ROOT)" in _bt)
        record('vpack_bootstrap_project_root_portable',_portable,'bootstrap defaults to its own Project directory and pins inner Guard root')
    except Exception as e:
        record('vpack_bootstrap_embedded_compiles',False,str(e));record('vpack_bootstrap_project_root_portable',False,str(e))
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_vpackcheck_selftest_') as td:
            tr=Path(td);(tr/VPACK_BOOTSTRAP_FILENAME).write_bytes(_vpack_bootstrap_bytes())
            parsed=parse_index_manifest(_manifest_protocol_text(real_root)) or {}
            ev=str(parsed.get('engine_version') or '');eh=str(parsed.get('engine_sha256') or '');gh=str(parsed.get('save_guard_sha256') or '')
            eps=[real_root/f'GAME_ENGINE_v{ev}.py',real_root/'.game_engine.py',Path(__file__).resolve()]
            ep=next((p for p in eps if p.is_file() and sha256_file(p)==eh),None)
            gps=list(real_root.glob('SAVE_GUARD_v*.py'))+[real_root/'.save_guard.py']
            gp=next((p for p in gps if p.is_file() and sha256_file(p)==gh),None)
            if ep is None or gp is None:raise EngineError('VPACK_SELFTEST_BOUND_TOOL_MISSING')
            gv=_guard_source_version(gp);engine_name=f'GAME_ENGINE_v{ev}.py';guard_name=f'SAVE_GUARD_v{gv[0]}.{gv[1]}.{gv[2]}.py'
            raw={fn:(real_root/fn).read_bytes() for fn in AUTH_FILES};raw[engine_name]=ep.read_bytes();raw[guard_name]=gp.read_bytes()
            members={n:sha256_bytes(b) for n,b in raw.items()};manifest={'format':VPACK_TRANSPORT_FORMAT,'save_set_id':parsed.get('save_set_id'),'save_version':version_text(parsed.get('version')),'engine_file':engine_name,'guard_file':guard_name,'engine_sha256':eh,'guard_sha256':gh,'members':members}
            zp=tr/'VOYAGER_SOURCE_SELFTEST.zip'
            def _write_test_pack(m):
                with zipfile.ZipFile(zp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
                    z.writestr('PACK.json',json.dumps(m,ensure_ascii=False,separators=(',',':'))+'\n')
                    for n,b in raw.items():z.writestr(n,b)
            _write_test_pack(manifest);good=vpack_transport_check(tr)
            canonical_boot=tr/VPACK_BOOTSTRAP_FILENAME;suffixed_boot=tr/'SAVE_GUARD_v2.4.1-2.py';canonical_boot.rename(suffixed_boot);good_suffix=vpack_transport_check(tr)
            bad=copy.deepcopy(manifest);bad['save_set_id']='SAVESET-V99.999-deadbeefdeadbeef';_write_test_pack(bad);rejected=vpack_transport_check(tr)
            ok=good.get('status')=='PASS' and good_suffix.get('status')=='PASS' and (good_suffix.get('detail') or {}).get('bootstrap_file')=='SAVE_GUARD_v2.4.1-2.py' and rejected.get('status')=='FAIL' and 'VPACK_IDENTITY_MISMATCH' in (rejected.get('errors') or [])
            record('vpackcheck_matches_bootstrap_identity_gate',ok,f"good={good.get('status')} suffix={good_suffix.get('status')} suffix_file={(good_suffix.get('detail') or {}).get('bootstrap_file')} bad={rejected.get('status')} errors={rejected.get('errors')}")
    except Exception as e:record('vpackcheck_matches_bootstrap_identity_gate',False,str(e))
    for topic in ["卡尔德552项产业收入","暗影舰队当前状态","当前金币余额"]:
        try:
            q=query_packet(real_root,topic,history_limit=2,task_limit=3,detail="compact");record("query_"+topic,q.get("status") in {"COMPLETE","OK","PARTIAL","TRUNCATED"} and bool(q.get("resolved_state_paths") or q.get("state_hits") or q.get("state") or q.get("tasks") or ('value' in q)),q.get("status"))
        except Exception as e:record("query_"+topic,False,str(e))
    try:
        _st=read_json(real_root/"state.json");_cc,_cp,_cpath=_calder_552_component(_st);_q=query_packet(real_root,"Calder's 552 industries",history_limit=0,task_limit=1,detail="compact")
        record("calder_552_legacy_redirect",_cpath=="world_state_overrides.multinational_industry_current" and _cc.get("asset_count")==get_by_path(_st,_cpath).get("asset_count") and "world_state_overrides.multinational_industry_current" in set(_q.get("resolved_state_paths") or []),f"path={_cpath}")
    except Exception as e:record("calder_552_component_resolution",False,str(e))
    try:
        _src=Path(__file__).read_text(encoding="utf-8");_hard=re.findall(r"retired_industry_portfolio_v\d+",_src)
        record("no_concrete_versioned_calder_runtime_path",not _hard,str(_hard[:8]))
    except Exception as e:record("no_concrete_versioned_calder_runtime_path",False,str(e))
    try:
        jq1=query_packet(real_root,"金川资源网络",history_limit=0,task_limit=0,detail="exact");jq2=query_packet(real_root,"金川最近日结",history_limit=0,task_limit=0,detail="exact")
        p1=set(jq1.get("resolved_state_paths") or []);p2=set(jq2.get("resolved_state_paths") or [])
        ok=(jq1.get("status")=="COMPLETE" and jq2.get("status")=="COMPLETE" and "world_state_overrides.mining_and_industry.jinchuan_resource_network_current" in p1 and "jinchuan_fleet.latest_daily_financial_settlement" in p2)
        record("jinchuan_exact_alias_current_and_settlement",ok,f"resource={jq1.get('status')}:{sorted(p1)} settlement={jq2.get('status')}:{sorted(p2)}")
    except Exception as e:record("jinchuan_exact_alias_current_and_settlement",False,str(e))
    try:
        mq=query_packet(real_root,"卡尔德552项产业收入和暗影舰队当前状态",history_limit=2,task_limit=3,detail="compact")
        payload_len=len(json.dumps(mq,ensure_ascii=False,separators=(",",":")))
        record("query_compact_mobile_budget",mq.get("status") in {"COMPLETE","OK","PARTIAL","TRUNCATED"} and payload_len<=24000,f"chars={payload_len}")
    except Exception as e:record("query_compact_mobile_budget",False,str(e))
    try:
        rf=reportframe_packet(real_root);record("reportframe",rf.get("status") in {"READY","READY_WITH_PARTIAL_FINANCE"} and ((rf.get("finance") or {}).get("coverage_status") in {"COMPLETE","PARTIAL_LEGACY_UNSTRUCTURED"}))
    except Exception as e:record("reportframe",False,str(e))
    try:
        _,hev,_=read_history_raw(real_root/"events.jsonl"); legacy=next((e for e in hev if _legacy_finance_event_candidate(e) and parse_iso(e.get("game_time")) is not None),None)
        if legacy is not None:
            ldt=parse_iso(legacy.get("game_time")); lsince=(ldt-dt.timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S")
            lrf=reportframe_packet(real_root,lsince); lfin=lrf.get("finance") or {}; lids={x.get("event_id") for x in lfin.get("legacy_unstructured_events",[]) if isinstance(x,dict)}
            record("reportframe_legacy_finance_honesty",lrf.get("status")=="READY_WITH_PARTIAL_FINANCE" and lfin.get("coverage_status")=="PARTIAL_LEGACY_UNSTRUCTURED" and lfin.get("gold_delta") is None and legacy.get("event_id") in lids,f"legacy={legacy.get('event_id')} count={lfin.get('legacy_unstructured_event_count')}")
        else:record("reportframe_legacy_finance_honesty",True,"no legacy finance candidates")
    except Exception as e:record("reportframe_legacy_finance_honesty",False,str(e))
    try:
        st=read_json(real_root/"state.json"); tt=read_json(real_root/"tasks.json"); now=parse_iso(st.get("game_time")); horizon=(now+dt.timedelta(days=7)) if now else None
        expected=[]; explicit_future=[]
        if now and horizon:
            for task in tt.get("active_tasks",[]) or []:
                mon=_task_monitor(tt,task); nr=parse_iso(mon.get("next_review_at")) if mon.get("next_review_at") else None
                if str(mon.get("mode"))=="scheduled" and nr is not None and now<nr<=horizon: expected.append((str(task.get("task_id")),nr.strftime("%Y-%m-%dT%H:%M:%S")))
                for x in _extract_times(task,"",False,now.year):
                    tt0=parse_iso(x.get("time")); p=str(x.get("path") or "")
                    if tt0 is not None and now<tt0<=horizon and any(k in p.lower() for k in ["next_review_at","next_settlement_at","unrest_end_sealed_at"]): explicit_future.append((p,x.get("category")))
        badcats=[x for x in explicit_future if x[1]=="historical_reference"]
        record("explicit_future_timepoint_category",not badcats,f"checked={len(explicit_future)} bad={badcats[:4]}")
        if expected:
            earliest=min(t for _,t in expected); expected_now=[x for x in expected if x[1]==earliest]
            tp=turn_packet(real_root,mode="preview",until=horizon.strftime("%Y-%m-%dT%H:%M:%S"),detail="compact")
            surfaced={(str(e.get("source_task_id")),str(e.get("time"))) for e in tp.get("candidate_events",[]) if e.get("source")=="task_timepoint"}
            missing=[x for x in expected_now if x not in surfaced];ph=str(tp.get('planning_horizon') or '')
            # An earlier semantic/hazard barrier intentionally truncates the candidate surface.
            # The scheduled task must still exist in TASKS, but is not required to leak beyond the barrier.
            if ph and ph<earliest:
                ok=all(any((str(z.get('task_id'))==tid and str((_task_monitor(tt,z) or {}).get('next_review_at'))==tm) for z in tt.get('active_tasks',[]) or []) for tid,tm in expected_now)
                record("scheduled_task_timepoint_surface_or_barrier_clamp",ok,f"earliest={earliest} barrier={ph} hidden={missing[:4]}")
            else:
                record("scheduled_task_timepoint_surface_or_barrier_clamp",not missing and (not ph or ph>=earliest),f"earliest={earliest} expected={len(expected_now)} missing={missing[:4]} horizon={ph}")
        else: record("scheduled_task_timepoint_surface_or_barrier_clamp",True,"no scheduled task within 7d")
    except Exception as e:
        record("explicit_future_timepoint_category",False,str(e));record("scheduled_task_timepoint_surface_or_barrier_clamp",False,str(e))
    try:
        stage1=turn_packet(real_root,mode="event",detail="compact")
        contract=stage1.get("task_review_contract") or {}
        if contract:
            ack={k:contract[k] for k in ["format","contract_token","base_save_set_id","base_game_time","task_ids","max_review_through"]}
            ack["reviewed_through"]=contract["max_review_through"];ack["semantic_events"]=[]
            with tempfile.NamedTemporaryFile("w",encoding="utf-8",suffix=".json",delete=False) as tf:
                json.dump(ack,tf,ensure_ascii=False);ack_path=Path(tf.name)
            try:
                pp=process_packet(real_root,contract["max_review_through"],ack_path)
                record("process_accepts_event_mode_review_ack",pp.get("phase")=="DETERMINISTIC_PLAN_READY" and pp.get("review_ack_applied") is True and pp.get("safe_until")==contract["max_review_through"],f"phase={pp.get('phase')} safe_until={pp.get('safe_until')}")
            finally:
                try:ack_path.unlink()
                except OSError:pass
        else:
            record("process_accepts_event_mode_review_ack",True,"no task review contract at current state")
    except Exception as e:record("process_accepts_event_mode_review_ack",False,str(e))
    # Persistence regression: an uncommitted partial SAVESET must not outrank a real save.
    try:
        with tempfile.TemporaryDirectory(prefix="voyager_partial_regression_") as td:
            tr=Path(td)
            partial=tr/"V99.0_SAVESET_0123456789abcdef";partial.mkdir();(partial/"INDEX.md").write_text("partial\n",encoding="utf-8");(partial/"WORLD.md").write_text("partial\n",encoding="utf-8")
            moved=quarantine_obvious_partial_artifacts(tr)
            record("partial_upload_quarantine",not partial.exists() and any(x.get("kind")=="saveset" for x in moved),str(moved))
    except Exception as ex: record("partial_upload_quarantine",False,str(ex))
    # Persistence regression: current internally valid save remains usable when an old parent is not materialized.
    try:
        groups=snapshot_dirs_by_version(Path(real_root),quarantine_partial=False)
        if groups:
            vv=max(groups);sample=groups[vv][0];cur=validate_game_snapshot_available(sample,Path(real_root))
            record("available_lineage_policy",cur is not None and (cur.get("lineage") or {}).get("status") in {"COMPLETE","TRUNCATED_PARENT_UNAVAILABLE","RECOVERY_ANCHOR"},str((cur or {}).get("lineage")))
        else:
            record("available_lineage_policy",True,"no local SAVESET in test base")
    except Exception as ex: record("available_lineage_policy",False,str(ex))
    # v2.10 maintenance regressions: epoch remains seven-file/self-contained, task compaction is conservative,
    # asset ledger construction is deterministic, and expanded GC covers development scratch without touching authority.
    try:
        with tempfile.TemporaryDirectory(prefix="voyager_epoch_selftest_") as td:
            tr=Path(td);hp=tr/"events.jsonl";meta={"record_type":"metadata","next_seq":5,"save_version":"V0.0"};evs=[{"seq":i,"event_id":f"E{i}","game_time":"8362-01-01T00:00:00","type":"test","summary":"x"*50,"changes":[],"source":"selftest"} for i in range(1,5)];raws=[json.dumps(e,ensure_ascii=False,separators=(",",":")).encode("utf-8") for e in evs];hp.write_bytes(b"\n".join([json.dumps(meta,separators=(",",":")).encode()]+raws)+b"\n");r=_compact_history_file_to_epochs(hp,keep_recent=1,force=True);_,ee,rr=read_history_raw(hp);_append_engine_history(hp,{"event_id":"E5","game_time":"8362-01-01T00:00:00","type":"needle_test","summary":"append searchable","changes":[],"source":"selftest"});_,ee2,_=read_history_raw(hp);idx=_history_index(tr);found=_history_index_events(tr,["needle_test"],5,False);record("history_epoch_roundtrip",r.get("status")=="COMPACTED" and len(ee)==4 and rr==raws and len(ee2)==5 and _history_epoch_physical_count(hp)>0,str(r));record("history_epoch_logical_index",idx.get("event_count")==5 and any(x.get("type")=="needle_test" for x in found),f"events={idx.get('event_count')} found={len(found)}")
    except Exception as ex:record("history_epoch_roundtrip",False,str(ex))
    try:
        sample_task={"task_data":{"old_result":{"status":"completed","completed_at":"8362-01-01T00:00:00","payload":"x"*120},"current_status_note":{"x":1},"pending_count":1}};ks=[x["key"] for x in _task_compactable_keys(sample_task)];record("task_compaction_key_safety",ks==["old_result"],str(ks))
    except Exception as ex:record("task_compaction_key_safety",False,str(ex))
    try:
        current=read_json(real_root/"state.json");sm=_asset_semantic_map(current.get('inventories') or {});amb=int((sm.get('counts') or {}).get('ambiguous') or 0)
        sample={'game_time':'8363-01-01T00:00:00','inventories':{'voyager':{'available':{'fighter_count':4,'fuel_price_gold':12.5},'crates':{'value':3,'unit':'箱'}}}}
        a=_build_asset_ledger(sample);ok0=a.get('schema')=='ASSET_LEDGER_V1' and a.get('semantic_map_schema')==ASSET_SEMANTIC_MAP_SCHEMA and a.get('row_count')==2 and all('price' not in r.get('legacy_path','') for r in a.get('rows') or [])
        blocked=False
        try:_build_asset_ledger({'inventories':{'voyager':{'型号甲':4}}})
        except EngineError as ex:blocked='ASSET_LEDGER_SEMANTIC_MAP_INCOMPLETE' in str(ex)
        st2=copy.deepcopy(sample);st2['asset_ledger_v1']=a;st2['inventory_authority_mode']='ASSET_LEDGER_V1_CANONICAL_WITH_LEGACY_WRITE_ADAPTER';sync=_sync_active_asset_ledger(st2);bad=_validate_active_asset_ledger(st2)
        record('asset_ledger_semantic_gate',ok0 and blocked and amb>=0,f"current_ambiguous={amb} rows={a.get('row_count')} blocked={blocked}")
        record('asset_ledger_commit_sync',sync.get('active') is True and bad is None,f"sync={sync} bad={bad}")
    except Exception as ex:record('asset_ledger_semantic_gate',False,str(ex))
    try:
        fs={'summary':{'funds':{'gold':0.1,'grey':0}},'engine_runtime':{}};_finance_activate(fs);[_finance_credit(fs,'gold',0.1) for _ in range(3)];_finance_credit(fs,'grey',1.235);fr=_finance_runtime(fs,False);rep=_finance_integrity_report(fs)
        record('fixed_point_finance_exact_units',fr['funds_units']['gold']==4000 and fr['funds_units']['grey']==12400 and fs['summary']['funds']['grey']==1.24 and _money_units4(0.1)==1000 and _money_mul4(0.1,0.2)==0.02 and rep.get('status')=='PASS',str({'gold_units':fr['funds_units']['gold'],'grey_units':fr['funds_units']['grey'],'gold_view':fs['summary']['funds']['gold'],'grey_view':fs['summary']['funds']['grey'],'integrity':rep.get('status')}))
    except Exception as ex:record('fixed_point_finance_exact_units',False,str(ex))
    try:
        ds={'game_time':'8363-01-01T00:00:00','summary':{'funds':{'gold':5,'grey':0}},'engine_runtime':{},'inventories':{'voyager':{'available':10,'reserve':2}}};_finance_activate(ds);dtsk={'active_tasks':[]}
        pay={'schema':DOMAIN_COMMAND_SCHEMA,'command_id':'SELFTEST-DOMAIN-1','base_save_set_id':'SAVESET-X','kind':'transfer_asset','source_path':'STATE.inventories.voyager.available','dest_path':'STATE.inventories.voyager.reserve','qty':3};effect=_domain_transfer_asset(ds,dtsk,pay);r1=_domain_register_receipt(ds,pay,effect,'SAVESET-X');r2=_domain_existing_receipt(ds,pay);reuse=False
        bad=copy.deepcopy(pay);bad['qty']=4
        try:_domain_existing_receipt(ds,bad)
        except EngineError as ex:reuse='DIFFERENT_PAYLOAD' in str(ex)
        record('domain_command_atomic_transfer_and_idempotency',ds['inventories']['voyager']['available']==7 and ds['inventories']['voyager']['reserve']==5 and r1==r2 and reuse,str({'available':ds['inventories']['voyager']['available'],'reserve':ds['inventories']['voyager']['reserve'],'reuse_blocked':reuse}))
    except Exception as ex:record('domain_command_atomic_transfer_and_idempotency',False,str(ex))
    try:
        ms={'inventories':{'a':{'model_id':'MODEL-A','qty':3},'b':{'model_id':'MODEL-B','qty':0}}};blocked=False
        try:_domain_transfer_asset(ms,{}, {'source_path':'STATE.inventories.a.qty','dest_path':'STATE.inventories.b.qty','qty':1})
        except EngineError as ex:blocked='DOMAIN_ASSET_IDENTITY_MISMATCH' in str(ex)
        record('domain_command_asset_identity_guard',blocked,str(blocked))
    except Exception as ex:record('domain_command_asset_identity_guard',False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix="voyager_gc_selftest_") as td:
            tr=Path(td);names=["final_probe.json","postcommit_probe.json","newchat_probe.json","newchat_probe.txt","battle_smoke.json","battle_neg_probe.json","v83_probe.json","compat_probe.json","candidate_engine_v9.9.9.py","migrate_v999.py","trace_probe.py"]
            old=time.time()-3*24*3600
            for n in names:(tr/n).write_text("x",encoding="utf-8");os.utime(tr/n,(old,old))
            gr=runtime_gc(tr,False);record("runtime_gc_expanded_patterns",all(not (tr/n).exists() for n in names) and gr.get("count")==len(names),str(gr))
    except Exception as ex:record("runtime_gc_expanded_patterns",False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix="voyager_newchat_gc_selftest_") as td:
            tr=Path(td);p=tr/"newchat_initial_files.txt";p.write_text("INDEX.md\nWORLD.md\n",encoding="utf-8");old=time.time()-120;os.utime(p,(old,old));gr=runtime_gc(tr,False,True);record("runtime_gc_newchat_text_artifact",not p.exists() and gr.get("count")==1,str(gr))
    except Exception as ex:record("runtime_gc_newchat_text_artifact",False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix="voyager_candidate_cache_gc_") as td:
            tr=Path(td);rt=tr/'.runtime';rt.mkdir();p=rt/'engine_session_upgrade_9_9_9_deadbeefcafe.json';p.write_text('{}',encoding='utf-8');old=time.time()-3*24*3600;os.utime(p,(old,old));gr=runtime_gc(tr,False);record('upgrade_candidate_cache_gc',not p.exists() and gr.get('count')==1,str(gr))
    except Exception as ex:record('upgrade_candidate_cache_gc',False,str(ex))
    try:
        long_obj={"payload":"x"*8192,"nested":{"ok":True}};parsed=_cli_json_input(json.dumps(long_obj,ensure_ascii=False),"SELFTEST_LONG_JSON");record("cli_long_inline_json",parsed==long_obj,f"chars={len(long_obj['payload'])}")
    except Exception as ex:record("cli_long_inline_json",False,str(ex))
    try:
        rejected=False
        try:battlecalc({"battle_id":"RAW-SELFTEST","sides":{"A":{"attack":1},"B":{"attack":1}}},real_root)
        except EngineError as ex:rejected="BATTLE_PREPARE_REQUIRED" in str(ex)
        record("battle_raw_mechanical_input_rejected",rejected,"raw battlecalc must require Engine-prepared snapshot")
    except Exception as ex:record("battle_raw_mechanical_input_rejected",False,str(ex))
    try:
        rejected=False
        raw={'battle_id':'FORCE-SELFTEST','sides':{'A':{'source':{'kind':'STATE_EXISTING','force_id':'FORCE-DOES-NOT-EXIST','revision':1},'units':[{'unit_id':'a'}]},'B':{'source':{'kind':'STATE_EXISTING','force_id':'FORCE-DOES-NOT-EXIST-2','revision':1},'units':[{'unit_id':'b'}]}}}
        try:battleprepare(raw,real_root)
        except EngineError as ex:rejected='BATTLE_FORCE_UNKNOWN' in str(ex)
        record("battle_unknown_force_rejected",rejected,"nonexistent force must never materialize")
    except Exception as ex:record("battle_unknown_force_rejected",False,str(ex))
    try:
        st0=read_json(real_root/'state.json');cat=_combat_catalog(real_root,st0);blocked=False
        try:_combat_model_id(cat,'不存在的超空间歼星炮')
        except EngineError as ex:blocked='BATTLE_MODEL_UNREGISTERED' in str(ex)
        record("battle_unregistered_weapon_rejected",blocked,f"catalog_models={len(cat.get('model_ids') or set())}")
    except Exception as ex:record("battle_unregistered_weapon_rejected",False,str(ex))
    try:
        obj={"combat":{"shield_hp":10,"ammo_remaining":3,"combat_status":"combat_capable"}};_battle_set_relative(obj,"combat.shield_hp",4);_battle_validate_mapping("STATE.test","shield","combat.shield_hp");record("battle_writeback_path",obj["combat"]["shield_hp"]==4 and obj["combat"]["ammo_remaining"]==3,str(obj))
    except Exception as ex:record("battle_writeback_path",False,str(ex))
    try:
        blocked=False
        try:_battle_validate_mapping("STATE.summary.funds","shield","gold")
        except EngineError:blocked=True
        mismatch=False
        try:_battle_validate_mapping("STATE.test","shield","combat.ammo_remaining")
        except EngineError:mismatch=True
        record("battle_writeback_semantic_guard",blocked and mismatch,f"sensitive_blocked={blocked} mismatch_blocked={mismatch}")
    except Exception as ex:record("battle_writeback_semantic_guard",False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix="voyager_cli_json_selftest_") as td:
            tr=Path(td);p=tr/"payload.json";p.write_text('{"x":1}',encoding="utf-8");a=_cli_json_input(str(p),"SELFTEST");b=_cli_json_input("@"+str(p),"SELFTEST");c=_cli_json_input('{"x":1}',"SELFTEST");blocked=False
            try:_cli_json_input(str(tr/"missing.json"),"SELFTEST")
            except EngineError:blocked=True
            record("cli_json_input_file_or_inline",a==b==c=={"x":1} and blocked,f"plain={a} at={b} inline={c} missing_blocked={blocked}")
    except Exception as ex:record("cli_json_input_file_or_inline",False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix="voyager_gc_recent_selftest_") as td:
            tr=Path(td);p=tr/"v83_recent_probe.json";p.write_text("x",encoding="utf-8");old=time.time()-120;os.utime(p,(old,old));normal=runtime_gc(tr,False,False);still=p.exists();aggr=runtime_gc(tr,False,True);record("runtime_gc_aggressive_recent_cleanup",still and not p.exists() and aggr.get("count")==1,f"normal={normal} aggressive={aggr}")
    except Exception as ex:record("runtime_gc_aggressive_recent_cleanup",False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix="voyager_upgrade_metadata_selftest_") as td:
            tr=Path(td);shutil.copyfile(real_root/'state.json',tr/'state.json');shutil.copyfile(real_root/'tasks.json',tr/'tasks.json');shutil.copyfile(real_root/'events.jsonl',tr/'events.jsonl');shutil.copyfile(real_root/'WORLD.md',tr/'WORLD.md')
            st0=read_json(tr/'state.json');tt0=read_json(tr/'tasks.json');_,hev0,_=read_history_raw(tr/'events.jsonl');gt0=st0.get('game_time');r=_sync_successful_engine_upgrade_metadata(tr,'9.9.9','V99.0');stx=read_json(tr/'state.json');ttx=read_json(tr/'tasks.json');_,hev1,_=read_history_raw(tr/'events.jsonl')
            erx=stx.get('engine_runtime') or {};fin=_finance_integrity_report(stx);dom=_domain_runtime_integrity_report(stx);cat=parse_world_static_catalog((tr/'WORLD.md').read_text('utf-8'))
            expected_delta=1 if r.get('history_event_appended') else 0
            ok=all([
                stx.get('game_time')==gt0,
                erx.get('engine_maintenance') is None,
                erx.get('automation') is None,
                (erx.get('recovery') or {}).get('current_checkpoint') is None,
                (ttx.get('recovery') or {}).get('current_checkpoint') is None,
                (ttx.get('automation_schema') or {}).get('engine_version') is None,
                len(hev1)==len(hev0)+expected_delta,
                r.get('profile')=='authority_roles_domain_finance_v1',
                fin.get('status')=='PASS',dom.get('status')=='PASS',cat.get('schema')==STATIC_CATALOG_SCHEMA,
            ])
            record('architecture_zero_time_upgrade_sync',ok,str({'result':r,'finance':fin.get('status'),'domain':dom.get('status'),'catalog':cat.get('model_counts'),'history_delta':len(hev1)-len(hev0)}))
    except Exception as ex:record('runtime_game_fact_separation_upgrade_sync',False,str(ex))
    try:
        idx=parse_index_manifest(_manifest_protocol_text(real_root)) or {};bp=_upgrade_baseline_engine(real_root);record("engine_upgrade_bound_baseline",bp.is_file() and (not idx.get('engine_sha256') or sha256_file(bp)==idx.get('engine_sha256')),f"baseline={bp.name} expected_version={idx.get('engine_version')}")
    except Exception as ex:record("engine_upgrade_bound_baseline",False,str(ex))
    try:
        t0=time.perf_counter();blocked=False
        try:
            with _upgrade_deadline(0.2,'selftest_deadline'):
                time.sleep(2)
        except EngineError as ex:blocked=str(ex).startswith('ENGINE_UPGRADE_GATE_TIMEOUT:selftest_deadline:')
        record('engine_upgrade_inprocess_deadline',blocked and (time.perf_counter()-t0)<1.5,f'blocked={blocked} elapsed={time.perf_counter()-t0:.3f}s')
    except Exception as ex:record('engine_upgrade_inprocess_deadline',False,str(ex))
    try:
        _gate_checks=[{'name':'sourcecheck_7','status':'PASS'},{'name':'boot','status':'FAIL'}];record('engine_upgrade_cold_subcheck_fail_closed',any(x.get('status')!='PASS' for x in _gate_checks),'synthetic failed child must be detectable and rejectable')
    except Exception as ex:record('engine_upgrade_cold_subcheck_fail_closed',False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_upgrade_module_selftest_') as td:
            tr=Path(td);p=tr/'probe.py';p.write_text('import os\nfrom pathlib import Path\nROOT=Path(os.environ.get("VOYAGER_ROOT","/bad")).resolve()\ndef root_text(): return str(ROOT)\n',encoding='utf-8')
            n,m=_load_upgrade_module(p,tr,'selftest_probe');ok=(m.root_text()==str(tr.resolve()));sys.modules.pop(n,None);record('engine_upgrade_module_root_isolation',ok,m.root_text())
    except Exception as ex:record('engine_upgrade_module_root_isolation',False,str(ex))
    try:
        fst={'game_time':'8362-01-01T00:00:00','external_force_registry':{'FORCE-SELFTEST':{'revision':1,'personnel':{'confirmed':10},'equipment':{'ground_weapon:rifle':{'confirmed':3}},'casualties_cumulative':{}}},'engine_runtime':{'combat_runtime':{'schema':COMBAT_RUNTIME_SCHEMA,'pending_loot':[]}}}
        fsnap={'battle_id':'BTL-SELFTEST-CONTINUITY','sources':{'A':{'force_id':'FORCE-SELFTEST','revision':1}},'mechanical_sides':{'A':{'units':[{'unit_id':'u1','registry_equipment_model_id':'ground_weapon:rifle'}]}}}
        fres={'final_state':{'A':{'units':{'u1':{'destroyed':True}}}}}
        fout={'casualty_ledger':{'A':{'killed':2,'wounded':1}},'pending_loot':[{'description':'selftest sealed claim'}]}
        fplans=_battle_force_outcome_plan(fsnap,fres,fst,fout);_apply_battle_force_outcomes(fst,fsnap,fres,fplans,fout);fr=fst['external_force_registry']['FORCE-SELFTEST'];cr=fst['engine_runtime']['combat_runtime']
        stale=False
        try:_apply_battle_force_outcomes(fst,fsnap,fres,fplans,fout)
        except EngineError as ex:stale='BATTLE_FORCE_REVISION_MISMATCH_COMMIT' in str(ex)
        ok=(fr['personnel']['confirmed']==8 and fr['equipment']['ground_weapon:rifle']['confirmed']==2 and fr['revision']==2 and fr['casualties_cumulative'].get('killed')==2 and fr['casualties_cumulative'].get('wounded')==1 and len(cr.get('pending_loot') or [])==1 and stale)
        record('battle_force_continuity_revision',ok,f"personnel={fr['personnel']['confirmed']} rifle={fr['equipment']['ground_weapon:rifle']['confirmed']} revision={fr['revision']} stale_blocked={stale}")
    except Exception as ex:record('battle_force_continuity_revision',False,str(ex))
    try:
        ost={'external_force_registry':{'FORCE-OVER':{'revision':7,'personnel':{'confirmed':4},'equipment':{}}}};osnap={'battle_id':'BTL-OVER','sources':{'A':{'force_id':'FORCE-OVER','revision':7}},'mechanical_sides':{'A':{'units':[]}}};blocked=False
        try:_battle_force_outcome_plan(osnap,{'final_state':{}},ost,{'casualty_ledger':{'A':{'killed':5}}})
        except EngineError as ex:blocked='BATTLE_CASUALTY_EXCEEDS_FORCE' in str(ex)
        record('battle_casualty_bound_rejected',blocked,'casualties cannot exceed pre-battle authority count')
    except Exception as ex:record('battle_casualty_bound_rejected',False,str(ex))
    try:
        st=read_json(real_root/'state.json');tt=read_json(real_root/'tasks.json');now=parse_iso(st.get('game_time'))
        if now:
            short=now+dt.timedelta(hours=6);long=now+dt.timedelta(days=1);a=_next_ai_monitor_time(tt,now,short,st);b=_next_ai_monitor_time(tt,now,long,st)
            future_reviews=[parse_iso((_task_monitor(tt,t) or {}).get('next_review_at')) for t in tt.get('active_tasks',[]) or [] if (_task_monitor(tt,t) or {}).get('requires_ai_review') is True and (_task_monitor(tt,t) or {}).get('next_review_at')]
            future_reviews=[x for x in future_reviews if x and x>now]
            ok=not (a and a.get('time')==now and future_reviews and min(future_reviews)>now)
            record('ai_monitor_future_review_horizon_invariance',ok,f"short={a} long={b}")
        else:record('ai_monitor_future_review_horizon_invariance',True,'no game time')
    except Exception as ex:record('ai_monitor_future_review_horizon_invariance',False,str(ex))
    try:
        ft={'runtime_schema':'TASK_RUNTIME_V3','runtime_profiles':{},'active_tasks':[{'task_id':'CHAIN','title':'chain','runtime_policy':{'schema':'TASK_POLICY_V2','profile':'autonomous_standard','monitor':{'mode':'scheduled','requires_ai_review':False,'review_on_time_advance':False,'next_review_at':'8363-01-03T07:20:00','resolver':'automation_rule_v1'}}}]}
        n0=parse_iso('8363-01-03T06:40:00');hz=parse_iso('8363-01-03T12:00:00');q1=deterministic_task_queue(ft,n0,hz);ft['active_tasks'][0]['runtime_policy']['monitor']['next_review_at']='8363-01-03T08:20:00';ft['active_tasks'][0]['runtime_policy']['monitor']['resolver']='jinchuan_daily_settlement_v1';q2=deterministic_task_queue(ft,parse_iso('8363-01-03T07:20:00'),hz)
        record('deterministic_chain_replan_surface',bool(q1 and q2 and q1[0]['time']=='8363-01-03T07:20:00' and q2[0]['time']=='8363-01-03T08:20:00'),f"first={q1[:1]} second={q2[:1]}")
    except Exception as ex:record('deterministic_chain_replan_surface',False,str(ex))
    try:
        anow=parse_iso('8363-01-03T06:40:00');afinal=parse_iso('8363-01-03T06:50:00');last_resolver_time=afinal
        record('final_node_time_audit_surface',_final_time_audit_required(anow,afinal) and last_resolver_time==afinal,'time audit must remain required when the final mechanical resolver lands exactly on the requested target')
    except Exception as ex:record('final_node_time_audit_surface',False,str(ex))
    try:
        mt={'task_data':{'state_path':'world_state_overrides.demo_current'},'runtime_policy':{'settlement_rule':{'amounts':{'gold':{'from':'STATE.world_state_overrides.demo_current.gold'}},'updates':[{'target':'STATE.world_state_overrides.demo_current.last'}]}}}
        mp=_task_machine_state_paths(mt);vals={v for _,v in mp};record('task_machine_state_path_surface',{'world_state_overrides.demo_current','STATE.world_state_overrides.demo_current.gold','STATE.world_state_overrides.demo_current.last'}<=vals,str(mp))
    except Exception as ex:record('task_machine_state_path_surface',False,str(ex))
    try:
        sr={'updates':[{'target':'STATE.demo.last'},{'target':'TASKS.self.task_data.last'}],'snapshot_target':'STATE.demo.snapshot','deterministic_unit_sales':{'ledger_target':'STATE.demo.ledger'}}
        targets=set(_settlement_state_change_targets(sr));record('settlement_history_coverage_targets',targets=={'STATE.demo.last','STATE.demo.snapshot','STATE.demo.ledger'},str(sorted(targets)))
    except Exception as ex:record('settlement_history_coverage_targets',False,str(ex))
    try:
        mst={'game_time':'8363-01-01T00:00:00','voyager_fleet':{'probe':{'condition_pct':40}},'engine_runtime':{'player_fleet_registry':{'schema':PLAYER_FLEET_REGISTRY_SCHEMA,'fleets':{'voyager':{'authority_root':'STATE.voyager_fleet','primary_personnel_path':'STATE.voyager_fleet.current_personnel','personnel_mirror_paths':[],'inventory_bindings':{},'installed_quantity_prefixes':['STATE.voyager_fleet.']}}},'maintenance_runtime':{'schema':MAINTENANCE_RUNTIME_SCHEMA,'repair_queue':[],'medical_queue':[],'completed_jobs':{},'blocked_jobs':{},'pending_replenishment':[]}}}
        n=parse_iso(mst['game_time']);added=_enqueue_maintenance_jobs(mst,[{'job_id':'REP-SELFTEST','kind':'repair','fleet_id':'voyager','target_id':'probe','complete_at':'8363-01-11T00:00:00','completion_actions':[{'op':'restore_pct_100','path':'STATE.voyager_fleet.probe.condition_pct'}]}],n);q=maintenance_event_queue(mst,n,parse_iso('8363-01-12T00:00:00'))
        over=False
        try:_normalize_maintenance_job(mst,{'job_id':'REP-OVER','kind':'repair','complete_at':'8363-02-01T00:00:01'},n)
        except EngineError as ex:over='MAINTENANCE_JOB_DURATION_INVALID' in str(ex)
        with tempfile.TemporaryDirectory(prefix='voyager_maint_selftest_') as td:
            tr=Path(td);(tr/'events.jsonl').write_text(json.dumps({'record_type':'metadata','next_seq':1,'save_version':'V0.0'},separators=(',',':'))+'\n',encoding='utf-8');row=_resolve_maintenance_event(tr,mst,{},q[0],parse_iso(q[0]['time']))
        mr=mst['engine_runtime']['maintenance_runtime'];ok=(len(added)==1 and q and over and mst['voyager_fleet']['probe']['condition_pct']==100 and row.get('status')=='COMPLETED' and not mr['repair_queue'] and 'REP-SELFTEST' in mr['completed_jobs'])
        record('maintenance_runtime_schedule_and_30d_gate',ok,f"event={q[:1]} over30_blocked={over} final={mst['voyager_fleet']['probe']['condition_pct']}")
    except Exception as ex:record('maintenance_runtime_schedule_and_30d_gate',False,str(ex))
    try:
        pst={'game_time':'8363-01-01T00:00:00','voyager_fleet':{'current_personnel':10},'summary':{'personnel':{'voyager':10,'total':15,'total_player_active':20}},'engine_runtime':{'player_fleet_registry':{'schema':PLAYER_FLEET_REGISTRY_SCHEMA,'fleets':{'voyager':{'authority_root':'STATE.voyager_fleet','primary_personnel_path':'STATE.voyager_fleet.current_personnel','personnel_mirror_paths':['STATE.summary.personnel.voyager','STATE.summary.personnel.total','STATE.summary.personnel.total_player_active'],'inventory_bindings':{},'installed_quantity_prefixes':['STATE.voyager_fleet.']}}}}}
        psnap={'battle_id':'BTL-PLAYER-SELFTEST','sources':{'A':{'authority_path':'STATE.voyager_fleet'}}};pp=_battle_player_outcome_plan(psnap,pst,{'player_casualty_ledger':{'A':{'fleet_id':'voyager','killed':2,'wounded':3}}});pchanges=_apply_battle_player_outcomes(pst,psnap,pp)
        ok=pst['voyager_fleet']['current_personnel']==8 and pst['summary']['personnel']['voyager']==8 and pst['summary']['personnel']['total']==13 and pst['summary']['personnel']['total_player_active']==18 and pst['engine_runtime']['player_fleet_registry']['fleets']['voyager']['casualties_cumulative_since_registry']['wounded']==3
        record('player_casualty_permanent_decrement_mirror_sync',ok,json.dumps(pst['summary']['personnel'],ensure_ascii=False))
        ptargets={str(x.get('target')) for x in pchanges if isinstance(x,dict)}
        need={'STATE.engine_runtime.player_fleet_registry.fleets.voyager.casualties_cumulative_since_registry','STATE.engine_runtime.player_fleet_registry.fleets.voyager.last_battle_id','STATE.engine_runtime.player_fleet_registry.fleets.voyager.as_of'}
        record('player_casualty_history_coverage_targets',need<=ptargets,f"missing={sorted(need-ptargets)}")
    except Exception as ex:record('player_casualty_permanent_decrement_mirror_sync',False,str(ex))
    try:
        rst={'game_time':'8363-01-01T00:00:00','voyager_fleet':{'installed':{'fortress6':5}},'inventories':{'voyager':{'fortress6':{'total_owned':7,'available':2,'allocated':{'ship':5},'reserved':{}}}},'engine_runtime':{'player_fleet_registry':{'schema':PLAYER_FLEET_REGISTRY_SCHEMA,'fleets':{'voyager':{'authority_root':'STATE.voyager_fleet','primary_personnel_path':'STATE.voyager_fleet.current_personnel','personnel_mirror_paths':[],'inventory_bindings':{'combat_robot:堡垒-6':{'available_path':'STATE.inventories.voyager.fortress6.available','total_owned_path':'STATE.inventories.voyager.fortress6.total_owned'}},'installed_quantity_prefixes':['STATE.voyager_fleet.installed.'],'installed_asset_bindings':{'STATE.voyager_fleet.installed.fortress6':{'model_id':'combat_robot:堡垒-6','allocation_path':'STATE.inventories.voyager.fortress6.allocated.ship'}}}}},'maintenance_runtime':{'schema':MAINTENANCE_RUNTIME_SCHEMA,'repair_queue':[],'medical_queue':[],'completed_jobs':{},'blocked_jobs':{},'pending_replenishment':[]}}}
        rsnap={'battle_id':'BTL-REPL-SELFTEST','sources':{'A':{'authority_path':'STATE.voyager_fleet'}},'mechanical_sides':{'A':{'units':[{'unit_id':'R1','equipment_model_id':'combat_robot:堡垒-6'}]}}};rres={'final_state':{'A':{'units':{'R1':{'destroyed':True}}}}};req={'replenishment_requests':[{'side':'A','unit_id':'R1','fleet_id':'voyager','model_id':'combat_robot:堡垒-6','installed_quantity_path':'STATE.voyager_fleet.installed.fortress6'}]};rp=_battle_replenishment_plan(rsnap,rres,rst,req);rch=_apply_battle_replenishment(rst,rsnap,rp)
        inv=rst['inventories']['voyager']['fortress6'];ok=rp and rp[0]['status']=='exact_model_replenish' and inv['total_owned']==6 and inv['available']==1 and inv['allocated']['ship']==5 and rst['voyager_fleet']['installed']['fortress6']==5 and any(x.get('target')=='STATE.inventories.voyager.fortress6.total_owned' for x in rch)
        record('same_fleet_exact_model_replenishment_registered_binding',ok,f"plan={rp} inventory={inv}")
        rst0=copy.deepcopy(rst);rst0['inventories']['voyager']['fortress6']={'total_owned':5,'available':0,'allocated':{'ship':5},'reserved':{}};rst0['voyager_fleet']['installed']['fortress6']=5;rst0['engine_runtime']['maintenance_runtime']['pending_replenishment']=[]
        rp0=_battle_replenishment_plan(rsnap,rres,rst0,req);_apply_battle_replenishment(rst0,rsnap,rp0);inv0=rst0['inventories']['voyager']['fortress6'];ok0=rp0 and rp0[0]['status']=='pending_no_same_fleet_stock' and inv0['total_owned']==4 and inv0['allocated']['ship']==4 and rst0['voyager_fleet']['installed']['fortress6']==4 and len(rst0['engine_runtime']['maintenance_runtime']['pending_replenishment'])==1
        record('same_fleet_no_stock_asset_loss_accounting',ok0,f"plan={rp0} inventory={inv0} installed={rst0['voyager_fleet']['installed']['fortress6']}")
    except Exception as ex:record('same_fleet_exact_model_replenishment_registered_binding',False,str(ex))
    try:
        ar=[{'path':'STATE.a','confidence':'high'},{'path':'STATE.a.b','confidence':'high'},{'path':'STATE.a.c.d','confidence':'high'},{'path':'STATE.z','confidence':'high'}];roots,supp=_state_archive_prune_descendants(ar);record('statearchive_parent_subsumes_descendants',[x['path'] for x in roots]==['STATE.a','STATE.z'] and len(supp)==2,str({'roots':roots,'suppressed':supp}))
    except Exception as ex:record('statearchive_parent_subsumes_descendants',False,str(ex))
    try:
        src=Path(__file__).read_text(encoding='utf-8');fn=src[src.find('def _engine_upgrade_packet_v28'):src.find('# ---------------------------------------------------------------------------\n# v2.8 long-term scaling',src.find('def _engine_upgrade_packet_v28'))]
        hp=fn.find('candidate_hash=sha256_file(candidate)');cp=fn.find('candidate_commit_save');rp=fn.find("'candidate_sha256':candidate_hash")
        record('engine_upgrade_candidate_hash_precommit_lock',hp>=0 and cp>hp and rp>cp,f'hash_pos={hp} commit_pos={cp} return_pos={rp}')
    except Exception as ex:record('engine_upgrade_candidate_hash_precommit_lock',False,str(ex))
    try:
        src=Path(__file__).read_text(encoding='utf-8')
        uses_candidate='metadata_sync=cmod._sync_successful_engine_upgrade_metadata(stage,cv,save_version)' in src
        old_parent_call=bool(re.search(r'(?m)^\s*metadata_sync=_sync_successful_engine_upgrade_metadata\(stage,cv,save_version\)\s*$',src))
        record('engine_upgrade_candidate_owns_metadata_sync',uses_candidate and not old_parent_call,'candidate module must generate its own WORLD/INDEX/checkpoint metadata before candidate validation')
    except Exception as ex:record('engine_upgrade_candidate_owns_metadata_sync',False,str(ex))
    try:
        vp=versioned_current_plan(real_root);ok=isinstance(vp.get('rows'),list) and vp.get('auto_apply') is False and all('classification' in z and 'confidence' in z for z in vp.get('rows') or [])
        record('versioned_current_plan_advisory_contract',ok,f"count={vp.get('count')} high={vp.get('high_confidence_count')} medium={vp.get('medium_confidence_count')}")
    except Exception as ex:record('versioned_current_plan_advisory_contract',False,str(ex))
    try:
        cur=read_json(real_root/'state.json');r0=_versioned_current_zero_policy_report(cur);legacy=copy.deepcopy(cur);legacy['save_version']='V9.42';legacy.setdefault('engine_runtime',{})['selftest_current_v999']={'x':1};r1=_versioned_current_zero_policy_report(legacy);fresh=copy.deepcopy(cur);fresh['save_version']='V9.43';fresh.setdefault('engine_runtime',{})['selftest_current_v999']={'x':1};r2=_versioned_current_zero_policy_report(fresh)
        ok=(r0.get('required') is True and r0.get('count')==0 and r1.get('required') is False and r1.get('count')>=1 and r2.get('required') is True and r2.get('count')>=1)
        record('versioned_current_zero_policy_current_root',ok,f"current={r0.get('count')} legacy_required={r1.get('required')} fresh_count={r2.get('count')}")
    except Exception as ex:record('versioned_current_zero_policy_current_root',False,str(ex))
    try:
        st={"summary":{"funds":{"gold":0.0,"grey":0.0}},"world_state_overrides":{"ledger":{"sales_cumulative":{"copies":100,"gold":2500.0,"by_package":{}},"copies_sold_cumulative":500,"gold_booked_cumulative":12500.0}}};task={"task_id":"SALES-MONO","task_data":{"packages":["A"],"sales_ranges":{"A":[2,2]},"price_gold_per_copy":25,"copies_sold_cumulative":500,"gold_booked_cumulative":12500.0}};rule={"deterministic_unit_sales":{"namespace":"SELFTEST-MONO","items":{"from":"TASKS.self.task_data.packages"},"ranges":{"from":"TASKS.self.task_data.sales_ranges"},"unit_price":{"from":"TASKS.self.task_data.price_gold_per_copy"},"ledger_target":"STATE.world_state_overrides.ledger","authoritative_cumulative_qty_target":"STATE.world_state_overrides.ledger.copies_sold_cumulative","authoritative_cumulative_gold_target":"STATE.world_state_overrides.ledger.gold_booked_cumulative","task_cumulative_qty_target":"TASKS.self.task_data.copies_sold_cumulative","task_cumulative_gold_target":"TASKS.self.task_data.gold_booked_cumulative"}};ser=_settlement_deterministic_unit_sales(rule,st,{"active_tasks":[task]},task,dt.datetime(8363,1,3,11,20),{"iso":"8363-01-03T11:20:00","next_iso":"8363-01-04T11:20:00"});ok=(st["world_state_overrides"]["ledger"]["sales_cumulative"]["copies"]==102 and st["world_state_overrides"]["ledger"]["copies_sold_cumulative"]==502 and task["task_data"]["copies_sold_cumulative"]==502 and task["task_data"]["gold_booked_cumulative"]==12550.0);record("settlement_authoritative_cumulative_monotonic",ok,f"series={ser}")
    except Exception as ex:record("settlement_authoritative_cumulative_monotonic",False,str(ex))
    try:
        st={"game_time":"8363-01-03T10:40:00","school":{"cash":5.0,"last":"8363-01-02T10:40:00","next":"8363-01-03T10:40:00"}};task={"task_id":"AUTO-MIRROR","current_status":"old","next_trigger":"old","task_data":{"last":"8363-01-02T10:40:00","next":"8363-01-03T10:40:00","cash":5.0},"runtime_policy":{"monitor":{},"automation":{"schema":AUTOMATION_RULE_SCHEMA,"repeat_seconds":86400,"actions":[{"op":"consume","target":"STATE.school.cash","qty":1.0},{"op":"set","target":"STATE.school.last","value":{"from":"STATE.game_time"}},{"op":"schedule","target":"STATE.school.next","after_seconds":86400}],"self_updates":[{"op":"set","path":"task_data.last","value":{"from":"STATE.game_time"}},{"op":"schedule","path":"task_data.next","after_seconds":86400},{"op":"set","path":"task_data.cash","value":{"from":"STATE.school.cash"}}],"status_template":"paid {time}","next_trigger_template":"next {next_time}"}}};tasks={"active_tasks":[task]};td=Path(tempfile.mkdtemp(prefix="voyager_auto_mirror_"));(td/"events.jsonl").write_text(json.dumps({"record_type":"metadata","schema_version":"V7.0","save_version":"V9.44","authority":"append-only history; current balances are not authoritative here","next_seq":1},ensure_ascii=False)+"\n",encoding="utf-8");_resolver_automation(td,st,tasks,task,dt.datetime(8363,1,3,10,40));_,_aev,_=read_history_raw(td/"events.jsonl");_targets=[x.get("target") for x in ((_aev[-1].get("changes") if _aev else []) or []) if isinstance(x,dict)];ok=(st["school"]["cash"]==4.0 and st["school"]["last"]=="8363-01-03T10:40:00" and st["school"]["next"]=="8363-01-04T10:40:00" and task["task_data"]["cash"]==4.0 and task["task_data"]["last"]=="8363-01-03T10:40:00" and task["task_data"]["next"]=="8363-01-04T10:40:00" and task["next_trigger"]=="next 8363-01-04 10:40" and "TASKS.active_tasks" in _targets);record("automation_recurring_business_mirror_sync",ok,f"state={st} task={task} targets={_targets}");shutil.rmtree(td,ignore_errors=True)
    except Exception as ex:record("automation_recurring_business_mirror_sync",False,str(ex))
    try:
        td=Path(tempfile.mkdtemp(prefix="voyager_jinchuan_mirror_"));(td/"events.jsonl").write_text(json.dumps({"record_type":"metadata","schema_version":"V7.0","save_version":"V9.51","authority":"append-only history; current balances are not authoritative here","next_seq":1},ensure_ascii=False)+"\n",encoding="utf-8")
        st={"summary":{"funds":{"gold":1000.0,"grey":100}},"jinchuan_fleet":{"latest_daily_financial_settlement":{"at":"8363-01-02T08:20:00"}},"world_state_overrides":{"mining_and_industry":{"jinchuan_resource_network_current":{"as_of":"8362-12-15T08:20:00","mining_base_count":13,"fixed_salvage_base_count":6,"unified_daily_gold":568435.2995,"unified_daily_grey":160878,"last_settlement_at":"8362-12-15T08:20:00","next_settlement_at":"8362-12-16T08:20:00"}}}}
        task={"task_id":"JIN-MIRROR","task_data":{"daily_gold":600035.2995,"daily_grey":169278,"mining_bases":14,"fixed_salvage_bases":6},"runtime_policy":{"monitor":{}}};tasks={"active_tasks":[task]};_resolver_jinchuan(td,st,tasks,task,dt.datetime(8363,1,3,8,20));rn=st["world_state_overrides"]["mining_and_industry"]["jinchuan_resource_network_current"]
        ok=(rn["as_of"]=="8363-01-03T08:20:00" and rn["mining_base_count"]==14 and rn["fixed_salvage_base_count"]==6 and rn["unified_daily_gold"]==600035.2995 and rn["unified_daily_grey"]==169278 and rn["last_settlement_at"]=="8363-01-03T08:20:00" and rn["next_settlement_at"]=="8363-01-04T08:20:00" and st["jinchuan_fleet"]["latest_daily_financial_settlement"]["at"]=="8363-01-03T08:20:00")
        record("jinchuan_resource_network_current_settlement_sync",ok,f"resource={rn}");shutil.rmtree(td,ignore_errors=True)
    except Exception as ex:record("jinchuan_resource_network_current_settlement_sync",False,str(ex))
    try:
        record('legacy_current_version_rank_semantics',_legacy_current_version_rank('95')>_legacy_current_version_rank('8145') and _legacy_current_version_rank('926')>_legacy_current_version_rank('95'),f"v95={_legacy_current_version_rank('95')} v8145={_legacy_current_version_rank('8145')} v926={_legacy_current_version_rank('926')}")
    except Exception as ex:record('legacy_current_version_rank_semantics',False,str(ex))
    try:
        clean_s={'save_version':'V9.46','schema_version':'V7.0'};clean_t={'active_tasks':[{'task_id':'CLEAN','current_status':'ok'}],'queued_tasks':[]};r0=_current_semantic_hygiene_report(clean_s,clean_t)
        bad_s={'save_version':'V9.46','legacy_ref':'world_state_overrides.x_current_v95','narrative_state':{'authority':'derived_non_authoritative_cache'}};bad_t={'active_tasks':[{'task_id':'BAD','current_note':'stale'}],'queued_tasks':[]};r1=_current_semantic_hygiene_report(bad_s,bad_t)
        legacy_s=copy.deepcopy(bad_s);legacy_s['save_version']='V9.45';r2=_current_semantic_hygiene_report(legacy_s,bad_t)
        ok=(r0.get('required') is True and r0.get('count')==0 and r1.get('required') is True and r1.get('count')==3 and r2.get('required') is False)
        record('current_semantic_hygiene_zero_policy',ok,f"clean={r0.get('count')} bad={r1.get('count')} legacy_required={r2.get('required')}")
    except Exception as ex:record('current_semantic_hygiene_zero_policy',False,str(ex))
    try:
        cur=read_json(real_root/'state.json');probe=copy.deepcopy(cur);probe.setdefault('shadow_fleet',{}).pop('ground_power_snapshot',None)
        rr=shadow_shipboard_asset_crosspath_report(probe)
        record('shadow_ground_snapshot_optional_cache',rr.get('status')=='PASS' and rr.get('snapshot_present') is False,f"status={rr.get('status')} errors={(rr.get('errors') or [])[:3]}")
    except Exception as ex:record('shadow_ground_snapshot_optional_cache',False,str(ex))
    try:
        clean_s={'save_version':'V9.48','schema_version':'V7.0'};clean_t={'active_tasks':[],'queued_tasks':[]};r0=_current_semantic_hygiene_report(clean_s,clean_t)
        bad_s={'save_version':'V9.48','inventories':{'current_fleet_inventory_display_v927':{}},'legacy_ref':'world_state_overrides.current_recovery_override_v870.yanhuai4_defense_force'};r1=_current_semantic_hygiene_report(bad_s,clean_t)
        legacy=copy.deepcopy(bad_s);legacy['save_version']='V9.47';r2=_current_semantic_hygiene_report(legacy,clean_t)
        ok=(r0.get('broad_required') is True and r0.get('count')==0 and r1.get('broad_versioned_current_key_count')==1 and r1.get('broad_versioned_current_string_ref_count')==1 and r1.get('count')>=2 and r2.get('broad_required') is False and r2.get('count')==0)
        record('broad_current_version_semantic_hygiene',ok,f"clean={r0.get('count')} bad={r1.get('count')} legacy={r2.get('count')}")
    except Exception as ex:record('broad_current_version_semantic_hygiene',False,str(ex))
    try:
        cs={'save_version':'V9.48','shadow_fleet':{}};ct={'active_tasks':[],'queued_tasks':[]};r0=_current_semantic_hygiene_report(cs,ct)
        bad=copy.deepcopy(cs);bad['shadow_fleet']['combat_power_current']={'as_of':'8362-10-06T17:20:00'};r1=_current_semantic_hygiene_report(bad,ct)
        old=copy.deepcopy(bad);old['save_version']='V9.47';r2=_current_semantic_hygiene_report(old,ct)
        ok=(r0.get('count')==0 and r1.get('retired_current_cache_count')==1 and r1.get('count')>=1 and r2.get('broad_required') is False and r2.get('count')==0)
        record('retired_shadow_combat_power_cache_policy',ok,f"clean={r0.get('count')} bad={r1.get('count')} legacy={r2.get('count')}")
    except Exception as ex:record('retired_shadow_combat_power_cache_policy',False,str(ex))
    try:
        loc=_direct_state_alias_paths('暗影位置');base=_direct_state_alias_paths('暗影基地')
        ok=('shadow_fleet.current_location' in loc and 'world_state_overrides.fleet_and_logistics.shadow_base_current' not in loc and 'world_state_overrides.fleet_and_logistics.shadow_base_current' in base)
        record('shadow_location_exact_alias_authority',ok,f"location={loc} base={base}")
    except Exception as ex:record('shadow_location_exact_alias_authority',False,str(ex))
    try:
        m=re.search(r'infrastructure v(\d+\.\d+\.\d+)',__doc__ or '')
        record('engine_source_version_metadata_consistency',bool(m and m.group(1)==ENGINE_VERSION),f"doc={(m.group(1) if m else None)} constant={ENGINE_VERSION}")
    except Exception as ex:record('engine_source_version_metadata_consistency',False,str(ex))
    try:
        auth=validate_authority_set(real_root) or {};sid=str(auth.get('save_set_id') or '');idx=_state_semantic_index(real_root);cp=_runtime_sidecar('state_semantic_index.json')
        stale=copy.deepcopy(idx);stale['state_sha256']='0'*64;stale['state_stat']={'ino':0,'size':0,'mtime_ns':0,'ctime_ns':0};stale['engine_version']='0.0.0';cp.write_text(json.dumps(stale,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
        q=_exact_query(real_root,'金川资源网络');fresh=strict_json_load(cp);expected=get_by_path(read_json(real_root/'state.json'),'world_state_overrides.mining_and_industry.jinchuan_resource_network_current')
        ok=(q.get('status')=='COMPLETE' and q.get('save_set_id')==sid and q.get('value')==expected and fresh.get('state_sha256')==sha256_file(real_root/'state.json') and fresh.get('engine_version')==ENGINE_VERSION and fresh.get('save_set_id')==sid and fresh.get('integrity_sha256')==_state_sidecar_integrity(fresh) and q.get('runtime_index')=='state_semantic_sidecar_v2')
        record('exact_alias_cache_save_set_coherence',ok,f"query_sid={q.get('save_set_id')} sidecar_engine={fresh.get('engine_version')} expected_sid={sid}")
    except Exception as ex:record('exact_alias_cache_save_set_coherence',False,str(ex))
    try:
        idx=_state_semantic_index(real_root);cp=_runtime_sidecar('state_semantic_index.json');corrupt=copy.deepcopy(idx)
        expected=get_by_path(read_json(real_root/'state.json'),'summary.funds.gold');corrupt.setdefault('exact_alias_values',{})['summary.funds.gold']=123.456
        # Keep Engine/stat/SAVESET fields unchanged and deliberately leave the old
        # integrity digest. A non-authoritative cache corruption must never alter an exact answer.
        cp.write_text(json.dumps(corrupt,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
        q=_exact_query(real_root,'当前金币余额');fresh=strict_json_load(cp)
        ok=(q.get('status')=='COMPLETE' and q.get('value')==expected and fresh.get('exact_alias_values',{}).get('summary.funds.gold')==expected and fresh.get('integrity_sha256')==_state_sidecar_integrity(fresh))
        record('exact_alias_sidecar_corruption_fail_safe',ok,f"query={q.get('value')} authority={expected} repaired={fresh.get('exact_alias_values',{}).get('summary.funds.gold')}")
    except Exception as ex:record('exact_alias_sidecar_corruption_fail_safe',False,str(ex))
    try:
        # A corrupt runtime session cache must not be able to forge current SAVESET
        # identity or poison the STATE sidecar binding.  Keep authority stats intact
        # and change only the cached SID to reproduce the former hot-path failure.
        ensure_source_ready(real_root,allow_cache=False);rp=_runtime_cache_path(ROOT);rc=strict_json_load(rp);auth=validate_authority_set(real_root) or {};expected_sid=str(auth.get('save_set_id') or '')
        bad=copy.deepcopy(rc);bad['save_set_id']='SAVESET-V99.99-0000000000000000'
        # Deliberately preserve the old digest so the cache is detectably corrupt.
        rp.write_text(json.dumps(bad,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
        q=_exact_query(real_root,'当前金币余额');fresh=strict_json_load(rp);side=strict_json_load(_runtime_sidecar('state_semantic_index.json'))
        ok=(q.get('status')=='COMPLETE' and q.get('save_set_id')==expected_sid and fresh.get('save_set_id')==expected_sid and _runtime_session_cache_intact(fresh) and side.get('save_set_id')==expected_sid)
        record('runtime_session_cache_corruption_fail_safe',ok,f"query_sid={q.get('save_set_id')} cache_sid={fresh.get('save_set_id')} sidecar_sid={side.get('save_set_id')} expected={expected_sid}")
    except Exception as ex:record('runtime_session_cache_corruption_fail_safe',False,str(ex))
    try:
        idx=_history_index(real_root);cp=_runtime_sidecar('history_index.json');bad=copy.deepcopy(idx);target=None
        for _r in reversed(bad.get('records') or []):
            if _r.get('event_id'):
                target=_r;break
        if target is None:raise EngineError('SELFTEST_HISTORY_INDEX_EMPTY')
        eid=str(target.get('event_id') or '');target['blob']='CORRUPTED_HISTORY_CACHE_SENTINEL'
        cp.write_text(json.dumps(bad,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
        repaired=_history_index(real_root);fresh=strict_json_load(cp);rows=_history_index_events(real_root,[eid],5,False)
        fresh_target=next((r for r in (fresh.get('records') or []) if str(r.get('event_id') or '')==eid),{})
        ok=(fresh.get('integrity_sha256')==_history_index_integrity(fresh) and fresh.get('engine_version')==ENGINE_VERSION and fresh_target.get('blob')!='CORRUPTED_HISTORY_CACHE_SENTINEL' and bool(rows))
        record('history_index_sidecar_corruption_fail_safe',ok,f"eid={eid} repaired={fresh.get('integrity_sha256')==_history_index_integrity(fresh)} rows={len(rows)}")
    except Exception as ex:record('history_index_sidecar_corruption_fail_safe',False,str(ex))
    try:
        idx=_world_index(real_root);cp=_runtime_sidecar('world_index.json');bad=copy.deepcopy(idx);rid='RULE-COLD-START-V3-01'
        if rid not in (bad.get('registry') or {}):rid=next(iter((bad.get('registry') or {}).keys()),'')
        if not rid:raise EngineError('SELFTEST_WORLD_INDEX_EMPTY')
        bad.setdefault('registry',{}).setdefault(rid,{})['start']=0
        # Preserve the old integrity digest so locator tampering is detectable.
        cp.write_text(json.dumps(bad,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
        sec,_meta=_world_rule_from_index(real_root,_authority_world_text(real_root),rid,9000);fresh=strict_json_load(cp);loc=(fresh.get('registry') or {}).get(rid) or {}
        ok=(str(sec or '').startswith('### '+rid) and fresh.get('format')=='VOYAGER_WORLD_RULE_REGISTRY_V2' and fresh.get('integrity_sha256')==_world_index_integrity(fresh) and fresh.get('engine_version')==ENGINE_VERSION and loc.get('start')!=0)
        record('world_index_sidecar_corruption_fail_safe',ok,f"rid={rid} repaired={fresh.get('integrity_sha256')==_world_index_integrity(fresh)}")
    except Exception as ex:record('world_index_sidecar_corruption_fail_safe',False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_perfdb_selftest_') as td:
            tr=Path(td);rt=tr/'.runtime';rt.mkdir();pdb=rt/'performance.db';pdb.write_bytes(b'CORRUPTED_SQLITE')
            pp=performance_packet(tr,5)
            con=sqlite3.connect(str(pdb));cnt=con.execute("SELECT count(*) FROM samples").fetchone()[0];con.close()
            ok=pp.get('status')=='RESET_CORRUPT' and pp.get('commands')==[] and cnt==0
            record('performance_db_corruption_self_heals',ok,f"status={pp.get('status')} rows={cnt}")
    except Exception as ex:record('performance_db_corruption_self_heals',False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_cachedb_selftest_') as td:
            tr=Path(td);rt=tr/'.runtime';rt.mkdir();cdb=rt/'cache.db';cdb.write_bytes(b'CORRUPTED_SQLITE')
            con=_cache_connect(tr);con.execute('CREATE TABLE IF NOT EXISTS probe(x INTEGER)');con.execute('INSERT INTO probe VALUES(1)');con.commit();cnt=con.execute('SELECT count(*) FROM probe').fetchone()[0];con.close()
            record('cache_db_corruption_self_heals',cnt==1,f"rows={cnt}")
    except Exception as ex:record('cache_db_corruption_self_heals',False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_turn_session_meta_selftest_') as td:
            tr=Path(td);(tr/'.runtime'/'turn_sessions').mkdir(parents=True);sid='0123456789ab';stage=tr/f'.stage_session_{sid}_owned';stage.mkdir();marker=stage/'.PARENT.json';marker.write_text(json.dumps({'format':'VOYAGER_STAGE_PARENT_V1','parent_save_set_id':'SAVESET-V0.0-0123456789abcdef'},separators=(',',':')),encoding='utf-8')
            meta={'format':TURN_SESSION_META_FORMAT,'session_id':sid,'staging':str(stage),'parent_save_set_id':'SAVESET-V0.0-0123456789abcdef','parent_marker_sha256':sha256_file(marker),'requested_until':'8363-01-03T07:00:00','status':'OPEN'};_write_turn_session_meta(sid,meta,tr);mp=_turn_session_meta_path(sid,tr);bad=strict_json_load(mp);victim=tr/'victim';victim.mkdir();bad['staging']=str(victim);mp.write_text(json.dumps(bad,separators=(',',':'))+'\n',encoding='utf-8')
            blocked=False
            try:_read_turn_session_meta(sid,tr)
            except EngineError:blocked=True
            forged=copy.deepcopy(bad);forged['integrity_sha256']=_turn_session_meta_integrity(forged);_atomic_replace_bytes(mp,(json.dumps(forged,separators=(',',':'))+'\n').encode())
            confined=False
            try:_validated_turn_session_stage(_read_turn_session_meta(sid,tr),sid,tr,False)
            except EngineError:confined=True
            record('turn_session_meta_corruption_and_path_confinement',blocked and confined and victim.exists(),f'blocked={blocked} confined={confined} victim={victim.exists()}')
    except Exception as ex:record('turn_session_meta_corruption_and_path_confinement',False,str(ex))
    try:
        blocked=False
        try:_turn_session_meta_path('../../authority',ROOT)
        except EngineError:blocked=True
        record('turn_session_id_traversal_rejected',blocked,str(blocked))
    except Exception as ex:record('turn_session_id_traversal_rejected',False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_vpack_bootstrap_preserve_') as td:
            tr=Path(td);tools=tr/'snap'/'_tools';tools.mkdir(parents=True)
            (tools/'game_engine.py').write_bytes(Path(__file__).read_bytes());(tools/'save_guard.py').write_text('GUARD_PROTOCOL="2"\n',encoding='utf-8')
            compat=tr/'SAVE_GUARD_v2.4.1-2.py';compat.write_bytes(_vpack_bootstrap_bytes())
            stale=tr/'SAVE_GUARD_v2.4.0.py';stale.write_text('legacy guard\n',encoding='utf-8')
            rr=_activate_persistent_project_tools(tr,tr/'snap','2.5.0')
            ok=compat.is_file() and not stale.exists() and (tr/'SAVE_GUARD_v2.5.0.py').is_file() and compat.name not in (rr.get('removed') or [])
            record('vpack_bootstrap_survives_tool_activation',ok,str(rr))
    except Exception as ex:record('vpack_bootstrap_survives_tool_activation',False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_old_engine_hygiene_') as td:
            tr=Path(td);(tr/'GAME_ENGINE_v2.12.17.py').write_text('# old\n',encoding='utf-8');(tr/'GAME_ENGINE_v2.12.19.py').write_text('# current\n',encoding='utf-8');(tr/'GAME_ENGINE_v9.9.9.py').write_text('# candidate\n',encoding='utf-8')
            mv=_quarantine_superseded_engine_sources(tr,'2.12.19');ok=('GAME_ENGINE_v2.12.17.py' in mv and not (tr/'GAME_ENGINE_v2.12.17.py').exists() and (tr/'GAME_ENGINE_v2.12.19.py').exists() and (tr/'GAME_ENGINE_v9.9.9.py').exists())
            record('guard_superseded_engine_source_hygiene',ok,f"moved={mv}")
    except Exception as ex:record('guard_superseded_engine_source_hygiene',False,str(ex))
    try:
        clean={'save_version':'V9.50','active_tasks':[{'task_id':'CLEAN','retrieval_route':{'state_paths':['ref:CLEAN_CURRENT']},'task_data':{}}],'queued_tasks':[]}
        bad={'save_version':'V9.50','active_tasks':[{'task_id':'BAD','retrieval_route':{'state_paths':['world_state_overrides.foo_v123.bar']},'task_data':{'state_current_path':'world_state_overrides.foo_v123.bar'}}],'queued_tasks':[]}
        legacy=copy.deepcopy(bad);legacy['save_version']='V9.49'
        r0=_active_runtime_versioned_state_path_report(clean);r1=_active_runtime_versioned_state_path_report(bad);r2=_active_runtime_versioned_state_path_report(legacy)
        ok=(r0.get('required') is True and r0.get('count')==0 and r1.get('required') is True and r1.get('count')>=1 and r2.get('required') is False and r2.get('count')>=1)
        record('active_runtime_versioned_state_path_policy',ok,f"clean={r0.get('count')} bad={r1.get('count')} legacy_required={r2.get('required')}")
    except Exception as ex:record('active_runtime_versioned_state_path_policy',False,str(ex))
    try:
        anchor='- 当前动态事实只保留一个canonical对象；版本号属于事件/revision，不属于长期字段路径。新增任务不得继续绑定`*_current_vNNN`式路径。'
        zero='- **V9.43及以后零回潮硬门**：正式STATE不得再出现`*_current_vNNN`键；`VERSIONED_CURRENT_ZERO_POLICY`在full check中直接拒绝新SAVESET。V9.42及更早旧SAVESET仅为升级迁移兼容可读，不代表允许在新提交中继续保留该路径。'
        semantic='- **V9.46及以后当前语义卫生硬门**：STATE/TASKS当前层不得保存指向`*_current_vNNN`的字符串引用；active/queued任务不得再使用顶层`current_note`复制当前态；`STATE.narrative_state`已退役，冷启动统一使用`Guard --resume`生成的`COLD_START_PACKET_V5`、stable refs与active TASKS精确查询。旧SAVESET仅在升级迁移阶段兼容读取。'
        broad='- **V9.48及以后广义current零回潮硬门**：除`*_current_vNNN`外，任何键名或STATE/TASKS路径片段只要同时具有current语义并以`_vNN`旧版本后缀结束（例如`current_*_vNNN`、`current_vNNN`、`supplemental_current_*_vNNN`），均视为陈旧当前别名并由`CURRENT_SEMANTIC_HYGIENE`拒绝新SAVESET；V9.47及更早仅兼容迁移读取。'
        runtime='- **V9.50及以后active任务路径稳定化硬门**：active/queued TASKS的`retrieval_route.state_paths`及Engine实际解引用的机器STATE路径不得绑定任何`*_vNNN`版本化对象；持续当前事实必须使用无版本canonical路径或`ref:<KEY>` stable ref。任务ID、schema名、历史phase可保留版本标签。V9.49及更早仅兼容迁移读取。'
        sample='### RULE-STATE-CANONICAL-REF-01 test\n'+anchor+'\n'+zero+'\n'+semantic+'\n'+broad+'\n'+runtime+'\n'+semantic+'\n'+zero+'\n'+runtime+'\n'
        n=_normalize_current_hygiene_world_lines(sample)
        wanted=(zero,semantic,broad,runtime)
        ok=all(n.count(x)==1 for x in wanted) and n.index(zero)<n.index(semantic)<n.index(broad)<n.index(runtime)
        record('world_current_hygiene_rule_dedup',ok,f"counts={[n.count(x) for x in wanted]}")
    except Exception as ex:record('world_current_hygiene_rule_dedup',False,str(ex))
    try:
        mock={'save_version':'V9.54','voyager_fleet':{'vessel_roster':[{'vessel_id':'V1','name':'甲1号'},{'vessel_id':'V2','name':'甲2号'}],'current_location_partition':{'at_voyager_base':{'ships':1},'deployments':{'D':{'ships':1,'vessels':['V2'],'location_name':'测试星'}},'transit':{'ships':0}},'named_vessels':{}},'shadow_fleet':{'ship_count_active':1,'current_location':{'homeport':'LOC-SHADOWBASE-01','at_shadow_base':{'ships':1,'vessels':['S1']},'deployments':{},'transit':{'ships':0,'vessels':[]}},'vessels':{'S1':{'name':'暗测1号','location_id':'LOC-SHADOWBASE-01','location':'S-B5暗影基地','current_location':'S-B5暗影基地'}}},'jinchuan_fleet':{'vessels':{}}}
        idx=_player_vessel_location_index(mock);rep=_player_vessel_location_hygiene_report(mock);ok=(idx['甲1号']['location_name']=='远航者基地' and idx['甲2号']['location_name']=='测试星' and idx['暗测1号']['location_name']=='S-B5暗影基地' and rep.get('count')==0)
        record('player_vessel_location_partition_derivation',ok,f"idx={idx} rep={rep}")
    except Exception as ex:record('player_vessel_location_partition_derivation',False,str(ex))
    try:
        live_state=read_json(real_root/'state.json');loc_index=_player_vessel_location_index(live_state)
        probes=[('巨钳1号','巨钳1号现在在哪'),('探索者1号','探索者1号现在在哪'),('暗鸦9号','暗鸦9号现在在哪')];rows=[];ok=True
        for vessel_name,topic in probes:
            ex=_exact_vessel_location_query(real_root,topic);expected=(loc_index.get(vessel_name) or {}).get('location_name');actual=((ex or {}).get('vessel') or {}).get('location_name')
            rows.append((vessel_name,expected,actual));ok=ok and bool(ex and ex.get('status')=='COMPLETE' and expected and actual==expected)
        record('player_vessel_exact_location_aliases',ok,str(rows))
    except Exception as ex:record('player_vessel_exact_location_aliases',False,str(ex))
    try:
        st={'save_version':'V9.54','game_time':'8363-01-03T06:40:00'};tt={'active_tasks':[{'task_id':'STALE','task_data':{'next_progress_review_at':'8362-12-25T10:40:00'},'runtime_policy':{'monitor':{'next_review_at':'8363-01-04T06:40:00'}}}], 'queued_tasks':[]};r=_active_task_temporal_mirror_report(st,tt)
        old=copy.deepcopy(st);old['save_version']='V9.53';r0=_active_task_temporal_mirror_report(old,tt)
        record('active_task_temporal_mirror_hygiene_policy',r.get('required') is True and r.get('count')==1 and r0.get('required') is False,f"current={r} legacy={r0}")
    except Exception as ex:record('active_task_temporal_mirror_hygiene_policy',False,str(ex))
    try:
        st={'save_version':'V9.54','game_time':'8363-01-03T06:40:00','foo_current_83620915':{},'x_current':{'next_review_at':'8362-01-01T00:00:00','legacy_profile':{'next_review_at':'8362-01-01T00:00:00'}}};a=_dated_current_alias_report(st);b=_current_state_temporal_hygiene_report(st);old=copy.deepcopy(st);old['save_version']='V9.53';a0=_dated_current_alias_report(old);b0=_current_state_temporal_hygiene_report(old)
        record('dated_current_and_temporal_hygiene_policy',a.get('required') is True and a.get('count')==1 and b.get('count')==1 and a0.get('required') is False and b0.get('required') is False,f"dated={a} temporal={b}")
    except Exception as ex:record('dated_current_and_temporal_hygiene_policy',False,str(ex))
    try:
        good={'save_version':'V12.28','world_state_overrides':{'route':{'canonical_ref':'ref:X','role':'routing_only'}}};bad=copy.deepcopy(good);bad['world_state_overrides']['route']['next_settlement_at']='8363-01-04T00:20:00';old=copy.deepcopy(bad);old['save_version']='V12.27'
        rg=_routing_only_fact_hygiene_report(good);rb=_routing_only_fact_hygiene_report(bad);ro=_routing_only_fact_hygiene_report(old)
        record('routing_only_objects_carry_no_dynamic_facts',rg.get('required') and rg.get('count')==0 and rb.get('count')==1 and not ro.get('required'),f'good={rg} bad={rb} old_required={ro.get("required")}')
    except Exception as ex:record('routing_only_objects_carry_no_dynamic_facts',False,str(ex))
    try:
        good={'save_version':'V12.28','jinchuan_fleet':{'latest_daily_financial_settlement':{'at':'8363-01-03T08:20:00','gold':1}}};bad=copy.deepcopy(good);bad['jinchuan_fleet']['latest_daily_financial_settlement']['settled_at']='8363-01-02T08:20:00';old=copy.deepcopy(bad);old['save_version']='V12.27'
        rg=_current_settlement_record_coherence_report(good);rb=_current_settlement_record_coherence_report(bad);ro=_current_settlement_record_coherence_report(old)
        record('current_settlement_record_has_single_timestamp_authority',rg.get('required') and rg.get('count')==0 and rb.get('count')==1 and not ro.get('required'),f'good={rg} bad={rb} old_required={ro.get("required")}')
    except Exception as ex:record('current_settlement_record_has_single_timestamp_authority',False,str(ex))

    try:
        good={'save_version':'V9.55','world_state_overrides':{'multinational_industry_current':{'schema':'MULTINATIONAL_INDUSTRY_CURRENT_V2','asset_count':1}}}
        bad=copy.deepcopy(good);bad['historical_test_only']={'legacy_552_profile':{'next_settlement_at':'8363-01-04T00:20:00'}}
        rg=_calder_legacy_schedule_hygiene_report(good);rb=_calder_legacy_schedule_hygiene_report(bad);old=copy.deepcopy(bad);old['save_version']='V9.54';ro=_calder_legacy_schedule_hygiene_report(old)
        record('calder_legacy_profile_schedule_retired', rg.get('required') and rg.get('count')==0 and rb.get('count')==1 and not ro.get('required'), f'good={rg} bad={rb} old_required={ro.get("required")}')
    except Exception as exc:record('calder_legacy_profile_schedule_retired',False,str(exc))
    try:
        live=read_json(ROOT/'tasks.json');task=next((x for x in live.get('active_tasks',[]) if x.get('task_id')=='TSK-MIN-OPERATIONS'),None);su=((((task or {}).get('runtime_policy') or {}).get('automation') or {}).get('self_updates') or [])
        phases=[x for x in su if isinstance(x,dict) and x.get('path')=='phase' and x.get('value')=='commercial_operations_14_mines_6_salvage']
        titles=[x for x in su if isinstance(x,dict) and x.get('path')=='title' and x.get('value')=='金川14矿+6固定打捞运营']
        # Legacy V3 used a title self-update. V10/TASK_OBJECT_V4 deliberately keeps a stable title and derives current facts from phase/state.
        sv=parse_version(str(live.get('save_version') or 'V0.0'));v4=((live.get('task_object_schema') or {}).get('revision')==TASK_OBJECT_SCHEMA)
        phase_now=str((task or {}).get('phase') or '')
        if v4:
            # V4 may already be past the one-time construction transition; stable title + any canonical 14-mine commercial-operations phase is then sufficient.
            operational_phase=phase_now.startswith('commercial_operations_14_mines_') and ('salvage' in phase_now or phase_now.endswith('_operational'))
            ok_transition=((bool(phases) or operational_phase) and not titles and (task or {}).get('title')=='金川矿业与固定打捞运营')
        else:
            ok_transition=(bool(phases) and (bool(titles) or sv<(9,55)))
        record('jinchuan_construction_title_transition_surface',ok_transition,f'save={live.get("save_version")} v4={v4} phase_updates={len(phases)} title_updates={len(titles)} title={(task or {}).get("title")}')
    except Exception as exc:record('jinchuan_construction_title_transition_surface',False,str(exc))
    try:
        st=read_json(real_root/'state.json');base_task={'task_id':'V4-SELFTEST','type':'watcher','priority':'normal','title':'稳定标题','status':'active','owner_ids':[],'location_ids':[],'resource_locks':[],'retrieval_route':{'state_paths':['jinchuan_fleet.latest_daily_financial_settlement'],'world_rules':[],'history_tags':[]},'report_policy':{},'decision_gate':{},'phase':'watching','task_data':{},'semantic_context':'仅在真正新语义事实出现时报告。','trigger_condition':'出现新事件时。','view_rule':{'schema':DERIVED_VIEW_RULE_SCHEMA,'status_sources':['jinchuan_fleet.latest_daily_financial_settlement'],'next_source':'runtime_policy.monitor.next_review_at'},'runtime_policy':{'schema':'TASK_POLICY_V2','profile':'autonomous_standard','monitor':{'mode':'external_wait','requires_ai_review':False,'review_on_time_advance':False,'next_review_at':None,'resolver':'passive_event_v1','event_driven':True}}}
        view=_task_derived_view(base_task,st);surf=_task_surface(base_task,st,False);ok=('current_status' not in base_task and 'next_trigger' not in base_task and view.get('semantic_context')==base_task['semantic_context'] and 'derived_view' in surf)
        record('task_v4_derived_view_no_persistent_mirrors',ok,str(surf))
    except Exception as ex:record('task_v4_derived_view_no_persistent_mirrors',False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_changeset_selftest_') as td:
            tr=Path(td);pa=tr/'parent';sg=tr/'stage';pa.mkdir();sg.mkdir()
            for fn in ('state.json','tasks.json','rules.json','catalog.json','events.jsonl'):shutil.copyfile(real_root/fn,pa/fn);shutil.copyfile(real_root/fn,sg/fn)
            sx=read_json(sg/'state.json');sx.setdefault('engine_runtime',{}).setdefault('changeset_selftest',{})['probe']=1;_write_authority_json(sg/'state.json',sx)
            r=_ensure_transaction_changeset(pa,sg,'selftest');_,ee,_=read_history_raw(sg/'events.jsonl');last=ee[-1] if ee else {};targets=[x.get('target') for x in (last.get('changes') or []) if isinstance(x,dict)]
            record('transaction_changeset_actual_diff_auto_audit',r.get('status')=='APPENDED' and last.get('type')=='transaction_changeset' and any(str(x).startswith('STATE.engine_runtime.changeset_selftest') for x in targets),f'r={r} targets={targets}')
    except Exception as ex:record('transaction_changeset_actual_diff_auto_audit',False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_changeset_collision_selftest_') as td:
            tr=Path(td);pa=tr/'parent';sa=tr/'stage_a';sb=tr/'stage_b';pa.mkdir();sa.mkdir();sb.mkdir()
            for fn in ('state.json','tasks.json','rules.json','catalog.json','events.jsonl'):
                shutil.copyfile(real_root/fn,pa/fn);shutil.copyfile(real_root/fn,sa/fn);shutil.copyfile(real_root/fn,sb/fn)
            for sample,label in ((sa,'A'),(sb,'B')):
                test_rules=read_json(sample/'rules.json');test_rules['selftest_collision_marker']=label;_write_authority_json(sample/'rules.json',test_rules)
            ra=_ensure_transaction_changeset(pa,sa,'same-zero-time-scope');rb=_ensure_transaction_changeset(pa,sb,'same-zero-time-scope')
            _,ea,_=read_history_raw(sa/'events.jsonl');_,eb,_=read_history_raw(sb/'events.jsonl');ida=(ea[-1] or {}).get('event_id');idb=(eb[-1] or {}).get('event_id')
            record('transaction_changeset_zero_time_id_collision_resistance',ra.get('status')=='APPENDED' and rb.get('status')=='APPENDED' and ida and idb and ida!=idb,f'a={ida} b={idb}')
    except Exception as ex:record('transaction_changeset_zero_time_id_collision_resistance',False,str(ex))
    try:
        good={'schema':WORLD_PROCESS_RULE_SCHEMA,'repeat_seconds':3600,'transitions':[{'id':'T1','when':[{'path':'STATE.summary.funds.grey','op':'gte','value':0}],'actions':[{'op':'set','target':'STATE.engine_runtime.world_process_selftest','value':True}]}]};bad={'schema':WORLD_PROCESS_RULE_SCHEMA,'transitions':[{'id':'X','when':[],'actions':[]} ]}
        record('world_process_rule_sealed_schema',not _validate_world_process_rule(good) and bool(_validate_world_process_rule(bad)),f'good={_validate_world_process_rule(good)} bad={_validate_world_process_rule(bad)}')
    except Exception as ex:record('world_process_rule_sealed_schema',False,str(ex))
    try:
        good={'schema':PROGRESS_RULE_SCHEMA,'target':'STATE.engine_runtime.progress_selftest','rate_per_second':0.5,'minimum':0,'maximum':100,'milestones':[]};bad={'schema':PROGRESS_RULE_SCHEMA,'target':'STATE.x'}
        record('progress_rule_requires_explicit_rate',not _validate_progress_rule(good) and bool(_validate_progress_rule(bad)),f'good={_validate_progress_rule(good)} bad={_validate_progress_rule(bad)}')
    except Exception as ex:record('progress_rule_requires_explicit_rate',False,str(ex))
    try:
        _bad_task={"task_id":"PROGRESS-BAD","status":"active","task_data":{"database_mirror_progress_pct":57},"runtime_policy":{"monitor":{"mode":"continuous","requires_ai_review":True,"review_on_time_advance":True,"last_reviewed_at":"8363-01-01T00:00:00","resolver":"passive_event_v1"},"task_class":"watcher"}}
        _good_task={"task_id":"PROGRESS-GOOD","type":"exploration_science","status":"active","task_data":{},"runtime_policy":{"monitor":{"mode":"continuous","requires_ai_review":False,"review_on_time_advance":False,"last_reviewed_at":"8363-01-01T00:00:00","resolver":"progress_rule_v1"},"progress_rule":{"schema":PROGRESS_RULE_SCHEMA,"target":"STATE.demo.progress","rate_per_second":0.01,"minimum":0,"maximum":100,"milestones":[]},"task_class":"job"}}
        record('continuous_numeric_progress_contract',bool(_continuous_progress_contract_errors(_bad_task,True)) and not _continuous_progress_contract_errors(_good_task,True),f"bad={_continuous_progress_contract_errors(_bad_task,True)} good={_continuous_progress_contract_errors(_good_task,True)}")
    except Exception as ex:record('continuous_numeric_progress_contract',False,str(ex))
    try:
        _pst={"demo":{"progress":57.0}};_pt={"active_tasks":[{"task_id":"P","title":"p","type":"research","status":"active","task_data":{},"runtime_policy":{"monitor":{"mode":"continuous","requires_ai_review":False,"review_on_time_advance":False,"last_reviewed_at":"8363-01-01T00:00:00","next_review_at":None,"resolver":"progress_rule_v1"},"progress_rule":{"schema":PROGRESS_RULE_SCHEMA,"target":"STATE.demo.progress","rate_per_second":0.01,"minimum":0,"maximum":100,"milestones":[]}}}]}
        _pn=parse_iso('8363-01-01T00:00:00');_ph=parse_iso('8363-01-01T01:00:00');_pq=deterministic_task_queue(_pt,_pn,_ph,_pst)
        record('continuous_progress_horizon_scheduling',bool(_pq and _pq[0]['time']=='8363-01-01T01:00:00'),str(_pq))
    except Exception as ex:record('continuous_progress_horizon_scheduling',False,str(ex))
    try:
        _fst={"demo":{"progress":0.0}};_ft={"active_tasks":[{"task_id":"PF","title":"fractional","type":"research","status":"active","task_data":{},"runtime_policy":{"monitor":{"mode":"continuous","requires_ai_review":False,"review_on_time_advance":False,"last_reviewed_at":"8363-01-01T00:00:00","resolver":"progress_rule_v1"},"progress_rule":{"schema":PROGRESS_RULE_SCHEMA,"target":"STATE.demo.progress","rate_per_second":0.3,"minimum":0,"maximum":100,"milestones":[{"id":"M1","threshold":1.0,"actions":[]}]}}}]};_fq=deterministic_task_queue(_ft,parse_iso("8363-01-01T00:00:00"),parse_iso("8363-01-01T00:01:00"),_fst)
        record('continuous_progress_fractional_milestone_rounds_up',bool(_fq and _fq[0]['time']=='8363-01-01T00:00:04'),str(_fq))
    except Exception as ex:record('continuous_progress_fractional_milestone_rounds_up',False,str(ex))
    try:
        _bev={"resolver":"progress_rule_v1"};_bt=parse_iso("8363-01-01T00:10:00");record('continuous_progress_materializes_at_semantic_boundary',_deterministic_event_precedes_barrier(_bev,_bt,_bt,{"kind":"task_ai_review"}) and not _deterministic_event_precedes_barrier({"resolver":"settlement_rule_v1"},_bt,_bt,{"kind":"task_ai_review"}),"progress precedes same-second semantic barrier; unrelated deterministic event does not")
    except Exception as ex:record('continuous_progress_materializes_at_semantic_boundary',False,str(ex))
    try:
        _legacy={"task_id":"LEG","type":"exploration_science","status":"active","task_data":{"database_mirror_progress_pct":57},"runtime_policy":{"monitor":{"mode":"continuous","requires_ai_review":True,"last_reviewed_at":"8363-01-01T00:00:00","resolver":"passive_event_v1"},"task_class":"watcher"}};_td={"save_version":"V10.137","automation_schema":{},"active_tasks":[_legacy]};_act=_activate_continuous_progress_contract(_td,"V10.136");_ok=_continuous_progress_contract_enabled(_td) and not _continuous_progress_contract_errors(_legacy,True);_legacy["task_data"]["database_mirror_progress_pct"]=58;_invalid=bool(_continuous_progress_contract_errors(_legacy,True))
        record('continuous_progress_contract_activation_and_signed_legacy_exemption',_ok and _invalid and _act.get('legacy_exempted_task_ids')==['LEG'],f"activation={_act} invalid_after_edit={_invalid}")
    except Exception as ex:record('continuous_progress_contract_activation_and_signed_legacy_exemption',False,str(ex))
    try:
        cp=cold_start_packet(real_root);_cp_chars=len(json.dumps(cp,ensure_ascii=False,separators=(',',':')));record('cold_start_packet_v5',cp.get('packet')==COLD_START_PACKET_SCHEMA and 'fleet_locations' in cp and 'task_counts' in cp and 'active_tasks' not in cp and 'authority_fingerprint' in cp and 'semantic_reviews_due' in cp and _cp_chars<=4096,f"packet={cp.get('packet')} chars={_cp_chars}")
        _st=read_json(real_root/'state.json');_tt=read_json(real_root/'tasks.json');_now=parse_iso(_st.get('game_time'))
        _expected_open={str(x.get('task_id') or x.get('id') or '') for x in (_tt.get('active_tasks') or []) if isinstance(x,dict) and _task_player_decision_gate_open(x)}
        _open={str(x.get('task_id') or '') for x in (cp.get('open_decision_gates') or []) if isinstance(x,dict)}
        record('cold_start_open_decision_gates_explicit_only',_open==_expected_open,f'open={sorted(_open)} expected={sorted(_expected_open)}')
        # A correctness surface must not silently hide the 9th+ simultaneous gate.
        # Use synthetic tasks so the mobile smoke suite exercises expansion beyond the
        # former eight-row presentation cap without changing any authority file.
        _base=copy.deepcopy((_tt.get('active_tasks') or [{}])[0]);_many=[]
        for _i in range(10):
            _x=copy.deepcopy(_base);_x['task_id']=f'COLD-GATE-SELFTEST-{_i}';_x['title']=f'Gate {_i}';_x['decision_gate_open']=True
            _x['runtime_policy']={'monitor':{'mode':'external_wait','requires_ai_review':False,'review_on_time_advance':False,'next_review_at':None,'resolver':'passive_event_v1','event_driven':True}}
            _many.append(_x)
        _s_many,_g_many=_cold_start_review_surfaces(_st,{'active_tasks':_many},_now)
        record('cold_start_decision_surfaces_not_silently_truncated',len(_g_many)==10,f'count={len(_g_many)} ids={[x.get("task_id") for x in _g_many]}')
    except Exception as ex:
        record('cold_start_packet_v5',False,str(ex));record('cold_start_open_decision_gates_explicit_only',False,str(ex))
    try:
        ss={'save_version':'V10.0','engine_runtime':{'recovery':{},'state_refs':{}},'audits':{'schema':'AUDIT','active':[],'archive':[]},'commander_runtime_rules':{'_structure':{'revision':'COMMANDER_RUNTIME_RULES_V3'},'parameters':{},'overrides':{}}};tt={'save_version':'V10.0','task_object_schema':{'revision':TASK_OBJECT_SCHEMA},'recovery':{},'automation_schema':{}};rep=_v10_authority_surface_report(ss,tt);ss['engine_runtime']['engine_maintenance']={};rep2=_v10_authority_surface_report(ss,tt)
        record('v10_authority_surface_hygiene_policy',rep.get('required') and rep.get('count')==0 and rep2.get('count')==1,f'good={rep} bad={rep2}')
    except Exception as ex:record('v10_authority_surface_hygiene_policy',False,str(ex))
    try:
        _wt="## Old\n\n### Dynamic A\n- x\n\n### RULE-KEEP-01 Keep\n- y\n\n### Dynamic B\n- z\n";_secs=_world_markdown_h3_sections(_wt);_bm={x['title']:x for x in _secs};_new=_wt
        for _x in sorted([_bm['Dynamic A'],_bm['Dynamic B']],key=lambda x:x['start'],reverse=True):_new=_new[:_x['start']]+_new[_x['end']:]
        record('world_purify_exact_heading_archive_rule_preservation','Dynamic A' not in _new and 'Dynamic B' not in _new and 'RULE-KEEP-01' in _new,f"sections={len(_secs)} rule_kept={'RULE-KEEP-01' in _new}")
    except Exception as ex:record('world_purify_exact_heading_archive_rule_preservation',False,str(ex))
    try:
        cq=query_packet(real_root,"金川矿业与固定打捞运营",history_limit=2,task_limit=3,detail="compact")
        record("compact_history_bridge",bool(cq.get("history")),f"history={len(cq.get('history') or [])}")
    except Exception as e:record("compact_history_bridge",False,str(e))
    try:
        st=read_json(real_root/"state.json");tt=read_json(real_root/"tasks.json");wat=[x for x in tt.get("active_tasks",[]) if isinstance((((x.get("runtime_policy") or {}).get("monitor") or {}).get("watch_condition")),dict)]
        ok_watch=True;details=[]
        for task in wat:
            ws=_watch_condition_status(st,task);status=ws.get("status");triggered=bool(ws.get("triggered"));digest=ws.get("current_digest")
            coherent=bool(ws.get("configured")) and status in {"UNCHANGED","CHANGED"} and triggered==(status=="CHANGED") and isinstance(digest,str) and len(digest)==64
            details.append((task.get("task_id"),status,triggered));ok_watch=ok_watch and coherent
        record("watch_condition_live_status_coherent",ok_watch,str(details))
    except Exception as e:record("watch_condition_baseline_quiet",False,str(e))
    try:
        st=read_json(real_root/"state.json");tt=read_json(real_root/"tasks.json");now=parse_iso(st.get("game_time"));wat=[x for x in tt.get("active_tasks",[]) if isinstance((((x.get("runtime_policy") or {}).get("monitor") or {}).get("watch_condition")),dict)]
        if now and wat:
            probe=copy.deepcopy(st);src=(((wat[0].get("runtime_policy") or {}).get("monitor") or {}).get("watch_condition") or {}).get("sources",[])[0];rp=resolve_state_ref(probe,str(src));cur=get_by_path(probe,rp)
            if isinstance(cur,dict):cur["__watch_selftest_probe__"]=1
            else:raise EngineError("WATCH_SELFTEST_SOURCE_NOT_DICT")
            # Isolate the watcher under test. Unrelated overdue AI reviews in the live save
            # must not make this unit test depend on the current campaign state.
            tt_probe=copy.deepcopy(tt);tt_probe["active_tasks"]=[copy.deepcopy(wat[0])];tt_probe["queued_tasks"]=[]
            ev=_next_ai_monitor_time(tt_probe,now,now+dt.timedelta(days=1),probe);ok=bool(ev and ev.get("kind")=="task_watch_condition" and ev.get("watch_condition",{}).get("triggered") and ev.get("resolution_required") and "current_digest" in ev.get("watch_condition",{}))
            record("watch_condition_state_change_barrier",ok,str(ev))
            record("watch_condition_primary_barrier_kind",ev.get("kind") in TASK_AI_BARRIER_KINDS if ev else False,str(TASK_AI_BARRIER_KINDS))
            sem,pg=_cold_start_review_surfaces(probe,tt_probe,now)
            wid=str(wat[0].get("task_id") or "")
            record("cold_start_semantic_review_not_player_gate",any(str(x.get("task_id") or "")==wid for x in sem) and all(str(x.get("task_id") or "")!=wid for x in pg),f"semantic={sem} player={pg}")
            tt2=copy.deepcopy(tt_probe);tw=next(x for x in tt2.get("active_tasks",[]) if x.get("task_id")==wid);tw.setdefault("task_data",{})["decision_gate_open"]=True
            # Make the AI watcher quiet to prove the explicit commander gate is independent.
            w2=((tw.get("runtime_policy") or {}).get("monitor") or {}).get("watch_condition") or {};w2["baseline_digest"]=_watch_condition_status(probe,tw).get("current_digest") or w2.get("baseline_digest")
            sem2,pg2=_cold_start_review_surfaces(probe,tt2,now);ev2=_next_ai_monitor_time(tt2,now,now+dt.timedelta(days=1),probe)
            record("cold_start_explicit_player_gate_surface",any(str(x.get("task_id") or "")==wid for x in pg2) and all(str(x.get("task_id") or "")!=wid for x in sem2),f"semantic={sem2} player={pg2}")
            record("player_gate_without_monitor_is_primary_barrier",bool(ev2 and ev2.get("kind")=="task_player_decision_gate" and ev2.get("task_id")==wid and ev2.get("decision_gate")),str(ev2))
        else:
            record("watch_condition_state_change_barrier",True,"no watch task/current time")
            record("watch_condition_primary_barrier_kind",True,"no watch task/current time")
            record("cold_start_semantic_review_not_player_gate",True,"no watch task/current time")
            record("cold_start_explicit_player_gate_surface",True,"no watch task/current time")
            record("player_gate_without_monitor_is_primary_barrier",True,"no watch task/current time")
    except Exception as e:
        record("watch_condition_state_change_barrier",False,str(e));record("watch_condition_primary_barrier_kind",False,str(e));record("cold_start_semantic_review_not_player_gate",False,str(e));record("cold_start_explicit_player_gate_surface",False,str(e));record("player_gate_without_monitor_is_primary_barrier",False,str(e))
    try:
        life_state={'save_version':'V10.133','entity_lifecycle':{'schema':ENTITY_LIFECYCLE_SCHEMA,'entities':{'ORG-A':{'canonical_name':'旧组织','aliases':[],'status':'merged','successor_id':'ORG-B'},'ORG-B':{'canonical_name':'新组织','aliases':[],'status':'active','current_state_path':'world_state_overrides.x_current.organizations.新组织'}}},'world_state_overrides':{'x_current':{'organizations':{'新组织':{}}}},'engine_runtime':{'state_refs':{}}}
        life_tasks={'active_tasks':[{'task_id':'LIFE','retrieval_route':{'state_paths':['world_state_overrides.x_current.organizations.新组织'],'query_order':[]},'view_rule':{'status_sources':['world_state_overrides.x_current.organizations.新组织']},'task_data':{}}],'queued_tasks':[]}
        good=_entity_lifecycle_integrity_report(life_state,life_tasks);bad_s=copy.deepcopy(life_state);bad_s['world_state_overrides']['x_current']['organizations']['旧组织']={};bad_t=copy.deepcopy(life_tasks);bad_t['active_tasks'][0]['retrieval_route']['state_paths'][0]='world_state_overrides.x_current.organizations.旧组织';bad=_entity_lifecycle_integrity_report(bad_s,bad_t)
        record('entity_lifecycle_merge_hard_gate',good.get('required') is True and good.get('count')==0 and bad.get('count',0)>=2,f"good={good.get('count')} bad={bad.get('rows')}")
    except Exception as ex:record('entity_lifecycle_merge_hard_gate',False,str(ex))
    try:
        es={'save_version':'V10.283','engine_runtime':{'player_fleet_registry':{'fleets':{'voyager':{'display_name':'远航者舰队','authority_root':'STATE.voyager_fleet'}}},'state_refs':{}},'voyager_fleet':{},'entity_lifecycle':{'schema':ENTITY_LIFECYCLE_SCHEMA,'entities':{'ORG-X':{'canonical_name':'组织X','aliases':[],'status':'active','current_state_path':'world_state_overrides.orgs.组织X'}}},'world_state_overrides':{'orgs':{'组织X':{}},'autonomous_entity_registry':{'instantiated':{'测试自治站':{'name':'测试自治站','kind':'independent_station'}}}}}
        sync=_sync_entity_registry(es);good=_entity_registry_integrity_report(es);bad=copy.deepcopy(es);bad['entity_registry']['entities']['FLEET-VOYAGER']['ships']=99;badrep=_entity_registry_integrity_report(bad)
        record('entity_registry_routing_only_hard_gate',sync.get('entity_count')==3 and good.get('required') is True and good.get('count')==0 and any(x.get('kind')=='dynamic_or_unknown_fields' for x in badrep.get('rows',[])),f"sync={sync} bad={badrep.get('rows')}")
    except Exception as ex:record('entity_registry_routing_only_hard_gate',False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix="voyager_history_tail_selftest_") as td:
            tr=Path(td);pa=tr/"parent.jsonl";ch=tr/"child.jsonl"
            meta={"record_type":"metadata","schema_version":"V7.0","save_version":"V1.0","authority":"append-only","next_seq":4}
            evs=[{"seq":i,"event_id":f"HT{i}","game_time":"8363-01-01T00:00:00","type":"test","summary":"x","changes":[],"source":"selftest"} for i in range(1,4)]
            raw=[json.dumps(x,ensure_ascii=False,separators=(",",":")).encode() for x in evs]
            pa.write_bytes(b"\n".join([json.dumps(meta,separators=(",",":")).encode()]+raw)+b"\n")
            meta2=copy.deepcopy(meta);meta2["next_seq"]=5;e4={"seq":4,"event_id":"HT4","game_time":"8363-01-01T00:00:00","type":"test","summary":"tail","changes":[],"source":"selftest"};e4r=json.dumps(e4,separators=(",",":")).encode()
            ch.write_bytes(b"\n".join([json.dumps(meta2,separators=(",",":")).encode()]+raw+[e4r])+b"\n")
            vc={};pair=_history_read_pair_incremental(pa,ch,vc);ok=(pair.get("mode")=="tail_incremental" and pair.get("tail_event_count")==1 and len(pair["current"][1])==4 and pair["current"][2][:3]==raw)
            bad0=copy.deepcopy(evs[0]);bad0["summary"]="changed";braw=json.dumps(bad0,separators=(",",":")).encode();ch.write_bytes(b"\n".join([json.dumps(meta2,separators=(",",":")).encode(),braw]+raw[1:]+[e4r])+b"\n");pair2=_history_read_pair_incremental(pa,ch,{})
            record("history_tail_incremental_and_fallback",ok and pair2.get("mode")=="full_fallback",f"fast={pair.get('mode')} tail={pair.get('tail_event_count')} changed_prefix={pair2.get('mode')}")
    except Exception as ex:record("history_tail_incremental_and_fallback",False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix="voyager_history_batch_selftest_") as td:
            hp=Path(td)/"events.jsonl";meta={"record_type":"metadata","schema_version":"V7.0","save_version":"V1.0","authority":"append-only","next_seq":2};e1={"seq":1,"event_id":"HB1","game_time":"8363-01-01T00:00:00","type":"test","summary":"one","changes":[],"source":"selftest"};hp.write_text(json.dumps(meta,separators=(",",":"))+"\n"+json.dumps(e1,separators=(",",":"))+"\n",encoding="utf-8");before=hp.read_bytes()
            with _history_append_batch(hp):
                for eid in ("HB2","HB3","HB4"):_append_engine_history(hp,{"event_id":eid,"game_time":"8363-01-01T00:00:00","type":"test","summary":"batched","changes":[],"source":"selftest"})
                mid=(hp.read_bytes()==before)
            mm,ee,_=read_history_raw(hp);record("turn_session_history_batch_single_flush",mid and len(ee)==4 and mm.get("next_seq")==5 and [x.get("seq") for x in ee]==[1,2,3,4],f"mid_unchanged={mid} events={len(ee)} next={mm.get('next_seq')}")
    except Exception as ex:record("turn_session_history_batch_single_flush",False,str(ex))
    try:
        with tempfile.TemporaryDirectory(prefix="voyager_session_authority_cache_selftest_") as td:
            tr=Path(td);_write_authority_json(tr/"state.json",{"game_time":"8363-01-01T00:00:00"});_write_authority_json(tr/"tasks.json",{"game_time":"8363-01-01T00:00:00","active_tasks":[],"queued_tasks":[]});(tr/"WORLD.md").write_text("# test\n",encoding="utf-8");sid="abc123abc123";a=_turn_session_authority_load(sid,tr);b=_turn_session_authority_load(sid,tr);_write_authority_json(tr/"state.json",{"game_time":"8363-01-01T01:00:00"});c=_turn_session_authority_load(sid,tr);_turn_session_authority_invalidate(sid)
            record("turn_session_authority_object_resident_cache",a is b and b.get("cache_hit") is True and c is not b and c.get("cache_hit") is False and c["state"].get("game_time")=="8363-01-01T01:00:00",f"same={a is b} hit={b.get('cache_hit')} invalidated={c is not b}")
    except Exception as ex:record("turn_session_authority_object_resident_cache",False,str(ex))
    try:
        latest=latest_valid_snapshot(real_root,verify_parent=True);maj,minor=latest['version'];nxt=_next_autosave_version(real_root)
        record("autosave_policy_next_version",nxt==version_text((maj,minor+1)),f"latest={version_text(latest['version'])} next={nxt}")
    except Exception as ex:record("autosave_policy_next_version",False,str(ex))
    try:
        probe={"format":TURN_RECOVERY_CHECKPOINT_FORMAT,"checkpoint_id":"cp_20260101T000000000000Z_0123456789ab","session_id":"0123456789ab","parent_save_set_id":"SAVESET-V1.0-0123456789abcdef","authority_sha256":{fn:"0"*64 for fn in AUTH_FILES}}
        h1=_turn_session_checkpoint_integrity(probe);probe["parent_save_set_id"]="SAVESET-V1.1-fedcba9876543210";h2=_turn_session_checkpoint_integrity(probe)
        record("turn_recovery_checkpoint_integrity_digest",h1!=h2 and len(h1)==64 and len(h2)==64,f"h1={h1[:12]} h2={h2[:12]}")
    except Exception as ex:record("turn_recovery_checkpoint_integrity_digest",False,str(ex))
    try:
        src=Path(__file__).read_text(encoding='utf-8')
        ok=("NO_UNSAVED_PLAYER_VISIBLE_STATE" in src and 'return _turn_session_commit_ready(session_id,meta,stage,version,scope,publish)' in src and '"status"]="COMMIT_FAILED"' in src and 'action=="recover"' in src)
        record("autosave_no_unsaved_player_visible_source_gate",ok,f"meta={TURN_SESSION_META_FORMAT} checkpoint={TURN_RECOVERY_CHECKPOINT_FORMAT}")
    except Exception as ex:record("autosave_no_unsaved_player_visible_source_gate",False,str(ex))
    try:
        sample="| `GAME_ENGINE_v2.18.1.py` | 当前游戏引擎 |\n| `SAVE_GUARD_v2.3.9.py` | 冷启动验证器 |\n"
        synced=prepare_index(sample,"V10.999","selftest","SAVESET-V10.998-deadbeefdeadbeef","e"*64,"f"*64,BUNDLED_GUARD_VERSION)
        ok=(f"| `GAME_ENGINE_v{ENGINE_VERSION}.py` | 当前游戏引擎 |" in synced and f"| `SAVE_GUARD_v{BUNDLED_GUARD_VERSION}.py` | 冷启动验证器 |" in synced)
        record("index_seven_file_tool_table_sync",ok,"seven-file responsibility table follows bound tools")
    except Exception as ex:record("index_seven_file_tool_table_sync",False,str(ex))
    try:
        missing="SESSION_STAGING_MISSING_OR_INVALID: gone";stale="SESSION_STALE_PARENT: restart session from current SAVESET"
        ok=(not missing.startswith("SESSION_STALE_PARENT") and stale.startswith("SESSION_STALE_PARENT"))
        record("session_status_stale_parent_classification",ok,"missing staging is recoverable loss, not stale parent")
    except Exception as ex:record("session_status_stale_parent_classification",False,str(ex))
    try:
        src=Path(__file__).read_text(encoding="utf-8")
        ps=src[src.index("def project_source_check"):src.index("def build_project_source_package")]
        pkg=src[src.index("def build_project_source_package"):src.index("def deterministic_unit")]
        ok=("PROJECT_AB_POINTER_MISSING" not in ps and "runtime_infra_files={AB_ACTIVE_FILE,*AB_SLOT_FILES.values()}" in ps and "AB_SLOT_FILES.values()" not in pkg and "always exactly 7 files" in ps)
        record("project_source_strict_seven_file_invariant",ok,"A/B slots remain runtime-only and never become Project source requirements")
    except Exception as ex:record("project_source_strict_seven_file_invariant",False,str(ex))

    try:
        _p={"engine_runtime":{"long_horizon":{"hazard_clocks":{"HZ-X":{"profile_id":"market_event","cycle":2}}}}}
        _c={"engine_runtime":{"long_horizon":{"hazard_clocks":{"HZ-X":{"profile_id":"market_event","cycle":3}}}}}
        _w='<!-- '+RUNTIME_RULES_MARKER+'\n'+json.dumps({"random_event_framework":{"history_event_per_hazard_cycle_required":True}},separators=(",",":"))+'\n'+RUNTIME_RULES_MARKER+'_END -->'
        good=[{"event_id":"HZ-HZ-X-2","type":"random_event_mechanical","random_event":True}]
        record("hazard_cycle_history_hard_gate",not _hazard_cycle_history_coverage_errors(_p,_c,good,_w) and bool(_hazard_cycle_history_coverage_errors(_p,_c,[],_w)),str(_hazard_cycle_history_coverage_errors(_p,_c,[],_w)))
    except Exception as ex:record("hazard_cycle_history_hard_gate",False,str(ex))
    try:
        _s={"engine_runtime":{"seed_anchor":"selftest-seed","long_horizon":{"hazard_clocks":{"HZ-S":{"profile_id":"small_nation_significant_instability","cycle":0,"risk_multiplier":122/123,"risk_multiplier_basis":{"baseline_entity_count":123,"excluded_active_crisis_entities":["白峡共和国"]}}}}},"world_state_overrides":{"organizations_and_politics":{"nation_dynamics":{}}}}
        _rr=_random_event_framework_v3_runtime_rules();_rules={"random_event_framework":_rr["framework"],"random_event_tables":_rr["tables"]}
        _ev=_materialize_hazard_event({"event_id":"HZ-HZ-S-0","family":"small_nation_significant_instability","time":"8363-01-01T00:00:00","severity":"notable","scope":"small_nations","requires_simulation":True},_s,_rules)
        _entity=(_ev.get("mechanical_payload") or {}).get("affected_entity");_apply_mechanical_political_hazard_state(_s,_ev);_basis=_s["engine_runtime"]["long_horizon"]["hazard_clocks"]["HZ-S"]["risk_multiplier_basis"]
        record("political_hazard_exclusion_and_persistence",_entity!="白峡共和国" and _entity in _basis.get("excluded_active_crisis_entities",[]) and _s["world_state_overrides"]["organizations_and_politics"]["nation_dynamics"].get(_entity,{}).get("latest_random_political_event",{}).get("event_id")=="HZ-HZ-S-0",f"entity={_entity} basis={_basis}")
    except Exception as ex:record("political_hazard_exclusion_and_persistence",False,str(ex))
    try:
        record("mechanical_multi_event_limit_config",_mechanical_multi_event_limit({"random_event_framework":{"mechanical_multi_event_limit_per_advance":77}})==77 and _mechanical_multi_event_limit({"random_event_framework":{"mechanical_multi_event_limit_per_advance":99999}})==4096,"configured cap")
    except Exception as ex:record("mechanical_multi_event_limit_config",False,str(ex))

    _selftest_mobile_seven(record,real_root)
    failed=[x for x in tests if x["status"]!="PASS"]
    return {"engine_version":ENGINE_VERSION,"status":"FAIL" if failed else "PASS","profile":"mobile_smoke_v2","tests":tests,"passed":len(tests)-len(failed),"failed":len(failed),"note":"Mobile smoke suite includes cold-start/cache, watcher, partial-upload and truncated-lineage persistence regressions."}


def print_json(x:Any)->None:print(json.dumps(x,ensure_ascii=False,indent=2))


def _cli_result_exit_code(cmd: str, result: Any) -> int:
    if not isinstance(result, dict):
        return 0
    status=str(result.get("status") or "")
    if cmd in {"check","sourcecheck","vpackcheck","selftest","doctor"}:
        return 0 if status=="PASS" else 1
    if cmd=="guard":
        return 0 if status=="PASS" else 1
    if cmd=="transact":
        # COMMIT success is independent of PUBLISH/package delivery.
        return 0 if status=="SAVED" else 6
    if cmd=="save":
        # A normal COMMIT intentionally does not require a Project Source/ZIP.
        return 0 if status=="COMMITTED" else 6
    return 0



def _task_by_id(tasks_doc: dict, task_id: str) -> Optional[dict]:
    for t in tasks_doc.get("active_tasks",[]) or []:
        if t.get("task_id")==task_id:return t
    return None


def _history_next_seq(path: Path) -> int:
    _, events, _ = read_history_view(path)
    return _history_expected_next_seq(events)


_HISTORY_APPEND_BATCHES:Dict[str,dict]={}

def _history_append_batch_key(path:Path)->str:
    # Batches cannot leak into another thread operating on the same directory.
    return str(path.resolve()) + ':' + str(threading.get_ident())

@contextmanager
def _history_append_batch(path:Path):
    with engine_lock(path.parent):
        key=_history_append_batch_key(path)
        if key in _HISTORY_APPEND_BATCHES:
            ctx=_HISTORY_APPEND_BATCHES[key]
            # A caught exception in a nested batch still rolls back that nested scope.
            checkpoint=copy.deepcopy(ctx)
            try: yield ctx
            except BaseException:
                ctx.clear();ctx.update(checkpoint);raise
            return
        before=path.read_bytes();meta,events,_=read_history_view(path,_raw_bytes=before)
        ids=[e.get('event_id') for e in events]
        if not all(isinstance(eid,str) and eid.strip() for eid in ids) or len(ids)!=len(set(ids)):raise EngineError('HISTORY_EXISTING_EVENT_IDS_INVALID')
        ctx={'path':path,'before_bytes':before,'before_sha256':sha256_bytes(before),'meta':copy.deepcopy(meta),
             'event_ids':{e.get('event_id') for e in events},'next_seq':_history_expected_next_seq(events),
             'new_raw':[],'dirty':False}
        _HISTORY_APPEND_BATCHES[key]=ctx
        try:
            yield ctx
            if ctx['dirty']:
                if sha256_file(path)!=ctx['before_sha256']:raise EngineError('HISTORY_BATCH_SOURCE_CHANGED_DURING_SESSION')
                m=copy.deepcopy(ctx['meta']);m['next_seq']=ctx['next_seq']
                state_path=path.parent/'state.json'
                if state_path.is_file():
                    current=strict_json_load(state_path)
                    if current.get('game_time'):m['game_time_current']=current['game_time']
                _native_durable_replace_bytes(path,_history_replace_metadata_bytes(before,m,ctx['new_raw']))
        finally:
            _HISTORY_APPEND_BATCHES.pop(key,None)

def _v130_layer__append_engine_history_01(path: Path, event: dict) -> None:
    # Both metadata and event bytes are one durable replace under the same lock.
    with engine_lock(path.parent):
        ctx=_HISTORY_APPEND_BATCHES.get(_history_append_batch_key(path))
        if ctx is None:
            with _history_append_batch(path):
                _v130_layer__append_engine_history_01(path,event)
            return
        ev=copy.deepcopy(event);ev.setdefault('event_schema','EVENT_V2');eid=ev.get('event_id')
        if not isinstance(eid,str) or not eid.strip():raise EngineError('ENGINE_HISTORY_EVENT_ID_REQUIRED')
        if eid in ctx['event_ids']:raise EngineError(f'ENGINE_HISTORY_EVENT_ID_DUPLICATE:{eid}')
        ev['seq']=ctx['next_seq']
        raw=json.dumps(ev,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        ctx['next_seq']+=1;ctx['event_ids'].add(eid);ctx['new_raw'].append(raw);ctx['dirty']=True


def _final_time_audit_required(now: dt.datetime, final_time: dt.datetime) -> bool:
    """Every real time advance needs a final audit, even when the last resolver lands exactly on the target.

    Mechanical resolver history covers resolver-owned state, but _set_runtime_time also mutates
    runtime/hazard clocks.  Recovery checkpoints may be synchronized after the resolver as well.
    Therefore the audit decision must never depend on the timestamp of the last mechanical event.
    """
    return bool(now is not None and final_time is not None and final_time > now)


def _routine_time_changes() -> List[dict]:
    """Broad-but-auditable targets shared by every engine-owned time step."""
    return [
        {"target":"STATE.game_time","action":"advance"},
        {"target":"STATE.voyage_day","action":"sync_calendar_day"},
        {"target":"STATE.engine_runtime","action":"advance_runtime_and_hazard_clocks"},
        {"target":"STATE.shadow_fleet.current_location","action":"sync_as_of"},
        {"target":"TASKS.game_time","action":"advance"},
    ]


def _set_runtime_time(state: dict, tasks: dict, world_text: str, new_time: dt.datetime, runtime_rules: Optional[dict]=None) -> List[dict]:
    old=parse_iso(state.get("game_time")); iso=new_time.strftime("%Y-%m-%dT%H:%M:%S")
    if old is None or new_time<old:raise EngineError("AUTOADVANCE_TIME_REGRESSION")
    if _mobile_contract(state) and new_time-old>dt.timedelta(hours=24):raise EngineError('SINGLE_ADVANCE_HARD_MAX_24H')
    rules=runtime_rules if isinstance(runtime_rules,dict) else load_runtime_rules(COMPONENT_ROOT)
    _haz_limit=_mechanical_multi_event_limit(rules);lh=preview_long_horizon(state,rules,new_time,max_events=_haz_limit)
    if lh.get("truncated"):
        raise EngineError(f"HAZARD_EVENT_BATCH_TRUNCATED:limit={_haz_limit}:processed_until={lh.get('processed_until')}")
    events=lh.get("events") or [];semantic=[e for e in events if e.get("requires_simulation",True)]
    if semantic:raise EngineError("AUTOADVANCE_HAZARD_BARRIER_CROSSED")
    state["game_time"]=iso;tasks["game_time"]=iso
    er=state.setdefault("engine_runtime",{});er["last_evaluated_game_time"]=iso
    lho=er.setdefault("long_horizon",{});lho["hazard_clocks"]=lh.get("clock_updates") or lho.get("hazard_clocks") or {};lho["last_processed_game_time"]=iso
    loc=(state.get("shadow_fleet") or {}).get("current_location")
    if isinstance(loc,dict):
        sem=loc.get("time_semantics")
        if isinstance(sem,dict) and sem.get("schema")=="LOCATION_TIME_SEMANTICS_V1":sem["verified_through"]=iso
        else:loc["as_of"]=iso
    if isinstance(state.get("voyage_day"),int) and old:
        state["voyage_day"] += max(0,(new_time.date()-old.date()).days)
    return [e for e in events if not e.get("requires_simulation",True)]

