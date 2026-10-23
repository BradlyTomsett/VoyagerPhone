import sys
sys.dont_write_bytecode=True
import copy,hashlib,importlib.util,json,os,pathlib,shutil,time,traceback,zipfile,statistics,platform
P=pathlib.Path;BASE=P(os.environ['VOYAGER_TEST_SOURCE']);OUT=P(os.environ['VOYAGER_STEP18_OUTPUT']);OUT.mkdir();rows=[]
def load(p):
 s=importlib.util.spec_from_file_location('m'+str(time.time_ns()),p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
a=load(BASE/'engine.py');g=load(BASE/'guard.py')
def clone(n):
 r=OUT/n;shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));return r
def test(name,fn):
 start=time.monotonic()
 try:detail=fn();rows.append({'name':name,'status':'PASS','detail':detail,'seconds':round(time.monotonic()-start,3)})
 except Exception as ex:rows.append({'name':name,'status':'FAIL','error':str(ex),'trace':traceback.format_exc()})
 print(rows[-1]['status'],name,flush=True);(OUT/'results.json').write_text(json.dumps({'status':'FAIL' if any(x['status']=='FAIL' for x in rows) else 'PASS','tests':rows},ensure_ascii=False,indent=2)+'\n')
def pack(r,path):
 m=a.read_json(r/'manifest.json');names=['manifest.json',*m['components'],*[x['path'] for x in m['cold_archives'].values()],*m['development_sources']['files']]
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
  for n in names:z.write(r/n,n)
def forks():
 dest=OUT/'forks';dest.mkdir();r=clone('fork_a');p=dest/'VOYAGER_SOURCE_V14.48_a.zip';pack(r,p);assert not g.inspect_transport(p)[1]
 state=a.read_json(r/'state.json');state['step18_isolated_fork_fixture']=True;a._write_authority_json(r/'state.json',state);m=a.read_json(r/'manifest.json');a._component_write_manifest_native(r,m['save_version'],m.get('parent_save_set_id'),m.get('migration_lineage'));q=dest/'VOYAGER_SOURCE_V14.48_b.zip';pack(r,q);assert not g.inspect_transport(q)[1]
 try:g.find_transport(dest)
 except SystemExit as ex:assert 'SOURCE_ZIP_FORK' in str(ex),ex
 else:raise AssertionError('same-version fork was selected')
 return 'two individually bound same-version forks refused; mtime never resolves ambiguity'
test('same_version_transport_fork_refused',forks)
def delivery():
 r=clone('export_world');b=load(r/'engine.py');m=b.read_json(r/'manifest.json');now=m['game_time'];c={'schema':b.DOMAIN_COMMAND_SCHEMA,'command_id':'EXPORT-ONCE','kind':'create_task','base_save_set_id':m['save_set_id'],'task':{'task_id':'TSK-EXPORT-ONCE','type':'manual','title':'隔离导出重试验收','status':'queued'},'authorization':'host_intent','authorization_ref':'HOST:EXPORT','actor_id':'PER-COMMANDER-01'};e={'schema':'HOST_COMMAND_INTENT_V1','command':c,'subject_id':c['actor_id'],'parent_save_set_id':m['save_set_id'],'instruction_text':'Isolated one task only','evidence_ref':'fixture:EXPORT','decision':'approved','targets':b._domain_command_targets(c),'limits':b._domain_authorization_cost(c),'valid_from':now,'valid_until':now};res=b.host_intent_command(r,e,'V14.50');assert res['status']=='SAVED'
 before={n:b.sha256_file(r/n) for n in b.COMPONENT_FILES};os.environ['VOYAGER_COMMIT_IOFAIL']='export'
 try:failed=b.export_save_set(r,res['save_set_id'])
 finally:os.environ.pop('VOYAGER_COMMIT_IOFAIL',None)
 assert failed['export_status']=='FAILED' and failed['committed'] and failed['retry_action']=='export_only',failed
 os.environ['VOYAGER_DELIVERY_ROOT']=str(OUT/'delivery')
 try:done=b.export_save_set(r,res['save_set_id'])
 finally:os.environ.pop('VOYAGER_DELIVERY_ROOT',None)
 assert done['export_status']=='VERIFIED',done
 assert before=={n:b.sha256_file(r/n) for n in b.COMPONENT_FILES};assert b.host_intent_command(r,e,'V14.51')['status']=='ALREADY_APPLIED'
 p=P(done['path']);digest=b.sha256_file(p);dev=r/'development/tests/step18/common.py';dev.write_text(dev.read_text()+'\n#post-export source modification\n');assert b.sha256_file(p)==digest and not g.inspect_transport(p)[1]
 return {'committed_then_export_failure':True,'only_export_retry':True,'no_business_reexecution':True,'frozen_zip_survives_later_development_changes':True}
test('commit_export_failure_retry_and_frozen_source',delivery)
def performance():
 r=clone('performance');b=load(r/'engine.py')
 with b.SnapshotContext(r) as ctx:assert ctx.validated_report()['status']=='READY_WITH_LIMITATIONS'
 samples=[]
 for i in range(20):
  with b.SnapshotContext(r) as ctx:
   start=time.monotonic();result=b.query_packet(r,'当前金币余额');samples.append(time.monotonic()-start);assert ctx.metrics['history_decodes']==0 and result['status']=='COMPLETE'
 topics=['当前金币余额','当前任务','当前场景','暗影舰队位置'];start=time.monotonic();separate=[b.visible_query_packet(r,x) for x in topics];single=time.monotonic()-start;start=time.monotonic();batch=b.visible_query_batch_packet(r,topics);batched=time.monotonic()-start;assert separate==batch['results']
 return {'samples':20,'warm_query_median_seconds':statistics.median(samples),'warm_query_p95_seconds':sorted(samples)[18],'warm_history_decodes':0,'four_separate_function_seconds':single,'four_topic_batch_seconds':batched,'batch_results_equal':True,'environment':platform.platform(),'measurement_scope':'function body after validated snapshot; no 30% speedup claim, no ChatGPT latency promise'}
test('bounded_warm_queries_and_shared_batch_measurement',performance)
raise SystemExit(1 if any(x['status']=='FAIL' for x in rows) else 0)
