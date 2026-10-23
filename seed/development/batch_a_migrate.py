#!/usr/bin/env python3
"""Evidence-bound zero-time Batch A migration. Never a general patch endpoint.
Run the old restricted next_seq repair first; pass its exact committed result as
--source. Candidate code is independently built before deriving this plan.
"""
import argparse,copy,hashlib,importlib.util,json,os,pathlib,shutil,sys

def digest(obj):return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def load(path):return json.loads(path.read_text())
def write(path,obj):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def filehash(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def fingerprint(root):return {str(p.relative_to(root)):filehash(p) for p in sorted(root.rglob('*')) if p.is_file() and '.runtime' not in p.parts and '__pycache__' not in p.parts and not p.name.startswith('.')}
def migrate_docs(source,decision):
 s=load(source/'state.json');t=load(source/'tasks.json');old=copy.deepcopy(s)
 assert s['game_time']==t['game_time']=='8363-12-02T22:45:00'
 assert decision['selected_policy']=='preserve_no_replay_resume_at_end' and decision['user_choice']=='保留缺口，从22:45继续'
 er=s['engine_runtime'];lh=er['long_horizon'];clocks=lh['hazard_clocks'];assert len(clocks)==12
 assert all(c['last_evaluated']=='8363-12-02T12:00:00' for c in clocks.values())
 gapid='GAP-83631202-1200-2245'
 gap={'schema':'RISK_GAP_WINDOW_V1','start':'8363-12-02T12:00:00','end':s['game_time'],'status':'acknowledged_unsimulated',
      'policy':decision['selected_policy'],'decision_evidence_ref':'development/evidence/batch_a_user_policy.json',
      'seed_sha256':digest(er['seed_anchor']),'clocks':copy.deepcopy(clocks),'source_event_ids':['CONV-V1443-2535','CONV-V1443-2536'],
      'evidence_assessment':'Accepted continuation does not contain risk integration receipts; no past simulation is asserted.'}
 er['risk_gap_registry_v1']={gapid:gap}
 for c in clocks.values():c.update(evaluation_epoch_id=gapid,evaluation_cursor=s['game_time'])
 # Keep last_evaluated and last_processed_game_time unchanged: they mean actually evaluated.
 p=s['world_state_overrides']['intelligence_and_security']['xianyue_asteroid_shadow_patrol_current'];task=next(x for x in t['active_tasks'] if x['task_id']=='TSK-SHADOW-XIANYUE-ASTEROID-PATROL')
 er['batch_a_migration_evidence']={'prior_patrol_task':copy.deepcopy(task),'prior_patrol_fields':{k:copy.deepcopy(p.get(k)) for k in ('local_event_slot','mission_status','decision_gate')},'source_save_set_id':load(source/'manifest.json')['save_set_id']}
 assert p['current_local_event'] is None and task['task_data']['current_event_id'] is None
 p.update(slot_status='empty',scene_id=None,mission_mode='hidden_standby',local_event_slot='empty',mission_status='hidden_standby',decision_gate='白眠已结案；七舰熄炉附近隐蔽待命，新事件需指挥官明确授权。')
 task.update(phase='hidden_standby',report_policy='七舰在熄炉附近隐蔽待命，十一舰留S-B5；无开放局地事件，不自动调舰或创建新事件。',decision_gate=p['decision_gate'],semantic_context='白眠已结案归档，不追20:30买家；七舰保持既有隐蔽停泊部署，霍克等人恢复日常。')
 task['task_data'].update(slot_status='empty',scene_id=None,mission_mode='hidden_standby',local_incident_status='closed',new_incidents_allowed_without_order=False)
 loc=s['shadow_fleet']['current_location'];er['batch_a_migration_evidence']['prior_location_verification_basis']=loc.get('verification_basis')
 loc['time_semantics']={'schema':'LOCATION_TIME_SEMANTICS_V1','effective_at':loc['as_of'],'observed_at':loc['as_of'],'verified_through':s['game_time'],'recorded_at':s['game_time'],'basis':'accepted_continuation_explicit_no_redeployment','source_event_ids':['CONV-V1443-2535','CONV-V1443-2536']}
 loc['verification_basis']='Accepted V14.43 continuation: existing seven-vessel hidden deployment retained; no movement inferred.'
 er['authority_map_v1']={'schema':'FIELD_AUTHORITY_MAP_V1','funds':'engine_runtime.finance_runtime.funds_units','ships':'summary.ships','personnel':'summary.personnel','location':'shadow_fleet.current_location','tasks':'tasks:active_tasks','scene':'engine_runtime.scene_registry_v1','handoff':'derived_projection_only','historical_continuity':'evidence_only_not_current_authority'}
 terminal={}
 for bucket in ('recent_completed_tasks','completed_tasks','cancelled_tasks'):
  values=t.get(bucket,[]);values=values.values() if isinstance(values,dict) else values
  for r in values:
   if isinstance(r,dict) and r.get('task_id'):terminal[r['task_id']]={'task_id':r['task_id'],'status':r.get('status'),'source':'tasks:'+bucket}
 er['task_registry_v1']=terminal
 # Audit each inherited authorization. No ambiguous scope receives an unlimited grant.
 er['standing_authorization_migration_v1']={key:{'original_sha256':digest(row),'status':'inactive_retained' if row.get('status')!='active' else 'needs_typed_target_mapping','reason':'No new authority inferred from prose; exact host instruction gateway available.'} for key,row in s.get('standing_authorizations',{}).items()}
 return s,t

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--candidate',type=pathlib.Path,required=True);p.add_argument('--plan',type=pathlib.Path,required=True);p.add_argument('--apply',action='store_true');args=p.parse_args()
 source=args.source.resolve();candidate=args.candidate.resolve();m=load(source/'manifest.json');decision=load(candidate/'development/evidence/batch_a_user_policy.json')
 if m['save_version']!='V14.44' or m['parent_save_set_id']!='SAVESET-V14.43-24eac9bf774f7764':raise ValueError('MAINTENANCE_SOURCE_BASELINE_MISMATCH')
 # Validate the complete input independently with its own historical Guard.
 spec=importlib.util.spec_from_file_location('migration_parent_guard',source/'guard.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
 mm,errors=g.validate_dir(source,strict=True);assert mm and not errors,errors
 assert g.development_intact(source,mm)
 s,t=migrate_docs(source,decision)
 before=fingerprint(source);tools={'engine.py':filehash(candidate/'engine.py'),'guard.py':filehash(candidate/'guard.py')}
 plan={'schema':'BATCH_A_MAINTENANCE_PLAN_V1','source_save_set_id':m['save_set_id'],'source_fingerprint':before,'candidate_tools':tools,'decision_sha256':digest(decision),'target_state_sha256':digest(s),'target_tasks_sha256':digest(t),'scope':'steps00-07','game_time_advanced':False}
 plan['plan_sha256']=digest(plan)
 if not args.apply:write(args.plan,plan);print(json.dumps({'status':'PLAN_AVAILABLE','plan_sha256':plan['plan_sha256']}));return
 if load(args.plan)!=plan:raise ValueError('MAINTENANCE_PLAN_STALE_OR_MODIFIED')
 # Candidate validation is performed on a separate complete target. This does not
 # bypass the normal upgrade gate: parent and target byte sets are independently
 # frozen, and the explicit maintenance transaction is constrained to this plan.
 os.environ.update(VOYAGER_ROOT=str(candidate),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm',PYTHONDONTWRITEBYTECODE='1')
 spec=importlib.util.spec_from_file_location('batch_a_candidate',candidate/'engine.py');api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
 # Keep all source data verbatim except the explicitly derived state/tasks and one new audit.
 for name in ('rules.json','catalog.json','events.jsonl','manifest.json'):shutil.copy2(source/name,candidate/name)
 # F16 was lost by the old repair manifest writer; restore the exact input policy.
 origin=load(candidate/'development/evidence/batch_a_origin_manifest.json');manifest=load(candidate/'manifest.json');manifest['asset_policy']=copy.deepcopy(origin['asset_policy']);write(candidate/'manifest.json',manifest)
 s['world_state_overrides']['current_handoff_snapshot']=api._handoff_projection(s,t,m['save_set_id'])
 write(candidate/'state.json',s);write(candidate/'tasks.json',t)
 event={'event_id':'EVT-BATCH-A-'+plan['plan_sha256'][:24],'type':'system','subtype':'batch_a_maintenance','game_time':s['game_time'],'zero_time':True,'summary':'Batch A evidence-bound maintenance; no gameplay actions or settlements.','source':'GAME ENGINE 2.60.0 BATCH_A_MAINTENANCE_V1','changes':[{'target':'state:engine_runtime','action':'explicit_maintenance_contracts'},{'target':'tasks:active_tasks','action':'evidence_backed_patrol_projection'}],'source_refs':['state:self','tasks:self','events:self','manifest:self'],'maintenance_plan':plan['plan_sha256'],'risk_gap_policy':decision}
 api._append_engine_history(candidate/'events.jsonl',event)
 meta,events,_=api.read_history_raw(candidate/'events.jsonl');meta['game_time_current']=s['game_time'];api._native_durable_replace_bytes(candidate/'events.jsonl',api._history_replace_metadata_bytes((candidate/'events.jsonl').read_bytes(),meta))
 os.environ['VOYAGER_DEV_SOURCE_DIR']=str(candidate)
 lineage={'from_save_set_id':m['save_set_id'],'from_layout':'native_eight_component_v4_tiered_history','to_layout':'native_eight_component_v4_tiered_history','game_time_advanced':False,'batch_a_plan_sha256':plan['plan_sha256']}
 target=api._component_write_manifest_native(candidate,'V14.45',m['save_set_id'],lineage)
 report=api.run_checks(candidate,full=True,require_manifest=True)
 write(args.plan.with_name('maintenance_target_check.json'),report)
 if report['status']!='PASS':raise ValueError('MAINTENANCE_TARGET_NOT_READY:'+json.dumps(report.get('errors',[]),ensure_ascii=False))
 if fingerprint(source)!=before:raise ValueError('MAINTENANCE_SOURCE_CHANGED')
 print(json.dumps({'status':'TARGET_VALIDATED','save_set_id':target['save_set_id'],'plan_sha256':plan['plan_sha256'],'game_time':s['game_time']}))
if __name__=='__main__':main()
