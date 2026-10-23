# === VOYAGER_DEV_MODULE: business_settlement ===
BUSINESS_RULE_SCHEMA='BUSINESS_DAILY_RULE_V1'
BUSINESS_RUNTIME_SCHEMA='BUSINESS_RUNTIME_V1'


def _business_rule(task):
    rule=(task.get('runtime_policy') or {}).get('business_rule')
    if not isinstance(rule,dict) or rule.get('schema')!=BUSINESS_RULE_SCHEMA:raise EngineError('BUSINESS_RULE_REQUIRED')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',str(rule.get('business_id') or '')):raise EngineError('BUSINESS_ID_INVALID')
    if rule.get('currency')!='copper' or rule.get('repeat_seconds')!=86400:raise EngineError('BUSINESS_PERIOD_OR_CURRENCY_UNSUPPORTED')
    if not isinstance(rule.get('fixed_costs'),dict) or any(type(v) is not int or v<0 for v in rule['fixed_costs'].values()):raise EngineError('BUSINESS_FIXED_COST_INVALID')
    if not rule.get('authorization_basis') or not rule.get('effective_from'):raise EngineError('BUSINESS_AUTHORIZATION_AND_EPOCH_REQUIRED')
    return rule


def _business_runtime(state,bid):
    rt=state.get('engine_runtime',{}).get('business_runtime_v1')
    if not isinstance(rt,dict) or rt.get('schema')!=BUSINESS_RUNTIME_SCHEMA:raise EngineError('BUSINESS_MIGRATION_REQUIRED')
    row=rt.get('businesses',{}).get(bid)
    if not isinstance(row,dict):raise EngineError('BUSINESS_NOT_REGISTERED')
    return row


def _business_day_key(iso):
    when=parse_iso(iso)
    if when is None or when.isoformat()!=iso:raise EngineError('BUSINESS_CANONICAL_TIME_REQUIRED')
    return iso


def _business_integer(value,name):
    if type(value) is not int or value<0:raise EngineError('BUSINESS_NONNEGATIVE_INTEGER:'+name)
    return value


def _business_v1_validate_day(record):
    required={'scheduled_at','record_kind','source_refs','cash_receipts_copper','cash_purchases_copper','other_cash_expenses_copper','gross_sales_copper','cogs_copper','inventory'}
    if not isinstance(record,dict) or set(record)!=required:raise EngineError('BUSINESS_DAY_SCHEMA')
    _business_day_key(record['scheduled_at'])
    if record['record_kind'] not in ('actual','commander_accepted_simulation'):raise EngineError('BUSINESS_FORECAST_IS_NOT_ACTUAL')
    if not isinstance(record['source_refs'],list) or not 1<=len(record['source_refs'])<=40 or any(not isinstance(x,str) or not x.strip() or len(x)>500 for x in record['source_refs']):raise EngineError('BUSINESS_SOURCE_REQUIRED')
    for field in required-{'scheduled_at','record_kind','source_refs','inventory'}:_business_integer(record[field],field)
    inv=record['inventory']
    if not isinstance(inv,dict) or set(inv)!={'status','opening_basis','opening','purchases','sold','waste','closing'} or inv['status']!='confirmed' or inv['opening_basis'] not in ('stocktake','previous_close'):raise EngineError('BUSINESS_INVENTORY_UNCONFIRMED')
    for field in ('opening','purchases','sold','waste','closing'):
        if not isinstance(inv[field],dict) or len(inv[field])>2000:raise EngineError('BUSINESS_INVENTORY_SCHEMA')
        for sku,n in inv[field].items():
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',str(sku)) or type(n) is not int or n<0:raise EngineError('BUSINESS_SKU_QUANTITY_INVALID')
    keys=set().union(*(set(inv[k]) for k in ('opening','purchases','sold','waste','closing')))
    for sku in keys:
        expected=inv['opening'].get(sku,0)+inv['purchases'].get(sku,0)-inv['sold'].get(sku,0)-inv['waste'].get(sku,0)
        if expected<0 or inv['closing'].get(sku,0)!=expected:raise EngineError('BUSINESS_INVENTORY_EQUATION:'+sku)
    return record


