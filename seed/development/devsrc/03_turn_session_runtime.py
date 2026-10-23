# === VOYAGER_DEV_MODULE: turn_session_runtime ===
def _turn_session_meta_integrity(obj:dict)->str:
    payload=copy.deepcopy(obj);payload.pop("integrity_sha256",None)
    return sha256_bytes(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8"))

def _turn_session_meta_path(session_id:str,root:Path=ROOT)->Path:
    if not isinstance(session_id,str) or not TURN_SESSION_ID_RE.fullmatch(session_id):raise EngineError("SESSION_ID_INVALID")
    return root.resolve()/".runtime"/"turn_sessions"/(session_id+".json")

def _write_turn_session_meta(session_id:str,meta:dict,root:Path=ROOT)->None:
    obj=copy.deepcopy(meta);obj["format"]=TURN_SESSION_META_FORMAT;obj["session_id"]=session_id;obj["integrity_sha256"]=_turn_session_meta_integrity(obj)
    p=_turn_session_meta_path(session_id,root);p.parent.mkdir(parents=True,exist_ok=True)
    _atomic_replace_bytes(p,(json.dumps(obj,ensure_ascii=False,separators=(",",":"))+"\n").encode("utf-8"))

def _read_turn_session_meta(session_id:str,root:Path=ROOT)->dict:
    p=_turn_session_meta_path(session_id,root)
    if not p.is_file():raise EngineError("SESSION_NOT_FOUND")
    try:obj=strict_json_load(p)
    except Exception as e:raise EngineError(f"SESSION_META_INVALID: {e}")
    if not isinstance(obj,dict) or obj.get("format")!=TURN_SESSION_META_FORMAT:raise EngineError("SESSION_META_FORMAT_INVALID: restart the non-authoritative Turn Session")
    if obj.get("session_id")!=session_id:raise EngineError("SESSION_META_ID_MISMATCH")
    if not isinstance(obj.get("integrity_sha256"),str) or obj.get("integrity_sha256")!=_turn_session_meta_integrity(obj):raise EngineError("SESSION_META_INTEGRITY_MISMATCH")
    return obj

def _validated_turn_session_stage(meta:dict,session_id:str,root:Path=ROOT,require_current_parent:bool=True)->Path:
    root=root.resolve();raw=meta.get("staging")
    if not isinstance(raw,str) or not raw:raise EngineError("SESSION_STAGING_PATH_MISSING")
    rawp=Path(raw)
    try:
        if rawp.is_symlink():raise EngineError("SESSION_STAGING_SYMLINK_FORBIDDEN")
        stage=rawp.resolve(strict=True)
    except EngineError:raise
    except Exception as e:raise EngineError(f"SESSION_STAGING_MISSING_OR_INVALID: {e}")
    if stage.parent!=root or not stage.name.startswith(f".stage_session_{session_id}_"):raise EngineError("SESSION_STAGING_PATH_OUTSIDE_OWNED_SCOPE")
    if not stage.is_dir() or stage.is_symlink():raise EngineError("SESSION_STAGING_NOT_SAFE_DIRECTORY")
    marker=stage/".PARENT.json"
    if not marker.is_file():raise EngineError("SESSION_STAGING_PARENT_MARKER_MISSING")
    if sha256_file(marker)!=meta.get("parent_marker_sha256"):raise EngineError("SESSION_STAGING_PARENT_MARKER_CHANGED")
    try:pm=strict_json_load(marker)
    except Exception as e:raise EngineError(f"SESSION_STAGING_PARENT_MARKER_INVALID: {e}")
    if pm.get("format")!="VOYAGER_STAGE_PARENT_V1" or pm.get("parent_save_set_id")!=meta.get("parent_save_set_id"):raise EngineError("SESSION_STAGING_PARENT_BINDING_MISMATCH")
    if require_current_parent:
        latest=latest_valid_snapshot(root,verify_parent=True)
        if latest.get("save_set_id")!=meta.get("parent_save_set_id"):raise EngineError("SESSION_STALE_PARENT: restart session from current SAVESET")
        validate_stage_parent(stage,root,latest)
    return stage

_TURN_SESSION_AUTHORITY_CACHE:Dict[str,dict]={}

def _turn_session_authority_signature(stage:Path)->dict:
    return {fn:sha256_file(stage/fn) for fn in ("state.json","tasks.json","rules.json","catalog.json")}

def _turn_session_authority_load(session_id:str,stage:Path)->dict:
    sig=_turn_session_authority_signature(stage);row=_TURN_SESSION_AUTHORITY_CACHE.get(session_id)
    if isinstance(row,dict) and row.get("stage")==str(stage.resolve()) and row.get("signature")==sig:
        row["cache_hit"]=True;return row
    world=_authority_world_text(stage)
    row={"stage":str(stage.resolve()),"signature":sig,"state":read_json(stage/"state.json"),"tasks":read_json(stage/"tasks.json"),"world":world,"rules":load_runtime_rules(stage),"cache_hit":False}
    _TURN_SESSION_AUTHORITY_CACHE[session_id]=row;return row

def _turn_session_authority_refresh(session_id:str,stage:Path,row:dict)->None:
    row["signature"]=_turn_session_authority_signature(stage);row["cache_hit"]=False;_TURN_SESSION_AUTHORITY_CACHE[session_id]=row

def _turn_session_authority_invalidate(session_id:str)->None:
    _TURN_SESSION_AUTHORITY_CACHE.pop(session_id,None)

def _turn_session_checkpoint_root(session_id:str,root:Path=ROOT)->Path:
    if not isinstance(session_id,str) or not TURN_SESSION_ID_RE.fullmatch(session_id):raise EngineError("SESSION_ID_INVALID")
    return root.resolve()/".runtime"/"recovery_checkpoints"/session_id


def _turn_session_checkpoint_integrity(obj:dict)->str:
    payload=copy.deepcopy(obj);payload.pop("integrity_sha256",None)
    return sha256_bytes(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8"))


def _turn_session_checkpoint_id()->str:
    stamp=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"cp_{stamp}_{uuid.uuid4().hex[:12]}"


def _append_turn_session_journal(session_id:str,kind:str,payload:Optional[dict]=None,root:Path=ROOT)->dict:
    """Append a small non-authoritative event journal row without rehashing authority files."""
    if not isinstance(session_id,str) or not TURN_SESSION_ID_RE.fullmatch(session_id):raise EngineError("SESSION_ID_INVALID")
    p=root.resolve()/".runtime"/"turn_journals"/(session_id+".jsonl");p.parent.mkdir(parents=True,exist_ok=True)
    row={"format":"TURN_SESSION_JOURNAL_V1","session_id":session_id,"recorded_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"kind":str(kind)}
    if isinstance(payload,dict):row["payload"]=copy.deepcopy(payload)
    raw=(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n").encode("utf-8")
    with p.open("ab") as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    return {"path":str(p),"bytes_appended":len(raw)}


def _write_turn_recovery_checkpoint(session_id:str,stage:Path,meta:dict,reason:str,root:Path=ROOT)->dict:
    """Persist a recoverable Turn Session checkpoint at player-visible barriers/failures.

    Checkpoints are runtime infrastructure, not game authority and not SAVESETs.  They copy
    the exact five staged authority files plus the parent marker, bind every byte by SHA-256,
    and can recreate a lost/corrupted session staging tree while the same parent SAVESET is
    still current.
    """
    stage=Path(stage).resolve();root=root.resolve()
    _validated_turn_session_stage(meta,session_id,root,require_current_parent=True)
    cp_root=_turn_session_checkpoint_root(session_id,root);cp_root.mkdir(parents=True,exist_ok=True)
    cid=_turn_session_checkpoint_id();tmp=cp_root/("."+cid+".tmp");final=cp_root/cid
    tmp.mkdir(parents=False,exist_ok=False)
    try:
        for fn in AUTH_FILES:shutil.copy2(stage/fn,tmp/fn)
        shutil.copy2(stage/".PARENT.json",tmp/".PARENT.json")
        hashes={fn:sha256_file(tmp/fn) for fn in AUTH_FILES};parent_hash=sha256_file(tmp/".PARENT.json")
        st=read_json(tmp/"state.json")
        manifest={
            "format":TURN_RECOVERY_CHECKPOINT_FORMAT,"checkpoint_id":cid,"session_id":session_id,
            "parent_save_set_id":meta.get("parent_save_set_id"),"parent_marker_sha256":parent_hash,
            "authority_sha256":hashes,"game_time":st.get("game_time"),"requested_until":meta.get("requested_until"),
            "last_advanced_to":meta.get("last_advanced_to"),"session_status":meta.get("status"),"barrier":copy.deepcopy(meta.get("barrier")),
            "reason":str(reason),"created_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        manifest["integrity_sha256"]=_turn_session_checkpoint_integrity(manifest)
        _atomic_replace_bytes(tmp/"CHECKPOINT.json",(json.dumps(manifest,ensure_ascii=False,separators=(",",":"))+"\n").encode("utf-8"))
        os.replace(tmp,final)
    except Exception:
        try:writable_tree(tmp);shutil.rmtree(tmp,ignore_errors=True)
        except Exception:pass
        raise
    # Keep only a short local recovery chain; the newest checkpoint id is bound in session meta.
    cps=sorted([x for x in cp_root.iterdir() if x.is_dir() and x.name.startswith("cp_")],key=lambda x:x.name,reverse=True)
    for old in cps[3:]:
        try:writable_tree(old);shutil.rmtree(old,ignore_errors=True)
        except Exception:pass
    return {"format":TURN_RECOVERY_CHECKPOINT_FORMAT,"checkpoint_id":cid,"path":str(final),"game_time":manifest.get("game_time"),"reason":reason,"integrity_sha256":manifest["integrity_sha256"]}


def _read_turn_recovery_checkpoint(session_id:str,meta:dict,root:Path=ROOT)->Tuple[Path,dict]:
    cid=meta.get("recovery_checkpoint_id")
    if not isinstance(cid,str) or not re.fullmatch(r"cp_\d{8}T\d{12}Z_[0-9a-f]{12}",cid):raise EngineError("SESSION_RECOVERY_CHECKPOINT_MISSING")
    cp=_turn_session_checkpoint_root(session_id,root)/cid
    if not cp.is_dir() or cp.is_symlink():raise EngineError("SESSION_RECOVERY_CHECKPOINT_NOT_FOUND")
    mp=cp/"CHECKPOINT.json"
    try:m=strict_json_load(mp)
    except Exception as e:raise EngineError(f"SESSION_RECOVERY_CHECKPOINT_MANIFEST_INVALID:{e}")
    if not isinstance(m,dict) or m.get("format")!=TURN_RECOVERY_CHECKPOINT_FORMAT or m.get("session_id")!=session_id or m.get("checkpoint_id")!=cid:raise EngineError("SESSION_RECOVERY_CHECKPOINT_IDENTITY_INVALID")
    if m.get("parent_save_set_id")!=meta.get("parent_save_set_id"):raise EngineError("SESSION_RECOVERY_CHECKPOINT_PARENT_MISMATCH")
    if m.get("integrity_sha256")!=_turn_session_checkpoint_integrity(m):raise EngineError("SESSION_RECOVERY_CHECKPOINT_INTEGRITY_MISMATCH")
    hashes=m.get("authority_sha256") or {}
    if set(hashes)!=set(AUTH_FILES):raise EngineError("SESSION_RECOVERY_CHECKPOINT_FILESET_INVALID")
    for fn in AUTH_FILES:
        if not (cp/fn).is_file() or sha256_file(cp/fn)!=hashes.get(fn):raise EngineError(f"SESSION_RECOVERY_CHECKPOINT_HASH_MISMATCH:{fn}")
    if not (cp/".PARENT.json").is_file() or sha256_file(cp/".PARENT.json")!=m.get("parent_marker_sha256"):raise EngineError("SESSION_RECOVERY_CHECKPOINT_PARENT_MARKER_INVALID")
    return cp,m


def _update_turn_session_checkpoint_meta(session_id:str,meta:dict,stage:Path,reason:str,root:Path=ROOT)->dict:
    cp=_write_turn_recovery_checkpoint(session_id,stage,meta,reason,root)
    meta["recovery_checkpoint_id"]=cp["checkpoint_id"];meta["recovery_checkpoint_game_time"]=cp.get("game_time");meta["recovery_checkpoint_reason"]=reason
    _write_turn_session_meta(session_id,meta,root)
    return cp


def _remove_turn_session_runtime(session_id:str,root:Path=ROOT,remove_stage:Optional[Path]=None)->None:
    _turn_session_authority_invalidate(session_id)
    if remove_stage is not None:
        try:
            p=Path(remove_stage)
            if p.exists() and p.parent.resolve()==root.resolve() and p.name.startswith(f".stage_session_{session_id}_"):
                writable_tree(p);shutil.rmtree(p,ignore_errors=True)
        except Exception:pass
    try:_turn_session_meta_path(session_id,root).unlink(missing_ok=True)
    except Exception:pass
    for p in (root.resolve()/".runtime"/"recovery_checkpoints"/session_id, root.resolve()/".runtime"/"turn_journals"/(session_id+".jsonl")):
        try:
            if p.is_dir():writable_tree(p);shutil.rmtree(p,ignore_errors=True)
            else:p.unlink(missing_ok=True)
        except Exception:pass


def _next_autosave_version(root:Path=ROOT)->str:
    parent=latest_valid_snapshot(root,verify_parent=True);major,minor=parent["version"]
    return version_text((major,minor+1))


def _turn_session_autosave_scope(meta:dict)->str:
    return f"AUTOSAVE_POLICY_V1 Turn Session {meta.get('session_id')} through {meta.get('last_advanced_to') or meta.get('requested_until')}"


def _turn_session_commit_ready(session_id:str,meta:dict,stage:Path,version:Optional[str],scope:Optional[str],publish:bool=False)->dict:
    if meta.get("status") not in {"READY_TO_COMMIT","COMMIT_FAILED"}:raise EngineError("SESSION_NOT_READY_TO_COMMIT")
    ver=str(version or meta.get("autosave_version") or _next_autosave_version(ROOT));scp=str(scope or meta.get("autosave_scope") or _turn_session_autosave_scope(meta))
    meta["autosave_version"]=ver;meta["autosave_scope"]=scp;meta["autosave_policy"]=AUTOSAVE_POLICY_SCHEMA;_write_turn_session_meta(session_id,meta)
    state=read_json(stage/"state.json");tasks=read_json(stage/"tasks.json");at=str(state.get("game_time") or "")
    _sync_current_checkpoints(state,tasks,ver,at);_write_authority_json(stage/"state.json",state);_write_authority_json(stage/"tasks.json",tasks)
    if meta.get('commit_retry_count') and not meta.get('commit_retry_recorded'):
        _append_engine_history(stage/'events.jsonl',{'event_id':f'AUTO-COMMIT-RETRY-{session_id}','game_time':at,'type':'automation_commit_retry','summary':'确定性会话提交重试记录；业务效果只在成功提交后生效。','source':f'GAME ENGINE v{ENGINE_VERSION} session','authority_files':[],'changes':[],'execution_diagnostics':{'retry_count':meta['commit_retry_count'],'failure_reason':str(meta.get('commit_error') or '').split(':',1)[0],'engine_version':ENGINE_VERSION}})
        meta['commit_retry_recorded']=True;_write_turn_session_meta(session_id,meta)
    # atomic_save adds a transaction changeset to the stage. Retain the exact
    # precommit bytes so a failed attempt cannot append that changeset twice.
    _precommit=_update_turn_session_checkpoint_meta(session_id,meta,stage,"precommit",ROOT)
    try:
        res=atomic_save(stage,ver,scp,ROOT,False,publish)
    except Exception as e:
        # The failed transaction remains recoverable and may only be retried/aborted; advancing
        # farther on top of an uncommitted player-visible state is forbidden.
        meta["status"]="COMMIT_FAILED";meta["commit_failed_at_utc"]=dt.datetime.now(dt.timezone.utc).isoformat();meta["commit_error"]=f"{type(e).__name__}:{e}";meta['commit_retry_count']=int(meta.get('commit_retry_count') or 0)+1
        cp=None
        try:
            clean,_=_read_turn_recovery_checkpoint(session_id,meta,ROOT)
            for fn in AUTH_FILES:_atomic_replace_bytes(stage/fn,(clean/fn).read_bytes())
            _turn_session_authority_invalidate(session_id)
            cp=_update_turn_session_checkpoint_meta(session_id,meta,stage,"commit_failure",ROOT)
        except Exception as ce:
            meta["checkpoint_error"]=f"{type(ce).__name__}:{ce}";_write_turn_session_meta(session_id,meta)
        latest=None
        try:latest=latest_valid_snapshot(ROOT,verify_parent=True).get("save_set_id")
        except Exception:pass
        raise EngineError(f"GAME_STATE_COMMIT_FAILED:last_safe={latest}:checkpoint={(cp or {}).get('checkpoint_id')}:detail={e}")
    _remove_turn_session_runtime(session_id,ROOT,None);runtime_gc(ROOT,False)
    frame=reportframe_packet(ROOT,since=meta.get('started_game_time'),since_seq=meta.get('report_since_seq'))
    executed=[{'task_id':r.get('task_id'),'job_id':r.get('job_id'),'resolver':r.get('resolver'),'status':r.get('status','COMMITTED'),'scheduled_time':r.get('scheduled_time'),'elapsed_ms':r.get('elapsed_ms'),'rule_sha256':r.get('rule_sha256')} for r in (meta.get('execution_results') or []) if isinstance(r,dict) and (r.get('task_id') or r.get('job_id'))]
    return {"status":'PAUSED_COMMITTED' if (state.get('engine_runtime') or {}).get('pending_turn') else 'COMMITTED',"pending_turn":(state.get('engine_runtime') or {}).get('pending_turn'),"session_id":session_id,"save":res,"report_frame":frame,"deterministic_events_executed":executed,"unexecuted_reason":(meta.get('barrier') or {}).get('kind'),"autosave":True,"autosave_policy":AUTOSAVE_POLICY_SCHEMA,"player_visible_state":"COMMITTED"}


def _recoverable_turn_sessions(root:Path=ROOT,limit:int=8)->List[dict]:
    out=[];d=root.resolve()/".runtime"/"turn_sessions"
    if not d.is_dir():return out
    current_sid=None
    try:current_sid=latest_valid_snapshot(root,verify_parent=True).get("save_set_id")
    except Exception:pass
    for mp in sorted(d.glob("*.json"),key=lambda x:x.stat().st_mtime if x.exists() else 0,reverse=True):
        sid=mp.stem
        if not TURN_SESSION_ID_RE.fullmatch(sid):continue
        try:
            meta=_read_turn_session_meta(sid,root)
            if meta.get("parent_save_set_id")!=current_sid:continue
            stage_ok=False
            try:_validated_turn_session_stage(meta,sid,root,require_current_parent=True);stage_ok=True
            except Exception:pass
            cp_ok=False;cpid=meta.get("recovery_checkpoint_id")
            if cpid:
                try:_read_turn_recovery_checkpoint(sid,meta,root);cp_ok=True
                except Exception:pass
            if not stage_ok and not cp_ok:continue
            out.append({"session_id":sid,"status":meta.get("status"),"requested_until":meta.get("requested_until"),"last_advanced_to":meta.get("last_advanced_to"),"semantic_barrier":copy.deepcopy(meta.get("barrier")),"stage_available":stage_ok,"checkpoint_available":cp_ok,"checkpoint_id":cpid,"autosave_version":meta.get("autosave_version")})
            if len(out)>=max(1,int(limit)):break
        except Exception:continue
    return out


def turn_session(action:str,until:Optional[str]=None,session_id:Optional[str]=None,patch:Optional[Path]=None,version:Optional[str]=None,scope:Optional[str]=None,publish:bool=False)->dict:
    d=ROOT/".runtime"/"turn_sessions";d.mkdir(parents=True,exist_ok=True)
    if action=='resume':
        guard(ROOT,restore=True,restore_tool_files=False)
        pending=(read_json(ROOT/'state.json').get('engine_runtime') or {}).get('pending_turn')
        if not pending:raise EngineError('NO_PENDING_COMMITTED_TURN')
        return turn_session('start',until=pending['requested_until'],version=version,scope=scope,publish=publish)
    if action=="start":
        if not until:raise EngineError("SESSION_UNTIL_REQUIRED")
        guard(ROOT,restore=True,restore_tool_files=False)
        initial=read_json(ROOT/'state.json');pending=(initial.get('engine_runtime') or {}).get('pending_turn') or {}
        original=pending.get('started_at') or initial['game_time'];target=parse_iso(until)
        if target is None:raise EngineError('SESSION_TIME_INVALID')
        requested=target;target=_advance_cap(initial,target,original);until=target.isoformat()
        _,hist,_=read_history_view(ROOT/'events.jsonl');report_seq=pending.get('report_since_seq',max((int(e.get('seq') or 0) for e in hist),default=0))
        sid=uuid.uuid4().hex[:12];info=create_stage(ROOT,"session_"+sid);stage=Path(info["staging"]);marker=stage/".PARENT.json"
        meta={"format":TURN_SESSION_META_FORMAT,"session_id":sid,"staging":str(stage),"parent_save_set_id":info.get("parent"),"parent_marker_sha256":sha256_file(marker),"requested_until":until,"original_requested_until":requested.isoformat(),"started_game_time":original,"report_since_seq":report_seq,"created_at":dt.datetime.now(dt.timezone.utc).isoformat(),"status":"OPEN","autosave_policy":AUTOSAVE_POLICY_SCHEMA}
        _write_turn_session_meta(sid,meta);_append_turn_session_journal(sid,"session_started",{"requested_until":until,"parent_save_set_id":info.get("parent")})
        if pending and (pending.get('barrier') or {}).get('kind')=='scheduler_continuation':
            return turn_session('advance',session_id=sid,version=version,scope=scope,publish=publish)
        if pending and (pending.get('barrier') or {}).get('kind') in ('story_consequence_ai','story_consequence_authorization'):
            # The typed story command is committed independently while paused.
            # Rebuild from its new authoritative state, never replay the old plan
            # or require an unsafe raw patch to clear a resolved story barrier.
            return turn_session('advance',session_id=sid,version=version,scope=scope,publish=publish)
        if pending:
            meta.update({'status':'BARRIER','barrier':pending.get('barrier'),'requested_until':pending['requested_until']});_write_turn_session_meta(sid,meta)
            return {'status':'RESUMED_AWAITING_PATCH','session_id':sid,'staging':str(stage),'pending_turn':pending,'semantic_barrier':pending.get('barrier'),'next_action':'session apply --id <session_id> --patch <semantic_patch>; session advance --id <session_id>','player_visible_state':'COMMITTED'}
        return turn_session("advance",session_id=sid,version=version,scope=scope,publish=publish)
    if not session_id:raise EngineError("SESSION_ID_REQUIRED")
    mp=_turn_session_meta_path(session_id);meta=_read_turn_session_meta(session_id)

    if action=="status":
        stage=None;stage_ok=False;stale=False;stage_error=None;game_time=meta.get("last_advanced_to")
        try:
            stage=_validated_turn_session_stage(meta,session_id,ROOT,require_current_parent=True);stage_ok=True
            resident=_turn_session_authority_load(session_id,stage);game_time=resident["state"].get("game_time")
        except EngineError as exc:
            stage_error=str(exc);stale=stage_error.startswith("SESSION_STALE_PARENT")
        cp_ok=False;checkpoint_error=None
        if meta.get("recovery_checkpoint_id"):
            try:_read_turn_recovery_checkpoint(session_id,meta,ROOT);cp_ok=True
            except EngineError as exc:checkpoint_error=str(exc)
        return {"status":meta.get("status"),"session":meta,"game_time":game_time,"stale_parent":stale,"stage_available":stage_ok,"stage_error":stage_error,"checkpoint_available":cp_ok,"checkpoint_error":checkpoint_error,"player_visible_state":"COMMITTED" if meta.get("status")=="COMMITTED" else ("RECOVERABLE_CHECKPOINT" if cp_ok else "UNCOMMITTED_INTERNAL")}

    if action=="recover":
        latest=latest_valid_snapshot(ROOT,verify_parent=True)
        if latest.get("save_set_id")!=meta.get("parent_save_set_id"):raise EngineError("SESSION_STALE_PARENT: checkpoint cannot be applied to a newer authority")
        cp,cm=_read_turn_recovery_checkpoint(session_id,meta,ROOT)
        new_stage=ROOT/f".stage_session_{session_id}_recovered_{uuid.uuid4().hex[:8]}";new_stage.mkdir(parents=False,exist_ok=False)
        try:
            for fn in AUTH_FILES:shutil.copy2(cp/fn,new_stage/fn)
            shutil.copy2(cp/".PARENT.json",new_stage/".PARENT.json")
            meta["staging"]=str(new_stage);meta["parent_marker_sha256"]=sha256_file(new_stage/".PARENT.json");meta["status"]=cm.get("session_status") or "BARRIER";meta["recovered_at_utc"]=dt.datetime.now(dt.timezone.utc).isoformat();_write_turn_session_meta(session_id,meta)
            _validated_turn_session_stage(meta,session_id,ROOT,require_current_parent=True);_turn_session_authority_invalidate(session_id);_append_turn_session_journal(session_id,"checkpoint_recovered",{"checkpoint_id":cm.get("checkpoint_id"),"game_time":cm.get("game_time")})
            return {"status":"RECOVERED","session_id":session_id,"checkpoint_id":cm.get("checkpoint_id"),"game_time":cm.get("game_time"),"session_status":meta.get("status"),"staging":str(new_stage)}
        except Exception:
            try:writable_tree(new_stage);shutil.rmtree(new_stage,ignore_errors=True)
            except Exception:pass
            raise

    # All mutating actions below require a safe owned staging directory and current parent.
    stage=_validated_turn_session_stage(meta,session_id,ROOT,require_current_parent=True)
    if action=="apply":
        if patch is None:raise EngineError("SESSION_PATCH_REQUIRED")
        if meta.get("status")=="COMMIT_FAILED":raise EngineError("SESSION_COMMIT_FAILED_RETRY_OR_ABORT_REQUIRED")
        raw=strict_json_load(patch)
        economic_targets={e.get('target') for e in raw.get('economic_effects',[]) if isinstance(e,dict)}
        for op in raw.get('operations') or []:
            if not isinstance(op,dict) or op.get('op')=='history_append':continue
            head=str(op.get('file','')).replace('.json','');ref=head+':'+str(op.get('path','')).strip('/').replace('/','.')
            if head in ('state','tasks','rules','catalog','manifest','events.jsonl') and ref not in economic_targets:raise EngineError('SESSION_PROTECTED_WRITE_REQUIRES_TYPED_COMMAND')
        out=apply_patch(stage,patch);_turn_session_authority_invalidate(session_id)
        cp=_update_turn_session_checkpoint_meta(session_id,meta,stage,"semantic_patch",ROOT);_append_turn_session_journal(session_id,"semantic_patch_applied",{"checkpoint_id":cp.get("checkpoint_id"),"changed":out.get("changed"),"history_appended":out.get("history_appended")})
        return {"status":"SESSION_PATCHED","session_id":session_id,"apply":out,"recovery_checkpoint":cp,"player_visible_state":"RECOVERABLE_CHECKPOINT","autosave_policy":AUTOSAVE_POLICY_SCHEMA}
    if action=="abort":
        _append_turn_session_journal(session_id,"session_aborted",{"status":meta.get("status")});_remove_turn_session_runtime(session_id,ROOT,stage);runtime_gc(ROOT,False);return {"status":"ABORTED","session_id":session_id}
    if action=="advance":
        if meta.get("status")=="COMMIT_FAILED":raise EngineError("SESSION_COMMIT_FAILED_RETRY_OR_ABORT_REQUIRED")
        if meta.get("status")=="READY_TO_COMMIT":return _turn_session_commit_ready(session_id,meta,stage,version,scope,publish)
        target=parse_iso(meta.get("requested_until"));resident=_turn_session_authority_load(session_id,stage);state=resident["state"];tasks=resident["tasks"];world=resident["world"];rules=resident["rules"];now=parse_iso(state.get("game_time"))
        if not target or not now:raise EngineError("SESSION_TIME_INVALID")
        target=_advance_cap(state,target,meta.get('started_game_time'))
        if target<now:raise EngineError("SESSION_TARGET_BEFORE_STAGED_TIME")
        executed=[];cursor=now;barrier=None;advance_result=None
        _session_before={fn:(stage/fn).read_bytes() for fn in ("state.json","tasks.json","events.jsonl")};_session_meta_before=mp.read_bytes() if mp.is_file() else None
        history_batch=_history_append_batch(stage/"events.jsonl");history_batch.__enter__()
        try:
            seen_events=set()
            # Drain every node at the boundary, including simultaneous maintenance jobs.
            # A strict cursor < target silently left the second job at an exact target
            # timestamp behind; the next turn's old strict queue bound then lost it.
            while cursor<=target:
                ai=_next_ai_monitor_time(tasks,cursor,target,state)
                lh_all=preview_long_horizon(state,rules,target,max_events=_mechanical_multi_event_limit(rules))
                hzs=[e for e in (lh_all.get("events") or []) if e.get("requires_simulation",True) and parse_iso(e.get("time")) and cursor<parse_iso(e["time"])<=target]
                hz=min(hzs,key=lambda e:e["time"]) if hzs else None;cand=[]
                if hz:cand.append({"time":parse_iso(hz["time"]),"kind":"hazard","event":hz})
                if ai:cand.append(ai)
                barrier=min(cand,key=lambda x:(x["time"],x.get("kind") or "")) if cand else None;hard=barrier["time"] if barrier else target
                q=deterministic_event_queue(state,tasks,cursor,hard);ev=q[0] if q else None;et=parse_iso(ev["time"]) if ev else None
                if ev is not None and et is not None and _deterministic_event_precedes_barrier(ev,et,hard,barrier):
                    event_key=(ev.get('task_id'),ev.get('job_id'),ev.get('resolver'),ev.get('time'))
                    if event_key in seen_events:raise EngineError('DETERMINISTIC_SCHEDULER_NO_PROGRESS')
                    if len(seen_events)>=1024:
                        barrier={'time':cursor,'kind':'scheduler_continuation','event':{'next_task_id':ev.get('task_id'),'next_job_id':ev.get('job_id'),'next_resolver':ev.get('resolver')},'resolution_required':'session resume continues the remaining due nodes'}
                        break
                    seen_events.add(event_key)
                    _mh=_set_runtime_time(state,tasks,world,et,rules);executed.extend(_record_mechanical_hazards(stage,state,_mh));cursor=et
                    _resolver_started=time.perf_counter()
                    _rule_source=_task_by_id(tasks,ev['task_id']) if ev.get('task_id') else next((j for qname in ('repair_queue','medical_queue') for j in (_maintenance_runtime(state).get(qname) or []) if j.get('job_id')==ev.get('job_id')),None)
                    _rule_digest=sha256_bytes(json.dumps((_rule_source or {}).get('runtime_policy') or (_rule_source or {}).get('completion_actions') or {},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
                    row=_resolve_deterministic_event(stage,state,tasks,ev,et)
                    if isinstance(row,dict):
                        row.setdefault("scheduled_time",ev["time"]);row.setdefault("scheduled_resolver",ev["resolver"])
                        row['rule_sha256']=_rule_digest;row['elapsed_ms']=round((time.perf_counter()-_resolver_started)*1000,3);row['engine_version']=ENGINE_VERSION
                        if ev.get("task_id"):row.setdefault("source_task_id",ev.get("task_id"))
                        if ev.get("job_id"):row.setdefault("source_job_id",ev.get("job_id"))
                    executed.append(row)
                    if isinstance(row,dict):
                        receipt_id=f"AUTO-EXEC-{session_id}-{len(seen_events):04d}"
                        _append_engine_history(stage/'events.jsonl',{'event_id':receipt_id,'game_time':et.strftime('%Y-%m-%dT%H:%M:%S'),'type':'automation_execution_receipt','summary':'确定性任务执行记录；业务变化见关联事件。','source':f'GAME ENGINE v{ENGINE_VERSION} session','authority_files':[],'changes':[],'execution_diagnostics':{'task_id':ev.get('task_id'),'job_id':ev.get('job_id'),'resolver':ev.get('resolver'),'scheduled_time':ev.get('time'),'status':row.get('status','COMMITTED'),'elapsed_ms':row['elapsed_ms'],'rule_sha256':row['rule_sha256'],'engine_version':ENGINE_VERSION,'retry_count':int(meta.get('commit_retry_count') or 0),'failure_reason':(row.get('semantic_barrier') or {}).get('kind') if row.get('status')=='AI_REQUIRED' else None,'business_event_id':row.get('event_id')}})
                    _append_turn_session_journal(session_id,"deterministic_event",{"time":et.strftime("%Y-%m-%dT%H:%M:%S"),"resolver":ev.get("resolver"),"task_id":ev.get("task_id"),"job_id":ev.get("job_id"),"status":row.get("status") if isinstance(row,dict) else None,"event_id":row.get("event_id") if isinstance(row,dict) else None})
                    if isinstance(row,dict) and row.get("status")=="AI_REQUIRED":
                        sb=row.get("semantic_barrier") or {};barrier={"time":et,"kind":sb.get("kind") or "maintenance_authority_conflict","job_id":sb.get("job_id"),"event":sb};break
                    continue
                if barrier and barrier.get("kind") in TASK_AI_BARRIER_KINDS:
                    if hard>cursor:_mh=_set_runtime_time(state,tasks,world,hard,rules);executed.extend(_record_mechanical_hazards(stage,state,_mh));cursor=hard
                    break
                if barrier and barrier.get("kind")=="hazard":break
                if target>cursor:_mh=_set_runtime_time(state,tasks,world,target,rules);executed.extend(_record_mechanical_hazards(stage,state,_mh));cursor=target
                break
            final=cursor
            if not barrier and state.get('engine_runtime',{}).pop('pending_turn',None):
                _append_engine_history(stage/'events.jsonl',{'event_id':'TURN-RESUMED-'+session_id,'game_time':final.isoformat(),'type':'turn_completed','source':f'GAME ENGINE v{ENGINE_VERSION} session','summary':'待续指令已完成，清除恢复窗口。','changes':[{'target':'STATE.engine_runtime.pending_turn','action':'clear_completed_pending_turn'}],'authority_files':['state.json']})
            if _final_time_audit_required(now,final):
                at=final.strftime("%Y-%m-%dT%H:%M:%S")
                _append_engine_history(stage/"events.jsonl",{"event_id":f"SESSION-TIME-{session_id}-{final.strftime('%Y%m%d-%H%M%S')}","game_time":at,"type":"time_advance","summary":f"GAME ENGINE v{ENGINE_VERSION} Turn Session推进至{final.strftime('%Y-%m-%d %H:%M:%S')}；逐机械节点重规划且未跨越Hazard语义事件。","changes":_routine_time_changes(),"source":f"GAME ENGINE v{ENGINE_VERSION} turn_session","authority_files":["state.json","tasks.json"]})
            _write_authority_json(stage/"state.json",state);_write_authority_json(stage/"tasks.json",tasks);_turn_session_authority_refresh(session_id,stage,resident)
            bmeta=({"time":barrier["time"].strftime("%Y-%m-%dT%H:%M:%S"),"kind":barrier.get("kind"),"task_id":barrier.get("task_id"),"job_id":barrier.get("job_id"),"title":barrier.get("title"),"event":barrier.get("event"),"watch_condition":barrier.get("watch_condition"),"decision_gate":barrier.get("decision_gate"),"resolution_required":barrier.get("resolution_required")} if barrier else None)
            meta.update({"last_advanced_to":final.strftime("%Y-%m-%dT%H:%M:%S"),"barrier":bmeta,"status":"BARRIER" if barrier else "READY_TO_COMMIT","execution_results":executed,"replanning":"after_each_deterministic_resolver","autosave_policy":AUTOSAVE_POLICY_SCHEMA});_write_turn_session_meta(session_id,meta)
            advance_result={"status":meta["status"],"session_id":session_id,"processed_until":meta["last_advanced_to"],"semantic_barrier":meta["barrier"],"deterministic_events_executed":executed,"staging":str(stage),"replanning":"after_each_deterministic_resolver"}
        finally:
            exc=sys.exc_info();flush_error=None
            try:history_batch.__exit__(*exc)
            except Exception as _he:flush_error=_he
            if exc[0] is not None or flush_error is not None:
                for _fn,_raw in _session_before.items():
                    try:_atomic_replace_bytes(stage/_fn,_raw)
                    except Exception:pass
                if _session_meta_before is not None:
                    try:_atomic_replace_bytes(mp,_session_meta_before)
                    except Exception:pass
                _turn_session_authority_invalidate(session_id)
            if flush_error is not None:raise flush_error
        if advance_result is None:raise EngineError("SESSION_ADVANCE_NO_RESULT")
        if advance_result.get("status")=="BARRIER":
            cp=_update_turn_session_checkpoint_meta(session_id,meta,stage,"semantic_barrier",ROOT);_append_turn_session_journal(session_id,"semantic_barrier_checkpoint",{"checkpoint_id":cp.get("checkpoint_id"),"game_time":cp.get("game_time"),"barrier":meta.get("barrier")})
            advance_result.update({"recovery_checkpoint":cp,"player_visible_state":"RECOVERABLE_CHECKPOINT","autosave_policy":AUTOSAVE_POLICY_SCHEMA,"saved":False})
            return _session_persist_barrier(session_id,meta,stage,advance_result,version,scope,publish)
        # NO_UNSAVED_PLAYER_VISIBLE_STATE: a completed turn is never returned as merely READY.
        return _turn_session_commit_ready(session_id,meta,stage,version,scope,publish)
    if action=="commit":
        if meta.get("status") not in {"READY_TO_COMMIT","COMMIT_FAILED"}:raise EngineError("SESSION_NOT_READY_TO_COMMIT")
        return _turn_session_commit_ready(session_id,meta,stage,version,scope,publish)
    raise EngineError("SESSION_ACTION_INVALID")

def runtime_gc(root:Path=ROOT,dry_run:bool=False,aggressive:bool=False)->dict:
    """Conservative cleanup for non-authoritative runtime/development debris.

    Normal post-save cleanup uses a short grace window so a shell-redirection target
    that is still open cannot be unlinked underneath the caller. Explicit
    ``gc --aggressive`` uses a 60-second safety floor and is intended for end-of-audit
    cleanup. Committed SAVESETs, Project Source packages, authority files, backup ZIPs,
    and currently bound versioned tools are never selected.
    """
    removed=[];now=time.time();targets=[];protected_stages=set()
    session_dir=root/'.runtime'/'turn_sessions'
    if session_dir.is_dir():
        for meta_path in session_dir.glob('*.json'):
            try:
                meta=strict_json_load(meta_path)
                if meta.get('status') not in {'COMMITTED','ABORTED'} and meta.get('staging'):
                    protected_stages.add(str(Path(meta['staging']).resolve()))
            except Exception:pass
    scratch_age=60 if aggressive else 15*60
    stage_age=60 if aggressive else 60*60
    work_age=60 if aggressive else 60*60
    cache_age=60 if aggressive else 60*60
    def add(p:Path,age:float):
        try:
            if str(p.resolve()) in protected_stages:return
            if p.exists() and now-p.stat().st_mtime>age:targets.append(p)
        except Exception:pass
    for p in root.glob('.stage_*'): add(p,stage_age)
    for p in root.glob('.engine_upgrade_cold_*'): add(p,stage_age)
    for p in root.glob('.quarantine_*'): add(p,7*24*3600)
    work=root/'.runtime'/'work'
    if work.is_dir():
        for p in work.iterdir(): add(p,work_age)
    rtdir=root/'.runtime'
    if rtdir.is_dir():
        for p in rtdir.glob('engine_session_upgrade_*.json'): add(p,cache_age)
    # Finished/abandoned Turn Session metadata whose staging no longer exists.
    tsdir=root/'.runtime'/'turn_sessions'
    if tsdir.is_dir():
        for p in tsdir.glob('*.json'):
            try:
                obj=strict_json_load(p);sp=Path(str(obj.get('staging') or ''))
                if (not sp.exists()) and now-p.stat().st_mtime>stage_age:targets.append(p)
            except Exception:add(p,work_age)
    # Known development/audit scratch outputs that can pollute the mobile root.
    disposable_patterns=(
        'ack_*.json','review_ack_*.json','patch_*.json','process_*.json','turn_*.json',
        'final_check_*.json','final_*.json','postcommit_*.json','newchat_*.json','newchat_*.txt','newchat_*.out','newchat_*.err','newchat_*.log','report_*.json',
        'routineplan_*.json','sourcecheck_*.json','enginehealth_*.json','marketoffer_*.json',
        'combatcalc_*.json','battlecalc_*.json','battle_smoke*.json','battle_neg_*','battle_txn_*',
        'battle_stage*.json','battle_fixture_save*.json','transaction_*.json','txn_*.json',
        'v[0-9]*_check*.json','v[0-9]*_smoke*.json','v[0-9]*_*.json','v[0-9]*_*.txt','v[0-9]*_*.out','v[0-9]*_*.err','v[0-9]*_*.log',
        'compat_*.json','cold_*.json','cold_*.out','cold_*.err','perf_*.json','pre_*.json','post_v*.json',
        'rp_*.json','check_after_*.json','taskcompact_*.json','statearchive_*.json','statearch_*.json',
        '*_regression_tmp.json','candidate_check_*.json','candidate_engine_v*.py',
        'migrate_v*.py','migration_v*.py','tmp_engine_*.py','prepare_v*.py','trace_*.py','patch_*.py',
        '*.prof','old_routine.txt','new_routine.txt'
    )
    protected=set(AUTH_FILES+[f'GAME_ENGINE_v{ENGINE_VERSION}.py',f'SAVE_GUARD_v{BUNDLED_GUARD_VERSION}.py'])
    for pat in disposable_patterns:
        for p in root.glob(pat):
            if p.name not in protected:add(p,scratch_age)
    # Deduplicate, then remove only files/dirs explicitly selected above.
    seen=set();uniq=[]
    for p in targets:
        try:key=str(p.resolve())
        except Exception:key=str(p)
        if key in seen:continue
        seen.add(key);uniq.append(p)
    for p in uniq:
        rel=str(p.relative_to(root)) if p.is_relative_to(root) else str(p)
        removed.append(rel)
        if not dry_run:
            try:
                if p.is_dir():writable_tree(p);shutil.rmtree(p,ignore_errors=True)
                else:p.chmod(0o644);p.unlink(missing_ok=True)
            except Exception:pass
    mode="AGGRESSIVE_DRY_RUN" if dry_run and aggressive else ("DRY_RUN" if dry_run else ("AGGRESSIVE_CLEANED" if aggressive else "CLEANED"))
    return {"status":mode,"removed":removed,"count":len(removed),"aggressive":aggressive,"retention_seconds":{"scratch":scratch_age,"stage":stage_age,"work":work_age,"upgrade_cache":cache_age},"policy":"known runtime/staging/session/development scratch only; explicit aggressive cleanup has a 60-second safety floor; authority, committed SAVESET, Project Source and backup ZIP are never auto-deleted"}

