#!/usr/bin/env python3
"""Actual story-turn transfer + learning commit interruption matrix.
All host intents are synthetic and restricted to isolated test clones.
"""
import argparse,pathlib,sys,os,json,subprocess,importlib.util,time,traceback
sys.dont_write_bytecode=True
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);ns=p.parse_args();source=ns.source.resolve();out=ns.output.resolve();out.mkdir(parents=True,exist_ok=False)
s=importlib.util.spec_from_file_location('h',source/'development/tests/stage1_v1453.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
prepared=h.clone(source,out/'prepared_fixture');a=h.load_api(prepared,'story_fault_prepare');actor='PER-HAWK-MALEN-01';sid='TEST-FAULT-SCENE'
actions=[{'type':'scene_open','scene_id':sid,'task_id':None,'family':'conversation','title':'SYNTHETIC fault test','location_ref':'LOC-FREEPORT-XILU9','participants':[actor],'presence_mode':'remote','visible_to':['player','npc:'+actor]},{'type':'fact_append','scene_id':sid,'fact_id':'F-OPEN','subject_id':actor,'predicate':'statement','value':'合成故障夹具。','epistemic':'confirmed','source_category':'direct_observation'}]+[{'type':'knowledge_disclose','scene_id':sid,'fact_id':'F-OPEN','viewer_id':v,'channel':'heard','basis_event_id':'$current_transaction'} for v in ['player','npc:'+actor]]+[{'type':'scene_phase','scene_id':sid,'phase':'open'}]
c=h.command(a,prepared,'story_setup','FAULT-SETUP',actions=actions);env=h.envelope(a,prepared,c);env['limits']['uses']=100;a.host_intent_command(prepared,env,'V14.60')
ctx=a.prepare_turn(prepared,sid,actor,'player','合成故障测试');proposal={'schema':a.STORY_TURN_SCHEMA,'turn_id':'TEST-STAGE3-FAULT','base_identity':ctx['base_identity'],'scene_id':sid,'actor_id':actor,'viewer':'player','player_intent':'合成故障测试','intent_tags':['trade'],'basis_refs':['fact/'+sid+'/F-OPEN'],'segments':[{'mode':'outcome','speaker_id':None,'text':'','basis_refs':[],'receipt_refs':['effect:0']}],'effects':[{'kind':'account_transfer','source_account':'covert','destination_account':'fleet','currency':'grey','amount':'1.23','reason':'SYNTHETIC interruption'}],'updates':[{'type':'fact_append','scene_id':sid,'fact_id':'F-FAULT','subject_id':actor,'predicate':'social_reaction','value':'合成交易后的已授权回应。','epistemic':'confirmed','source_category':'direct_observation'},{'type':'knowledge_disclose','scene_id':sid,'fact_id':'F-FAULT','viewer_id':'npc:'+actor,'channel':'observed','basis_event_id':'$current_transaction'}],'consequences':[],'claims':[],'public_reason':'一次事务同时完成转账与学习。','candidates':['核对后执行']}
command=h.command(a,prepared,'story_turn',proposal['turn_id'],proposal=proposal);original_env=h.envelope(a,prepared,command);original_env['limits']['uses']=100
request=out/'synthetic_host_envelope.json';request.write_text(json.dumps(original_env,ensure_ascii=False))
worker="""import os,pathlib,importlib.util,json
r=pathlib.Path(os.environ['VOYAGER_ROOT']);s=importlib.util.spec_from_file_location('h',r/'development/tests/stage1_v1453.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h);a=h.load_api(r);a.host_intent_command(r,json.loads(pathlib.Path(os.environ['STORY_TEST_ENVELOPE']).read_text()),'V14.90')
"""
rows=[]
for phase,unknown in [(x,False) for x in ['after_journal','after_component','after_manifest','after_receipt','after_cleanup']]+[('after_component',True)]:
 name=phase+('_unknown' if unknown else '');t=time.perf_counter()
 try:
  r=h.clone(prepared,out/name);a=h.load_api(r,name);initial=a.read_json(r/'manifest.json');g=a._repair_guard_module(r)
  cp=subprocess.run([sys.executable,'-c',worker],env=dict(os.environ,VOYAGER_ROOT=str(r),STORY_TEST_ENVELOPE=str(request),VOYAGER_COMMIT_KILL=phase),capture_output=True,text=True,timeout=240);assert cp.returncode==86,cp.stderr[-2000:]+cp.stdout[-1000:]
  j=r/'.runtime/native_commit_journal.json';oldjournal=j.read_bytes() if j.exists() else None
  if unknown:(r/'tasks.json').write_bytes((r/'tasks.json').read_bytes()+b' ')
  before={n:h.sha(r/n) for n in a.COMPONENT_FILES}
  with g.guard_lock(r):m,errors=g.recover_interrupted_commit(r) if j.exists() else g.validate_dir(r,strict=True)
  if unknown:
   assert not m and any('UNKNOWN_MODIFICATION' in x for x in errors),errors;assert before=={n:h.sha(r/n) for n in a.COMPONENT_FILES};detail={'unknown_bytes_preserved':True}
  else:
   assert m and not errors,errors;target=phase in ('after_manifest','after_receipt','after_cleanup');state=a.read_json(r/'state.json');assert a._account_units(state,'covert','grey')==(31200900 if target else 31213200);assert ('F-FAULT' in a._knowledge_known(state,sid,'npc:'+actor))==target;assert (proposal['turn_id'] in state['engine_runtime']['story_turns_v1']['turns'])==target
   if target and oldjournal:
    hashes={n:h.sha(r/n) for n in a.COMPONENT_FILES};j.write_bytes(oldjournal)
    with g.guard_lock(r):again,errs=g.recover_interrupted_commit(r)
    assert again and not errs,errs;assert hashes=={n:h.sha(r/n) for n in a.COMPONENT_FILES}
   # Retry original turn and envelope; parent rollbacks execute once, target
   # recoveries return the exact permanent receipt. Neither may double-learn.
   retry_hashes={n:h.sha(r/n) for n in a.COMPONENT_FILES};stability_refusals=0
   try:retry=a.host_intent_command(r,original_env,'V14.91')
   except a.EngineError as exc:
    # A read boundary can legitimately refuse a changing source. This is an
    # explicitly separate fresh request, never skipping/relaxing the old check.
    # First prove the failed attempt left ALL authority bytes untouched and
    # independently revalidate the recovered complete source with Guard.
    if str(exc)!='SOURCE_CHANGED_DURING_COMPONENT_CHECK':raise
    assert retry_hashes=={n:h.sha(r/n) for n in a.COMPONENT_FILES}
    with g.guard_lock(r):stable,stability_errors=g.validate_dir(r,strict=True)
    assert stable and not stability_errors and g.development_intact(r,stable)
    assert not g.active_journal(r,'native_commit_journal.json')
    stability_refusals=1;retry=a.host_intent_command(r,original_env,'V14.91')
   assert retry['status']==('ALREADY_APPLIED' if target else 'SAVED');s=a.read_json(r/'state.json');assert a._account_units(s,'covert','grey')==31200900
   assert len([v for v in s['engine_runtime']['story_runtime_v1']['learning_events'] if v['scene_id']==sid and v['fact_id']=='F-FAULT' and v['viewer_id']=='npc:'+actor])==1
   assert len([e for e in a.read_history_raw(r/'events.jsonl')[1] if e.get('command_id')==proposal['turn_id']])==1;assert a.turn_report(r,proposal['turn_id'])['status']=='COMMITTED'
   detail={'recovered_to':'target' if target else 'parent','money_memory_turn_all_atomic':True,'original_retry_exactly_once':True,'old_journal_reappearance_checked':bool(target and oldjournal),'fail_closed_source_stability_refusals':stability_refusals,'fresh_retry_requires_independent_complete_Guard_validation':True}
  row={'name':name,'status':'PASS','detail':detail}
 except Exception as e:row={'name':name,'status':'FAIL','error':str(e),'trace':traceback.format_exc()}
 row['seconds']=time.perf_counter()-t;rows.append(row);print(row['status'],name,row.get('error',''),flush=True)
 (out/'results.json').write_text(json.dumps({'schema':'STAGE3_STORY_FAULTS_V1','status':'FAIL' if any(x['status']=='FAIL' for x in rows) else 'PASS','manifest_sha256':h.sha(source/'manifest.json'),'engine_sha256':h.sha(source/'engine.py'),'tests':rows},ensure_ascii=False,indent=2))
raise SystemExit(1 if any(x['status']=='FAIL' for x in rows) else 0)
