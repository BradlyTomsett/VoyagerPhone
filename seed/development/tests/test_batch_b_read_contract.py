import sys
sys.dont_write_bytecode=True
import contextlib,copy,importlib.util,io,json,os,pathlib,shutil,time
P=pathlib.Path;BASE=P(os.environ['VOYAGER_TEST_SOURCE']).resolve();OUT=P(os.environ['VOYAGER_BATCH_B_OUTPUT']).resolve();OUT.mkdir(parents=True,exist_ok=True);os.environ.update(VOYAGER_ROOT=str(BASE),PYTHONDONTWRITEBYTECODE='1',VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm')
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
a=load(BASE/'engine.py','release');dev=load(BASE/'development/devsrc/runtime.py','dev');b,_=dev.load(BASE/'engine.py');rows=[]
def test(name,fn):
 try:r=fn();rows.append({'name':name,'status':'PASS','detail':r});print('PASS',name,flush=True)
 except Exception as ex:rows.append({'name':name,'status':'FAIL','error':repr(ex)});print('FAIL',name,repr(ex),flush=True)
 (OUT/'results.json').write_text(json.dumps({'status':'FAIL' if any(x['status']=='FAIL' for x in rows) else 'PASS','tests':rows},ensure_ascii=False,indent=2)+'\n')
def clone(name):
 r=OUT/name;shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));return r
def reject(fn,token):
 try:fn()
 except Exception as ex:assert token in str(ex),ex;return
 raise AssertionError('not rejected')
def equivalent():
 for command in (['accountquery'],['query','当前金币余额'],['contentquery','--kind','semantic_rule'],['querybatch','--topics','["当前金币余额","当前任务","当前场景","暗影舰队位置"]']):
  values=[]
  for api in (a,b):
   out=io.StringIO()
   with contextlib.redirect_stdout(out):
    code=api.main(command)
   assert code==0,out.getvalue()
   values.append(json.loads(out.getvalue()))
  assert values[0]==values[1],command
 return 'release engine and checked isolated development modules agree for four public read commands'
test('development_release_behavior_equivalence',equivalent)
def hashes():
 r=clone('bad_source');p=r/'development/devsrc/27_accounts_games.py';p.write_bytes(p.read_bytes()+b'\n# altered\n');mod=load(r/'development/devsrc/runtime.py','bad_dev');reject(lambda:mod.load(r/'engine.py'),'SOURCE_MODULE_DIGEST')
 r=clone('missing_export');p=r/'development/devsrc/SOURCE_MANIFEST.json';m=json.loads(p.read_text());m['responsibilities']['27_accounts_games.py']['exports'].append('missing_required_export');p.write_text(json.dumps(m));mod=load(r/'development/devsrc/runtime.py','missing_dev');reject(lambda:mod.load(r/'engine.py'),'SOURCE_EXPORT_MISSING')
 return 'module tamper and missing exported symbol fail before calling public commands'
test('development_module_hash_and_export_fail_closed',hashes)
def disabled():
 first=a.query_packet(BASE,'当前金币余额');os.environ['VOYAGER_DISABLE_DERIVED_CACHE']='1'
 try:second=a.query_packet(BASE,'当前金币余额')
 finally:os.environ.pop('VOYAGER_DISABLE_DERIVED_CACHE')
 assert first==second;return 'same packet with semantics cache disabled'
test('cache_disabled_result_equivalence',disabled)
def expanded():
 r=clone('history_10x');m=a.read_json(r/'manifest.json');meta,ev,raw=a._history_read_verified(r/'events.jsonl');n=len(ev)*9;start=meta['next_seq'];now=a.read_json(r/'state.json')['game_time'];lines=[]
 for i in range(n):lines.append(json.dumps({'event_id':'SYNTHETIC-ONLY-'+str(i),'seq':start+i,'record_type':'event','type':'system','game_time':now,'summary':'isolated derived history scaling fixture, never released'},separators=(',',':')).encode())
 meta['next_seq']=start+n;data=a._history_replace_metadata_bytes((r/'events.jsonl').read_bytes(),meta,lines);(r/'events.jsonl').write_bytes(data);a._compact_history_file_to_epochs(r/'events.jsonl',64,True);state=a.read_json(r/'state.json');facts=a._history_epoch_runtime_facts(r);state['engine_runtime']['scaling']['history_epoch'].update({k:facts[k] for k in ('compression_recommended','compression_applied')});a._write_authority_json(r/'state.json',state);a._component_write_manifest_native(r,m['save_version'],m.get('parent_save_set_id'),m.get('migration_lineage'))
 with a.SnapshotContext(r) as ctx:report=ctx.validated_report();assert report['status']=='READY_WITH_LIMITATIONS',report['errors']
 with a.SnapshotContext(r) as ctx:
  result=a.query_packet(r,'当前金币余额');assert ctx.metrics['history_decodes']==0 and ctx.metrics['semantic_cache_hits']==1;metrics=copy.deepcopy(ctx.metrics)
 assert result['value']==a.query_packet(BASE,'当前金币余额')['value'];return {'logical_events':start+n-1,'warm_history_decodes':metrics['history_decodes'],'warm_json_parses':metrics['json_parses'],'no_linear_full_history_expansion':True}
test('tenfold_history_exact_query_does_not_expand_cold_history',expanded)
raise SystemExit(1 if any(x['status']=='FAIL' for x in rows) else 0)
