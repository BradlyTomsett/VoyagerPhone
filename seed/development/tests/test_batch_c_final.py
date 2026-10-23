import sys
sys.dont_write_bytecode=True
import copy,importlib.util,json,os,pathlib,shutil,time,traceback,contextlib,io,hashlib
P=pathlib.Path;BASE=P(os.environ['VOYAGER_TEST_SOURCE']).resolve();OUT=P(os.environ['VOYAGER_BATCH_C_OUTPUT']).resolve();OUT.mkdir(parents=True,exist_ok=True);os.environ.update(VOYAGER_ROOT=str(BASE),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm');os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None)
def load(r):
 os.environ['VOYAGER_ROOT']=str(r);s=importlib.util.spec_from_file_location('e'+str(time.time_ns()),r/'engine.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a);return a
r=OUT/'world';shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));a=load(r);rows=[];version=48

def test(name,fn):
 try:detail=fn();rows.append({'name':name,'status':'PASS','detail':detail});print('PASS',name,flush=True)
 except Exception as ex:rows.append({'name':name,'status':'FAIL','error':repr(ex),'trace':traceback.format_exc()});print('FAIL',name,repr(ex),flush=True)
 (OUT/'results.json').write_text(json.dumps({'status':'FAIL' if any(x['status']=='FAIL' for x in rows) else 'PASS','engine_sha256':a.sha256_file(BASE/'engine.py'),'tests':rows},ensure_ascii=False,indent=2)+'\n')
def envelope(cid,actions):
 m=a.read_json(r/'manifest.json');now=a.read_json(r/'state.json')['game_time'];c={'schema':a.DOMAIN_COMMAND_SCHEMA,'command_id':cid,'base_save_set_id':m['save_set_id'],'kind':'story_transaction','actions':actions,'authorization':'host_intent','authorization_ref':'HOST:'+cid,'actor_id':'PER-COMMANDER-01'};return {'schema':'HOST_COMMAND_INTENT_V1','command':c,'subject_id':c['actor_id'],'parent_save_set_id':m['save_set_id'],'instruction_text':'Isolated final integration test; exact story actions only','evidence_ref':'fixture:'+cid,'decision':'approved','targets':a._domain_command_targets(c),'valid_from':now,'valid_until':now,'limits':a._domain_authorization_cost(c)}
def send(cid,actions,api=None):
 global version
 e=envelope(cid,actions);result=(api or a).host_intent_command(r,e,'V14.'+str(version));assert result['status']=='SAVED',result;version+=1;return result

def portable_protection():
 c=a.read_json(BASE/'development/evidence/batch_c_baseline_contract.json');s=a.read_json(BASE/'state.json');s['engine_runtime'].pop('story_runtime_v1');assert a._repair_digest(s)==c['state_digest'];_,events,raw=a.read_history_raw(BASE/'events.jsonl');assert [a.sha256_bytes(x) for x in raw[:c['old_event_count']]]==c['original_event_raw_sha256'];assert len(events)==c['old_event_count']+1
 for name,digest in {**c['component_hashes'],**c['cold_files']}.items():assert a.sha256_file(BASE/name)==digest
 return {'source_gameplay_facts':True,'old_event_byte_count':c['old_event_count'],'portable_proof':True}
test('portable_input_contract_and_history_byte_protection',portable_protection)

def setup():
 actions=[]
 for i,(sid,tid) in enumerate([('CHECK-A','TSK-MIN-OPERATIONS'),('CHECK-B','TSK-YUHUO-OPERATIONS')]):
  eid='NPC-CHECK-'+str(i);actions += [{'type':'entity_register','entity_id':eid,'name':['玛拉·弗恩','诺兰·泽恩'][i]}, {'type':'scene_create','scene_id':sid,'task_id':tid,'family':'ordinary_life','title':'独立集成测试门厅','participants':[eid]}, {'type':'fact_append','scene_id':sid,'fact_id':'OBS','subject_id':eid,'predicate':'goal','value':'希望把情况说明清楚','epistemic':'confirmed','source_category':'creative_setting'}, {'type':'knowledge_disclose','scene_id':sid,'fact_id':'OBS','viewer_id':'player','channel':'heard','basis_event_id':'$current_transaction'}, {'type':'knowledge_disclose','scene_id':sid,'fact_id':'OBS','viewer_id':'npc:'+eid,'channel':'heard','basis_event_id':'$current_transaction'}, {'type':'scene_phase','scene_id':sid,'phase':'open'}]
 actions.append({'type':'experience_record','entry':{'entry_id':'FINAL-ALIAS','object_type':'intent_alias','value':{'alias':'手边钱','canonical_topic':'当前金币余额'},'instruction_ref':'fixture:FINAL-SETUP'}});send('FINAL-SETUP',actions)
 current=a.visible_query_packet(r,'当前场景');assert current['status']=='FOCUS_REQUIRED' and len(current['value']['candidates'])==2,current
 batch=a.visible_query_batch_packet(r,['当前场景','手边钱']);assert batch['results'][0]['status']=='FOCUS_REQUIRED' and batch['results'][1]['status']=='COMPLETE';assert a.knowledge_packet(r,'CHECK-A','npc:NPC-CHECK-1')['facts']==[]
 strategy=a._experience_strategy(a.experience_packet(r),'rescue',['rescue']*4);assert strategy['suggested_families'][0]!='rescue' and strategy['temporary_recent_pattern_counts']['rescue']==4
 os.environ['VOYAGER_EXPERIENCE']='0'
 try:assert a._experience_strategy(a.experience_packet(r),'rescue',['rescue']*4)['suggested_families'][0]=='rescue'
 finally:os.environ.pop('VOYAGER_EXPERIENCE')
 return {'current_and_batch_focus_required':True,'alias_exact':True,'NPC_isolation':True,'temporary_repetition_rank_improves_without_permanent_preference':True,'switch_rollback':True}
