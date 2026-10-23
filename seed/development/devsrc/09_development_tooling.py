# === VOYAGER_DEV_MODULE: development_tooling ===
DEV_MODULE_MARKER_RE=re.compile(r'^# === VOYAGER_DEV_MODULE: ([a-z0-9_]+) ===$',re.M)
DEV_MODULE_MANIFEST_FORMAT='VOYAGER_ENGINE_DEV_MODULES_V1'
DEV_MODULE_API_FORMAT='VOYAGER_ENGINE_MODULE_API_V1'
DEV_MODULE_API={
    'authority_storage':{'responsibility':'manifest/state/tasks authority loading and source readiness','public':['validate_authority_set','ensure_source_ready']},
    'query_layer':{'responsibility':'read-only typed query intents and evidence retrieval','public':['query_packet','query_batch_packet','evidence_packet']},
    'save_transactions':{'responsibility':'atomic staging, validation and SAVESET commit; state writes enter through transaction/domain interfaces','public':['atomic_save','transact']},
    'finance_domain':{'responsibility':'exact fixed-point committed balance arithmetic','public':['_money_units4','_finance_credit','_finance_integrity_report']},
    'domain_commands':{'responsibility':'idempotent complete business actions across assets/fleet/travel/maintenance/medical/manufacturing','public':['domain_command_packet','domain_command_status']},
    'scheduler':{'responsibility':'deterministic scheduling and advance planning','public':['routineplan_packet']},
    'legacy_migration':{'responsibility':'explicit-only isolated parsing/migration of old saves; never called by normal runtime','public':['legacy_migration_packet']},
    'p2_contracts':{'responsibility':'EVENT_V2, query completeness, cold-start budget and reference integrity contracts','public':['reference_integrity_packet']},
    'development_tooling':{'responsibility':'lossless reproducible single-file split/bundle tooling','public':['devsplit_packet','devbundle_packet']},
}

def _dev_module_segments(source_bytes:bytes)->list:
    """Losslessly split the shipped single-file Engine into contiguous development modules."""
    text=source_bytes.decode('utf-8','strict');matches=list(DEV_MODULE_MARKER_RE.finditer(text));rows=[]
    if not matches:return [{'name':'00_full','bytes':source_bytes}]
    if matches[0].start()>0:rows.append({'name':'00_prelude','bytes':text[:matches[0].start()].encode('utf-8')})
    seen=set()
    for i,m in enumerate(matches):
        name=m.group(1)
        if name in seen:raise EngineError(f'DEV_MODULE_DUPLICATE:{name}')
        seen.add(name);end=matches[i+1].start() if i+1<len(matches) else len(text)
        rows.append({'name':name,'bytes':text[m.start():end].encode('utf-8')})
    if b''.join(x['bytes'] for x in rows)!=source_bytes:raise EngineError('DEV_MODULE_SPLIT_NOT_LOSSLESS')
    return rows

