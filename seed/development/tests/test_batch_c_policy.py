import sys
sys.dont_write_bytecode=True
import copy,importlib.util,json,os,pathlib,shutil,time,traceback
P=pathlib.Path;BASE=P(os.environ['VOYAGER_TEST_SOURCE']).resolve();OUT=P(os.environ['VOYAGER_BATCH_C_OUTPUT']).resolve();OUT.mkdir(parents=True,exist_ok=True);r=OUT/'world';shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));os.environ.update(VOYAGER_ROOT=str(r),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm');os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None);s=importlib.util.spec_from_file_location('e',r/'engine.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a);rows=[]
def test(name,fn):
 try:detail=fn();rows.append({'name':name,'status':'PASS','detail':detail});print('PASS',name,flush=True)
 except Exception as ex:rows.append({'name':name,'status':'FAIL','error':str(ex),'trace':traceback.format_exc()});print('FAIL',name,str(ex),flush=True)
 (OUT/'results.json').write_text(json.dumps({'status':'FAIL' if any(x['status']=='FAIL' for x in rows) else 'PASS','engine_sha256':a.sha256_file(BASE/'engine.py'),'tests':rows},ensure_ascii=False,indent=2)+'\n')
def known():
 sid='XILU9-WHITESLEEP-0317-83631202';state=a.read_json(r/'state.json');old={d['fact_id'] for d in state['engine_runtime']['scene_registry_v1']['records'][sid]['disclosures'] if d['viewer']=='observer:HAWKE'};view=a.knowledge_packet(r,sid,'npc:PER-HAWK-MALEN-01');assert {f['fact_id'] for f in view['facts']}==old and old;assert all(f['acquired_from'] for f in view['facts']);assert all(f['epistemic']=='confirmed' for f in view['facts'] if f['fact_id']=='WS-PARTY');return {'old_observer_knowledge_preserved_under_canonical_actor':len(old),'acquisition_times_and_sources_preserved':True}
test('canonical_Hawke_identity_preserves_proven_old_knowledge',known)
def protected_alias():
 state=a.read_json(r/'state.json');tasks=a.read_json(r/'tasks.json');action={'type':'experience_record','entry':{'entry_id':'OVERRIDE','object_type':'intent_alias','value':{'alias':'当前金币余额','canonical_topic':'暗影舰队位置'},'instruction_ref':'fixture:alias'}};payload={'kind':'story_transaction','command_id':'OVERRIDE','authorization':'host_intent','authorization_ref':'HOST:OVERRIDE','actions':[action]};token=a._host_intent_scope.set({'evidence_ref':'fixture:alias'})
 try:
  try:a._story_actions_apply(r,copy.deepcopy(state),tasks,payload)
  except Exception as ex:assert 'BUILTIN_QUERY_PROTECTED' in str(ex),ex
  else:raise AssertionError('built-in alias overwritten')
 finally:a._host_intent_scope.reset(token)
 return 'learning cannot redefine canonical cash/time/task/scene queries'
test('built_in_query_semantics_cannot_be_redefined_by_experience',protected_alias)
def performance():
 with a.SnapshotContext(r) as ctx:assert ctx.validated_report()['status']=='READY_WITH_LIMITATIONS'
 (r/'.runtime/experience_v1.json').unlink(missing_ok=True)
 with a.SnapshotContext(r) as ctx:
  before=time.monotonic();result=a.visible_query_packet(r,'当前金币余额');elapsed=time.monotonic()-before;assert result['status']=='COMPLETE';assert ctx.metrics['history_decodes']==0 and ctx.metrics['semantic_cache_hits']==1;metrics=dict(ctx.metrics)
 assert not (r/'.runtime/experience_v1.json').exists()
 return {'warm_exact_query_seconds':elapsed,'history_decodes':0,'learning_cache_not_needed_for_builtin_queries':True,'metrics':metrics}
test('normal_exact_queries_do_not_expand_history_for_learning',performance)
def no_gm():
 os.environ.pop('VOYAGER_DEVELOPER_MODE');os.environ.pop('VOYAGER_DIAGNOSTIC_CONTEXT')
 try:
  try:a.narrative_context_packet(r,viewer='gm')
  except Exception as ex:assert 'GM_DIAGNOSTIC' in str(ex),ex
  else:raise AssertionError('GM focus metadata exposed')
 finally:os.environ.update(VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm')
 state=a.read_json(BASE/'state.json');contract=a.read_json(BASE/'development/evidence/batch_c_baseline_contract.json');state['engine_runtime'].pop('story_runtime_v1');assert a._repair_digest(state)==contract['state_digest'];check=a.run_checks(r,full=True);assert check['status']=='PASS',check['errors'];return {'private_focus_metadata_denied_before_read':True,'final_all_gameplay_facts_unchanged':True,'fullcheck':'PASS'}
test('private_context_gate_and_final_protection',no_gm)
raise SystemExit(1 if any(x['status']=='FAIL' for x in rows) else 0)
