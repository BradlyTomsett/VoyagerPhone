#!/usr/bin/env python3
"""Portable lossless codec, corruption, compatibility, lookup and rollback tests."""
import argparse,base64,copy,gzip,hashlib,importlib.util,json,lzma,os,pathlib,shutil,subprocess,sys,time,traceback,zlib
sys.dont_write_bytecode=True
P=pathlib.Path;parser=argparse.ArgumentParser();parser.add_argument('--source',type=P,required=True);parser.add_argument('--output',type=P,required=True);args=parser.parse_args()
BASE=args.source.resolve();OUT=args.output.resolve()
if OUT==BASE or BASE in OUT.parents:parser.error('Output must be outside source')
OUT.mkdir(parents=True,exist_ok=False)
os.environ.update(VOYAGER_ROOT=str(BASE),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm');os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None)
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
a=load(BASE/'engine.py','codec_engine');g=load(BASE/'guard.py','codec_guard');restore=load(BASE/'development/restore_v1449.py','codec_restore');transcode=load(BASE/'development/transcode_history.py','codec_transcode')
def sha(data):return hashlib.sha256(data).hexdigest()
before={name:sha((BASE/name).read_bytes()) for name in ('manifest.json',*json.loads((BASE/'manifest.json').read_text())['components'])};rows=[]
def clone(name):
    r=OUT/name;shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));return r
def rejected(fn,token=None):
    try:fn()
    except Exception as ex:
        if token:assert token in str(ex),(token,str(ex))
        return str(ex)
    raise AssertionError('Expected rejection')