def _business_prepaid_expense(state,rule,iso):
    total=0;covered=[]
    for path in rule.get('prepaid_contract_refs',[]):
        contract=get_by_path(state,path);day=iso[:10]
        lo=contract.get('from');hi=contract.get('through')
        if not isinstance(lo,str) or not isinstance(hi,str) or parse_iso(lo+'T00:00:00') is None or parse_iso(hi+'T00:00:00') is None:raise EngineError('BUSINESS_PREPAID_CONTRACT_INVALID')
        if lo<=day<=hi:
            daily=sum(_business_integer(contract.get(k),k) for k in ('daily_salary_copper','daily_meals_copper'))
            days=(parse_iso(hi+'T00:00:00')-parse_iso(lo+'T00:00:00')).days+1
            if contract.get('days')!=days or contract.get('total_paid_copper')!=daily*days or sum(contract.get(k,0) for k in ('salary_prepaid_copper','meals_prepaid_copper'))!=daily*days:raise EngineError('BUSINESS_PREPAID_PAYMENT_UNVERIFIED')
            total+=daily;covered.append({'contract_ref':'state:'+path,'expense_copper':daily,'additional_cash_payment_copper':0})
    return total,covered


def _business_v1_assessment(state,task,iso):
    try:
        rule=_business_rule(task);row=_business_runtime(state,rule['business_id']);_account_units(state,rule['account_id'],'copper')
        if iso<rule['effective_from']:raise EngineError('BUSINESS_NO_HISTORICAL_REPLAY')
        saved=row['inputs'].get(iso)
        if not saved:return {'status':'NEEDS_EVIDENCE','missing':['confirmed_day_record','current_SKU_stocktake'],'scheduled_at':iso}
        record=_business_validate_day(saved['record'])
        if saved.get('record_sha256')!=_repair_digest(record) or saved.get('rule_sha256')!=_repair_digest(rule) or not saved.get('authorization_evidence') or not saved.get('command_id'):raise EngineError('BUSINESS_INPUT_BINDING_INVALID')
        if record['scheduled_at']!=iso:raise EngineError('BUSINESS_INPUT_PERIOD_MISMATCH')
        inv=record['inventory']
        if row.get('inventory_status')=='confirmed':
            if row.get('inventory')!=inv['opening']:raise EngineError('BUSINESS_OPENING_STOCK_MISMATCH')
        elif inv['opening_basis']!='stocktake':raise EngineError('BUSINESS_FIRST_STOCKTAKE_REQUIRED')
        expense=sum(rule['fixed_costs'].values());prepaid,contracts=_business_prepaid_expense(state,rule,iso)
        debit=record['cash_purchases_copper']+record['other_cash_expenses_copper']+expense
        delta=record['cash_receipts_copper']-debit
        available=_account_units(state,rule['account_id'],'copper')-_account_reserved(state,rule['account_id'],'copper')
        if available+delta<0:return {'status':'INSUFFICIENT_FUNDS','missing':['cash_shortfall'],'shortfall_copper':-(available+delta),'scheduled_at':iso}
        return {'status':'READY','scheduled_at':iso,'cash_delta_copper':delta,'cash_debits_copper':debit,'fixed_costs_copper':expense,'prepaid_expense_copper':prepaid,'prepaid_contracts':contracts,'profit_copper':record['gross_sales_copper']-record['cogs_copper']-record['other_cash_expenses_copper']-expense-prepaid,'record_sha256':saved['record_sha256'],'rule_sha256':saved['rule_sha256']}
    except Exception as ex:return {'status':'INVALID','missing':[str(ex)],'scheduled_at':iso}


