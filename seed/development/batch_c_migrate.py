#!/usr/bin/env python3
"""Exact zero-time V14.46 -> V14.47 story-service contract migration."""
import copy,hashlib,importlib.util,json,os,pathlib,sys
P=pathlib.Path

def digest(o):return hashlib.sha256(json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,o):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n')
def migrate(source,target,audit):
 source=source.resolve();target=target.resolve();m=load(source/'manifest.json');assert m['save_set_id']=='SAVESET-V14.46-aac59e5c68893646','SOURCE_MISMATCH'
 spec=importlib.util.spec_from_file_location('parent_guard',source/'guard.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g);bound,errors=g.validate_dir(source,strict=True);assert bound and not errors and g.development_intact(source,bound),errors
 s=load(source/'state.json');tasks=load(source/'tasks.json');now=s['game_time'];assert now=='8363-12-02T22:45:00'==tasks['game_time'];records=s['engine_runtime']['scene_registry_v1']['records'];bindings={}
 for t in tasks['active_tasks']+tasks['queued_tasks']:
  tid=t['task_id'];bindings[tid]={'task_id':tid,'one_open_scene':True,'adapter':'patrol_v1' if tid=='TSK-SHADOW-XIANYUE-ASTEROID-PATROL' else 'generic','scene_ids':[sid for sid,r in records.items() if r['task_id']==tid]}
 s['engine_runtime']['story_runtime_v1']={'schema':'STORY_RUNTIME_V1','policy_version':'bounded_director_v1','task_scene_bindings':bindings,'focus_scene_id':None,'legacy_viewer_bindings':{'observer:HAWKE': {'viewer_id': 'npc:PER-HAWK-MALEN-01', 'source_ref': 'state:entity_registry.entities.PER-HAWK-MALEN-01', 'source_save_set_id': 'SAVESET-V14.46-aac59e5c68893646', 'basis': 'Existing accepted HAWKE observer in Whitesleep; canonical entity 霍克·马伦 has alias 霍克. Identity route only; retain original disclosure times and epistemics.'}},'entities':{},'facts':{},'learning_events':[],'evidence_links':[],'decisions':{},'proposals':{},'consequences':{},'migration':{'source_save_set_id':m['save_set_id'],'zero_time':True,'historical_scene_records_unchanged':True,'no_new_stories_or_people_created':True,'historical_knowledge':'retain explicit disclosures; no inferred full disclosure'}}
 sourcefp={n:sha(source/n) for n in ['manifest.json',*m['components'],*[r['path'] for r in m['cold_archives'].values()],*m['development_sources']['files']]}
 plan={'schema':'BATCH_C_MAINTENANCE_PLAN_V1','source_save_set_id':m['save_set_id'],'source_fingerprint':sourcefp,'scope':'steps13-16','target_state_sha256':digest(s),'game_time_advanced':False,'candidate_tools':{n:sha(target/n) for n in ('engine.py','guard.py')}};plan['plan_sha256']=digest(plan);write(audit/'migration_plan.json',plan)
 write(target/'state.json',s);os.environ.update(VOYAGER_ROOT=str(target),VOYAGER_DEV_SOURCE_DIR=str(target),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm',PYTHONDONTWRITEBYTECODE='1');spec=importlib.util.spec_from_file_location('candidate',target/'engine.py');api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
 api._append_engine_history(target/'events.jsonl',{'event_id':'EVT-BATCH-C-'+plan['plan_sha256'][:24],'type':'system','subtype':'batch_c_maintenance','game_time':now,'zero_time':True,'summary':'Zero-time story bindings, explicit knowledge, bounded narrative proposal and reversible experience services. No scene opened, person generated, cash or deployment changed.','source':'GAME ENGINE 2.62.0 BATCH_C_MAINTENANCE_V1','changes':[{'target':'state:engine_runtime.story_runtime_v1','action':'initialize_empty_authorized_story_contract'}],'source_refs':['state:self','tasks:self','events:self','manifest:self'],'maintenance_plan':plan['plan_sha256']})
 api._component_write_manifest_native(target,'V14.47',m['save_set_id'],{'from_save_set_id':m['save_set_id'],'from_layout':'native_eight_component_v4_tiered_history','to_layout':'native_eight_component_v4_tiered_history','game_time_advanced':False,'batch_c_plan_sha256':plan['plan_sha256']})
 report=api.run_checks(target,full=True);write(audit/'migration_check.json',report);print(json.dumps({'status':report['status'],'errors':report['errors'],'save_set_id':load(target/'manifest.json')['save_set_id']},ensure_ascii=False));assert report['status']=='PASS'
if __name__=='__main__':migrate(*(P(x) for x in sys.argv[1:]))
