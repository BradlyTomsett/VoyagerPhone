# === VOYAGER_DEV_MODULE: autonomous_business ===
# V14.64: simulation is a distinct evidence class. No host-intent context is synthesized.
_BUSINESS_V1_VALIDATE = _business_v1_validate_day
_BUSINESS_V1_ASSESS = _business_v1_assessment
_BUSINESS_V1_RESOLVE = _business_v1_resolver_daily
_BUSINESS_V1_INTEGRITY = _business_v1_integrity_report
_BUSINESS_V1_PROOFS = _business_v1_settlement_proofs
AUTONOMOUS_BUSINESS_SCHEMA = 'AUTONOMOUS_BUSINESS_POLICY_V1'


def _business_validate_day(record):
    if not isinstance(record, dict) or record.get('inventory', {}).get('status') != 'continuous_simulated':
        if isinstance(record, dict) and record.get('record_kind') == 'commander_accepted_simulation':
            raise EngineError('BUSINESS_SIMULATION_CANNOT_CLAIM_PHYSICAL_STOCKTAKE')
        return _BUSINESS_V1_VALIDATE(record)
    if record.get('record_kind') != 'commander_accepted_simulation':
        raise EngineError('BUSINESS_SIMULATED_INVENTORY_EVIDENCE_CLASS')
    inv = record['inventory']
    if inv.get('opening_basis') not in ('authorized_simulation_anchor', 'previous_simulated_close', 'previous_confirmed_close'):
        raise EngineError('BUSINESS_SIMULATION_OPENING_BASIS')
    shadow = copy.deepcopy(record)
    shadow['inventory']['status'] = 'confirmed'
    shadow['inventory']['opening_basis'] = 'previous_close'
    _BUSINESS_V1_VALIDATE(shadow)
    return record


def _business_policy(state, task, iso, enforce_operating=True):
    rule = _business_rule(task); row = _business_runtime(state, rule['business_id'])
    policy = row.get('autonomy_policy')
    if not isinstance(policy, dict) or policy.get('schema') != AUTONOMOUS_BUSINESS_SCHEMA:
        raise EngineError('BUSINESS_AUTONOMY_NOT_GRANTED')
    if row.get('autonomy_policy_sha256') != _repair_digest(policy):
        raise EngineError('BUSINESS_AUTONOMY_POLICY_DIGEST')
    if policy.get('status') not in ('active','paused','revoked'):raise EngineError('BUSINESS_POLICY_STATUS')
    if enforce_operating and (policy.get('status') != 'active' or not policy['effective_from'] <= iso or (policy.get('expires_at') and iso > policy['expires_at'])):
        raise EngineError('BUSINESS_AUTONOMY_INACTIVE')
    if (policy['business_id'], policy['task_id'], policy['account_id']) != (rule['business_id'], task['task_id'], rule['account_id']):
        raise EngineError('BUSINESS_AUTONOMY_SUBJECT')
    if policy['rule_sha256'] != _repair_digest(rule):raise EngineError('BUSINESS_AUTONOMY_RULE_CHANGED')
    if policy.get('evidence_class') != 'commander_accepted_simulation' or policy.get('authority') != 'explicit_commander_upgrade_instruction':
        raise EngineError('BUSINESS_AUTONOMY_AUTHORITY')
    if not policy.get('source_ref') or not policy.get('grant_event_id') or policy.get('allow_cross_account_transfer') is not False:
        raise EngineError('BUSINESS_AUTONOMY_SCOPE')
    if enforce_operating and row.get('risk_flags'):raise EngineError('BUSINESS_MAJOR_RISK_REQUIRES_COMMANDER:'+','.join(row['risk_flags']))
    for k in ('daily_revenue_limit_copper','daily_purchase_limit_copper','daily_cash_debit_limit_copper','minimum_cash_reserve_copper','daily_units_limit'):
        _business_integer(policy[k], k)
    model = policy['model']
    if not isinstance(model, dict) or not model or len(model) > 2000:raise EngineError('BUSINESS_AUTONOMY_MODEL')
    for sku, m in model.items():
        if not re.fullmatch('[A-Za-z0-9_-]{1,100}', sku):raise EngineError('BUSINESS_AUTONOMY_SKU')
        for k in ('unit_cost_copper','unit_price_copper','base_daily_demand','reorder_threshold','target_stock','purchase_batch'):
            _business_integer(m[k],sku+'.'+k)
        if m['unit_price_copper'] < m['unit_cost_copper'] or m['target_stock'] < m['reorder_threshold']:
            raise EngineError('BUSINESS_AUTONOMY_MODEL_BOUNDS')
    return policy