def _business_day_record(state,tasks,payload):
    task=_task_by_id(tasks,payload['task_id']);rule=_business_rule(task);row=_business_runtime(state,rule['business_id'])
    if payload['account_id']!=rule['account_id']:raise EngineError('BUSINESS_ACCOUNT_TARGET_MISMATCH')
    # Only a real gateway/embedding host may confirm previously unknown actuals.
    env=_host_intent_scope.get()
    if payload.get('authorization')!='host_intent' or not isinstance(env,dict) or env.get('command')!=payload or env.get('decision')!='approved' or not env.get('evidence_ref'):raise EngineError('BUSINESS_ACTUALS_REQUIRE_TRUSTED_HOST_CONFIRMATION')
    record=copy.deepcopy(_business_validate_day(payload['day_record']));iso=record['scheduled_at'];now=state['game_time'];mon=_task_monitor(tasks,task)
    if iso<rule['effective_from'] or iso!=mon.get('next_review_at'):raise EngineError('BUSINESS_RECORD_NOT_CURRENT_DUE_PERIOD')
    if parse_iso(iso)>parse_iso(now):raise EngineError('BUSINESS_FUTURE_ACTUALS_FORBIDDEN')
    if iso in row['settlements']:raise EngineError('BUSINESS_PERIOD_ALREADY_SETTLED')
    digest=_repair_digest(record);old=row['inputs'].get(iso)
    if old and old['record_sha256']!=digest:raise EngineError('BUSINESS_INPUT_ALREADY_CONFIRMED_USE_EXPLICIT_CORRECTION')
    if old:return {'kind':'business_day_record','task_id':task['task_id'],'assessment':_business_assessment(state,task,iso),'record_sha256':old['record_sha256'],'rule_sha256':old['rule_sha256'],'already_confirmed':True,'cash_changed':False,'changes':[]}
    proof={'kind':'host_confirmed_record','evidence_ref':env['evidence_ref'],'intent_sha256':_repair_digest(env),'record_kind':record['record_kind']}
    row['inputs'][iso]={'record':record,'record_sha256':digest,'rule_sha256':_repair_digest(rule),'authorization_evidence':proof,'command_id':payload['command_id'],'recorded_at':now}
    assessment=_business_assessment(state,task,iso)
    if assessment['status']=='INVALID':raise EngineError('BUSINESS_INPUT_INVALID:'+str(assessment['missing']))
    required_debit=record['cash_purchases_copper']+record['other_cash_expenses_copper']+sum(rule['fixed_costs'].values())
    if _business_integer(payload.get('cash_debit_limit_copper'),'cash_debit_limit_copper')<required_debit:raise EngineError('BUSINESS_CASH_DEBIT_LIMIT_INSUFFICIENT')
    return {'kind':'business_day_record','task_id':task['task_id'],'assessment':assessment,'record_sha256':digest,'rule_sha256':_repair_digest(rule),'cash_changed':False,'changes':[{'target':'state:engine_runtime.business_runtime_v1.businesses.'+rule['business_id']+'.inputs','action':'record_host_confirmed_business_evidence'}]}


