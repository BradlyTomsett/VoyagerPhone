#!/usr/bin/env python3
"""Reproducible bug regressions; every write is in an isolated output tree."""
import sys
sys.dont_write_bytecode=True
import argparse,contextlib,hashlib,hmac,importlib.util,io,json,os,pathlib,shutil,threading,time,traceback,zipfile
P=pathlib.Path;p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);args=p.parse_args();BASE=args.source.resolve();OUT=args.output.resolve();
if OUT==BASE or BASE in OUT.parents:p.error('Output must be outside the supplied source tree')
OUT.mkdir(parents=True,exist_ok=False);ROWS=[]
os.environ.update(VOYAGER_ROOT=str(BASE),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm');os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None)
def load(p):
 if p.name=='engine.py':os.environ['VOYAGER_ROOT']=str(p.parent)
 s=importlib.util.spec_from_file_location('x'+str(time.time_ns()),p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
a=load(BASE/'engine.py');g=load(BASE/'guard.py')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def clone(n):
 r=OUT/n;shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));return r
def test(name,fn):
 start=time.monotonic()
 try:detail=fn();row={'name':name,'status':'PASS','detail':detail}
 except Exception as ex:row={'name':name,'status':'FAIL','error':str(ex),'trace':traceback.format_exc()}
 row['seconds']=round(time.monotonic()-start,3);ROWS.append(row);print(row['status'],name,flush=True)
 (OUT/'results.json').write_text(json.dumps({'status':'PASS' if all(x['status']=='PASS' for x in ROWS) else 'FAIL','source_save_set_id':a.read_json(BASE/'manifest.json')['save_set_id'],'engine_sha256':sha(BASE/'engine.py'),'guard_sha256':sha(BASE/'guard.py'),'test_sha256':sha(P(__file__)),'manifest_sha256':sha(BASE/'manifest.json'),'tests':ROWS},ensure_ascii=False,indent=2)+'\n')
def pack(r,p):
 m=json.loads((r/'manifest.json').read_text());names=['manifest.json',*m['components'],*[x['path'] for x in m['cold_archives'].values()],*m['development_sources']['files']]
 with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
  for n in names:z.write(r/n,n)
def variant(r,mode):
 m=json.loads((r/'manifest.json').read_text())
 if mode=='development':
  p=r/'development/README.md';p.write_text(p.read_text()+'\nIsolated documentation fork fixture.\n');m['development_sources']['files']['development/README.md']=sha(p)
 else:m['asset_policy']['isolated_manifest_marker']='new requested policy metadata'
 (r/'manifest.json').write_text(json.dumps(m,ensure_ascii=False))
def expected_exit(fn,code):
 try:fn()
 except SystemExit as ex:assert code in str(ex),ex;return
 raise AssertionError('Expected refusal: '+code)
def source_forks():
 r=clone('fork_world');d=OUT/'fork_zips';d.mkdir();one=d/'VOYAGER_SOURCE_V14.49_a.zip';two=d/'VOYAGER_SOURCE_V14.49_b.zip';pack(r,one);variant(r,'development');pack(r,two);assert not g.inspect_transport(one)[1] and not g.inspect_transport(two)[1]
 expected_exit(lambda:g.find_transport(d),'MANIFEST_FORK')
 direct=clone('mixed_world');shutil.copyfile(two,direct/two.name);expected_exit(lambda:g.select_source(direct),'MANIFEST_FORK')
 two.unlink();shutil.copyfile(one,two);assert g.find_transport(d) in (one,two)
 return 'ZIP/ZIP and directory/ZIP metadata forks refused; identical duplicate packages allowed'
test('full_manifest_forks_and_identical_duplicates',source_forks)
def cache_manifest():
 r=clone('cache_source');one=OUT/'cache_a.zip';two=OUT/'cache_b.zip';pack(r,one);variant(r,'metadata');pack(r,two);d=OUT/'extraction';d.mkdir();root,old=g.extract_transport(one,d);old_bytes=(root/'manifest.json').read_bytes();root,new=g.extract_transport(two,d)
 assert new['asset_policy'].get('isolated_manifest_marker')=='new requested policy metadata','stale manifest returned'
 assert json.loads((root/'manifest.json').read_text())==new
 assert any((p/'manifest.json').read_bytes()==old_bytes for p in root.parent.glob(root.name+'.invalid.*')),'old cache evidence not preserved'
 return 'explicitly selected manifest replaces cached metadata, prior cache quarantined'
test('cached_extraction_matches_requested_entire_manifest',cache_manifest)
def changed_since_inspection():
 r=clone('inspection_source');p=OUT/'inspected.zip';pack(r,p);inspected,err=g.inspect_transport(p);assert not err;variant(r,'metadata');pack(r,p);d=OUT/'inspection';d.mkdir();expected_exit(lambda:g.extract_transport(p,d,inspected),'SOURCE_CHANGED_SINCE_INSPECTION');return 'source swap between inspection/extraction refused'