def _business_autonomous_input(state, task, iso):
    """Pure generation: planning never posts income or purchases, including future previews."""
    rule = _business_rule(task); row = _business_runtime(state,rule['business_id']); p = _business_policy(state,task,iso)
    if iso < rule['effective_from']:raise EngineError('BUSINESS_NO_HISTORICAL_REPLAY')
    last = row.get('last_settled_at')
    expected = _roll_daily(parse_iso(last)) if last else p['effective_from']
    if iso != expected:raise EngineError('BUSINESS_SIMULATION_PERIOD_NOT_CONTIGUOUS')
    opening = copy.deepcopy(row['inventory'] if last else p['opening_simulated_inventory'])
    if set(opening) != set(p['model']):raise EngineError('BUSINESS_SIMULATION_SKU_COVERAGE')
    inv = {'status':'continuous_simulated','opening_basis':('previous_confirmed_close' if row.get('inventory_status')=='confirmed' else 'previous_simulated_close') if last else 'authorized_simulation_anchor',
           'opening':opening,'purchases':{},'sold':{},'waste':{},'closing':{}}
    if iso == p['effective_from'] and not last:
        record = copy.deepcopy(p['initial_day_record'])
        if record['inventory']['opening'] != opening:raise EngineError('BUSINESS_ANCHOR_INVENTORY_MISMATCH')
    else:
        # ±10% demand around the already +25% reference; no compounded population/growth multiplier.
        demand_pct = _deterministic_range('BUSINESS_DEMAND_V1|'+rule['business_id']+'|'+iso,90,110)
        sales = cogs = purchases = 0
        cash_budget=max(0,_account_units(state,rule['account_id'],'copper')-_account_reserved(state,rule['account_id'],'copper')-p['minimum_cash_reserve_copper']-sum(rule['fixed_costs'].values())-p['other_daily_cash_expenses_copper'])
        purchase_budget=min(p['daily_purchase_limit_copper'],p['daily_cash_debit_limit_copper']-sum(rule['fixed_costs'].values())-p['other_daily_cash_expenses_copper'],cash_budget)
        for sku, m in p['model'].items():
            qty = (m['base_daily_demand']*demand_pct+50)//100
            buy = 0
            if m['purchase_batch'] and opening[sku]-qty <= m['reorder_threshold']:
                need = max(0,m['target_stock']-opening[sku])
                buy = ((need+m['purchase_batch']-1)//m['purchase_batch'])*m['purchase_batch']
            if buy and m['unit_cost_copper']:
                affordable=max(0,purchase_budget-purchases)//m['unit_cost_copper']
                buy=min(buy,(affordable//m['purchase_batch'])*m['purchase_batch'])
            if buy and m.get('supply_status') != 'modeled_available':raise EngineError('BUSINESS_SUPPLY_REQUIRES_REVIEW:'+sku)
            qty = min(qty,opening[sku]+buy)
            # Deterministic small food spoilage is explicit, valued separately from sales COGS.
            waste = min(max(0,opening[sku]+buy-qty), _deterministic_range('BUSINESS_WASTE_V1|'+iso+'|'+sku,0,1)) if m.get('perishable') else 0
            inv['purchases'][sku]=buy;inv['sold'][sku]=qty;inv['waste'][sku]=waste
            inv['closing'][sku]=opening[sku]+buy-qty-waste
            sales+=qty*m['unit_price_copper'];cogs+=qty*m['unit_cost_copper'];purchases+=buy*m['unit_cost_copper']
        record={'scheduled_at':iso,'record_kind':'commander_accepted_simulation',
                'source_refs':[p['source_ref'],'policy:'+p['policy_id'],'model:bounded_demand_v1','previous_simulated_close:'+last],
                'cash_receipts_copper':sales,'cash_purchases_copper':purchases,'other_cash_expenses_copper':p['other_daily_cash_expenses_copper'],
                'gross_sales_copper':sales,'cogs_copper':cogs,'inventory':inv}
    _business_validate_day(record)
    _business_model_check(record,p)
    return {'record':record,'record_sha256':_repair_digest(record),'rule_sha256':_repair_digest(rule),
            'authorization_evidence':{'kind':'standing_simulation_policy','policy_id':p['policy_id'],'policy_sha256':_repair_digest(p),
                'grant_event_id':p['grant_event_id'],'source_ref':p['source_ref'],'record_kind':'commander_accepted_simulation',
                'physical_receipts_confirmed':False,'inventory_physical_stocktake':False},
            'command_id':'SIMINPUT-'+_repair_digest([rule['business_id'],iso])[:24],'recorded_at':iso}


def _business_model_check(record, p):
    inv=record['inventory'];model=p['model']
    if any(set(inv[k]) != set(model) for k in ('opening','purchases','sold','waste','closing')):raise EngineError('BUSINESS_MODEL_SKU_COVERAGE')
    totals={field:sum(inv[k][sku]*m[cost] for sku,m in model.items()) for field,k,cost in (
        ('gross_sales_copper','sold','unit_price_copper'),('cogs_copper','sold','unit_cost_copper'),('cash_purchases_copper','purchases','unit_cost_copper'))}
    if any(record[k] != v for k,v in totals.items()):raise EngineError('BUSINESS_MODEL_AMOUNT_MISMATCH')
    if record['cash_receipts_copper'] != record['gross_sales_copper']:raise EngineError('BUSINESS_MODEL_RECEIVABLE_NOT_AUTHORIZED')
    if record['gross_sales_copper']>p['daily_revenue_limit_copper'] or record['cash_purchases_copper']>p['daily_purchase_limit_copper'] or sum(inv['sold'].values())>p['daily_units_limit']:
        raise EngineError('BUSINESS_DAILY_SCOPE_EXCEEDED')
    if record['other_cash_expenses_copper'] != p['other_daily_cash_expenses_copper']:raise EngineError('BUSINESS_OTHER_EXPENSE_SCOPE')


def _business_simulation_assessment(state,task,iso,saved):
    rule=_business_rule(task);row=_business_runtime(state,rule['business_id']);p=_business_policy(state,task,iso)
    record=_business_validate_day(saved['record']);inv=record['inventory'];_business_model_check(record,p)
    if record['record_kind']!='commander_accepted_simulation' or inv['status']!='continuous_simulated':raise EngineError('BUSINESS_SIMULATION_CLASS')
    if saved != _business_autonomous_input(state,task,iso):raise EngineError('BUSINESS_SIMULATION_INPUT_NOT_REPRODUCIBLE')
    expected=row['inventory'] if row.get('last_settled_at') else p['opening_simulated_inventory']
    if inv['opening']!=expected:raise EngineError('BUSINESS_OPENING_STOCK_MISMATCH')
    fixed=sum(rule['fixed_costs'].values());prepaid,contracts=_business_prepaid_expense(state,rule,iso)
    debit=record['cash_purchases_copper']+record['other_cash_expenses_copper']+fixed
    if debit>p['daily_cash_debit_limit_copper']:raise EngineError('BUSINESS_DAILY_DEBIT_SCOPE_EXCEEDED')
    delta=record['cash_receipts_copper']-debit
    available=_account_units(state,rule['account_id'],'copper')-_account_reserved(state,rule['account_id'],'copper')
    # Reserve must cover outgoing obligations before assuming today's modeled sales.
    if available<debit+p['minimum_cash_reserve_copper'] or available+delta<p['minimum_cash_reserve_copper']:
        return {'status':'INSUFFICIENT_FUNDS','missing':['cash_reserve'],'scheduled_at':iso,'cash_debits_copper':debit}
    waste=sum(inv['waste'][sku]*m['unit_cost_copper'] for sku,m in p['model'].items())
    return {'status':'READY','scheduled_at':iso,'cash_delta_copper':delta,'cash_debits_copper':debit,'fixed_costs_copper':fixed,
        'prepaid_expense_copper':prepaid,'prepaid_contracts':contracts,'inventory_loss_copper':waste,
        'profit_copper':record['gross_sales_copper']-record['cogs_copper']-record['other_cash_expenses_copper']-fixed-prepaid-waste,
        'record_sha256':saved['record_sha256'],'rule_sha256':saved['rule_sha256']}


def _business_assessment(state,task,iso):
    try:
        rule=_business_rule(task);row=_business_runtime(state,rule['business_id']);saved=row['inputs'].get(iso)
        if not row.get('autonomy_policy') or saved and saved.get('authorization_evidence',{}).get('kind')!='standing_simulation_policy':
            return _BUSINESS_V1_ASSESS(state,task,iso)
        saved=saved or _business_autonomous_input(state,task,iso)
        return _business_simulation_assessment(state,task,iso,saved)
    except Exception as ex:return {'status':'INVALID','missing':[str(ex)],'scheduled_at':iso}


def _business_journal(record,check,policy):
    lines=[]
    def post(debit,credit,amount):
        if type(amount) is not int or amount<0:raise EngineError('BUSINESS_JOURNAL_EXACT_INTEGER')
        if amount:lines.extend([{'account':debit,'debit_copper':amount,'credit_copper':0},{'account':credit,'debit_copper':0,'credit_copper':amount}])
    post('shop_cash','sales_revenue',record['cash_receipts_copper'])
    post('simulated_inventory_asset','shop_cash',record['cash_purchases_copper'])
    post('cost_of_goods_sold','simulated_inventory_asset',record['cogs_copper'])
    post('other_operating_expense','shop_cash',record['other_cash_expenses_copper'])
    rule_costs=policy['fixed_costs']
    for key,amount in rule_costs.items():post(key+'_expense','shop_cash',amount)
    post('inventory_loss_expense','simulated_inventory_asset',check['inventory_loss_copper'])
    # Contract was paid by covert funds historically: allocation is a noncash donated benefit.
    post('prepaid_contract_expense','externally_prepaid_benefit_allocation',check['prepaid_expense_copper'])
    model=policy['model'];inv=record['inventory']
    values={k:sum(inv[k][sku]*m['unit_cost_copper'] for sku,m in model.items()) for k in ('opening','purchases','sold','waste','closing')}
    if values['opening']+values['purchases']-values['sold']-values['waste']!=values['closing']:raise EngineError('BUSINESS_INVENTORY_VALUE_EQUATION')
    if sum(x['debit_copper']-x['credit_copper'] for x in lines)!=0:raise EngineError('BUSINESS_JOURNAL_UNBALANCED')
    return {'schema':'BUSINESS_JOURNAL_V1','currency':'copper','evidence_class':'commander_accepted_simulation',
        'physical_receipts_confirmed':False,'lines':lines,'inventory_values_copper':values,
        'cash_delta_copper':check['cash_delta_copper'],'profit_copper':check['profit_copper'],
        'procurement_expensed_twice':False,'prepaid_cash_paid_today_copper':0,'cross_account_cash_transfer_copper':0}


def _business_autonomous_resolve(stage,state,tasks,task,when):
    rule=_business_rule(task);row=_business_runtime(state,rule['business_id']);iso=when.isoformat()
    if not row.get('autonomy_policy'):return _BUSINESS_V1_RESOLVE(stage,state,tasks,task,when)
    prior=row['settlements'].get(iso)
    if prior:
        saved=row['inputs'].get(iso)
        if not saved or saved['record_sha256']!=prior['record_sha256'] or prior['rule_sha256']!=_repair_digest(rule):raise EngineError('BUSINESS_SETTLED_INPUT_CONFLICT')
        return {**copy.deepcopy(prior),'status':'ALREADY_APPLIED'}
    if state['game_time']!=iso or _task_monitor(tasks,task).get('next_review_at')!=iso:raise EngineError('BUSINESS_SETTLEMENT_TIME_MISMATCH')
    check=_business_assessment(state,task,iso)
    if check['status']!='READY':return {'status':'AI_REQUIRED','task_id':task['task_id'],'semantic_barrier':{'kind':'business_reconciliation','assessment':check}}
    saved=row['inputs'].get(iso)
    if saved and saved['authorization_evidence']['kind']!='standing_simulation_policy':return _BUSINESS_V1_RESOLVE(stage,state,tasks,task,when)
    saved=saved or _business_autonomous_input(state,task,iso)
    row['inputs'][iso]=copy.deepcopy(saved)
    _append_engine_history(stage/'events.jsonl',{'event_id':saved['command_id'],'command_id':saved['command_id'],'game_time':iso,
        'type':'system','subtype':'autonomous_simulation_input','summary':'依据长期授权生成正式模拟经营输入；不代表真实POS或实物盘点。',
        'source':'GAME ENGINE standing simulation policy','authority_files':['state.json'],
        'changes':[{'target':'state:engine_runtime.business_runtime_v1','action':'register_simulation_with_provenance'}],
        'simulation_input':copy.deepcopy(saved),'authorization_kind':'standing_simulation_policy'})
    return _BUSINESS_V1_RESOLVE(stage,state,tasks,task,when)


def _resolver_business_daily(stage,state,tasks,task,when):
    before=copy.deepcopy(state);before_tasks=copy.deepcopy(tasks)
    try:
        with _history_append_batch(stage/'events.jsonl'):
            return _business_autonomous_resolve(stage,state,tasks,task,when)
    except BaseException:
        state.clear();state.update(before);tasks.clear();tasks.update(before_tasks);raise


def _business_confirmed_input_history(base,saved):
    ev=history_lookup(base,command_id=saved['command_id'])
    if not ev or ev.get('domain_kind')!='business_day_record' or ev.get('authorization',{}).get('status')!='verified' or ev.get('authorization',{}).get('authority')!='host_intent' or ev.get('authorization',{}).get('evidence_ref')!=saved['authorization_evidence'].get('evidence_ref') or ev.get('domain_effect',{}).get('record_sha256')!=saved['record_sha256'] or ev.get('domain_effect',{}).get('rule_sha256')!=saved['rule_sha256']:
        raise EngineError('BUSINESS_INPUT_HISTORY_MISSING')
    return ev


def business_stocktake_comparison(state,task,record):
    """Compare a trusted actual stocktake with the simulation; old unresolved differences remain open."""
    _business_validate_day(record)
    if record['record_kind']!='actual' or record['inventory']['status']!='confirmed' or record['inventory']['opening_basis']!='stocktake':raise EngineError('BUSINESS_REAL_STOCKTAKE_REQUIRED')
    row=_business_runtime(state,_business_rule(task)['business_id']);opening=record['inventory']['opening'];old=row['inventory']
    return {'schema':'BUSINESS_STOCKTAKE_RECONCILIATION_V1','at':record['scheduled_at'],'previous_inventory_status':row['inventory_status'],
        'previous_book_quantities':copy.deepcopy(old),'confirmed_opening_quantities':copy.deepcopy(opening),
        'difference_quantities':{sku:opening.get(sku,0)-old.get(sku,0) for sku in sorted(set(old)|set(opening))},
        'historical_discrepancies_preserved':True,'cash_adjustment_copper':0,
        'valuation_difference_status':'unvalued_until_explicit_cost_evidence','source_refs':copy.deepcopy(record['source_refs'])}


def _business_policy_source_copy_proof(base,parent,old_state,new_state,new_events):
    """Narrow migration evidence for copied model prices. This never authorizes new market prices."""
    oldrows=old_state.get('engine_runtime',{}).get('business_runtime_v1',{}).get('businesses',{})
    newrows=new_state.get('engine_runtime',{}).get('business_runtime_v1',{}).get('businesses',{})
    covered=set()
    for bid,row in newrows.items():
        if not row.get('autonomy_policy') or oldrows.get(bid,{}).get('autonomy_policy'):continue
        if bid!='YUHUO':raise EngineError('BUSINESS_NEW_MODEL_REQUIRES_EXPLICIT_MIGRATION_SOURCE')
        if old_state['game_time']!=new_state['game_time']:raise EngineError('BUSINESS_GRANT_MUST_BE_ZERO_TIME')
        task=_task_by_id(read_json(Path(parent)/'tasks.json'),row['task_id']);p=_business_policy(new_state,task,old_state['game_time'])
        draft=get_by_path(old_state,'world_state_overrides.freeport_xilu9_current.hawke_commercial_cover.yu_huo_draft_close_83631210')
        grant=[ev for ev in new_events if ev.get('event_id')==p['grant_event_id']]
        if len(grant)!=1 or grant[0].get('authority_kind')!='explicit_commander_upgrade_instruction' or grant[0].get('simulation_policy_sha256')!=_repair_digest(p) or grant[0].get('cash_changed') is not False:raise EngineError('BUSINESS_POLICY_INSTALLATION_PROVENANCE')
        if p['fixed_costs']!=_business_rule(task)['fixed_costs']:raise EngineError('BUSINESS_POLICY_INHERITED_WAGES')
        rec=p['initial_day_record']
        for field in ('gross_sales_copper','cogs_copper','cash_purchases_copper','other_cash_expenses_copper','scheduled_at'):
            if rec[field]!=draft[field]:raise EngineError('BUSINESS_POLICY_DRAFT_SOURCE_MISMATCH')
        if rec['cash_receipts_copper']!=draft['gross_sales_copper']:raise EngineError('BUSINESS_POLICY_SIMULATED_RECEIPTS_SOURCE')
        mapping=['food','repair','trial','candy','water','air','fuel','medical','parts','cable']
        if set(p['model'])!=set(mapping):raise EngineError('BUSINESS_POLICY_INHERITED_MODEL_COVERAGE')
        sold_mapping=['food','repair','trial','water','air','parts','cable']
        for sku,source in zip(sold_mapping,draft['sales_items']):
            model=p['model'][sku]
            if model['unit_cost_copper']*source['sold']!=source['cogs_copper'] or model['unit_price_copper']*source['sold']!=source['sales_copper'] or model['base_daily_demand']!=source['sold']:raise EngineError('BUSINESS_POLICY_PRICE_NOT_SOURCE_COPY:'+sku)
        for sku in ('candy','fuel','medical'):
            if any(p['model'][sku][key]!=0 for key in ('unit_cost_copper','unit_price_copper','base_daily_demand','purchase_batch')):raise EngineError('BUSINESS_UNKNOWN_RESERVE_PRICE_INVENTED')
        for i,sku in enumerate(mapping):
            for field,dfield in (('opening','opening'),('purchases','purchased'),('sold','sold'),('closing','closing')):
                if rec['inventory'][field][sku]!=draft['category_stocktake_simulation'][i][dfield]:raise EngineError('BUSINESS_POLICY_ANCHOR_SOURCE')
        _business_autonomous_input(new_state,task,p['effective_from'])
        prefix='state:engine_runtime.business_runtime_v1.businesses.'+bid+'.autonomy_policy.'
        covered.update(prefix+'model.'+sku+'.'+key for sku in mapping for key in ('unit_cost_copper','unit_price_copper'))
        covered.update(prefix+'fixed_costs.'+key for key in p['fixed_costs'])
    return covered


def _business_settlement_proofs(base,parent,old_state,new_state,new_events):
    """Replay authorized model inputs from parent; verify cash and double-entry journal exactly."""
    old_rows=old_state.get('engine_runtime',{}).get('business_runtime_v1',{}).get('businesses',{})
    new_rows=new_state.get('engine_runtime',{}).get('business_runtime_v1',{}).get('businesses',{})
    if not any(r.get('autonomy_policy') for r in old_rows.values()):
        proofs,covered=_BUSINESS_V1_PROOFS(base,parent,old_state,new_state,new_events)
        covered.update(_business_policy_source_copy_proof(base,parent,old_state,new_state,new_events))
        return proofs,covered
    tasks=read_json(Path(parent)/'tasks.json');proofs={};covered=set()
    for bid,row in new_rows.items():
        previous=old_rows.get(bid,{})
        if not previous.get('autonomy_policy'):
            if row!=previous:raise EngineError('BUSINESS_UNRELATED_ROW_CHANGED')
            continue
        for key in ('autonomy_policy','autonomy_policy_sha256','historical_gaps','historical_inventory_discrepancies','capital_financing_review'):
            if row.get(key)!=previous.get(key):raise EngineError('BUSINESS_POLICY_OR_HISTORY_IMMUTABLE:'+key)
        for iso,saved in previous['inputs'].items():
            if row['inputs'].get(iso)!=saved:raise EngineError('BUSINESS_CONFIRMED_INPUT_IMMUTABLE')
        for iso,rec in previous['settlements'].items():
            if row['settlements'].get(iso)!=rec:raise EngineError('BUSINESS_OLD_RECEIPT_IMMUTABLE')
        fresh=sorted((iso,r) for iso,r in row['settlements'].items() if iso not in previous['settlements'])
        working=copy.deepcopy(old_state);task=_task_by_id(tasks,row['task_id']);wr=_business_runtime(working,bid)
        for iso,rec in fresh:
            parent_saved=previous['inputs'].get(iso)
            actual=bool(parent_saved and parent_saved['record']['record_kind']=='actual')
            saved=copy.deepcopy(parent_saved) if actual else _business_autonomous_input(working,task,iso)
            if actual:_business_confirmed_input_history(parent,saved)
            if row['inputs'].get(iso)!=saved:raise EngineError('BUSINESS_RECEIPT_NO_VALID_PARENT_INPUT')
            ins=[ev for ev in new_events if ev.get('event_id')==saved['command_id']]
            evs=[ev for ev in new_events if ev.get('event_id')==rec['event_id']]
            if (not actual and (len(ins)!=1 or ins[0].get('simulation_input')!=saved)) or len(evs)!=1 or evs[0].get('business_settlement')!=rec:raise EngineError('BUSINESS_EVENT_RECEIPT_MISMATCH')
            check=_BUSINESS_V1_ASSESS(working,task,iso) if actual else _business_simulation_assessment(working,task,iso,saved)
            if check['status']!='READY' or rec.get('status')!='COMPLETE':raise EngineError('BUSINESS_PARENT_NOT_READY')
            for key,value in check.items():
                if key!='status' and rec.get(key)!=value:raise EngineError('BUSINESS_RECEIPT_RECOMPUTE_MISMATCH:'+key)
            if actual:
                if rec.get('inventory_status')!='confirmed' or rec.get('stocktake_reconciliation')!=business_stocktake_comparison(working,task,saved['record']):raise EngineError('BUSINESS_ACTUAL_STOCKTAKE_RECEIPT')
            elif rec.get('accounting_journal')!=_business_journal(saved['record'],check,wr['autonomy_policy']) or rec.get('inventory_movements')!=saved['record']['inventory'] or rec.get('inventory_status')!='continuous_simulated' or rec.get('physical_receipts_confirmed') is not False:raise EngineError('BUSINESS_JOURNAL_OR_EVIDENCE_MISMATCH')
            rule=_business_rule(task);before=_account_units(working,rule['account_id'],'copper')
            expected_eid='BUSINESS-'+sha256_bytes((bid+'|'+iso+'|daily_close').encode())[:24]
            if rec.get('business_id')!=bid or rec.get('task_id')!=task['task_id'] or rec.get('account_id')!=rule['account_id'] or rec.get('event_id')!=expected_eid or rec.get('cash_before_copper')!=before or rec.get('cash_after_copper')!=before+check['cash_delta_copper']:raise EngineError('BUSINESS_RECEIPT_SUBJECT_OR_CASH')
            for key in ('cash_receipts_copper','cash_purchases_copper','other_cash_expenses_copper','gross_sales_copper','cogs_copper','record_kind','source_refs'):
                if rec.get(key)!=saved['record'][key]:raise EngineError('BUSINESS_RECEIPT_INPUT_AMOUNTS')
            cash=[x for x in _account_registry(new_state)['ledger'] if x['entry_id']==rec['cash_entry_id']]
            if len(cash)!=1 or cash[0]['command_id']!=expected_eid or cash[0]['account_id']!=rule['account_id'] or cash[0]['currency']!='copper' or cash[0]['delta_units']!=check['cash_delta_copper'] or cash[0]['game_time']!=iso:raise EngineError('BUSINESS_CASH_SOURCE_MISMATCH')
            proofs[cash[0]['entry_id']]=cash[0]
            prefix='state:engine_runtime.business_runtime_v1.businesses.'+bid+'.settlements.'+iso
            covered.add(prefix+'.fixed_costs_copper');covered.update(prefix+'.fixed_cost_items.'+k for k in rule['fixed_costs'])
            _account_post(working,rule['account_id'],'copper',check['cash_delta_copper'])
            wr['inventory']=copy.deepcopy(saved['record']['inventory']['closing']);wr['inventory_status']=saved['record']['inventory']['status'];wr['last_settled_at']=iso
        if fresh and (row['inventory']!=wr['inventory'] or row['last_settled_at']!=wr['last_settled_at'] or row['inventory_status']!=wr['inventory_status']):raise EngineError('BUSINESS_FINAL_INVENTORY_MISMATCH')
        for iso in set(row['inputs'])-set(previous['inputs'])-{at for at,_ in fresh}:
            saved=row['inputs'][iso]
            if saved['record']['record_kind']!='actual' or iso!=_task_monitor(read_json(Path(base)/'tasks.json'),_task_by_id(read_json(Path(base)/'tasks.json'),row['task_id'])).get('next_review_at'):raise EngineError('BUSINESS_UNSETTLED_OR_FUTURE_AUTOMATIC_INPUT')
            _business_confirmed_input_history(base,saved)
    return proofs,covered


def business_integrity_report(state,tasks,base=None):
    rows=state.get('engine_runtime',{}).get('business_runtime_v1',{}).get('businesses',{})
    if not any(row.get('autonomy_policy') for row in rows.values()):return _BUSINESS_V1_INTEGRITY(state,tasks,base)
    errors=[]
    try:
        for bid,row in rows.items():
            task=_task_by_id(tasks,row['task_id']);rule=_business_rule(task)
            if not row.get('autonomy_policy'):continue
            p=_business_policy(state,task,rule['effective_from'],enforce_operating=False)
            if base is not None:
                grant=history_lookup(base,event_id=p['grant_event_id'])
                if not grant or grant.get('simulation_policy_sha256')!=_repair_digest(p) or grant.get('authority_kind')!='explicit_commander_upgrade_instruction':raise EngineError('BUSINESS_POLICY_GRANT_HISTORY_MISSING')
            working=copy.deepcopy(state);wr=_business_runtime(working,bid)
            wr['inventory']=copy.deepcopy(p['opening_simulated_inventory']);wr['last_settled_at']=None;wr['inventory_status']='unknown';wr['risk_flags']=[]
            expected_cash=None
            for iso,rec in sorted(row['settlements'].items()):
                _account_record(working,rule['account_id'])['balances']['copper']=rec['cash_before_copper']
                stored=row['inputs'].get(iso);actual=bool(stored and stored['record']['record_kind']=='actual')
                saved=copy.deepcopy(stored) if actual else _business_autonomous_input(working,task,iso)
                if saved!=row['inputs'].get(iso):raise EngineError('BUSINESS_INPUT_NOT_REPRODUCIBLE')
                if expected_cash is not None and rec['cash_before_copper']!=expected_cash:raise EngineError('BUSINESS_CASH_SEQUENCE')
                check_state=copy.deepcopy(working);_account_record(check_state,rule['account_id'])['balances']['copper']=rec['cash_before_copper']
                check=_BUSINESS_V1_ASSESS(check_state,task,iso) if actual else _business_simulation_assessment(check_state,task,iso,saved)
                if check['status']!='READY' or any(rec.get(k)!=v for k,v in check.items() if k!='status'):raise EngineError('BUSINESS_SETTLEMENT_RECOMPUTE')
                if actual:
                    _business_validate_day(saved['record'])
                    if rec.get('inventory_status')!='confirmed' or rec.get('stocktake_reconciliation')!=business_stocktake_comparison(working,task,saved['record']):raise EngineError('BUSINESS_ACTUAL_STOCKTAKE_RECEIPT')
                elif rec.get('accounting_journal')!=_business_journal(saved['record'],check,p) or rec.get('inventory_movements')!=saved['record']['inventory'] or rec.get('inventory_status')!='continuous_simulated' or rec.get('record_kind')!='commander_accepted_simulation' or rec.get('physical_receipts_confirmed') is not False:raise EngineError('BUSINESS_JOURNAL_OR_INVENTORY_CLASS')
                if rec['cash_after_copper']-rec['cash_before_copper']!=rec['cash_delta_copper']:raise EngineError('BUSINESS_CASH_EQUATION')
                cash=[x for x in _account_registry(state)['ledger'] if x['entry_id']==rec['cash_entry_id']]
                if len(cash)!=1 or cash[0]['delta_units']!=rec['cash_delta_copper'] or cash[0]['before_units']!=rec['cash_before_copper'] or cash[0]['after_units']!=rec['cash_after_copper'] or cash[0]['account_id']!=rule['account_id'] or cash[0]['currency']!='copper':raise EngineError('BUSINESS_CASH_RECEIPT_MISSING')
                if base is not None:
                    ev=history_lookup(base,event_id=rec['event_id']);inp=history_lookup(base,event_id=saved['command_id'])
                    if actual:_business_confirmed_input_history(base,saved)
                    if not ev or ev.get('business_settlement')!=rec or (not actual and (not inp or inp.get('simulation_input')!=saved)):raise EngineError('BUSINESS_INPUT_OR_EVENT_HISTORY_MISSING')
                wr['inventory']=copy.deepcopy(saved['record']['inventory']['closing']);wr['last_settled_at']=iso;wr['inventory_status']=saved['record']['inventory']['status']
                expected_cash=rec['cash_after_copper']
            for iso in set(row['inputs'])-set(row['settlements']):
                saved=row['inputs'][iso]
                if saved['record']['record_kind']!='actual' or iso!=_task_monitor(tasks,task).get('next_review_at') or iso>state['game_time']:raise EngineError('BUSINESS_UNSETTLED_OR_FUTURE_AUTOMATIC_INPUT')
                _business_validate_day(saved['record'])
                if saved['record_sha256']!=_repair_digest(saved['record']) or saved['rule_sha256']!=_repair_digest(rule):raise EngineError('BUSINESS_ACTUAL_INPUT_BINDING')
                if base is not None:_business_confirmed_input_history(base,saved)
            if row['last_settled_at']!=wr['last_settled_at'] or (row['settlements'] and (row['inventory']!=wr['inventory'] or row['inventory_status']!=wr['inventory_status'])):raise EngineError('BUSINESS_INVENTORY_CONTINUITY')
    except Exception as ex:errors.append(str(ex))
    return {'status':'FAIL' if errors else 'PASS','errors':errors,'evidence_classes':['historical_confirmed','commander_accepted_simulation','unconfirmed_draft'], 'physical_inventory_never_inferred':True}


RESOLVER_FUNCTIONS['business_daily_settlement_v1']=_resolver_business_daily


def _scheduled_finance_once(implementation):
    """Protect old income resolvers against duplicate/direct/future calls as well as scheduler replay."""
    def wrapped(stage,state,tasks,task,when):
        iso=when.isoformat();mon=_task_monitor(tasks,task)
        if mon.get('last_reviewed_at') and iso<=mon['last_reviewed_at']:
            return {'status':'ALREADY_APPLIED','task_id':task['task_id'],'scheduled_at':iso,'cash_changed':False}
        if iso!=state['game_time'] or iso!=mon.get('next_review_at'):raise EngineError('SCHEDULED_SETTLEMENT_NOT_CURRENT_DUE_PERIOD')
        before=copy.deepcopy(state);before_tasks=copy.deepcopy(tasks);history=(stage/'events.jsonl').read_bytes()
        try:
            with _history_append_batch(stage/'events.jsonl'):
                return implementation(stage,state,tasks,task,when)
        except BaseException:
            state.clear();state.update(before);tasks.clear();tasks.update(before_tasks);(stage/'events.jsonl').write_bytes(history);raise
    return wrapped

_RESOLVE_MINING_V1=_resolver_jinchuan
_RESOLVE_RULE_V1=_resolver_settlement_rule
_resolver_jinchuan=_scheduled_finance_once(_RESOLVE_MINING_V1)
_resolver_settlement_rule=_scheduled_finance_once(_RESOLVE_RULE_V1)
RESOLVER_FUNCTIONS['jinchuan_daily_settlement_v1']=_resolver_jinchuan
RESOLVER_FUNCTIONS['settlement_rule_v1']=_resolver_settlement_rule


def _business_balance_evidence(state,account_id):
    rows=state.get('engine_runtime',{}).get('business_runtime_v1',{}).get('businesses',{})
    for row in rows.values():
        p=row.get('autonomy_policy',{})
        if p.get('account_id')==account_id:
            simulated=any(r.get('record_kind')=='commander_accepted_simulation' for r in row['settlements'].values())
            return {'class':'accepted_simulated_book_balance' if simulated else 'accepted_historical_opening',
                'physical_cash_verified':False,'policy_id':p['policy_id'],'contains_authorized_simulation':simulated,
                'meaning':'accepted in-game ledger balance; not evidence of physical receipts or POS reconciliation'}
    return None
