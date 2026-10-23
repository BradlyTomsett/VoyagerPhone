#!/usr/bin/env python3
"""Version-bound first-stage acceptance; all game actions use isolated copies."""
import argparse,copy,hashlib,importlib.util,json,os,pathlib,shutil,sys,time,traceback
sys.dont_write_bytecode=True
P=pathlib.Path
def load_api(root,name='stage1_test',dev=False):
    os.environ.update(VOYAGER_ROOT=str(root),PYTHONDONTWRITEBYTECODE='1',VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm')
    os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None)
    path=root/('development/devsrc/runtime.py' if dev else 'engine.py')
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m.load(root/'engine.py')[0] if dev else m
def read(p):return json.loads(P(p).read_text())
def sha(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()
def reject(fn,part=None):
    try:fn()
    except Exception as ex:
        if part is not None:assert part in str(ex),str(ex)
        return str(ex)
    raise AssertionError('EXPECTED_REJECTION')
def clone(source,out):
    shutil.copytree(source,out,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'))
    return out
def envelope(a,root,command):
    now=a.read_json(root/'state.json')['game_time']
    return {'schema':'HOST_COMMAND_INTENT_V1','decision':'approved','subject_id':command['actor_id'],'parent_save_set_id':command['base_save_set_id'],'instruction_text':'SYNTHETIC TEST ONLY: confirm exact fixture data/action; never production authorization.','evidence_ref':'fixture:stage1-acceptance','valid_from':now,'valid_until':now,'targets':a._domain_command_targets(command),'limits':{'uses':1,'gold_units':str(10**18),'grey_units':str(10**18),'quantity':str(10**18)},'command':command}
def command(a,root,kind,cid,**fields):
    return {'schema':a.DOMAIN_COMMAND_SCHEMA,'command_id':cid,'base_save_set_id':a.read_json(root/'manifest.json')['save_set_id'],'kind':kind,'actor_id':'PER-COMMANDER-01','authorization':'host_intent','authorization_ref':'HOST:'+cid,**fields}
def day_record():
    return {'scheduled_at':'8363-12-10T23:20:00','record_kind':'actual','source_refs':['fixture:cash-and-SKU-stocktake'],'cash_receipts_copper':1500,'cash_purchases_copper':400,'other_cash_expenses_copper':20,'gross_sales_copper':1500,'cogs_copper':300,'inventory':{'status':'confirmed','opening_basis':'stocktake','opening':{'TEST_SKU':10},'purchases':{'TEST_SKU':4},'sold':{'TEST_SKU':3},'waste':{},'closing':{'TEST_SKU':11}}}
def run(source,output,groups):
    source=source.resolve();output=output.resolve()
    if output.exists() or source in output.parents:raise ValueError('NEW_EXTERNAL_TEST_OUTPUT_REQUIRED')
    output.mkdir(parents=True);a=load_api(source);rows=[];m=read(source/'manifest.json')
    before={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file() and '.runtime' not in p.parts and '__pycache__' not in p.parts and p.name!='.game_engine.lock'}
    def test(name,fn):
        start=time.perf_counter()
        try:detail=fn();rows.append({'name':name,'status':'PASS','seconds':round(time.perf_counter()-start,3),'detail':detail})
        except Exception as ex:rows.append({'name':name,'status':'FAIL','seconds':round(time.perf_counter()-start,3),'error':str(ex),'traceback':traceback.format_exc()})
        report={'schema':'STAGE1_V1453_ACCEPTANCE_V1','save_set_id':m['save_set_id'],'manifest_sha256':sha(source/'manifest.json'),'engine_sha256':sha(source/'engine.py'),'guard_sha256':sha(source/'guard.py'),'status':'PASS' if all(x['status']=='PASS' for x in rows) else 'FAIL','tests':rows}
        (output/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(rows[-1]['status'],name,rows[-1]['seconds'],flush=True)
    if 'unit' in groups:
        def baseline():
            c=read(source/'development/evidence/stage1_v1453_input_contract.json');s=a.read_json(source/'state.json');t=a.read_json(source/'tasks.json')
            assert m['save_version']=='V14.53' and m['parent_save_set_id']==c['input_save_set_id']
            assert s['game_time']==c['game_time'] and s['voyage_day']==c['voyage_day'] and s['summary']==c['summary'] and s['engine_runtime']['finance_runtime']['funds_units']==c['finance_units']
            meta,events,raw=a.read_history_raw(source/'events.jsonl');n=c['logical_history_count']
            assert len(events)==n+2 and a.sha256_bytes(b'\n'.join(raw[:n])+b'\n')==c['logical_history_raw_sha256']
            assert all(x['zero_time'] for x in events[n:]) and events[n]['subtype']=='stage1_correctness_maintenance' and events[n+1]['type']=='transaction_changeset'
            allowed={('state.json','/engine_runtime/account_registry_v1/'+x) for x in ('accounts/covert/balances/grey','accounts/covert/currencies/1','accounts/covert/legacy_read_only_views/2','accounts/covert/units_per_currency/grey','opening_migrations_v1453','opening_units/covert/grey')}
            allowed|={('state.json','/engine_runtime/business_runtime_v1'),('state.json','/world_state_overrides/current_handoff_snapshot/save_set_id')}
            allowed|={('tasks.json','/active_tasks/'+str(i)+'/'+field) for i in range(5) for field in ('semantic_context','historical_semantic_contexts')}
            allowed|={('tasks.json','/active_tasks/4/runtime_policy/'+field) for field in ('business_rule','monitor/resolver')}
            assert {(x['file'],x['path']) for x in events[n+1]['field_changes']}==allowed
            assert len(t['active_tasks'])==5 and not t['queued_tasks']
            # Every untouched declared input file must remain byte-exact.
            mutable={'engine.py','state.json','tasks.json','events.jsonl','manifest.json','development/README.md'}
            mutable.update('development/devsrc/'+x for x in ('00_prelude.py','02_authority_storage.py','11_mechanics_hazards.py','12_scheduler.py','16a_pricing_domain.py','17_domain_commands.py','20_cli.py','24_bootstrap.py','26_reliable_runtime.py','27_accounts_games.py','30_runtime_services.py','31_story_scenes.py','33_narrative_director.py','35_story_services.py','SOURCE_MANIFEST.json'))
            unchanged={n:v for n,v in c['files'].items() if n not in mutable}
            assert all(sha(source/n)==v for n,v in unchanged.items())
            assert (source/'development/HISTORICAL_README_V14.50.md').read_bytes() and sha(source/'development/HISTORICAL_README_V14.50.md')==c['files']['development/README.md']
            assert all(x.get('historical_semantic_contexts') or not x.get('semantic_context') for x in t['active_tasks'])
            return {'game_time':s['game_time'],'old_history_byte_exact':n,'zero_time_events':2,'unchanged_files':len(unchanged),'five_balances':a._five_account_balances(s)}
        test('frozen_game_facts_and_history',baseline)
        def accounts():
            s=a.read_json(source/'state.json');t=a.read_json(source/'tasks.json');gold=a._account_units(s,'fleet','gold');grey=a._account_units(s,'fleet','grey')
            assert a._account_units(s,'covert','grey')==31213200
            p={'kind':'account_transfer','source_account':'covert','destination_account':'fleet','currency':'grey','amount':'1.23','reason':'test'}
            cost=a._domain_authorization_cost(p);assert cost['grey_units']==12300
            tok=a._account_command_scope.set('TEST-TRANSFER')
            try:a._account_transfer_apply(s,p)
            finally:a._account_command_scope.reset(tok)
            assert a._account_units(s,'fleet','grey')==grey+12300 and a._account_units(s,'covert','grey')==31200900 and a._account_units(s,'fleet','gold')==gold
            assert a.accounts_integrity_report(s)['status']=='PASS'
            reject(lambda:a._account_post(s,'covert','grey',1),'QUANTUM')
            reject(lambda:a._account_transfer_apply(s,{**p,'currency':'gold'}),'MISMATCH')
            reject(lambda:a._account_transfer_apply(s,{**p,'amount':'999999999999999999'}),'INSUFFICIENT')
            assert a._pricing_account_target({'account':'covert','quote':{'total':{'currency':'grey'}}})=='state:account:covert:grey'
            # No fleet-only exemption for a grey wager.
            assert a._domain_authorization_cost({'kind':'game_session','game_action':'reserve','account_id':'covert','currency':'grey','stake_units':100})['grey_units']==100
            return cost
        test('accounts_scale_transfer_budget_and_quantum',accounts)
        def reservation():
            s=a.read_json(source/'state.json');t=a.read_json(source/'tasks.json');balance=a._account_units(s,'covert','copper')
            p={'session_id':'FULL_BALANCE','game_action':'reserve','account_id':'covert','currency':'copper','stake_units':balance,'choice':'heads','command_id':'TEST-RESERVE'}
            a._game_session_apply(s,t,p);reject(lambda:a._account_post(s,'covert','copper',-1),'RESERVED')
            a._game_session_apply(s,t,{**p,'game_action':'play'});a._game_session_apply(s,t,{**p,'game_action':'settle'})
            assert a.accounts_integrity_report(s)['status']=='PASS'
            return {'balance':a._account_units(s,'covert','copper'),'reserved':a._account_reserved(s,'covert','copper')}
        test('reserved_cash_and_game_settlement',reservation)
        def scheduler():
            s=a.read_json(source/'state.json');t=a.read_json(source/'tasks.json');now=a.parse_iso(s['game_time']);end=a.parse_iso('8363-12-11T12:00:00')
            plan=a.routineplan_packet(source,end.isoformat());barrier=plan['semantic_barrier']
            assert barrier['time']=='8363-12-10T23:20:00' and barrier['kind']=='business_reconciliation'
            assert not plan['deterministic_events']
            tt=copy.deepcopy(t);tt['active_tasks'][0]['runtime_policy']['monitor']['resolver']='UNKNOWN_TEST_RESOLVER'
            first=a._next_ai_monitor_time(tt,now,end,s)
            issues=[a._task_execution_coverage(s,tt,x,now,end) for x in tt['active_tasks']]
            assert any(x and x['reason']=='SCHEDULED_RESOLVER_UNAVAILABLE' for x in issues)
            assert first is not None
            assert a.scheduler_coverage_packet(source)['status']=='ACTION_REQUIRED'
            return barrier
        test('scheduler_business_and_unknown_resolver_barriers',scheduler)
        def business():
            s=a.read_json(source/'state.json');t=a.read_json(source/'tasks.json');task=a._task_by_id(t,'TSK-YUHUO-OPERATIONS');iso=day_record()['scheduled_at'];s['game_time']=t['game_time']=iso
            p=command(a,source,'business_day_record','TEST-DAY',task_id=task['task_id'],account_id='shop',day_record=day_record(),cash_debit_limit_copper=1044)
            env=envelope(a,source,p);env.update(valid_from=iso,valid_until=iso);tok=a._host_intent_scope.set(env)
            try:result=a._business_day_record(s,t,p)
            finally:a._host_intent_scope.reset(tok)
            check=a._business_assessment(s,task,iso)
            assert check['status']=='READY' and check['cash_delta_copper']==456 and check['profit_copper']==402 and check['prepaid_expense_copper']==154 and check['fixed_costs_copper']==624
            assert a._account_units(s,'shop','copper')==29398
            low=copy.deepcopy(s);low['engine_runtime']['account_registry_v1']['accounts']['shop']['balances']['copper']=0
            low['engine_runtime']['business_runtime_v1']['businesses']['YUHUO']['inputs'][iso]['record']['cash_receipts_copper']=0
            saved=low['engine_runtime']['business_runtime_v1']['businesses']['YUHUO']['inputs'][iso];saved['record_sha256']=a._repair_digest(saved['record'])
            assert a._business_assessment(low,task,iso)['status']=='INSUFFICIENT_FUNDS'
            bad=day_record();bad['inventory']['closing']['TEST_SKU']=100
            reject(lambda:a._business_validate_day(bad),'EQUATION')
            reject(lambda:a._business_validate_day({**day_record(),'record_kind':'forecast'}),'FORECAST')
            unknown=day_record();unknown['inventory']['status']='unknown'
            reject(lambda:a._business_validate_day(unknown),'UNCONFIRMED')
            return result
        # Isolated append-capable resolver fixture is tested by the integration group.
        test('business_cash_cost_prepaid_and_invalid_inputs',business)
        def consequences():
            original=a.read_json(source/'state.json');tasks=a.read_json(source/'tasks.json')
            def action(status,now,reason=None):
                s=copy.deepcopy(original);s['game_time']=now
                s['engine_runtime']['story_runtime_v1']['consequences']['TEST-EXPIRED']={'consequence_id':'TEST-EXPIRED','scene_id':'TEST-SCENE','status':'pending','not_before':'8363-12-09T00:00:00','not_after':'8363-12-09T01:00:00','effect_type':'pending_reply','cause_event_id':'TEST-CAUSE'}
                p={'type':'consequence_resolve','scene_id':'TEST-SCENE','consequence_id':'TEST-EXPIRED','status':status,'reason':reason or 'fixture'}
                tok=a._story_scope.set({'event_id':'TEST-RESOLUTION'})
                try:out=a._narrative_action(source,s,tasks,p)
                finally:a._story_scope.reset(tok)
                assert not a._narrative_integrity(s)
                return out,s,p
            for status in ('cancelled','expired','missed'):action(status,original['game_time'])
            action('cancelled','8363-12-08T00:00:00')
            action('delivered','8363-12-09T00:00:00');action('delivered','8363-12-09T01:00:00')
            reject(lambda:action('delivered',original['game_time']),'OUTSIDE')
            reject(lambda:action('expired','8363-12-09T01:00:00'),'NOT_EXPIRED')
            out,s,p=action('cancelled',original['game_time'])
            tok=a._story_scope.set({'event_id':'TEST-AGAIN'})
            try:reject(lambda:a._narrative_action(source,s,tasks,p),'NOT_PENDING')
            finally:a._story_scope.reset(tok)
            return {'valid_cancellation_and_expiry':True,'inclusive_delivery_window':True,'no_repeat':True}
        test('consequence_cancel_expire_and_delivery_boundaries',consequences)
        def parity():
            d=load_api(source,'stage1_development',True);s=a.read_json(source/'state.json');t=a.read_json(source/'tasks.json')
            assert d._five_account_balances(s)==a._five_account_balances(s)
            assert d._scheduler_coverage(s,t)==a._scheduler_coverage(s,t)
            assert d._domain_authorization_cost({'kind':'account_transfer','currency':'grey','amount':'1.23'})==a._domain_authorization_cost({'kind':'account_transfer','currency':'grey','amount':'1.23'})
            assert d._business_assessment(s,a._task_by_id(t,'TSK-YUHUO-OPERATIONS'),'8363-12-10T23:20:00')==a._business_assessment(s,a._task_by_id(t,'TSK-YUHUO-OPERATIONS'),'8363-12-10T23:20:00')
            return {'release_and_modules_equivalent':True}
        test('development_release_service_equivalence',parity)
        def outputs():
            expected=a._five_account_balances(a.read_json(source/'state.json'))
            for packet in (a.account_query_packet(source),a.visible_query_packet(source,'五项余额',detail='exact'),a.cold_start_packet(source),a.reportframe_packet(source,since='8363-12-10T17:20:00')):
                got=packet.get('five_balances') or packet.get('value') or packet.get('fleet_core',{}).get('five_balances')
                assert got==expected
                if packet.get('packet')==a.COLD_START_PACKET_SCHEMA:
                    assert packet['context_bytes']==len(json.dumps(packet,ensure_ascii=False,separators=(',',':')).encode()) and packet['context_bytes']<=3500
            reject(lambda:a.visible_query_packet(source,'五项余额',audience='observer',observer_id='HAWKE'),'OBSERVER')
            return {'five_balances_on_four_public_paths':True}
        test('five_accounts_public_paths_and_viewer_isolation',outputs)
    if 'integration' in groups:
        def integration():
            r=clone(source,output/'gameplay_copy');b=load_api(r,'stage1_gameplay')
            advanced=b.turn_session('start',until='8363-12-11T12:00:00',version='V14.54',scope='TEST ONLY first-stage boundary')
            (output/'boundary.json').write_text(json.dumps(advanced,ensure_ascii=False,indent=2,default=str)+'\n')
            assert b.read_json(r/'state.json')['game_time']=='8363-12-10T23:20:00'
            assert b._account_units(b.read_json(r/'state.json'),'shop','copper')==29398
            p=command(b,r,'business_day_record','TEST-REGISTER-DAY',task_id='TSK-YUHUO-OPERATIONS',account_id='shop',day_record=day_record(),cash_debit_limit_copper=1044)
            reject(lambda:b.domain_command_packet(r,p,'V14.55','test'),'TRUSTED_BOUNDARY')
            result=b.host_intent_command(r,envelope(b,r,p),'V14.55')
            assert result['status']=='SAVED' and b._account_units(b.read_json(r/'state.json'),'shop','copper')==29398
            parent_state=b.read_json(r/'state.json');parent_ids={e['event_id'] for e in b.read_history_raw(r/'events.jsonl')[1]}
            proof_parent=output/'business_proof_parent';proof_parent.mkdir()
            (proof_parent/'tasks.json').write_text(json.dumps(b.read_json(r/'tasks.json'),ensure_ascii=False))
            start=b.turn_session('resume',version='V14.56',scope='TEST ONLY resume')
            done=b.turn_session('advance',session_id=start['session_id'],version='V14.56',scope='TEST ONLY resolve verified business')
            (output/'completed_turn.json').write_text(json.dumps(done,ensure_ascii=False,indent=2,default=str)+'\n')
            state=b.read_json(r/'state.json');tasks=b.read_json(r/'tasks.json')
            assert state['game_time']=='8363-12-11T12:00:00'
            assert b._account_units(state,'shop','copper')==29854
            row=state['engine_runtime']['business_runtime_v1']['businesses']['YUHUO'];receipt=row['settlements']['8363-12-10T23:20:00']
            assert receipt['cash_delta_copper']==456 and receipt['profit_copper']==402 and receipt['prepaid_expense_copper']==154
            assert row['inventory']=={'TEST_SKU':11} and len(row['settlements'])==1
            events=[e for e in b.read_history_raw(r/'events.jsonl')[1] if e['event_id'] not in parent_ids]
            b._business_settlement_proofs(r,proof_parent,parent_state,state,events)
            # Matching forged event/state copies must still fail recomputation.
            for field in ('cash_delta_copper','fixed_costs_copper'):
                fake_state=copy.deepcopy(state);fake_events=copy.deepcopy(events)
                fake=fake_state['engine_runtime']['business_runtime_v1']['businesses']['YUHUO']['settlements']['8363-12-10T23:20:00'];fake[field]+=1
                for ev in fake_events:
                    if ev.get('event_id')==fake['event_id']:ev['business_settlement']=copy.deepcopy(fake)
                reject(lambda:b._business_settlement_proofs(r,proof_parent,parent_state,fake_state,fake_events),'RECOMPUTE')
            assert b._task_by_id(tasks,'TSK-YUHUO-OPERATIONS')['runtime_policy']['monitor']['next_review_at']=='8363-12-11T23:20:00'
            repeated=b.host_intent_command(r,envelope(b,r,p),'V14.57')
            assert repeated['status']=='ALREADY_APPLIED'
            assert b._resolver_business_daily(r,state,tasks,b._task_by_id(tasks,'TSK-YUHUO-OPERATIONS'),b.parse_iso('8363-12-10T23:20:00'))['status']=='ALREADY_APPLIED'
            check=b.run_checks(r,full=True);assert check['status']=='PASS',check['errors']
            return {'boundary_committed':True,'registered_without_cash_change':True,'cash_after':29854,'one_payroll':True,'COGS_no_cash_debit':True,'prepaid_not_paid_again':True,'retry_idempotent':True,'fullcheck':check['status']}
        test('real_session_register_settle_and_retry',integration)
        def transaction():
            r=clone(source,output/'transfer_copy');b=load_api(r,'stage1_transfer');p=command(b,r,'account_transfer','TEST-GREY-TRANSFER',source_account='covert',destination_account='fleet',currency='grey',amount='1.23',reason='TEST ONLY')
            env=envelope(b,r,p);denied=copy.deepcopy(env);denied['limits']['grey_units']='12299'
            reject(lambda:b.host_intent_command(r,denied,'V14.54'),'LIMIT_EXCEEDED')
            out=b.host_intent_command(r,env,'V14.54');assert out['status']=='SAVED'
            state=b.read_json(r/'state.json');assert b._account_units(state,'covert','grey')==31200900
            assert b.host_intent_command(r,env,'V14.55')['status']=='ALREADY_APPLIED'
            bad={**p,'amount':'1.24'};reject(lambda:b.host_intent_command(r,envelope(b,r,bad),'V14.55'),'DIFFERENT_PAYLOAD')
            assert b.run_checks(r,full=True)['status']=='PASS'
            return {'real_commit_and_retry':True,'grey_budget_cannot_bypass_covert':True}
        test('real_grey_transfer_authorization_and_idempotency',transaction)
        def covert_price():
            r=clone(source,output/'covert_price_copy');b=load_api(r,'stage1_covert_price')
            request={'item_id':'SUPPLY-FOOD','unit':'包','quantity':10,'currency':'grey','transaction_type':'purchase'}
            q=b.calculate_price_quote(request,r);assert q['status']=='VALID',q
            delivery={'inventory_ref':'state:inventories.supply_inventory.fleets.voyager.food.value','delta':10,'unit':'包'}
            confirmed={'settlement_id':'COVERT-GREY-TEST','quote_id':q['quote_id'],'binding_sha256':q['binding_sha256'],'direction':'debit','account':'covert','status':'completed','cash_amount':q['total'],'asset_disposition_verified':True,'inventory_delivery':delivery}
            # Explicit isolated confirmed-event fixture, never a production write.
            b._append_engine_history(r/'events.jsonl',{'event_id':'TEST-ONLY-COVERT-PRICE','type':'system','game_time':b.read_json(r/'state.json')['game_time'],'summary':'SYNTHETIC TEST ONLY confirmed delivery','confirmed_price_settlement':confirmed})
            m=b.read_json(r/'manifest.json');b._component_write_manifest_native(r,m['save_version'],m['parent_save_set_id'],m['migration_lineage'])
            q=b.calculate_price_quote(request,r);p=command(b,r,'settle_price','TEST-COVERT-PRICE',settlement_id='COVERT-GREY-TEST',quote=q,direction='debit',account='covert',source_event_id='TEST-ONLY-COVERT-PRICE',delivery=delivery)
            before=b.read_json(r/'state.json');cost=b._domain_authorization_cost(p)
            assert cost['grey_units']==b._money_units_currency(q['total']['amount'],'grey') and cost['grey_units']>0
            out=b.host_intent_command(r,envelope(b,r,p),'V14.54');assert out['status']=='SAVED'
            after=b.read_json(r/'state.json')
            assert b._account_units(after,'covert','grey')==b._account_units(before,'covert','grey')-cost['grey_units']
            assert after['engine_runtime']['finance_runtime']['funds_units']==before['engine_runtime']['finance_runtime']['funds_units']
            assert b.get_by_path(after,delivery['inventory_ref'][6:])==b.get_by_path(before,delivery['inventory_ref'][6:])+10
            assert b.host_intent_command(r,envelope(b,r,p),'V14.55')['status']=='ALREADY_APPLIED'
            check=b.run_checks(r,full=True);assert check['status']=='PASS',check['errors']
            return {'covert_grey_quote_and_real_settlement':True,'main_accounts_unchanged':True,'inventory_delivered':10,'grey_debit_units':cost['grey_units'],'retry_idempotent':True,'fullcheck':'PASS'}
        test('real_covert_grey_price_settlement_and_delivery',covert_price)
    unchanged=all((source/n).is_file() and sha(source/n)==v for n,v in before.items())
    test('test_source_not_mutated',lambda: {'unchanged':True} if unchanged else (_ for _ in ()).throw(AssertionError('SOURCE_MUTATED')))
    return 0 if all(r['status']=='PASS' for r in rows) else 1
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=P,default=P(__file__).resolve().parents[2]);p.add_argument('--output',type=P,required=True);p.add_argument('--groups',default='unit,integration');ns=p.parse_args();raise SystemExit(run(ns.source,ns.output,set(ns.groups.split(','))))
