#!/usr/bin/env python3
"""Runnable acceptance tests. Mutated states and long simulations are isolated test fixtures."""
import os,sys,json,copy,shutil,tempfile,argparse,importlib.util,hashlib,datetime
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=Path(__file__).resolve().parents[3]);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--original',type=Path);args=ap.parse_args()
    base=args.base.resolve();os.environ.update(VOYAGER_ROOT=str(base),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm')
    spec=importlib.util.spec_from_file_location('voyager_acceptance',base/'engine.py');e=importlib.util.module_from_spec(spec);sys.modules[spec.name]=e;spec.loader.exec_module(e)
    state=json.loads((base/'state.json').read_text());tasks=json.loads((base/'tasks.json').read_text());checks=[]
    def check(name,fn):
        try:
            detail=fn();checks.append({'name':name,'status':'PASS','detail':detail})
        except Exception as ex:checks.append({'name':name,'status':'FAIL','error':type(ex).__name__+':'+str(ex)})
    def require(condition,detail=None):
        assert condition,detail
        return detail or True
    def rejected(fn,expected):
        try:fn()
        except e.EngineError as ex:return require(expected in str(ex),str(ex))
        raise AssertionError('operation was accepted')
    def row(s):return s['engine_runtime']['business_runtime_v1']['businesses']['YUHUO']
    def task(t=tasks,tid='TSK-YUHUO-OPERATIONS'):return e._task_by_id(t,tid)
    first=row(state)['settlements']['8363-12-10T23:20:00'];policy=row(state)['autonomy_policy']
    check('Dec10 exact profit and cash',lambda:require((first['profit_copper'],first['cash_delta_copper'],first['cash_before_copper'],first['cash_after_copper'])==(292,1006,29398,30404)))
    check('Production clock and fleet totals',lambda:require(state['game_time']=='8363-12-11T08:00:00' and state['summary']['ships']['total_player_active']==78 and state['summary']['personnel']['total_player_active']==23946 and len(tasks['active_tasks'])==5 and not tasks.get('queued_tasks')))
    check('Shop balance clearly labeled as simulated book balance',lambda:require(e._five_account_balances(state)['shop_copper']['status']=='ACCEPTED_SIMULATED_BOOK_BALANCE' and e._five_account_balances(state)['shop_copper']['balance_evidence']['physical_cash_verified'] is False))
    check('Independent account ledger equations',lambda:require(e.accounts_integrity_report(state)['status']=='PASS'))
    check('Business integrity and history',lambda:require(e.business_integrity_report(state,tasks,base)['status']=='PASS'))
    check('All monetary journal fields are integers and balance',lambda:require(all(type(x[k]) is int for x in first['accounting_journal']['lines'] for k in ('debit_copper','credit_copper')) and sum(x['debit_copper']-x['credit_copper'] for x in first['accounting_journal']['lines'])==0))
    check('Sales COGS and purchases are distinct',lambda:require(first['cogs_copper']==1700 and first['cash_purchases_copper']==1140 and first['accounting_journal']['inventory_values_copper']['closing']-first['accounting_journal']['inventory_values_copper']['opening']==-560))
    check('No duplicate prepayment or construction charge',lambda:require(first['accounting_journal']['prepaid_cash_paid_today_copper']==0 and row(state)['capital_financing_review']['cash_posted_copper']==0 and row(state)['capital_financing_review']['payment_source'] is None))
    check('Simulated inventory cannot masquerade as stocktake',lambda:require(first['inventory_status']=='continuous_simulated' and first['physical_receipts_confirmed'] is False and row(state)['historical_inventory_discrepancies'][0]['quantity']==1 and row(state)['historical_inventory_discrepancies'][0]['status']=='open'))
    check('Contract allocation expires without renewal or cash payment',lambda:require(e._business_prepaid_expense(state,e._business_rule(task()),'8363-12-20T23:20:00')[0]==154 and e._business_prepaid_expense(state,e._business_rule(task()),'8363-12-21T23:20:00')[0]==0))
    next_at=task()['runtime_policy']['monitor']['next_review_at']
    def altered_assessment(edit):
        s=copy.deepcopy(state);edit(s);before=copy.deepcopy(s);result=e._business_assessment(s,task(),next_at);require(s==before,'assessment mutated state');return result
    check('Major safety incident still blocks',lambda:require(altered_assessment(lambda s:row(s)['risk_flags'].append('safety_incident'))['status']=='INVALID'))
    check('Risk alert does not corrupt historical integrity',lambda:require((lambda s:(row(s)['risk_flags'].append('safety_incident'),e.business_integrity_report(s,tasks,base)['status'])[1])(copy.deepcopy(state))=='PASS'))
    check('Insufficient cash cannot assume sales or borrow',lambda:require(altered_assessment(lambda s:s['engine_runtime']['account_registry_v1']['accounts']['shop']['balances'].update(copper=100))['status']=='INSUFFICIENT_FUNDS'))
    def edit_policy(s,**kw):
        row(s)['autonomy_policy'].update(kw);row(s)['autonomy_policy_sha256']=e._repair_digest(row(s)['autonomy_policy'])
    check('Revenue cap enforced',lambda:require(altered_assessment(lambda s:edit_policy(s,daily_revenue_limit_copper=1))['status']=='INVALID'))
    check('Revoked policy cannot operate',lambda:require(altered_assessment(lambda s:edit_policy(s,status='revoked'))['status']=='INVALID'))
    check('Policy content tamper rejected',lambda:require(altered_assessment(lambda s:row(s)['autonomy_policy'].update(account_id='covert'))['status']=='INVALID'))
    def supplier(s):
        row(s)['autonomy_policy']['model']['air']['supply_status']='unavailable';row(s)['autonomy_policy_sha256']=e._repair_digest(row(s)['autonomy_policy'])
    check('Unavailable supplier does not create stock',lambda:require(altered_assessment(supplier)['status']=='INVALID'))
    rec=copy.deepcopy(row(state)['inputs']['8363-12-10T23:20:00']['record'])
    def malformed_inventory():
        r=copy.deepcopy(rec);r['inventory']['closing']['food']+=1;return rejected(lambda:e._business_validate_day(r),'BUSINESS_INVENTORY_EQUATION')
    check('Inventory equation corruption rejected',malformed_inventory)
    def counterfeit_stocktake():
        r=copy.deepcopy(rec);r['inventory']['status']='confirmed';r['inventory']['opening_basis']='stocktake';return rejected(lambda:e._business_validate_day(r),'BUSINESS_SIMULATION_CANNOT_CLAIM_PHYSICAL_STOCKTAKE')
    check('Simulation stocktake relabeling rejected',counterfeit_stocktake)
    def host_required():
        s=copy.deepcopy(state);t=copy.deepcopy(tasks);return rejected(lambda:e._business_day_record(s,t,{'task_id':task()['task_id'],'account_id':'shop','authorization':'host_intent','day_record':rec}),'BUSINESS_ACTUALS_REQUIRE_TRUSTED_HOST_CONFIRMATION')
    check('Untrusted real confirmation still rejected',host_required)
    def compare_stocktake():
        r=copy.deepcopy(rec);r.update(record_kind='actual',scheduled_at=next_at);r['inventory'].update(status='confirmed',opening_basis='stocktake');r['inventory']['opening']=copy.deepcopy(row(state)['inventory']);r['inventory']['opening']['trial']+=1
        for k in ('purchases','sold','waste'):r['inventory'][k]={sku:0 for sku in r['inventory']['opening']}
        r['inventory']['closing']=copy.deepcopy(r['inventory']['opening']);before=copy.deepcopy(state);out=e.business_stocktake_comparison(state,task(),r)
        return require(out['difference_quantities']['trial']==1 and out['historical_discrepancies_preserved'] and state==before)
    check('Real stocktake difference comparison preserves old discrepancy',compare_stocktake)
    with tempfile.TemporaryDirectory(prefix='business_fixture_',dir=str(args.output.resolve().parent)) as td:
        stage=Path(td)
        for n in ('state.json','tasks.json','events.jsonl'):shutil.copyfile(base/n,stage/n)
        shutil.copytree(base/'archives',stage/'archives')
        original_history=(stage/'events.jsonl').read_bytes()
        def reset():
            (stage/'events.jsonl').write_bytes(original_history);return copy.deepcopy(state),copy.deepcopy(tasks)
        def duplicate_business():
            s,t=reset();before=copy.deepcopy(s);out=e._resolver_business_daily(stage,s,t,task(t),e.parse_iso(first['scheduled_at']));return require(out['status']=='ALREADY_APPLIED' and s==before and (stage/'events.jsonl').read_bytes()==original_history)
        check('Repeated same business close is zero effect',duplicate_business)
        for tid in ('TSK-MIN-OPERATIONS','TSK-CALDER-INDUSTRIES-302','TSK-MKT-RESEARCH-DATA-SALES'):
            def future(tid=tid):
                s,t=reset();ts=task(t,tid);before=copy.deepcopy(s);resolver=e.RESOLVER_FUNCTIONS[ts['runtime_policy']['monitor']['resolver']]
                result=rejected(lambda:resolver(stage,s,t,ts,e.parse_iso(ts['runtime_policy']['monitor']['next_review_at'])),'SCHEDULED_SETTLEMENT_NOT_CURRENT_DUE_PERIOD');require(s==before);return result
            check('Future income prohibited '+tid,future)
            def duplicate(tid=tid):
                s,t=reset();ts=task(t,tid);before=copy.deepcopy(s);resolver=e.RESOLVER_FUNCTIONS[ts['runtime_policy']['monitor']['resolver']];out=resolver(stage,s,t,ts,e.parse_iso(ts['runtime_policy']['monitor']['last_reviewed_at']));return require(out['status']=='ALREADY_APPLIED' and s==before)
            check('Historical income replay prohibited '+tid,duplicate)
        def rollback():
            s,t=reset();s['game_time']=next_at;before=copy.deepcopy(s);before_t=copy.deepcopy(t);original_post=e._account_post
            def fail(*a,**kw):raise e.EngineError('TEST_SYNTHETIC_CASH_WRITE_FAILURE')
            e._account_post=fail
            try:result=rejected(lambda:e._resolver_business_daily(stage,s,t,task(t),e.parse_iso(next_at)),'TEST_SYNTHETIC_CASH_WRITE_FAILURE')
            finally:e._account_post=original_post
            require(s==before and t==before_t and (stage/'events.jsonl').read_bytes()==original_history,'partial state survived failure');return result
        check('Injected mid-settlement failure rolls input cash task history back',rollback)
        def soak():
            s,t=reset();summaries=[];previous=row(s)['inventory'];start=copy.deepcopy(s['engine_runtime']['account_registry_v1']['accounts']['covert'])
            for i in range(31):
                ts=task(t);iso=ts['runtime_policy']['monitor']['next_review_at'];s['game_time']=iso;out=e._resolver_business_daily(stage,s,t,ts,e.parse_iso(iso));require(out['status']=='COMPLETE',out)
                inv=out['inventory_movements'];require(inv['opening']==previous);require(all(inv['opening'][sku]+inv['purchases'][sku]-inv['sold'][sku]-inv['waste'][sku]==inv['closing'][sku]>=0 for sku in inv['opening']))
                require(sum(x['debit_copper']-x['credit_copper'] for x in out['accounting_journal']['lines'])==0)
                previous=copy.deepcopy(inv['closing']);summaries.append({k:out[k] for k in ('scheduled_at','cash_purchases_copper','profit_copper','cash_delta_copper','cash_after_copper','prepaid_expense_copper','inventory_loss_copper')})
                e._write_authority_json(stage/'tasks.json',t);e._write_authority_json(stage/'state.json',s)
            require(s['engine_runtime']['account_registry_v1']['accounts']['covert']==start);require(e.accounts_integrity_report(s)['status']=='PASS')
            require(len(row(s)['settlements'])==32 and row(s)['historical_inventory_discrepancies']==row(state)['historical_inventory_discrepancies'])
            (args.output.parent/'business_31day_soak.json').write_text(json.dumps({'fixture':'isolated_business_model_only_not_production_world_advance','rows':summaries},ensure_ascii=False,indent=2))
            return {'isolated_business_days':31,'through':summaries[-1]['scheduled_at'],'lowest_cash_copper':min(r['cash_after_copper'] for r in summaries),'physical_stock_claimed':False}
        check('31-day isolated business model soak',soak)
    if args.original:
        old=json.loads((args.original/'state.json').read_text());ot=json.loads((args.original/'tasks.json').read_text())
        check('Fleet assets and NPC registries preserved',lambda:require(state['asset_ledger_v1']==old['asset_ledger_v1'] and state['entity_registry']==old['entity_registry'] and state['key_personnel_current_roles']==old['key_personnel_current_roles'] and set(x['task_id'] for x in tasks['active_tasks'])==set(x['task_id'] for x in ot['active_tasks'])))
        check('Covert accounts and historical stock snapshots unchanged',lambda:require(state['engine_runtime']['account_registry_v1']['accounts']['covert']==old['engine_runtime']['account_registry_v1']['accounts']['covert'] and state['world_state_overrides']['freeport_xilu9_current']['hawke_commercial_cover']['current_inventory_exact']==old['world_state_overrides']['freeport_xilu9_current']['hawke_commercial_cover']['current_inventory_exact']))
        _,before_events,_=e.read_history_view(args.original/'events.jsonl');_,after_events,_=e.read_history_view(base/'events.jsonl')
        check('All historical hot events preserved byte-equivalent as JSON',lambda:require(after_events[:len(before_events)]==before_events,{'old_event_count':len(before_events)}))
        archives=[x for x in (args.original/'archives').iterdir() if x.is_file()]
        check('Every historical cold archive preserved byte for byte',lambda:require(all(x.read_bytes()==(base/'archives'/x.name).read_bytes() for x in archives),{'archives':len(archives)}))
        new=after_events[len(before_events):]
        check('Only due industry close posted once; future research/mining not booked',lambda:require(len([x for x in new if x.get('source_task_id')=='TSK-CALDER-INDUSTRIES-302' and x.get('type')=='economic_settlement'])==1 and not [x for x in new if x.get('source_task_id') in ('TSK-MIN-OPERATIONS','TSK-MKT-RESEARCH-DATA-SALES') and x.get('type')=='economic_settlement']))
    result={'status':'PASS' if all(x['status']=='PASS' for x in checks) else 'FAIL','passed':sum(x['status']=='PASS' for x in checks),'total':len(checks),'checks':checks,'production_time':state['game_time'],'isolated_fixture_results_do_not_change_save':True}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