def _business_v1_resolver_daily(stage,state,tasks,task,when):
    iso=when.isoformat();rule=_business_rule(task);row=_business_runtime(state,rule['business_id']);prior=row['settlements'].get(iso)
    if prior:
        if prior['rule_sha256']!=_repair_digest(rule) or row['inputs'].get(iso,{}).get('record_sha256')!=prior['record_sha256']:raise EngineError('BUSINESS_SETTLED_INPUT_CONFLICT')
        return {**copy.deepcopy(prior),'status':'ALREADY_APPLIED'}
    if state['game_time']!=iso or _task_monitor(tasks,task).get('next_review_at')!=iso:raise EngineError('BUSINESS_SETTLEMENT_TIME_MISMATCH')
    check=_business_assessment(state,task,iso)
    if check['status']!='READY':return {'status':'AI_REQUIRED','task_id':task['task_id'],'semantic_barrier':{'kind':'business_reconciliation','task_id':task['task_id'],'assessment':check}}
    record=row['inputs'][iso]['record'];aid=rule['account_id'];before=_account_units(state,aid,'copper');key=rule['business_id']+'|'+iso+'|daily_close';eid='BUSINESS-'+sha256_bytes(key.encode())[:24]
    token=_account_command_scope.set(eid)
    try:cash=_account_post(state,aid,'copper',check['cash_delta_copper'])
    finally:_account_command_scope.reset(token)
    nxt=_roll_daily(when)
    receipt={**check,'status':'COMPLETE','business_key':key,'event_id':eid,'task_id':task['task_id'],'business_id':rule['business_id'],'account_id':aid,'period_start':(when-dt.timedelta(days=1)).isoformat(),'scheduled_at':iso,'next_at':nxt,'input_command_id':row['inputs'][iso]['command_id'],'source_refs':record['source_refs'],'record_kind':record['record_kind'],'inventory_status':record['inventory']['status'],'cash_before_copper':before,'cash_after_copper':_account_units(state,aid,'copper'),'cash_entry_id':cash['entry_id'],'cash_receipts_copper':record['cash_receipts_copper'],'cash_purchases_copper':record['cash_purchases_copper'],'other_cash_expenses_copper':record['other_cash_expenses_copper'],'gross_sales_copper':record['gross_sales_copper'],'cogs_copper':record['cogs_copper'],'fixed_cost_items':copy.deepcopy(rule['fixed_costs'])}
    if record['inventory']['status']=='continuous_simulated':
        receipt.update(authorization_evidence=copy.deepcopy(row['inputs'][iso]['authorization_evidence']),accounting_journal=_business_journal(record,check,row['autonomy_policy']),inventory_movements=copy.deepcopy(record['inventory']),physical_receipts_confirmed=False)
    if record['record_kind']=='actual' and record['inventory']['opening_basis']=='stocktake' and row.get('autonomy_policy'):
        receipt['stocktake_reconciliation']=business_stocktake_comparison(state,task,record)
    row['settlements'][iso]=receipt;row['inventory']=copy.deepcopy(record['inventory']['closing']);row['inventory_status']=record['inventory']['status'];row['last_settled_at']=iso
    td=task['task_data'];td.update(last_payroll_at=iso,next_payroll_at=nxt,next_close_at=nxt,last_full_shop_day=iso[:10],as_of=iso,latest_shop_balance_copper=receipt['cash_after_copper'],latest_cash_copper=receipt['cash_after_copper'],cash_silver=receipt['cash_after_copper']/100)
    mon=task['runtime_policy']['monitor'];mon.update(last_reviewed_at=iso,next_review_at=nxt)
    cover=get_by_path(state,'world_state_overrides.freeport_xilu9_current.hawke_commercial_cover') if rule['business_id']=='YUHUO' else None
    mirror_changes=[]
    if cover is not None:
        for key in ('next_payroll_at','next_full_shop_close_at'):
            cover['simulation_current'][key]=nxt
            mirror_changes.append({'target':'state:world_state_overrides.freeport_xilu9_current.hawke_commercial_cover.simulation_current.'+key,'action':'derive_verified_business_next_node'})
        cover['shop_cash_continuation_83631205']['next_close_at']=nxt
        mirror_changes.append({'target':'state:world_state_overrides.freeport_xilu9_current.hawke_commercial_cover.shop_cash_continuation_83631205.next_close_at','action':'derive_verified_business_next_node'})
    changes=[{'target':'state:engine_runtime.business_runtime_v1.businesses.'+rule['business_id'],'action':'settle_verified_day_and_roll_inventory'},{'target':'state:engine_runtime.account_registry_v1','action':'post_independent_cash_once'},{'target':'tasks:active_tasks','action':'roll_business_daily_monitor'}]+[{'target':'state:'+v['path'],'action':'derive_account_view'} for v in _account_record(state,aid).get('legacy_read_only_views',[])]
    _append_engine_history(stage/'events.jsonl',{'event_id':eid,'game_time':iso,'type':'business_daily_settlement','summary':'独立店铺依据可审计经营输入完成日结，保留真实或模拟证据类别；成本与现金分列，预付合同不重复付款。','source':'GAME ENGINE business_daily_settlement_v1','source_task_id':task['task_id'],'authority_files':['state.json','tasks.json'],'changes':changes+mirror_changes,'business_settlement':receipt,'finance_independent':{'account_id':aid,'currency':'copper','delta_units':check['cash_delta_copper'],'cash_entry_id':cash['entry_id']}})
    # Session execution diagnostics are added to its returned row, never to authority.
    return copy.deepcopy(receipt)


