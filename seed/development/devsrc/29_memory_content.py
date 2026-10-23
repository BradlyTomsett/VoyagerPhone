# === VOYAGER_DEV_MODULE: memory_content ===
CONTENT_UNITS={'艘','人','台','架','支','枚','包','桶','箱','罐','kg','t','吨','米','m','份','晚','gold','grey','copper','silver','%','hour','day','dimensionless'}
CONTENT_KINDS={'organization','location','equipment','scene_family','semantic_rule','random_tables'}


def validate_content_package(package,installed):
    if not isinstance(package,dict) or (package.get('schema')!='VOYAGER_CONTENT_PACKAGE_V1' or (type(package.get('schema_version')) is not int or package.get('schema_version')!=1)):raise EngineError('CONTENT_SCHEMA')
    pid=package.get('package_id');namespace=package.get('namespace');version=package.get('version')
    if not isinstance(pid,str) or not re.fullmatch(r'[a-z][a-z0-9_.-]{2,100}',pid) or not isinstance(namespace,str) or not re.fullmatch(r'[a-z][a-z0-9_.-]{2,80}',namespace):raise EngineError('CONTENT_NAMESPACE')
    if not isinstance(version,str) or not re.fullmatch(r'\d+\.\d+\.\d+',version):raise EngineError('CONTENT_VERSION')
    if package.get('rule_version') is None or not package.get('source') or package.get('visibility') not in ('player','gm','definition_only'):raise EngineError('CONTENT_SOURCE_OR_VISIBILITY')
    if pid in installed:raise EngineError('CONTENT_PACKAGE_ALREADY_INSTALLED')
    for dep,wanted in package.get('dependencies',{}).items():
        if dep not in installed or installed[dep]['version']!=wanted:raise EngineError('CONTENT_DEPENDENCY:'+dep)
    used={d['id'] for p in installed.values() for d in p.get('definitions',[])};conflicts={d.get('conflict_key') for p in installed.values() for d in p.get('definitions',[]) if d.get('conflict_key')};seen=set()
    definitions=package.get('definitions')
    if not isinstance(definitions,list) or not definitions:raise EngineError('CONTENT_DEFINITIONS_REQUIRED')
    def data_only(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k in ('python','code','script','exec','eval','__class__'):raise EngineError('CONTENT_EXECUTABLE_CODE_FORBIDDEN')
                if k=='unit' and v not in CONTENT_UNITS:raise EngineError('CONTENT_UNKNOWN_UNIT:'+str(v))
                if k in ('price','price_gold','unit_price'):raise EngineError('CONTENT_PRICE_REQUIRES_PRICE_REGISTRY')
                data_only(v)
        elif isinstance(x,list):
            for v in x:data_only(v)
        elif isinstance(x,float) and not math.isfinite(x):raise EngineError('CONTENT_NONFINITE_NUMBER')
        elif x is not None and not isinstance(x,(str,int,float,bool)):raise EngineError('CONTENT_NOT_JSON_DATA')
    for row in definitions:
        if not isinstance(row,dict) or row.get('kind') not in CONTENT_KINDS or not isinstance(row.get('id'),str) or not row['id'].startswith(namespace+':'):raise EngineError('CONTENT_DEFINITION_ID_OR_KIND')
        rid=row['id']
        if rid in seen or rid in used:raise EngineError('CONTENT_DUPLICATE_ID:'+rid)
        seen.add(rid)
        if row.get('conflict_key') in conflicts:raise EngineError('CONTENT_RULE_CONFLICT')
        if row.get('conflict_key'):conflicts.add(row['conflict_key'])
        if row.get('kind')=='semantic_rule' and row.get('implementation')!='semantic_only':raise EngineError('CONTENT_RULE_BINDING_REQUIRED')
        if row.get('kind')=='random_tables' and (pid!='voyager.core.random' or row.get('resolver')!='deterministic_hazard_tables_v3'):raise EngineError('CONTENT_MECHANICAL_RESOLVER_UNREGISTERED')
        if row.get('kind')=='equipment' and (not row.get('unit') or row.get('ownership_effect')!='definition_only'):raise EngineError('CONTENT_EQUIPMENT_MUST_BE_DEFINITION_ONLY')
        data_only(row)
    data_only(package)
    return {'status':'PASS','package_id':pid,'definitions':len(definitions),'definition_ids':sorted(seen),'world_instances_created':0}


def _content_install(stage,payload):
    path=Path(stage)/'catalog.json';catalog=read_json(path);registry=catalog.get('content_packages_v1') or {'schema':'CONTENT_PACKAGE_REGISTRY_V1','packages':{}};package=copy.deepcopy(payload['package']);check=validate_content_package(package,registry['packages'])
    registry['packages'][package['package_id']]=package;catalog['content_packages_v1']=registry;_write_authority_json(path,catalog)
    return {'kind':'content_install','validation':check,'changes':[{'target':'catalog:content_packages_v1.packages.'+package['package_id'],'action':'install_data_only_definition_package'}]}


def content_query_packet(base=ROOT,kind=None,topic=None,audience='player'):
    ensure_source_ready(base);registry=read_json_view(Path(base)/'catalog.json').get('content_packages_v1',{});rows=[]
    if audience=='gm' and (os.environ.get('VOYAGER_DEVELOPER_MODE')!='1' or os.environ.get('VOYAGER_DIAGNOSTIC_CONTEXT')!='gm'):raise EngineError('GM_DIAGNOSTIC_CONTEXT_REQUIRED')
    for pid,pack in registry.get('packages',{}).items():
        if audience!='gm' and pack.get('visibility')=='gm':continue
        for row in pack['definitions']:
            if audience!='gm' and row.get('visibility')=='gm':continue
            if kind and row['kind']!=kind:continue
            if topic and topic not in json.dumps(row,ensure_ascii=False):continue
            rows.append({'package_id':pid,'version':pack['version'],'definition':copy.deepcopy(row),'creates_player_asset':False})
    return {'packet':'CONTENT_QUERY_V1','status':'COMPLETE','definitions':rows,'prices':'unknown unless separately registered in price authority'}


def _registered_random_data():
    catalog=read_json(ROOT/'catalog.json');package=catalog.get('content_packages_v1',{}).get('packages',{}).get('voyager.core.random')
    if not package:raise EngineError('CORE_RANDOM_CONTENT_PACKAGE_REQUIRED_EXPLICIT_MIGRATION')
    return copy.deepcopy(next(d['data'] for d in package['definitions'] if d['kind']=='random_tables'))


def content_integrity_report(base):
    errors=[];catalog=read_json(Path(base)/'catalog.json');packages=catalog.get('content_packages_v1',{}).get('packages',{})
    if not packages:return {'status':'LEGACY','errors':[]}
    checked={}
    try:
        # Dependencies are validated against the complete installed set, while the
        # uniqueness/conflict pass accumulates earlier definitions deterministically.
        for pid,p in packages.items():
            deps={k:v for k,v in packages.items() if k!=pid and k not in checked}
            shell={k:{**v,'definitions':[]} for k,v in deps.items()};validate_content_package(p,{**shell,**checked});checked[pid]=p
        random=next(d['data'] for d in packages['voyager.core.random']['definitions'] if d['kind']=='random_tables')
        sealed=read_json(Path(base)/'rules.json')['runtime_rules']
        if set(random)!={'framework','tables'}:errors.append('RANDOM_CONTENT_SCHEMA')
        if sealed.get('random_event_tables')!=random['tables']:errors.append('RANDOM_CONTENT_RULE_BINDING:random_event_tables')
        for key,value in random['framework'].items():
            if sealed.get('random_event_framework',{}).get(key)!=value:errors.append('RANDOM_CONTENT_RULE_BINDING:framework.'+key)
    except Exception as ex:errors.append(str(ex))
    return {'status':'FAIL' if errors else 'PASS','errors':errors,'packages':len(packages)}


def memory_read_packet(base,path,audience='player'):
    ensure_source_ready(base);base=Path(base);state=read_json(base/'state.json');registry=state['engine_runtime'].get('memory_layers_v1') or {};entry=registry.get('cold_paths',{}).get(path)
    if not entry:raise EngineError('MEMORY_REFERENCE_NOT_FOUND')
    if audience!='gm':
        return {'packet':'MEMORY_READ_V1','status':'REFERENCE_ONLY','source_path':path,'summary':entry['summary'],'epistemic':'source_summary_not_new_fact','archive_ref':entry['archive_ref'],'full_payload_requires':'gm diagnostic context'}
    if os.environ.get('VOYAGER_DEVELOPER_MODE')!='1' or os.environ.get('VOYAGER_DIAGNOSTIC_CONTEXT')!='gm':raise EngineError('GM_DIAGNOSTIC_CONTEXT_REQUIRED')
    with gzip.open(base/entry['archive_ref'],'rt',encoding='utf-8') as stream:wrapper=json.load(stream)
    payload=wrapper['payload']
    if _repair_digest(payload)!=entry['payload_sha256'] or wrapper['payload_sha256']!=entry['payload_sha256']:raise EngineError('MEMORY_ARCHIVE_HASH')
    value=payload['objects'][path]
    if _repair_digest(value)!=entry['object_sha256']:raise EngineError('MEMORY_OBJECT_HASH')
    return {'packet':'MEMORY_READ_V1','status':'COMPLETE','source_path':path,'value':value,'source_event_ids':entry['source_event_ids'],'archived':True}


def memory_integrity_report(base):
    state=read_json(Path(base)/'state.json');reg=state.get('engine_runtime',{}).get('memory_layers_v1')
    if not reg:return {'status':'LEGACY','errors':[]}
    errors=[]
    for path,entry in reg.get('cold_paths',{}).items():
        try:
            marker=get_by_path(state,path)
            if marker.get('$storage')!='cold_archive' or marker.get('archive_ref')!=entry['archive_ref']:errors.append('MEMORY_REDIRECT:'+path)
            # Actual file hash is checked at the shared authority boundary; payload
            # hashes and exact old values are inspected on explicit retrieval/full audit.
            if not (Path(base)/entry['archive_ref']).is_file():errors.append('MEMORY_ARCHIVE_MISSING:'+path)
        except Exception as ex:errors.append(str(ex))
    return {'status':'FAIL' if errors else 'PASS','errors':errors,'cold_objects':len(reg.get('cold_paths',{}))}

_batch_b_memory_read=memory_read_packet
_batch_b_content_query=content_query_packet
