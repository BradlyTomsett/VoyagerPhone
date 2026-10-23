#!/usr/bin/env python3
"""Exact attached V14.58 -> V14.59; native manifest-last zero-time maintenance.
Work on an independent copy; no business data or old logical event bytes change.
"""
from pathlib import Path
import sys,os,json,hashlib,importlib.util,shutil,argparse
sys.dont_write_bytecode=True
P=Path
p=argparse.ArgumentParser();p.add_argument('--root',type=P,required=True);p.add_argument('--candidate',type=P,required=True);p.add_argument('--audit',type=P,required=True);args=p.parse_args();root=args.root.resolve();candidate=args.candidate.resolve();out=args.audit.resolve();out.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()
def write(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n')
def api(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
os.environ.update(VOYAGER_ROOT=str(root),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm',PYTHONDONTWRITEBYTECODE='1');old=api(root/'engine.py','parent');initial=old.strict_json_load(root/'manifest.json');assert initial['save_set_id']=='SAVESET-V14.58-00f16348a31896bf';old.ensure_source_ready(root,allow_cache=False)
os.environ['VOYAGER_ROOT']=str(candidate);new=api(candidate/'engine.py','candidate');assert sha(candidate/'guard.py')==new.BUNDLED_GUARD_SHA256
hashes={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and '.runtime' not in p.parts and '__pycache__' not in p.parts and p.name!='.game_engine.lock'};stage=P(old.create_stage(root,'migration_batch2')['staging'])
for path in (candidate/'development').rglob('*'):
 if path.is_file() and '__pycache__' not in path.parts:
  dest=stage/path.relative_to(candidate);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
for name in ['engine.py','guard.py']:shutil.copyfile(candidate/name,stage/name)
om,oe,ob=old.read_history_raw(root/'events.jsonl');plan={'parent':initial['save_set_id'],'candidate_engine_sha256':sha(candidate/'engine.py'),'guard_sha256':sha(candidate/'guard.py'),'source_hashes':hashes,'old_history_count':len(oe),'old_history_raw_sha256':old.sha256_bytes(b'\n'.join(ob)+b'\n'),'unchanged':['state.json','tasks.json','rules.json','catalog.json'],'zero_time':True};plan['digest']=new._repair_digest(plan);write('plan.json',plan)
new._append_engine_history(stage/'events.jsonl',{'event_id':'MAINT-V1459-'+plan['digest'][:20],'type':'system','subtype':'performance_batch2_followup_maintenance','game_time':initial['game_time'],'zero_time':True,'summary':'第二批性能补齐：查询只读投影、旧披露与别名索引、修复快照去重。无业务效果。','changes':[],'authority_files':[],'source':'ENGINE2.70.0','maintenance_plan_sha256':plan['digest']})
files={str(p.relative_to(stage)):sha(p) for p in (stage/'development').rglob('*') if p.is_file() and '__pycache__' not in p.parts};m=new._component_write_manifest_native(stage,'V14.59',initial['save_set_id'],{'from_save_set_id':initial['save_set_id'],'from_layout':'native_eight_component_v4_tiered_history','to_layout':'native_eight_component_v4_tiered_history','game_time_advanced':False,'method':'performance_batch2_zero_time'},frozen_development_sources={'schema':'VOYAGER_DEV_SOURCES_V1','files':files,'build_command':'python3 development/build.py --output engine.py'});m['current_guide']={'path':'development/CONTINUE_V14_59.md','sha256':files['development/CONTINUE_V14_59.md'],'role':'only_current_continuation_guide'};(stage/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
for name in plan['unchanged']:assert sha(stage/name)==sha(root/name)
nm,ne,nb=new.read_history_raw(stage/'events.jsonl');assert ob==nb[:-1] and oe==ne[:-1] and len(ne)==len(oe)+1
full=new.run_checks(stage,full=True,expected_version='V14.59',parent_snapshot={'dir':root,'save_set_id':initial['save_set_id'],'version':old.parse_version('V14.58')});write('full.json',full);assert full['status']=='PASS',full['errors'];print('full PASS; publishing isolated candidate',flush=True)
with old.engine_lock(root,exclusive=True):
 assert all(sha(root/n)==digest for n,digest in hashes.items());current=old.ensure_source_ready(root,allow_cache=False);old._native_validate_stage_parent(stage,root,current);snapshot=old._native_snapshot_parent(root,current);j=old._native_make_commit_journal(root,stage,current,m,snapshot,engine_upgrade=True);write('journal.json',j);g=new._repair_guard_module(candidate)
 try:
  for rel in sorted(files):
   dest=root/rel;dest.parent.mkdir(parents=True,exist_ok=True);old._native_durable_copy(stage/rel,dest)
  for name in old.COMPONENT_FILES:
   if name!='manifest.json':old._native_durable_copy(stage/name,root/name)
  old._native_test_failpoint('batch2_before_manifest');old._native_durable_copy(stage/'manifest.json',root/'manifest.json');old._native_test_failpoint('batch2_after_manifest')
  check,errors=g.validate_dir(root,strict=True);assert check and not errors and g.development_intact(root,check),errors;g._finish_journal(root,old._native_commit_journal_path(root),j,'committed')
 except BaseException:
  result,errors=g.recover_interrupted_commit(root)
  if errors:raise ValueError('PUBLICATION_RECOVERY_FAILED:'+str(errors))
  raise
shutil.rmtree(stage);write('publication.json',{'status':'COMMITTED','save_set_id':m['save_set_id'],'game_time':m['game_time'],'engine_sha256':sha(root/'engine.py'),'guard_sha256':sha(root/'guard.py'),'manifest_sha256':sha(root/'manifest.json'),'old_history_count':len(oe),'new_history_count':len(ne),'old_history_original_bytes_unchanged':True,'unchanged_authority':plan['unchanged']});print('COMMITTED',m['save_set_id'],flush=True)