def _task_execution_coverage(state,tasks,task,now,horizon):
    mon=_task_monitor(tasks,task);mode=mon.get('mode');resolver=str(mon.get('resolver') or '');nr=parse_iso(mon.get('next_review_at')) if mon.get('next_review_at') else None
    if mode!='scheduled':return None
    due=max(now,nr) if nr else now
    if due>horizon:return None
    if mon.get('requires_ai_review') is True:return None
    problem=None;assessment=None
    if nr is None:problem='SCHEDULED_DEADLINE_MISSING'
    elif not callable(RESOLVER_FUNCTIONS.get(resolver)):problem='SCHEDULED_RESOLVER_UNAVAILABLE'
    elif resolver=='business_daily_settlement_v1':
        assessment=_business_assessment(state,task,nr.isoformat()) if isinstance(state,dict) else {'status':'NEEDS_STATE'}
        if assessment['status']!='READY':problem='BUSINESS_'+assessment['status']
    if not problem:return None
    return {'time':due,'scheduled_time':nr.isoformat() if nr else None,'task_id':task.get('task_id'),'title':task.get('title'),'kind':'business_reconciliation' if resolver=='business_daily_settlement_v1' else 'task_execution_uncovered','reason':problem,'assessment':assessment,'resolution_required':'Use the trusted typed business_day_record input for confirmed current records, or repair the declared resolver. Unknown income/inventory is never zero; no historical replay.'}


def _scheduler_coverage(state,tasks,save_set_id=None):
    now=parse_iso(state['game_time']);end=now+dt.timedelta(days=1)
    rows=[]
    for task in tasks.get('active_tasks',[]):
        mon=_task_monitor(tasks,task);issue=_task_execution_coverage(state,tasks,task,now,end)
        rows.append({'task_id':task['task_id'],'mode':mon.get('mode'),'resolver':mon.get('resolver'),'callable_resolver':callable(RESOLVER_FUNCTIONS.get(str(mon.get('resolver') or ''))),'next_at':mon.get('next_review_at'),'execution_status':'ACTION_REQUIRED' if issue else ('AI_MANAGED' if mon.get('requires_ai_review') else 'EXECUTABLE' if callable(RESOLVER_FUNCTIONS.get(str(mon.get('resolver') or ''))) else 'EVENT_WATCHER'),'issue':{**issue,'time':issue['time'].isoformat()} if issue else None})
    issues=[r['issue'] for r in rows if r['issue']]
    return {'packet':'SCHEDULER_COVERAGE_V1','status':'ACTION_REQUIRED' if issues else 'COVERED','game_time':state['game_time'],'save_set_id':save_set_id,'can_advance_through_24h':not issues,'next_blocker':min(issues,key=lambda x:(x['time'],x['task_id'])) if issues else None,'tasks':rows}


def scheduler_coverage_packet(base=ROOT):
    with SnapshotContext(base):
        ensure_source_ready(base)
        return _scheduler_coverage(read_json_view(Path(base)/'state.json'),read_json_view(Path(base)/'tasks.json'),read_json_view(Path(base)/'manifest.json')['save_set_id'])


