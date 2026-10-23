#!/usr/bin/env python3
"""Batch A release regression; every mutation is in a disposable world.
Results are written outside the supplied authority root. No fixture errors are PASS.
"""
import argparse,copy,hashlib,importlib.util,json,os,pathlib,shutil,subprocess,sys,tempfile,time,traceback
sys.dont_write_bytecode=True
p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--group',choices=['fast','transaction','fault','all'],default='all');args=p.parse_args()
BASE=args.source.resolve();OUT=args.output.resolve();OUT.mkdir(parents=True,exist_ok=True);RUN=OUT/'worlds';RUN.mkdir(exist_ok=True)
os.environ.update(VOYAGER_ROOT=str(BASE),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm',PYTHONDONTWRITEBYTECODE='1');os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None)
spec=importlib.util.spec_from_file_location('batch_a_test_engine',BASE/'engine.py');api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
results=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save():
 row={'schema':'RELEASE_TEST_EVIDENCE_V1','source_save_set_id':json.loads((BASE/'manifest.json').read_text())['save_set_id'],'engine_sha256':sha(BASE/'engine.py'),'guard_sha256':sha(BASE/'guard.py'),'test_sha256':sha(pathlib.Path(__file__)),'python':sys.version,'group':args.group,'tests':results,'status':'FAIL' if any(r['status']!='PASS' for r in results) else 'PASS','passed':sum(r['status']=='PASS' for r in results),'total':len(results)}
 (OUT/'results.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
def test(name,fn):
 start=time.monotonic()
 try:detail=fn();results.append({'name':name,'status':'PASS','detail':detail,'seconds':round(time.monotonic()-start,3)});print('PASS',name,flush=True)
 except Exception as ex:results.append({'name':name,'status':'FAIL','error':str(ex),'traceback':traceback.format_exc(),'seconds':round(time.monotonic()-start,3)});print('FAIL',name,str(ex),flush=True)
 save()
def require(b,msg='assertion failed'):
 if not b:raise AssertionError(msg)
def rejected(fn,token):
 try:fn()
 except Exception as ex:require(token in str(ex),str(ex));return str(ex)
 raise AssertionError('unexpected acceptance')
def fixture(name):
 target=RUN/name;shutil.copytree(BASE,target,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));return target

def rebind(r):
 m=api.strict_json_load(r/'manifest.json');return api._component_write_manifest_native(r,m['save_version'],m.get('parent_save_set_id'),m.get('migration_lineage'))
def hashes(r):return {n:sha(r/n) for n in api.COMPONENT_FILES}
def cli(r,argv,tag,extra=None,timeout=120):
 env=dict(os.environ,VOYAGER_ROOT=str(r),**(extra or {}));cp=subprocess.run([sys.executable,str(r/'engine.py'),*argv],env=env,cwd=r,capture_output=True,text=True,timeout=timeout)
 (OUT/(tag+'.stdout')).write_text(cp.stdout);(OUT/(tag+'.stderr')).write_text(cp.stderr)
 try:value=json.loads(cp.stdout)
 except Exception:value={'raw':cp.stdout[-2000:]}
 return cp,value

def intent(r,cid='TEST-TASK-01'):
 m=api.strict_json_load(r/'manifest.json');now=api.strict_json_load(r/'state.json')['game_time']
 c={'schema':api.DOMAIN_COMMAND_SCHEMA,'kind':'create_task','command_id':cid,'base_save_set_id':m['save_set_id'],'authorization':'host_intent','authorization_ref':'HOST:'+cid,'actor_id':'PER-COMMANDER-01','task':{'task_id':'TSK-'+cid,'type':'manual','title':'独立测试任务','status':'queued','phase':'waiting'}}
 return {'schema':'HOST_COMMAND_INTENT_V1','decision':'approved','parent_save_set_id':m['save_set_id'],'subject_id':c['actor_id'],'command':c,'instruction_text':'建立此项独立测试任务，不调舰不花费。','evidence_ref':'authenticated-test-host:'+cid,'valid_from':now,'valid_until':now,'targets':api._domain_command_targets(c),'limits':{'uses':1,'gold_units':0,'grey_units':0,'quantity':0}}

if args.group in ('fast','all'):
 def readiness_consistency():
  before=hashes(BASE);report=api.readiness_report(BASE);require(report['status']=='READY_WITH_LIMITATIONS',report)
  for argv in (['startup'],['query','当前金币余额']):
   cp,row=cli(BASE,argv,'healthy_'+argv[0]);require(cp.returncode==0,row);require(row['readiness']['status']==report['status'])
  cp=subprocess.run([sys.executable,str(BASE/'guard.py'),'--resume'],env=dict(os.environ,VOYAGER_ROOT=str(BASE)),capture_output=True,text=True,timeout=120);row=json.loads(cp.stdout);require(cp.returncode==0,row);require(row['readiness']['status']==report['status']);require(hashes(BASE)==before)
  return {'status':report['status'],'authority_unchanged':True}
 test('guard_startup_query_same_readiness_and_no_writes',readiness_consistency)
 def bad_history():
  r=fixture('bad_history');m,e,_=api.read_history_raw(r/'events.jsonl');m['next_seq']-=12;api._native_durable_replace_bytes(r/'events.jsonl',api._history_replace_metadata_bytes((r/'events.jsonl').read_bytes(),m));rebind(r);before=hashes(r);report=api.readiness_report(r);require(report['status']=='BLOCKED');require(report['layers']['history']['status']=='FAIL')
  for argv in (['startup'],['query','当前金币余额']):
   cp,row=cli(r,argv,'bad_'+argv[0]);require(cp.returncode!=0 and row['readiness']['status']=='BLOCKED',row)
  cp=subprocess.run([sys.executable,str(r/'guard.py'),'--resume'],env=dict(os.environ,VOYAGER_ROOT=str(r)),capture_output=True,text=True,timeout=120);require(cp.returncode!=0 and json.loads(cp.stdout)['readiness']['status']=='BLOCKED');require(hashes(r)==before)
  plan=api.consistency_repair_plan(r);require(any(x['kind']=='history_metadata' for x in plan['changes']))
  return 'bad metadata blocked all ordinary entrypoints, restricted plan still available'
 test('bad_history_never_fake_ready',bad_history)
 def bad_sequence():
  r=fixture('bad_sequence');rows=(r/'events.jsonl').read_bytes().splitlines(keepends=True);rec=json.loads(rows[-1]);rec['seq']+=1;rows[-1]=(json.dumps(rec,ensure_ascii=False)+'\n').encode();(r/'events.jsonl').write_bytes(b''.join(rows));rebind(r)
  return rejected(lambda:api.consistency_repair_plan(r),'seq discontinuity')
 test('sequence_gap_not_metadata_repair',bad_sequence)
 def terminal_scene():
  s=api.strict_json_load(BASE/'state.json');t=api.strict_json_load(BASE/'tasks.json');reg=s['engine_runtime']['scene_registry_v1'];rec=next(v for v in reg['records'].values() if v['phase']=='closed');tid='TSK-ARCHIVED-TEST';t.setdefault('recent_completed_tasks',[]).append({'task_id':tid,'status':'completed'});rec['task_id']=tid
  require(api._scene_integrity_report(s,t)['status']=='PASS');rec['phase']='open';rec['status']='active';require(api._scene_integrity_report(s,t)['status']=='FAIL');return 'terminal task is valid for closed scene only'
 test('closed_scene_survives_task_archive',terminal_scene)
 def clock_coverage():
  s=api.strict_json_load(BASE/'state.json');rules=api.strict_json_load(BASE/'rules.json')['runtime_rules'];original=copy.deepcopy(s['engine_runtime']['long_horizon']['hazard_clocks']);require(all(c['last_evaluated']=='8363-12-02T12:00:00' for c in original.values()))
  target=api.parse_iso(s['game_time'])+api.dt.timedelta(seconds=60);a=api.preview_long_horizon(s,rules,target);b=api.preview_long_horizon(s,rules,target);require(a==b);require(not a['events']);require(s['engine_runtime']['long_horizon']['hazard_clocks']==original)
  nexts=copy.deepcopy(s);tasks=api.strict_json_load(BASE/'tasks.json');observed=nexts['shadow_fleet']['current_location']['as_of'];api._set_runtime_time(nexts,tasks,'',target,rules);require(nexts['shadow_fleet']['current_location']['as_of']==observed);require(api._location_coverage_valid(nexts));api._set_runtime_time(nexts,tasks,'',target+api.dt.timedelta(seconds=60),rules);require(api._location_coverage_valid(nexts));require(api._risk_window_report(nexts)['status']!='FAIL')
  broken=copy.deepcopy(s);broken['engine_runtime']['risk_gap_registry_v1']={};rejected(lambda:api.preview_long_horizon(broken,rules,target),'UNCOVERED_INTERVAL');return {'deterministic':True,'actual_evaluation_timestamp_preserved':True,'future_two_windows':True}
 test('risk_gap_truth_determinism_and_future_windows',clock_coverage)
 def location():
  s=api.strict_json_load(BASE/'state.json');require(api._location_coverage_valid(s));s['shadow_fleet']['current_location']['time_semantics']['verified_through']='8363-12-02T12:00:00';require(not api._location_coverage_valid(s));return 'observation and validated-through timestamps have distinct contracts'
 test('location_time_semantics',location)
 def auth_rejections():
  r=BASE;e=intent(r);s=api.strict_json_load(r/'state.json');before=hashes(r)
  rejected(lambda:api.domain_command_packet(r,e['command'],None,'test',True),'TRUSTED_BOUNDARY')
  for field,value,token in [('subject_id','OTHER','SUBJECT'),('parent_save_set_id','OLD','PARENT'),('valid_until','8360-01-01T00:00:00','EXPIRED'),('targets',[],'TARGET')]:
   bad=copy.deepcopy(e);bad[field]=value;rejected(lambda:api.host_intent_command(r,bad,None,True),token)
  bad=copy.deepcopy(e);bad['limits']['uses']=0;rejected(lambda:api.host_intent_command(r,bad,None,True),'LIMIT')
  bad=copy.deepcopy(e);bad['command']['authorized']=True;rejected(lambda:api.host_intent_command(r,bad,None,True),'CLAIM_FORBIDDEN')
  bad=copy.deepcopy(e);bad['command']['base_save_set_id']='OLD';rejected(lambda:api.host_intent_command(r,bad,None,True),'STALE_BASE')
  require(hashes(r)==before);return 'self-approval, wrong subject, parent, expiry, targets, budget and stale base rejected without writes'
 test('authorization_negative_matrix',auth_rejections)
 def extension():
  r=fixture('extensions');m=api.strict_json_load(r/'manifest.json');policy=copy.deepcopy(m['asset_policy']);m['x_vendor']={'a':1};(r/'manifest.json').write_text(json.dumps(m));new=rebind(r);require(new['asset_policy']==policy and new['x_vendor']=={'a':1});new['required_extensions']=['UNKNOWN'];(r/'manifest.json').write_text(json.dumps(new));return rejected(lambda:rebind(r),'UNKNOWN_REQUIRED')
 test('manifest_policy_roundtrip_and_required_extension_gate',extension)
 def modes():
  spec=importlib.util.spec_from_file_location('runtime_test',BASE/'development/devsrc/runtime.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);dev,_=mod.load(BASE/'engine.py');require(dev._risk_window_report(api.strict_json_load(BASE/'state.json'))==api._risk_window_report(api.strict_json_load(BASE/'state.json')));require(dev.domain_command_catalog(BASE)['kinds']==api.domain_command_catalog(BASE)['kinds']);return 'development and bundled release contracts equivalent'
 test('development_release_equivalence',modes)

if args.group in ('transaction','all'):
 def task_commit():
  r=fixture('task_commit');before=api.strict_json_load(r/'state.json');e=intent(r);result=api.host_intent_command(r,e,'V14.47');require(result.get('committed'),result);h=hashes(r);again=api.host_intent_command(r,e,'V14.48');require(again['status']=='ALREADY_APPLIED');require(hashes(r)==h)
  changed=copy.deepcopy(e);changed['command']['task']['title']='changed';rejected(lambda:api.host_intent_command(r,changed,'V14.48'),'DIFFERENT_PAYLOAD');after=api.strict_json_load(r/'state.json');require(after['game_time']==before['game_time']);require(after['engine_runtime']['finance_runtime']==before['engine_runtime']['finance_runtime']);require(after['shadow_fleet']['current_location']==before['shadow_fleet']['current_location'])
  cp,boot=cli(r,['startup'],'committed_boot');require(cp.returncode==0,boot);require(boot['save_set_id']==result['save_set_id']);return {'committed':True,'replay_once':True,'cold_boot':True}
 test('legal_task_action_commit_replay_and_cold_boot',task_commit)
 def purchase():
  r=fixture('purchase');q=api.calculate_price_quote({'item_id':'XILU-ORDINARY_ROOM_NIGHT','unit':'晚','quantity':1,'currency':'gold','region':'熄炉-9','transaction_type':'service'},r);require(q['status']=='VALID',q)
  receipt={'settlement_id':'TEST-SERVICE','quote_id':q['quote_id'],'binding_sha256':q['binding_sha256'],'direction':'debit','account':'fleet','status':'completed','cash_amount':q['total'],'asset_disposition_verified':True}
  # Synthetic completed-delivery evidence is explicitly confined to this fixture.
  ev={'event_id':'TEST-DELIVERY','type':'system','game_time':api.strict_json_load(r/'state.json')['game_time'],'summary':'TEST ONLY completed room service receipt','source':'isolated acceptance fixture','changes':[],'confirmed_price_settlement':receipt};api._append_engine_history(r/'events.jsonl',ev);rebind(r);q=api.calculate_price_quote(q['request'],r)
  e=intent(r,'TEST-PURCHASE');c=e['command'];c.update(kind='settle_price',settlement_id='TEST-SERVICE',quote=q,direction='debit',account='fleet',source_event_id='TEST-DELIVERY');c.pop('task');e['parent_save_set_id']=c['base_save_set_id']=api.strict_json_load(r/'manifest.json')['save_set_id'];e['targets']=api._domain_command_targets(c);e['limits'].update(gold_units=20,quantity=1);e['instruction_text']='支付已确认交付的普通客房一晚，20铜币。'
  before=api.strict_json_load(r/'state.json')['engine_runtime']['finance_runtime']['funds_units']['gold'];result=api.host_intent_command(r,e,'V14.47');after=api.strict_json_load(r/'state.json')['engine_runtime']['finance_runtime']['funds_units']['gold'];require(before-after==20,(before,after,result));h=hashes(r);require(api.host_intent_command(r,e,'V14.48')['status']=='ALREADY_APPLIED');require(hashes(r)==h);return 'completed service purchase: trusted scope + quote + delivery evidence + exact cash + permanent once-only receipt'
 test('confirmed_purchase_full_transaction',purchase)

if args.group in ('fault','all'):
 # Create one valid parent/target pair, then inject partial writes into fresh copies.
 # Separate real processes die at actual commit hooks for each point.
 for phase in ('after_journal','after_component','after_manifest','after_receipt','after_cleanup'):
  def fault(phase=phase):
   r=fixture('fault_'+phase);e=intent(r,'FAULT-'+phase);request=OUT/(phase+'_envelope.json');request.write_text(json.dumps(e));script="import importlib.util,json,pathlib,os; r=pathlib.Path(os.environ['VOYAGER_ROOT']); spec=importlib.util.spec_from_file_location('test_worker',r/'engine.py'); a=importlib.util.module_from_spec(spec); spec.loader.exec_module(a); a.host_intent_command(r,json.loads(pathlib.Path(os.environ['TEST_ENVELOPE']).read_text()),'V14.47')"
   cp=subprocess.run([sys.executable,'-c',script],env=dict(os.environ,VOYAGER_ROOT=str(r),VOYAGER_COMMIT_KILL=phase,TEST_ENVELOPE=str(request)),capture_output=True,text=True,timeout=180);(OUT/(phase+'_worker.stderr')).write_text(cp.stderr);require(cp.returncode==86,cp.stderr[-3000:]);jpath=r/'.runtime/native_commit_journal.json';j=api.strict_json_load(jpath) if jpath.exists() else None
   spec=importlib.util.spec_from_file_location('recover_'+phase,r/'guard.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
   if j:
    with g.guard_lock(r):m,errors=g.recover_interrupted_commit(r)
    require(not errors,errors);require(m['save_version']==('V14.46' if phase in ('after_journal','after_component') else 'V14.47'))
    rejected(lambda:g.write_journal(r,jpath,j),'FINALIZED_TRANSACTION')
   require(not g.active_journal(r,'native_commit_journal.json'));report=api.readiness_report(r);require(report['status']!='BLOCKED',report)
   return {'killed_at':phase,'outcome':'parent' if phase in ('after_journal','after_component') else 'target','journal_clean':True,'late_journal_refused':bool(j)}
  test('process_death_'+phase,fault)
 def unknown():
  r=fixture('unknown');e=intent(r,'UNKNOWN');request=OUT/'unknown_envelope.json';request.write_text(json.dumps(e));script="import importlib.util,json,pathlib,os; r=pathlib.Path(os.environ['VOYAGER_ROOT']); spec=importlib.util.spec_from_file_location('worker',r/'engine.py'); a=importlib.util.module_from_spec(spec); spec.loader.exec_module(a); a.host_intent_command(r,json.loads(pathlib.Path(os.environ['TEST_ENVELOPE']).read_text()),'V14.47')";cp=subprocess.run([sys.executable,'-c',script],env=dict(os.environ,VOYAGER_ROOT=str(r),VOYAGER_COMMIT_KILL='after_component',TEST_ENVELOPE=str(request)),capture_output=True,text=True,timeout=180);require(cp.returncode==86,cp.stderr[-1000:]);(r/'tasks.json').write_bytes((r/'tasks.json').read_bytes()+b' ');before=hashes(r);g=api._repair_guard_module(r)
  with g.guard_lock(r):m,err=g.recover_interrupted_commit(r)
  require(m is None and any('UNKNOWN_MODIFICATION' in e for e in err),err);require(hashes(r)==before);require((r/'.runtime/native_commit_journal.json').exists());return 'unknown bytes and journal retained; no overwrite'
 test('unknown_writer_bytes_protected',unknown)
save();raise SystemExit(1 if any(r['status']!='PASS' for r in results) else 0)