test('inspection_and_extraction_identity_bound',changed_since_inspection)
def advanced_cache():
 r=clone('advanced_source');p=OUT/'advanced.zip';pack(r,p);d=OUT/'advanced_delivery';d.mkdir();root,m=g.extract_transport(p,d);b=load(root/'engine.py');old=m['save_set_id'];b._component_write_manifest_native(root,'V14.60',old);before=(root/'manifest.json').read_bytes();expected_exit(lambda:g.extract_transport(p,d),'CACHED_SOURCE_DIVERGED');assert (root/'manifest.json').read_bytes()==before;return 'a valid cached save with a newer/different SID is retained; older transport cannot replace saved progress'
test('advanced_cached_game_save_never_replaced',advanced_cache)
def damaged_direct():
 r=clone('damaged_direct');p=r/'VOYAGER_SOURCE_V14.49_healthy.zip';pack(r,p);(r/'development/README.md').write_text('isolated damaged member');root,m,selection=g.select_source(r);assert root!=r and selection['kind']=='zip';assert g.development_intact(root,m);return 'damaged materialized development cannot outrank a complete healthy ZIP'
test('direct_development_binding_is_checked_before_selection',damaged_direct)

def key_publication():
 r=clone('key_race');b=load(r/'engine.py');entered=threading.Event();resume=threading.Event();real=b.os.fdopen;errors=[]
 def delayed(*args,**kw):
  stream=real(*args,**kw)
  if threading.current_thread().name=='KEY-WRITER':entered.set();assert resume.wait(10)
  return stream
 def writer():
  try:b._derived_key(r)
  except Exception as ex:errors.append(str(ex))
 b.os.fdopen=delayed;t=threading.Thread(target=writer,name='KEY-WRITER');t.start()
 try:
  assert entered.wait(10),'key writer did not reach controlled publication point'
  key=b._derived_key(r);assert len(key)==32
 finally:resume.set();t.join(10);b.os.fdopen=real
 assert not t.is_alive() and not errors,errors;assert (r/'.runtime/derived_cache.key').read_bytes()==key
 return 'two concurrent initializers see only one complete 32-byte key'
test('shared_reader_cache_key_atomic_publication',key_publication)
def optional_cache():
 r=clone('bad_cache_key');runtime=r/'.runtime';runtime.mkdir();(runtime/'derived_cache.key').write_bytes(b'');b=load(r/'engine.py');before={n:sha(r/n) for n in b.COMPONENT_FILES};report=b.readiness_report(r);assert report['status']=='READY_WITH_LIMITATIONS',report
 out=b.query_packet(r,'当前金币余额');assert out['status']=='COMPLETE';assert before=={n:sha(r/n) for n in b.COMPONENT_FILES}
 binding={'test':'invalid-key'};body={'binding':binding,'value':{'bad':True}};mac=hmac.new(b'',json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode(),'sha256').hexdigest();(runtime/'test_empty_key.json').write_text(json.dumps({'body':body,'mac':mac}));assert b._derived_read(r,'test_empty_key.json',binding) is None
 original=b._native_atomic_json
 def fail(*args,**kw):raise OSError('isolated cache I/O failure')
 (runtime/'derived_cache.key').unlink();b._native_atomic_json=fail
 try:assert b._derived_write(r,'unwritable.json',{}, {}) is False
 finally:b._native_atomic_json=original
 return 'corrupt/empty cache key and cache write failure do not block healthy authority; empty-key MAC ignored'
test('derived_cache_damage_is_optional_not_fatal',optional_cache)
def missing_source():
 cases=['archive','component','development']
 for case in cases:
  r=clone('missing_'+case);b=load(r/'engine.py')
  path=next((r/'archives').glob('history*')) if case=='archive' else r/('tasks.json' if case=='component' else 'development/README.md');path.unlink();report=b.readiness_report(r);assert report['status']=='BLOCKED' and report['capabilities']['read'] is False,report
  out=io.StringIO();os.environ['VOYAGER_ROOT']=str(r)
  with contextlib.redirect_stdout(out):code=b.main(['readiness'])
  assert code!=0 and json.loads(out.getvalue())['status']=='BLOCKED',out.getvalue()
 r=clone('closing_source_change');b=load(r/'engine.py');detected=False
 try:
  with b.SnapshotContext(r) as ctx:
   assert ctx.validated_report()['status']=='READY_WITH_LIMITATIONS'
   next((r/'archives').glob('history*')).unlink()
 except b.EngineError as ex:assert 'SNAPSHOT_CHANGED_DURING_READ' in str(ex),ex;detected=True
 assert detected,'missing-file fallback bypassed closing byte barrier'
 return 'missing members yield structured BLOCKED; deleting a member during a read still trips the closing source-change barrier'
test('missing_members_have_structured_blocking_readiness',missing_source)
raise SystemExit(1 if any(x['status']=='FAIL' for x in ROWS) else 0)
