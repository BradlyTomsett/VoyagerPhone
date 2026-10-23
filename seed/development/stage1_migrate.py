#!/usr/bin/env python3
"""Exact V14.52 -> V14.53 zero-time maintenance, native journal publication.

Use a NEW copy of the supplied parent as --root. No gameplay is performed.
The checked input contract, leaf diff, full history prefix and target manifest
are frozen before a journal is written. Guard handles interrupted publication.
"""
import argparse,contextlib,copy,hashlib,importlib.util,json,os,pathlib,shutil,sys
sys.dont_write_bytecode=True
P=pathlib.Path
INPUT_SID='SAVESET-V14.52-44c7669ed02a73ca'
def sha(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()
def load(p):return json.loads(P(p).read_text('utf-8'))
def write(p,o):P(p).parent.mkdir(parents=True,exist_ok=True);P(p).write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n')
def api(path,name):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def publish(parent,root,stage,manifest,devfiles,hashes,audit):
    with parent.engine_lock(root,exclusive=True):
        assert all(sha(root/n)==digest for n,digest in hashes.items()),'SOURCE_CHANGED_BEFORE_PUBLICATION'
        current=parent.ensure_source_ready(root,allow_cache=False);parent._native_validate_stage_parent(stage,root,current)
        snap=parent._native_snapshot_parent(root,current)
        journal=parent._native_make_commit_journal(root,stage,current,manifest,snap,engine_upgrade=True)
        write(audit/'publication_journal.json',journal)
        try:
            for rel in sorted(devfiles):
                dest=root/rel;dest.parent.mkdir(parents=True,exist_ok=True);parent._native_durable_copy(stage/rel,dest)
            for name in parent.COMPONENT_FILES:
                if name!='manifest.json':parent._native_durable_copy(stage/name,root/name)
            parent._native_test_failpoint('stage1_before_manifest')
            parent._native_durable_copy(stage/'manifest.json',root/'manifest.json')
            parent._native_test_failpoint('stage1_after_manifest')
            g=api(root/'guard.py','stage1_published_guard');m,errors=g.validate_dir(root,strict=True)
            if not m or errors or not g.development_intact(root,m):raise ValueError('PUBLISHED_SOURCE_INVALID:'+str(errors))
            parent._native_clear_journal(parent._native_commit_journal_path(root))
        except BaseException:
            parent._native_recover_interrupted_commit(root);raise
def transform(s,t,parent):
    before=copy.deepcopy(s);er=s['engine_runtime'];reg=er['account_registry_v1'];cov=reg['accounts']['covert']
    original=s['world_state_overrides']['v1452_live_continuation']['accounts']['separate_accounts']['hawk_covert_grey_1e2']
    assert original==312132 and 'grey' not in cov['currencies']
    units=original*100
    cov['currencies'].append('grey');cov['units_per_currency']['grey']=10000;cov['balances']['grey']=units
    cov['legacy_read_only_views'].append({'path':'world_state_overrides.current_handoff_snapshot.funds.covert_grey','currency':'grey','units_per_value':10000,'format':'decimal_text','available_only':False})
    reg['opening_units']['covert']['grey']=units
    reg['opening_migrations_v1453']=[{'account_id':'covert','currency':'grey','integer_units':str(units),'units_per_currency':10000,'quantum':100,'source_ref':'state:world_state_overrides.v1452_live_continuation.accounts.separate_accounts.hawk_covert_grey_1e2','source_units_per_currency':100,'source_save_set_id':parent,'kind':'accepted_existing_balance_not_income','zero_cash_change':True}]
    task=next(x for x in t['active_tasks'] if x['task_id']=='TSK-YUHUO-OPERATIONS');mon=task['runtime_policy']['monitor'];assert mon['next_review_at']=='8363-12-10T23:20:00'
    mon['resolver']='business_daily_settlement_v1'
    task['runtime_policy']['business_rule']={'schema':'BUSINESS_DAILY_RULE_V1','business_id':'YUHUO','account_id':'shop','currency':'copper','repeat_seconds':86400,'effective_from':mon['next_review_at'],'time_basis':'existing_game_time_no_real_clock','fixed_costs':{'wages':520,'meals':96,'ppe':8},'prepaid_contract_refs':['world_state_overrides.freeport_xilu9_current.hawke_commercial_cover.reto_guard_contract_live.contract'],'authorization_basis':{'source_save_set_id':parent,'task_id':task['task_id'],'source_ref':'tasks:TSK-YUHUO-OPERATIONS.autonomy','scope':'existing authorized ordinary operation; unknown actuals require trusted confirmation'}}
    er['business_runtime_v1']={'schema':'BUSINESS_RUNTIME_V1','businesses':{'YUHUO':{'task_id':task['task_id'],'opening_at':s['game_time'],'inventory_status':'unknown','inventory':{},'inputs':{},'settlements':{},'last_settled_at':None,'historical_gaps':['12/05 prior POS incomplete; no backfill','12/10 SKU stocktake not confirmed; historical quantities are not present inventory']}}}
    for task in t['active_tasks']:
        if task.get('semantic_context'):
            task['historical_semantic_contexts']=[{'text':task['semantic_context'],'source_save_set_id':parent,'role':'historical_source_text_not_current_state'}]
            task['semantic_context']='当前状态、金额和下一节点由 task_data、runtime_policy.monitor 及 view_rule 的权威 STATE 引用派生。旧日期说明保存在 historical_semantic_contexts，不作为当前事实。'
    assert s['game_time']==before['game_time'] and reg['ledger']==before['engine_runtime']['account_registry_v1']['ledger']
    return s,t

def migrate(root,candidate,audit):
    root=root.resolve();candidate=candidate.resolve();audit=audit.resolve()
    if root==candidate or root in candidate.parents or candidate in root.parents:raise ValueError('INDEPENDENT_PARENT_AND_CANDIDATE_REQUIRED')
    os.environ.update(VOYAGER_ROOT=str(root),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm',PYTHONDONTWRITEBYTECODE='1')
    os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None)
    parent=api(root/'engine.py','stage1_parent')
    initial=load(root/'manifest.json');assert initial['save_set_id']==INPUT_SID,'EXACT_INPUT_REQUIRED'
    baseline=parent.ensure_source_ready(root,allow_cache=False)
    assert baseline['save_set_id']==INPUT_SID
    hashes={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and '.runtime' not in p.parts and p.name!='.game_engine.lock' and '__pycache__' not in p.parts}
    sm=load(candidate/'development/devsrc/SOURCE_MANIFEST.json');assert sm['engine_version']=='2.64.0'
    assert (candidate/'guard.py').read_bytes()==(root/'guard.py').read_bytes()
    assert (candidate/'engine.py').read_bytes()=='# GENERATED FILE — edit development/devsrc modules, then run development/build.py.\n'.encode()+b''.join((candidate/'development/devsrc'/n).read_bytes() for n in sm['order'])+b'\nif __name__=="__main__":raise SystemExit(main())\n'
    cmod=api(candidate/'engine.py','stage1_candidate')
    with contextlib.nullcontext():
        stage=P(parent.create_stage(root,'migration_v1453')['staging'])
        for p in (candidate/'development').rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:
                dest=stage/p.relative_to(candidate);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
        for name in ('engine.py','guard.py'):shutil.copyfile(candidate/name,stage/name)
        state,tasks=transform(load(root/'state.json'),load(root/'tasks.json'),INPUT_SID)
        cmod._write_authority_json(stage/'state.json',state);cmod._write_authority_json(stage/'tasks.json',tasks)
        fields=cmod._event_v3_field_changes(root,stage,{'state.json','tasks.json'})
        plan={'schema':'V1453_STAGE1_MAINTENANCE_PLAN_V1','source_save_set_id':INPUT_SID,'source_files':hashes,'candidate_engine_sha256':sha(candidate/'engine.py'),'candidate_guard_sha256':sha(candidate/'guard.py'),'field_changes':fields,'zero_time':True,'cash_or_assets_changed':False}
        plan['plan_sha256']=cmod._repair_digest(plan)
        write(audit/'migration_plan.json',plan)
        # Exact allowlist is generated from the proposed plan, reviewed by tests.
        cmod._append_engine_history(stage/'events.jsonl',{'event_id':'MAINT-V1453-'+plan['plan_sha256'][:20],'type':'system','subtype':'stage1_correctness_maintenance','game_time':state['game_time'],'zero_time':True,'summary':'第一阶段零时间维护：接入已有潜伏灰币；修复店铺日结调度与待核对边界、当前说明及后果生命周期。没有新收入、工资支付、库存盘点、人物行动或随机消费。','changes':[{'target':'state:engine_runtime.account_registry_v1','action':'register_accepted_existing_grey_balance'},{'target':'state:engine_runtime.business_runtime_v1','action':'initialize_empty_future_business_contract'},{'target':'tasks:active_tasks','action':'connect_business_resolver_and_archive_stale_current_text'}],'authority_files':['state.json','tasks.json'],'source':'GAME ENGINE 2.64.0 STAGE1_MAINTENANCE','maintenance_plan_sha256':plan['plan_sha256']})
        cmod._ensure_transaction_changeset(root,stage,'V14.53 stage1 zero-time maintenance')
        devfiles={str(p.relative_to(stage)):sha(p) for p in (stage/'development').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        manifest=cmod._component_write_manifest_native(stage,'V14.53',INPUT_SID,{'from_save_set_id':INPUT_SID,'from_layout':'native_eight_component_v4_tiered_history','to_layout':'native_eight_component_v4_tiered_history','game_time_advanced':False,'method':'stage1_zero_time_maintenance_native_journal','maintenance_plan_sha256':plan['plan_sha256']},frozen_development_sources={'schema':'VOYAGER_DEV_SOURCES_V1','files':devfiles,'build_command':'python3 development/build.py --output engine.py'})
        manifest['current_guide']={'path':'development/CONTINUE_V14_53.md','sha256':devfiles['development/CONTINUE_V14_53.md'],'role':'only_current_continuation_guide'}
        write(stage/'manifest.json',manifest)
        print('candidate migration built; running fullcheck',flush=True)
        check=cmod.run_checks(stage,full=True,expected_version='V14.53',parent_snapshot={'dir':root,'save_set_id':INPUT_SID,'version':parent.parse_version('V14.52')})
        write(audit/'migration_fullcheck.json',check)
        if check['status']!='PASS':raise ValueError('MIGRATION_CHECK_FAILED:'+str(check['errors']))
        oldmeta,oldevents,oldraw=parent.read_history_raw(root/'events.jsonl');newmeta,newevents,newraw=cmod.read_history_raw(stage/'events.jsonl')
        assert newraw[:len(oldraw)]==oldraw and len(newraw)==len(oldraw)+2
        assert all(e.get('zero_time') for e in newevents[len(oldevents):])
        # Candidate tests and established upgrade gates precede all parent writes.
        print('fullcheck PASS; running established native selftest',flush=True)
        st=cmod.native_component_selftest(stage);write(audit/'candidate_selftest.json',st)
        if st['status']!='PASS':raise ValueError('CANDIDATE_SELFTEST_FAILED')
        print('native selftest PASS; running compatibility/performance/cold CLI gates',flush=True)
        preflight=cmod._phase4_native_preflight(root,candidate/'engine.py',candidate/'guard.py',cmod,stage,stage);write(audit/'upgrade_preflight.json',preflight)
        assert preflight['status']=='PASS'
        publish(parent,root,stage,manifest,devfiles,hashes,audit)
        write(audit/'publication.json',{'status':'COMMITTED','save_set_id':manifest['save_set_id'],'game_time':state['game_time'],'old_events':len(oldevents),'new_events':len(newevents),'old_history_raw_sha256':parent.sha256_bytes(b'\n'.join(oldraw)+b'\n'),'old_history_unchanged':True,'guard_unchanged':True,'journal_protocol':'VOYAGER_NATIVE_COMMIT_JOURNAL_V2','publication_manifest_last':True})
        shutil.rmtree(stage)
    print(json.dumps({'status':'COMMITTED','save_set_id':manifest['save_set_id'],'version':'V14.53','game_time':state['game_time']},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=P,required=True);p.add_argument('--candidate',type=P,default=P(__file__).resolve().parents[1]);p.add_argument('--audit',type=P,required=True);a=p.parse_args();migrate(a.root,a.candidate,a.audit)