def business_query_packet(base=ROOT,task_id='TSK-YUHUO-OPERATIONS'):
    with SnapshotContext(base):
        ensure_source_ready(base);state=read_json_view(Path(base)/'state.json');tasks=read_json_view(Path(base)/'tasks.json');task=_task_by_id(tasks,task_id);rule=_business_rule(task);row=_business_runtime(state,rule['business_id']);iso=_task_monitor(tasks,task).get('next_review_at')
        return {'packet':'BUSINESS_QUERY_V1','save_set_id':read_json_view(Path(base)/'manifest.json')['save_set_id'],'game_time':state['game_time'],'task_id':task_id,'business_id':rule['business_id'],'cash_copper':_account_units(state,rule['account_id'],'copper'),'next_at':iso,'assessment':_business_assessment(state,task,iso),'last_settled_at':row.get('last_settled_at'),'latest_receipt':row['settlements'].get(row.get('last_settled_at')),'inventory_status':row['inventory_status'],'fixed_costs':rule['fixed_costs'],'prepaid_at_next_close':_business_prepaid_expense(state,rule,iso),'historical_gaps':row.get('historical_gaps',[]),'balance_evidence':_business_balance_evidence(state,rule['account_id']),'input_entry':'standing authorized simulation is registered automatically only when due; actual business_day_record still requires the existing trusted host gateway'}


def _business_v1_integrity_report(state,tasks,base=None):
    rt=state.get('engine_runtime',{}).get('business_runtime_v1')
    if rt is None:
        errors=['BUSINESS_MIGRATION_REQUIRED'] if any(_task_monitor(tasks,t).get('resolver')=='business_daily_settlement_v1' for t in tasks.get('active_tasks',[])) else []
        return {'status':'FAIL' if errors else 'LEGACY','errors':errors}
    errors=[]
    try:
        if rt.get('schema')!=BUSINESS_RUNTIME_SCHEMA:raise EngineError('BUSINESS_RUNTIME_SCHEMA')
        for bid,row in rt['businesses'].items():
            task=_task_by_id(tasks,row['task_id']);rule=_business_rule(task)
            if rule['business_id']!=bid or row['inventory_status'] not in ('unknown','confirmed'):raise EngineError('BUSINESS_ID_OR_STOCK_STATUS')
            for iso,saved in row['inputs'].items():
                record=_business_validate_day(saved['record'])
                if iso!=record['scheduled_at'] or iso<rule['effective_from'] or saved['record_sha256']!=_repair_digest(record) or not saved.get('authorization_evidence'):raise EngineError('BUSINESS_INPUT_CONTRACT')
                if base is not None:
                    ev=history_lookup(base,command_id=saved['command_id'])
                    if not ev or ev.get('domain_kind')!='business_day_record' or ev.get('authorization',{}).get('evidence_ref')!=saved['authorization_evidence'].get('evidence_ref') or ev.get('domain_effect',{}).get('record_sha256')!=saved['record_sha256'] or ev.get('domain_effect',{}).get('rule_sha256')!=saved['rule_sha256']:raise EngineError('BUSINESS_INPUT_HISTORY_MISSING')
            for iso,rec in row['settlements'].items():
                saved=row['inputs'].get(iso)
                if not saved or rec['record_sha256']!=saved['record_sha256'] or rec['cash_after_copper']-rec['cash_before_copper']!=rec['cash_delta_copper']:raise EngineError('BUSINESS_SETTLEMENT_BINDING')
                matches=[x for x in _account_registry(state)['ledger'] if x['entry_id']==rec['cash_entry_id']]
                if len(matches)!=1 or matches[0]['delta_units']!=rec['cash_delta_copper']:raise EngineError('BUSINESS_CASH_RECEIPT_MISSING')
                if base is not None:
                    ev=history_lookup(base,event_id=rec['event_id'])
                    if not ev or ev.get('business_settlement')!=rec:raise EngineError('BUSINESS_EVENT_RECEIPT_MISSING')
    except Exception as ex:errors.append(str(ex))
    return {'status':'FAIL' if errors else 'PASS','errors':errors}