def devsplit_packet(source:Path,output:Optional[Path]=None)->dict:
    source=source.resolve();raw=source.read_bytes();segments=_dev_module_segments(raw)
    out=(output.resolve() if output else (ROOT/'.runtime'/'devsrc'/f'engine_{ENGINE_VERSION}_{sha256_bytes(raw)[:12]}'))
    if out.exists():writable_tree(out);shutil.rmtree(out)
    out.mkdir(parents=True,exist_ok=False);order=[];hashes={}
    for i,row in enumerate(segments):
        fn=f'{i:02d}_{row["name"]}.py';(out/fn).write_bytes(row['bytes']);order.append(fn);hashes[fn]=sha256_bytes(row['bytes'])
    segment_names={row['name'] for row in segments};api=copy.deepcopy(DEV_MODULE_API);missing_modules=sorted(set(api)-segment_names)
    if missing_modules:raise EngineError('DEV_MODULE_API_MODULE_MISSING:'+','.join(missing_modules))
    for mod,rec in api.items():
        for symbol in rec.get('public') or []:
            if not re.search(r'^def '+re.escape(symbol)+r'\s*\(',raw.decode('utf-8','strict'),re.M):raise EngineError(f'DEV_MODULE_API_SYMBOL_MISSING:{mod}:{symbol}')
    api_doc={'format':DEV_MODULE_API_FORMAT,'engine_version':ENGINE_VERSION,'modules':api}
    api_raw=(json.dumps(api_doc,ensure_ascii=False,indent=2)+'\n').encode('utf-8');(out/'MODULE_API.json').write_bytes(api_raw)
    manifest={'format':DEV_MODULE_MANIFEST_FORMAT,'engine_version':ENGINE_VERSION,'source_sha256':sha256_bytes(raw),'source_name':source.name,'order':order,'module_sha256':hashes,'module_api_file':'MODULE_API.json','module_api_sha256':sha256_bytes(api_raw)}
    (out/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'packet':'DEV_SPLIT_V2','status':'READY','source':str(source),'source_sha256':manifest['source_sha256'],'directory':str(out),'module_count':len(order),'order':order,'manifest':str(out/'MANIFEST.json'),'module_api':str(out/'MODULE_API.json')}

def devbundle_packet(source_dir:Path,output:Path)->dict:
    source_dir=source_dir.resolve();mp=source_dir/'MANIFEST.json'
    if not mp.is_file():raise EngineError('DEV_BUNDLE_MANIFEST_MISSING')
    m=read_json(mp)
    if m.get('format')!=DEV_MODULE_MANIFEST_FORMAT:raise EngineError('DEV_BUNDLE_MANIFEST_FORMAT_INVALID')
    api_name=str(m.get('module_api_file') or '')
    if api_name:
        ap=source_dir/api_name
        if not ap.is_file() or sha256_file(ap)!=m.get('module_api_sha256'):raise EngineError('DEV_BUNDLE_MODULE_API_INVALID')
        api=read_json(ap)
        if api.get('format')!=DEV_MODULE_API_FORMAT:raise EngineError('DEV_BUNDLE_MODULE_API_FORMAT_INVALID')
    order=m.get('order') or []
    if not isinstance(order,list) or not order:raise EngineError('DEV_BUNDLE_ORDER_INVALID')
    parts=[];changed=[]
    for fn in order:
        if not isinstance(fn,str) or '/' in fn or '\\' in fn or fn.startswith('.'):raise EngineError('DEV_BUNDLE_MODULE_NAME_INVALID')
        fp=source_dir/fn
        if not fp.is_file():raise EngineError(f'DEV_BUNDLE_MODULE_MISSING:{fn}')
        b=fp.read_bytes();parts.append(b)
        expected=(m.get('module_sha256') or {}).get(fn)
        if expected and sha256_bytes(b)!=expected:changed.append(fn)
    raw=b''.join(parts)
    try:text=raw.decode('utf-8','strict');compile(raw,str(output),'exec')
    except Exception as ex:raise EngineError(f'DEV_BUNDLE_COMPILE_FAILED:{type(ex).__name__}:{ex}')
    if 'ENGINE_MAGIC = "VOYAGER_FLEET_GAME_ENGINE"' not in text and "ENGINE_MAGIC = 'VOYAGER_FLEET_GAME_ENGINE'" not in text:raise EngineError('DEV_BUNDLE_ENGINE_MAGIC_MISSING')
    # Markers must remain unique after edits, preserving future reversible splits.
    _dev_module_segments(raw)
    output=output.resolve();output.parent.mkdir(parents=True,exist_ok=True);tmp=output.with_name(f'.{output.name}.{os.getpid()}.tmp');tmp.write_bytes(raw);os.replace(tmp,output)
    return {'packet':'DEV_BUNDLE_V1','status':'READY','output':str(output),'sha256':sha256_file(output),'bytes':len(raw),'changed_modules':changed,'byte_identical_to_source':sha256_bytes(raw)==m.get('source_sha256'),'module_count':len(order)}

