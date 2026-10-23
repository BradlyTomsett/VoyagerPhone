# === VOYAGER_DEV_MODULE: transaction_service ===
def _native_commit_journal_path(root:Path)->Path:
    return Path(root)/'.runtime'/NATIVE_COMMIT_JOURNAL_FILENAME


def _native_atomic_json(path:Path,obj:dict)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.name in (NATIVE_COMMIT_JOURNAL_FILENAME,CONSISTENCY_REPAIR_JOURNAL) and path.parent.name=='.runtime':
        _repair_guard_module(path.parent.parent).write_journal(path.parent.parent,path,obj);return
    tmp=path.with_name(path.name+f'.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp')
    _native_durable_replace_bytes(path,(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n').encode())


def _native_sync_dir(path:Path)->None:
    try:fd=os.open(path,os.O_RDONLY | getattr(os,'O_DIRECTORY',0))
    except OSError as ex:raise EngineError('DIRECTORY_SYNC_UNSUPPORTED:'+str(ex)) from ex
    try:os.fsync(fd)
    finally:os.close(fd)


def _native_durable_replace_bytes(path:Path,data:bytes)->None:
    tmp=path.with_name('.'+path.name+'.durable.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('xb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path);_native_sync_dir(path.parent)
    finally:tmp.unlink(missing_ok=True)


def _native_development_clone(source,dest,tmp):
    parts=dest.resolve().parts
    if os.environ.get('VOYAGER_DISABLE_SNAPSHOT_DEDUP')=='1' or '.runtime' not in parts or 'development' not in parts:return False
    runtime=Path(*parts[:parts.index('.runtime')+1]);suffix=parts[parts.index('.runtime')+1:]
    if not suffix or suffix[0] not in ('snapshots','transactions','consistency_repairs','repairs','repair_snapshots'):return False
    if source.is_symlink():raise EngineError('DEVELOPMENT_SOURCE_SYMLINK')
    data=source.read_bytes();digest=sha256_bytes(data);pool=runtime/'development_objects';pool.mkdir(parents=True,exist_ok=True)
    if pool.is_symlink():raise EngineError('DEVELOPMENT_OBJECT_POOL_SYMLINK')
    obj=pool/digest;staged=None
    try:
        if not obj.exists():
            staged=pool/('.object.'+uuid.uuid4().hex)
            with staged.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.chmod(staged,0o444)
            try:os.link(staged,obj);_native_sync_dir(pool);_stage2_count('development_objects_created')
            except FileExistsError:pass
        if obj.is_symlink() or obj.read_bytes()!=data or obj.stat().st_mode&0o222:raise EngineError('DEVELOPMENT_OBJECT_NOT_IMMUTABLE_OR_BOUND')
        os.link(obj,tmp);os.replace(tmp,dest);_native_sync_dir(dest.parent);_stage2_count('development_snapshot_links');return True
    except OSError:
        tmp.unlink(missing_ok=True);_stage2_count('development_snapshot_copy_fallback');return False
    finally:
        if staged:staged.unlink(missing_ok=True)


def _native_durable_copy(source:Path,dest:Path)->None:
    tmp=dest.with_name('.'+dest.name+'.durable.'+uuid.uuid4().hex+'.tmp')
    try:
        if _native_development_clone(Path(source),Path(dest),tmp):return
        with source.open('rb') as src,tmp.open('xb') as dst:
            shutil.copyfileobj(src,dst,1024*1024);dst.flush();os.fsync(dst.fileno())
        os.replace(tmp,dest);_native_sync_dir(dest.parent)
    finally:tmp.unlink(missing_ok=True)


def _native_clear_journal(journal:Path)->None:
    if journal.is_file():
        root=journal.parent.parent;j=strict_json_load(journal)
        _repair_guard_module(root)._finish_journal(root,journal,j,'committed')


def _native_test_failpoint(phase:str)->None:
    if os.environ.get('VOYAGER_DEVELOPER_MODE')!='1':return
    if os.environ.get('VOYAGER_COMMIT_IOFAIL')==phase:raise OSError('TEST_IO_FAILURE:'+phase)
    if os.environ.get('VOYAGER_COMMIT_KILL')==phase:os._exit(86)


def _native_validate_stage_parent(staging:Path,root:Path,current:dict)->dict:
    p=Path(staging)/'.PARENT.json'
    if not p.is_file():raise EngineError('STAGING_PARENT_MARKER_MISSING')
    marker=strict_json_load(p)
    if marker.get('format')!='VOYAGER_STAGE_PARENT_V1':raise EngineError('STAGING_PARENT_MARKER_FORMAT')
    if marker.get('parent_save_set_id')!=current.get('save_set_id'):raise EngineError(f"STALE_STAGING_PARENT:{marker.get('parent_save_set_id')}!={current.get('save_set_id')}")
    if marker.get('parent_bundle_sha256')!=current.get('bundle'):raise EngineError('STAGING_PARENT_BUNDLE_MISMATCH')
    expected={fn:sha256_file(Path(root)/fn) for fn in COMPONENT_FILES}
    if marker.get('parent_file_sha256')!=expected:raise EngineError('STAGING_PARENT_FILESET_MISMATCH')
    return marker


def _native_historical_source_check(source:Path,guard_path:Path)->dict:
    spec=importlib.util.spec_from_file_location('voyager_snapshot_guard_'+uuid.uuid4().hex,guard_path)
    module=importlib.util.module_from_spec(spec);exec(compile(guard_path.read_bytes(),str(guard_path),'exec',dont_inherit=True),module.__dict__)
    manifest,errors=module.validate_dir(source,strict=True,allow_historical_guard=True)
    return {'status':'PASS' if manifest else 'FAIL','save_set_id':manifest.get('save_set_id') if manifest else None,'errors':errors}


def _native_snapshot_parent(root:Path,current:dict)->Path:
    sid=str(current.get('save_set_id') or '')
    if not sid:raise EngineError('COMMIT_PARENT_SAVESET_MISSING')
    target=_native_snapshot_dir(root,sid);target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        chk=_native_historical_source_check(target,root/'guard.py')
        if chk.get('status')!='PASS':raise EngineError('COMMIT_PARENT_SNAPSHOT_INVALID:'+','.join(chk.get('errors') or []))
        return target
    tmp=Path(tempfile.mkdtemp(prefix=target.name+'.tmp.',dir=target.parent))
    try:
        for fn in COMPONENT_FILES:_native_durable_copy(Path(root)/fn,tmp/fn)
        for rel in _component_cold_archives(current.get('component_manifest') or _component_manifest_read(root)):
            dest=tmp/rel;dest.parent.mkdir(parents=True,exist_ok=True)
            _native_durable_copy(root/rel,dest);_native_sync_dir(dest.parent)
        for rel,digest in ((current.get('component_manifest') or _component_manifest_read(root)).get('development_sources',{}).get('files') or {}).items():
            if (root/rel).is_file():
                dest=tmp/rel;dest.parent.mkdir(parents=True,exist_ok=True);_native_durable_copy(root/rel,dest)
        chk=component_source_check(tmp,strict_fileset=True)
        if chk.get('status')!='PASS':raise EngineError('COMMIT_PARENT_SNAPSHOT_BUILD_INVALID:'+','.join(chk.get('errors') or []))
        _native_sync_dir(tmp);os.replace(tmp,target);_native_sync_dir(target.parent)
    except BaseException:
        shutil.rmtree(tmp,ignore_errors=True);raise
    return target


def _native_recover_interrupted_commit(root:Path)->Optional[dict]:
    root=Path(root).resolve();journal=_native_commit_journal_path(root)
    if not journal.is_file():return None
    try:j=strict_json_load(journal)
    except Exception as ex:raise EngineError(f'COMMIT_JOURNAL_PARSE:{type(ex).__name__}:{ex}')
    if j.get('schema')!=NATIVE_COMMIT_JOURNAL_SCHEMA:raise EngineError('COMMIT_JOURNAL_SCHEMA_INVALID')
    snapshots=(root/'.runtime'/'snapshots').resolve();snap=(root/str(j.get('parent_snapshot') or '')).resolve()
    if snapshots not in snap.parents:raise EngineError('COMMIT_JOURNAL_SNAPSHOT_PATH_INVALID')
    chk=_native_historical_source_check(snap,root/'guard.py')
    if chk.get('status')!='PASS':raise EngineError('COMMIT_PARENT_SNAPSHOT_INVALID:'+','.join(chk.get('errors') or []))
    if chk.get('save_set_id')!=j.get('parent_save_set_id'):raise EngineError('COMMIT_PARENT_SAVESET_MISMATCH')
    target=component_source_check(root,strict_fileset=False)
    if target.get('status')=='PASS' and target.get('save_set_id')==j.get('target_save_set_id'):
        _native_clear_journal(journal)
        return {'status':'COMMITTED_CLEANED','save_set_id':target['save_set_id'],'snapshot':str(snap)}
    for fn in COMPONENT_FILES:
        if fn=='manifest.json':continue
        _native_durable_copy(snap/fn,root/fn)
    _native_durable_copy(snap/'manifest.json',root/'manifest.json')
    for rel in _component_cold_archives(_component_manifest_read(snap)):
        dest=root/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        _native_durable_copy(snap/rel,dest)
    post=_native_historical_source_check(root,root/'guard.py')
    if post.get('status')!='PASS':raise EngineError('COMMIT_RESTORE_VERIFY_FAILED:'+','.join(post.get('errors') or []))
    _native_clear_journal(journal)
    return {'status':'RESTORED_INTERRUPTED_COMMIT','save_set_id':post.get('save_set_id'),'snapshot':str(snap)}


