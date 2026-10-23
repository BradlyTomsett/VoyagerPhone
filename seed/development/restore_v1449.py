#!/usr/bin/env python3
"""Restore exact V14.49 bytes into a new directory, only before new game facts.

History payloads are kept once. Original containers are reconstructed from the
lossless payload and tiny verified encoding recipes, then every old hash is checked.
Compression-library differences fail closed; the original input ZIP remains a backup.
"""
import argparse,base64,gzip,hashlib,importlib.util,json,os,pathlib,shutil,sys,tempfile,zlib
sys.dont_write_bytecode=True
P=pathlib.Path
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def restore(source,output):
    source=P(source).resolve();output=P(output).resolve();backup=source/'development/evidence/v1449_codec_rollback'
    if output.exists() or source==output or source in output.parents or output in source.parents:raise ValueError('NEW_EXTERNAL_OUTPUT_REQUIRED')
    previous=json.loads((backup/'manifest.json').read_text())
    recipes=json.loads((backup/'history_recipes.json').read_text())
    if previous['save_set_id']!=recipes['source_save_set_id']:raise ValueError('ROLLBACK_BASE_UNSUPPORTED')
    for name in ('rules.json','catalog.json','state.json','tasks.json'):
        if sha((source/name).read_bytes())!=previous['authority_components'][name]:raise ValueError('NEW_GAME_FACTS_REQUIRE_COMPATIBLE_MIGRATION:'+name)
    os.environ['VOYAGER_ROOT']=str(source)
    guard=load(source/'guard.py','current_guard')
    current,errors=guard.validate_dir(source,strict=True)
    if errors or not current or not guard.development_intact(source,current):raise ValueError('CURRENT_SOURCE_NOT_INTACT')
    api=load(source/'engine.py','current_engine')
    _,events,raws=api.read_history_raw(source/'events.jsonl')
    if len(events)!=recipes['logical_event_count'] or sha(b'\n'.join(raws)+b'\n')!=recipes['logical_sha256']:
        raise ValueError('NEW_GAME_FACTS_REQUIRE_COMPATIBLE_MIGRATION:events.jsonl')
    files={**previous['components'],**{r['path']:r['file_sha256'] for r in previous['cold_archives'].values()},**previous['development_sources']['files']}
    contents={}
    for name,digest in files.items():
        if name=='engine.py' or name in recipes['archives']:continue
        p=backup/name if (backup/name).is_file() else source/name
        if not p.is_file() or p.is_symlink():raise ValueError('PREVIOUS_SOURCE_BYTES_UNAVAILABLE:'+name)
        data=p.read_bytes()
        if sha(data)!=digest:raise ValueError('PREVIOUS_SOURCE_BYTES_UNAVAILABLE:'+name)
        contents[name]=data
    order=json.loads(contents['development/devsrc/SOURCE_MANIFEST.json'])['order']
    contents['engine.py']=(recipes['engine_banner'].encode()+b''.join(contents['development/devsrc/'+name] for name in order)+recipes['engine_tail'].encode())
    for name,recipe in recipes['archives'].items():
        raw=b'\n'.join(raws[recipe['seq_start']-1:recipe['seq_end']])+b'\n'
        if sha(raw)!=recipe['events_sha256']:raise ValueError('ROLLBACK_LOGICAL_SEGMENT_MISMATCH:'+name)
        comp=zlib.compress(raw,9)
        if sha(comp)!=recipe['compressed_sha256']:raise ValueError('ROLLBACK_CODEC_LIBRARY_MISMATCH:'+name)
        text=recipe['prefix'].encode()+base64.b64encode(comp)+recipe['suffix'].encode()
        encoder=zlib.compressobj(recipe['gzip_level'],zlib.DEFLATED,-15)
        body=encoder.compress(text)+encoder.flush()
        trailer=(zlib.crc32(text)&0xffffffff).to_bytes(4,'little')+(len(text)&0xffffffff).to_bytes(4,'little')
        contents[name]=base64.b64decode(recipe['gzip_header_b64'])+body+trailer
    for name,digest in files.items():
        if sha(contents[name])!=digest:raise ValueError('ROLLBACK_RECONSTRUCTION_HASH_MISMATCH:'+name)
    output.parent.mkdir(parents=True,exist_ok=True);stage=P(tempfile.mkdtemp(prefix='.'+output.name+'.restore-',dir=output.parent))
    try:
        for name,data in contents.items():
            p=stage/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        (stage/'manifest.json').write_bytes((backup/'manifest.json').read_bytes())
        old_guard=load(stage/'guard.py','previous_guard');m,errors=old_guard.validate_dir(stage,strict=True)
        if errors or not m or not old_guard.development_intact(stage,m):raise ValueError('RESTORED_SOURCE_NOT_INTACT:'+str(errors))
        _,errors=old_guard.verify_cold_archives(stage,m)
        if errors:raise ValueError('RESTORED_ARCHIVES_NOT_INTACT:'+str(errors))
        os.replace(stage,output)
        return {'status':'RESTORED_PREVIOUS_COPY','save_set_id':m['save_set_id'],'files':len(files)+1,'source_bytes_exact':True,'history_payload_not_duplicated':True}
    finally:
        if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=P,default=P(__file__).resolve().parents[1]);parser.add_argument('--output',type=P,required=True);args=parser.parse_args()
    try:print(json.dumps(restore(args.source,args.output),ensure_ascii=False))
    except Exception as ex:print(json.dumps({'status':'REFUSED','error':str(ex)},ensure_ascii=False));raise SystemExit(1)
