#!/usr/bin/env python3
"""Exact attached V14.60 -> V14.61, zero-time native manifest-last upgrade.
Use an independent unchanged parent copy and this edited candidate. Does not
invent biographies, advance time, execute life nodes or rewrite logical history.
"""
import argparse,copy,hashlib,importlib.util,json,os,pathlib,shutil,sys
sys.dont_write_bytecode=True
P=pathlib.Path
INPUT_SID='SAVESET-V14.60-50a40db20c5a8242'
def sha(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()
def read(p):return json.loads(P(p).read_text())
def write(p,v):P(p).parent.mkdir(parents=True,exist_ok=True);P(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
def api(path,name):
 s=importlib.util.spec_from_file_location(name,path);a=importlib.util.module_from_spec(s);s.loader.exec_module(a);return a
def migrate(root,candidate,audit):
 root=root.resolve();candidate=candidate.resolve();audit=audit.resolve()
 assert root!=candidate and root not in candidate.parents and candidate not in root.parents
 os.environ.update(VOYAGER_ROOT=str(root),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm',PYTHONDONTWRITEBYTECODE='1')
 parent=api(root/'engine.py','lw_parent');m=read(root/'manifest.json');assert m['save_set_id']==INPUT_SID;parent.ensure_source_ready(root,allow_cache=False)
 hashes={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and '.runtime' not in p.parts and '__pycache__' not in p.parts and p.name!='.game_engine.lock'}
 new=api(candidate/'engine.py','lw_candidate');assert new.ENGINE_VERSION=='2.72.0' and sha(candidate/'guard.py')==new.BUNDLED_GUARD_SHA256
 stage=P(parent.create_stage(root,'living_world_maintenance')['staging'])
 for p in (candidate/'development').rglob('*'):
  if p.is_file() and '__pycache__' not in p.parts:
   dest=stage/p.relative_to(candidate);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
 for name in ('engine.py','guard.py'):shutil.copyfile(candidate/name,stage/name)
 state=read(root/'state.json');rules=read(root/'rules.json');old=copy.deepcopy(state)
 rt=state['engine_runtime']['living_world_v1']
 # Preserve all existing biographies, game facts, visits, plans and receipts.
 # Old public actors are observations, not proof of actual player control.
 if rt.get('player_characters'):rt['legacy_observed_pov']=copy.deepcopy(rt['player_characters'])
 rt['controls']={};rt['player_characters']=[];rt.setdefault('presence_epochs',{});rt['policy_version']=2
 new._write_authority_json(stage/'state.json',state);new._write_authority_json(stage/'rules.json',rules)
 # Exact old game state outside the explicit control/presence contract fields.
 reverted=copy.deepcopy(read(stage/'state.json'));reverted['engine_runtime']['living_world_v1']=copy.deepcopy(old['engine_runtime']['living_world_v1']);assert reverted==old
 _,oe,ob=parent.read_history_raw(root/'events.jsonl');fields=new._event_v3_field_changes(root,stage,{'state.json'})
 plan={'schema':'LIVING_WORLD_MAINTENANCE_V1','parent':INPUT_SID,'engine_sha256':sha(candidate/'engine.py'),'guard_sha256':sha(candidate/'guard.py'),'field_changes':fields,'zero_time':True,'old_history_count':len(oe),'old_history_raw_sha256':new.sha256_bytes(b'\n'.join(ob)+b'\n'),'unchanged':['tasks.json','catalog.json','rules.json'],'old_business_state_exact':True,'new_game_events':0};plan['digest']=new._repair_digest(plan);write(audit/'plan.json',plan)
 new._append_engine_history(stage/'events.jsonl',{'event_id':'MAINT-V1461-'+plan['digest'][:20],'type':'system','subtype':'living_world_bugfix_maintenance','game_time':m['game_time'],'zero_time':True,'summary':'修复生活系统的身份、记忆、在场、视角、背景证据、历史重写、日程、访问、预算、控制与原子行动时钟；保持游戏进度。','changes':[{'target':'state:engine_runtime.living_world_v1','action':'explicit_control_and_presence_contract_upgrade'}],'authority_files':['state.json'],'source':'GAME ENGINE 2.72.0','maintenance_plan_sha256':plan['digest']})
 new._ensure_transaction_changeset(root,stage,'V14.61 zero-time living-world bug fixes')
 files={str(p.relative_to(stage)):sha(p) for p in (stage/'development').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
 target=new._component_write_manifest_native(stage,'V14.61',INPUT_SID,{'from_save_set_id':INPUT_SID,'from_layout':'native_eight_component_v4_tiered_history','to_layout':'native_eight_component_v4_tiered_history','game_time_advanced':False,'method':'living_world_bugfix_zero_time_native_journal'},frozen_development_sources={'schema':'VOYAGER_DEV_SOURCES_V1','files':files,'build_command':'python3 development/build.py --output engine.py'})
 target['current_guide']={'path':'development/CONTINUE_V14_61.md','sha256':files['development/CONTINUE_V14_61.md'],'role':'only_current_continuation_guide'};write(stage/'manifest.json',target)
 _,ne,nb=new.read_history_raw(stage/'events.jsonl');assert nb[:-2]==ob and len(ne)==len(oe)+2 and all(e['zero_time'] for e in ne[-2:])
 for n in plan['unchanged']:assert sha(root/n)==sha(stage/n)
 full=new.run_checks(stage,full=True,expected_version='V14.61',parent_snapshot={'dir':root,'save_set_id':INPUT_SID,'version':parent.parse_version('V14.60')});write(audit/'full.json',full);assert full['status']=='PASS',full['errors']
 with parent.engine_lock(root,exclusive=True):
  assert all(sha(root/n)==h for n,h in hashes.items());current=parent.ensure_source_ready(root,allow_cache=False);parent._native_validate_stage_parent(stage,root,current);snap=parent._native_snapshot_parent(root,current);j=parent._native_make_commit_journal(root,stage,current,target,snap,engine_upgrade=True);g=api(candidate/'guard.py','lw_guard')
  try:
   for rel in sorted(files):
    dest=root/rel;dest.parent.mkdir(parents=True,exist_ok=True);parent._native_durable_copy(stage/rel,dest)
   for name in parent.COMPONENT_FILES:
    if name!='manifest.json':parent._native_durable_copy(stage/name,root/name)
   parent._native_durable_copy(stage/'manifest.json',root/'manifest.json');check,errors=g.validate_dir(root,strict=True);assert check and not errors and g.development_intact(root,check),errors;g._finish_journal(root,parent._native_commit_journal_path(root),j,'committed')
  except BaseException:
   g.recover_interrupted_commit(root);raise
 shutil.rmtree(stage);write(audit/'publication.json',{'status':'COMMITTED','save_set_id':target['save_set_id'],'game_time':target['game_time'],'old_history_count':len(oe),'new_history_count':len(ne),'old_history_byte_exact':True,'old_game_state_exact_except_control_presence_contract':True,'new_people':0,'new_game_events':0,'unchanged_authority':plan['unchanged']});print('COMMITTED',target['save_set_id'],flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=P,required=True);p.add_argument('--candidate',type=P,required=True);p.add_argument('--audit',type=P,required=True);a=p.parse_args();migrate(a.root,a.candidate,a.audit)
