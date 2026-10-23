# === VOYAGER_DEV_MODULE: cli ===

# === VOYAGER NATIVE EIGHT-COMPONENT AUTHORITY LAYER V2 ===
COMPONENT_SET_SCHEMA='VOYAGER_COMPONENT_SET_V2'
COMPONENT_SET_SCHEMA_LEGACY='VOYAGER_COMPONENT_SET_V1'
COMPONENT_FILES=('manifest.json','rules.json','catalog.json','state.json','tasks.json','events.jsonl','engine.py','guard.py')
COMPONENT_DATA_FILES=('rules.json','catalog.json','state.json','tasks.json','events.jsonl')
_COMPONENT_TRANSPORT_ENV='VOYAGER_TRANSPORT_PATH'
_COMPONENT_DELIVERY_ROOT_ENV='VOYAGER_DELIVERY_ROOT'

def _component_cold_archives(manifest:dict)->dict:
    raw=manifest.get('cold_archives') or {}
    if not isinstance(raw,dict):return {}
    out={}
    for key,rec in raw.items():
        if not isinstance(rec,dict):continue
        rel=str(rec.get('path') or '').strip().replace('\\','/')
        if not rel or rel.startswith('/') or '..' in Path(rel).parts:continue
        out[rel]=rec
    return out

def _copy_declared_cold_archives(src:Path,dst:Path,manifest:Optional[dict]=None)->None:
    m=manifest or _component_manifest_read(src)
    for rel in _component_cold_archives(m):
        sp=Path(src)/rel;dp=Path(dst)/rel
        if not sp.is_file():raise EngineError('COLD_ARCHIVE_MISSING:'+rel)
        dp.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(sp,dp)


def _csha_bytes(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def _csha_file(p:Path)->str:
    return sha256_file(p)


def _csha_zip_member(z:zipfile.ZipFile,name:str)->str:
    h=hashlib.sha256()
    with z.open(name,'r') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def _component_manifest_read(root:Path=COMPONENT_ROOT)->dict:
    try:m=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    except Exception as ex:raise EngineError(f'COMPONENT_MANIFEST_PARSE:{type(ex).__name__}:{ex}')
    if not isinstance(m,dict) or m.get('schema') not in {COMPONENT_SET_SCHEMA,COMPONENT_SET_SCHEMA_LEGACY}:raise EngineError('COMPONENT_MANIFEST_SCHEMA_INVALID')
    return m


def _component_world_from_parts(rules:dict,catalog:dict)->str:
    seq=[]
    for row in rules.get('document_segments') or []:
        if isinstance(row,dict) and isinstance(row.get('markdown'),str):seq.append((int(row.get('order',0)),row['markdown']))
    for row in catalog.get('document_segments') or []:
        if isinstance(row,dict) and isinstance(row.get('markdown'),str):seq.append((int(row.get('order',0)),row['markdown']))
    rr=rules.get('runtime_rules');sc=catalog.get('static_catalog')
    if not isinstance(rr,dict) or not isinstance(sc,dict):raise EngineError('COMPONENT_RULE_OR_CATALOG_MACHINE_BLOCK_INVALID')
    seq.append((int(rules.get('runtime_rules_order',10**9)),'<!-- '+RUNTIME_RULES_MARKER+'\n'+json.dumps(rr,ensure_ascii=False,separators=(',',':'))+'\n'+RUNTIME_RULES_MARKER+'_END -->'))
    seq.append((int(catalog.get('static_catalog_order',10**9+1)),'<!-- '+STATIC_CATALOG_MARKER+'\n'+json.dumps(sc,ensure_ascii=False,separators=(',',':'))+'\n'+STATIC_CATALOG_MARKER+'_END -->'))
    return ''.join(x[1] for x in sorted(seq,key=lambda z:z[0]))


def _authority_world_text(base:Path=ROOT)->str:
    rules=read_json(Path(base)/'rules.json');catalog=read_json(Path(base)/'catalog.json')
    return _component_world_from_parts(rules,catalog)


def _authority_world_sha256(base:Path=ROOT)->str:
    return _csha_bytes(_authority_world_text(base).encode('utf-8'))


def _manifest_protocol_text(base:Path=ROOT)->str:
    m=_component_manifest_read(Path(base));r=read_json(Path(base)/'rules.json')
    return '\n'.join([
        f'# 远航者舰队 {m.get("save_version")} — manifest projection',
        f'> **当前存档版本**：{m.get("save_version")}',
        f'> **INDEX运行协议修订号**：MOBILE-EIGHT-COMPONENT-V2',
        f'> **WORLD设定修订号**：{r.get("source_world_revision") or "unknown"}',
        f'- `game_engine_version`：`{m.get("engine_version")}`',
        f'- `game_engine_sha256`：`{((m.get("tool_bindings") or {}).get("engine.py") or (m.get("components") or {}).get("engine.py") or "")}`',
        f'- `save_guard_sha256`：`{((m.get("tool_bindings") or {}).get("guard.py") or (m.get("components") or {}).get("guard.py") or "")}`',
        f'- `parent_save_set_id`：`{m.get("parent_save_set_id") or ""}`',
        f'- `save_set_id`：`{m.get("save_set_id") or ""}`',
        '- `source_file_count`：`8`',
        '来源权威直接为manifest/rules/catalog/state/tasks/events/engine/guard；不生成旧五文件兼容视图。',
    ])+'\n'


def current_index_version(base:Path)->Optional[str]:
    try:return str(_component_manifest_read(base).get('save_version') or '') or None
    except Exception:return None


def _component_data_hashes(root:Path)->dict:
    return {fn:_csha_file(root/fn) for fn in COMPONENT_DATA_FILES}


def _component_tool_hashes(root:Path)->dict:
    return {fn:_csha_file(root/fn) for fn in ('engine.py','guard.py')}


def _component_bundle_hash(hashes:dict)->str:
    return _csha_bytes(''.join(f'{k}\t{hashes[k]}\n' for k in sorted(hashes)).encode('utf-8'))


def _v130_layer__component_write_manifest_native_01(root:Path,save_version:str,parent_sid:Optional[str],migration_lineage:Optional[dict]=None)->dict:
    for fn in COMPONENT_DATA_FILES+('engine.py','guard.py'):
        if not (root/fn).is_file():raise EngineError('COMPONENT_MISSING_FOR_MANIFEST:'+fn)
    st=read_json(root/'state.json');gt=st.get('game_time')
    data_hashes=_component_data_hashes(root);tools=_component_tool_hashes(root)
    authority_bundle=_component_bundle_hash(data_hashes)
    sid=f'SAVESET-{save_version}-{authority_bundle[:16]}'
    all_hashes={**data_hashes,**tools};transport_bundle=_component_bundle_hash(all_hashes);cset='COMPSET-'+transport_bundle[:24]
    old={}
    try:old=_component_manifest_read(root)
    except Exception:pass
    m={
      'schema':COMPONENT_SET_SCHEMA,'format_version':2,'save_version':save_version,'save_set_id':sid,
      'parent_save_set_id':parent_sid,'authority_bundle_sha256':authority_bundle,'component_set_id':cset,
      'component_bundle_sha256':transport_bundle,'game_time':gt,'engine_version':ENGINE_VERSION,'engine_protocol':ENGINE_PROTOCOL,
      'guard_version':BUNDLED_GUARD_VERSION,'guard_protocol':GUARD_PROTOCOL,'entrypoint':'guard.py','engine_entrypoint':'engine.py',
      'components':all_hashes,'authority_components':data_hashes,'tool_bindings':tools,
      'component_roles':{
        'rules.json':'current rules, conditions, formulas, priorities and rule registry',
        'catalog.json':'stable equipment, ship, location and organization templates and catalog registry',
        'state.json':'current facts and deterministic runtime state',
        'tasks.json':'tasks, triggers, authorization and pending decisions',
        'events.jsonl':'append-only events, exact changes and narrative history',
        'engine.py':'deterministic execution, query, validation and transaction engine',
        'guard.py':'source validation, recovery and boot launcher'},
      'runtime':{'native_eight_component':True,'migration_parser':'explicit_legacy_migration_only'},
      'migration_lineage':migration_lineage or old.get('migration_lineage') or {'from_save_set_id':old.get('save_set_id'),'from_layout':'eight_component_v1_with_runtime_projection','to_layout':'native_eight_component_v2'}
    }
    (root/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8',newline='\n')
    return m


def _v130_layer_component_source_check_01(root:Path=COMPONENT_ROOT,strict_fileset:bool=True)->dict:
    errors=[]
    try:m=_component_manifest_read(root)
    except Exception as ex:return {'status':'FAIL','schema':COMPONENT_SET_SCHEMA,'errors':[str(ex)]}
    comps=m.get('components') or {};expected=set(COMPONENT_FILES)
    for fn in COMPONENT_FILES:
        p=root/fn
        if not p.is_file():errors.append('MISSING:'+fn);continue
        if fn!='manifest.json' and comps.get(fn)!=_csha_file(p):errors.append('HASH_MISMATCH:'+fn)
    if m.get('schema')==COMPONENT_SET_SCHEMA:
        try:
            dh=_component_data_hashes(root);th=_component_tool_hashes(root)
            if m.get('authority_components')!=dh:errors.append('AUTHORITY_HASH_SET_MISMATCH')
            if m.get('tool_bindings')!=th:errors.append('TOOL_BINDING_MISMATCH')
            ab=_component_bundle_hash(dh);tb=_component_bundle_hash({**dh,**th})
            if m.get('authority_bundle_sha256')!=ab:errors.append('AUTHORITY_BUNDLE_MISMATCH')
            if m.get('component_bundle_sha256')!=tb:errors.append('COMPONENT_BUNDLE_MISMATCH')
            sid=f'SAVESET-{m.get("save_version")}-{ab[:16]}'
            if m.get('save_set_id')!=sid:errors.append('SAVESET_ID_MISMATCH')
            if 'legacy_runtime_view' in (m.get('runtime') or {}):errors.append('LEGACY_RUNTIME_VIEW_FLAG_FORBIDDEN')
            if 'legacy_compat' in json.dumps(m,ensure_ascii=False):errors.append('LEGACY_COMPAT_CURRENT_FLAG_FORBIDDEN')
        except Exception as ex:errors.append('V2_BINDING:'+str(ex))
    if strict_fileset:
        actual={p.name for p in root.iterdir() if p.is_file() and not p.name.startswith('VOYAGER_SOURCE_') and not p.name.startswith('.')}
        extra=sorted(actual-expected);missing=sorted(expected-actual)
        if extra:errors.append('UNEXPECTED_TOPLEVEL:'+','.join(extra))
        if missing:errors.append('MISSING_TOPLEVEL:'+','.join(missing))
    if (root/'.runtime'/'legacy_compat').exists():errors.append('LEGACY_COMPAT_DIRECTORY_PRESENT')
    try:
        _stage2_validate_tool_compile((root/'engine.py').read_bytes(),str(root/'engine.py'));_stage2_validate_tool_compile((root/'guard.py').read_bytes(),str(root/'guard.py'))
    except Exception as ex:errors.append('TOOL_COMPILE:'+str(ex))
    return {'status':'FAIL' if errors else 'PASS','schema':m.get('schema'),'save_set_id':m.get('save_set_id'),'save_version':m.get('save_version'),'component_set_id':m.get('component_set_id'),'component_count':8,'errors':errors}


def _v1403_previous_validate_authority_set(base:Path)->Optional[dict]:
    try:
        chk=component_source_check(base,strict_fileset=False)
        if chk.get('status')!='PASS':return None
        m=_component_manifest_read(base);sv=str(m.get('save_version'));ver=parse_version(sv)
        idx={'version':ver,'save_set_id':m.get('save_set_id'),'parent_save_set_id':m.get('parent_save_set_id'),'engine_version':m.get('engine_version'),'engine_sha256':((m.get('tool_bindings') or {}).get('engine.py')),'save_guard_sha256':((m.get('tool_bindings') or {}).get('guard.py')),'hashes':m.get('authority_components') or {},'bundle':m.get('authority_bundle_sha256') or m.get('component_bundle_sha256')}
        return {'base':Path(base),'version':ver,'bundle':idx['bundle'],'save_set_id':m.get('save_set_id'),'manifest':m.get('authority_components') or {},'index':idx,'index_sha256':_csha_file(Path(base)/'manifest.json'),'component_manifest':m}
    except Exception:return None


def ensure_source_ready(base:Path,allow_cache:bool=True)->dict:
    if _active_runtime_journal(Path(base),'consistency_repair_journal.json'):raise EngineError('CONSISTENCY_REPAIR_RECOVERY_REQUIRED_RUN_GUARD')
    a=validate_authority_set(Path(base))
    if not a:raise EngineError('COMPONENT_AUTHORITY_INVALID')
    return a
























def guard(root:Path=ROOT,restore:bool=True,restore_tool_files:bool=True)->dict:
    root=Path(root).resolve()
    with engine_lock(root,exclusive=True):
        chk=component_source_check(root,strict_fileset=False);recovery=None
        if (chk.get('status')!='PASS' or _native_commit_journal_path(root).exists()) and restore:
            recovery=_native_recover_interrupted_commit(root)
            chk=component_source_check(root,strict_fileset=False)
        if chk.get('status')!='PASS':raise EngineError('COMPONENT_GUARD_FAILED:'+','.join(chk.get('errors') or []))
        a=validate_authority_set(root)
        return {'status':'PASS','mode':'NATIVE_EIGHT_COMPONENT','engine_version':ENGINE_VERSION,'save_set_id':a.get('save_set_id'),'version':version_text(a.get('version')),'restored':bool(recovery),'recovery':recovery,'sourcecheck':chk}


def _v130_layer_latest_valid_snapshot_02(root:Path=ROOT,verify_parent:bool=True)->dict:
    a=validate_authority_set(Path(root))
    if not a:raise EngineError('NO_COMMITTED_COMPONENT_AUTHORITY')
    return {'dir':Path(root),'version':a['version'],'save_set_id':a['save_set_id'],'bundle':a['bundle'],'manifest':a['manifest'],'index':a['index'],'commit':{'parent_save_set_id':a['index'].get('parent_save_set_id'),'save_set_id':a['save_set_id']}}


def _native_snapshot_dir(root:Path,sid:str)->Path:
    return root/'.runtime'/'snapshots'/sid.replace('/','_')


def _v130_layer_create_stage_02(root:Path=ROOT,label:str='work')->dict:
    root=Path(root).resolve();ensure_source_ready(root,allow_cache=False)
    d=root/'.runtime'/'staging';d.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix=f'{label}_',dir=d))
    for fn in COMPONENT_FILES:shutil.copy2(root/fn,stage/fn)
    return {'status':'READY','staging':str(stage),'base_save_set_id':_component_manifest_read(root).get('save_set_id'),'native_components':True}