def test(name,fn):
    started=time.monotonic()
    try:detail=fn();row={'name':name,'status':'PASS','detail':detail}
    except Exception as ex:row={'name':name,'status':'FAIL','error':str(ex),'trace':traceback.format_exc()}
    row['seconds']=round(time.monotonic()-started,3);rows.append(row);print(row['status'],name,flush=True)
    result={'schema':'HISTORY_CODEC_V1450_ACCEPTANCE_V1','status':'PASS' if all(x['status']=='PASS' for x in rows) else 'FAIL',
        'save_set_id':json.loads((BASE/'manifest.json').read_text())['save_set_id'],'engine_sha256':sha((BASE/'engine.py').read_bytes()),
        'guard_sha256':sha((BASE/'guard.py').read_bytes()),'test_sha256':sha(P(__file__).read_bytes()),'tests':rows,
        'source_components_unchanged':before=={name:sha((BASE/name).read_bytes()) for name in before}}
    (OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

contract=json.loads((BASE/'development/evidence/v1450_input_contract.json').read_text())
metadata,events,raws=a.read_history_raw(BASE/'events.jsonl')
manifest=json.loads((BASE/'manifest.json').read_text())
physical=(BASE/'events.jsonl').read_bytes().splitlines()
epochs=[json.loads(line) for line in physical if json.loads(line).get('record_type')=='history_epoch']

def exact():
    for name,digest in contract['unchanged_files'].items():assert sha((BASE/name).read_bytes())==digest,name
    assert len(events)==2540 and sha(b'\n'.join(raws)+b'\n')==contract['logical_sha256']
    assert sha(physical[0])==contract['metadata_raw_sha256'] and sha(b'\n'.join(physical[20:])+b'\n')==contract['hot_lines_sha256']
    assert metadata['next_seq']==2541 and len(epochs)==19 and len(physical[20:])==65
    assert all(rec['codec']==a.HISTORY_EPOCH_CODEC for rec in epochs)
    assert manifest['asset_policy']==contract['asset_policy']
    assert manifest['history_tiers']['cold_event_count']==2475 and manifest['history_tiers']['hot_event_count']==65
    verified,errors=g.verify_cold_archives(BASE,manifest);assert not errors and len(verified)==22,errors
    assert {str(p.relative_to(BASE)) for p in (BASE/'archives').rglob('*') if p.is_file()}=={r['path'] for r in manifest['cold_archives'].values()}
    return {'logical_events':2540,'logical_bytes_exact':True,'hot_lines_exact':65,'cold_segments':19,'verified_archives':22,'new_events':0,'unchanged_files':len(contract['unchanged_files'])}
test('all_original_event_bytes_metadata_hot_tail_and_game_facts',exact)

def inline():
    raw=json.dumps({'seq':1,'event_id':'INLINE','type':'system','summary':'仅用于压缩测试'},ensure_ascii=False).encode()
    new=a._make_history_epoch_record([raw],1);assert a._decode_history_epoch_record(new)[1]==[raw]
    legacy=copy.deepcopy(new);compressed=zlib.compress(raw+b'\n',9)
    legacy.update(codec='zlib+base64',payload_b64=base64.b64encode(compressed).decode(),compressed_sha256=sha(compressed),compressed_bytes=len(compressed))
    assert a._decode_history_epoch_record(legacy)[1]==[raw]
    return {'legacy_zlib_inline':True,'new_xz_inline':True,'same_logical_bytes':True}
test('legacy_and_new_inline_epochs',inline)

def restore_exact():
    target=OUT/'restored_v1449';result=restore.restore(BASE,target);old=json.loads((target/'manifest.json').read_text())
    assert result['source_bytes_exact'] and result['files']==277,result
    for rec in epochs:
        old_rec=next(json.loads(line) for line in (target/'events.jsonl').read_bytes().splitlines() if json.loads(line).get('record_type')=='history_epoch' and json.loads(line)['seq_start']==rec['seq_start'])
        assert a._decode_history_epoch_record(old_rec,0,target)[1]==raws[rec['seq_start']-1:rec['seq_end']]
    env=dict(os.environ,VOYAGER_ROOT=str(target),PYTHONDONTWRITEBYTECODE='1');cp=subprocess.run([sys.executable,str(target/'guard.py'),'--resume'],env=env,text=True,capture_output=True,timeout=180)
    assert cp.returncode==0 and json.loads(cp.stdout)['readiness']['status']=='READY_WITH_LIMITATIONS',(cp.stdout,cp.stderr)
    prior=OUT/'restored_v1448';cp=subprocess.run([sys.executable,str(target/'development/restore_previous.py'),'--source',str(target),'--output',str(prior)],env=env,text=True,capture_output=True,timeout=180)
    assert cp.returncode==0,(cp.stdout,cp.stderr)
    return {'restored_original_members':277,'legacy_external_segments_read_by_new_engine':19,'previous_cold_boot':True,'v1448_recovery_chain':True}
test('exact_original_source_and_legacy_external_history_restore',restore_exact)

def mixed():
    r=clone('mixed');old=OUT/'restored_v1449';old_manifest=json.loads((old/'manifest.json').read_text())
    original=next(json.loads(line) for line in (old/'events.jsonl').read_bytes().splitlines() if json.loads(line).get('record_type')=='history_epoch')
    key=f"HISTORY_{original['seq_start']:06d}_{original['seq_end']:06d}";m=json.loads((r/'manifest.json').read_text());new_path=m['cold_archives'][key]['path']
    (r/new_path).unlink();shutil.copyfile(old/original['archive_ref'],r/original['archive_ref']);m['cold_archives'][key]=old_manifest['cold_archives'][key]
    lines=(r/'events.jsonl').read_bytes().splitlines();lines[1]=json.dumps(original,separators=(',',':')).encode();(r/'events.jsonl').write_bytes(b'\n'.join(lines)+b'\n');(r/'manifest.json').write_text(json.dumps(m))
    a._component_write_manifest_native(r,m['save_version'],m['parent_save_set_id'],m['migration_lineage'])
    assert a.read_history_raw(r/'events.jsonl')[2]==raws
    verified,errors=g.verify_cold_archives(r,json.loads((r/'manifest.json').read_text()));assert not errors and len(verified)==22,errors
    return 'one old zlib segment and eighteen XZ segments decode to the identical event stream'
test('mixed_codec_archive_compatibility',mixed)

def future():
    r=clone('future_compaction');old={rec['archive_ref']:sha((r/rec['archive_ref']).read_bytes()) for rec in epochs}
    result=a._compact_history_file_to_epochs(r/'events.jsonl',keep_recent=8,force=True);assert result['status']=='COMPACTED',result
    assert a.read_history_raw(r/'events.jsonl')[2]==raws
    for path,digest in old.items():assert sha((r/path).read_bytes())==digest
    recs=[json.loads(line) for line in (r/'events.jsonl').read_bytes().splitlines() if json.loads(line).get('record_type')=='history_epoch']
    assert len(recs)>19 and all(rec['codec']==a.HISTORY_EPOCH_CODEC for rec in recs)
    m=json.loads((r/'manifest.json').read_text());a._component_write_manifest_native(r,m['save_version'],m['parent_save_set_id'],m['migration_lineage'])
    _,errors=g.verify_cold_archives(r,json.loads((r/'manifest.json').read_text()));assert not errors,errors
    return {'new_cold_segments':len(recs)-19,'prior_segments_unchanged':19,'logical_stream_unchanged':True}
test('future_hot_compaction_uses_new_codec_without_rewriting_cold',future)

def malformed():
    raw=json.dumps({'seq':1,'event_id':'BOUNDS','summary':'a'*4096},separators=(',',':')).encode();record=a._make_history_epoch_record([raw],1);cases=0
    for codec in ('zlib+base64',a.HISTORY_EPOCH_CODEC):
        original=(zlib.compress(raw+b'\n',9) if codec=='zlib+base64' else lzma.compress(raw+b'\n',preset=6))
        for altered in (original[:-1],original+b'trailing',original+original):
            bad=copy.deepcopy(record);bad.update(codec=codec,payload_b64=base64.b64encode(altered).decode(),compressed_sha256=sha(altered),compressed_bytes=len(altered))
            rejected(lambda:a._decode_history_epoch_record(bad));cases+=1
    for field,value in [('codec','unsupported'),('compressed_bytes',1),('uncompressed_bytes',1),('events_sha256','0'*64),('uncompressed_sha256','0'*64),('event_count',2),('seq_start',2),('search_index',[])]:
        bad=copy.deepcopy(record);bad[field]=value;rejected(lambda:a._decode_history_epoch_record(bad));cases+=1
    limit=a.HISTORY_EPOCH_MAX_DECODED_BYTES
    try:a.HISTORY_EPOCH_MAX_DECODED_BYTES=1024;rejected(lambda:a._decode_history_epoch_record(record),'too large');cases+=1
    finally:a.HISTORY_EPOCH_MAX_DECODED_BYTES=limit
    limit=a.HISTORY_EPOCH_LZMA_MEMORY_LIMIT
    try:a.HISTORY_EPOCH_LZMA_MEMORY_LIMIT=1024*1024;rejected(lambda:a._decode_history_epoch_record(record),'Memory usage limit');cases+=1
    finally:a.HISTORY_EPOCH_LZMA_MEMORY_LIMIT=limit
    return {'corruption_and_stream_boundary_rejections':cases,'decoded_byte_and_memory_bounds_exercised':True}
test('malformed_stream_metadata_hash_and_resource_bounds',malformed)

def guards():
    rec=epochs[0];row=next(r for r in manifest['cold_archives'].values() if r['path']==rec['archive_ref']);payload=json.loads(gzip.decompress((BASE/rec['archive_ref']).read_bytes()))['payload'];g._verify_history_payload(payload,row)
    count=0
    for field,value in [('codec','unsupported'),('seq_end',row['seq_end']+1),('event_count',1),('compressed_sha256','0'*64),('compressed_bytes',1),('uncompressed_bytes',1),('events_sha256','0'*64)]:
        p=copy.deepcopy(payload);p[field]=value;rejected(lambda:g._verify_history_payload(p,row));count+=1
    for codec in ('zlib+base64',a.HISTORY_EPOCH_CODEC):
        raw=b'{"seq":1,"event_id":"GUARD"}\n';comp=zlib.compress(raw,9) if codec=='zlib+base64' else lzma.compress(raw,preset=6)
        for badcomp in (comp[:-1],comp+b'trailing'):
            r={'codec':codec,'seq_start':1,'seq_end':1,'event_count':1,'compressed_sha256':sha(badcomp),'events_sha256':sha(raw),'compressed_bytes':len(badcomp),'uncompressed_bytes':len(raw),'uncompressed_sha256':sha(raw)}
            p={**r,'schema':'VOYAGER_HISTORY_PAYLOAD_V1' if codec=='zlib+base64' else 'VOYAGER_HISTORY_PAYLOAD_V2','payload_b64':base64.b64encode(badcomp).decode()};rejected(lambda:g._verify_history_payload(p,r));count+=1
    r=clone('corrupted_archive');p=r/rec['archive_ref'];data=p.read_bytes();p.write_bytes(data[:-1]+bytes([data[-1]^1]));_,errors=g.verify_cold_archives(r,manifest);assert errors
    return {'inner_fault_rejections':count,'outer_file_corruption_rejected':True}
test('independent_guard_codec_hash_count_size_and_stream_checks',guards)

def locators():
    r=clone('locators');hits=[]
    for seq in (1,1000,1001,1832,2475,2476,2540):
        expected=events[seq-1];actual=a.history_lookup(r,event_id=expected['event_id']);assert actual==expected;hits.append(seq)
    (r/'.runtime/history_locator_v2.json').write_text('{"fake":true}');assert a.history_lookup(r,event_id=events[1831]['event_id'])==events[1831]
    with a.SnapshotContext(r) as ctx:assert ctx.validated_report()['status']=='READY_WITH_LIMITATIONS'
    with a.SnapshotContext(r) as ctx:
        result=a.query_packet(r,'当前金币余额');assert result['status']=='COMPLETE' and ctx.metrics['history_decodes']==0
    return {'exact_cold_and_hot_sequences':hits,'invalid_index_rebuilt':True,'warm_balance_history_decodes':0}
test('cold_hot_index_boundaries_and_warm_read_without_history_decode',locators)

def refusal():
    rejected(lambda:restore.restore(BASE,BASE),'NEW_EXTERNAL_OUTPUT_REQUIRED')
    r=clone('changed_facts');(r/'state.json').write_bytes((r/'state.json').read_bytes()+b' ')
    rejected(lambda:restore.restore(r,OUT/'forbidden_facts'),'NEW_GAME_FACTS');assert not (OUT/'forbidden_facts').exists()
    r=clone('new_event');a._append_engine_history(r/'events.jsonl',{'event_id':'TEST-NEW-EVENT','type':'system','game_time':manifest['game_time'],'summary':'isolated fixture'})
    m=json.loads((r/'manifest.json').read_text());a._component_write_manifest_native(r,m['save_version'],m['parent_save_set_id'],m['migration_lineage'])
    rejected(lambda:restore.restore(r,OUT/'forbidden_events'),'NEW_GAME_FACTS');assert not (OUT/'forbidden_events').exists()
    rejected(lambda:transcode.transcode_copy(BASE,BASE,'V14.51'),'NEW_EXTERNAL_OUTPUT_REQUIRED')
    rejected(lambda:transcode.transcode_copy(BASE,OUT/'forbidden_version',manifest['save_version']),'NEWER_SAVE_VERSION_REQUIRED');assert not (OUT/'forbidden_version').exists()
    r=clone('missing_source');(r/epochs[0]['archive_ref']).unlink();rejected(lambda:transcode.transcode_copy(r,OUT/'forbidden_copy','V14.51'),'SOURCE_NOT_INTACT');assert not (OUT/'forbidden_copy').exists()
    return 'new facts/events, in-place migration/restore and missing source rejected before output publication'
test('copy_only_migration_and_new_fact_rollback_refusals',refusal)

test('idempotent_copy_of_already_upgraded_history',lambda:transcode.transcode_copy(BASE,OUT/'idempotent','V14.51'))
assert before=={name:sha((BASE/name).read_bytes()) for name in before}
raise SystemExit(0 if all(row['status']=='PASS' for row in rows) else 1)
