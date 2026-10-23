#!/usr/bin/env python3
"""Exact V14.54 -> V14.55, equivalent zero-time story runtime upgrade via native journal.

Run on a NEW independent copy. Validates candidate and history before publication;
one new reference-only state branch; tasks/rules/catalog remain byte-exact.
One maintenance event and one zero-time transaction changeset.
"""
import argparse,copy,hashlib,importlib.util,json,os,pathlib,shutil,sys
sys.dont_write_bytecode=True
P=pathlib.Path
INPUT_SID='SAVESET-V14.54-5b8218beebb9b3fe'
def sha(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()
def load(p):return json.loads(P(p).read_text('utf-8'))
def write(p,o):P(p).parent.mkdir(parents=True,exist_ok=True);P(p).write_text(json.dumps(o,ensure_ascii=False,indent=2,default=str)+'\n')
def api(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def migrate(root,candidate,audit,draft=False):
    root=root.resolve();candidate=candidate.resolve();audit=audit.resolve()
    if root==candidate or root in candidate.parents or candidate in root.parents:raise ValueError('INDEPENDENT_PARENT_AND_CANDIDATE_REQUIRED')
    os.environ.update(VOYAGER_ROOT=str(root),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm',PYTHONDONTWRITEBYTECODE='1')
    os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None)
    parent=api(root/'engine.py','stage3_parent');initial=load(root/'manifest.json');assert initial['save_set_id']==INPUT_SID,'EXACT_INPUT_REQUIRED'
    parent.ensure_source_ready(root,allow_cache=False)
    hashes={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and '.runtime' not in p.parts and p.name!='.game_engine.lock' and '__pycache__' not in p.parts}
    cmod=api(candidate/'engine.py','stage3_candidate');sm=load(candidate/'development/devsrc/SOURCE_MANIFEST.json');assert sm['engine_version']=='2.66.0'
    assert (candidate/'guard.py').read_bytes()==(root/'guard.py').read_bytes()
    assert (candidate/'engine.py').read_bytes()=='# GENERATED FILE — edit development/devsrc modules, then run development/build.py.\n'.encode()+b''.join((candidate/'development/devsrc'/n).read_bytes() for n in sm['order'])+b'\nif __name__=="__main__":raise SystemExit(main())\n'
    stage=P(parent.create_stage(root,'migration_v1455')['staging'])
    for p in (candidate/'development').rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:
            dest=stage/p.relative_to(candidate);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    for name in ('engine.py','guard.py'):shutil.copyfile(candidate/name,stage/name)
    oldmeta,oldevents,oldraw=parent.read_history_raw(root/'events.jsonl')
    state=load(root/'state.json');original=copy.deepcopy(state)
    assert 'story_turns_v1' not in state['engine_runtime']
    state['engine_runtime']['story_turns_v1']=cmod._s3_initial_state(state,load(root/'rules.json'))
    cmod._write_authority_json(stage/'state.json',state)
    reverted=copy.deepcopy(load(stage/'state.json'));reverted['engine_runtime'].pop('story_turns_v1');assert reverted==original
    fields=cmod._event_v3_field_changes(root,stage,{'state.json'})
    assert {(r['file'],r['path']) for r in fields}=={('state.json','/engine_runtime/story_turns_v1')}
    plan={'schema':'V1455_STAGE3_MAINTENANCE_PLAN_V1','input_save_set_id':INPUT_SID,'source_files':hashes,'candidate_engine_sha256':sha(candidate/'engine.py'),'candidate_guard_sha256':sha(candidate/'guard.py'),'field_changes':fields,'unchanged_authority_files':['tasks.json','rules.json','catalog.json'],'zero_time':True,'old_history_raw_sha256':parent.sha256_bytes(b'\n'.join(oldraw)+b'\n'),'old_history_count':len(oldevents),'maintenance_events':1,'transaction_changeset_events':1,'new_game_events':0}
    plan['plan_sha256']=cmod._repair_digest(plan);write(audit/'migration_plan.json',plan)
    cmod._append_engine_history(stage/'events.jsonl',{'event_id':'MAINT-V1455-'+plan['plan_sha256'][:20],'type':'system','subtype':'stage3_story_service_maintenance','game_time':initial['game_time'],'zero_time':True,'summary':'第三阶段零时间维护：为既有人物建立引用及未知空结构，连接可见上下文、结构化提案、单事务效果回执与后果调度。未新增人物、经历、知识传播、场景或游戏效果。','changes':[{'target':'state:engine_runtime.story_turns_v1','action':'reference_only_empty_runtime_initialization'}],'authority_files':['state.json'],'source':'GAME ENGINE 2.66.0 STAGE3_MAINTENANCE','maintenance_plan_sha256':plan['plan_sha256']})
    cmod._ensure_transaction_changeset(root,stage,'V14.55 stage3 zero-time maintenance')
    devfiles={str(p.relative_to(stage)):sha(p) for p in (stage/'development').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    manifest=cmod._component_write_manifest_native(stage,'V14.55',INPUT_SID,{'from_save_set_id':INPUT_SID,'from_layout':'native_eight_component_v4_tiered_history','to_layout':'native_eight_component_v4_tiered_history','game_time_advanced':False,'method':'stage3_zero_time_native_journal','maintenance_plan_sha256':plan['plan_sha256']},frozen_development_sources={'schema':'VOYAGER_DEV_SOURCES_V1','files':devfiles,'build_command':'python3 development/build.py --output engine.py'})
    manifest['current_guide']={'path':'development/CONTINUE_V14_55.md','sha256':devfiles['development/CONTINUE_V14_55.md'],'role':'only_current_continuation_guide'};write(stage/'manifest.json',manifest)
    for n in plan['unchanged_authority_files']:assert sha(root/n)==sha(stage/n)
    newmeta,newevents,newraw=cmod.read_history_raw(stage/'events.jsonl');assert newraw[:len(oldraw)]==oldraw and len(newraw)==len(oldraw)+2 and all(e['zero_time'] for e in newevents[len(oldraw):])
    print('candidate migration built; fullcheck',flush=True)
    check=cmod.run_checks(stage,full=True,expected_version='V14.55',parent_snapshot={'dir':root,'save_set_id':INPUT_SID,'version':parent.parse_version('V14.54')});write(audit/'migration_fullcheck.json',check)
    assert check['status']=='PASS',check['errors']
    print('fullcheck PASS; native selftest',flush=True)
    st={'status':'NOT_RUN','reason':'isolated development draft'} if draft else cmod.native_component_selftest(stage);write(audit/'native_selftest.json',st);assert draft or st['status']=='PASS',st
    print('selftest PASS; compatibility, performance and cold boot gates',flush=True)
    preflight={'status':'NOT_RUN','reason':'isolated development draft'} if draft else cmod._phase4_native_preflight(root,candidate/'engine.py',candidate/'guard.py',cmod,stage,stage);write(audit/'upgrade_preflight.json',preflight);assert draft or preflight['status']=='PASS'
    publisher=api(candidate/'development/stage1_migrate.py','native_publisher')
    # Reuse the existing native publisher including manifest-last order, Guard and
    # unknown-write refusal; do not rewrite authority and merely refresh hashes.
    publisher.publish(parent,root,stage,manifest,devfiles,hashes,audit)
    write(audit/'publication.json',{'status':'COMMITTED','draft':draft,'save_set_id':manifest['save_set_id'],'game_time':initial['game_time'],'unchanged_authority_files':plan['unchanged_authority_files'],'old_history_count':len(oldevents),'new_history_count':len(newevents),'new_event_ids':[e['event_id'] for e in newevents[len(oldraw):]],'zero_effect_events':2,'new_game_events':0,'old_history_raw_sha256':plan['old_history_raw_sha256'],'old_history_byte_exact':True,'guard_unchanged':True})
    shutil.rmtree(stage);print(json.dumps({'status':'COMMITTED','save_set_id':manifest['save_set_id'],'version':'V14.55'},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=P,required=True);p.add_argument('--candidate',type=P,default=P(__file__).resolve().parents[1]);p.add_argument('--audit',type=P,required=True);p.add_argument('--draft',action='store_true');a=p.parse_args();migrate(a.root,a.candidate,a.audit,a.draft)