def _business_v1_settlement_proofs(base,parent,old_state,new_state,new_events):
    """Recompute each new close against its confirmed parent input; exact coverage only."""
    old_rows=old_state.get('engine_runtime',{}).get('business_runtime_v1',{}).get('businesses',{})
    new_rows=new_state.get('engine_runtime',{}).get('business_runtime_v1',{}).get('businesses',{})
    tasks=read_json(Path(parent)/'tasks.json');proofs={};covered=set()
    for bid,row in new_rows.items():
        previous=old_rows.get(bid,{});old_closes=previous.get('settlements',{})
        for iso,receipt in old_closes.items():
            if row['settlements'].get(iso)!=receipt:raise EngineError('BUSINESS_OLD_RECEIPT_IMMUTABLE')
        fresh=[(iso,r) for iso,r in row['settlements'].items() if iso not in old_closes]
        if not fresh:continue
        task=_task_by_id(tasks,row['task_id']);rule=_business_rule(task)
        working=copy.deepcopy(old_state)
        for iso,rec in sorted(fresh):
            matches=[ev for ev in new_events if ev.get('event_id')==rec.get('event_id') and ev.get('type')=='business_daily_settlement']
            if len(matches)!=1 or matches[0].get('business_settlement')!=rec:raise EngineError('BUSINESS_EVENT_RECEIPT_MISMATCH')
            check=_business_assessment(working,task,iso)
            if check['status']!='READY' or rec.get('status')!='COMPLETE':raise EngineError('BUSINESS_RECEIPT_NO_VALID_PARENT_INPUT')
            for key,value in check.items():
                if key!='status' and rec.get(key)!=value:raise EngineError('BUSINESS_RECEIPT_RECOMPUTE_MISMATCH:'+key)
            if rec.get('business_id')!=bid or rec.get('task_id')!=task['task_id'] or rec.get('account_id')!=rule['account_id']:raise EngineError('BUSINESS_RECEIPT_SUBJECT_MISMATCH')
            before=_account_units(working,rule['account_id'],'copper')
            if rec.get('cash_before_copper')!=before or rec.get('cash_after_copper')!=before+check['cash_delta_copper']:raise EngineError('BUSINESS_RECEIPT_CASH_MISMATCH')
            record=_business_runtime(working,bid)['inputs'][iso]['record']
            if row['inputs'].get(iso)!=_business_runtime(working,bid)['inputs'][iso]:raise EngineError('BUSINESS_CONFIRMED_INPUT_IMMUTABLE')
            if rec.get('fixed_cost_items')!=rule['fixed_costs'] or any(rec.get(k)!=record[k] for k in ('cash_receipts_copper','cash_purchases_copper','other_cash_expenses_copper','gross_sales_copper','cogs_copper','record_kind','source_refs')):raise EngineError('BUSINESS_RECEIPT_INPUT_AMOUNTS')
            cash=[x for x in _account_registry(new_state)['ledger'] if x['entry_id']==rec.get('cash_entry_id')]
            if len(cash)!=1 or cash[0]['command_id']!=rec['event_id'] or cash[0]['account_id']!=rule['account_id'] or cash[0]['currency']!='copper' or cash[0]['delta_units']!=check['cash_delta_copper']:raise EngineError('BUSINESS_CASH_SOURCE_MISMATCH')
            proofs[cash[0]['entry_id']]=cash[0]
            prefix='state:engine_runtime.business_runtime_v1.businesses.'+bid+'.settlements.'+iso
            # Accept exactly the recomputed fixed-cost outputs, not arbitrary new prices.
            covered.add(prefix+'.fixed_costs_copper')
            covered.update(prefix+'.fixed_cost_items.'+k for k in rule['fixed_costs'])
            _account_post(working,rule['account_id'],'copper',check['cash_delta_copper'])
            current=_business_runtime(working,bid);current['inventory']=copy.deepcopy(record['inventory']['closing']);current['inventory_status']='confirmed'
    return proofs,covered


RESOLVER_FUNCTIONS['business_daily_settlement_v1']=_business_v1_resolver_daily
DETERMINISTIC_RESOLVERS.add('business_daily_settlement_v1')
TASK_AI_BARRIER_KINDS.update({'business_reconciliation','task_execution_uncovered'})
