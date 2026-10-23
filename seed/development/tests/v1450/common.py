import hashlib,importlib.util,json,pathlib,os
def protected(source):
    source=pathlib.Path(source);c=json.loads((source/'development/evidence/v1450_input_contract.json').read_text())
    for name,digest in c['unchanged_files'].items():assert hashlib.sha256((source/name).read_bytes()).hexdigest()==digest,name
    os.environ['VOYAGER_ROOT']=str(source)
    spec=importlib.util.spec_from_file_location('protected_history',source/'engine.py');api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
    _,events,raw=api.read_history_raw(source/'events.jsonl')
    assert len(events)==c['logical_events'] and hashlib.sha256(b'\n'.join(raw)+b'\n').hexdigest()==c['logical_sha256']
    return {'unchanged_files':len(c['unchanged_files']),'logical_events':len(events),'logical_bytes_exact':True,'new_game_events':0,'step17':'NOT_AUTHORIZED_UNCHANGED','input_save_set_id':c['input_save_set_id']}
