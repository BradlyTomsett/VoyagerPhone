#!/usr/bin/env python3
"""Sequential normal timings, synthetic isolated growth only; no model generation."""
import pathlib,os,sys,json,importlib.util,argparse,copy,time,shutil,platform,statistics
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);n=p.parse_args();source=n.source.resolve();out=n.output.resolve();out.mkdir(parents=True,exist_ok=False)
s=importlib.util.spec_from_file_location('h',source/'development/tests/stage1_v1453.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h);rows=[]
def measure(fn,times=5):
 samples=[];last=None
 for _ in range(times):
  t=time.perf_counter();last=fn();samples.append({'seconds':time.perf_counter()-t,'json_body_bytes':len(json.dumps(last,ensure_ascii=False,separators=(',',':'),default=str).encode())})
 vals=sorted(r['seconds'] for r in samples);return {'samples':samples,'median_seconds':statistics.median(vals),'p95_nearest_rank_seconds':vals[max(0,__import__('math').ceil(.95*len(vals))-1)]},last
for profile,extra_events,extra_npcs,extra_definitions in [('small',0,16,1),('medium',5000,128,100),('large',20000,512,300)]:
 root=h.clone(source,out/profile);a=h.load_api(root,'scale_'+profile);state=a.read_json(root/'state.json');tasks=a.read_json(root/'tasks.json');rt=a._story_runtime(state);now=state['game_time'];eid='SYNTHETIC-SCALE-SOURCE-'+profile;sid='SYNTHETIC-SCALE-'+profile;actors=[]
 for i in range(extra_npcs):
  pid='PER-SCALE-'+profile+'-'+str(i);actors.append(pid);rt['entities'][pid]={'entity_id':pid,'name':'合成人物'+profile+str(i),'aliases':[],'role':'explicit synthetic scale fixture only','registered_at':now,'source_event_id':eid,'crew_or_asset_created':False};a._s3_runtime(state)['npcs'][pid]=a._s3_empty_npc(pid)
 a._sync_entity_registry(state);token=a._story_scope.set({'event_id':eid,'command_id':eid,'authorization_ref':'SYNTHETIC-FIXTURE','outer':{'kind':'story_setup'},'stage':root})
 try:
  for start in range(0,len(actors),32):
   scene=sid if start==0 else sid+'-'+str(start//32)
   a._s3_apply_update(root,state,tasks,{'type':'scene_open','scene_id':scene,'task_id':None,'family':'conversation','title':'SYNTHETIC scale only','location_ref':'LOC-FREEPORT-XILU9','participants':actors[start:start+32],'presence_mode':'remote','visible_to':['player']});a._s3_apply_update(root,state,tasks,{'type':'scene_phase','scene_id':scene,'phase':'open'})
 finally:a._story_scope.reset(token)
 for i,pid in enumerate(actors):
  scene=sid if i<32 else sid+'-'+str(i//32)
  fid='SCALE-F-'+str(i);rt['facts'][scene+'/'+fid]={'fact_id':fid,'scene_id':scene,'subject_id':pid,'predicate':'statement','value':'scale needle '+str(i)+'；仅为合成规模资料。','epistemic':'confirmed','valid_from':now,'valid_to':None,'source_category':'direct_observation','confidence_basis':'synthetic fixture','source_event_ids':[eid],'supersedes_fact_id':None}
  for viewer in ['player','npc:'+pid]:rt['learning_events'].append({'scene_id':scene,'fact_id':fid,'viewer_id':viewer,'learned_at':now,'channel':'document','basis_event_id':eid,'record_event_id':eid})
 a._write_authority_json(root/'state.json',state)
 with a._history_append_batch(root/'events.jsonl'):
  a._append_engine_history(root/'events.jsonl',{'event_id':eid,'type':'system','game_time':now,'summary':'SYNTHETIC SCALING FIXTURE ONLY; no production history or authorization.','changes':[{'target':'state:engine_runtime.story_runtime_v1','action':'explicit_synthetic_fixture'}],'authority_files':['state.json']})
  for i in range(extra_events):a._append_engine_history(root/'events.jsonl',{'event_id':'SYNTHETIC-HISTORY-'+profile+'-'+str(i),'type':'system','game_time':now,'summary':'Synthetic history evidence '+str(i),'changes':[],'authority_files':[]})
 a._sync_current_scaling_status(root)  # Existing derived-state contract, never disable threshold checks.
 m=a.read_json(root/'manifest.json');a._component_write_manifest_native(root,m['save_version'],m['parent_save_set_id'],m['migration_lineage']);check=a.run_checks(root,full=True);assert check['status']=='PASS',check['errors'];(out/(profile+'_fixture_fullcheck.json')).write_text(json.dumps(check,ensure_ascii=False,indent=2))
 # Definitions are installed using the real authorized path, never assets.
 package=h.read(source/'development/examples/content_v2/demo_adjutant_1_0_0.json');template=package['definitions'][1];package['definitions']=[{**copy.deepcopy(template),'id':'demo.adjutant:scale-'+str(i)} for i in range(extra_definitions)];package['content_sha256']=a._s4_package_digest(package);plan=a.content_upgrade_preview(root,package);c=h.command(a,root,'content_upgrade','SYNTHETIC-SCALE-CONTENT',package=package,plan=plan);install,_=measure(lambda:a.host_intent_command(root,h.envelope(a,root,c),'V14.70'),1)
 shutil.rmtree(root/'.runtime',ignore_errors=True)
 cold,_=measure(lambda:a.readiness_report(root),1);memory_cold,memory=measure(lambda:a.memory_search(root,'player','scale needle',scene_id=sid,limit=5),1);warm_memory,memory=measure(lambda:a.memory_search(root,'player','scale needle',scene_id=sid,limit=5));prep,context=measure(lambda:a.prepare_turn(root,sid,actors[0],'player','scale needle',budget_bytes=16384))
 assert len(memory['rows'])==5 and context['model_status']=='NEEDS_AI' and context['context_bytes']==len(json.dumps(context,ensure_ascii=False,separators=(',',':'),default=str).encode())
 context_size=len(json.dumps(context,ensure_ascii=False,separators=(',',':'),default=str).encode())
 assert context_size<=16384 or context.get('budget_exceeded') and context.get('budget_status')=='EXCEEDED_REQUIRES_PAGINATION'
 transfer=h.command(a,root,'account_transfer','SYNTHETIC-SCALE-TRANSFER',source_account='covert',destination_account='fleet',currency='grey',amount='1.23',reason='SYNTHETIC scaling commit');commit,result=measure(lambda:a.host_intent_command(root,h.envelope(a,root,transfer),'V14.71'),1);assert result['status']=='SAVED'
 rows.append({'profile':profile,'synthetic':True,'extra_history':extra_events,'logical_history_before_install':2614+1+extra_events,'extra_NPCs':extra_npcs,'total_NPCs':16+extra_npcs,'focused_NPCs':min(32,extra_npcs),'independent_scenes':(extra_npcs+31)//32,'new_content_definitions':extra_definitions,'state_bytes':(root/'state.json').stat().st_size,'history_file_bytes':(root/'events.jsonl').stat().st_size,'cold_readiness':cold,'memory_index_build_and_read':memory_cold,'warm_memory':warm_memory,'prepare':prep,'content_install':install,'real_commit':commit,'context_bytes':context['context_bytes'],'context_budget_status':context.get('budget_status','WITHIN_BUDGET'),'model_generation':'NOT_RUN','identity':a._s3_identity(root)});(out/'scale_samples.json').write_text(json.dumps({'schema':'STAGE4_SCALE_BENCH_V1','status':'PASS','environment':{'python':sys.version,'platform':platform.platform(),'os_page_cache_flushed':False,'CPU_model':'not exposed by runtime','RAM_limit':'not exposed by runtime','profile_timing_mixed':False,'read_samples':5,'cold_and_write_samples':1,'quantiles':'nearest rank; n=5 reads only, not a distribution guarantee'},'source_engine_sha256':h.sha(source/'engine.py'),'source_manifest_sha256':h.sha(source/'manifest.json'),'profiles':rows},ensure_ascii=False,indent=2));print('PASS',profile,flush=True)
