"""Step 2 regression on independent copies. Fixtures derive identifiers from authority."""
from pathlib import Path
import contextlib,copy,hashlib,importlib.util,json,os,shutil,subprocess,sys,tempfile,threading,time
WORK=Path(os.environ.get('VOYAGER_STEP2_TEST_SOURCE',str(Path(__file__).resolve().parents[2]))).resolve()
HERE=Path(os.environ.get('VOYAGER_STEP2_TEST_OUTPUT',tempfile.mkdtemp(prefix='voyager_consistency_tests_'))).resolve();HERE.mkdir(parents=True,exist_ok=True)
INPUT_PATH=Path(os.environ.get('VOYAGER_STEP2_FIXED_INPUTS',str(WORK/'development/tests/step2_fixed_inputs.json')))
RESULTS=[]
os.environ.update(VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm',PYTHONDONTWRITEBYTECODE='1',VOYAGER_ROOT=str(WORK),VOYAGER_DEV_SOURCE_DIR=str(WORK))
spec=importlib.util.spec_from_file_location('step2_engine',WORK/'engine.py');api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
RUN=Path(tempfile.mkdtemp(prefix='regression_',dir=HERE));(RUN/'outputs').mkdir()
def save(): (HERE/'regression_results.json').write_text(json.dumps({'status':'FAIL' if any(not r['passed'] for r in RESULTS) else 'PASS','run_dir':str(RUN),'tests':RESULTS,'passed':sum(r['passed'] for r in RESULTS),'failed':sum(not r['passed'] for r in RESULTS)},ensure_ascii=False,indent=2)+'\n')
def check(name,fn):
 try:
  detail=fn();RESULTS.append({'name':name,'passed':True,'detail':detail});print('PASS',name,flush=True)
 except Exception as ex:RESULTS.append({'name':name,'passed':False,'detail':type(ex).__name__+':'+str(ex)});print('FAIL',name,ex,flush=True)
 save()
def require(value,message='assertion failed'):
 if not value:raise AssertionError(message)
def fixture(name,include_development=True):
 r=RUN/name;ignored=['.runtime','__pycache__','.game_engine.lock']+([] if include_development else ['development'])
 shutil.copytree(WORK,r,ignore=shutil.ignore_patterns(*ignored))
 # A delivered project may already be repaired. Reintroduce only evidence-known
 # metadata/reference mirror drift in the independent fixture, never its economy.
 _,history,_=api._history_read_verified(r/'events.jsonl',validate_metadata=False)
 audits=[e for e in history if e.get('subtype')=='consistency_repair' and isinstance(e.get('repair_plan'),dict)]
 if audits:
  rows=audits[-1]['repair_plan'].get('changes',[]);docs={n:api.strict_json_load(r/n) for n in ('state.json','tasks.json')};changed=False
  for row in rows:
   if row.get('file') not in docs or row.get('kind') not in {'derived_settlement_time','registered_reference_migration','event_stage_mirror'}:continue
   doc=docs[row['file']]
   if api._repair_get(doc,row['path'])==row['new']:api._repair_set(doc,row['path'],row['old']);changed=True
  if changed:
   for n,doc in docs.items():api._native_durable_replace_bytes(r/n,api._authority_json_bytes(doc))
   rebind(r)
 return r
def rebind(root):
 m=json.loads((root/'manifest.json').read_text());return api._component_write_manifest_native(root,m['save_version'],m.get('parent_save_set_id'),m.get('migration_lineage'))
def hashes(root):return {n:api.sha256_file(root/n) for n in ('manifest.json',*api.COMPONENT_DATA_FILES,'engine.py','guard.py')}
def rejects(fn,fragment):
 try:fn()
 except Exception as ex:require(fragment in str(ex),str(ex));return str(ex)
 raise AssertionError('unexpected acceptance')
def cli(root,args,name,extra=None):
 env={**os.environ,'VOYAGER_ROOT':str(root),'VOYAGER_DELIVERY_ROOT':str(RUN/(root.name+'_delivery')),**(extra or {})}
 cp=subprocess.run([sys.executable,str(root/'engine.py'),*args],env=env,cwd=root,text=True,capture_output=True,timeout=180)
 (RUN/'outputs'/(name+'.stdout.json')).write_text(cp.stdout);(RUN/'outputs'/(name+'.stderr.txt')).write_text(cp.stderr)
 try:value=json.loads(cp.stdout)
 except Exception:value={'raw':cp.stdout[-1500:]}
 return cp,value
# Baseline fixture: tools are built; authority data still exactly the step 1 data.
base=fixture('evidence_base');original_hashes=hashes(base);plan=api.consistency_repair_plan(base)
def plan_evidence():
 require(bool(plan['changes']),'provided authority fixture must have evidence-backed repairs')
 require(plan['full_audit_status']==api.run_checks(WORK,full=True,require_manifest=True)['status'])
 require(hashes(base)==original_hashes)
 require(all(r['evidence'] for r in plan['changes']))
 return {'fields':len(plan['changes']),'audit_errors':len(plan['full_audit_errors']),'read_only':True}
check('registered_evidence_plan_preserves_input_bytes',plan_evidence)
check('no_gameplay_authorization_at_repair_cli',lambda: (lambda pair:require(pair[0].returncode!=0 and 'REPAIR_EXPLICIT_DEVELOPER_CONTEXT_REQUIRED' in str(pair[1])))(cli(base,['repairplan'],'context_refusal',{'VOYAGER_DEVELOPER_MODE':'0'})))
def arbitrary_patch():
 bad=copy.deepcopy(plan);bad['changes'].append({'file':'state.json','path':'/game_time','old':'invented','new':'invented'})
 result=rejects(lambda:api.consistency_repair_apply(base,bad),'STALE_OR_UNPROVEN');require(hashes(base)==original_hashes);return result
check('arbitrary_patch_rejected_without_authority_changes',arbitrary_patch)
def stale_plan():
 stale=copy.deepcopy(plan);stale['fingerprint']['engine.py']='0'*64
 return rejects(lambda:api.consistency_repair_apply(base,stale),'STALE_OR_UNPROVEN')
check('stale_dependency_plan_rejected',stale_plan)
def commit_current():
 before_state=json.loads((base/'state.json').read_text());before_tasks=(base/'tasks.json').read_bytes();before_physical=(base/'events.jsonl').read_bytes().splitlines(keepends=True)
 _,before_events,before_raw=api._history_read_verified(base/'events.jsonl',validate_metadata=False);cold={n:api.sha256_file(base/n) for n in api._component_cold_archives(json.loads((base/'manifest.json').read_text()))}
 ambient=os.environ.get('VOYAGER_DEV_SOURCE_DIR');os.environ['VOYAGER_DEV_SOURCE_DIR']=str(RUN/'unrelated_development')
 try:result=api.consistency_repair_apply(base,plan)
 finally:
  if ambient is None:os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None)
  else:os.environ['VOYAGER_DEV_SOURCE_DIR']=ambient
 (HERE/'fixture_commit_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 expected=copy.deepcopy(before_state)
 for row in plan['changes']:
  if row['file']=='state.json':api._repair_set(expected,row['path'],row['new'])
 require(json.loads((base/'state.json').read_text())==expected);require((base/'tasks.json').read_bytes()==before_tasks)
 meta,events,raw=api.read_history_raw(base/'events.jsonl');require(raw[:-1]==before_raw);require(events[-1]['seq']+1==meta['next_seq']);require(len(events)==len(before_events)+1)
 after_physical=(base/'events.jsonl').read_bytes().splitlines(keepends=True);require(after_physical[1:-1]==before_physical[1:])
 require(all(api.sha256_file(base/n)==h for n,h in cold.items()));require(set(result['unresolved_errors']).issubset(set(plan['full_audit_errors'])))
 return {'fields':result['changed_fields'],'existing_events_unchanged':len(before_events),'archives_unchanged':len(cold),'full_audit':result['full_audit_status'],'remaining_groups':len(result['unresolved_errors'])}
check('atomic_proven_repair_exact_allowlist_and_raw_history',commit_current)
def repeated():
 h=hashes(base);new_plan=api.consistency_repair_plan(base);require(new_plan['status']=='NO_PROVEN_REPAIR');result=api.consistency_repair_apply(base,new_plan)
 require(result['status']=='NO_CHANGE' and hashes(base)==h);rejects(lambda:api.consistency_repair_apply(base,plan),'STALE_OR_UNPROVEN');return 'new plan no-op; obsolete plan rejected; no duplicate event'
check('repeat_repair_no_duplicate_audit_or_money_change',repeated)
def metadata_stale():
 r=fixture('metadata_stale');m,events,_=api.read_history_raw(r/'events.jsonl');m['next_seq']=events[-1]['seq'];api._native_durable_replace_bytes(r/'events.jsonl',api._history_replace_metadata_bytes((r/'events.jsonl').read_bytes(),m));rebind(r)
 rejects(lambda:api.read_history_raw(r/'events.jsonl'),'next_seq mismatch')
 cp,v=cli(r,['query',json.loads(INPUT_PATH.read_text())['ordinary_query']],'stale_normal_refusal');require(cp.returncode!=0,'ordinary load should reject stale metadata')
 p=api.consistency_repair_plan(r);row=next(x for x in p['changes'] if x['kind']=='history_metadata');require(row['new']==events[-1]['seq']+1)
 result=api.consistency_repair_apply(r,p);require(result['changed_fields']==len(p['changes']));require(api.read_history_raw(r/'events.jsonl')[0]['next_seq']==events[-1]['seq']+2)
 return {'ordinary_load_refused':True,'restricted_entry_repaired':True,'derived_from_last_logical_seq':True}
check('stale_metadata_blocked_normal_load_but_restricted_repair_works',metadata_stale)
def gap():
 r=fixture('sequence_gap');rows=(r/'events.jsonl').read_bytes().splitlines(keepends=True);index=max(i for i,x in enumerate(rows) if json.loads(x).get('seq'));event=json.loads(rows[index]);event['seq']+=1;rows[index]=(json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n').encode();(r/'events.jsonl').write_bytes(b''.join(rows));rebind(r)
 return rejects(lambda:api.consistency_repair_plan(r),'seq discontinuity')
check('sequence_gap_never_repaired_as_next_seq',gap)
def bad_archive(rehash=False,payload=False):
 r=fixture('archive_'+str(rehash)+'_'+str(payload));m=json.loads((r/'manifest.json').read_text());rel=next(row['path'] for row in m['cold_archives'].values() if 'seq_start' in row);p=r/rel
 if payload:
  import gzip
  obj=json.loads(gzip.decompress(p.read_bytes()));obj['payload']['event_count']+=1;p.write_bytes(gzip.compress(json.dumps(obj,ensure_ascii=False).encode()))
 else:p.write_bytes(p.read_bytes()[:-10]+b'corrupted')
 if rehash:
  for row in m['cold_archives'].values():
   if row['path']==rel:row['file_sha256']=api.sha256_file(p)
  (r/'manifest.json').write_text(json.dumps(m,ensure_ascii=False))
 h=hashes(r);message=rejects(lambda:api.consistency_repair_plan(r),'REPAIR_');require(hashes(r)==h);return message
check('cold_archive_byte_corruption_refused',lambda:bad_archive(False))
check('cold_archive_rebound_corruption_still_refused',lambda:bad_archive(True))
check('cold_wrapper_payload_digest_corruption_refused',lambda:bad_archive(True,True))
def registry_error(duplicate=False):
 r=fixture('registry_duplicate' if duplicate else 'registry_invalid');m=json.loads((r/'manifest.json').read_text());row=copy.deepcopy(next(iter(m['cold_archives'].values())))
 if not duplicate:row['path']='../invalid-evidence'
 m['cold_archives']['TEST-'+api._repair_digest(row)[:16]]=row;(r/'manifest.json').write_text(json.dumps(m,ensure_ascii=False))
 return rejects(lambda:api.consistency_repair_plan(r),'COLD_REGISTRY_PATH_INVALID_OR_DUPLICATE')
check('invalid_cold_registry_entry_never_silently_ignored',lambda:registry_error(False))
check('duplicate_cold_registry_path_never_silently_ignored',lambda:registry_error(True))
def range_error():
 r=fixture('range_error');m=json.loads((r/'manifest.json').read_text());entry=next(row for row in m['cold_archives'].values() if 'seq_start' in row);entry['seq_end']+=1;(r/'manifest.json').write_text(json.dumps(m,ensure_ascii=False));return rejects(lambda:api.consistency_repair_plan(r),'ARCHIVE_RANGE')
check('manifest_archive_range_mismatch_refused',range_error)
def empty_protocol():
 p=RUN/'empty.jsonl';p.write_bytes(b'{"record_type":"metadata","next_seq":1}\n');m,e,_=api.read_history_raw(p);require(api._history_expected_next_seq(e)==m['next_seq']==1);return 'existing empty-history sequence convention retained'
check('empty_history_protocol',empty_protocol)
def typed_sequence():
 p=RUN/'typed_sequence.jsonl';p.write_bytes(b'{"record_type":"metadata","next_seq":2}\n{"seq":true,"event_id":"TEST"}\n');return rejects(lambda:api.read_history_raw(p),'seq discontinuity')
check('boolean_sequence_is_not_integer_sequence',typed_sequence)
def physical_append():
 p=RUN/'append.jsonl';m={'record_type':'metadata','next_seq':1};p.write_bytes((json.dumps(m)+'\r\n\r\n').encode());state=api.strict_json_load(WORK/'state.json');event={'event_id':'TEST-'+api.sha256_file(p)[:20],'game_time':state['game_time'],'type':'system','summary':'regression append','changes':[],'source':'isolated regression'}
 api._append_engine_history(p,event);before=p.read_bytes();m,events,_=api.read_history_raw(p)
 event2={**event,'event_id':event['event_id']+'-next'};api._append_engine_history(p,event2);require(p.read_bytes().splitlines(keepends=True)[1:-1]==before.splitlines(keepends=True)[1:]);require(api.read_history_raw(p)[0]['next_seq']==events[-1]['seq']+2)
 unchanged=p.read_bytes();rejects(lambda:api._append_engine_history(p,event2),'DUPLICATE');require(p.read_bytes()==unchanged);rejects(lambda:api._append_engine_history(p,{**event,'event_id':''}),'REQUIRED');return 'CRLF/blank lines preserved; duplicate/missing IDs refused'
check('single_append_preserves_physical_bytes_and_ids',physical_append)
def rollback_batch():
 p=RUN/'batch.jsonl';p.write_bytes(b'{"record_type":"metadata","next_seq":1}\n');before=p.read_bytes();event={'event_id':'TEST-'+api.sha256_file(p)[:16],'game_time':api.strict_json_load(WORK/'state.json')['game_time'],'type':'system','summary':'isolated batch','changes':[],'source':'regression'}
 try:
  with api._history_append_batch(p):api._append_engine_history(p,event);raise RuntimeError('fault')
 except RuntimeError:pass
 require(p.read_bytes()==before)
 with api._history_append_batch(p):
  api._append_engine_history(p,event)
  try:
   with api._history_append_batch(p):api._append_engine_history(p,{**event,'event_id':event['event_id']+'-rolledback'});raise RuntimeError('inner fault')
  except RuntimeError:pass
  api._append_engine_history(p,{**event,'event_id':event['event_id']+'-committed'})
 meta,events,_=api.read_history_raw(p);require(len(events)==2 and meta['next_seq']==events[-1]['seq']+1);require(not api._HISTORY_APPEND_BATCHES);return 'outer exception rollback; caught nested exception rollback; one final flush'
check('single_batch_nested_rollback_and_cleanup',rollback_batch)
def concurrent_append():
 p=RUN/'threads.jsonl';p.write_bytes(b'{"record_type":"metadata","next_seq":1}\n');errors=[];event={'game_time':api.strict_json_load(WORK/'state.json')['game_time'],'type':'system','summary':'isolated concurrent append','changes':[],'source':'regression'}
 def append(i):
  try:api._append_engine_history(p,{**event,'event_id':'TEST-'+api.sha256_file(WORK/'manifest.json')[:16]+'-'+str(i)})
  except BaseException as ex:errors.append(str(ex))
 ts=[threading.Thread(target=append,args=(i,)) for i in range(4)]
 for t in ts:t.start()
 for t in ts:t.join()
 m,e,_=api.read_history_raw(p);require(not errors and len(e)==len(ts) and m['next_seq']==e[-1]['seq']+1,str(errors));return 'independent thread batch ownership + file lock; contiguous append'
check('concurrent_append_no_half_event_or_duplicate_sequence',concurrent_append)
def stage_semantics():
 facts=api._repair_preflight(WORK);t=copy.deepcopy(facts['tasks']);state=copy.deepcopy(facts['state']);reg=state['engine_runtime']['scene_registry_v1'];ref=next(iter(reg['legacy_closed'].values()));event=api.get_by_path(state,ref['source_path']);task=next(x for x in t['active_tasks'] if x.get('task_data',{}).get('state_current_path') and 'current_event_stage' in x.get('task_data',{}));status=task['status'];phase=task['phase'];task['task_data'].update(current_event_state_path=ref['source_path'],current_event_id=event['event_id'],current_event_stage=task['status'])
 changes=[];api._repair_event_stages({'tasks':t,'state':state},changes,[]);require(len(changes)==1 and changes[0]['new']==api.authoritative_event_stage(event));require(task['status']==status and task['phase']==phase)
 event={**event,'status':status,'phase':phase};require(api.authoritative_event_stage(event)==phase);return 'lifecycle/task phase remain independent; only registered event-stage mirror synchronized'
check('lifecycle_event_phase_and_task_phase_do_not_collapse',stage_semantics)
def ambiguous_mapping():
 state={'root':{'x_y':{'z':1},'x':{'y_z':1}}};c=api._repair_flattened_candidates(state,['root','x_y_z']);require(len(c)==2);return 'ambiguous exact decompositions retained, no guess'
check('ambiguous_migration_mapping_not_unique',ambiguous_mapping)
# Guard and repair recovery tests: genuinely terminate a separate process.
for failpoint in ('repair_after_journal','repair_after_events.jsonl','repair_after_state.json','repair_before_manifest','repair_after_manifest'):
 def fault_case(phase=failpoint):
  r=fixture('fault_'+phase.replace('.','_'));p=api.consistency_repair_plan(r);file=RUN/(r.name+'_plan.json');file.write_text(json.dumps(p,ensure_ascii=False));before=hashes(r)
  cp,v=cli(r,['repairapply','--plan',str(file)],r.name+'_kill',{'VOYAGER_COMMIT_KILL':phase});require(cp.returncode==86,str(v));require((r/'.runtime'/api.CONSISTENCY_REPAIR_JOURNAL).is_file())
  cp,v=cli(r,['query',json.loads(INPUT_PATH.read_text())['ordinary_query']],r.name+'_query');require(cp.returncode!=0 and 'RECOVERY_REQUIRED' in str(v),str(v))
  guard_env={**os.environ,'VOYAGER_ROOT':str(r)};cp=subprocess.run([sys.executable,str(r/'guard.py'),'--resume'],env=guard_env,text=True,capture_output=True,timeout=180);(RUN/'outputs'/(r.name+'_guard.json')).write_text(cp.stdout);require(cp.returncode==0,cp.stdout+cp.stderr)
  require(not (r/'.runtime'/api.CONSISTENCY_REPAIR_JOURNAL).exists())
  if phase=='repair_after_manifest':require(hashes(r)!=before and api.consistency_repair_plan(r)['status']=='NO_PROVEN_REPAIR')
  else:require(hashes(r)==before)
  return {'kill_exit':86,'guard_resumed':True,'outcome':'target' if phase=='repair_after_manifest' else 'parent'}
 check('interruption_'+failpoint,fault_case)
def recovery_unknown_write():
 r=fixture('unknown_write');p=api.consistency_repair_plan(r);file=RUN/'unknown_write_plan.json';file.write_text(json.dumps(p,ensure_ascii=False));cp,_=cli(r,['repairapply','--plan',str(file)],'unknown_write_kill',{'VOYAGER_COMMIT_KILL':'repair_after_events.jsonl'});require(cp.returncode==86)
 path=r/'state.json';path.write_bytes(path.read_bytes()+b' ');unknown=path.read_bytes();result=rejects(lambda:api.consistency_repair_recover(r),'SOURCE_CHANGED');require(path.read_bytes()==unknown and (r/'.runtime'/api.CONSISTENCY_REPAIR_JOURNAL).exists());return result
check('recovery_refuses_unknown_third_party_write',recovery_unknown_write)
def io_rollback():
 r=fixture('io_rollback');p=api.consistency_repair_plan(r);before=hashes(r);os.environ['VOYAGER_COMMIT_IOFAIL']='repair_after_state.json'
 try:result=rejects(lambda:api.consistency_repair_apply(r,p),'TEST_IO_FAILURE')
 finally:os.environ.pop('VOYAGER_COMMIT_IOFAIL',None)
 require(hashes(r)==before and not (r/'.runtime'/api.CONSISTENCY_REPAIR_JOURNAL).exists());return result
check('io_exception_recovers_parent_and_preserves_error',io_rollback)
def standalone_repair():
 r=fixture('single_file_runtime_without_development',include_development=False)
 p=api.consistency_repair_plan(r);require(p['development_verification'].startswith('not materialized'))
 file=RUN/'single_file_plan.json';file.write_text(json.dumps(p,ensure_ascii=False));before=hashes(r)
 cp,_=cli(r,['repairapply','--plan',str(file)],'single_file_kill',{'VOYAGER_COMMIT_KILL':'repair_after_events.jsonl'});require(cp.returncode==86)
 recovery=api.consistency_repair_recover(r);require(recovery['outcome']=='parent' and hashes(r)==before)
 result=api.consistency_repair_apply(r,api.consistency_repair_plan(r));require(result['status']=='COMMITTED')
 cp,value=cli(r,['boot'],'single_file_boot');require(cp.returncode==0,str(value));require(not (r/'development').exists())
 return 'plan, interrupted recovery, commit and boot use engine + Guard + authority/archives; no development directory'
check('single_file_repair_recovery_and_boot_without_development',standalone_repair)
def development_release():
 spec=importlib.util.spec_from_file_location('development_runtime',WORK/'development/devsrc/runtime.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);dev,_=mod.load(WORK/'engine.py')
 require(dev.main.__name__==api.main.__name__ and dev._consistency_previous_main.__name__==api._consistency_previous_main.__name__)
 d=dev.consistency_repair_plan(WORK);r=api.consistency_repair_plan(WORK);require(d==r,'development/release repair plan differ')
 require(dev.authoritative_event_stage({'status':'active','phase':'investigating'})==api.authoritative_event_stage({'status':'active','phase':'investigating'}))
 return {'modules':len(json.loads((WORK/'development/devsrc/SOURCE_MANIFEST.json').read_text())['order']),'same_plan':True,'captured_old_main':True}
check('development_and_generated_release_actual_bindings',development_release)
print('REGRESSION_COMPLETE',len(RESULTS),'failed',sum(not r['passed'] for r in RESULTS),flush=True)
raise SystemExit(any(not r['passed'] for r in RESULTS))
