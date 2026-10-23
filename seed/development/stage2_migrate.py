#!/usr/bin/env python3
"""Exact V14.53 -> V14.54, tool-only zero-time upgrade via native journal.

Run on a NEW independent copy. Validates candidate and history before publication;
state/tasks/rules/catalog remain byte-exact. One zero-effect maintenance event.
"""
import argparse,hashlib,importlib.util,json,os,pathlib,shutil,sys
sys.dont_write_bytecode=True
P=pathlib.Path
INPUT_SID='SAVESET-V14.53-0286a558f6516026'
def sha(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()
def load(p):return json.loads(P(p).read_text('utf-8'))
def write(p,o):P(p).parent.mkdir(parents=True,exist_ok=True);P(p).write_text(json.dumps(o,ensure_ascii=False,indent=2,default=str)+'\n')
def api(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def migrate(root,candidate,audit):
    root=root.resolve();candidate=candidate.resolve();audit=audit.resolve()
    if root==candidate or root in candidate.parents or candidate in root.parents:raise ValueError('INDEPENDENT_PARENT_AND_CANDIDATE_REQUIRED')
    os.environ.update(VOYAGER_ROOT=str(root),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm',PYTHONDONTWRITEBYTECODE='1')
    os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None)
    parent=api(root/'engine.py','stage2_parent');initial=load(root/'manifest.json');assert initial['save_set_id']==INPUT_SID,'EXACT_INPUT_REQUIRED'
    parent.ensure_source_ready(root,allow_cache=False)
    hashes={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and '.runtime' not in p.parts and p.name!='.game_engine.lock' and '__pycache__' not in p.parts}
    cmod=api(candidate/'engine.py','stage2_candidate');sm=load(candidate/'development/devsrc/SOURCE_MANIFEST.json');assert sm['engine_version']=='2.65.0'
    assert (candidate/'guard.py').read_bytes()==(root/'guard.py').read_bytes()
    assert (candidate/'engine.py').read_bytes()=='# GENERATED FILE — edit development/devsrc modules, then run development/build.py.\n'.encode()+b''.join((candidate/'development/devsrc'/n).read_bytes() for n in sm['order'])+b'\nif __name__=="__main__":raise SystemExit(main())\n'
    stage=P(parent.create_stage(root,'migration_v1454')['staging'])
    for p in (candidate/'development').rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:
            dest=stage/p.relative_to(candidate);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    for name in ('engine.py','guard.py'):shutil.copyfile(candidate/name,stage/name)
    oldmeta,oldevents,oldraw=parent.read_history_raw(root/'events.jsonl')
    plan={'schema':'V1454_STAGE2_MAINTENANCE_PLAN_V1','input_save_set_id':INPUT_SID,'source_files':hashes,'candidate_engine_sha256':sha(candidate/'engine.py'),'candidate_guard_sha256':sha(candidate/'guard.py'),'field_changes':[],'unchanged_authority_files':['state.json','tasks.json','rules.json','catalog.json'],'zero_time':True,'old_history_raw_sha256':parent.sha256_bytes(b'\n'.join(oldraw)+b'\n'),'old_history_count':len(oldevents),'maintenance_events':1,'new_game_events':0}
    plan['plan_sha256']=cmod._repair_digest(plan);write(audit/'migration_plan.json',plan)
    cmod._append_engine_history(stage/'events.jsonl',{'event_id':'MAINT-V1454-'+plan['plan_sha256'][:20],'type':'system','subtype':'stage2_performance_maintenance','game_time':initial['game_time'],'zero_time':True,'summary':'第二阶段零时间维护：共享只读快照，真实字节绑定事务验证复用、只读历史视图、编译证明及紧凑输出。未改变游戏时间、五账、资产、任务或随机状态。','changes':[],'authority_files':[],'source':'GAME ENGINE 2.65.0 STAGE2_MAINTENANCE','maintenance_plan_sha256':plan['plan_sha256']})
    assert cmod._ensure_transaction_changeset(root,stage,'V14.54 tool-only maintenance')['status']=='NOOP'
    devfiles={str(p.relative_to(stage)):sha(p) for p in (stage/'development').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    manifest=cmod._component_write_manifest_native(stage,'V14.54',INPUT_SID,{'from_save_set_id':INPUT_SID,'from_layout':'native_eight_component_v4_tiered_history','to_layout':'native_eight_component_v4_tiered_history','game_time_advanced':False,'method':'stage2_zero_time_native_journal','maintenance_plan_sha256':plan['plan_sha256']},frozen_development_sources={'schema':'VOYAGER_DEV_SOURCES_V1','files':devfiles,'build_command':'python3 development/build.py --output engine.py'})
    manifest['current_guide']={'path':'development/CONTINUE_V14_54.md','sha256':devfiles['development/CONTINUE_V14_54.md'],'role':'only_current_continuation_guide'};write(stage/'manifest.json',manifest)
    for n in plan['unchanged_authority_files']:assert sha(root/n)==sha(stage/n)
    newmeta,newevents,newraw=cmod.read_history_raw(stage/'events.jsonl');assert newraw[:len(oldraw)]==oldraw and len(newraw)==len(oldraw)+1 and newevents[-1]['zero_time']
    print('candidate migration built; fullcheck',flush=True)
    check=cmod.run_checks(stage,full=True,expected_version='V14.54',parent_snapshot={'dir':root,'save_set_id':INPUT_SID,'version':parent.parse_version('V14.53')});write(audit/'migration_fullcheck.json',check)
    assert check['status']=='PASS',check['errors']
    print('fullcheck PASS; native selftest',flush=True)
    st=cmod.native_component_selftest(stage);write(audit/'native_selftest.json',st);assert st['status']=='PASS',st
    print('selftest PASS; compatibility, performance and cold boot gates',flush=True)
    preflight=cmod._phase4_native_preflight(root,candidate/'engine.py',candidate/'guard.py',cmod,stage,stage);write(audit/'upgrade_preflight.json',preflight);assert preflight['status']=='PASS'
    publisher=api(candidate/'development/stage1_migrate.py','native_publisher')
    # Reuse the existing native publisher including manifest-last order, Guard and
    # unknown-write refusal; do not rewrite authority and merely refresh hashes.
    publisher.publish(parent,root,stage,manifest,devfiles,hashes,audit)
    write(audit/'publication.json',{'status':'COMMITTED','save_set_id':manifest['save_set_id'],'game_time':initial['game_time'],'unchanged_authority_files':plan['unchanged_authority_files'],'old_history_count':len(oldevents),'new_history_count':len(newevents),'new_event_id':newevents[-1]['event_id'],'zero_effect_events':1,'new_game_events':0,'old_history_raw_sha256':plan['old_history_raw_sha256'],'old_history_byte_exact':True,'guard_unchanged':True})
    shutil.rmtree(stage);print(json.dumps({'status':'COMMITTED','save_set_id':manifest['save_set_id'],'version':'V14.54'},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=P,required=True);p.add_argument('--candidate',type=P,default=P(__file__).resolve().parents[1]);p.add_argument('--audit',type=P,required=True);a=p.parse_args();migrate(a.root,a.candidate,a.audit)