test('final_authorized_parallel_focus_alias_and_pattern_strategy',setup)

def privacy_and_constraints():
 before={n:a.sha256_file(r/n) for n in a.COMPONENT_FILES};p={'scene_id':'CHECK-A','phase':'open','gold_delta':100,'type':'scene_phase'}
 try:a.host_intent_command(r,envelope('BAD-SCHEMA',[p]),'V14.'+str(version))
 except Exception as ex:assert 'SCHEMA' in str(ex),ex
 else:raise AssertionError('mechanical field accepted')
 assert before=={n:a.sha256_file(r/n) for n in a.COMPONENT_FILES}
 for args in (['knowledgequery','--scene-id','CHECK-A','--viewer','gm'],['assetquery','--audience','observer','--observer-id','NPC-CHECK-0']):
  out=io.StringIO()
  with contextlib.redirect_stdout(out):code=a.main(args)
  assert code!=0,out.getvalue()
 projection=a.story_projection_packet(r);assert projection['focus']['status']=='FOCUS_REQUIRED' and projection['scene'] is None
 # Unverified source/topic associations never enter the experience log.
 bad={'type':'experience_record','entry':{'entry_id':'BAD-SOURCE','object_type':'source_success','value':{'topic':'当前金币余额','source_ref':'state:shadow_fleet.current_location'},'instruction_ref':'fixture:BAD-SOURCE'}}
 try:a.host_intent_command(r,envelope('BAD-SOURCE',[bad]),'V14.'+str(version))
 except Exception as ex:assert 'TOPIC_MISMATCH' in str(ex),ex
 else:raise AssertionError('wrong learned source accepted')
 assert before=={n:a.sha256_file(r/n) for n in a.COMPONENT_FILES};return 'strict mechanical schema, cross-viewer access and wrong learned source rejected with no authority changes'
test('dedicated_endpoints_and_learning_negative_matrix',privacy_and_constraints)

def revoke_and_dev():
 send('FINAL-REVOKE',[{'type':'experience_revoke','entry_id':'FINAL-ALIAS','reason':'test rollback'}]);assert a.experience_packet(r)['records']==[]
 bad={'type':'experience_record','entry':{'entry_id':'FINAL-ALIAS','object_type':'intent_alias','value':{'alias':'手边钱','canonical_topic':'当前金币余额'},'instruction_ref':'fixture:REUSE'}}
 before={n:a.sha256_file(r/n) for n in a.COMPONENT_FILES}
 try:a.host_intent_command(r,envelope('REUSE',[bad]),'V14.'+str(version))
 except Exception as ex:assert 'ENTRY_EXISTS' in str(ex),ex
 else:raise AssertionError('revoked ID reused')
 assert before=={n:a.sha256_file(r/n) for n in a.COMPONENT_FILES}
 spec=importlib.util.spec_from_file_location('dev',r/'development/devsrc/runtime.py');dev=importlib.util.module_from_spec(spec);spec.loader.exec_module(dev);d,_=dev.load(r/'engine.py')
 assert d.story_projection_packet(r)==a.story_projection_packet(r)
 proposal={'schema':'NARRATIVE_PROPOSAL_V1','base_save_set_id':a.read_json(r/'manifest.json')['save_set_id'],'scene_id':'CHECK-A','audience':'player','intent_ref':'HOST:DEVELOPMENT-WRITE','basis_refs':['fact/CHECK-A/OBS'],'draft_text':'门缝的微风吹动衣角。玛拉想把情况说明清楚，你耐心听完后，她放缓语气，愿意继续谈下去。','new_facts':[],'claims':[{'speaker_id':'NPC-CHECK-0','text':'我觉得这里可以慢慢说明。','epistemic':'hypothesis','basis_fact_ids':['OBS']}],'action_requests':[],'consequence_requests':[],'required_unknowns':[],'narrative_tags':['ordinary_life']}
 send('DEVELOPMENT-WRITE',[{'type':'entity_register','entity_id':'NPC-DEV-WRITE','name':'艾琳·莱斯'},{'type':'narrative_commit','scene_id':'CHECK-A','proposal_id':'FINAL-PROP','proposal':proposal}],d)
 report=a.narrative_report_packet(r,'FINAL-PROP');assert 'basis_fact_ids' not in json.dumps(report);assert a.narrative_context_packet(r,'CHECK-A')['recent_claims'];assert a.knowledge_packet(r,'CHECK-A','npc:NPC-CHECK-0')['beliefs'];assert not a.knowledge_packet(r,'CHECK-A','npc:NPC-CHECK-1')['beliefs']
 state=a.read_json(r/'state.json');assert state['entity_registry']['entities']['NPC-DEV-WRITE']['managed_by']=='story_runtime_v1'
 original=a.read_json(BASE/'state.json');assert state['summary']==original['summary'] and state['inventories']==original['inventories'] and state['engine_runtime']['finance_runtime']==original['engine_runtime']['finance_runtime'] and state['engine_runtime']['long_horizon']==original['engine_runtime']['long_horizon'];assert a.run_checks(r,full=True)['status']=='PASS'
 return {'revoke_is_permanent_per_entry_id':True,'development_real_commit_matches_release_routes':True,'all_mechanics_and_cash_preserved':True}
test('revoke_ID_protection_and_development_real_write_equivalence',revoke_and_dev)
raise SystemExit(1 if any(x['status']=='FAIL' for x in rows) else 0)
