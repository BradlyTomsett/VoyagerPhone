# === VOYAGER_DEV_MODULE: content_versions ===
CONTENT_V2_SCHEMA='VOYAGER_CONTENT_PACKAGE_V2'
CONTENT_V2_KINDS={'location','organization','equipment','scene_family','semantic_rule'}
_s4_legacy_content_integrity=content_integrity_report


def _s4_version(text):
    if not isinstance(text,str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',text):raise EngineError('CONTENT_VERSION')
    return tuple(map(int,text.split('.')))


def _s4_version_matches(version,constraint):
    value=_s4_version(version)
    if not isinstance(constraint,str) or len(constraint)>100:raise EngineError('CONTENT_DEPENDENCY_RANGE')
    for term in constraint.split(','):
        match=re.fullmatch(r'\s*(>=|<=|==|>|<)?\s*(\d+\.\d+\.\d+)\s*',term)
        if not match:raise EngineError('CONTENT_DEPENDENCY_RANGE')
        wanted=_s4_version(match[2]);op=match[1] or '=='
        if not {'>=':value>=wanted,'<=':value<=wanted,'==':value==wanted,'>':value>wanted,'<':value<wanted}[op]:return False
    return True


def _s4_package_digest(package):return _repair_digest({k:v for k,v in package.items() if k!='content_sha256'})


def _s4_data_only(value):
    if isinstance(value,dict):
        for key,child in value.items():
            if key in {'python','code','script','exec','eval','__class__','write_path','price','unit_price','price_gold'}:raise EngineError('CONTENT_DATA_ONLY_OR_PRICE_AUTHORITY')
            if key=='unit' and child not in CONTENT_UNITS:raise EngineError('CONTENT_UNKNOWN_UNIT')
            _s4_data_only(child)
    elif isinstance(value,list):
        for child in value:_s4_data_only(child)
    elif isinstance(value,float) and not math.isfinite(value):raise EngineError('CONTENT_NONFINITE')
    elif value is not None and type(value) not in (str,int,float,bool):raise EngineError('CONTENT_JSON_ONLY')


def _s4_validate_package(package,install=True):
    required={'schema','schema_version','package_id','namespace','version','dependencies','compatibility','migration_notes','migrations','definitions','content_sha256','source','visibility'}
    _s3_fields(package,required)
    if package['schema']!=CONTENT_V2_SCHEMA or package['schema_version']!=2:raise EngineError('CONTENT_V2_SCHEMA')
    for key in ('namespace','package_id'):
        if not isinstance(package[key],str) or not re.fullmatch(r'[a-z][a-z0-9_.-]{2,100}',package[key]):raise EngineError('CONTENT_NAMESPACE')
    if package['package_id'].startswith('voyager.core.') or package['namespace'].startswith('voyager.core'):raise EngineError('CONTENT_CORE_REQUIRES_ENGINE_MIGRATION')
    _s4_version(package['version']);_s4_data_only(package)
    if package['content_sha256']!=_s4_package_digest(package):raise EngineError('CONTENT_DIGEST_MISMATCH')
    if package['visibility'] not in ('player','gm','definition_only') or not isinstance(package['source'],str) or not package['source']:raise EngineError('CONTENT_SOURCE_VISIBILITY')
    if not isinstance(package['migration_notes'],str) or len(package['migration_notes'])>4000:raise EngineError('CONTENT_MIGRATION_NOTES')
    _s3_fields(package['compatibility'],{'engine','schema_versions'})
    compatible=_s4_version_matches(ENGINE_VERSION,package['compatibility']['engine'])
    if install and not compatible or package['compatibility']['schema_versions']!=[2]:raise EngineError('CONTENT_ENGINE_COMPATIBILITY')
    if not isinstance(package['dependencies'],dict) or len(package['dependencies'])>30:raise EngineError('CONTENT_DEPENDENCIES')
    for dep,term in package['dependencies'].items():
        if not re.fullmatch(r'[a-z][a-z0-9_.-]{2,100}',dep):raise EngineError('CONTENT_DEPENDENCY_ID')
        _s4_version_matches('0.0.0',term)
    definitions=package['definitions']
    if not isinstance(definitions,list) or not 1<=len(definitions)<=500:raise EngineError('CONTENT_DEFINITION_LIMIT')
    ids=set()
    for row in definitions:
        _s3_fields(row,{'id','kind','title','data','tags','priority','visibility','status','conflict_key'})
        if not isinstance(row['id'],str) or not re.fullmatch(re.escape(package['namespace'])+r':[A-Za-z0-9_.:-]{1,100}',row['id']) or row['id'] in ids:raise EngineError('CONTENT_DEFINITION_ID')
        ids.add(row['id'])
        if row['kind'] not in CONTENT_V2_KINDS or row['status'] not in ('active','deprecated') or row['visibility'] not in ('player','gm','definition_only'):raise EngineError('CONTENT_DEFINITION_KIND')
        if type(row['priority']) is not int or not 0<=row['priority']<=100 or not isinstance(row['tags'],list) or len(row['tags'])>12 or any(not isinstance(t,str) or len(t)>40 for t in row['tags']):raise EngineError('CONTENT_RULE_METADATA')
        _story_text(row['title'],200)
        if row['conflict_key'] is not None and not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',str(row['conflict_key'])):raise EngineError('CONTENT_CONFLICT_KEY')
        data=row['data']
        if row['kind']=='scene_family':
            _s3_fields(data,{'family','description'})
            if data['family'] not in ('conversation','negotiation','investigation'):raise EngineError('CONTENT_SCENE_FAMILY')
            _story_text(data['description'],4000)
        elif row['kind']=='equipment':
            _s3_fields(data,{'unit','ownership_effect','description'})
            if data['ownership_effect']!='definition_only':raise EngineError('CONTENT_INSTALL_IS_NOT_ASSET')
            _story_text(data['description'],4000)
        elif row['kind']=='semantic_rule':
            _s3_fields(data,{'implementation','text','subjects','scene_types','valid_from','valid_until'})
            if data['implementation']!='semantic_only':raise EngineError('CONTENT_MECHANICAL_RESOLVER_UNSUPPORTED')
            _story_text(data['text'],4000)
            for field in ('subjects','scene_types'):
                if not isinstance(data[field],list) or not data[field] or any(not isinstance(t,str) or len(t)>100 for t in data[field]):raise EngineError('CONTENT_RULE_SCOPE')
            lo=parse_iso(data['valid_from']);hi=parse_iso(data['valid_until'])
            if data['valid_from'] is not None and not lo or data['valid_until'] is not None and not hi or lo and hi and lo>hi:raise EngineError('CONTENT_RULE_TIME')
        else:
            _s3_fields(data,{'description'});_story_text(data['description'],4000)
    if not isinstance(package['migrations'],list) or len(package['migrations'])>500:raise EngineError('CONTENT_MIGRATION_LIMIT')
    for op in package['migrations']:
        _s3_fields(op,{'op','definition_id','from_version'})
        if op['op']!='retain_version' or not isinstance(op['definition_id'],str):raise EngineError('CONTENT_MIGRATION_UNSUPPORTED')
        _s4_version(op['from_version'])
    if len(json.dumps(package,ensure_ascii=False).encode())>2_000_000:raise EngineError('CONTENT_PACKAGE_SIZE')
    return package


def _s4_content_registry(catalog):
    registry=copy.deepcopy(catalog.get('content_versions_v2'))
    if registry is None:
        registry={'schema':'CONTENT_VERSION_REGISTRY_V2','packages':{},'receipts':{}}
        for pid,package in catalog.get('content_packages_v1',{}).get('packages',{}).items():
            registry['packages'][pid]={'active_version':package['version'],'namespace':package['namespace'],'versions':{package['version']:{'package':copy.deepcopy(package),'sha256':_s4_package_digest(package),'source_event_id':None,'origin':'legacy_sealed_definition'}}}
    return registry


def _s4_active_packages(registry):return {pid:rec['versions'][rec['active_version']]['package'] for pid,rec in registry['packages'].items()}


def _s4_content_graph(packages):
    graph={pid:list(p.get('dependencies',{})) for pid,p in packages.items()}
    ExtensionServices.check_dependencies(graph)
    ids={};namespaces={};conflicts={}
    for pid,p in packages.items():
        if p['namespace'] in namespaces and namespaces[p['namespace']]!=pid:raise EngineError('CONTENT_NAMESPACE_COLLISION')
        namespaces[p['namespace']]=pid
        for dep,term in p.get('dependencies',{}).items():
            if dep not in packages or not _s4_version_matches(packages[dep]['version'],term):raise EngineError('CONTENT_DEPENDENCY_CONFLICT')
        for d in p['definitions']:
            if d['id'] in ids:raise EngineError('CONTENT_DUPLICATE_DEFINITION')
            ids[d['id']]=pid;key=d.get('conflict_key')
            if key:
                if key in conflicts:raise EngineError('CONTENT_RULE_CONFLICT_REQUIRES_RESOLUTION')
                conflicts[key]=d['id']
    return graph


def _s4_content_bindings(state,pid):
    return [{'scene_id':sid,'binding':copy.deepcopy(rec['content_binding'])} for sid,rec in _scene_registry(state)['records'].items() if rec.get('content_binding',{}).get('package_id')==pid]


def _s4_content_plan(base,package):
    _s4_validate_package(package);catalog=read_json(Path(base)/'catalog.json');state=read_json(Path(base)/'state.json');reg=_s4_content_registry(catalog);pid=package['package_id'];rec=reg['packages'].get(pid);old=rec['versions'][rec['active_version']]['package'] if rec else None
    if rec and package['version'] in rec['versions']:
        if rec['versions'][package['version']]['sha256']!=package['content_sha256']:raise EngineError('CONTENT_SAME_VERSION_DIFFERENT_BYTES')
        if rec['active_version']!=package['version']:raise EngineError('CONTENT_DOWNGRADE_REQUIRES_FORWARD_REPAIR')
    if old and _s4_version(package['version'])<_s4_version(old['version']):raise EngineError('CONTENT_DOWNGRADE_REQUIRES_FORWARD_REPAIR')
    if rec and rec['namespace']!=package['namespace']:raise EngineError('CONTENT_NAMESPACE_IMMUTABLE')
    before={d['id']:d for d in old['definitions']} if old else {};after={d['id']:d for d in package['definitions']};removed=sorted(set(before)-set(after));changed=sorted(k for k in before.keys()&after.keys() if before[k]!=after[k]);bindings=_s4_content_bindings(state,pid)
    used={r['binding']['definition_id'] for r in bindings}
    if used&set(removed):raise EngineError('CONTENT_USED_DEFINITION_CANNOT_DELETE')
    breaking=[k for k in changed if before[k]['kind']!=after[k]['kind'] or before[k].get('data',{}).get('unit')!=after[k].get('data',{}).get('unit')]
    if old and _s4_version(package['version'])[0]!=_s4_version(old['version'])[0]:breaking=sorted(set(breaking)|set(changed)|set(removed))
    needed={(d,old['version']) for d in breaking} if old else set();provided={(op['definition_id'],op['from_version']) for op in package['migrations']}
    if not needed<=provided or any(d not in before or not rec or v not in rec['versions'] for d,v in provided):raise EngineError('CONTENT_BREAKING_REQUIRES_EXPLICIT_RETAIN_MIGRATION')
    active=_s4_active_packages(reg);active[pid]=package;graph=_s4_content_graph(active)
    plan={'schema':'CONTENT_UPGRADE_PLAN_V2','base_identity':_s3_identity(base),'package_id':pid,'from_version':old['version'] if old else None,'to_version':package['version'],'content_sha256':package['content_sha256'],'add':sorted(set(after)-set(before)),'change':changed,'remove':removed,'deprecate':sorted(k for k,d in after.items() if d['status']=='deprecated'),'breaking':breaking,'migrations':copy.deepcopy(package['migrations']),'affected_instances':bindings,'dependency_graph':graph,'compatibility':'all previous definitions retained by version; no old world instance, price or RNG rewritten','world_instances_created':0}
    plan['plan_sha256']=_repair_digest(plan);return plan


def content_upgrade_preview(base,package):
    with SnapshotContext(base):
        ensure_source_ready(base);return copy.deepcopy(_s4_content_plan(base,package))


def _s4_content_apply(stage,state,tasks,payload):
    _s4_host_required(payload)
    if payload['kind']=='content_upgrade':
        package=copy.deepcopy(payload['package']);plan=_s4_content_plan(stage,package)
        if payload['plan']!=plan:raise EngineError('CONTENT_UPGRADE_STALE_OR_TAMPERED_PLAN')
        catalog=read_json(Path(stage)/'catalog.json');reg=_s4_content_registry(catalog);pid=package['package_id'];rec=reg['packages'].setdefault(pid,{'namespace':package['namespace'],'versions':{}});event_id=_s4_event_id(payload)
        rec['versions'].setdefault(package['version'],{'package':package,'sha256':package['content_sha256'],'source_event_id':event_id,'origin':'verified_host_content_upgrade'});rec['active_version']=package['version'];reg['receipts'][payload['command_id']]={'event_id':event_id,'plan_sha256':plan['plan_sha256'],'package_id':pid,'version':package['version']};catalog['content_versions_v2']=reg;catalog.setdefault('content_packages_v1',{'schema':'CONTENT_PACKAGE_REGISTRY_V1','packages':{}})['packages'][pid]=package;_write_authority_json(Path(stage)/'catalog.json',catalog)
        return {'kind':'content_upgrade','plan':plan,'source_event_id':event_id,'changes':[{'target':'catalog:content_versions_v2.packages.'+pid,'action':'retain_old_versions_install_active_definition_atomically'},{'target':'catalog:content_packages_v1.packages.'+pid,'action':'active_definition_compatibility_view'}],'world_instances_created':0,'command_payload':copy.deepcopy(payload)}
    ref=payload['definition_ref'];row=_s4_content_resolve(stage,ref,'gm',new_instance=True)
    if row['definition']['kind']!='scene_family':raise EngineError('CONTENT_SCENE_REQUIRES_SCENE_FAMILY')
    action=copy.deepcopy(payload['scene']);_s3_fields(action,{'type','scene_id','task_id','family','title','location_ref','participants','presence_mode','visible_to'})
    if action['type']!='scene_open' or action['family']!=row['definition']['data']['family']:raise EngineError('CONTENT_SCENE_TEMPLATE_MISMATCH')
    effect=_s3_apply(stage,state,tasks,{**payload,'kind':'story_setup','actions':[action]},event_payload=payload)
    _scene_registry(state)['records'][action['scene_id']]['content_binding']={**copy.deepcopy(ref),'definition_sha256':_repair_digest(row['definition']),'source_event_id':_s4_event_id(payload)}
    return {**effect,'kind':'content_scene_open','definition_ref':copy.deepcopy(ref),'definition_sha256':_repair_digest(row['definition']),'world_assets_created':0,'command_payload':copy.deepcopy(payload)}


def _s4_content_targets(payload):
    if payload['kind']=='content_install':return ['catalog:content_packages_v1.packages.'+str(payload['package'].get('package_id'))]
    if payload['kind']=='content_upgrade':return ['catalog:content_versions_v2.packages.'+str(payload['package'].get('package_id')),'catalog:content_packages_v1.packages.'+str(payload['package'].get('package_id'))]
    return _s3_action_targets(payload['scene'])


def _s4_content_resolve(base,ref,viewer='player',new_instance=False):
    _s3_viewer(viewer);_s3_fields(ref,{'package_id','version','definition_id','package_sha256'})
    reg=_s4_content_registry(read_json_view(Path(base)/'catalog.json'));rec=reg['packages'].get(ref['package_id']);snapshot=(rec or {}).get('versions',{}).get(ref['version'])
    if not snapshot or snapshot['sha256']!=ref['package_sha256']:raise EngineError('CONTENT_DEFINITION_UNAVAILABLE')
    package=snapshot['package'];row=next((d for d in package['definitions'] if d['id']==ref['definition_id']),None)
    if not row or viewer!='gm' and ('gm' in (package.get('visibility'),row.get('visibility'))):raise EngineError('CONTENT_DEFINITION_UNAVAILABLE')
    if new_instance and (ref['version']!=rec['active_version'] or row.get('status')=='deprecated'):raise EngineError('CONTENT_NEW_INSTANCE_REQUIRES_ACTIVE_DEFINITION')
    return {'definition':copy.deepcopy(row),'binding':copy.deepcopy(ref),'definition_only':True,'instructions_are_data':True,'mechanical_prices':'requires independent real price authority'}


def content_resolve(base,ref,viewer='player'):
    with SnapshotContext(base):
        ensure_source_ready(base);return _s4_content_resolve(base,ref,viewer)


def _s4_content_integrity(base):
    catalog=read_json(Path(base)/'catalog.json');reg=catalog.get('content_versions_v2')
    if not reg:return _s4_legacy_content_integrity(base)
    errors=[]
    try:
        if reg.get('schema')!='CONTENT_VERSION_REGISTRY_V2':raise EngineError('CONTENT_REGISTRY_SCHEMA')
        active=_s4_active_packages(reg);_s4_content_graph(active)
        if active!=catalog['content_packages_v1']['packages']:raise EngineError('CONTENT_ACTIVE_VIEW_MISMATCH')
        for pid,rec in reg['packages'].items():
            for ver,snapshot in rec['versions'].items():
                p=snapshot['package']
                if p['version']!=ver or p['package_id']!=pid or p['namespace']!=rec['namespace'] or snapshot['sha256']!=_s4_package_digest(p):raise EngineError('CONTENT_VERSION_BINDING')
                if p['schema']==CONTENT_V2_SCHEMA:
                    _s4_validate_package(p,install=False)
                    if not snapshot['source_event_id']:raise EngineError('CONTENT_VERSION_EVENT_EVIDENCE')
                if snapshot['source_event_id']:
                    ev=history_lookup(base,event_id=snapshot['source_event_id']) or {};cmd=(ev.get('domain_effect') or {}).get('command_payload',{})
                    expected='content_install' if snapshot.get('origin')=='verified_legacy_content_install' else 'content_upgrade'
                    if ev.get('domain_kind')!=expected or ev.get('authorization',{}).get('status')!='verified' or cmd.get('package')!=p or _domain_payload_digest(cmd)!=ev.get('payload_sha256'):raise EngineError('CONTENT_VERSION_EVENT_EVIDENCE')
        # Core RNG remains sealed to existing rules; V2 cannot redefine it.
        random=next(d['data'] for d in active['voyager.core.random']['definitions'] if d['kind']=='random_tables');sealed=read_json(Path(base)/'rules.json')['runtime_rules']
        if random['tables']!=sealed['random_event_tables'] or any(sealed['random_event_framework'].get(k)!=v for k,v in random['framework'].items()):raise EngineError('CONTENT_CORE_RANDOM_BINDING')
        state=read_json(Path(base)/'state.json')
        for sid,scene in _scene_registry(state)['records'].items():
            binding=scene.get('content_binding')
            if not binding:continue
            ref={k:binding[k] for k in ('package_id','version','definition_id','package_sha256')};row=_s4_content_resolve(base,ref,'gm')['definition']
            event=history_lookup(base,event_id=binding['source_event_id']) or {}
            if _repair_digest(row)!=binding['definition_sha256'] or event.get('domain_kind')!='content_scene_open' or event.get('domain_effect',{}).get('definition_ref')!=ref or event.get('domain_effect',{}).get('command_payload',{}).get('scene',{}).get('scene_id')!=sid:raise EngineError('CONTENT_INSTANCE_BINDING')
    except Exception as ex:errors.append(str(ex).split(':')[0])
    return {'status':'FAIL' if errors else 'PASS','errors':errors,'packages':len(reg.get('packages',{})),'no_world_asset_installation':True}


ExtensionServices.register('content_upgrade',('package','plan'),_s4_content_apply,_s4_content_targets,_s4_zero_cost)
ExtensionServices.register('content_scene_open',('definition_ref','scene'),_s4_content_apply,_s4_content_targets,_s4_zero_cost)


def _s4_legacy_install(stage,state,tasks,payload):
    # Preserve the old first-install API while keeping the active version view
    # consistent. V1 remains no-upgrade; V2 uses the explicit preview contract.
    old=read_json(Path(stage)/'catalog.json');reg=_s4_content_registry(old)
    effect=_content_install(stage,payload);catalog=read_json(Path(stage)/'catalog.json');p=copy.deepcopy(payload['package']);pid=p['package_id']
    reg['packages'][pid]={'active_version':p['version'],'namespace':p['namespace'],'versions':{p['version']:{'package':p,'sha256':_s4_package_digest(p),'source_event_id':_s4_event_id(payload),'origin':'verified_legacy_content_install'}}}
    _s4_content_graph(_s4_active_packages(reg));catalog['content_versions_v2']=reg;_write_authority_json(Path(stage)/'catalog.json',catalog)
    effect['changes'].append({'target':'catalog:content_versions_v2.packages.'+pid,'action':'bind_legacy_first_install_definition_version'});effect['command_payload']=copy.deepcopy(payload);return effect


ExtensionServices.register('content_install',DOMAIN_REQUIRED_FIELDS['content_install'],_s4_legacy_install,_s4_content_targets,_s3_previous_cost)
content_integrity_report=_s4_content_integrity


class ContentVersionService:
    preview=staticmethod(content_upgrade_preview)
    resolve=staticmethod(content_resolve)
    # Commit is an ordinary typed command through existing trusted host/gateway.
    commit=staticmethod(domain_command_packet)