def _native_update_version_fields(stage:Path,version:str)->None:
    st=read_json(stage/'state.json');tk=read_json(stage/'tasks.json');rr=read_json(stage/'rules.json');cc=read_json(stage/'catalog.json')
    gt=st.get('game_time');tk['game_time']=gt
    for d in (st,tk,rr,cc):
        d.pop('save_version',None)
        d.setdefault('manifest_ref',{'component':'manifest.json','fields':['save_version','save_set_id']})
    _write_authority_json(stage/'state.json',st);_write_authority_json(stage/'tasks.json',tk);_write_authority_json(stage/'rules.json',rr);_write_authority_json(stage/'catalog.json',cc)
    meta,events,_=read_history_view(stage/'events.jsonl');physical=_history_physical_nonmeta_lines(stage/'events.jsonl');meta.pop('save_version',None);meta.setdefault('manifest_ref',{'component':'manifest.json','fields':['save_version','save_set_id']});meta['game_time_current']=gt;meta['next_seq']=_history_expected_next_seq(events)
    first=json.dumps(meta,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    _atomic_replace_bytes(stage/'events.jsonl',_history_replace_metadata_bytes((stage/'events.jsonl').read_bytes(),meta))


def atomic_save(staging:Path,version:str,scope:str,root:Path=ROOT,make_export:bool=False,make_project:bool=False,**kwargs)->dict:
    root=Path(root).resolve()
    with engine_lock(root,exclusive=True):
        try:
            result=_native_atomic_save_unlocked(staging,version,scope,root,False,False,**kwargs)
        except Exception as ex:
            # A failure after the manifest commit point must never invite replay.
            current=component_source_check(root,strict_fileset=False)
            stage_manifest=Path(staging)/'manifest.json'
            try:target=strict_json_load(stage_manifest).get('save_set_id')
            except Exception:target=None
            if (target and current.get('status')=='PASS' and
                    current.get('save_set_id')==target and current.get('save_version')==version):
                result={'status':'COMMITTED','committed':True,'save_set_id':current.get('save_set_id'),
                        'export_status':'NOT_REQUESTED','retry_action':'export_only' if (make_export or make_project) else None}
                try:writable_tree(staging);shutil.rmtree(staging,ignore_errors=True)
                except OSError:pass
            elif current.get('status')=='PASS':
                raise TransactionNotCommitted(current.get('save_set_id'),ex) from ex
            else:raise
    result.update(committed=True,export_status='NOT_REQUESTED',package_generated=False,
                  package_verified=False,external_persistence_confirmed=False,retry_action=None)
    if make_export or make_project:
        result['export']=export_save_set(root,result['save_set_id'])
        result['export_status']=result['export']['export_status']
        result['package_generated']=result['export']['package_generated']
        result['package_verified']=result['export']['package_verified']
        result['retry_action']=result['export'].get('retry_action')
    return result


def _v1403_previous__native_atomic_save_unlocked(staging:Path,version:str,scope:str,root:Path=ROOT,make_export:bool=False,make_project:bool=False,**kwargs)->dict:
    root=Path(root).resolve();staging=Path(staging).resolve();cur=ensure_source_ready(root,allow_cache=False);oldv=cur['version'];newv=parse_version(version)
    _native_validate_stage_parent(staging,root,cur)
    if newv<=oldv:raise EngineError(f'SAVE_VERSION_NOT_INCREMENTED:{version}<={version_text(oldv)}')
    parent_sid=cur['save_set_id']
    _native_update_version_fields(staging,version)
    _sync_current_scaling_status(staging)
    _ensure_transaction_changeset(root,staging,scope)
    # Tools are always bound from the active source root for normal state commits.
    for fn in ('engine.py','guard.py'):
        if (root/fn).resolve()!=(staging/fn).resolve():shutil.copy2(root/fn,staging/fn)
    m=_component_write_manifest_native(staging,version,parent_sid)
    cc=_current_authority_consistency_report(staging)
    if cc.get('status')!='PASS':raise EngineError('PRECOMMIT_CURRENT_CONSISTENCY:'+json.dumps(cc.get('errors') or [],ensure_ascii=False))
    chk=component_source_check(staging,strict_fileset=True)
    if chk.get('status')!='PASS':raise EngineError('STAGING_COMPONENT_INVALID:'+','.join(chk.get('errors') or []))
    # Domain/full consistency validation uses native helpers and no materialized legacy files.
    vr=run_checks(staging,full=True,expected_version=version,require_manifest=True,parent_snapshot={'dir':root,'save_set_id':parent_sid,'version':oldv})
    if vr.get('errors'):raise EngineError('GAME_STATE_COMMIT_FAILED:'+json.dumps(vr.get('errors')[:12],ensure_ascii=False))
    old_archives=_component_cold_archives(cur.get('component_manifest') or _component_manifest_read(root))
    for rel,row in _component_cold_archives(m).items():
        if rel in old_archives:continue
        source=staging/rel;dest=root/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        if not source.is_file() or sha256_file(source)!=row.get('file_sha256'):raise EngineError('NEW_COLD_ARCHIVE_INVALID:'+rel)
        if dest.is_file():
            if sha256_file(dest)!=row.get('file_sha256'):raise EngineError('NEW_COLD_ARCHIVE_COLLISION:'+rel)
        else:_native_durable_copy(source,dest)
    snap=_native_snapshot_parent(root,cur)
    journal=_native_commit_journal_path(root)
    _native_make_commit_journal(root,staging,cur,m,snap)
    _native_test_failpoint('after_journal')
    try:
        # Data and tools are activated first; manifest remains the commit point.  The
        # durable journal lets Guard restore the parent after power loss at any step.
        for fn in COMPONENT_FILES:
            if fn=='manifest.json':continue
            _native_durable_copy(staging/fn,root/fn)
            if fn=='state.json':_native_test_failpoint('after_component')
        _native_durable_copy(staging/'manifest.json',root/'manifest.json')
        _native_test_failpoint('after_manifest')
        post=component_source_check(root,strict_fileset=False)
        if post.get('status')!='PASS':raise EngineError('POST_COMMIT_COMPONENT_INVALID:'+','.join(post.get('errors') or []))
    except BaseException:
        _native_recover_interrupted_commit(root)
        raise
    _native_atomic_json(journal.parent/'transactions'/strict_json_load(journal)['transaction_id']/'commit_receipt.json',{'status':'COMMITTED','save_set_id':m['save_set_id']})
    _native_test_failpoint('after_receipt')
    _native_clear_journal(journal)
    _native_test_failpoint('after_cleanup')
    out={'status':'COMMITTED','version':version,'save_set_id':m.get('save_set_id'),'parent_save_set_id':parent_sid,'engine_version':ENGINE_VERSION,'bundle_sha256':m.get('authority_bundle_sha256'),'component_set_id':m.get('component_set_id'),'game_time':m.get('game_time'),'snapshot_dir':str(snap),'warnings':vr.get('warnings') or [],'native_eight_component':True}
    try:writable_tree(staging);shutil.rmtree(staging,ignore_errors=True)
    except Exception:pass
    return out


def _development_source_files(manifest:dict)->dict:
    rec=manifest.get('development_sources') or {}
    if not rec:return {}
    files=rec.get('files')
    if rec.get('schema')!='VOYAGER_DEV_SOURCES_V1' or not isinstance(files,dict) or not files:raise EngineError('DEVELOPMENT_SOURCES_SCHEMA')
    for name,digest in files.items():
        if not isinstance(name,str) or not name.startswith('development/') or name.endswith('/') or '..' in Path(name).parts or not re.fullmatch(r'[0-9a-f]{64}',str(digest)):
            raise EngineError('DEVELOPMENT_SOURCE_ENTRY_INVALID')
    return files

def _component_zip_check(path:Path)->dict:
    p=Path(path).resolve();errors=[];m=None
    try:
        with zipfile.ZipFile(p,'r') as z:
            names=z.namelist()
            if len(names)!=len(set(names)) or 'manifest.json' not in names:return {'status':'FAIL','path':str(p),'manifest':None,'errors':['SOURCE_ZIP_FILESET']}
            m=json.loads(z.read('manifest.json').decode('utf-8'));archives=_component_cold_archives(m);dev=_development_source_files(m);expected=set(COMPONENT_FILES)|set(archives)|set(dev)
            if set(names)!=expected:errors.append('SOURCE_ZIP_FILESET')
            if m.get('schema') not in {COMPONENT_SET_SCHEMA,COMPONENT_SET_SCHEMA_LEGACY}:errors.append('SOURCE_ZIP_SCHEMA')
            if not errors:
                actual={n:_csha_bytes(z.read(n)) for n in COMPONENT_FILES if n!='manifest.json'}
                declared=m.get('components') or {}
                if declared!=actual:errors.append('SOURCE_ZIP_COMPONENT_HASHES')
                for rel,archive_rec in archives.items():
                    expected_hash=str(archive_rec.get('file_sha256') or '')
                    if not expected_hash or _csha_zip_member(z,rel)!=expected_hash:errors.append('SOURCE_ZIP_COLD_ARCHIVE_HASH:'+rel)
                for rel,digest in dev.items():
                    if _csha_zip_member(z,rel)!=digest:errors.append('SOURCE_ZIP_DEVELOPMENT_HASH:'+rel)
                data={n:actual[n] for n in COMPONENT_DATA_FILES};tools={n:actual[n] for n in ('engine.py','guard.py')}
                if m.get('authority_components')!=data or m.get('tool_bindings')!=tools:errors.append('SOURCE_ZIP_BINDINGS')
                if m.get('authority_bundle_sha256')!=_component_bundle_hash(data) or m.get('component_bundle_sha256')!=_component_bundle_hash(actual):errors.append('SOURCE_ZIP_BUNDLE')
                sv=str(m.get('save_version') or '');expected_sid=f'SAVESET-{sv}-{_component_bundle_hash(data)[:16]}'
                if m.get('save_set_id')!=expected_sid:errors.append('SOURCE_ZIP_SAVESET_ID')
    except Exception as ex:errors.append(f'{type(ex).__name__}:{ex}')
    return {'status':'FAIL' if errors else 'PASS','path':str(p),'manifest':m,'errors':errors}

def _v1403_previous__component_transport_sync_status(current_save_set_id:Optional[str],component_root:Optional[Path]=None,honor_transport_env:bool=True)->dict:
    root=Path(component_root or COMPONENT_ROOT).resolve();raw=os.environ.get(_COMPONENT_TRANSPORT_ENV) if honor_transport_env else None
    explicit=Path(raw).resolve() if raw else None
    if explicit is not None:
        candidates=[explicit] if explicit.is_file() else []
    else:
        candidates=sorted(root.parent.glob('VOYAGER_SOURCE_V*.zip'),key=lambda x:x.stat().st_mtime,reverse=True)
    if not candidates:return {'status':'PROJECT_SOURCE_NOT_OBSERVED','current_save_set_id':current_save_set_id,'verified':False}
    peek=[]
    for p in candidates:
        try:
            with zipfile.ZipFile(p,'r') as z:m=json.loads(z.read('manifest.json').decode('utf-8'))
            peek.append((p,m))
        except Exception:continue
    ordered=[x for x in peek if x[1].get('save_set_id')==current_save_set_id]+[x for x in peek if x[1].get('save_set_id')!=current_save_set_id]
    invalid=[]
    for p,m0 in ordered:
        chk=_component_zip_check(p)
        if chk.get('status')!='PASS':invalid.append({'transport_file':p.name,'errors':chk.get('errors')});continue
        m=chk.get('manifest') or m0;sid=m.get('save_set_id');same=(sid==current_save_set_id)
        return {'status':'VERIFIED_PROJECT_SOURCE' if same else 'STALE_PROJECT_SOURCE','current_save_set_id':current_save_set_id,'source_save_set_id':sid,'parent_save_set_id':m.get('parent_save_set_id'),'verified':same,'transport_file':p.name,'component_set_id':m.get('component_set_id')}
    return {'status':'PROJECT_SOURCE_INVALID','current_save_set_id':current_save_set_id,'verified':False,'invalid_candidates':invalid}


def _native_project_source_dir_check(source_dir:Path,expected_save_set_id:Optional[str]=None)->dict:
    base=Path(source_dir).resolve()
    if (base/'manifest.json').is_file():
        out=component_source_check(base,strict_fileset=True);out['mode']='native_component_directory';return out
    cands=sorted((p for p in base.glob('VOYAGER_SOURCE_V*.zip') if p.is_file()),key=lambda x:x.stat().st_mtime,reverse=True)
    if not cands:return {'status':'FAIL','mode':'native_component_transport','base':str(base),'errors':['SOURCE_ZIP_NONE_FOUND']}
    rows=[]
    for p in cands:
        try:
            with zipfile.ZipFile(p,'r') as z:m=json.loads(z.read('manifest.json').decode('utf-8'))
            sv=str(m.get('save_version') or '');vm=re.fullmatch(r'V(\d+)\.(\d+)',sv);ver=(int(vm.group(1)),int(vm.group(2))) if vm else (-1,-1)
            rows.append({'path':p,'manifest':m,'version':ver})
        except Exception:continue
    if expected_save_set_id:
        rows=[r for r in rows if r['manifest'].get('save_set_id')==expected_save_set_id]
        if not rows:return {'status':'FAIL','mode':'native_component_transport','base':str(base),'errors':['SOURCE_SAVESET_NOT_FOUND:'+str(expected_save_set_id)]}
    elif rows:
        high=max(r['version'] for r in rows);rows=[r for r in rows if r['version']==high]
        sids={str(r['manifest'].get('save_set_id') or '') for r in rows}
        if len(sids)>1:return {'status':'FAIL','mode':'native_component_transport','base':str(base),'errors':['SOURCE_ZIP_FORK:'+','.join(sorted(sids))]}
    selected=None;zip_errors=[]
    for r in rows:
        chk=_component_zip_check(r['path'])
        if chk.get('status')=='PASS':selected=(r,chk);break
        zip_errors.extend(chk.get('errors') or [])
    if selected is None:return {'status':'FAIL','mode':'native_component_transport','base':str(base),'errors':['SOURCE_ZIP_INVALID']+zip_errors}
    r,chk=selected;m=chk.get('manifest') or {};gh=((m.get('tool_bindings') or {}).get('guard.py') or (m.get('components') or {}).get('guard.py'))
    guards=[]
    for gp in list(base.glob('guard*.py'))+list(base.glob('SAVE_GUARD*.py')):
        try:
            if gp.is_file() and _csha_file(gp)==gh:guards.append(gp.name)
        except Exception:pass
    errors=[]
    if not guards:errors.append('EXTERNAL_GUARD_HASH_MATCH_NOT_FOUND')
    return {'status':'FAIL' if errors else 'PASS','mode':'native_component_transport','base':str(base),'save_set_id':m.get('save_set_id'),'save_version':m.get('save_version'),'transport_file':r['path'].name,'external_guard_matches':sorted(set(guards)),'zip_check':{'status':chk.get('status'),'errors':chk.get('errors')},'errors':errors}


_legacy_source_transport_sync_status=_v130_layer__source_transport_sync_status_01
def _source_transport_sync_status(base:Path,current_save_set_id:Optional[str])->dict:
    if COMPONENT_MODE:return _component_transport_sync_status(current_save_set_id,Path(base))
    return _legacy_source_transport_sync_status(base,current_save_set_id)


def _component_package(root:Path=COMPONENT_ROOT,delivery_root:Optional[Path]=None)->dict:
    chk=_native_historical_source_check(root,COMPONENT_ROOT/'guard.py')
    if chk.get('status')!='PASS':raise EngineError('COMPONENT_SOURCECHECK_FAILED:'+','.join(chk.get('errors') or []))
    m=_component_manifest_read(root);archives=_component_cold_archives(m);dev=_development_source_files(m);delivery=Path(delivery_root or os.environ.get(_COMPONENT_DELIVERY_ROOT_ENV,str(root.parent))).resolve();delivery.mkdir(parents=True,exist_ok=True)
    tag=str(m.get('component_bundle_sha256') or '')[:16];name=f"VOYAGER_SOURCE_{m.get('save_version')}_{tag}.zip";out=delivery/name;tmp=delivery/('.'+name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for fn in COMPONENT_FILES:z.write(root/fn,fn)
            for rel in sorted(archives):
                fp=root/rel
                if not fp.is_file():raise EngineError('COLD_ARCHIVE_MISSING:'+rel)
                z.write(fp,rel)
            devroots=[root,Path(os.environ['VOYAGER_DEV_SOURCE_DIR']).resolve() if os.environ.get('VOYAGER_DEV_SOURCE_DIR') else None,COMPONENT_ROOT]
            for rel,digest in sorted(dev.items()):
                fp=next((d/rel for d in devroots if d is not None and (d/rel).is_file() and not (d/rel).is_symlink() and sha256_file(d/rel)==digest),None)
                if fp is None or fp.is_symlink() or sha256_file(fp)!=digest:raise EngineError('DEVELOPMENT_SOURCE_MISSING_OR_CHANGED:'+rel)
                z.write(fp,rel)
        with tmp.open('rb') as stream:os.fsync(stream.fileno())
        if _component_zip_check(tmp).get('status')!='PASS':raise EngineError('EXPORT_TEMP_ZIP_INVALID')
        os.replace(tmp,out);_native_sync_dir(delivery)
    finally:tmp.unlink(missing_ok=True)
    return {'status':'READY','format':'VOYAGER_COMPONENT_SOURCE_ZIP_V2','save_set_id':m.get('save_set_id'),'save_version':m.get('save_version'),'component_set_id':m.get('component_set_id'),'path':str(out),'sha256':_csha_file(out),'sourcecheck':chk,'members':list(COMPONENT_FILES)+sorted(archives)+sorted(dev)}

def build_project_source_package(snap:dict,root:Path)->dict:
    if COMPONENT_MODE:return _component_package(COMPONENT_ROOT)
    return _legacy_build_project_source_package(snap,root) if '_legacy_build_project_source_package' in globals() else {}


def _v130_layer__component_post_command_sync_01(cmd:str,result:Any)->Any:
    # Native commands already commit directly to components. No post-hoc legacy synchronization exists.
    return result


def _v130_layer_native_component_selftest_01(root:Path=ROOT)->dict:
    tests=[]
    def rec(name,ok,detail=None):tests.append({'name':name,'status':'PASS' if ok else 'FAIL','detail':detail})
    chk=component_source_check(root,strict_fileset=False);rec('native_sourcecheck',chk.get('status')=='PASS',chk.get('errors'))
    rec('legacy_compat_absent',not (Path(root)/'.runtime'/'legacy_compat').exists())
    try:
        a=validate_authority_set(root);rec('native_authority_validate',bool(a),a.get('save_set_id') if a else None)
        w=_authority_world_text(root);rec('rules_catalog_roundtrip_world',RUNTIME_RULES_MARKER in w and STATIC_CATALOG_MARKER in w,len(w))
        st=read_json(Path(root)/'state.json');rec('finance_fixed_point_integrity',_finance_integrity_report(st).get('status')=='PASS',_finance_integrity_report(st))
        sm=_asset_semantic_map(st.get('inventories') or {});rec('asset_semantic_map_v2',sm.get('schema')==ASSET_SEMANTIC_MAP_SCHEMA,sm.get('counts'))
        dr=_domain_runtime_integrity_report(st);rec('domain_command_runtime_integrity',dr.get('status') in {'PASS','LEGACY'},dr)
        cs=cold_start_packet(Path(root));rec('cold_start_native',cs.get('packet')==COLD_START_PACKET_SCHEMA,cs.get('game_time'))
        q=query_packet(Path(root),'远航者舰队当前位置',detail='compact');rec('location_query_contract',q.get('status')=='COMPLETE',q.get('status'))
        q2=query_packet(Path(root),'莉娅的医疗观察状态',detail='compact');rec('lia_query_contract',q2.get('status')=='COMPLETE',q2.get('status'))
        with tempfile.TemporaryDirectory(prefix='voyager_native_stage_test_') as td:
            # stage constructor is the actual transaction entry point; assert it contains only component files + runtime dirs.
            info=create_stage(Path(root),'selftest');sp=Path(info['staging']);rec('native_stage_no_legacy_files',not any((sp/x).exists() for x in ('INDEX.md','WORLD.md','STATE.json','TASKS.json','HISTORY.jsonl')));shutil.rmtree(sp,ignore_errors=True)
    except Exception as ex:rec('native_selftest_exception',False,f'{type(ex).__name__}:{ex}')
    failed=sum(1 for x in tests if x['status']=='FAIL');return {'status':'PASS' if not failed else 'FAIL','engine_version':ENGINE_VERSION,'passed':len(tests)-failed,'failed':failed,'tests':tests}

# === END NATIVE COMPONENT LAYER ===

def asset_reconcile_packet(base:Path=ROOT)->dict:
    ready=ensure_source_ready(base);state=read_json(Path(base)/'state.json');ledger=state.get('asset_ledger_v1') or {};reg=(state.get('engine_runtime') or {}).get('asset_mapping_registry') or {};groups={};unverified=[];mismatches=[];seen=set()
    for row in reg.get('migrated_entries') or []:
        path=str(row.get('source_path') or '');aid=str(row.get('asset_id') or '');rec=(ledger.get('assets') or {}).get(aid) or {};role=str(row.get('field_role') or 'quantity')
        if path in seen:mismatches.append({'source_path':path,'kind':'duplicate_mapping'});continue
        seen.add(path)
        try:old=get_by_path(state,path)
        except Exception:old=None
        quantity=(rec.get('fields') or {}).get(role)
        if old!=quantity:mismatches.append({'source_path':path,'asset_id':aid,'kind':'projection_mismatch','ledger':quantity,'legacy':old})
        unit=rec.get('unit')
        if not unit or rec.get('unit_status')!='verified':unverified.append({'asset_id':aid,'source_path':path,'missing':['verified_unit']});continue
        key=(rec.get('asset_type_id'),unit,rec.get('owner_ref'),rec.get('location_ref'))
        if not all(key) or not isinstance(quantity,(int,float)) or isinstance(quantity,bool):mismatches.append({'asset_id':aid,'kind':'invalid_group_dimensions_or_quantity'});continue
        g=groups.setdefault(key,{'asset_type_id':key[0],'unit':key[1],'owner_ref':key[2],'location_ref':key[3],'quantity':0,'asset_ids':[]})
        g['quantity']=_domain_number_add(g['quantity'],quantity);g['asset_ids'].append(aid)
    return {'packet':'ASSET_RECONCILIATION_V1','status':'FAIL' if mismatches else 'PASS_WITH_UNVERIFIED_UNITS' if unverified else 'PASS','save_set_id':ready.get('save_set_id'),'game_time':state.get('game_time'),'migrated_field_count':len(seen),'excluded_field_count':len(reg.get('excluded_entries') or []),'verified_groups':[groups[x] for x in sorted(groups)],'unverified_units':unverified,'mismatches':mismatches,'policy':'Each total is scoped to identical type, unit, owner and location; excluded fields never counted.'}


def asset_query_packet(base:Path=ROOT,asset_id:Optional[str]=None,legacy_path:Optional[str]=None)->dict:
    ready=ensure_source_ready(base);state=read_json(Path(base)/'state.json');ledger=state.get('asset_ledger_v1') or {};reg=(state.get('engine_runtime') or {}).get('asset_mapping_registry') or {}
    if ledger.get('authority_mode')!='ledger_canonical_legacy_read_only':raise EngineError('ASSET_LEDGER_CANONICAL_MIGRATION_REQUIRED')
    if asset_id and legacy_path:raise EngineError('ASSET_QUERY_CHOOSE_ONE_REFERENCE')
    if legacy_path:
        if not legacy_path.startswith('state:inventories.'):raise EngineError('ASSET_QUERY_LEGACY_REFERENCE_INVALID')
        row=_asset_registry_entry(state,legacy_path)
        if not row:raise EngineError('ASSET_QUERY_LEGACY_REFERENCE_UNKNOWN')
        if 'reason_code' in row:raise EngineError('ASSET_QUERY_EXCLUDED:'+str(row['reason_code']))
        asset_id=str(row['asset_id'])
    assets=ledger.get('assets') or {}
    if asset_id:
        rec=assets.get(asset_id)
        if not isinstance(rec,dict):raise EngineError('ASSET_QUERY_NOT_FOUND:'+asset_id)
        rows=[copy.deepcopy(rec)]
    else:rows=[copy.deepcopy(assets[x]) for x in sorted(assets)]
    return {'packet':'ASSET_LEDGER_QUERY_V1','save_set_id':ready.get('save_set_id'),'game_time':state.get('game_time'),'authority':'state:asset_ledger_v1.assets','projection_status':'MATCH' if _validate_active_asset_ledger(state) is None else 'CONFLICT','asset_count':len(rows),'assets':rows,'excluded_source_field_count':len(reg.get('excluded_entries') or []),'totals_policy':'No aggregate across different units, types, owners or locations'}


def domain_command_catalog_v1408(base:Path=ROOT)->dict:
    ensure_source_ready(base)
    return {'packet':'DOMAIN_COMMAND_CATALOG_V1','schema':DOMAIN_COMMAND_SCHEMA,'canonical_entry':'invoke','legacy_entry':'domaincommand','queries':['commandcatalog','domainstatus','assetquery','assetreconcile','query','querybatch','rulesaudit'],'common_required':{'schema':'literal DOMAIN_COMMAND_V2','command_id':'nonempty string','base_save_set_id':'committed SAVESET string','kind':'canonical kind or exact alias','authorization':'literal standing_authorization','authorization_ref':'existing active grant ID','actor_id':'grant subject ID'},'kinds':{k:{'required_fields':{field:('positive number' if field=='qty' else 'object' if field in ('task','completion_evidence') else 'list[completion_action]' if field=='completion_actions' else 'game timestamp' if field in ('complete_at','arrival_at') else 'nonempty string') for field in DOMAIN_REQUIRED_FIELDS[k]},'optional_fields':({'gold_delta':'gold, 4 decimals; nonpositive verified spend','grey_delta':'grey, 2 decimals; nonpositive verified spend'} if k=='adjust_funds' else {'completion_actions':'validated compare-and-set actions'} if k=='start_medical_observation' else {'task':'title and task_id only; no resource or progress claim'} if k in ('construct_facility','start_manufacturing','start_research') else {}),'authorization':'standing_authorization with verified machine_grant','result':'DOMAIN_COMMAND_RESULT_V2'} for k in sorted(DOMAIN_PUBLIC_KINDS)},'aliases':copy.deepcopy(DOMAIN_KIND_ALIASES),'references':{'state':'state:<canonical path>','task':'tasks:task:<task_id>','entity':'state:entity:<entity_id>','location':'state:location:<location_id>'},'unavailable_legacy_kinds':sorted(DOMAIN_COMMAND_KINDS-DOMAIN_PUBLIC_KINDS),'result_categories':['ARGUMENT_ERROR','REFERENCE_NOT_FOUND','AUTHORIZATION_DENIED','PRECONDITION_NOT_MET','DRY_RUN','SAVED','ALREADY_APPLIED']}


def main(argv:Optional[List[str]]=None)->int:
    p=argparse.ArgumentParser(prog="game_engine.py")
    p.add_argument("--version-info",action="store_true")
    sub=p.add_subparsers(dest="cmd")
    sub.add_parser("guard")
    c=sub.add_parser("check");c.add_argument("--full",action="store_true");c.add_argument("--quick",action="store_true");c.add_argument("--base",default=str(ROOT));c.add_argument("--allow-unbound-manifest",action="store_true",help="engine-upgrade staging only: validate authority data before a new manifest is generated")
    q=sub.add_parser("query");q.add_argument("topic");q.add_argument("--base",default=str(ROOT));q.add_argument("--history-limit",type=int,default=5);q.add_argument("--detail",choices=["exact","compact","context","full"],default="compact")
    rf=sub.add_parser("reportframe");rf.add_argument("--base",default=str(ROOT));rf.add_argument("--since");rf.add_argument('--since-seq',type=int)
    qb=sub.add_parser('querybatch');qb.add_argument('--topics',required=True);qb.add_argument('--base',default=str(ROOT));qb.add_argument('--detail',choices=['compact','context','full'],default='compact')
    ep=sub.add_parser('evidence');ep.add_argument('--source',choices=['state','rules','catalog','events','manifest'],required=True);ep.add_argument('--path',required=True);ep.add_argument('--offset',type=int,default=0);ep.add_argument('--limit',type=int,default=4000);ep.add_argument('--base',default=str(ROOT))
    for viewer_parser in (q,rf,qb,ep):
        viewer_parser.add_argument('--audience',choices=['player','observer','gm'],default='player')
        viewer_parser.add_argument('--observer-id')
        viewer_parser.add_argument('--gm-context')
    si=sub.add_parser('sceneindex');si.add_argument('--base',default=str(ROOT));si.add_argument('--offset',type=int,default=0);si.add_argument('--limit',type=int,default=20)
    sq=sub.add_parser('scenequery');sq.add_argument('--base',default=str(ROOT));sq.add_argument('--id',required=True)
    for viewer_parser in (si,sq):
        viewer_parser.add_argument('--audience',choices=['player','observer','gm'],default='player')
        viewer_parser.add_argument('--observer-id');viewer_parser.add_argument('--gm-context')
    sp=sub.add_parser('startup');sp.add_argument('--base',default=str(ROOT));sp.add_argument('--layer',choices=['essential','navigation','focus'],default='essential');sp.add_argument('--offset',type=int,default=0);sp.add_argument('--limit',type=int,default=20);sp.add_argument('--budget-bytes',type=int,default=4096)
    ra=sub.add_parser('rulesaudit');ra.add_argument('--base',default=str(ROOT));ra.add_argument('--rule-id')
    fg=sub.add_parser('validateforce');fg.add_argument('--input',required=True)
    cc=sub.add_parser("combatcalc");cc.add_argument("kind",choices=["ship","ground","aircraft"]);cc.add_argument("--base",default=str(ROOT));cc.add_argument("--input",required=True,help="JSON object, @path/to/input.json, or an existing plain JSON file path; ship requires length_m, hull_type, source_factor, hull_age_years")
    bp=sub.add_parser("battleprepare");bp.add_argument("--base",default=str(ROOT));bp.add_argument("--input",required=True,help="battle intent JSON; authority-backed participants and registered equipment only; direct combat numbers forbidden")
    bc=sub.add_parser("battlecalc");bc.add_argument("--base",default=str(ROOT));bc.add_argument("--input",required=True,help="BATTLE_SNAPSHOT_V2 returned by battleprepare; raw combat numbers are rejected")
    ba=sub.add_parser("battleapply");ba.add_argument("--input",required=True,help="restricted: verified authorization bridge required before writeback");ba.add_argument("--version");ba.add_argument("--scope",default="battle mechanical writeback");ba.add_argument("--dry-run",action="store_true")
    bcm=sub.add_parser("battlecommit");bcm.add_argument("--input",required=True,help="restricted: verified authorization bridge required before writeback");bcm.add_argument("--version");bcm.add_argument("--scope",default="battle full transaction");bcm.add_argument("--dry-run",action="store_true")
    ms=sub.add_parser("maintenance");ms.add_argument("--base",default=str(ROOT))
    me=sub.add_parser("maintenanceenqueue");me.add_argument("--input",required=True);me.add_argument("--version");me.add_argument("--scope",default="maintenance queue enqueue");me.add_argument("--dry-run",action="store_true")
    ic=sub.add_parser("invoke");ic.add_argument("--input",required=True);ic.add_argument("--version");ic.add_argument("--scope",default="domain command transaction");ic.add_argument("--dry-run",action="store_true")
    ccatalog=sub.add_parser("commandcatalog");ccatalog.add_argument("--base",default=str(ROOT))
    ar=sub.add_parser("assetreconcile");ar.add_argument("--base",default=str(ROOT))
    aq=sub.add_parser("assetquery");aq.add_argument("--id");aq.add_argument("--legacy-path");aq.add_argument("--base",default=str(ROOT))
    dc=sub.add_parser("domaincommand");dc.add_argument("--input",required=True);dc.add_argument("--version");dc.add_argument("--scope",default="domain command transaction");dc.add_argument("--dry-run",action="store_true")
    dsr=sub.add_parser("domainstatus");dsr.add_argument("--base",default=str(ROOT))
    sg=sub.add_parser("secondhandgate");sg.add_argument("transaction_id");sg.add_argument("--base",default=str(ROOT))
    cg=sub.add_parser("contactgate");cg.add_argument("runtime_event_id");cg.add_argument("target_class",choices=sorted(CONTACT_INITIATIVE_CLASSES));cg.add_argument("--base",default=str(ROOT))
    t=sub.add_parser("turn");t.add_argument("--base",default=str(ROOT));t.add_argument("--mode",choices=["event","until","preview"],default="event");t.add_argument("--until");t.add_argument("--interrupt-level",choices=["routine","notable","important","critical"]);t.add_argument("--detail",choices=["compact","full"],default="compact");t.add_argument("--review-ack")
    pr=sub.add_parser("process");pr.add_argument("--base",default=str(ROOT));pr.add_argument("--until",required=True);pr.add_argument("--review-ack")
    ap=sub.add_parser("apply");ap.add_argument("--staging",required=True);ap.add_argument("--patch",required=True)
    d=sub.add_parser("diff");d.add_argument("--from-dir");d.add_argument("--to-dir",default=str(ROOT));d.add_argument("--limit",type=int,default=200)
    st=sub.add_parser("stage");st.add_argument("--label",default="work")
    sv=sub.add_parser("save");sv.add_argument("--staging",required=True);sv.add_argument("--version",required=True);sv.add_argument("--scope",required=True);sv.add_argument("--export",action="store_true");sv.add_argument("--no-export",action="store_true");sv.add_argument("--publish",action="store_true")
    tx=sub.add_parser("transact");tx.add_argument("--patch",required=True);tx.add_argument("--version",required=True);tx.add_argument("--scope",required=True);tx.add_argument("--export",action="store_true");tx.add_argument("--publish",action="store_true");tx.add_argument("--review-ack")
    sc=sub.add_parser("sourcecheck");sc.add_argument("--base",default=str(ROOT));sc.add_argument("--mode",choices=["project","runtime"],default="project")
    pk=sub.add_parser("package");pk.add_argument("--save-set")
    vpk=sub.add_parser("packtransport");vpk.add_argument("--save-set")
    vpc=sub.add_parser("vpackcheck");vpc.add_argument("--base",required=True)
    dr=sub.add_parser("doctor");dr.add_argument("--base",default=str(ROOT));dr.add_argument("--source-dir");dr.add_argument("--deep",action="store_true")
    ar=sub.add_parser("archiveplan");ar.add_argument("--base",default=str(ROOT))
    rp=sub.add_parser("routineplan");rp.add_argument("--base",default=str(ROOT));rp.add_argument("--until",required=True)
    aa=sub.add_parser("autoadvance");aa.add_argument("--until",required=True);aa.add_argument("--version",required=True);aa.add_argument("--scope",required=True);aa.add_argument("--publish",action="store_true")
    eu=sub.add_parser("engineupgrade");eu.add_argument("--candidate",required=True);eu.add_argument("--save-version",required=True);eu.add_argument("--scope",required=True);eu.add_argument("--migration-patch");eu.add_argument("--no-export",action="store_true")
    sub.add_parser("boot")
    sub.add_parser("cachebuild")
    pq=sub.add_parser("pricequote");pq.add_argument("--input",required=True);pq.add_argument("--base",default=str(ROOT))
    pi=sub.add_parser("pricequery");pi.add_argument("--input",default="{}");pi.add_argument("--base",default=str(ROOT))
    mo=sub.add_parser("marketoffer");mo.add_argument("--input",required=True,help="JSON object, @path/to/input.json, or an existing plain JSON file path")
    ac=sub.add_parser("autocandidates");ac.add_argument("--min-count",type=int,default=3)
    sub.add_parser("enginehealth")
    pf=sub.add_parser("performance");pf.add_argument("--limit",type=int,default=50)
    sub.add_parser("versionedcurrentplan")
    sub.add_parser("worldpurifyplan");wpur=sub.add_parser("worldpurify");wpur.add_argument("--version");wpur.add_argument("--scope",default="WORLD historical snapshot purification");wpur.add_argument("--dry-run",action="store_true")
    sub.add_parser("statearchiveplan");sa=sub.add_parser("statearchive");sa.add_argument("--version");sa.add_argument("--scope",default="STATE semantic archive");sa.add_argument("--dry-run",action="store_true")
    sub.add_parser("taskcompactplan");tc=sub.add_parser("taskcompact");tc.add_argument("--version");tc.add_argument("--scope",default="TASKS automatic historical compaction");tc.add_argument("--dry-run",action="store_true")
    sub.add_parser("historystatus");he=sub.add_parser("historyepoch");he.add_argument("--version");he.add_argument("--scope",default="HISTORY Epoch threshold compaction");he.add_argument("--dry-run",action="store_true");he.add_argument("--force",action="store_true")
    sub.add_parser("assetledgerplan");al=sub.add_parser("assetledgermigrate");al.add_argument("--version");al.add_argument("--scope",default="ASSET_LEDGER_V1 domain migration");al.add_argument("--batch",required=True);al.add_argument("--dry-run",action="store_true");al.add_argument("--force",action="store_true")
    gc=sub.add_parser("gc");gc.add_argument("--dry-run",action="store_true");gc.add_argument("--aggressive",action="store_true",help="end-of-audit cleanup with a 60-second safety floor for known disposable artifacts")
    ss=sub.add_parser("session");ss.add_argument("action",choices=["start","resume","status","recover","apply","advance","commit","abort"]);ss.add_argument("--until");ss.add_argument("--id");ss.add_argument("--patch");ss.add_argument("--version");ss.add_argument("--scope");ss.add_argument("--publish",action="store_true")
    ds=sub.add_parser("devsplit");ds.add_argument("--output")
    db=sub.add_parser("devbundle");db.add_argument("--source-dir",required=True);db.add_argument("--output",required=True)
    rc=sub.add_parser('refcheck');rc.add_argument('--base',default=str(ROOT))
    lm=sub.add_parser('migrate-old-save');lm.add_argument('--input',required=True);lm.add_argument('--output',required=True)
    sub.add_parser("selftest")
    for parser in (ss,sv,tx,aa):parser.add_argument('--verbose-result',action='store_true',help='include full validation and diff diagnostics')
    args=p.parse_args(argv)
    _perf_started=time.perf_counter()
    if args.version_info:
        print_json({"engine_version":ENGINE_VERSION,"engine_protocol":ENGINE_PROTOCOL,"runtime_schema":RUNTIME_SCHEMA,"task_runtime_schema":TASK_RUNTIME_SCHEMA,"guard_protocol":GUARD_PROTOCOL,"sha256":sha256_file(Path(__file__).resolve()),"path":str(Path(__file__).resolve())});return 0
    if not args.cmd:p.print_help();return 2
    try:
        diagnostic_commands={'check','doctor','diff','archiveplan','routineplan','enginehealth','performance','versionedcurrentplan','worldpurifyplan','statearchiveplan','taskcompactplan','historystatus','assetledgerplan','refcheck','autocandidates','selftest'}
        if args.cmd in diagnostic_commands and not (os.environ.get('VOYAGER_DEVELOPER_MODE')=='1' and os.environ.get('VOYAGER_DIAGNOSTIC_CONTEXT')=='gm'):
            raise EngineError('GM_DIAGNOSTIC_CONTEXT_REQUIRED')
        if args.cmd=='turn' and args.mode=='preview' and not (os.environ.get('VOYAGER_DEVELOPER_MODE')=='1' and os.environ.get('VOYAGER_DIAGNOSTIC_CONTEXT')=='gm'):
            raise EngineError('GM_DIAGNOSTIC_CONTEXT_REQUIRED')
        result=None
        if args.cmd=="guard":
            result=guard(ROOT,restore=True,restore_tool_files=True)
            if isinstance(result,dict) and result.get("status")=="PASS":
                try:_write_runtime_cache(ROOT,{"status":"PASS"})
                except Exception:pass
        elif args.cmd=="check":
            base=Path(args.base)
            if base.resolve()==ROOT.resolve() and args.full:guard(ROOT,restore=True,restore_tool_files=False)
            result=run_checks(base,full=args.full,require_manifest=not args.allow_unbound_manifest)
        elif args.cmd=="query":result=visible_query_packet(Path(args.base),args.topic,args.history_limit,args.detail,args.audience,args.observer_id,args.gm_context)
        elif args.cmd=="reportframe":result=visible_reportframe_packet(Path(args.base),args.since,args.since_seq,args.audience,args.observer_id,args.gm_context)
        elif args.cmd=='querybatch':result=visible_query_batch_packet(Path(args.base),_cli_json_input(args.topics,'QUERY_BATCH'),args.detail,args.audience,args.observer_id,args.gm_context)
        elif args.cmd=='evidence':result=visible_evidence_packet(Path(args.base),args.source,args.path,args.offset,args.limit,args.audience,args.observer_id,args.gm_context)
        elif args.cmd=='sceneindex':result=scene_index_packet(Path(args.base),args.offset,args.limit,args.audience,args.observer_id,args.gm_context)
        elif args.cmd=='scenequery':result=scene_query_packet(Path(args.base),args.id,args.audience,args.observer_id,args.gm_context)
        elif args.cmd=='startup':result=startup_layer_packet(Path(args.base),args.layer,args.offset,args.limit,args.budget_bytes)
        elif args.cmd=='rulesaudit':result=resolve_rule_registry(Path(args.base),args.rule_id)
        elif args.cmd=='validateforce':result=validate_force_generation_packet(_cli_json_input(args.input,'FORCE_GENERATION'),ROOT)
        elif args.cmd=="combatcalc":
            payload=_cli_json_input(args.input,"COMBAT_INPUT")
            result=combatcalc(Path(args.base),args.kind,payload)
        elif args.cmd=="battleprepare":
            payload=_cli_json_input(args.input,"BATTLE_PREPARE_INPUT");result=battleprepare(payload,Path(args.base))
        elif args.cmd=="battlecalc":
            payload=_cli_json_input(args.input,"BATTLE_INPUT")
            result=battlecalc(payload,Path(args.base))
        elif args.cmd=="battleapply":
            raise EngineError("BATTLE_WRITE_REQUIRES_VERIFIED_AUTHORIZATION_ENTRY")
            payload=_cli_json_input(args.input,"BATTLE_APPLY_INPUT");result=battle_apply(ROOT,payload,args.version,args.scope,args.dry_run)
        elif args.cmd=="battlecommit":
            raise EngineError("BATTLE_WRITE_REQUIRES_VERIFIED_AUTHORIZATION_ENTRY")
            payload=_cli_json_input(args.input,"BATTLE_COMMIT_INPUT");result=battle_commit(ROOT,payload,args.version,args.scope,args.dry_run)
        elif args.cmd=="maintenance":result=maintenance_status_packet(Path(args.base))
        elif args.cmd=="maintenanceenqueue":
            raise EngineError("MAINTENANCE_ENQUEUE_UNAVAILABLE_USE_INVOKE_VERIFIED_JOB")
        elif args.cmd=="commandcatalog":result=domain_command_catalog(Path(args.base))
        elif args.cmd=="assetreconcile":result=asset_reconcile_packet(Path(args.base))
        elif args.cmd=="assetquery":result=asset_query_packet(Path(args.base),args.id,args.legacy_path)
        elif args.cmd in ("domaincommand","invoke"):
            payload=_cli_json_input(args.input,"DOMAIN_COMMAND_INPUT");result=domain_command_packet(ROOT,payload,args.version,args.scope,args.dry_run)
        elif args.cmd=="domainstatus":result=domain_command_status(Path(args.base))
        elif args.cmd=="secondhandgate":result=secondhand_gate_packet(Path(args.base),args.transaction_id)
        elif args.cmd=="contactgate":result=contact_gate_packet(Path(args.base),args.runtime_event_id,args.target_class)
        elif args.cmd=="turn":result=turn_packet(Path(args.base),args.mode,args.until,args.interrupt_level,args.detail,Path(args.review_ack) if args.review_ack else None)
        elif args.cmd=="process":result=process_packet(Path(args.base),args.until,Path(args.review_ack) if args.review_ack else None)
        elif args.cmd=="apply":
            if COMPONENT_MODE and os.environ.get("VOYAGER_DEVELOPER_MODE")!="1":raise EngineError("RAW_PATCH_INTERNAL_ONLY_USE_DOMAIN_COMMAND_OR_SESSION")
            result=apply_patch(Path(args.staging),Path(args.patch))
        elif args.cmd=="diff":
            to=Path(args.to_dir);fr=Path(args.from_dir) if args.from_dir else latest_valid_snapshot(ROOT)["dir"];result=diff_dirs(fr,to,args.limit)
        elif args.cmd=="stage":
            if COMPONENT_MODE and os.environ.get("VOYAGER_DEVELOPER_MODE")!="1":raise EngineError("RAW_STAGE_INTERNAL_ONLY_USE_DOMAIN_COMMAND_OR_SESSION")
            result=create_stage(ROOT,args.label)
        elif args.cmd=="save":
            if COMPONENT_MODE and os.environ.get("VOYAGER_DEVELOPER_MODE")!="1":raise EngineError("RAW_SAVE_INTERNAL_ONLY_USE_DOMAIN_COMMAND_OR_SESSION")
            result=atomic_save(Path(args.staging),args.version,args.scope,ROOT,args.export and not args.no_export,args.publish)
        elif args.cmd=="transact":
            if COMPONENT_MODE and os.environ.get("VOYAGER_DEVELOPER_MODE")!="1":raise EngineError("RAW_TRANSACT_INTERNAL_ONLY_USE_DOMAIN_COMMAND_OR_SESSION")
            result=transact(ROOT,Path(args.patch),args.version,args.scope,args.export,Path(args.review_ack) if args.review_ack else None,args.publish)
        elif args.cmd=="sourcecheck":
            requested=Path(args.base).resolve()
            result=component_source_check(requested,strict_fileset=(args.mode=="project")) if (requested/"manifest.json").is_file() else component_source_check(requested,strict_fileset=(args.mode=="project"))
        elif args.cmd=="package":
            if COMPONENT_MODE:
                sid=args.save_set or (_component_manifest_read(COMPONENT_ROOT).get('save_set_id'))
                result=export_save_set(COMPONENT_ROOT,sid)
            else:
                if args.save_set:
                    sp=snapshot_path_from_sid(ROOT,args.save_set)
                    if sp is None:raise EngineError(f"PACKAGE_SAVESET_NOT_FOUND:{args.save_set}")
                    snap=validate_game_snapshot_available(sp,ROOT)
                    if snap is None:raise EngineError(f"PACKAGE_SAVESET_INVALID:{args.save_set}")
                else:
                    guard(ROOT,restore=True,restore_tool_files=False);snap=latest_valid_snapshot(ROOT,verify_parent=True)
                result=build_project_source_package(snap,ROOT)
        elif args.cmd=='packtransport':
            if COMPONENT_MODE:
                sid=args.save_set or (_component_manifest_read(COMPONENT_ROOT).get('save_set_id'))
                result=export_save_set(COMPONENT_ROOT,sid)
            else:
                if args.save_set:
                    sp=snapshot_path_from_sid(ROOT,args.save_set)
                    if sp is None:raise EngineError(f'VPACK_SAVESET_NOT_FOUND:{args.save_set}')
                    snap=validate_game_snapshot_available(sp,ROOT)
                    if snap is None:raise EngineError(f'VPACK_SAVESET_INVALID:{args.save_set}')
                else:
                    guard(ROOT,restore=True,restore_tool_files=False);snap=latest_valid_snapshot(ROOT,verify_parent=True)
                result=build_vpack_source_package(snap,ROOT)
        elif args.cmd=='vpackcheck':result=component_source_check(Path(args.base).resolve(),strict_fileset=True) if (Path(args.base).resolve()/'manifest.json').is_file() else vpack_transport_check(Path(args.base).resolve())
        elif args.cmd=="doctor":result=doctor(Path(args.base),Path(args.source_dir) if args.source_dir else None,args.deep)
        elif args.cmd=="archiveplan":result=runtime_archive_plan(Path(args.base))
        elif args.cmd=="routineplan":result=routineplan_packet(Path(args.base),args.until)
        elif args.cmd=="autoadvance":result=autoadvance(ROOT,args.until,args.version,args.scope,False,args.publish)
        elif args.cmd=="engineupgrade":result=engine_upgrade_packet(ROOT,Path(args.candidate),args.save_version,args.scope,Path(args.migration_patch) if args.migration_patch else None,False)
        elif args.cmd=="boot":result=cold_start_packet(ROOT)
        elif args.cmd=="cachebuild":result=rebuild_runtime_cache_db(ROOT)
        elif args.cmd=="pricequote":result=price_quote_packet(Path(args.base),_cli_json_input(args.input,"PRICE_QUOTE"))
        elif args.cmd=="pricequery":result=price_query_packet(Path(args.base),_cli_json_input(args.input,"PRICE_QUERY"))
        elif args.cmd=="marketoffer":
            payload=_cli_json_input(args.input,"MARKET_OFFER_INPUT");result=market_offer_packet(payload,ROOT);result["settlement_status"]="NEEDS_CONFIRMED_REVALIDATED_TRANSACTION"
        elif args.cmd=="autocandidates":result=automation_candidate_packet(ROOT,args.min_count)
        elif args.cmd=="enginehealth":result=engine_health_packet(ROOT)
        elif args.cmd=="performance":result=performance_packet(ROOT,args.limit)
        elif args.cmd=="versionedcurrentplan":result=versioned_current_plan(ROOT)
        elif args.cmd=="worldpurifyplan":result=world_purify_plan(ROOT)
        elif args.cmd=="worldpurify":result=world_purify_apply(ROOT,args.version,args.scope,args.dry_run)
        elif args.cmd=="statearchiveplan":result=state_archive_plan(ROOT)
        elif args.cmd=="statearchive":result=state_archive_apply(ROOT,args.version,args.scope,args.dry_run)
        elif args.cmd=="taskcompactplan":result=task_compact_plan(ROOT)
        elif args.cmd=="taskcompact":result=task_compact_apply(ROOT,args.version,args.scope,args.dry_run)
        elif args.cmd=="historystatus":result=history_epoch_status(ROOT)
        elif args.cmd=="historyepoch":result=history_epoch_apply(ROOT,args.version,args.scope,args.dry_run,args.force)
        elif args.cmd=="assetledgerplan":result=asset_ledger_plan(ROOT)
        elif args.cmd=="assetledgermigrate":result=asset_ledger_migrate(ROOT,args.version,args.scope,args.dry_run,args.force,args.batch)
        elif args.cmd=="gc":result=runtime_gc(ROOT,args.dry_run,args.aggressive)
        elif args.cmd=="session":result=turn_session(args.action,args.until,args.id,Path(args.patch) if args.patch else None,args.version,args.scope,args.publish)
        elif args.cmd=='devsplit':result=devsplit_packet(Path(__file__),Path(args.output) if args.output else None)
        elif args.cmd=='devbundle':result=devbundle_packet(Path(args.source_dir),Path(args.output))
        elif args.cmd=='refcheck':result=reference_integrity_packet(Path(args.base))
        elif args.cmd=='migrate-old-save':result=legacy_migration_packet(Path(args.input),Path(args.output))
        elif args.cmd=="selftest":result=native_component_selftest(ROOT) if COMPONENT_MODE else selftest(ROOT)
        else:raise EngineError("unknown command")
        result=_component_post_command_sync(args.cmd,result)
        if not getattr(args,'verbose_result',False):result=_public_mobile_packet(result,args.cmd)
        _perf_record(args.cmd,_perf_started,result)
        print_json(result)
        return _cli_result_exit_code(args.cmd,result)
    except ForkError as e:
        print_json({"status":"FAIL","error":"FORK_DETECTED","detail":str(e)});return 3
    except CorruptedLatestError as e:
        print_json({"status":"FAIL","error":"CORRUPTED_LATEST_SNAPSHOT","detail":str(e)});return 4
    except TransactionNotCommitted as e:
        print_json({'status':'FAIL','committed':False,'save_set_id':e.save_set_id,
                    'export_status':'NOT_STARTED','external_persistence_confirmed':False,
                    'retry_action':'retry_transaction_after_guard','error':str(e)});return 1
    except EngineError as e:
        code=str(e).split(":",1)[0];category="ARGUMENT_ERROR" if any(x in code for x in ("ARGUMENT","SCHEMA","KIND_INVALID","KIND_REQUIRED")) else "REFERENCE_NOT_FOUND" if "NOT_FOUND" in code or "UNBOUND" in code else "AUTHORIZATION_DENIED" if "AUTHORIZATION" in code or "PROOF" in code else "PRECONDITION_NOT_MET"
        print_json({"status":"FAIL","committed":False,"save_set_id":None,"export_status":"NOT_REQUESTED","retry_action":"correct_request","result_category":category,"error_code":code,"error":str(e)});return 1
    except Exception as e:
        print_json({"status":"FAIL","error":"UNHANDLED_ENGINE_EXCEPTION","exception_type":type(e).__name__,"detail":str(e)});return 5



# === P0/P1 NATIVE EIGHT-COMPONENT OVERRIDES v1 ===
CURRENT_COMPONENT_ROLES = {'manifest','rules','catalog','state','tasks','events'}
LEGACY_COMPONENT_NAMES = {'WORLD':'rules','STATE':'state','TASKS':'tasks','HISTORY':'events','INDEX':'manifest'}
ASSET_MAPPING_REGISTRY_SCHEMA = 'ASSET_MAPPING_REGISTRY_V3'
ASSET_LEDGER_CANONICAL_FORMAT = 'ASSET_LEDGER_BATCH_REGISTRY_V2'
DOMAIN_COMMAND_SCHEMA = 'DOMAIN_COMMAND_V2'


def _component_role_ref(ref:str, *, allow_legacy_migration:bool=False)->str:
    """Normalize component-role references. Legacy names are accepted only by migration callers."""
    raw=str(ref or '').strip()
    if not raw:return raw
    head,sep,tail=raw.partition(':')
    if head in CURRENT_COMPONENT_ROLES:return raw
    if head.upper() in LEGACY_COMPONENT_NAMES:
        if not allow_legacy_migration:raise EngineError('LEGACY_COMPONENT_ROUTE_FORBIDDEN:'+head)
        return LEGACY_COMPONENT_NAMES[head.upper()]+(sep+tail if sep else '')
    return raw


def _native_current_protocol_integrity(base:Path)->dict:
    m=_component_manifest_read(base);st=read_json_view(base/'state.json');tk=read_json_view(base/'tasks.json');rr=read_json_view(base/'rules.json');cc=read_json_view(base/'catalog.json')
    meta,events,_=read_history_view(base/'events.jsonl')
    errs=[]
    for name,d in [('state',st),('tasks',tk),('rules',rr),('catalog',cc),('events_metadata',meta)]:
        if isinstance(d,dict) and 'save_version' in d:errs.append(name+':duplicate_current_save_version')
    blob=json.dumps({'state':st,'tasks':tk},ensure_ascii=False)
    if 'legacy_runtime_view' in blob or 'legacy_compat' in blob:errs.append('legacy_current_flag_present')
    def scan_routes(x,path=''):
        if isinstance(x,dict):
            for k,v in x.items():scan_routes(v,path+'.'+str(k))
        elif isinstance(x,list):
            for i,v in enumerate(x):scan_routes(v,path+f'[{i}]')
        elif isinstance(x,str) and any(t in path.lower() for t in ('retrieval_route','route_template','query_order','source_ref','stable_state_refs')):
            if re.search(r'(?<![A-Za-z])(WORLD|STATE|TASKS|HISTORY|INDEX):',x):errs.append('legacy_route:'+path+':'+x[:120])
    scan_routes(tk,'tasks');scan_routes(st,'state')
    reg=((st.get('engine_runtime') or {}).get('asset_mapping_registry') or {})
    if reg.get('schema')!=ASSET_MAPPING_REGISTRY_SCHEMA:errs.append('asset_mapping_registry_missing')
    for rel,rec in _component_cold_archives(m).items():
        fp=base/rel
        if not fp.is_file():errs.append('cold_archive_missing:'+rel);continue
        expected_hash=rec.get('file_sha256')
        if not isinstance(expected_hash,str) or len(expected_hash)!=64:errs.append('cold_archive_hash_metadata:'+rel)
        elif _csha_file(fp)!=expected_hash:errs.append('cold_archive_hash_mismatch:'+rel)
        payload_hash=rec.get('payload_sha256')
        if payload_hash is not None and (not isinstance(payload_hash,str) or len(payload_hash)!=64):errs.append('cold_archive_payload_hash_metadata:'+rel)
    rreg=rr.get('rule_registry') or {}
    try:resolve_rule_registry(base)
    except EngineError as ex:errs.append('rule_registry_invalid:'+str(ex))
    creg=cc.get('catalog_registry') or {}
    if creg.get('schema')!='CATALOG_REGISTRY_V3' or not isinstance(creg.get('entities'),dict):errs.append('catalog_registry_not_v3')
    return {'status':'PASS' if not errs else 'FAIL','errors':errs,'manifest_version':m.get('save_version'),'rule_count':len(rreg.get('rules') or {}),'catalog_entity_count':len(creg.get('entities') or {}),'asset_mapping_count':reg.get('entry_count')}


_component_source_check_base = _v130_layer_component_source_check_01
def _v130_layer_component_source_check_02(root:Path=COMPONENT_ROOT,strict_fileset:bool=True)->dict:
    out=_component_source_check_base(root,strict_fileset)
    if out.get('status')=='PASS':
        p=_native_current_protocol_integrity(Path(root))
        if p.get('status')!='PASS':
            out['status']='FAIL';out.setdefault('errors',[]).extend('NATIVE_PROTOCOL:'+x for x in p.get('errors',[]))
        out['native_protocol']=p
    return out


def _asset_registry_entry(state:dict,path:str)->Optional[dict]:
    reg=((state.get('engine_runtime') or {}).get('asset_mapping_registry') or {});canonical=path.removeprefix('state:').removeprefix('STATE.')
    if reg.get('schema')==ASSET_MAPPING_REGISTRY_SCHEMA:
        for row in (reg.get('migrated_entries') or [])+(reg.get('excluded_entries') or []):
            if isinstance(row,dict) and str(row.get('source_path'))==canonical:return row
        return None
    # Legacy V2 remains readable for older SAVESET validation/migration.
    for row in reg.get('entries') or []:
        if isinstance(row,dict) and str(row.get('source_path'))==canonical:return row
    return None

def _asset_registry_quantity_guard(state:dict,path:str)->dict:
    canonical=path[6:] if path.startswith(('STATE.','state:')) else path
    row=_asset_registry_entry(state,canonical)
    if not row:raise EngineError('ASSET_MAPPING_REQUIRED:'+canonical)
    if 'reason_code' in row:raise EngineError('ASSET_MAPPING_EXCLUDED:'+str(row.get('reason_code'))+':'+canonical)
    if row.get('semantic_type')!='quantity':raise EngineError('ASSET_MAPPING_NOT_QUANTITY:'+canonical)
    if row.get('confidence/status')=='ambiguous':raise EngineError('ASSET_MAPPING_AMBIGUOUS:'+canonical)
    if str(row.get('migration_status') or '').startswith(('blocked','excluded')):raise EngineError('ASSET_MAPPING_MIGRATION_BLOCKED:'+canonical)
    return row

def _asset_ledger_mapped_row(state:dict,ref:str)->tuple:
    if not isinstance(ref,str) or not ref.startswith('state:inventories.'):
        raise EngineError('ASSET_REFERENCE_CANONICAL_STATE_REQUIRED')
    path=ref[6:];row=_asset_registry_quantity_guard(state,path)
    ledger=state.get('asset_ledger_v1') or {}
    if ledger.get('ledger_format')!=ASSET_LEDGER_CANONICAL_FORMAT or ledger.get('authority_mode')!='ledger_canonical_legacy_read_only':
        raise EngineError('ASSET_LEDGER_CANONICAL_MIGRATION_REQUIRED')
    aid=str(row.get('asset_id') or '');rec=(ledger.get('assets') or {}).get(aid)
    if not isinstance(rec,dict) or path not in (rec.get('source_paths') or []):raise EngineError('ASSET_LEDGER_MAPPING_MISSING:'+path)
    role=str(row.get('field_role') or 'quantity');quantity=(rec.get('fields') or {}).get(role)
    if quantity!=get_by_path(state,path):raise EngineError('ASSET_LEDGER_COMPATIBILITY_CONFLICT:'+path)
    return row,rec,quantity,path,role


def _domain_transfer_asset(state:dict,tasks:dict,payload:dict)->dict:
    src=str(payload.get('source_path') or '');dst=str(payload.get('dest_path') or '');qty=payload.get('qty')
    if src==dst:raise EngineError('ASSET_TRANSFER_DISTINCT_BUCKETS_REQUIRED')
    if not isinstance(qty,(int,float)) or isinstance(qty,bool) or not math.isfinite(float(qty)) or float(qty)<=0:raise EngineError('DOMAIN_ASSET_QTY_INVALID')
    sr,sa,sv,sp,role=_asset_ledger_mapped_row(state,src);dr,da,dv,dp,drole=_asset_ledger_mapped_row(state,dst)
    if sa['asset_id']==da['asset_id']:raise EngineError('ASSET_TRANSFER_DISTINCT_ASSET_RECORDS_REQUIRED')
    if role!=drole or sa.get('asset_type_id')!=da.get('asset_type_id') or not sa.get('asset_type_id'):
        raise EngineError('ASSET_TRANSFER_TYPE_MISMATCH')
    if not sa.get('unit') or sa.get('unit')!=da.get('unit'):raise EngineError('ASSET_TRANSFER_UNIT_UNVERIFIED_OR_MISMATCH')
    if sa.get('owner_ref')!=da.get('owner_ref'):raise EngineError('ASSET_TRANSFER_OWNERSHIP_CHANGE_REQUIRES_VERIFIED_CONTRACT')
    if not isinstance(sv,(int,float)) or isinstance(sv,bool) or not isinstance(dv,(int,float)) or isinstance(dv,bool):raise EngineError('ASSET_TRANSFER_QUANTITY_INVALID')
    if isinstance(sv,int) and not float(qty).is_integer():raise EngineError('DOMAIN_ASSET_INTEGER_SOURCE_REQUIRES_INTEGER_QTY')
    if float(sv)<float(qty):raise EngineError('DOMAIN_ASSET_INSUFFICIENT_SOURCE')
    after_source=_domain_number_add(sv,-qty);after_dest=_domain_number_add(dv,qty)
    if abs(float(sv)+float(dv)-float(after_source)-float(after_dest))>1e-9:raise EngineError('ASSET_QUANTITY_CONSERVATION_FAILED')
    sa['fields'][role]=after_source;da['fields'][drole]=after_dest
    parent,key=_dot_parent(state,sp);parent[key]=after_source
    parent,key=_dot_parent(state,dp);parent[key]=after_dest
    return {'kind':'transfer_asset','qty':qty,'asset_type_id':sa['asset_type_id'],'unit':sa['unit'],'source_asset_id':sa['asset_id'],'dest_asset_id':da['asset_id'],'source_before':sv,'source_after':after_source,'dest_before':dv,'dest_after':after_dest,'changes':[{'target':'state:asset_ledger_v1.assets.'+sa['asset_id']+'.fields.'+role,'action':'debit_asset'},{'target':'state:asset_ledger_v1.assets.'+da['asset_id']+'.fields.'+drole,'action':'credit_asset'},{'target':src,'action':'refresh_read_only_projection'},{'target':dst,'action':'refresh_read_only_projection'}]}


def _task_route_normalize_current(task:dict)->dict:
    out=copy.deepcopy(task);rr=out.get('retrieval_route') or {}
    for k in ('query_order','world_rules','history_tags'):
        if isinstance(rr.get(k),list):rr[k]=[_component_role_ref(x,allow_legacy_migration=False) for x in rr[k]]
    out['retrieval_route']=rr
    return out


def _domain_create_task(state,tasks,payload):
    t=payload.get('task')
    if not isinstance(t,dict):raise EngineError('DOMAIN_CREATE_TASK_OBJECT_REQUIRED')
    t=_task_route_normalize_current(t);tid=str(t.get('task_id') or '').strip()
    if not tid:raise EngineError('DOMAIN_CREATE_TASK_ID_REQUIRED')
    if str(t.get('type') or '') in {'construction','manufacturing','research'} and not (t.get('task_data') or {}).get('domain_created'):raise EngineError('DOMAIN_PROJECT_USE_TYPED_START')
    if _domain_task_lookup(tasks,tid)[2] is not None or any(str(x.get('task_id'))==tid for x in tasks.get('recent_completed_tasks',[]) if isinstance(x,dict)):raise EngineError('DOMAIN_TASK_ALREADY_EXISTS:'+tid)
    forbidden=('authorization','completion_evidence','completed_at','verified_resource_settlement') if (t.get('task_data') or {}).get('domain_created') else ('authorization','runtime_policy','completion_evidence','completed_at','verified_resource_settlement')
    if any(k in t for k in forbidden):raise EngineError('DOMAIN_TASK_CALLER_VERIFICATION_FORBIDDEN')
    status=str(t.get('status') or 'active');bucket='queued_tasks' if status in {'queued','scheduled','paused'} else 'active_tasks'
    t['status']='queued' if bucket=='queued_tasks' and status=='scheduled' else status
    # The engine supplies its own monitor contract; callers cannot assert verified
    # runtime/completion state, yet a minimal legitimate task remains executable.
    for key,value in {'priority':'normal','owner_ids':[],'location_ids':[],'resource_locks':[],'task_data':{},'phase':'waiting','report_policy':'按指挥官明确命令处理。','decision_gate':'未授权不自动执行。','semantic_context':'人工任务，无自动资源变更。','trigger_condition':'指挥官后续明确指令。','view_rule':{'schema':DERIVED_VIEW_RULE_SCHEMA,'status_sources':[],'next_source':'runtime_policy.monitor.next_review_at'}}.items():t.setdefault(key,copy.deepcopy(value))
    t.setdefault('runtime_policy',{'schema':'TASK_POLICY_V2','profile':'queued_standard' if bucket=='queued_tasks' else 'supervised_standard','monitor':{'mode':'manual','requires_ai_review':True,'review_on_time_advance':False,'event_driven':False,'next_review_at':None},'overrides':{},'task_class':'job'})
    tasks.setdefault(bucket,[]).append(t)
    return {'kind':'create_task','task_id':tid,'changes':[{'target':f'tasks:{bucket}.task:{tid}','action':'create_task'}]}


def _domain_cancel_task(state,tasks,payload):
    tid=str(payload.get('task_id') or '').strip();reason=str(payload.get('reason') or '').strip()
    if not tid or not reason:raise EngineError('DOMAIN_CANCEL_TASK_ID_AND_REASON_REQUIRED')
    bucket,i,t=_domain_task_lookup(tasks,tid)
    if t is None:raise EngineError('DOMAIN_TASK_NOT_FOUND_OR_ALREADY_CLOSED:'+tid)
    if (t.get('resource_locks') or []) or (t.get('runtime_policy') or {}).get('resolver'):raise EngineError('DOMAIN_CANCEL_REQUIRES_RESOURCE_RELEASE_CONTRACT')
    done=copy.deepcopy(t);done['status']='cancelled';done['phase']='cancelled';done['cancelled_at']=state.get('game_time');done['cancel_reason']=reason
    tasks[bucket].pop(i);tasks.setdefault('recent_completed_tasks',[]).append(done)
    return {'kind':'cancel_task','task_id':tid,'changes':[{'target':f'tasks:{bucket}.task:{tid}','action':'remove_cancelled_task'},{'target':f'tasks:recent_completed_tasks.task:{tid}','action':'append_cancelled_task'}]}


def _domain_pause_task(state,tasks,payload):
    tid=str(payload.get('task_id') or '').strip();reason=str(payload.get('reason') or '').strip()
    bucket,i,t=_domain_task_lookup(tasks,tid)
    if t is None:raise EngineError('DOMAIN_TASK_NOT_FOUND:'+tid)
    if bucket=='active_tasks':tasks[bucket].pop(i);tasks.setdefault('queued_tasks',[]).append(t);bucket='queued_tasks'
    t['status']='paused';t['phase']='paused';t['paused_at']=state.get('game_time');t['pause_reason']=reason or 'domain_command'
    return {'kind':'pause_task','task_id':tid,'changes':[{'target':f'tasks:{bucket}.task:{tid}','action':'pause_task'}]}


def _v130_layer__domain_schedule_task_01(state,tasks,payload):
    tid=str(payload.get('task_id') or '').strip();at=str(payload.get('scheduled_at') or '').strip()
    if not tid or parse_iso(at) is None:raise EngineError('DOMAIN_SCHEDULE_TASK_VALID_TIME_REQUIRED')
    bucket,i,t=_domain_task_lookup(tasks,tid)
    if t is None:raise EngineError('DOMAIN_TASK_NOT_FOUND:'+tid)
    if bucket=='active_tasks':tasks[bucket].pop(i);tasks.setdefault('queued_tasks',[]).append(t)
    t['status']='scheduled';t['phase']='scheduled';t.setdefault('task_data',{})['scheduled_at']=at
    return {'kind':'schedule_task','task_id':tid,'scheduled_at':at,'changes':[{'target':f'tasks:queued_tasks.task:{tid}','action':'schedule_task'}]}


def _domain_asset_state_change(state,tasks,payload,kind):
    p=copy.deepcopy(payload)
    p['source_path']=str(p.get('source_path') or '');p['dest_path']=str(p.get('dest_path') or '')
    out=_domain_transfer_asset(state,tasks,p);out['kind']=kind;return out


def _v130_layer__domain_job_start_01(state,tasks,payload,kind,job_kind):
    jid=str(payload.get('job_id') or '').strip();complete_at=payload.get('complete_at')
    if not jid:raise EngineError('DOMAIN_JOB_ID_REQUIRED')
    mr=_maintenance_runtime(state,create=True)
    try:_maintenance_find_active(mr,jid);raise EngineError('DOMAIN_JOB_ALREADY_EXISTS:'+jid)
    except EngineError as ex:
        if 'MAINTENANCE_JOB_NOT_FOUND' not in str(ex):raise
    job={'job_id':jid,'kind':job_kind,'started_at':state.get('game_time'),'complete_at':complete_at,'status':'active','subject_ref':payload.get('subject_ref'),'task_id':payload.get('task_id'),'data':copy.deepcopy(payload.get('data') or {})}
    q='medical' if 'medical' in job_kind or 'observation' in job_kind else 'repairs'
    mr.setdefault(q,[]).append(job)
    return {'kind':kind,'job_id':jid,'changes':[{'target':f'state:engine_runtime.maintenance_runtime.{q}','action':'start_job'}]}


def _domain_job_advance(state,tasks,payload,kind):
    jid=str(payload.get('job_id') or '').strip();progress=payload.get('progress')
    mr=_maintenance_runtime(state,create=True);q,i,job=_maintenance_find_active(mr,jid)
    if progress is not None:
        if not isinstance(progress,(int,float)) or isinstance(progress,bool):raise EngineError('DOMAIN_JOB_PROGRESS_INVALID')
        old=float(job.get('progress') or 0);new=float(progress)
        if new<old or new>100:raise EngineError('DOMAIN_JOB_PROGRESS_NONMONOTONIC')
        job['progress']=new
    for k in ('complete_at','status_note'):
        if k in payload:job[k]=payload[k]
    return {'kind':kind,'job_id':jid,'changes':[{'target':f'state:engine_runtime.maintenance_runtime.{q}.job:{jid}','action':'advance_job'}]}


def _v130_layer__domain_personnel_transfer_01(state,tasks,payload):
    src=str(payload.get('source_path') or '');dst=str(payload.get('dest_path') or '');qty=payload.get('qty')
    if not src.startswith('state:') or not dst.startswith('state:') or not isinstance(qty,int) or qty<=0:raise EngineError('DOMAIN_PERSONNEL_TRANSFER_FIELDS_INVALID')
    sp,sk=_dot_parent(state,src[6:]);dp,dk=_dot_parent(state,dst[6:]);sv=sp[sk];dv=dp[dk]
    if not isinstance(sv,int) or not isinstance(dv,int) or sv<qty:raise EngineError('DOMAIN_PERSONNEL_TRANSFER_COUNTS_INVALID')
    sp[sk]-=qty;dp[dk]+=qty
    return {'kind':'personnel_transfer','qty':qty,'changes':[{'target':src,'action':'decrement_personnel'},{'target':dst,'action':'increment_personnel'}]}


def _v130_layer__domain_travel_01(state,tasks,payload,kind):
    eid=str(payload.get('entity_id') or '').strip();loc=str(payload.get('location_id') or '').strip()
    if not eid or not loc:raise EngineError('DOMAIN_TRAVEL_ENTITY_LOCATION_REQUIRED')
    er=state.setdefault('entity_registry',{});entities=er.get('entities') if isinstance(er,dict) else None
    if not isinstance(entities,dict) or eid not in entities:raise EngineError('DOMAIN_TRAVEL_ENTITY_NOT_REGISTERED:'+eid)
    rec=entities[eid]
    if kind=='start_travel':
        rec['travel']={'from_location':rec.get('current_location_id'),'to_location':loc,'started_at':state.get('game_time'),'arrival_at':payload.get('arrival_at'),'status':'in_transit'}
    else:
        tr=rec.get('travel') or {}
        if tr.get('to_location') and tr.get('to_location')!=loc:raise EngineError('DOMAIN_TRAVEL_ARRIVAL_LOCATION_MISMATCH')
        rec['current_location_id']=loc;rec['travel']={'status':'arrived','arrived_at':state.get('game_time'),'to_location':loc}
    return {'kind':kind,'entity_id':eid,'location_id':loc,'changes':[{'target':f'state:entity_registry.entities.{eid}','action':kind}]}


def _domain_relocate_asset(state,tasks,payload):
    # Quantity relocation uses the same conserved transfer contract.
    out=_domain_transfer_asset(state,tasks,payload);out['kind']='relocate_asset';return out


def _domain_project_task(state,tasks,payload,kind,ptype):
    tid=str(payload.get('task_id') or '').strip()
    if kind.startswith('start_') or kind=='construct_facility':
        raw=payload.get('task') or {}
        if not isinstance(raw,dict) or any(k not in ('task_id','title','description') for k in raw):raise EngineError('DOMAIN_PROJECT_UNVERIFIED_PLAN_FIELDS_FORBIDDEN')
        task=copy.deepcopy(raw)
        task.setdefault('task_id',tid);task.setdefault('type',ptype);task.setdefault('status','queued');task.setdefault('phase','awaiting_verified_plan');task.setdefault('owner_ids',[]);task.setdefault('location_ids',[]);task.setdefault('resource_locks',[]);task.setdefault('retrieval_route',{'query_order':['tasks:self'],'state_paths':[]});task.setdefault('report_policy','等待可核验计划；未开始执行。');task.setdefault('decision_gate','需要指挥官确认资源、工期与完成条件。');task.setdefault('task_data',{});task['task_data']['project_kind']=ptype;task['task_data']['domain_created']=True;task.setdefault('title',ptype+' '+tid);task.setdefault('priority','normal');task.setdefault('view_rule',{'schema':DERIVED_VIEW_RULE_SCHEMA,'status_sources':[],'next_source':'runtime_policy.monitor.next_review_at'});task.setdefault('runtime_policy',{'schema':'TASK_POLICY_V2','profile':'queued_standard','monitor':{'mode':'external_wait','requires_ai_review':True,'review_on_time_advance':False,'event_driven':True},'overrides':{},'task_class':'job'})
        pp=copy.deepcopy(payload);pp['task']=task
        out=_domain_create_task(state,tasks,pp);out['kind']=kind;return out
    bucket,i,t=_domain_task_lookup(tasks,tid)
    if t is None:raise EngineError('DOMAIN_TASK_NOT_FOUND:'+tid)
    progress=payload.get('progress')
    if not isinstance(progress,(int,float)) or isinstance(progress,bool):raise EngineError('DOMAIN_PROJECT_PROGRESS_REQUIRED')
    td=t.setdefault('task_data',{});old=float(td.get('progress') or 0);new=float(progress)
    if new<old or new>100:raise EngineError('DOMAIN_PROJECT_PROGRESS_NONMONOTONIC')
    td['progress']=new;t['phase']=str(payload.get('phase') or t.get('phase') or 'in_progress')
    return {'kind':kind,'task_id':tid,'progress':new,'changes':[{'target':f'tasks:{bucket}.task:{tid}.task_data.progress','action':'advance_progress'}]}


def _domain_commitment(state,tasks,payload,kind):
    cid=str(payload.get('commitment_id') or '').strip();reg=state.setdefault('engine_runtime',{}).setdefault('commitment_registry',{'schema':'COMMITMENT_REGISTRY_V1','items':{}});items=reg.setdefault('items',{})
    if not cid:raise EngineError('DOMAIN_COMMITMENT_ID_REQUIRED')
    if kind in {'register_contract','register_commitment'}:
        if cid in items:raise EngineError('DOMAIN_COMMITMENT_ALREADY_EXISTS:'+cid)
        items[cid]={'commitment_id':cid,'type':'contract' if kind=='register_contract' else 'commitment','status':'open','created_at':state.get('game_time'),'terms':copy.deepcopy(payload.get('terms') or {}),'authorization_ref':payload.get('authorization_ref')}
    else:
        if cid not in items:raise EngineError('DOMAIN_COMMITMENT_NOT_FOUND:'+cid)
        items[cid]['status']='resolved';items[cid]['resolved_at']=state.get('game_time');items[cid]['resolution']=copy.deepcopy(payload.get('resolution') or {})
    return {'kind':kind,'commitment_id':cid,'changes':[{'target':f'state:engine_runtime.commitment_registry.items.{cid}','action':kind}]}


DOMAIN_PUBLIC_KINDS={'adjust_funds','transfer_asset','create_task','cancel_task','complete_task','start_repair','complete_repair','complete_maintenance','start_medical_observation','complete_medical','start_travel','arrive_location','construct_facility','start_manufacturing','start_research'}
DOMAIN_KIND_ALIASES={'资金调整':'adjust_funds','资产调拨':'transfer_asset','新建任务':'create_task','取消任务':'cancel_task','完成任务':'complete_task','开始维修':'start_repair','完成维修':'complete_repair','完成维护':'complete_maintenance','开始医疗观察':'start_medical_observation','完成医疗':'complete_medical','开始旅行':'start_travel','抵达地点':'arrive_location','建造设施':'construct_facility','开始制造':'start_manufacturing','开始研究':'start_research'}
DOMAIN_REQUIRED_FIELDS={'adjust_funds':('reason',),'transfer_asset':('source_path','dest_path','qty'),'create_task':('task',),'cancel_task':('task_id','reason'),'complete_task':('task_id','completion_evidence'),'start_repair':('job_id','complete_at','completion_actions'),'complete_repair':('job_id',),'complete_maintenance':('job_id',),'start_medical_observation':('job_id','complete_at'),'complete_medical':('job_id',),'start_travel':('entity_id','location_id','arrival_at'),'arrive_location':('entity_id','location_id'),'construct_facility':('task_id',),'start_manufacturing':('task_id',),'start_research':('task_id',)}
DOMAIN_COMMAND_KINDS={
 'adjust_funds','transfer_asset','deploy_ship','recall_ship','complete_maintenance','purchase_asset','sell_asset','manufacture_asset','capture_asset','transfer_ownership','authorize_task','complete_task','complete_repair','complete_medical',
 'create_task','cancel_task','pause_task','schedule_task','reserve_asset','release_asset','allocate_asset','start_manufacturing','advance_manufacturing','start_repair','advance_repair','start_medical_observation','update_medical_observation','personnel_transfer','start_travel','arrive_location','relocate_asset','construct_facility','advance_construction','start_research','advance_research','register_contract','register_commitment','resolve_commitment'
}


def _v130_layer__apply_domain_command_02(stage:Path,state:dict,tasks:dict,payload:dict)->dict:
    kind=str(payload.get('kind') or '')
    if kind not in DOMAIN_COMMAND_KINDS:raise EngineError(f'DOMAIN_COMMAND_KIND_INVALID:{kind}')
    if kind=='adjust_funds':return _domain_adjust_funds(state,tasks,payload)
    if kind=='transfer_asset':return _domain_transfer_asset(state,tasks,payload)
    if kind=='deploy_ship':return _domain_deploy_ship(state,tasks,payload)
    if kind=='recall_ship':return _domain_recall_ship(state,tasks,payload)
    if kind=='purchase_asset':return _domain_commercial_asset(state,tasks,payload,'purchase_asset')
    if kind=='sell_asset':return _domain_commercial_asset(state,tasks,payload,'sell_asset')
    if kind=='manufacture_asset':return _domain_commercial_asset(state,tasks,payload,'manufacture_asset')
    if kind=='capture_asset':return _domain_capture_asset(state,tasks,payload)
    if kind=='transfer_ownership':return _domain_transfer_ownership(state,tasks,payload)
    if kind=='authorize_task':return _domain_authorize_task(state,tasks,payload)
    if kind=='complete_task':return _domain_complete_task(state,tasks,payload)
    if kind=='complete_repair':return _domain_complete_maintenance_typed(stage,state,tasks,payload,'repair','complete_repair')
    if kind=='complete_medical':return _domain_complete_maintenance_typed(stage,state,tasks,payload,'medical','complete_medical')
    if kind=='complete_maintenance':return _domain_complete_maintenance(stage,state,tasks,payload)
    if kind=='create_task':return _domain_create_task(state,tasks,payload)
    if kind=='cancel_task':return _domain_cancel_task(state,tasks,payload)
    if kind=='pause_task':return _domain_pause_task(state,tasks,payload)
    if kind=='schedule_task':return _domain_schedule_task(state,tasks,payload)
    if kind in {'reserve_asset','release_asset','allocate_asset'}:return _domain_asset_state_change(state,tasks,payload,kind)
    if kind=='start_repair':return _domain_job_start(state,tasks,payload,kind,'repair')
    if kind=='advance_repair':return _domain_job_advance(state,tasks,payload,kind)
    if kind=='start_medical_observation':return _domain_job_start(state,tasks,payload,kind,'medical_observation')
    if kind=='update_medical_observation':return _domain_job_advance(state,tasks,payload,kind)
    if kind=='personnel_transfer':return _domain_personnel_transfer(state,tasks,payload)
    if kind in {'start_travel','arrive_location'}:return _domain_travel(state,tasks,payload,kind)
    if kind=='relocate_asset':return _domain_relocate_asset(state,tasks,payload)
    if kind in {'start_manufacturing','advance_manufacturing'}:return _domain_project_task(state,tasks,payload,kind,'manufacturing')
    if kind in {'construct_facility','advance_construction'}:return _domain_project_task(state,tasks,payload,kind,'construction')
    if kind in {'start_research','advance_research'}:return _domain_project_task(state,tasks,payload,kind,'research')
    if kind in {'register_contract','register_commitment','resolve_commitment'}:return _domain_commitment(state,tasks,payload,kind)
    raise EngineError('DOMAIN_COMMAND_UNREACHABLE:'+kind)


# Replace current asset planning with explicit-registry/domain-batch semantics.
def _asset_mapping_status(row:dict, field:str)->str:
    explicit=row.get(field+'_mapping_status')
    if explicit in {'known','unknown','unmapped','not_applicable'}: return explicit
    ref=row.get(field+'_ref')
    if ref in (None,''): return 'unmapped'
    if str(ref).endswith('unspecified'): return 'unknown'
    return 'known'

def _asset_group_conservation_report(state:dict, rows:list)->dict:
    by={}
    for r in rows: by.setdefault(str(r.get('asset_id')),[]).append(r)
    violations=[];checked=0
    for aid,grp in by.items():
        vals={}
        for r in grp:
            role=r.get('field_role');path=r.get('source_path')
            if role not in {'total','available','reserved','allocated'} or not path: continue
            try:v=get_by_path(state,path)
            except Exception: continue
            if isinstance(v,(int,float)) and not isinstance(v,bool): vals.setdefault(role,[]).append(float(v))
        if 'total' not in vals: continue
        checked+=1;total=vals['total'][0]
        if 'available' in vals and vals['available'][0]>total: violations.append({'asset_id':aid,'kind':'available_gt_total'})
        for role in ('reserved','allocated'):
            if role in vals and sum(vals[role])>total: violations.append({'asset_id':aid,'kind':role+'_gt_total'})
        # Exact equality is safe only when the registry explicitly says allocation coverage is complete.
        if any(bool(r.get('allocation_coverage_complete')) for r in grp):
            rhs=(vals.get('available') or [0])[0]+sum(vals.get('reserved') or [])+sum(vals.get('allocated') or [])
            if abs(total-rhs)>1e-9: violations.append({'asset_id':aid,'kind':'exact_conservation_failed','total':total,'rhs':rhs})
    return {'groups_checked':checked,'violations':violations,'status':'PASS' if not violations else 'FAIL'}

def asset_ledger_plan(base:Path=ROOT)->dict:
    ensure_source_ready(base);state=read_json(base/'state.json');reg=((state.get('engine_runtime') or {}).get('asset_mapping_registry') or {})
    if reg.get('schema')==ASSET_MAPPING_REGISTRY_SCHEMA:
        migrated=[x for x in (reg.get('migrated_entries') or []) if isinstance(x,dict)];excluded=[x for x in (reg.get('excluded_entries') or []) if isinstance(x,dict)]
        ledger=state.get('asset_ledger_v1') or {};batches=ledger.get('batches') or {};reports=[]
        for bid,b in batches.items():
            rows=[x for x in migrated if x.get('migration_batch_id')==bid];cons=_asset_group_conservation_report(state,rows)
            reports.append({'batch_id':bid,'quantity_rows':len(rows),'logical_assets':len(set(x.get('asset_id') for x in rows)),'excluded_source_field_count':int((b or {}).get('excluded_source_field_count',0) or 0),'conservation':cons,'status':'ACTIVE_MIGRATED_WITH_EXCLUSIONS' if str((b or {}).get('status','')).startswith('MIGRATED') else str((b or {}).get('status') or 'UNKNOWN')})
        return {'packet':'ASSET_LEDGER_PLAN_V7','registry_schema':ASSET_MAPPING_REGISTRY_SCHEMA,'entry_count':reg.get('entry_count'),'migrated_entry_count':len(migrated),'excluded_entry_count':len(excluded),'logical_asset_count':len(set(x.get('asset_id') for x in migrated)),'exclusion_reason_counts':copy.deepcopy(reg.get('exclusion_reason_counts') or {}),'batch_reports':reports,'unified_ledger_status':'ACTIVE_SPARSE_WITH_EXCLUSIONS','already_active':isinstance(state.get('asset_ledger_v1'),dict),'review_archive':copy.deepcopy(reg.get('review_archive') or {}),'policy':'Only explicitly migrated rows are ledger assets. Excluded source fields remain authoritative legacy fields; re-evaluation requires explicit archived review/evidence and never guesses ownership/location/container.'}
    # V2 compatibility for older SAVESETs.
    entries=[x for x in (reg.get('entries') or []) if isinstance(x,dict)]
    if not entries:raise EngineError('ASSET_MAPPING_REGISTRY_REQUIRED')
    batches=copy.deepcopy(reg.get('migration_batches') or []);batch_reports=[]
    quantity=[x for x in entries if x.get('semantic_type')=='quantity' and not str(x.get('migration_status') or '').startswith('excluded')]
    for b in batches:
        bid=b.get('batch_id');q=[x for x in quantity if x.get('migration_batch_id')==bid];cons=_asset_group_conservation_report(state,q)
        blocked=any(_asset_mapping_status(x,f) in {'unknown','unmapped'} for x in q for f in ('owner','location','container')) or bool(cons.get('violations'))
        batch_reports.append({'batch_id':bid,'quantity_rows':len(q),'logical_assets':len(set(x.get('asset_id') for x in q)),'conservation':cons,'status':'BLOCKED_MAPPING_INCOMPLETE' if blocked else 'READY_FOR_MIGRATION'})
    return {'packet':'ASSET_LEDGER_PLAN_V6_COMPAT','registry_schema':reg.get('schema'),'entry_count':reg.get('entry_count'),'batch_reports':batch_reports,'already_active':isinstance(state.get('asset_ledger_v1'),dict)}

def _asset_ledger_dry_run_preview(state:dict, rows:list, batch_report:dict)->dict:
    grouped={}
    for r in rows:
        aid=str(r.get('asset_id')); rec=grouped.setdefault(aid,{'asset_id':aid,'owner_ref':r.get('owner_ref'),'location_ref':r.get('location_ref'),'container_ref':r.get('container_ref'),'old_fields':{},'source_paths':[],'blockers':[]})
        path=str(r.get('source_path')); role=str(r.get('field_role') or 'quantity')
        try:v=get_by_path(state,path)
        except Exception:v='SOURCE_PATH_MISSING'
        rec['old_fields'][role]=v; rec['source_paths'].append(path)
        for fld in ('owner','location','container'):
            st=_asset_mapping_status(r,fld)
            if st in {'unknown','unmapped'}:
                rec['blockers'].append(fld+'_'+st)
    assets=[];excluded=[]
    for aid in sorted(grouped):
        rec=grouped[aid];rec['blockers']=sorted(set(rec['blockers']))
        rec['migration_eligibility']='EXCLUDED_BLOCKED' if rec['blockers'] else 'ELIGIBLE'
        rec['proposed_ledger_fields']=copy.deepcopy(rec['old_fields'])
        assets.append(rec)
        if rec['blockers']:excluded.append({'asset_id':aid,'blockers':rec['blockers']})
    return {'assets':assets,'excluded_assets':excluded,'eligible_asset_count':sum(1 for x in assets if x['migration_eligibility']=='ELIGIBLE'),'excluded_asset_count':len(excluded),'conservation':batch_report.get('conservation')}

def _asset_ledger_migrate_unlocked(root:Path=ROOT,version:Optional[str]=None,scope:str='asset domain migration',dry_run:bool=False,force:bool=False,batch:Optional[str]=None)->dict:
    state=read_json(root/'state.json');reg=((state.get('engine_runtime') or {}).get('asset_mapping_registry') or {})
    if reg.get('schema')==ASSET_MAPPING_REGISTRY_SCHEMA:
        ledger=state.get('asset_ledger_v1') or {};batches=ledger.get('batches') or {}
        if batch not in batches:raise EngineError('ASSET_LEDGER_BATCH_UNKNOWN:'+str(batch))
        rows=[x for x in (reg.get('migrated_entries') or []) if isinstance(x,dict) and x.get('migration_batch_id')==batch]
        rep=next((x for x in asset_ledger_plan(root).get('batch_reports',[]) if x.get('batch_id')==batch),{})
        return {'packet':'ASSET_LEDGER_MIGRATE_V6','status':'ALREADY_MIGRATED','dry_run_status':'DRY_RUN_ALREADY_MIGRATED' if dry_run else None,'batch_id':batch,'asset_count':len(set(x.get('asset_id') for x in rows)),'source_field_count':len(rows),'batch_report':rep,'force_ignored_for_safety_gates':bool(force),'saved':False,'policy':'Compact exclusions cannot be promoted without an explicit new evidence review; archived review data is evidence-only.'}
    plan=asset_ledger_plan(root);reports={x.get('batch_id'):x for x in plan.get('batch_reports',[])}
    if batch not in reports: raise EngineError('ASSET_LEDGER_BATCH_UNKNOWN:'+str(batch))
    rep=reports[batch]
    state=read_json(root/'state.json');reg=((state.get('engine_runtime') or {}).get('asset_mapping_registry') or {})
    rows=[x for x in reg.get('entries',[]) if x.get('semantic_type')=='quantity' and x.get('migration_batch_id')==batch and not str(x.get('migration_status') or '').startswith('excluded')]
    if rep.get('status')!='READY_FOR_MIGRATION':
        out={'packet':'ASSET_LEDGER_MIGRATE_V5','status':'BLOCKED_MAPPING_INCOMPLETE','dry_run_status':'DRY_RUN_BLOCKED' if dry_run else None,'batch_id':batch,'batch_report':rep,'force_ignored_for_safety_gates':bool(force),'saved':False}
        if dry_run: out['preview']=_asset_ledger_dry_run_preview(state,rows,rep)
        return out
    ledger=copy.deepcopy(state.get('asset_ledger_v1') or {'schema':'ASSET_LEDGER_V1','batches':{},'assets':{}})
    before={}
    for r in rows:
        aid=str(r.get('asset_id')); path=str(r.get('source_path')); role=str(r.get('field_role') or 'quantity')
        try:v=get_by_path(state,path)
        except Exception as ex: raise EngineError('ASSET_LEDGER_SOURCE_PATH_MISSING:'+path) from ex
        rec=ledger['assets'].setdefault(aid,{'asset_id':aid,'owner_ref':r.get('owner_ref'),'location_ref':r.get('location_ref'),'container_ref':r.get('container_ref'),'fields':{},'source_paths':[]})
        rec['fields'][role]=v;rec['source_paths'].append(path);before[path]=v
    ledger['batches'][batch]={'status':'MIGRATED','asset_count':len(set(x.get('asset_id') for x in rows)),'source_field_count':len(rows)}
    if dry_run:
        return {'packet':'ASSET_LEDGER_MIGRATE_V5','status':'DRY_RUN_READY','batch_id':batch,'asset_count':len(set(x.get('asset_id') for x in rows)),'source_field_count':len(rows),'conservation':_asset_group_conservation_report(state,rows),'preview':_asset_ledger_dry_run_preview(state,rows,rep),'saved':False}
    if not version:raise EngineError('ASSET_LEDGER_VERSION_REQUIRED')
    # This executor only activates once a batch is fully mapped; legacy source fields remain read-only compatibility views thereafter.
    state['asset_ledger_v1']=ledger
    rt=state.setdefault('engine_runtime',{}).setdefault('asset_ledger_runtime',{})
    rt.setdefault('migrated_batches',{})[batch]={'status':'active','legacy_fields':'derived_read_only'}
    info=create_stage(root,'asset_ledger');stage=Path(info['staging'])
    try:
        _write_authority_json(stage/'state.json',state);gt=str(state.get('game_time') or '')
        digest=sha256_bytes((str(batch)+str(version)+gt).encode())[:12]
        _append_engine_history(stage/'events.jsonl',{'event_id':f'EVT-ASSET-LEDGER-{digest}','game_time':gt,'type':'system','subtype':'asset_ledger_batch_migration','summary':f'GAME ENGINE v{ENGINE_VERSION}迁移资产账批次{batch}。','changes':[{'target':'state:asset_ledger_v1','action':'activate_batch'},{'target':'state:engine_runtime.asset_ledger_runtime','action':'record_migrated_batch'}],'source':f'GAME ENGINE v{ENGINE_VERSION} ASSET_LEDGER_V1','authority_files':['state.json'],'zero_time':True})
        saved=atomic_save(stage,version,scope,root,False,False)
        return {'packet':'ASSET_LEDGER_MIGRATE_V5','status':'MIGRATED','batch_id':batch,'asset_count':len(set(x.get('asset_id') for x in rows)),'saved':True,'save':saved}
    except BaseException:
        try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
        except Exception:pass
        raise


def asset_ledger_migrate(root:Path=ROOT,version:Optional[str]=None,scope:str='asset domain migration',dry_run:bool=False,force:bool=False,batch:Optional[str]=None)->dict:
    with engine_lock(Path(root).resolve(),exclusive=True):
        return _asset_ledger_migrate_unlocked(root,version,scope,dry_run,force,batch)

def _component_write_manifest_native(root:Path,save_version:str,parent_sid:Optional[str],migration_lineage:Optional[dict]=None,frozen_development_sources:Optional[dict]=None)->dict:
    for fn in COMPONENT_DATA_FILES+('engine.py','guard.py'):
        if not (root/fn).is_file():raise EngineError('COMPONENT_MISSING_FOR_MANIFEST:'+fn)
    old_manifest={}
    try:old_manifest=_component_manifest_read(root)
    except Exception:pass
    st=read_json(root/'state.json');gt=st.get('game_time');data_hashes=_component_data_hashes(root);tools=_component_tool_hashes(root);authority_bundle=_component_bundle_hash(data_hashes);sid=f'SAVESET-{save_version}-{authority_bundle[:16]}';all_hashes={**data_hashes,**tools};transport_bundle=_component_bundle_hash(all_hashes);cset='COMPSET-'+transport_bundle[:24]
    if migration_lineage is None:
        prior_lineage=(old_manifest.get('migration_lineage') or {}) if isinstance(old_manifest,dict) else {}
        default_layout=('native_eight_component_v4_tiered_history' if old_manifest.get('history_tiers') else
                        'native_eight_component_v3_cold_archives' if old_manifest.get('cold_archives') else 'native_eight_component_v3')
        from_layout=str(prior_lineage.get('to_layout') or default_layout)
        if not from_layout.startswith('native_eight_component_v'):from_layout=default_layout
        old_time=old_manifest.get('game_time') if isinstance(old_manifest,dict) else None
        ot=parse_iso(old_time) if isinstance(old_time,str) else None;nt=parse_iso(gt) if isinstance(gt,str) else None
        advanced=bool(ot and nt and nt>ot)
        migration_lineage={'from_save_set_id':parent_sid,'from_layout':from_layout,'to_layout':from_layout,'game_time_advanced':advanced}
    elif migration_lineage.get('engine_upgrade'):
        # The caller may be the parent Engine, which cannot know a newer layout.
        # Derive both ends from the bound parent manifest instead of a literal.
        migration_lineage=copy.deepcopy(migration_lineage)
        prior=(old_manifest.get('migration_lineage') or {}) if isinstance(old_manifest,dict) else {}
        layout=('native_eight_component_v4_tiered_history' if old_manifest.get('history_tiers') else
                'native_eight_component_v3_cold_archives' if old_manifest.get('cold_archives') else 'native_eight_component_v3')
        migration_lineage['from_layout']=str(prior.get('to_layout') or layout)
        migration_lineage['to_layout']=migration_lineage['from_layout']
    m={'schema':COMPONENT_SET_SCHEMA,'format_version':2,'save_version':save_version,'save_set_id':sid,'parent_save_set_id':parent_sid,'authority_bundle_sha256':authority_bundle,'component_set_id':cset,'component_bundle_sha256':transport_bundle,'game_time':gt,'engine_version':ENGINE_VERSION,'engine_protocol':ENGINE_PROTOCOL,'guard_version':BUNDLED_GUARD_VERSION,'guard_protocol':GUARD_PROTOCOL,'entrypoint':'guard.py','engine_entrypoint':'engine.py','components':all_hashes,'authority_components':data_hashes,'tool_bindings':tools,'component_roles':{'rules.json':'current executable and semantic rules keyed by rule_id','catalog.json':'stable templates and definitions keyed by entity_id','state.json':'current facts and deterministic runtime state','tasks.json':'tasks, triggers, authorization and pending decisions','events.jsonl':'append-only events, exact changes and narrative history','engine.py':'deterministic execution, query, validation and transaction engine','guard.py':'source validation, recovery and boot launcher'},'runtime':{'native_eight_component':True,'migration_parser':'explicit_legacy_migration_only'},'migration_lineage':migration_lineage}
    required=old_manifest.get('required_extensions') or []
    supported={'asset_policy','batch_a_maintenance','extension_registry'}
    if any(x not in supported for x in required):raise EngineError('MANIFEST_UNKNOWN_REQUIRED_EXTENSION')
    for key,value in old_manifest.items():
        if key not in m and key not in {'history_tiers','development_sources','cold_archives'}:m[key]=copy.deepcopy(value)
    if isinstance(old_manifest,dict) and old_manifest.get('cold_archives'):m['cold_archives']=copy.deepcopy(old_manifest.get('cold_archives'))
    if old_manifest.get('history_tiers'):
        cold_rows=[row for row in (m.get('cold_archives') or {}).values() if 'seq_start' in row]
        cold_events=sum(int(row['event_count']) for row in cold_rows)
        with (root/'events.jsonl').open('rb') as stream:metadata=strict_json_loads(stream.readline().decode('utf-8'))
        total=int(metadata['next_seq'])-1
        if cold_events>total:raise EngineError('HISTORY_TIER_COUNT_EXCEEDS_LOGICAL_HISTORY')
        m['history_tiers']={'schema':'VOYAGER_HISTORY_TIERS_V1','hot_path':'events.jsonl',
                            'cold_event_count':cold_events,'cold_segments':len(cold_rows),
                            'cold_range_end':max((int(row['seq_end']) for row in cold_rows),default=0),
                            'hot_event_count':total-cold_events,
                            'index_policy':'derived_locator_index_bound_to_history_sha256_and_engine_version'}
    devroot=None if frozen_development_sources is not None else os.environ.get('VOYAGER_DEV_SOURCE_DIR')
    if frozen_development_sources is not None:
        m['development_sources']=copy.deepcopy(frozen_development_sources)
    elif devroot:
        development=Path(devroot).resolve()/'development'
        if not development.is_dir():raise EngineError('DEVELOPMENT_SOURCE_DIRECTORY_MISSING')
        files={str(f.relative_to(Path(devroot).resolve())).replace(os.sep,'/'):sha256_file(f) for f in sorted(development.rglob('*')) if f.is_file() and not f.is_symlink() and '__pycache__' not in f.parts and f.suffix not in ('.pyc','.pyo') and '.runtime' not in f.parts}
        if not files:raise EngineError('DEVELOPMENT_SOURCE_EMPTY')
        m['development_sources']={'schema':'VOYAGER_DEV_SOURCES_V1','files':files,'build_command':'python3 development/build.py --output engine.py'}
    elif old_manifest.get('development_sources'):
        m['development_sources']=copy.deepcopy(old_manifest['development_sources'])
    (root/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8',newline='\n');return m



# Native staging carries a parent marker for transaction/session integrity; hidden runtime metadata is not a component.
def _v130_layer_create_stage_03(root:Path=ROOT,label:str='work')->dict:
    root=Path(root).resolve();cur=ensure_source_ready(root,allow_cache=False)
    d=root/'.runtime'/'staging';d.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix=f'.stage_{label}_',dir=d))
    for fn in COMPONENT_FILES:shutil.copy2(root/fn,stage/fn)
    marker={'format':'VOYAGER_STAGE_PARENT_V1','parent_save_set_id':cur.get('save_set_id'),'parent_version':version_text(cur.get('version')),'created_from':'native_eight_component'}
    (stage/'.PARENT.json').write_text(json.dumps(marker,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    return {'status':'READY','staging':str(stage),'base_save_set_id':cur.get('save_set_id'),'native_components':True}

_component_source_check_p0p1 = _v130_layer_component_source_check_02
def _v130_layer_component_source_check_03(root:Path=COMPONENT_ROOT,strict_fileset:bool=True)->dict:
    # strict fileset ignores hidden transaction metadata such as .PARENT.json.
    if strict_fileset and (Path(root)/'.PARENT.json').is_file():
        hidden=Path(root)/'.PARENT.json';tmp=hidden.with_name('.PARENT.json.sourcecheck_hold')
        os.replace(hidden,tmp)
        try:return _component_source_check_p0p1(root,strict_fileset=True)
        finally:os.replace(tmp,hidden)
    return _component_source_check_p0p1(root,strict_fileset)



# Session-owned stages must live directly under ROOT to satisfy the fail-closed session path contract.
def _v130_layer_create_stage_04(root:Path=ROOT,label:str='work')->dict:
    root=Path(root).resolve();cur=ensure_source_ready(root,allow_cache=False)
    if str(label).startswith('session_'):
        sid=str(label)[len('session_'):]
        stage=root/f'.stage_session_{sid}_{uuid.uuid4().hex[:8]}'
        stage.mkdir(parents=False,exist_ok=False)
    else:
        d=root/'.runtime'/'staging';d.mkdir(parents=True,exist_ok=True)
        stage=Path(tempfile.mkdtemp(prefix=f'.stage_{label}_',dir=d))
    for fn in COMPONENT_FILES:shutil.copy2(root/fn,stage/fn)
    marker={'format':'VOYAGER_STAGE_PARENT_V1','parent_save_set_id':cur.get('save_set_id'),'parent_version':version_text(cur.get('version')),'created_from':'native_eight_component'}
    (stage/'.PARENT.json').write_text(json.dumps(marker,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    return {'status':'READY','staging':str(stage),'base_save_set_id':cur.get('save_set_id'),'parent':cur.get('save_set_id'),'native_components':True}



def latest_valid_snapshot(root:Path=ROOT,verify_parent:bool=True)->dict:
    a=validate_authority_set(Path(root))
    if not a:raise EngineError('NO_COMMITTED_COMPONENT_AUTHORITY')
    return {'dir':Path(root),'version':a['version'],'save_set_id':a['save_set_id'],'bundle':a['bundle'],'manifest':a['manifest'],'index':a['index'],'index_sha256':a['index_sha256'],'commit':{'parent_save_set_id':a['index'].get('parent_save_set_id'),'save_set_id':a['save_set_id']}}


def create_stage(root:Path=ROOT,label:str='work')->dict:
    root=Path(root).resolve();cur=ensure_source_ready(root,allow_cache=False)
    if str(label).startswith('session_'):
        sid=str(label)[len('session_'):]
        stage=root/f'.stage_session_{sid}_{uuid.uuid4().hex[:8]}'
        stage.mkdir(parents=False,exist_ok=False)
    else:
        d=root/'.runtime'/'staging';d.mkdir(parents=True,exist_ok=True)
        stage=Path(tempfile.mkdtemp(prefix=f'.stage_{label}_',dir=d))
    for fn in COMPONENT_FILES:shutil.copy2(root/fn,stage/fn)
    _copy_declared_cold_archives(root,stage,cur.get('component_manifest') or _component_manifest_read(root))
    marker={'format':'VOYAGER_STAGE_PARENT_V1','parent_save_set_id':cur.get('save_set_id'),'parent_version':version_text(cur.get('version')),'parent_bundle_sha256':cur.get('bundle'),'parent_index_sha256':cur.get('index_sha256'),'parent_file_sha256':{fn:sha256_file(root/fn) for fn in COMPONENT_FILES}}
    (stage/'.PARENT.json').write_text(json.dumps(marker,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    return {'status':'READY','staging':str(stage),'base_save_set_id':cur.get('save_set_id'),'parent':cur.get('save_set_id'),'native_components':True}



# Final strict sourcecheck: hidden transaction/session metadata is outside the eight-component fileset.
# Identical checked body retained once; historical public capture name remains.
_v130_layer_component_source_check_04=_v130_layer_component_source_check_02



def _current_ref_string(s:str)->str:
    if s.startswith(('STATE.','state:')):return 'state:'+s[6:]
    if s.startswith(('TASKS.','tasks:')):return 'tasks:'+s[6:]
    if s.startswith('WORLD:'):return 'rules:'+s[6:]
    if s.startswith('HISTORY:'):return 'events:'+s[8:]
    if s.startswith('INDEX:'):return 'manifest:'+s[6:]
    return s


def _normalize_current_refs_obj(x):
    if isinstance(x,dict):return {k:_normalize_current_refs_obj(v) for k,v in x.items()}
    if isinstance(x,list):return [_normalize_current_refs_obj(v) for v in x]
    if isinstance(x,str):return _current_ref_string(x)
    return x

_apply_domain_command_native_p0p1=_v130_layer__apply_domain_command_02
def _apply_domain_command_v1408(stage:Path,state:dict,tasks:dict,payload:dict)->dict:
    return _normalize_current_refs_obj(_apply_domain_command_native_p0p1(stage,state,tasks,payload))


def _event_change_target_prefixes(events: List[dict]) -> set:
    out=set();role={'state':'STATE','tasks':'TASKS','rules':'WORLD','catalog':'CATALOG','events':'HISTORY','manifest':'INDEX'}
    def one(ch):
        if not isinstance(ch,dict):return
        t=ch.get('target')
        if not isinstance(t,str) or not t.strip():return
        raw=t.strip();head=re.split(r'[:./]',raw,maxsplit=1)[0];out.add(role.get(head.lower(),head.upper()))
    for e in events:
        changes=e.get('changes') if isinstance(e,dict) else None
        if isinstance(changes,list):
            for ch in changes:one(ch)
        elif isinstance(changes,dict):one(changes)
    return out


def _event_targets_by_domain(events: List[dict]) -> Dict[str,List[str]]:
    out={'WORLD':[],'STATE':[],'TASKS':[],'CATALOG':[],'HISTORY':[],'INDEX':[]};role={'state':'STATE','tasks':'TASKS','rules':'WORLD','catalog':'CATALOG','events':'HISTORY','manifest':'INDEX'}
    def one(ch):
        if not isinstance(ch,dict):return
        t=ch.get('target')
        if not isinstance(t,str) or not t.strip():return
        raw=t.strip();head=re.split(r'[:./]',raw,maxsplit=1)[0];dom=role.get(head.lower(),head.upper())
        if dom not in out:return
        rest=raw[len(head):].lstrip(':./').replace('.','/')
        out[dom].append('/'+rest if rest else '')
    for e in events:
        changes=e.get('changes') if isinstance(e,dict) else None
        if isinstance(changes,list):
            for ch in changes:one(ch)
        elif isinstance(changes,dict):one(changes)
    return out


def evidence_packet(base,source,path,offset=0,limit=4000):
    ready=ensure_source_ready(base)
    if not isinstance(offset,int) or offset<0 or not 1<=limit<=16000:raise EngineError('EVIDENCE_PAGE_INVALID')
    source=str(source).lower();resolved=path
    if source=='state':
        state=read_json(base/'state.json');resolved=resolve_state_ref(state,path.removeprefix('state:').removeprefix('STATE.'));value=get_by_path(state,resolved);raw=json.dumps(value,ensure_ascii=False,separators=(',',':'))
    elif source=='rules':
        rid=path.removeprefix('rules:');rec=resolve_rule_registry(base,rid)
        raw=json.dumps(rec,ensure_ascii=False,separators=(',',':'));resolved=rid
    elif source=='catalog':
        cat=read_json(base/'catalog.json');eid=path.removeprefix('catalog:');rec=((cat.get('catalog_registry') or {}).get('entities') or {}).get(eid)
        if rec is None:raise EngineError('EVIDENCE_ENTITY_NOT_FOUND:'+eid)
        raw=json.dumps(rec,ensure_ascii=False,separators=(',',':'));resolved=eid
    elif source=='manifest':
        man=read_json(base/'manifest.json');key=path.removeprefix('manifest:');value=get_by_path(man,key) if key else man;raw=json.dumps(value,ensure_ascii=False,separators=(',',':'));resolved=key
    elif source=='events':
        meta,events,_=read_history_view(base/'events.jsonl');needle=path.removeprefix('events:');rows=[]
        for e in events:
            if str(e.get('event_id'))==needle or str(e.get('command_id'))==needle or needle in json.dumps(e,ensure_ascii=False):rows.append(e)
        raw=json.dumps(rows,ensure_ascii=False,separators=(',',':'));resolved=needle
    else:raise EngineError('EVIDENCE_SOURCE_INVALID')
    end=min(len(raw),offset+limit)
    return {'packet':'EVIDENCE_PAGE_V2','save_set_id':ready.get('save_set_id'),'source':source,'path':resolved,'offset':offset,'text':raw[offset:end],'total_chars':len(raw),'next_offset':end if end<len(raw) else None,'status':'TRUNCATED' if end<len(raw) else 'COMPLETE','usage':'Pages are slices of one bound eight-component source.'}


def _public_json_safe(value:Any)->Any:
    if isinstance(value,Path):return str(value)
    if isinstance(value,dict):return {str(k):_public_json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_public_json_safe(v) for v in value]
    if isinstance(value,set):return [_public_json_safe(v) for v in sorted(value,key=lambda x:str(x))]
    return value


def _component_post_command_sync(cmd:str,result:Any)->Any:
    return _public_json_safe(_normalize_current_refs_obj(result))



_component_source_check_p2_final_base=_v130_layer_component_source_check_04
def _v130_layer_component_source_check_05(root:Path=COMPONENT_ROOT,strict_fileset:bool=True)->dict:
    out=_component_source_check_p2_final_base(root,strict_fileset)
    if out.get('status')=='PASS':
        ri=reference_integrity_packet(Path(root));out['reference_integrity']=ri
        if ri.get('status')!='PASS':
            out['status']='FAIL';out.setdefault('errors',[]).extend('REFERENCE:'+x for x in ri.get('errors',[]))
    return out



# === PHASE1 VALIDATION / REGRESSION HARDENING v1 ===
# V13.0 structural consolidation: historical patch layers have explicit internal names.
# Public entry points below are unique; compatibility layers are called explicitly rather
# than relying on later same-name definitions to overwrite earlier implementations.

_component_source_check_phase1_base = _v130_layer_component_source_check_05
_run_checks_phase1_base = _v130_layer_run_checks_01
_native_component_selftest_phase1_base = _v130_layer_native_component_selftest_01


def _phase1_manifest_protocol_report(root:Path)->dict:
    root=Path(root).resolve();errors=[]
    try:m=_component_manifest_read(root)
    except Exception as ex:
        return {'status':'FAIL','errors':['MANIFEST:'+str(ex)],'root':str(root)}
    if str(m.get('engine_protocol')) != str(ENGINE_PROTOCOL):
        errors.append(f'ENGINE_PROTOCOL_MISMATCH:manifest={m.get("engine_protocol")}:runtime={ENGINE_PROTOCOL}')
    if str(m.get('engine_version')) != str(ENGINE_VERSION):
        errors.append(f'ENGINE_VERSION_MISMATCH:manifest={m.get("engine_version")}:runtime={ENGINE_VERSION}')
    if str(m.get('guard_protocol')) != str(GUARD_PROTOCOL):
        errors.append(f'GUARD_PROTOCOL_MISMATCH:manifest={m.get("guard_protocol")}:bound={GUARD_PROTOCOL}')
    if str(m.get('guard_version')) != str(BUNDLED_GUARD_VERSION):
        errors.append(f'GUARD_VERSION_MISMATCH:manifest={m.get("guard_version")}:bound={BUNDLED_GUARD_VERSION}')
    return {'status':'FAIL' if errors else 'PASS','errors':errors,'root':str(root),
            'engine_version':ENGINE_VERSION,'engine_protocol':ENGINE_PROTOCOL,
            'manifest_engine_version':m.get('engine_version'),'manifest_engine_protocol':m.get('engine_protocol')}


def _history_epoch_runtime_facts(root:Path)->dict:
    ep=Path(root)/'events.jsonl';epochs=0;raw_count=0;raw_bytes=0
    with ep.open('rb') as fh:
        first=fh.readline();meta=strict_json_loads(first.decode('utf-8'));logical=max(0,int(meta.get('next_seq') or 1)-1)
        for raw in fh:
            raw=raw.rstrip(b'\r\n')
            if not raw.strip():continue
            if b'\"record_type\":\"history_epoch\"' in raw:epochs+=1
            else:raw_count+=1;raw_bytes+=len(raw)+1
    if epochs:
        recommended=(raw_count>HISTORY_EPOCH_KEEP_RECENT or (raw_count>HISTORY_EPOCH_MIN_RECENT and raw_bytes>HISTORY_EPOCH_RECENT_BYTE_BUDGET))
    else:
        recommended=(logical>=HISTORY_EPOCH_EVENT_THRESHOLD or ep.stat().st_size>=HISTORY_EPOCH_BYTE_THRESHOLD)
    return {'compression_recommended':bool(recommended),'compression_applied':bool(epochs),'physical_epoch_records':epochs,'logical_event_count':logical,'raw_recent_event_count':raw_count,'raw_recent_bytes':raw_bytes}

def _sync_current_scaling_status(root:Path)->dict:
    root=Path(root);state=read_json(root/'state.json');sc=((state.setdefault('engine_runtime',{})).setdefault('scaling',{}));facts=_history_epoch_runtime_facts(root)
    hs=sc.setdefault('history_epoch',{});hs['event_threshold']=HISTORY_EPOCH_EVENT_THRESHOLD;hs['byte_threshold']=HISTORY_EPOCH_BYTE_THRESHOLD;hs['status_schema']='HISTORY_EPOCH_STATUS_V2';hs['compression_recommended']=facts['compression_recommended'];hs['compression_applied']=facts['compression_applied'];hs['status_source']='engine:historystatus'
    ledger=state.get('asset_ledger_v1');reg=((state.get('engine_runtime') or {}).get('asset_mapping_registry') or {});als=sc.setdefault('asset_ledger',{});als['schema']='ASSET_LEDGER_V1';als['mapping_registry_schema']=reg.get('schema') or ASSET_MAPPING_REGISTRY_SCHEMA;als['activation_status']='ACTIVE_SPARSE_WITH_EXCLUSIONS' if isinstance(ledger,dict) else 'NOT_ACTIVE';als['migration_scope']='only explicitly migrated registry entries are ledger assets; excluded legacy current fields remain authoritative'
    comps=_component_manifest_read(root).get('components') or {};sc['authority_file_count']=len(comps);sc['core_save_file_count']=1+len(comps);sc['authority_file_count_semantics']='hash_checked components excluding manifest.json'
    _write_authority_json(root/'state.json',state);return facts

def _shadow_patrol_single_event_report(state:dict,tasks:dict)->dict:
    """The dossier owns the open event; task and deployment may only refer to it."""
    errors=[];task_id='TSK-SHADOW-XIANYUE-ASTEROID-PATROL'
    found=[t for t in tasks.get('active_tasks',[]) if isinstance(t,dict) and t.get('task_id')==task_id]
    dossier=(((state.get('world_state_overrides') or {}).get('intelligence_and_security') or {}).get('xianyue_asteroid_shadow_patrol_current') or {})
    group=(((state.get('shadow_fleet') or {}).get('quick_reaction_force_current') or {}).get('deployed_group_current') or {})
    if len(found)!=1:errors.append('PATROL_TASK_COUNT:'+str(len(found)))
    if not isinstance(dossier,dict) or not dossier:errors.append('PATROL_DOSSIER_MISSING')
    if not isinstance(group,dict) or not group:errors.append('PATROL_GROUP_MISSING')
    if errors:return {'status':'FAIL','errors':errors}
    task=found[0];data=task.get('task_data') or {};slot=dossier.get('current_local_event');task_event_id=data.get('current_event_id')
    if slot is None:
        if task_event_id is not None:errors.append('PATROL_TASK_EVENT_WITHOUT_DOSSIER_EVENT')
        if data.get('current_event_state_path') is not None:errors.append('PATROL_EVENT_PATH_WITHOUT_DOSSIER_EVENT')
        if data.get('current_event_stage') is not None:errors.append('PATROL_EVENT_STAGE_WITHOUT_DOSSIER_EVENT')
        if data.get('slot_status')!='empty' or data.get('scene_id') is not None:errors.append('PATROL_TASK_PHASE_EXPECTS_OPEN_EVENT')
        if dossier.get('slot_status')!='empty' or dossier.get('scene_id') is not None:errors.append('PATROL_DOSSIER_SLOT_NOT_RELEASED')
    else:
        if not isinstance(slot,dict) or not isinstance(slot.get('event_id'),str) or not slot.get('event_id'):
            errors.append('PATROL_DOSSIER_EVENT_ID_MISSING')
        else:
            if task_event_id!=slot['event_id']:errors.append('PATROL_TASK_EVENT_ID_MISMATCH')
            if data.get('current_event_state_path')!='world_state_overrides.intelligence_and_security.xianyue_asteroid_shadow_patrol_current.current_local_event':
                errors.append('PATROL_TASK_EVENT_PATH_MISMATCH')
            # An open event has one stage, owned by the dossier and referenced by TASKS.
            event_stage=slot.get('phase') or slot.get('status')
            if not isinstance(event_stage,str) or not event_stage or data.get('current_event_stage')!=event_stage:
                errors.append('PATROL_TASK_EVENT_STAGE_MISMATCH')
        if 'closed' in str(slot.get('status') or '').lower():errors.append('PATROL_CLOSED_EVENT_IN_OPEN_SLOT')
        if 'closed' in str(slot.get('phase') or '').lower():errors.append('PATROL_CLOSED_EVENT_IN_OPEN_SLOT')
        if data.get('slot_status')=='empty' or dossier.get('slot_status')=='empty':
            errors.append('PATROL_OPEN_EVENT_REPORTED_CLOSED')
    for key in ('current_event','last_event_closeout','last_event_redeployment'):
        if key in group:errors.append('PATROL_DUPLICATE_GROUP_EVENT_FIELD:'+key)
    if 'current_assignment' in dossier:errors.append('PATROL_DUPLICATE_DOSSIER_ASSIGNMENT')
    return {'status':'FAIL' if errors else 'PASS','errors':errors,'task_id':task_id,
            'open_event_id':slot.get('event_id') if isinstance(slot,dict) else None}

def _current_authority_consistency_report(root:Path)->dict:
    root=Path(root).resolve();errors=[];facts={}
    try:
        state=read_json_view(root/'state.json');tasks=read_json_view(root/'tasks.json');manifest=read_json_view(root/'manifest.json')
        if parse_version(str(manifest.get('save_version'))) >= (14,2):
            patrol=_shadow_patrol_single_event_report(state,tasks);facts['shadow_patrol_event']=patrol
            errors.extend(patrol.get('errors') or [])
        auto=tasks.get('automation_schema') or {};sc=((state.get('engine_runtime') or {}).get('scaling') or {})
        if auto.get('cold_start_packet')!=COLD_START_PACKET_SCHEMA:errors.append(f'TASK_COLD_START_SCHEMA:{auto.get("cold_start_packet")}!={COLD_START_PACKET_SCHEMA}')
        if auto.get('asset_mapping_registry_schema')!=ASSET_MAPPING_REGISTRY_SCHEMA:errors.append(f'TASK_ASSET_MAPPING_SCHEMA:{auto.get("asset_mapping_registry_schema")}!={ASSET_MAPPING_REGISTRY_SCHEMA}')
        comps=manifest.get('components') or {};facts['core_save_files']=1+len(comps);facts['hash_checked_components']=len(comps)
        if len(comps)!=7:errors.append(f'MANIFEST_COMPONENT_COUNT:{len(comps)}!=7')
        if int(sc.get('authority_file_count',-1))!=len(comps):errors.append(f'AUTHORITY_FILE_COUNT:{sc.get("authority_file_count")}!={len(comps)}')
        if int(sc.get('core_save_file_count',-1))!=1+len(comps):errors.append(f'CORE_SAVE_FILE_COUNT:{sc.get("core_save_file_count")}!={1+len(comps)}')
        acct=get_by_path(state,CALDER_552_CANONICAL_PATH);facts['industry']={k:acct.get(k) for k in ('asset_count','daily_net_income_gold','daily_net_income_grey','next_settlement_at')}
        if not isinstance(acct.get('asset_count'),int) or acct.get('asset_count',-1)<0:errors.append('INDUSTRY_ASSET_COUNT_INVALID')
        for k in ('daily_net_income_gold','daily_net_income_grey'):
            if not isinstance(acct.get(k),(int,float)) or isinstance(acct.get(k),bool):errors.append('INDUSTRY_INCOME_INVALID:'+k)
        active=[x for x in tasks.get('active_tasks',[]) if x.get('task_id')=='TSK-CALDER-INDUSTRIES-302']
        if len(active)!=1:errors.append(f'INDUSTRY_TASK_COUNT:{len(active)}')
        else:
            task=active[0];sr=((task.get('runtime_policy') or {}).get('settlement_rule') or {});amounts=sr.get('amounts') or {};tv=sr.get('template_vars') or {}
            if ((amounts.get('gold') or {}).get('from'))!='state:'+CALDER_552_CANONICAL_PATH+'.daily_net_income_gold':errors.append('INDUSTRY_GOLD_NOT_AUTHORITY_REF')
            if ((amounts.get('grey') or {}).get('from'))!='state:'+CALDER_552_CANONICAL_PATH+'.daily_net_income_grey':errors.append('INDUSTRY_GREY_NOT_AUTHORITY_REF')
            if ((tv.get('asset_count') or {}).get('from'))!='state:'+CALDER_552_CANONICAL_PATH+'.asset_count':errors.append('INDUSTRY_COUNT_NOT_AUTHORITY_REF')
            td=task.get('task_data') or {}
            if any(k in td for k in ('asset_count','daily_net_income_gold','daily_net_income_grey','daily_gold','daily_grey')):errors.append('INDUSTRY_TASK_DUPLICATE_CURRENT_FACTS')
        econ=((state.get('world_state_overrides') or {}).get('current_handoff_snapshot') or {}).get('economy') or {}
        if any(k in econ for k in ('multinational_assets','multinational_daily_gold','multinational_daily_grey','multinational_next')):errors.append('INDUSTRY_HANDOFF_DUPLICATE_CURRENT_FACTS')
        if econ.get('multinational_industry_ref')!='state:'+CALDER_552_CANONICAL_PATH:errors.append('INDUSTRY_HANDOFF_REF_MISSING')
        reg=((state.get('engine_runtime') or {}).get('asset_mapping_registry') or {});ledger=state.get('asset_ledger_v1') or {}
        mig=[x for x in reg.get('migrated_entries',[]) if isinstance(x,dict)];exc=[x for x in reg.get('excluded_entries',[]) if isinstance(x,dict)]
        facts['asset_mapping']={'schema':reg.get('schema'),'entry_count':reg.get('entry_count'),'migrated':len(mig),'excluded':len(exc),'ledger_active':isinstance(state.get('asset_ledger_v1'),dict)}
        if reg.get('schema')!=ASSET_MAPPING_REGISTRY_SCHEMA:errors.append('ASSET_MAPPING_REGISTRY_SCHEMA')
        if reg.get('entry_count')!=len(mig)+len(exc):errors.append('ASSET_MAPPING_REGISTRY_PARTITION')
        if not isinstance(state.get('asset_ledger_v1'),dict) or ledger.get('schema')!='ASSET_LEDGER_V1':errors.append('ASSET_LEDGER_NOT_ACTIVE')
        if 'ACTIVE' not in str(state.get('inventory_authority_mode') or ''):errors.append('ASSET_LEDGER_AUTHORITY_MODE')
        hs=sc.get('history_epoch') or {};hf=_history_epoch_runtime_facts(root);facts['history_epoch']=hf
        if bool(hs.get('compression_applied'))!=bool(hf.get('compression_applied')):errors.append('HISTORY_COMPRESSION_APPLIED_STATE_MISMATCH')
        if bool(hs.get('compression_recommended'))!=bool(hf.get('compression_recommended')):errors.append('HISTORY_COMPRESSION_RECOMMENDED_STATE_MISMATCH')
        # Current explanatory state may mention 552 only when explicitly marked historical; old 576/652 totals are never current facts.
        cal=(((state.get('world_state_overrides') or {}).get('organizations_and_politics') or {}).get('nation_dynamics') or {}).get('卡尔德自由邦') or {}
        current_text=json.dumps(cal,ensure_ascii=False)
        if '576项产业' in current_text or '652项产业' in current_text or '576-asset' in current_text or '652 assets' in current_text:errors.append('STALE_CURRENT_INDUSTRY_TOTAL')
        if '552项产业' in current_text and not any(x in current_text for x in ('当时','历史记录')):errors.append('LEGACY_552_NOT_HISTORICALLY_QUALIFIED')
    except Exception as ex:errors.append('CONSISTENCY_EXCEPTION:'+type(ex).__name__+':'+str(ex))
    return {'status':'PASS' if not errors else 'FAIL','errors':errors,'facts':facts}

def component_source_check(root:Path=COMPONENT_ROOT,strict_fileset:bool=True)->dict:
    root=Path(root).resolve()
    out=_component_source_check_phase1_base(root,strict_fileset)
    out['checked_root']=str(root)
    errors=list(out.get('errors') or [])
    warnings=list(out.get('warnings') or [])
    if (root/'manifest.json').is_file():
        pr=_phase1_manifest_protocol_report(root);out['protocol_binding']=pr
        errors.extend('PROTOCOL:'+x for x in pr.get('errors',[]))
        try:
            ri=out.get('reference_integrity') or reference_integrity_packet(root)
            out['reference_integrity']=ri
            errors.extend('REFERENCE:'+x for x in (ri.get('errors') or []) if 'REFERENCE:'+x not in errors)
            warnings.extend('REFERENCE:'+x for x in (ri.get('warnings') or []))
            cc=_current_authority_consistency_report(root);out['current_authority_consistency']=cc
            errors.extend('CURRENT_CONSISTENCY:'+x for x in (cc.get('errors') or []))
        except Exception as ex:
            errors.append('REFERENCE_CHECK_EXCEPTION:'+type(ex).__name__+':'+str(ex))
    else:
        if not any(str(x).startswith('MANIFEST') for x in errors):errors.append('MANIFEST_MISSING')
    out['errors']=sorted(set(errors));out['warnings']=sorted(set(warnings))
    out['error_count']=len(out['errors']);out['warning_count']=len(out['warnings'])
    out['status']='FAIL' if out['errors'] else 'PASS'
    return out


def run_checks_v1408(base: Path, full: bool = False, expected_version: Optional[str] = None,
               require_manifest: bool = True, parent_snapshot: Optional[dict] = None,
               validation_cache: Optional[dict] = None) -> dict:
    out=_run_checks_phase1_base(base,full,expected_version,require_manifest,parent_snapshot,validation_cache)
    base=Path(base).resolve()
    errors=list(out.get('errors') or []);warnings=list(out.get('warnings') or [])
    if require_manifest and parent_snapshot and (parent_snapshot.get('dir') is not None):
        try:
            parent=Path(parent_snapshot['dir']).resolve()
            if (base/'manifest.json').is_file() and parse_version(str(read_json(base/'manifest.json').get('save_version'))) >= (14,2):
                def patrol_slot(path):
                    state=read_json(path/'state.json')
                    return (((state.get('world_state_overrides') or {}).get('intelligence_and_security') or {}).get('xianyue_asteroid_shadow_patrol_current') or {}).get('current_local_event')
                before_slot=patrol_slot(parent);after_slot=patrol_slot(base)
                before_id=before_slot.get('event_id') if isinstance(before_slot,dict) else None
                after_id=after_slot.get('event_id') if isinstance(after_slot,dict) else None
                if before_id and after_id!=before_id and after_id is not None:
                    errors.append('PATROL_CLOSEOUT_MUST_RELEASE_SLOT_AND_STOP')
            pair=_history_read_pair_incremental(parent/'events.jsonl',base/'events.jsonl',validation_cache)
            newer=pair['current'][1][len(pair['parent'][1]):]
            if any(e.get('event_schema')=='EVENT_V3' for e in newer):
                changed={fn for fn,v in _substantive_parent_change(parent,base).items() if v}
                if changed:
                    proofs=[e for e in newer if e.get('type')=='transaction_changeset' and e.get('event_schema')=='EVENT_V3']
                    if len(proofs)!=1:errors.append('EVENT_V3_TRANSACTION_PROOF_COUNT')
                    else:
                        proof=proofs[0];actual=_event_v3_field_changes(parent,base,changed)
                        if proof.get('field_changes')!=actual or proof.get('audit_completeness')!='COMPLETE':
                            errors.append('EVENT_V3_FIELD_DIFF_MISMATCH')
                        for fn,label in (('state.json','state'),('tasks.json','tasks'),('rules.json','rules'),('catalog.json','catalog')):
                            if proof.get('parent_'+label+'_sha256')!=sha256_file(parent/fn) or proof.get('result_'+label+'_sha256')!=sha256_file(base/fn):
                                errors.append('EVENT_V3_AUTHORITY_HASH_MISMATCH:'+fn)
        except Exception as ex:errors.append('EVENT_V3_VALIDATION_EXCEPTION:'+type(ex).__name__+':'+str(ex))
    if (base/'manifest.json').is_file():
        pr=_phase1_manifest_protocol_report(base)
        errors.extend('PROTOCOL:'+x for x in pr.get('errors',[]))
        try:
            ri=reference_integrity_packet(base)
            errors.extend('REFERENCE:'+x for x in ri.get('errors',[]))
            warnings.extend('REFERENCE:'+x for x in ri.get('warnings',[]))
            out['reference_integrity']=ri
            cc=_current_authority_consistency_report(base);out['current_authority_consistency']=cc
            errors.extend('CURRENT_CONSISTENCY:'+x for x in (cc.get('errors') or []))
        except Exception as ex:
            errors.append('REFERENCE_CHECK_EXCEPTION:'+type(ex).__name__+':'+str(ex))
    sr=_v130_ast_structure_report(Path(__file__).resolve()) if '_v130_ast_structure_report' in globals() else {'status':'PASS','errors':[]}
    vb=_v130_version_binding_report(base) if '_v130_version_binding_report' in globals() and (base/'manifest.json').is_file() else {'status':'PASS','errors':[]}
    out['ast_structure']=sr;out['version_binding']=vb
    errors.extend('STRUCTURE:'+x for x in sr.get('errors',[]));errors.extend('VERSION_BINDING:'+x for x in vb.get('errors',[]))
    out['errors']=sorted(set(errors));out['warnings']=sorted(set(warnings))
    out['error_count']=len(out['errors']);out['warning_count']=len(out['warnings'])
    out['status']='FAIL' if out['errors'] else 'PASS'
    return out


def _phase1_asset_registry_regressions(root:Path)->list:
    rows=[]
    try:
        state=read_json(root/'state.json');reg=((state.get('engine_runtime') or {}).get('asset_mapping_registry') or {});ledger=state.get('asset_ledger_v1') or {}
        mig=[x for x in (reg.get('migrated_entries') or []) if isinstance(x,dict)];exc=[x for x in (reg.get('excluded_entries') or []) if isinstance(x,dict)]
        rows.append(('asset_registry_schema',reg.get('schema')==ASSET_MAPPING_REGISTRY_SCHEMA,str(reg.get('schema'))))
        rows.append(('asset_registry_entry_count',reg.get('entry_count')==len(mig)+len(exc),f"declared={reg.get('entry_count')} actual={len(mig)+len(exc)}"))
        rows.append(('asset_registry_partition_counts',reg.get('migrated_entry_count')==len(mig) and reg.get('excluded_entry_count')==len(exc),f'migrated={len(mig)} excluded={len(exc)}'))
        bad_exc=[x for x in exc if set(x)!={'source_path','reason_code'} or not x.get('source_path') or not x.get('reason_code')]
        rows.append(('asset_registry_exclusions_compact',not bad_exc,f'bad={len(bad_exc)}'))
        paths=[str(x.get('source_path')) for x in mig+exc];rows.append(('asset_registry_source_paths_unique',len(paths)==len(set(paths)),f'paths={len(paths)} unique={len(set(paths))}'))
        ledger_pairs=set()
        for aid,rec in (ledger.get('assets') or {}).items():
            for p in rec.get('source_paths') or []:ledger_pairs.add((str(p),str(aid)))
        mig_pairs={(str(x.get('source_path')),str(x.get('asset_id'))) for x in mig}
        rows.append(('asset_registry_migrated_matches_ledger',mig_pairs==ledger_pairs,f'registry={len(mig_pairs)} ledger={len(ledger_pairs)}'))
        required={'source_path','asset_id','semantic_type','field_role','owner_ref','location_ref','container_ref','owner_mapping_status','location_mapping_status','container_mapping_status','migration_batch_id','migration_status','asset_domain'}
        bad_m=[x.get('source_path') for x in mig if not required.issubset(x) or x.get('semantic_type')!='quantity']
        rows.append(('asset_registry_migrated_fields_complete',not bad_m,f'bad={len(bad_m)}'))
        archive=reg.get('review_archive') or {};rows.append(('asset_registry_review_archive_bound',isinstance(archive,dict) and len(str(archive.get('file_sha256') or ''))==64 and len(str(archive.get('payload_sha256') or ''))==64,str(archive.get('path'))))
    except Exception as ex:rows.append(('asset_registry_regression_exception',False,f'{type(ex).__name__}:{ex}'))
    return rows

def _v130_layer_native_component_selftest_02(root:Path=ROOT)->dict:
    root=Path(root).resolve();groups={};all_tests=[]
    def add(group,name,ok,detail=None):
        rec={'name':name,'status':'PASS' if ok else 'FAIL','detail':detail};groups.setdefault(group,[]).append(rec);all_tests.append(rec)
    # Protocol/root/sourcecheck hard gates.
    sc=component_source_check(root,strict_fileset=False)
    add('protocol_and_sourcecheck','sourcecheck_runtime',sc.get('status')=='PASS',{'errors':sc.get('errors'),'root':sc.get('checked_root')})
    pr=_phase1_manifest_protocol_report(root)
    add('protocol_and_sourcecheck','manifest_engine_protocol_matches_runtime',pr.get('status')=='PASS',pr)
    add('protocol_and_sourcecheck','resolved_root_is_requested_root',Path(sc.get('checked_root','')).resolve()==root,str(sc.get('checked_root')))
    # Explicit --base must win over VOYAGER_ROOT. Exercise the real CLI in a subprocess.
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_bad_base_') as td:
            missing=Path(td)/'missing';env=os.environ.copy();env['VOYAGER_ROOT']=str(root)
            cp=subprocess.run([sys.executable,str(Path(__file__).resolve()),'sourcecheck','--base',str(missing),'--mode','project'],env=env,text=True,capture_output=True,timeout=20)
            try:payload=json.loads(cp.stdout)
            except Exception:payload={}
            add('protocol_and_sourcecheck','sourcecheck_explicit_base_precedence',cp.returncode!=0 and payload.get('status')=='FAIL',{'returncode':cp.returncode,'stdout':cp.stdout[-500:]})
    except Exception as ex:add('protocol_and_sourcecheck','sourcecheck_explicit_base_precedence',False,str(ex))
    # Strict native fileset must reject a legacy top-level artifact.
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_strict_fileset_') as td:
            tr=Path(td)
            for fn in COMPONENT_FILES:shutil.copy2(root/fn,tr/fn)
            (tr/'WORLD.md').write_text('legacy',encoding='utf-8')
            bad=component_source_check(tr,strict_fileset=True)
            add('protocol_and_sourcecheck','strict_fileset_rejects_legacy_toplevel',bad.get('status')=='FAIL' and any('UNEXPECTED_TOPLEVEL' in x for x in bad.get('errors',[])),bad.get('errors'))
    except Exception as ex:add('protocol_and_sourcecheck','strict_fileset_rejects_legacy_toplevel',False,str(ex))
    # A mismatched manifest protocol must be rejected by sourcecheck.
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_protocol_mismatch_') as td:
            tr=Path(td)
            for fn in COMPONENT_FILES:shutil.copy2(root/fn,tr/fn)
            _copy_declared_cold_archives(root,tr,_component_manifest_read(root))
            mm=_component_manifest_read(tr);mm['engine_protocol']='999';(tr/'manifest.json').write_text(json.dumps(mm,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
            bad=component_source_check(tr,strict_fileset=True)
            add('protocol_and_sourcecheck','protocol_mismatch_is_hard_failure',bad.get('status')=='FAIL' and any('ENGINE_PROTOCOL_MISMATCH' in x for x in bad.get('errors',[])),bad.get('errors'))
    except Exception as ex:add('protocol_and_sourcecheck','protocol_mismatch_is_hard_failure',False,str(ex))
    # A legacy-only directory is not a normal sourcecheck target anymore.
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_legacy_only_') as td:
            tr=Path(td);(tr/'WORLD.md').write_text('legacy',encoding='utf-8');(tr/'STATE.json').write_text('{}',encoding='utf-8')
            bad=component_source_check(tr,strict_fileset=True)
            add('protocol_and_sourcecheck','legacy_only_layout_not_normal_source',bad.get('status')=='FAIL' and any('MANIFEST' in x for x in bad.get('errors',[])),bad.get('errors'))
    except Exception as ex:add('protocol_and_sourcecheck','legacy_only_layout_not_normal_source',False,str(ex))
    # Asset semantics regressions replace old hard-coded historical counts.
    for name,ok,detail in _phase1_asset_registry_regressions(root):add('asset_registry',name,ok,detail)
    # Native functional smoke remains, but its individual tests are exposed rather than hidden behind 11/11.
    try:
        old=_native_component_selftest_phase1_base(root)
        for rec in old.get('tests') or []:
            # The old classifier-count test is diagnostic only; current registry gates above are authoritative.
            if rec.get('name')=='asset_semantic_map_v2':continue
            add('native_smoke','smoke:'+str(rec.get('name')),rec.get('status')=='PASS',rec.get('detail'))
    except Exception as ex:add('native_smoke','legacy_native_smoke_wrapper',False,f'{type(ex).__name__}:{ex}')
    # P0/P1/P2 regression invariants already claimed fixed in previous releases.
    try:
        m=_component_manifest_read(root);state=read_json(root/'state.json');tasks=read_json(root/'tasks.json');rules=read_json(root/'rules.json');catalog=read_json(root/'catalog.json');meta,events,_=read_history_view(root/'events.jsonl')
        add('release_regressions','manifest_is_only_current_version_authority',all('save_version' not in d for d in (state,tasks,rules,catalog,meta) if isinstance(d,dict)),m.get('save_version'))
        blob=json.dumps({'state':state,'tasks':tasks},ensure_ascii=False)
        add('release_regressions','legacy_compat_current_flags_absent','legacy_runtime_view' not in blob and 'legacy_compat' not in blob,None)
        cs=cold_start_packet(root);add('release_regressions','cold_start_budget',int(cs.get('context_bytes') or 10**9)<=3500,cs.get('context_bytes'))
        add('release_regressions','native_eight_component_manifest',bool((m.get('runtime') or {}).get('native_eight_component')) and len(m.get('components') or {})==7,{'components':len(m.get('components') or {})})
        ri=sc.get('reference_integrity') or {};expected_warn=len(ri.get('warnings') or [])
        add('release_regressions','warning_aggregation_matches_reference_graph',sc.get('warning_count')==expected_warn,{'sourcecheck':sc.get('warning_count'),'reference':expected_warn})
    except Exception as ex:add('release_regressions','release_regression_exception',False,f'{type(ex).__name__}:{ex}')
    failed=[x for x in all_tests if x['status']!='PASS']
    group_summary={g:{'passed':sum(x['status']=='PASS' for x in rs),'failed':sum(x['status']!='PASS' for x in rs),'total':len(rs)} for g,rs in groups.items()}
    warnings=list(sc.get('warnings') or [])
    return {'packet':'NATIVE_REGRESSION_SUITE_V1','status':'FAIL' if failed else 'PASS','engine_version':ENGINE_VERSION,'engine_protocol':ENGINE_PROTOCOL,
            'root':str(root),'groups':group_summary,'tests':all_tests,'passed':len(all_tests)-len(failed),'failed':len(failed),
            'warnings':warnings,'warning_count':len(warnings),
            'note':'Top-level groups expose individual regression cases; historical classifier counts are not release gates.'}

# === END PHASE1 VALIDATION / REGRESSION HARDENING ===


# === PHASE2 TRANSACTION / EVENT HARDENING v1 ===
DOMAIN_TRANSACTION_SCHEMA='DOMAIN_TRANSACTION_V1'
DOMAIN_AUTHORIZATION_SCHEMA='DOMAIN_AUTHORIZATION_V1'
DOMAIN_RECEIPT_EVENT_SCHEMA='DOMAIN_RECEIPT_EVENT_V1'


def _phase2_state_path(raw:str)->str:
    s=str(raw or '').strip()
    if s.startswith('state:') or s.startswith('STATE.'):return s[6:]
    return s


def get_by_path(obj: Any, path: str) -> Any:
    raw=path;path=_phase2_state_path(path)
    if path.startswith('/'):
        parts=[p for p in path.split('/') if p]
    else:
        parts=[p for p in path.split('.') if p]
    cur=obj
    for p in parts:
        if isinstance(cur,dict) and p in cur:cur=cur[p]
        elif isinstance(cur,list) and p.isdigit() and int(p)<len(cur):cur=cur[int(p)]
        else:raise KeyError(raw)
    return cur


def resolve_state_ref(state:dict,path:str)->str:
    raw=str(path or '').strip()
    if not raw.startswith('ref:'):return _phase2_state_path(raw)
    key=raw[4:].strip();refs=(((state.get('engine_runtime') or {}).get('state_refs') or {}));mapped=refs.get(key)
    if not isinstance(mapped,str) or not mapped.strip():
        if key==CALDER_552_COMPONENT_REF:return _legacy_calder_552_portfolio_path(state)
        raise KeyError(raw)
    return _phase2_state_path(mapped)


def _phase2_task_self_suffix(ref:str)->Optional[str]:
    s=str(ref or '')
    for p in ('tasks:self.task_data.','TASKS.self.task_data.'):
        if s.startswith(p):return s[len(p):]
    return None


def _settlement_read_value(spec:Any,state:dict,tasks:dict,task:dict,vars:dict):
    if isinstance(spec,(int,float)) and not isinstance(spec,bool):return spec
    if isinstance(spec,dict):
        if 'var' in spec:return vars.get(str(spec['var']))
        if 'from' in spec:
            src=str(spec['from']);suffix=_phase2_task_self_suffix(src)
            if src.startswith(('state:','STATE.')):return get_by_path(state,src)
            if suffix is not None:return get_by_path(task.setdefault('task_data',{}),suffix)
    raise EngineError(f'SETTLEMENT_VALUE_INVALID:{spec!r}')


def _settlement_set_path(target:str,value:Any,state:dict,tasks:dict,task:dict)->None:
    suffix=_phase2_task_self_suffix(target)
    if str(target).startswith(('state:','STATE.')):root,path=state,_phase2_state_path(target)
    elif suffix is not None:root,path=task.setdefault('task_data',{}),suffix
    else:raise EngineError(f'SETTLEMENT_TARGET_INVALID:{target}')
    par,key=_dot_parent(root,path);par[key]=copy.deepcopy(value)


def _settlement_target_read(target:str,state:dict,tasks:dict,task:dict):
    suffix=_phase2_task_self_suffix(target)
    if str(target).startswith(('state:','STATE.')):return get_by_path(state,target)
    if suffix is not None:return get_by_path(task.setdefault('task_data',{}),suffix)
    raise EngineError(f'SETTLEMENT_TARGET_INVALID:{target}')


def _settlement_state_change_targets(rule:dict)->List[str]:
    out=[]
    for upd in rule.get('updates',[]) or []:
        if isinstance(upd,dict):
            t=str(upd.get('target') or '')
            if t.startswith(('state:','STATE.')):out.append(_current_ref_string(t))
    snap=str(rule.get('snapshot_target') or '')
    if snap.startswith(('state:','STATE.')):out.append(_current_ref_string(snap))
    ds=rule.get('deterministic_unit_sales') or {}
    if isinstance(ds,dict):
        for k in ('ledger_target','authoritative_cumulative_qty_target','authoritative_cumulative_gold_target','current_round_target','last_round_target','last_sales_target','next_sales_target'):
            t=str(ds.get(k) or '')
            if t.startswith(('state:','STATE.')):out.append(_current_ref_string(t))
    return list(dict.fromkeys(out))


_catalog_sales_inputs_phase2_base=_v130_layer__catalog_sales_inputs_01
def _catalog_sales_inputs(cfg,state,when):
    if state.get('engine_runtime',{}).get('pricing_runtime'):_pricing_research_catalog_check(state)
    c=copy.deepcopy(cfg);p=str(c.get('catalog_source') or '')
    if p.startswith('state:'):c['catalog_source']='STATE.'+p[6:]
    return _catalog_sales_inputs_phase2_base(c,state,when)














def _phase2_related_entities(payload:dict)->list:
    out=[]
    for k,v in payload.items():
        if k=='command_id':continue
        if k.endswith('_id') and isinstance(v,str) and v.strip():out.append(v.strip())
        elif k.endswith('_ids') and isinstance(v,list):out.extend(str(x) for x in v if isinstance(x,str) and x.strip())
    return list(dict.fromkeys(out))


def _phase2_rule_versions(stage:Path,kind:str)->list:
    try:rr=resolve_rule_registry(stage)['rules']
    except Exception:return []
    rows=[];wanted='domain_command:'+str(kind)
    for rid,rec in rr.items():
        if not isinstance(rec,dict) or rec.get('lifecycle_status')!='active' or rec.get('implementation_status')=='semantic_only':continue
        ops=[str(x.get('operation') or '') for x in (rec.get('effects') or []) if isinstance(x,dict)]
        if wanted in ops or (rid=='RULE-DOMAIN-COMMAND-01' and DOMAIN_COMMAND_SCHEMA in ops):
            rows.append({'rule_id':rid,'version':rec.get('version')})
    return rows


def _phase2_task_selector(tasks:dict,path:str):
    # Supports concrete audit targets such as active_tasks.task:TASK-ID.field.
    m=re.match(r'^(active_tasks|queued_tasks|recent_completed_tasks)\.task:([^\.]+)(?:\.(.*))?$',path)
    if m:
        bucket,tid,rest=m.groups();rows=tasks.get(bucket) or []
        for t in rows:
            if isinstance(t,dict) and str(t.get('task_id'))==tid:
                if not rest:return copy.deepcopy(t)
                try:return copy.deepcopy(get_by_path(t,rest))
                except Exception:return {'status':'MISSING'}
        return {'status':'MISSING'}
    try:return copy.deepcopy(get_by_path(tasks,path))
    except Exception:return {'status':'MISSING'}


def _phase2_state_selector(state:dict,path:str):
    # Queue selectors identify one job without embedding the whole queue in every event.
    m=re.match(r'^(.*(?:repair_queue|medical_queue))\.job:([^\.]+)(?:\.(.*))?$',path)
    if m:
        base,jid,rest=m.groups()
        try:rows=get_by_path(state,base)
        except Exception:return {'status':'MISSING'}
        for job in rows if isinstance(rows,list) else []:
            if isinstance(job,dict) and str(job.get('job_id'))==jid:
                if not rest:return copy.deepcopy(job)
                try:return copy.deepcopy(get_by_path(job,rest))
                except Exception:return {'status':'MISSING'}
        return {'status':'MISSING'}
    try:return copy.deepcopy(get_by_path(state,path))
    except Exception:return {'status':'MISSING'}


def _phase2_projection(state:dict,tasks:dict,changes:list)->dict:
    out={}
    for ch in changes or []:
        if not isinstance(ch,dict):continue
        target=_current_ref_string(str(ch.get('target') or '').strip())
        if not target:continue
        if target.startswith('state:'):out[target]=_phase2_state_selector(state,target[6:])
        elif target.startswith('tasks:'):out[target]=_phase2_task_selector(tasks,target[6:])
    return out


def _phase2_event_source_refs(changes:list,rule_versions:list)->list:
    refs=[]
    for ch in changes or []:
        if isinstance(ch,dict):
            t=_current_ref_string(str(ch.get('target') or '').strip())
            if t:refs.append(t)
    refs.extend('rules:'+str(x.get('rule_id')) for x in rule_versions if isinstance(x,dict) and x.get('rule_id'))
    return list(dict.fromkeys(refs))


def _event_v2_normalize(event:dict)->dict:
    # Before/after may contain entire megabyte-scale runtime objects in legacy
    # callers. The transaction changeset carries the exact leaf evidence instead.
    light={k:v for k,v in event.items() if k not in ('before','after','field_changes')}
    ev=_normalize_current_refs_obj(copy.deepcopy(light));ev['schema_version']=EVENT_SCHEMA_VERSION;ev['event_schema']=EVENT_SCHEMA_VERSION
    ev.setdefault('game_time',None);ev.setdefault('recorded_at',ev.get('game_time'))
    changes=ev.get('changes') or []
    if isinstance(changes,dict):changes=[changes]
    changes=_normalize_current_refs_obj(changes);ev['changes']=changes
    if not ev.get('command_id') and changes:
        eid=str(ev.get('event_id') or sha256_bytes(json.dumps(changes,ensure_ascii=False,sort_keys=True).encode())[:16]);ev['command_id']='SYS:'+eid
    ev.setdefault('actor','system:engine')
    ev.setdefault('authorization',{'schema':DOMAIN_AUTHORIZATION_SCHEMA,'status':'system_authorized','authority':'engine'})
    ev.setdefault('causes',[]);ev.setdefault('related_entities',[]);ev.setdefault('rule_versions',[])
    ev['effects']=_normalize_current_refs_obj(ev.get('effects') if 'effects' in ev else changes)
    ev.setdefault('narrative',ev.get('summary') or '');ev.setdefault('knowledge_scope','current_authority')
    refs=[]
    for r in ev.get('source_refs') or []:
        rr=str(r);refs.append({'state.json':'state:self','tasks.json':'tasks:self','rules.json':'rules:self','catalog.json':'catalog:self','events.jsonl':'events:self','manifest.json':'manifest:self'}.get(rr,_current_ref_string(rr)))
    if not refs:refs=_phase2_event_source_refs(changes,ev.get('rule_versions') or [])
    ev['source_refs']=list(dict.fromkeys(refs))
    if 'field_changes' in event:
        ev['field_changes']=copy.deepcopy(event['field_changes'])
        ev['audit_completeness']='COMPLETE' if event.get('audit_completeness')=='COMPLETE' else 'PENDING_VALIDATION'
    else:ev['audit_completeness']='TRANSACTION_COVERAGE_PENDING'
    return ev


def _phase2_parent_root_for_stage(events_path:Path)->Optional[Path]:
    stage=Path(events_path).resolve().parent
    marker=stage/'.PARENT.json'
    if not marker.is_file():return None
    try:parent_sid=str(strict_json_load(marker).get('parent_save_set_id') or '')
    except Exception:return None
    for anc in stage.parents:
        if not (anc/'manifest.json').is_file():continue
        try:
            if str(_component_manifest_read(anc).get('save_set_id') or '')==parent_sid:return anc
        except Exception:pass
    return None


def _phase2_enrich_event_projection(path:Path,event:dict)->dict:
    return _event_v2_normalize(event)


def _append_engine_history(path:Path,event:dict)->None:
    # Call the physical pre-P2 append implementation once, after current-reference and audit enrichment.
    _append_engine_history_p2_base(path,_phase2_enrich_event_projection(path,event))


def _phase2_domain_post_mutation_validate_v1408(state:dict,tasks:dict,before_time:str)->dict:
    errs=[]
    if str(state.get('game_time'))!=str(before_time):errs.append('DOMAIN_COMMAND_MUST_NOT_ADVANCE_GAME_TIME')
    if tasks.get('game_time') is not None and str(tasks.get('game_time'))!=str(state.get('game_time')):errs.append('TASK_STATE_GAME_TIME_MISMATCH')
    fr=_finance_integrity_report(state)
    if fr.get('status') not in {'PASS','LEGACY'}:errs.append('FINANCE:'+json.dumps(fr,ensure_ascii=False))
    dr=_domain_runtime_integrity_report(state)
    if dr.get('status') not in {'PASS','LEGACY'}:errs.append('DOMAIN_RUNTIME:'+json.dumps(dr,ensure_ascii=False))
    if errs:raise EngineError('DOMAIN_TRANSACTION_POSTCHECK_FAILED:'+';'.join(errs[:8]))
    return {'status':'PASS','checks':['game_time_unchanged','task_state_time_aligned','finance_integrity','domain_runtime_integrity']}


def _domain_command_packet_v2_unlocked(root:Path,payload:dict,version:Optional[str],scope:str,dry_run:bool=False)->dict:
    root=Path(root).resolve();guard(root,restore=True,restore_tool_files=False);ensure_source_ready(root,allow_cache=False)
    phases=['parse']
    if not isinstance(payload,dict) or payload.get('schema')!=DOMAIN_COMMAND_SCHEMA:raise EngineError(f'DOMAIN_COMMAND_SCHEMA_REQUIRED:{DOMAIN_COMMAND_SCHEMA}')
    cid=str(payload.get('command_id') or '').strip()
    if not cid or len(cid)>160:raise EngineError('DOMAIN_COMMAND_ID_INVALID')
    payload=_canonical_domain_payload(payload)
    auth=validate_authority_set(root) or {};current_sid=str(auth.get('save_set_id') or '');current_state=read_json(root/'state.json')
    old=_phase2_domain_existing_receipt(root,current_state,payload);phases.append('idempotency')
    if old is not None:return {'packet':'DOMAIN_COMMAND_RESULT_V2','status':'ALREADY_APPLIED','committed':True,'command_id':cid,'receipt':old,'save_set_id':current_sid,'export_status':'NOT_REQUESTED','retry_action':None,'saved':False,'transaction_schema':DOMAIN_TRANSACTION_SCHEMA,'phases':phases}
    base_sid=str(payload.get('base_save_set_id') or '')
    if base_sid!=current_sid:raise EngineError(f'DOMAIN_COMMAND_STALE_BASE:{base_sid}!={current_sid}')
    authz=_phase2_domain_authorization(current_state,payload);phases.extend(['authorization','precondition'])
    current_tasks=read_json(root/'tasks.json');before_time=str(current_state.get('game_time') or '')
    if dry_run:
        state=copy.deepcopy(current_state);tasks=copy.deepcopy(current_tasks);bs=copy.deepcopy(state);bt=copy.deepcopy(tasks)
        with tempfile.TemporaryDirectory(prefix='voyager_domain_preview_') as td:
            tp=Path(td)
            for fn in COMPONENT_FILES:shutil.copy2(root/fn,tp/fn)
            _copy_declared_cold_archives(root,tp,_component_manifest_read(root))
            effect=_apply_domain_command(tp,state,tasks,payload)
            phases.extend(['reservation','mutation']);post=_lw_domain_postcheck(state,tasks,before_time,payload,effect);phases.append('validation')
            changes=_normalize_current_refs_obj(copy.deepcopy(effect.get('changes') or []));rules=_phase2_rule_versions(root,str(payload.get('kind') or ''))
            return {'packet':'DOMAIN_COMMAND_RESULT_V2','status':'DRY_RUN','command_id':cid,'kind':payload.get('kind'),'authorization':authz,'effect':effect,'before':_phase2_projection(bs,bt,changes),'after':_phase2_projection(state,tasks,changes),'rule_versions':rules,'postcheck':post,'transaction_schema':DOMAIN_TRANSACTION_SCHEMA,'phases':phases+['event_preview'],'saved':False}
    if not version:raise EngineError('DOMAIN_COMMAND_VERSION_REQUIRED')
    info=create_stage(root,'domain_command');stage=Path(info['staging'])
    try:
        state=read_json(stage/'state.json');tasks=read_json(stage/'tasks.json');bs=copy.deepcopy(state);bt=copy.deepcopy(tasks)
        authz=_phase2_domain_authorization(state,payload,consume=True);phases.append('reservation');effect=_apply_domain_command(stage,state,tasks,payload);phases.append('mutation')
        receipt=_domain_register_receipt(state,payload,effect,current_sid);digest=receipt.get('payload_sha256');gt=str(state.get('game_time') or '')
        changes=_normalize_current_refs_obj(copy.deepcopy(effect.get('changes') or []));changes.append({'target':f'state:engine_runtime.domain_command_runtime.applied.{cid}','action':'record_idempotency_cache'});changes.append({'target':'state:engine_runtime.domain_command_runtime.order','action':'record_idempotency_order'});changes.append({'target':'state:engine_runtime.domain_authorization_ledger.grants.'+str(payload['authorization_ref']),'action':'consume_verified_grant'})
        _write_authority_json(stage/'state.json',state);_write_authority_json(stage/'tasks.json',tasks)
        post=_lw_domain_postcheck(state,tasks,before_time,payload,effect);phases.append('validation')
        rules=_phase2_rule_versions(stage,str(payload.get('kind') or ''))
        eid=f'DOMAIN-{cid}-{sha256_bytes(str(digest).encode())[:8]}';receipt['event_id']=eid
        hev={'event_id':eid,'game_time':gt,'recorded_at':gt,'type':'system','subtype':'domain_command_commit','summary':f'GAME ENGINE v{ENGINE_VERSION}原子执行领域命令{payload.get("kind")}（{cid}）。','changes':changes,'effects':changes,'source':f'GAME ENGINE v{ENGINE_VERSION} {DOMAIN_COMMAND_SCHEMA}','authority_files':['state.json']+(['tasks.json'] if any(str(x.get('target') or '').startswith('tasks:') for x in changes if isinstance(x,dict)) else []),'command_id':cid,'domain_kind':payload.get('kind'),'zero_time':gt==before_time,'started_at':before_time,'actor':'commander' if authz.get('authority')=='commander' else 'standing_authorization','authorization':authz,'causes':copy.deepcopy(payload.get('causes') or ([payload.get('source_event_id')] if payload.get('source_event_id') else [])),'related_entities':_phase2_related_entities(payload),'rule_versions':rules,'narrative':f'领域命令 {payload.get("kind")} 已按统一事务提交。','knowledge_scope':'current_authority','source_refs':_phase2_event_source_refs(changes,rules),'payload_sha256':digest,'receipt':copy.deepcopy(receipt),'domain_effect':copy.deepcopy(effect)}
        finrows=(effect.get('entries') or [])+(effect.get('finance_entries') or [])
        if finrows:
            fg=sum(_money_units_currency(x.get('delta',0),'gold') for x in finrows if x.get('currency')=='gold');fr=sum(_money_units_currency(x.get('delta',0),'grey') for x in finrows if x.get('currency')=='grey');hev['finance']={'account':'domain_command:'+str(payload.get('reason') or cid),'gold':_money_value_currency(fg,'gold'),'grey':_money_value_currency(fr,'grey')}
        _append_engine_history(stage/'events.jsonl',hev);phases.append('event')
        saved=atomic_save(stage,version,scope,root,False,False);phases.append('atomic_commit')
        return {'packet':'DOMAIN_COMMAND_RESULT_V2','status':'SAVED','command_id':cid,'kind':payload.get('kind'),'authorization':authz,'effect':effect,'receipt':receipt,'event_id':eid,'postcheck':post,'transaction_schema':DOMAIN_TRANSACTION_SCHEMA,'phases':phases,'save':saved,'committed':True,'save_set_id':saved.get('save_set_id'),'export_status':'NOT_REQUESTED','retry_action':None}
    except Exception:
        try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
        except Exception:pass
        raise


def domain_command_packet(root:Path,payload:dict,version:Optional[str],scope:str,dry_run:bool=False)->dict:
    with engine_lock(Path(root).resolve(),exclusive=True):
        return _domain_command_packet_v2_unlocked(root,payload,version,scope,dry_run)


def domain_command_status(base:Path=ROOT)->dict:
    ensure_source_ready(base);state=read_json(base/'state.json');dr=_domain_runtime(state,create=False) or {'applied':{},'order':[]};order=list(dr.get('order') or []);ap=dr.get('applied') or {}
    return {'packet':'DOMAIN_COMMAND_STATUS_V2','engine_version':ENGINE_VERSION,'schema':DOMAIN_COMMAND_SCHEMA,'transaction_schema':DOMAIN_TRANSACTION_SCHEMA,'supported_kinds':sorted(DOMAIN_PUBLIC_KINDS),'unavailable_legacy_kinds':sorted(DOMAIN_COMMAND_KINDS-DOMAIN_PUBLIC_KINDS),'receipt_cache_count':len(order),'receipt_cache_limit':int(dr.get('max_receipts') or DOMAIN_COMMAND_MAX_RECEIPTS),'permanent_receipt_authority':'events:command_id','recent_receipts':[copy.deepcopy(ap[x]) for x in order[-20:] if x in ap]}


_apply_patch_phase2_base=_v130_layer_apply_patch_01
def apply_patch(staging:Path,patch_path:Path)->dict:
    # Generic patch mechanics remain available to session/migration internals, but normal raw mutation is not a gameplay API.
    stage=Path(staging).resolve();name=stage.name
    internal=name.startswith('.stage_session_') or any(tok in name for tok in ('engineupgrade','migration','selftest')) or os.environ.get('VOYAGER_DEVELOPER_MODE')=='1'
    if not internal:
        patch=strict_json_load(patch_path)
        for i,op in enumerate(patch.get('operations') or []):
            if not isinstance(op,dict) or op.get('op')=='history_append':continue
            fn=str(op.get('file') or '');p=str(op.get('path') or '')
            if fn in ('state.json','tasks.json','rules.json','catalog.json','manifest.json','events.jsonl') or (fn=='state.json' and p.startswith(('/summary/funds','/summary/personnel','/summary/ships','/inventories','/voyager_fleet/current_location_partition','/engine_runtime/finance_runtime','/engine_runtime/maintenance_runtime','/engine_runtime/domain_command_runtime','/engine_runtime/commitment_registry','/entity_registry'))):
                raise EngineError(f'RAW_PATCH_DOMAIN_PATH_FORBIDDEN_USE_DOMAIN_COMMAND:{i}:{fn}:{p}')
    if not read_json(stage/'state.json').get('engine_runtime',{}).get('pricing_runtime'):return _apply_patch_phase2_base(stage,patch_path)
    return _pricing_apply_patch(stage,patch_path,_apply_patch_phase2_base)


def _phase2_current_route_regression(root:Path)->tuple:
    hits=[]
    for fn in ('state.json','tasks.json','rules.json','catalog.json'):
        data=read_json(root/fn)
        def walk(x,p=''):
            if isinstance(x,dict):
                for k,v in x.items():walk(v,p+'.'+str(k))
            elif isinstance(x,list):
                for i,v in enumerate(x):walk(v,p+f'[{i}]')
            elif isinstance(x,str) and re.search(r'(?<![A-Za-z])(STATE\.|TASKS\.|WORLD:|HISTORY:|INDEX:)',x):hits.append(fn+p+':'+x[:120])
        walk(data)
    return (not hits,hits[:20])


_native_component_selftest_phase2_base=_v130_layer_native_component_selftest_02
def _v130_layer_native_component_selftest_03(root:Path=ROOT)->dict:
    root=Path(root).resolve();base=_native_component_selftest_phase2_base(root);tests=list(base.get('tests') or []);groups=dict(base.get('groups') or {})
    rows=[]
    def add(name,ok,detail=None):rows.append({'name':name,'status':'PASS' if ok else 'FAIL','detail':detail})
    ok,hits=_phase2_current_route_regression(root);add('current_authority_legacy_routes_absent',ok,hits)
    # Every public domain command requires explicit authorization.
    try:
        sid=(validate_authority_set(root) or {}).get('save_set_id');p={'schema':DOMAIN_COMMAND_SCHEMA,'command_id':'SELFTEST-P2-AUTH','base_save_set_id':sid,'kind':'adjust_funds','reason':'selftest','gold_delta':1}
        blocked=False
        try:domain_command_packet(root,p,None,'selftest',True)
        except EngineError as ex:blocked='AUTHORIZATION_REQUIRED' in str(ex)
        add('domain_command_authorization_required',blocked,str(blocked))
    except Exception as ex:add('domain_command_authorization_required',False,str(ex))
    # Permanent receipt lookup survives cache absence.
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_receipt_test_') as td:
            hp=Path(td)/'events.jsonl';shutil.copy2(root/'events.jsonl',hp);shutil.copy2(root/'manifest.json',Path(td)/'manifest.json');shutil.copy2(root/'engine.py',Path(td)/'engine.py');_copy_declared_cold_archives(root,Path(td),_component_manifest_read(root));p={'schema':DOMAIN_COMMAND_SCHEMA,'command_id':'SELFTEST-PERSIST-1','base_save_set_id':'S','kind':'create_task','authorization':'commander'};dg=_domain_payload_digest(p)
            _append_engine_history_p2_base(hp,_event_v2_normalize({'event_id':'SELFTEST-PERSIST-E','game_time':read_json(root/'state.json').get('game_time'),'type':'system','subtype':'domain_command_commit','domain_kind':p['kind'],'summary':'receipt test','changes':[],'source':'selftest','command_id':p['command_id'],'payload_sha256':dg,'receipt':{'command_id':p['command_id'],'kind':p['kind'],'payload_sha256':dg,'event_id':'SELFTEST-PERSIST-E'}}))
            r=_phase2_domain_event_receipt(hp,p);add('domain_receipt_persistent_in_events',bool(r and r.get('payload_sha256')==dg),r)
    except Exception as ex:add('domain_receipt_persistent_in_events',False,str(ex))
    try:
        ev=_event_v2_normalize({'event_id':'SELFTEST-EV2','game_time':read_json(root/'state.json').get('game_time'),'type':'system','summary':'x','changes':[{'target':'STATE.summary.funds','action':'x'}],'source':'selftest','authority_files':['state.json']})
        add('event_v2_current_refs_and_system_command',ev.get('command_id')=='SYS:SELFTEST-EV2' and ev.get('effects',[{}])[0].get('target')=='state:summary.funds' and all((str(r).startswith(('state:','tasks:','rules:','catalog:','events:','manifest:')) and '.json' not in str(r) and '.jsonl' not in str(r)) for r in ev.get('source_refs',[])),{'command_id':ev.get('command_id'),'effects':ev.get('effects'),'source_refs':ev.get('source_refs')})
    except Exception as ex:add('event_v2_current_refs_and_system_command',False,str(ex))
    # Raw CLI transaction surfaces must be developer-only.
    try:
        env=os.environ.copy();env.pop('VOYAGER_DEVELOPER_MODE',None)
        cp=subprocess.run([sys.executable,str(Path(__file__).resolve()),'stage','--label','selftest_external_raw'],cwd=str(root),env=env,text=True,capture_output=True,timeout=20)
        add('raw_stage_cli_internal_only',cp.returncode!=0 and 'RAW_STAGE_INTERNAL_ONLY' in cp.stdout,{'returncode':cp.returncode,'stdout':cp.stdout[-300:]})
    except Exception as ex:add('raw_stage_cli_internal_only',False,str(ex))
    failed=sum(r['status']!='PASS' for r in rows);groups['phase2_transaction_event']={'passed':len(rows)-failed,'failed':failed,'total':len(rows)};tests.extend(rows)
    total_failed=sum(x.get('status')!='PASS' for x in tests);warnings=list(base.get('warnings') or [])
    return {'packet':'NATIVE_REGRESSION_SUITE_V2','status':'FAIL' if total_failed else 'PASS','engine_version':ENGINE_VERSION,'engine_protocol':ENGINE_PROTOCOL,'root':str(root),'groups':groups,'tests':tests,'passed':len(tests)-total_failed,'failed':total_failed,'warnings':warnings,'warning_count':len(warnings),'note':'Phase 2 adds transaction/auth/idempotency/EVENT_V2/current-route hard gates.'}

# === END PHASE2 TRANSACTION / EVENT HARDENING ===

# === PHASE3 DOMAIN COMMAND SAFETY HARDENING ===

def _domain_job_start(state,tasks,payload,kind,job_kind):
    jid=str(payload.get('job_id') or '').strip()
    if not jid:raise EngineError('DOMAIN_JOB_ID_REQUIRED')
    mr=_maintenance_runtime(state,create=True)
    if _maintenance_job_exists(mr,jid):raise EngineError('DOMAIN_JOB_ALREADY_EXISTS:'+jid)
    now=parse_iso(state.get('game_time'));complete=parse_iso(payload.get('complete_at'))
    if now is None or complete is None:raise EngineError('DOMAIN_JOB_COMPLETE_AT_REQUIRED')
    if complete<=now:raise EngineError('DOMAIN_JOB_COMPLETE_AT_MUST_BE_FUTURE')
    normalized_kind='medical' if ('medical' in job_kind or 'observation' in job_kind) else 'repair'
    raw={
        'job_id':jid,'kind':normalized_kind,'started_at':state.get('game_time'),'complete_at':payload.get('complete_at'),
        'fleet_id':payload.get('fleet_id'),'target_id':payload.get('target_id') or payload.get('subject_ref'),
        'completion_actions':copy.deepcopy(payload.get('completion_actions') or []),'source_event_id':payload.get('source_event_id'),
        'severity':payload.get('severity'),'tracked_count':payload.get('tracked_count',0)
    }
    job=_normalize_maintenance_job(state,raw,now)
    job['domain_subtype']=job_kind
    if payload.get('authorization_ref'):
        grant=(state.get('standing_authorizations') or {}).get(payload['authorization_ref'],{}).get('machine_grant')
        if grant:job['domain_authorization']={'authorization_ref':payload['authorization_ref'],'actor_id':payload.get('actor_id'),'grant_sha256':sha256_bytes(json.dumps(grant,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())}
    if payload.get('subject_ref') is not None:job['subject_ref']=payload.get('subject_ref')
    if payload.get('task_id') is not None:job['task_id']=payload.get('task_id')
    if payload.get('data') is not None:job['data']=copy.deepcopy(payload.get('data') or {})
    q='medical_queue' if normalized_kind=='medical' else 'repair_queue'
    mr[q].append(job)
    return {'kind':kind,'job_id':jid,'changes':[{'target':f'state:engine_runtime.maintenance_runtime.{q}.job:{jid}','action':'start_job'}]}


def _personnel_operational_path(path:str)->bool:
    if not isinstance(path,str) or not path.startswith('state:'):return False
    rel=path[6:]
    low=rel.lower()
    forbidden=('summary.','combat_power','ground_power_snapshot','personnel_baselines','personnel_complement','casualt','losses','nominal','template','fixed_organic_personnel')
    if any(tok in low for tok in forbidden):return False
    return rel.endswith('current_personnel') or rel.endswith('personnel.current_onboard')


def _domain_personnel_transfer(state,tasks,payload):
    src=str(payload.get('source_path') or '');dst=str(payload.get('dest_path') or '');qty=payload.get('qty')
    if not _personnel_operational_path(src) or not _personnel_operational_path(dst) or src==dst or not isinstance(qty,int) or isinstance(qty,bool) or qty<=0:
        raise EngineError('DOMAIN_PERSONNEL_TRANSFER_SEMANTIC_PATH_REQUIRED')
    try:sp,sk=_dot_parent(state,src[6:]);dp,dk=_dot_parent(state,dst[6:]);sv=sp[sk];dv=dp[dk]
    except Exception:raise EngineError('DOMAIN_PERSONNEL_TRANSFER_PATH_MISSING')
    if not isinstance(sv,int) or isinstance(sv,bool) or not isinstance(dv,int) or isinstance(dv,bool) or sv<qty:
        raise EngineError('DOMAIN_PERSONNEL_TRANSFER_COUNTS_INVALID')
    sp[sk]-=qty;dp[dk]+=qty
    return {'kind':'personnel_transfer','qty':qty,'changes':[{'target':src,'action':'decrement_personnel'},{'target':dst,'action':'increment_personnel'}]}


def _registered_location_ids(state:dict,root:Path=ROOT)->set:
    out=set();er=state.get('entity_registry') or {};ents=er.get('entities') if isinstance(er,dict) else {}
    if isinstance(ents,dict):
        for eid,rec in ents.items():
            if not isinstance(rec,dict) or rec.get('status') in {'deleted','archived'}:continue
            et=str(rec.get('entity_type') or '').lower()
            if any(tok in et for tok in ('location','station','planet','facility')):out.add(str(eid))
    try:
        cat=read_json(Path(root)/'catalog.json');cents=((cat.get('catalog_registry') or {}).get('entities') or {})
        if isinstance(cents,dict):
            for eid,rec in cents.items():
                if isinstance(rec,dict) and str(rec.get('entity_type') or '').lower() in {'location','facility','facility_type'} and rec.get('status')!='deprecated':out.add(str(eid))
    except Exception:pass
    return out


def _domain_travel(state,tasks,payload,kind):
    eid=str(payload.get('entity_id') or '').strip();loc=str(payload.get('location_id') or '').strip()
    if not eid or not loc:raise EngineError('DOMAIN_TRAVEL_ENTITY_LOCATION_REQUIRED')
    er=state.get('entity_registry') or {};entities=er.get('entities') if isinstance(er,dict) else None
    if not isinstance(entities,dict) or eid not in entities:raise EngineError('DOMAIN_TRAVEL_ENTITY_NOT_REGISTERED:'+eid)
    if loc not in _registered_location_ids(state,ROOT):raise EngineError('DOMAIN_TRAVEL_LOCATION_NOT_REGISTERED:'+loc)
    rec=entities[eid]
    if str(rec.get('entity_type') or '').lower() not in {'ship','fleet','mobile_asset','spacecraft'}:raise EngineError('DOMAIN_TRAVEL_ENTITY_NOT_MOBILE')
    path=str(rec.get('state_path') or '')
    try:position=get_by_path(state,path)
    except Exception:position=None
    if not isinstance(position,dict) or 'current_location_id' not in position:raise EngineError('DOMAIN_TRAVEL_CANONICAL_POSITION_UNBOUND:'+eid)
    now=parse_iso(state.get('game_time'))
    if kind=='start_travel':
        arrival=parse_iso(payload.get('arrival_at'))
        if arrival is None or now is None or arrival<=now:raise EngineError('DOMAIN_TRAVEL_ARRIVAL_AT_MUST_BE_FUTURE')
        if (position.get('travel') or {}).get('status')=='in_transit':raise EngineError('DOMAIN_TRAVEL_ALREADY_IN_TRANSIT')
        if not position.get('current_location_id'):raise EngineError('DOMAIN_TRAVEL_ORIGIN_UNKNOWN')
        position['travel']={'from_location':position['current_location_id'],'to_location':loc,'started_at':state.get('game_time'),'arrival_at':payload['arrival_at'],'status':'in_transit'}
    else:
        tr=position.get('travel') or {}
        if tr.get('status')!='in_transit':raise EngineError('DOMAIN_TRAVEL_NOT_IN_TRANSIT')
        if tr.get('to_location')!=loc:raise EngineError('DOMAIN_TRAVEL_ARRIVAL_LOCATION_MISMATCH')
        due=parse_iso(tr.get('arrival_at'))
        if due is None or now is None or now<due:raise EngineError('DOMAIN_TRAVEL_NOT_DUE')
        position['current_location_id']=loc;position['travel']={'status':'arrived','arrived_at':state.get('game_time'),'to_location':loc}
    return {'kind':kind,'entity_id':eid,'location_id':loc,'changes':[{'target':'state:'+path+'.travel','action':kind},{'target':'state:'+path+'.current_location_id','action':'arrival_position' if kind=='arrive_location' else 'unchanged'}]}


def _domain_schedule_task(state,tasks,payload):
    tid=str(payload.get('task_id') or '').strip();at=str(payload.get('scheduled_at') or '').strip();tm=parse_iso(at);now=parse_iso(state.get('game_time'))
    if not tid or tm is None or now is None:raise EngineError('DOMAIN_SCHEDULE_TASK_VALID_TIME_REQUIRED')
    if tm<now:raise EngineError('DOMAIN_SCHEDULE_TASK_PAST_TIME_FORBIDDEN')
    bucket,i,t=_domain_task_lookup(tasks,tid)
    if t is None:raise EngineError('DOMAIN_TASK_NOT_FOUND:'+tid)
    if bucket=='active_tasks':tasks[bucket].pop(i);tasks.setdefault('queued_tasks',[]).append(t)
    t['status']='scheduled';t['phase']='scheduled';t.setdefault('task_data',{})['scheduled_at']=at
    return {'kind':'schedule_task','task_id':tid,'scheduled_at':at,'changes':[{'target':f'tasks:queued_tasks.task:{tid}','action':'schedule_task'}]}

_native_component_selftest_phase3_base=_v130_layer_native_component_selftest_03
def _v130_layer_native_component_selftest_04(root:Path=ROOT)->dict:
    root=Path(root).resolve();base=_native_component_selftest_phase3_base(root);tests=list(base.get('tests') or []);groups=dict(base.get('groups') or {});rows=[]
    def add(name,ok,detail=None):rows.append({'name':name,'status':'PASS' if ok else 'FAIL','detail':detail})
    st=read_json(root/'state.json');ta=read_json(root/'tasks.json');now=parse_iso(st.get('game_time'));future=(now+dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S') if now else None
    try:
        a=copy.deepcopy(st);_domain_job_start(a,copy.deepcopy(ta),{'job_id':'SELFTEST-REPAIR','complete_at':future},'start_repair','repair');mr=_maintenance_runtime(a);add('repair_start_uses_repair_queue',any(x.get('job_id')=='SELFTEST-REPAIR' for x in mr['repair_queue']) and not any(x.get('job_id')=='SELFTEST-REPAIR' for x in mr['medical_queue']))
    except Exception as ex:add('repair_start_uses_repair_queue',False,str(ex))
    try:
        a=copy.deepcopy(st);_domain_job_start(a,copy.deepcopy(ta),{'job_id':'SELFTEST-MED','complete_at':future},'start_medical_observation','medical_observation');mr=_maintenance_runtime(a);add('medical_start_uses_medical_queue',any(x.get('job_id')=='SELFTEST-MED' for x in mr['medical_queue']))
    except Exception as ex:add('medical_start_uses_medical_queue',False,str(ex))
    try:
        a=copy.deepcopy(st);blocked=False
        try:_domain_personnel_transfer(a,copy.deepcopy(ta),{'source_path':'state:summary.ships.voyager','dest_path':'state:summary.ships.jinchuan','qty':1})
        except EngineError as ex:blocked='SEMANTIC_PATH' in str(ex)
        add('personnel_transfer_rejects_nonpersonnel_integer_paths',blocked,str(blocked))
    except Exception as ex:add('personnel_transfer_rejects_nonpersonnel_integer_paths',False,str(ex))
    try:
        a=copy.deepcopy(st);eid=next(iter((a.get('entity_registry') or {}).get('entities') or {}));blocked=False
        try:_domain_travel(a,copy.deepcopy(ta),{'entity_id':eid,'location_id':'LOC-NOT-REGISTERED-999'},'start_travel')
        except EngineError as ex:blocked='LOCATION_NOT_REGISTERED' in str(ex)
        add('travel_rejects_unregistered_location',blocked,str(blocked))
    except Exception as ex:add('travel_rejects_unregistered_location',False,str(ex))
    try:
        a=copy.deepcopy(st);b=copy.deepcopy(ta);tid=(b.get('active_tasks') or [{}])[0].get('task_id');past=(now-dt.timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%S');blocked=False
        try:_domain_schedule_task(a,b,{'task_id':tid,'scheduled_at':past})
        except EngineError as ex:blocked='PAST_TIME_FORBIDDEN' in str(ex)
        add('schedule_task_rejects_past_time',blocked,str(blocked))
    except Exception as ex:add('schedule_task_rejects_past_time',False,str(ex))
    failed=sum(r['status']!='PASS' for r in rows);groups['phase3_domain_safety']={'passed':len(rows)-failed,'failed':failed,'total':len(rows)};tests.extend(rows);total_failed=sum(x.get('status')!='PASS' for x in tests);warnings=list(base.get('warnings') or [])
    return {'packet':'NATIVE_REGRESSION_SUITE_V3','status':'FAIL' if total_failed else 'PASS','engine_version':ENGINE_VERSION,'engine_protocol':ENGINE_PROTOCOL,'root':str(root),'groups':groups,'tests':tests,'passed':len(tests)-total_failed,'failed':total_failed,'warnings':warnings,'warning_count':len(warnings),'note':'Phase 3 adds repair/medical/personnel/travel/scheduling safety gates.'}

# === END PHASE3 DOMAIN COMMAND SAFETY HARDENING ===

# === PHASE4 NATIVE ENGINE UPGRADE / LEGACY COMMAND COMPATIBILITY ===

def _phase4_declared_value(text:str,name:str)->str:
    m=re.search(r'^'+re.escape(name)+r'\s*=\s*["\']([^"\']+)["\']',text,re.M)
    if not m:raise EngineError('ENGINE_UPGRADE_DECLARATION_MISSING:'+name)
    return m.group(1)


def _phase4_candidate_guard(candidate:Path,root:Path)->tuple[str,str,str,Path]:
    text=Path(candidate).read_text(encoding='utf-8')
    gv=_phase4_declared_value(text,'BUNDLED_GUARD_VERSION');gh=_phase4_declared_value(text,'BUNDLED_GUARD_SHA256')
    gpver=_phase4_declared_value(text,'GUARD_PROTOCOL')
    choices=(Path(candidate).resolve().parent/'guard.py',Path(root).resolve()/'guard.py',Path(root).resolve()/f'SAVE_GUARD_v{gv}.py')
    for gp in choices:
        if not gp.is_file() or sha256_file(gp)!=gh:continue
        gtext=gp.read_text(encoding='utf-8')
        if _phase4_declared_value(gtext,'GUARD_VERSION')!=gv:continue
        if _phase4_declared_value(gtext,'GUARD_PROTOCOL')!=gpver:continue
        return gv,gh,gpver,gp
    raise EngineError(f'ENGINE_UPGRADE_CANDIDATE_GUARD_NOT_FOUND:{gv}:{gh}')


def _phase4_upgrade_development(candidate):
    candidate=Path(candidate).resolve();expected=candidate.read_bytes()
    roots=[candidate.parent]
    if os.environ.get('VOYAGER_DEV_SOURCE_DIR'):roots.append(Path(os.environ['VOYAGER_DEV_SOURCE_DIR']).resolve())
    for parent in roots:
        path=parent/'development'/'devsrc'/'SOURCE_MANIFEST.json'
        if not path.is_file() or path.is_symlink() or (parent/'development').is_symlink():continue
        if any(p.is_symlink() for p in (parent/'development').rglob('*')):continue
        manifest=strict_json_load(path);data={str(p.relative_to(parent)):p.read_bytes() for p in (parent/'development').rglob('*') if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts}
        try:
            chunks=[]
            for name in manifest['order']:
                raw=data['development/devsrc/'+name]
                if sha256_bytes(raw)!=manifest['responsibilities'][name]['sha256']:raise EngineError('UPGRADE_DEVELOPMENT_DIGEST')
                chunks.append(raw)
            built='# GENERATED FILE — edit development/devsrc modules, then run development/build.py.\n'.encode()+b''.join(chunks)+b'\nif __name__=="__main__":raise SystemExit(main())\n'
            if built==expected:return data
        except (KeyError,EngineError):continue
    raise EngineError('ENGINE_UPGRADE_MATCHING_COMPLETE_DEVELOPMENT_REQUIRED')


def _phase4_bind_candidate_manifest(root:Path,candidate:Path,guard_path:Path,save_version:Optional[str]=None,parent_sid:Optional[str]=None)->dict:
    root=Path(root).resolve();candidate=Path(candidate).resolve();guard_path=Path(guard_path).resolve()
    text=candidate.read_text(encoding='utf-8');gtext=guard_path.read_text(encoding='utf-8')
    cv=_phase4_declared_value(text,'ENGINE_VERSION');ep=_phase4_declared_value(text,'ENGINE_PROTOCOL')
    gv=_phase4_declared_value(gtext,'GUARD_VERSION');gp=_phase4_declared_value(gtext,'GUARD_PROTOCOL')
    shutil.copy2(candidate,root/'engine.py');shutil.copy2(guard_path,root/'guard.py')
    old=_component_manifest_read(root);sv=str(save_version or old.get('save_version') or '')
    development=_phase4_upgrade_development(candidate)
    for rel in (old.get('development_sources') or {}).get('files',{}):
        if rel not in development and (root/rel).is_file():(root/rel).unlink()
    for rel,raw in development.items():
        dest=root/rel;dest.parent.mkdir(parents=True,exist_ok=True);_native_durable_replace_bytes(dest,raw)
    data=_component_data_hashes(root);tools=_component_tool_hashes(root);authority=_component_bundle_hash(data);transport=_component_bundle_hash({**data,**tools})
    m=copy.deepcopy(old);m.update({'schema':COMPONENT_SET_SCHEMA,'format_version':2,'save_version':sv,'save_set_id':f'SAVESET-{sv}-{authority[:16]}','parent_save_set_id':old.get('parent_save_set_id') if parent_sid is None else parent_sid,'authority_bundle_sha256':authority,'component_set_id':'COMPSET-'+transport[:24],'component_bundle_sha256':transport,'engine_version':cv,'engine_protocol':ep,'guard_version':gv,'guard_protocol':gp,'entrypoint':'guard.py','engine_entrypoint':'engine.py','components':{**data,**tools},'authority_components':data,'tool_bindings':tools})
    m['development_sources']={'schema':'VOYAGER_DEV_SOURCES_V1','files':{rel:sha256_bytes(raw) for rel,raw in development.items()},'build_command':'python3 development/build.py --output engine.py'}
    m.setdefault('runtime',{})['native_eight_component']=True
    (root/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8',newline='\n')
    return m


@contextmanager
def _phase4_candidate_view(base:Path,candidate:Path,guard_path:Path,save_version:Optional[str]=None,parent_sid:Optional[str]=None):
    with tempfile.TemporaryDirectory(prefix='voyager_candidate_native_') as td:
        view=Path(td)
        for fn in COMPONENT_FILES:shutil.copy2(Path(base)/fn,view/fn)
        source_manifest=_component_manifest_read(Path(base))
        _copy_declared_cold_archives(Path(base),view,source_manifest)
        for rel,rec in _component_cold_archives(source_manifest).items():
            expected=str(rec.get('file_sha256') or '')
            if not expected or _csha_file(view/rel)!=expected:
                raise EngineError('ENGINE_UPGRADE_COLD_ARCHIVE_HASH:'+rel)
        m=_phase4_bind_candidate_manifest(view,candidate,guard_path,save_version,parent_sid)
        yield view,m


def _phase4_candidate_call(label:str,seconds:float,fn,*args,**kwargs):
    try:return _upgrade_call(label,seconds,fn,*args,**kwargs)
    except EngineError:raise
    except Exception as ex:raise EngineError(f'ENGINE_UPGRADE_CANDIDATE_EXCEPTION:{label}:{type(ex).__name__}:{ex}') from ex


def _phase4_cold_cli(cold:Path,label:str,args:list[str],seconds:float=25.0)->dict:
    """Run a public cold-start CLI probe in its own interpreter/lock lifetime."""
    cold=Path(cold).resolve();env=os.environ.copy();env['VOYAGER_ROOT']=str(cold)
    cmd=[sys.executable,str(cold/'engine.py'),*args]
    try:
        cp=subprocess.run(cmd,cwd=str(cold),env=env,text=True,capture_output=True,timeout=seconds,check=False)
    except subprocess.TimeoutExpired as ex:
        raise EngineError(f'ENGINE_UPGRADE_COLD_CLI_TIMEOUT:{label}:{seconds}s') from ex
    output=(cp.stdout or '').strip();err=(cp.stderr or '').strip()
    if cp.returncode!=0:
        raise EngineError(f'ENGINE_UPGRADE_COLD_CLI_FAILED:{label}:rc={cp.returncode}:{(output+err)[-1200:]}')
    try:
        packet=json.loads(output) if output else {}
    except Exception as ex:
        raise EngineError(f'ENGINE_UPGRADE_COLD_CLI_JSON_INVALID:{label}:{output[-1200:]}') from ex
    return {'packet':packet,'stdout':output[-800:],'stderr':err[-800:],'returncode':cp.returncode}


def _phase4_recent_native_roots(root:Path)->list:
    rows=[Path(root).resolve()];snapdir=Path(root)/'.runtime'/'snapshots';found=[]
    if snapdir.is_dir():
        for p in snapdir.iterdir():
            if not p.is_dir() or not (p/'manifest.json').is_file():continue
            try:m=_component_manifest_read(p);found.append((parse_version(str(m.get('save_version'))),p))
            except Exception:continue
    rows.extend(p for _,p in sorted(found,key=lambda x:x[0],reverse=True)[:2])
    return rows


def _phase4_native_cold_gate(stage:Path,candidate:Path,guard_path:Path,cmod)->dict:
    with _phase4_candidate_view(stage,candidate,guard_path) as (cold,m):
        # The bound Guard's image index gate is a declared packaged dependency.
        # Reproduce the complete supplied source instead of omitting it from the fixture.
        dev=_development_source_files(m)
        for rel,digest in dev.items():
            src=Path(stage)/rel
            if not src.is_file() or src.is_symlink() or sha256_file(src)!=digest:raise EngineError('ENGINE_UPGRADE_COLD_DEVELOPMENT_MISSING:'+rel)
            dest=cold/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
        checks=[];sc,_=_phase4_candidate_call('cold_sourcecheck',20,cmod.component_source_check,cold,True)
        checks.append({'name':'sourcecheck_8','status':sc.get('status'),'detail':str(sc)[-800:]})
        if sc.get('status')!='PASS':raise EngineError('ENGINE_UPGRADE_COLD_BOOT_FAILED:sourcecheck_8:'+','.join(sc.get('errors') or []))
        # Public query/routineplan probes intentionally run in separate CLI processes.
        # Each process owns and releases its read-lock lifetime before the next cold gate,
        # preventing lock-context leakage between in-process candidate/Guard checks.
        qcli=_phase4_cold_cli(cold,'query',['query','当前金币余额','--base',str(cold),'--detail','exact'])
        q=qcli.get('packet') or {};qok=isinstance(q,dict) and q.get('status')=='COMPLETE'
        checks.append({'name':'query_cli','status':'PASS' if qok else 'FAIL','detail':str(q)[-800:]})
        if not qok:raise EngineError('ENGINE_UPGRADE_COLD_BOOT_FAILED:query_cli')
        gt=parse_iso(read_json(cold/'state.json').get('game_time'));until=(gt+dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')
        rpcli=_phase4_cold_cli(cold,'routineplan',['routineplan','--base',str(cold),'--until',until])
        rp=rpcli.get('packet') or {};rpok=isinstance(rp,dict) and bool(rp.get('safe_until'))
        checks.append({'name':'routineplan_cli','status':'PASS' if rpok else 'FAIL','detail':str(rp)[-800:]})
        if not rpok:raise EngineError('ENGINE_UPGRADE_COLD_BOOT_FAILED:routineplan_cli')
        gname,gmod=_load_upgrade_module(cold/'guard.py',cold,'cold_native_guard')
        old=os.environ.get('VOYAGER_ROOT')
        try:
            os.environ['VOYAGER_ROOT']=str(cold)
            import io
            from contextlib import redirect_stdout,redirect_stderr
            out=io.StringIO();err=io.StringIO()
            with redirect_stdout(out),redirect_stderr(err):grc,_=_phase4_candidate_call('cold_guard',20,gmod.main,['--check'])
        finally:
            sys.modules.pop(gname,None)
            if old is None:os.environ.pop('VOYAGER_ROOT',None)
            else:os.environ['VOYAGER_ROOT']=old
        checks.append({'name':'guard','status':'PASS' if grc==0 else 'FAIL','detail':(out.getvalue()+err.getvalue())[-800:]})
        if grc!=0:raise EngineError('ENGINE_UPGRADE_COLD_BOOT_FAILED:guard:'+(out.getvalue()+err.getvalue())[-1600:])
        boot,_=_phase4_candidate_call('cold_boot',20,cmod.cold_start_packet,cold);bok=isinstance(boot,dict) and boot.get('packet')==str(getattr(cmod,'COLD_START_PACKET_SCHEMA',COLD_START_PACKET_SCHEMA))
        checks.append({'name':'boot','status':'PASS' if bok else 'FAIL','detail':str(boot)[-800:]})
        if not bok:raise EngineError('ENGINE_UPGRADE_COLD_BOOT_FAILED:boot')
        return {'status':'PASS','schema':'NATIVE_COMPLETE_SOURCE_COLD_GATE_V3','visible_files':sorted(p.name for p in cold.iterdir() if p.is_file() and not p.name.startswith('.')),'declared_development_files':len(dev),'checks':checks}


def _phase4_native_preflight(root:Path,candidate:Path,guard_path:Path,cmod,candidate_root:Path,stage:Path)->dict:
    compatibility=[]
    for base in _phase4_recent_native_roots(root):
        with _phase4_candidate_view(base,candidate,guard_path) as (view,m):
            chk,_=_phase4_candidate_call('recent_'+str(m.get('save_version')),35,cmod.run_checks,view,full=True,require_manifest=True)
            compatibility.append({'version':m.get('save_version'),'save_set_id':m.get('save_set_id'),'status':chk.get('status'),'errors':(chk.get('errors') or [])[:8]})
            if chk.get('status')!='PASS':raise EngineError('ENGINE_UPGRADE_RECENT_SNAPSHOT_COMPAT_FAILED:'+str(m.get('save_version')))
    bpath=Path(root)/'engine.py';bname,bmod=_load_upgrade_module(bpath,root,'phase4_baseline')
    try:
        gt=parse_iso(read_json(root/'state.json').get('game_time'));until=(gt+dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')
        specs=[('routineplan',lambda mod,base:mod.routineplan_packet(base,until)),('query',lambda mod,base:mod.query_packet(base,'当前金币余额',5,5,'exact'))];perf=[]
        for name,fn in specs:
            _upgrade_call('warm_base_'+name,20,fn,bmod,root);_phase4_candidate_call('warm_candidate_'+name,20,fn,cmod,candidate_root)
            bt=[];ct=[]
            for i in range(3):
                order=(('b',bmod,root,bt),('c',cmod,candidate_root,ct)) if i%2==0 else (('c',cmod,candidate_root,ct),('b',bmod,root,bt))
                for label,mod,base,bucket in order:
                    if label=='c':_,elapsed=_phase4_candidate_call(f'perf_{name}_{i}_{label}',20,fn,mod,base)
                    else:_,elapsed=_upgrade_call(f'perf_{name}_{i}_{label}',20,fn,mod,base)
                    bucket.append(elapsed)
            bmed=_median_ms(bt);cmed=_median_ms(ct);delta=_median_ms([ct[i]-bt[i] for i in range(3)]);ratio=_median_ms([ct[i]/bt[i] if bt[i]>0 else 1.0 for i in range(3)])
            row={'name':name,'status':'PASS','baseline_median_ms':round(bmed,2),'candidate_median_ms':round(cmed,2),'paired_delta_median_ms':round(delta,2),'paired_ratio_median':round(ratio,4),'absolute_limit_ms':5000,'relative_limit':1.20,'relative_absolute_floor_ms':100};perf.append(row)
            if cmed>5000:raise EngineError(f'ENGINE_UPGRADE_PERFORMANCE_REGRESSION_ABSOLUTE:{name}:{cmed:.0f}ms')
            if ratio>1.20 and delta>100:raise EngineError(f'ENGINE_UPGRADE_PERFORMANCE_REGRESSION_RELATIVE:{name}:{delta:.1f}:{ratio:.3f}')
        cold=_phase4_native_cold_gate(stage,candidate,guard_path,cmod)
        return {'status':'PASS','compatibility':compatibility,'performance':perf,'cold_boot_8component':cold,'execution_model':'native_candidate_bound_views'}
    finally:sys.modules.pop(bname,None)


def _phase4_engine_upgrade_commit(root:Path,stage:Path,version:str,scope:str,cmod)->dict:
    root=Path(root).resolve();stage=Path(stage).resolve()
    with engine_lock(root,exclusive=True):
        current=ensure_source_ready(root,allow_cache=False);oldv=current['version'];newv=parse_version(version);_native_validate_stage_parent(stage,root,current)
        if newv<=oldv:raise EngineError(f'SAVE_VERSION_NOT_INCREMENTED:{version}<={version_text(oldv)}')
        parent_sid=current['save_set_id'];_native_update_version_fields(stage,version)
        _ensure_transaction_changeset(root,stage,scope)
        parent_manifest=current.get('component_manifest') or _component_manifest_read(root)
        default_layout='native_eight_component_v3_cold_archives' if parent_manifest.get('cold_archives') else 'native_eight_component_v3'
        prior_layout=str((parent_manifest.get('migration_lineage') or {}).get('to_layout') or default_layout)
        m=cmod._component_write_manifest_native(stage,version,parent_sid,{'from_save_set_id':parent_sid,'from_layout':prior_layout,'to_layout':default_layout,'game_time_advanced':False,'change_scope':scope,'engine_upgrade':True},frozen_development_sources=_component_manifest_read(stage)['development_sources'])
        chk,_=_phase4_candidate_call('commit_sourcecheck',30,cmod.component_source_check,stage,True)
        if chk.get('status')!='PASS':raise EngineError('ENGINE_UPGRADE_STAGING_INVALID:'+','.join(chk.get('errors') or []))
        vr,_=_phase4_candidate_call('commit_full_check',60,cmod.run_checks,stage,full=True,expected_version=version,require_manifest=True,parent_snapshot={'dir':root,'save_set_id':parent_sid,'version':oldv})
        if vr.get('status')!='PASS':raise EngineError('ENGINE_UPGRADE_STATE_CHECK_FAILED:'+json.dumps((vr.get('errors') or [])[:12],ensure_ascii=False))
        snap=_native_snapshot_parent(root,current);journal=_native_commit_journal_path(root)
        recovery_guard=cmod._repair_guard_module(stage)
        recovery_parent,recovery_errors=recovery_guard.validate_dir(root,allow_historical_guard=True)
        if not recovery_parent or recovery_errors:raise EngineError('ENGINE_UPGRADE_RECOVERY_GUARD_INCOMPATIBLE:'+str(recovery_errors))
        _native_make_commit_journal(root,stage,current,m,snap,engine_upgrade=True)
        old_development=(parent_manifest.get('development_sources') or {}).get('files',{})
        new_development=m['development_sources']['files']
        try:
            for rel in sorted(set(old_development)|set(new_development)):
                dest=root/rel;actual=sha256_file(dest) if dest.is_file() and not dest.is_symlink() else None
                if dest.is_symlink() or dest.exists() and not dest.is_file() or actual not in (old_development.get(rel),new_development.get(rel)):raise EngineError('UNKNOWN_MODIFICATION:'+rel)
            for fn in COMPONENT_FILES:
                if fn=='manifest.json':continue
                _native_durable_copy(stage/fn,root/fn);_native_test_failpoint('after_component')
            for rel in sorted(set(old_development)|set(new_development)):
                dest=root/rel
                if rel in new_development:dest.parent.mkdir(parents=True,exist_ok=True);_native_durable_copy(stage/rel,dest)
                elif dest.is_file():dest.unlink();_native_sync_dir(dest.parent)
            _native_test_failpoint('after_upgrade_development')
            _native_durable_copy(stage/'manifest.json',root/'manifest.json');_native_test_failpoint('after_manifest')
            post,_=_phase4_candidate_call('commit_postcheck',30,cmod.component_source_check,root,False)
            if post.get('status')!='PASS' or not recovery_guard.development_intact(root,m):raise EngineError('ENGINE_UPGRADE_POST_COMMIT_INVALID:'+','.join(post.get('errors') or []))
        except BaseException:
            recovered,recovery_errors=recovery_guard.recover_interrupted_commit(root)
            if recovery_errors:raise EngineError('ENGINE_UPGRADE_RECOVERY_FAILED:'+str(recovery_errors))
            raise
        recovery_guard._finish_journal(root,journal,strict_json_load(journal),'committed')
        try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
        except Exception:pass
        return {'status':'COMMITTED','version':version,'save_set_id':m.get('save_set_id'),'parent_save_set_id':parent_sid,'engine_version':m.get('engine_version'),'bundle_sha256':m.get('authority_bundle_sha256'),'component_set_id':m.get('component_set_id'),'game_time':m.get('game_time'),'snapshot_dir':str(snap),'warnings':vr.get('warnings') or [],'native_eight_component':True,'engine_upgrade':True}


def engine_upgrade_packet(root:Path,candidate:Path,save_version:str,scope:str,migration_patch:Optional[Path]=None,make_export:bool=False)->dict:
    root=Path(root).resolve();candidate=Path(candidate).resolve();guard(root,restore=True,restore_tool_files=False);parent=latest_valid_snapshot(root,verify_parent=True)
    text=candidate.read_text(encoding='utf-8');compile(text,str(candidate),'exec')
    if 'ENGINE_MAGIC = "VOYAGER_FLEET_GAME_ENGINE"' not in text and "ENGINE_MAGIC='VOYAGER_FLEET_GAME_ENGINE'" not in text:raise EngineError('ENGINE_UPGRADE_MAGIC_MISSING')
    cv=_phase4_declared_value(text,'ENGINE_VERSION');pv=str((parent.get('index') or {}).get('engine_version') or ENGINE_VERSION)
    if semver_tuple(cv)<=semver_tuple(pv):raise EngineError(f'ENGINE_UPGRADE_VERSION_NOT_NEWER:{cv}<={pv}')
    gv,gh,gpver,gpath=_phase4_candidate_guard(candidate,root);candidate_hash=sha256_file(candidate);stage=None;cname=None
    try:
        with _phase4_candidate_view(root,candidate,gpath) as (candidate_root,cm):
            cname,cmod=_load_upgrade_module(candidate_root/'engine.py',candidate_root,'phase4_candidate')
            st,_=_phase4_candidate_call('candidate_native_selftest',90,cmod.native_component_selftest,candidate_root)
            if not isinstance(st,dict) or st.get('status')!='PASS':raise EngineError('ENGINE_UPGRADE_SELFTEST_FAILED:'+json.dumps(st,ensure_ascii=False)[-3000:])
            info=create_stage(root,'engine_upgrade');stage=Path(info['staging']);before=read_json(stage/'state.json').get('game_time')
            if migration_patch is not None:apply_patch(stage,migration_patch)
            shutil.copy2(candidate,stage/'engine.py');shutil.copy2(gpath,stage/'guard.py')
            _phase4_bind_candidate_manifest(stage,candidate,gpath,save_version,parent.get('save_set_id'))
            after=read_json(stage/'state.json').get('game_time')
            if after!=before:raise EngineError('ENGINE_UPGRADE_MUST_NOT_ADVANCE_GAME_TIME')
            pre=_phase4_native_preflight(root,candidate,gpath,cmod,candidate_root,stage)
            if sha256_file(candidate)!=candidate_hash:raise EngineError('ENGINE_UPGRADE_CANDIDATE_CHANGED')
            saved=_phase4_engine_upgrade_commit(root,stage,save_version,scope,cmod);stage=None
            saved.update(committed=True,external_persistence_confirmed=False)
            saved['export']=cmod.export_save_set(root,saved['save_set_id'])
            saved['export_status']=saved['export']['export_status']
            saved['retry_action']=saved['export'].get('retry_action')
            return {'status':'UPGRADED','from_engine':pv,'to_engine':cv,'candidate_sha256':candidate_hash,'candidate_selftest':'PASS','compatibility_preflight':pre,'metadata_sync':{'profile':'native_eight_component_engine_only','authority_changed':False,'game_time_advanced':False},'guard_binding':{'version':gv,'protocol':gpver,'sha256':gh},'save_result':saved}
    finally:
        if cname:sys.modules.pop(cname,None)
        if stage is not None:
            try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
            except Exception:pass


def _phase4_document_sections(base:Path)->tuple[str,list,dict]:
    rules=read_json(Path(base)/'rules.json');catalog=read_json(Path(base)/'catalog.json');located=[]
    for fn,data in (('rules.json',rules),('catalog.json',catalog)):
        for row in data.get('document_segments') or []:
            if not isinstance(row,dict) or not isinstance(row.get('markdown'),str):continue
            for sec in _world_markdown_h3_sections(row['markdown']):located.append({**sec,'file':fn,'order':row.get('order'),'row':row})
    return _authority_world_text(base),located,{'rules.json':rules,'catalog.json':catalog}


def world_purify_plan(base:Path=ROOT)->dict:
    ensure_source_ready(base);text,located,_=_phase4_document_sections(base);by={x['title']:x for x in located};rows=[];missing=[]
    for title in WORLD_PURIFY_V1_HEADINGS:
        sec=by.get(title)
        if sec is None:missing.append(title);continue
        rows.append({'title':title,'component':sec['file'],'segment_order':sec['order'],'bytes':len(sec['text'].encode('utf-8')),'sha256':sha256_bytes(sec['text'].encode('utf-8')),'contains_rule_heading':bool(re.search(r'(?m)^####?\s+RULE-',sec['text']))})
    return {'packet':'WORLD_PURIFY_PLAN_V2','schema':WORLD_PURIFY_SCHEMA,'authority_layout':'rules_catalog_document_segments','world_bytes':len(text.encode('utf-8')),'candidate_count':len(rows),'candidate_bytes':sum(x['bytes'] for x in rows),'missing_count':len(missing),'missing':missing,'candidates':rows,'safe_to_apply':len(rows)>0 and not missing and not any(x['contains_rule_heading'] for x in rows),'already_purified':len(rows)==0,'policy':'explicit exact-heading registry only; RULE-* and mixed sections are never selected by version heuristics'}


def _world_purify_stage(stage:Path)->dict:
    text,located,docs=_phase4_document_sections(stage);by={x['title']:x for x in located};missing=[x for x in WORLD_PURIFY_V1_HEADINGS if x not in by]
    if missing:raise EngineError('WORLD_PURIFY_SECTION_MISSING:'+','.join(missing))
    chosen=[by[x] for x in WORLD_PURIFY_V1_HEADINGS]
    for sec in chosen:
        if re.search(r'(?m)^####?\s+RULE-',sec['text']):raise EngineError('WORLD_PURIFY_RULE_SECTION_SELECTED:'+sec['title'])
    before_rules=set(re.findall(r'(?m)^###\s+(RULE-[A-Z0-9_-]+)',text));changed=set()
    grouped={}
    for sec in chosen:grouped.setdefault((sec['file'],sec['order']),[]).append(sec)
    for (fn,order),secs in grouped.items():
        rows=docs[fn].get('document_segments') or [];row=next((x for x in rows if isinstance(x,dict) and x.get('order')==order),None)
        if row is None:raise EngineError('WORLD_PURIFY_SEGMENT_MISSING:'+fn+':'+str(order))
        new=row['markdown']
        for sec in sorted(secs,key=lambda x:x['start'],reverse=True):new=new[:sec['start']]+new[sec['end']:]
        row['markdown']=re.sub(r'\n{4,}','\n\n\n',new);changed.add(fn)
    for fn in changed:_write_authority_json(stage/fn,docs[fn])
    after=_authority_world_text(stage);after_rules=set(re.findall(r'(?m)^###\s+(RULE-[A-Z0-9_-]+)',after))
    if before_rules!=after_rules:raise EngineError(f'WORLD_PURIFY_RULE_SET_CHANGED:lost={sorted(before_rules-after_rules)}:added={sorted(after_rules-before_rules)}')
    if any(('### '+x) in after for x in WORLD_PURIFY_V1_HEADINGS):raise EngineError('WORLD_PURIFY_SECTION_REMAINED')
    archived={x['title']:x['text'] for x in chosen};gt=str(read_json(stage/'state.json').get('game_time') or '');digest=sha256_bytes(json.dumps(sorted(archived),ensure_ascii=False,separators=(',',':')).encode())[:12]
    event={'event_id':f'EVT-WORLD-PURIFY-{gt.replace("-","").replace(":","").replace("T","-")}-{digest}','game_time':gt,'type':'world_historical_snapshot_archive','summary':f'GAME ENGINE v{ENGINE_VERSION}将{len(chosen)}个已被更强current事实取代的规则/目录文档历史小节完整归档至HISTORY。','changes':[{'target':('rules:' if x['file']=='rules.json' else 'catalog:')+f'document_segments.section:{x["title"]}','action':'archive_to_history_then_remove'} for x in chosen],'source':f'GAME ENGINE v{ENGINE_VERSION} WORLD_PURIFY_V2','authority_files':sorted(changed),'zero_time':True,'archived_world_sections':archived,'policy':'exact_heading_high_confidence_dynamic_history_only'}
    _append_engine_history(stage/'events.jsonl',event)
    return {'packet':'WORLD_PURIFY_STAGE_V2','archived_count':len(chosen),'archived_bytes':sum(len(x['text'].encode()) for x in chosen),'world_bytes_before':len(text.encode()),'world_bytes_after':len(after.encode()),'event_id':event['event_id'],'rule_count':len(after_rules),'components_changed':sorted(changed),'archived_titles':list(WORLD_PURIFY_V1_HEADINGS)}


def world_purify_apply(root:Path=ROOT,version:Optional[str]=None,scope:str='WORLD historical snapshot purification',dry_run:bool=False)->dict:
    plan=world_purify_plan(root)
    if dry_run:return {'status':'DRY_RUN','packet':'WORLD_PURIFY_APPLY_V2','plan':plan,'saved':False}
    if plan.get('candidate_count')==0:return {'status':'NOOP','packet':'WORLD_PURIFY_APPLY_V2','plan':plan,'saved':False,'reason':'ALREADY_PURIFIED'}
    if not plan.get('safe_to_apply'):raise EngineError('WORLD_PURIFY_PLAN_NOT_SAFE')
    if not version:raise EngineError('WORLD_PURIFY_VERSION_REQUIRED')
    info=create_stage(root,'worldpurify');stage=Path(info['staging'])
    try:
        detail=_world_purify_stage(stage);parent=(validate_authority_set(root) or {}).get('save_set_id');_component_write_manifest_native(stage,version,parent)
        chk=run_checks(stage,full=True,expected_version=version,require_manifest=True,parent_snapshot={'dir':root,'save_set_id':parent,'version':parse_version(str(_component_manifest_read(root).get('save_version')))})
        if chk.get('status')!='PASS':raise EngineError('WORLD_PURIFY_POSTCHECK_FAILED:'+json.dumps((chk.get('errors') or [])[:12],ensure_ascii=False))
        saved=atomic_save(stage,version,scope,root,False,False)
        return {'status':'SAVED','packet':'WORLD_PURIFY_APPLY_V2','plan':plan,'detail':detail,'save':saved}
    except BaseException:
        try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
        except Exception:pass
        raise


def _v130_ast_structure_report(engine_path:Path|None=None)->dict:
    path=Path(engine_path or __file__).resolve();errors=[]
    try:raw=path.read_bytes()
    except Exception as ex:return {'status':'FAIL','errors':['AST_PARSE:'+type(ex).__name__+':'+str(ex)],'engine_path':str(path)}
    key=_stage2_static_key('ast',raw,_STAGE2_AST_RULE_VERSION)
    cached=_stage2_static_cache.get(key) if os.environ.get('VOYAGER_DISABLE_VALIDATION_REUSE')!='1' else None
    if (isinstance(cached,dict) and cached.get('status') in ('PASS','FAIL') and isinstance(cached.get('errors'),list) and all(type(cached.get(k)) is int for k in ('duplicate_function_count','duplicate_class_count','duplicate_critical_constant_count','duplicate_cli_command_count','cli_command_count'))):
        _stage2_count('ast_proof_hits');return {**copy.deepcopy(cached),'engine_path':str(path)}
    _stage2_count('ast_parse_executions')
    try:tree=ast.parse(raw.decode('utf-8'),filename=str(path))
    except Exception as ex:return {'status':'FAIL','errors':['AST_PARSE:'+type(ex).__name__+':'+str(ex)],'engine_path':str(path)}
    duplicate_functions=[];duplicate_classes=[]
    def scan_scope(node,scope):
        f={};c={};body=getattr(node,'body',[]) or []
        for child in body:
            if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef)):f.setdefault(child.name,[]).append(child.lineno)
            elif isinstance(child,ast.ClassDef):c.setdefault(child.name,[]).append(child.lineno)
        for name,lines in f.items():
            if len(lines)>1:duplicate_functions.append({'scope':scope,'name':name,'lines':lines})
        for name,lines in c.items():
            if len(lines)>1:duplicate_classes.append({'scope':scope,'name':name,'lines':lines})
        for child in body:
            if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):scan_scope(child,scope+'.'+child.name)
    scan_scope(tree,'module')
    if duplicate_functions:errors.append('AST_DUPLICATE_FUNCTIONS:'+json.dumps(duplicate_functions,ensure_ascii=False,separators=(',',':')))
    if duplicate_classes:errors.append('AST_DUPLICATE_CLASSES:'+json.dumps(duplicate_classes,ensure_ascii=False,separators=(',',':')))
    critical={'ENGINE_VERSION','ENGINE_PROTOCOL','GUARD_PROTOCOL','BUNDLED_GUARD_VERSION','DOMAIN_COMMAND_SCHEMA','DOMAIN_COMMAND_KINDS'};assigns={k:[] for k in critical}
    for child in tree.body:
        targets=[]
        if isinstance(child,ast.Assign):
            for t in child.targets:
                if isinstance(t,ast.Name):targets.append(t.id)
        elif isinstance(child,ast.AnnAssign) and isinstance(child.target,ast.Name):targets=[child.target.id]
        for name in targets:
            if name in assigns:assigns[name].append(child.lineno)
    dup_constants={k:v for k,v in assigns.items() if len(v)>1}
    if dup_constants:errors.append('AST_DUPLICATE_CRITICAL_CONSTANTS:'+json.dumps(dup_constants,ensure_ascii=False,separators=(',',':')))
    commands={}
    for child in ast.walk(tree):
        if isinstance(child,ast.Call) and isinstance(child.func,ast.Attribute) and child.func.attr=='add_parser' and child.args and isinstance(child.args[0],ast.Constant) and isinstance(child.args[0].value,str):commands.setdefault(child.args[0].value,[]).append(child.lineno)
    dup_commands={k:v for k,v in commands.items() if len(v)>1}
    if dup_commands:errors.append('AST_DUPLICATE_CLI_COMMANDS:'+json.dumps(dup_commands,ensure_ascii=False,separators=(',',':')))
    result={'status':'FAIL' if errors else 'PASS','errors':errors,'duplicate_function_count':len(duplicate_functions),'duplicate_class_count':len(duplicate_classes),'duplicate_critical_constant_count':len(dup_constants),'duplicate_cli_command_count':len(dup_commands),'cli_command_count':len(commands)}
    if os.environ.get('VOYAGER_DISABLE_VALIDATION_REUSE')!='1':_stage2_static_store(key,result)
    return {**result,'engine_path':str(path)}


def _v130_version_binding_report(base:Path)->dict:
    base=Path(base).resolve();errors=[]
    try:m=_component_manifest_read(base)
    except Exception as ex:return {'status':'FAIL','errors':['MANIFEST:'+str(ex)],'root':str(base)}
    checks={'manifest_engine_version':str(m.get('engine_version'))==str(ENGINE_VERSION),'manifest_engine_protocol':str(m.get('engine_protocol'))==str(ENGINE_PROTOCOL),'manifest_guard_version':str(m.get('guard_version'))==str(BUNDLED_GUARD_VERSION),'manifest_guard_protocol':str(m.get('guard_protocol'))==str(GUARD_PROTOCOL)}
    for label,ok in checks.items():
        if not ok:errors.append('VERSION_BINDING:'+label)
    for fn in ('engine.py','guard.py'):
        fp=base/fn
        if not fp.is_file():errors.append('TOOL_MISSING:'+fn);continue
        actual=sha256_file(fp);expected=(m.get('tool_bindings') or {}).get(fn);component=(m.get('components') or {}).get(fn)
        if expected!=actual:errors.append(f'TOOL_HASH_MISMATCH:{fn}:tool_bindings')
        if component!=actual:errors.append(f'TOOL_HASH_MISMATCH:{fn}:components')
    gp=base/'guard.py'
    if gp.is_file() and sha256_file(gp)!=BUNDLED_GUARD_SHA256:errors.append('BUNDLED_GUARD_HASH_MISMATCH')
    return {'status':'FAIL' if errors else 'PASS','errors':errors,'root':str(base),'engine_version':ENGINE_VERSION,'engine_protocol':ENGINE_PROTOCOL,'guard_version':BUNDLED_GUARD_VERSION,'guard_protocol':GUARD_PROTOCOL}


_native_component_selftest_phase4_base=_v130_layer_native_component_selftest_04
def native_component_selftest(root:Path=ROOT)->dict:
    base=_native_component_selftest_phase4_base(root);tests=list(base.get('tests') or []);groups=dict(base.get('groups') or {});rows=[]
    def add(name,ok,detail=None):rows.append({'name':name,'status':'PASS' if ok else 'FAIL','detail':detail})
    sr=_v130_ast_structure_report(Path(__file__).resolve());add('v130_ast_unique_definitions',sr.get('status')=='PASS',sr)
    vb=_v130_version_binding_report(root);add('v130_version_protocol_hash_binding',vb.get('status')=='PASS',vb)
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_native_stage_parent_') as td:
            tr=Path(td)
            for fn in COMPONENT_FILES:shutil.copy2(Path(root)/fn,tr/fn)
            _copy_declared_cold_archives(Path(root),tr,_component_manifest_read(Path(root)))
            info=create_stage(tr,'selftest_parent_binding');stage=Path(info['staging'])
            latest=latest_valid_snapshot(tr,verify_parent=True);marker=validate_stage_parent(stage,tr,latest)
            bound=set((marker.get('parent_file_sha256') or {}).keys())
            add('native_stage_parent_fileset_binding',bound==set(COMPONENT_FILES),{'bound_files':sorted(bound),'expected_files':sorted(COMPONENT_FILES)})
            try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
            except Exception:pass
    except Exception as ex:add('native_stage_parent_fileset_binding',False,f'{type(ex).__name__}:{ex}')
    try:
        plan=world_purify_plan(root);add('legacy_worldpurifyplan_component_compatible',plan.get('packet')=='WORLD_PURIFY_PLAN_V2' and plan.get('authority_layout')=='rules_catalog_document_segments',{'candidates':plan.get('candidate_count'),'missing':plan.get('missing_count')})
        dry=world_purify_apply(root,dry_run=True);add('legacy_worldpurify_dry_run_component_compatible',dry.get('status')=='DRY_RUN' and dry.get('packet')=='WORLD_PURIFY_APPLY_V2',dry.get('status'))
    except Exception as ex:add('legacy_worldpurify_component_compatibility',False,f'{type(ex).__name__}:{ex}')
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_lineage_regression_') as td:
            tr=Path(td);[shutil.copy2(Path(root)/fn,tr/fn) for fn in COMPONENT_FILES];_copy_declared_cold_archives(Path(root),tr,_component_manifest_read(Path(root)));parent=_component_manifest_read(tr);sid=parent.get('save_set_id');t0=read_json(tr/'state.json').get('game_time')
            expected_layout=('native_eight_component_v4_tiered_history' if parent.get('history_tiers') else
                             'native_eight_component_v3_cold_archives' if parent.get('cold_archives') else 'native_eight_component_v3')
            m0=_component_write_manifest_native(tr,'V99.1',sid);l0=m0.get('migration_lineage') or {}
            st=read_json(tr/'state.json');tt=parse_iso(t0);st['game_time']=(tt+dt.timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M:%S');_write_authority_json(tr/'state.json',st)
            m1=_component_write_manifest_native(tr,'V99.2',m0.get('save_set_id'));l1=m1.get('migration_lineage') or {}
            ok=(l0.get('from_layout')==expected_layout and l0.get('to_layout')==expected_layout and l0.get('game_time_advanced') is False and l1.get('from_layout')==expected_layout and l1.get('to_layout')==expected_layout and l1.get('game_time_advanced') is True)
            add('native_manifest_lineage_tracks_layout_and_time',ok,{'zero_time':l0,'advanced':l1})
    except Exception as ex:add('native_manifest_lineage_tracks_layout_and_time',False,f'{type(ex).__name__}:{ex}')
    try:
        with tempfile.TemporaryDirectory(prefix='voyager_transport_sync_') as td:
            parent=Path(td);runtime=parent/'runtime';runtime.mkdir();[shutil.copy2(Path(root)/fn,runtime/fn) for fn in COMPONENT_FILES];_copy_declared_cold_archives(Path(root),runtime,_component_manifest_read(Path(root)));rm=_component_manifest_read(runtime);sid=rm.get('save_set_id');rarchives=_component_cold_archives(rm);rdev=_development_source_files(rm)
            match=parent/'VOYAGER_SOURCE_V99.1.zip'
            with zipfile.ZipFile(match,'w',compression=zipfile.ZIP_DEFLATED) as z:
                for fn in COMPONENT_FILES:z.write(runtime/fn,fn)
                for rel in sorted(rarchives):z.write(runtime/rel,rel)
                for rel,digest in sorted(rdev.items()):
                    source=Path(root)/rel
                    if not source.is_file() or sha256_file(source)!=digest:raise EngineError('SELFTEST_DEVELOPMENT_SOURCE_MISSING:'+rel)
                    z.write(source,rel)
            stale=parent/'VOYAGER_SOURCE_V0.0.zip'
            with zipfile.ZipFile(match,'r') as zin,zipfile.ZipFile(stale,'w',compression=zipfile.ZIP_DEFLATED) as zout:
                for n in zin.namelist():
                    raw=zin.read(n)
                    if n=='manifest.json':
                        mm=json.loads(raw.decode('utf-8'));mm['save_set_id']='SAVESET-V0.0-stale';raw=(json.dumps(mm,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
                    zout.writestr(n,raw)
            now=time.time();os.utime(match,(now-20,now-20));os.utime(stale,(now,now))
            sync=_component_transport_sync_status(sid,runtime,False);add('component_transport_sync_prefers_matching_save_set',sync.get('verified') is True and sync.get('transport_file')==match.name,sync)
            ext=parent/'guard_VTEST.py';shutil.copy2(runtime/'guard.py',ext);src=_native_project_source_dir_check(parent,sid);add('doctor_native_project_source_transport',src.get('status')=='PASS' and src.get('save_set_id')==sid,src)
            # Cold evidence archives are not parsed on normal boot, but their compressed bytes
            # are hash-verified before a transport or cached extraction is trusted.
            if rarchives:
                target_rel=sorted(rarchives)[0];badcold=parent/'VOYAGER_SOURCE_V99.1_BAD_COLD.zip'
                with zipfile.ZipFile(match,'r') as zin,zipfile.ZipFile(badcold,'w',compression=zipfile.ZIP_DEFLATED) as zout:
                    for n in zin.namelist():
                        raw=zin.read(n)
                        if n==target_rel:
                            bb=bytearray(raw);bb[max(0,len(bb)//2)]^=1;raw=bytes(bb)
                        zout.writestr(n,raw)
                bchk=_component_zip_check(badcold);berrs=bchk.get('errors') or []
                add('component_transport_rejects_cold_archive_hash_mismatch',bchk.get('status')=='FAIL' and ('SOURCE_ZIP_COLD_ARCHIVE_HASH:'+target_rel) in berrs,berrs)
                baddir=parent/'bad_archive_dir';shutil.copytree(runtime,baddir)
                bp=baddir/target_rel;bb=bytearray(bp.read_bytes());bb[max(0,len(bb)//2)]^=1;bp.write_bytes(bytes(bb))
                dchk=component_source_check(baddir,strict_fileset=True);derrs=dchk.get('errors') or []
                add('sourcecheck_rejects_cold_archive_hash_mismatch',dchk.get('status')=='FAIL' and any(('cold_archive_hash_mismatch:'+target_rel) in x for x in derrs),derrs)
                launch=parent/'guard_negative_launch';launch.mkdir();shutil.copy2(runtime/'guard.py',launch/'guard.py');env=os.environ.copy();env['VOYAGER_ROOT']=str(launch)
                cp=subprocess.run([sys.executable,str(launch/'guard.py'),'--source',str(badcold)],env=env,text=True,capture_output=True,timeout=30)
                gtext=(cp.stdout or '')+(cp.stderr or '')
                # A concurrently rejected malformed ZIP may surface as BadZipFile
                # rather than the inner archive hash code. Both fail closed; the
                # precise hash diagnosis was independently asserted above.
                rejected=(('SOURCE_ZIP_COLD_ARCHIVE_HASH:'+target_rel) in gtext or 'BadZipFile:' in gtext)
                add('guard_normal_boot_rejects_cold_archive_hash_mismatch',cp.returncode!=0 and bchk.get('status')=='FAIL' and rejected,{'returncode':cp.returncode,'output':gtext[:500]})
    except Exception as ex:
        add('component_transport_sync_prefers_matching_save_set',False,f'{type(ex).__name__}:{ex}');add('doctor_native_project_source_transport',False,f'{type(ex).__name__}:{ex}')
    failed=sum(x['status']!='PASS' for x in rows);groups['phase4_upgrade_legacy']={'passed':len(rows)-failed,'failed':failed,'total':len(rows)};tests.extend(rows);total=sum(x.get('status')!='PASS' for x in tests);warnings=list(base.get('warnings') or [])
    return {'packet':'NATIVE_REGRESSION_SUITE_V4','status':'FAIL' if total else 'PASS','engine_version':ENGINE_VERSION,'engine_protocol':ENGINE_PROTOCOL,'root':str(Path(root).resolve()),'groups':groups,'tests':tests,'passed':len(tests)-total,'failed':total,'warnings':warnings,'warning_count':len(warnings),'note':'Phase 4 adds native engine-upgrade and legacy command compatibility gates.'}

# === END PHASE4 NATIVE ENGINE UPGRADE / LEGACY COMMAND COMPATIBILITY ===

# === V14.03 mobile read transaction and handoff ===
