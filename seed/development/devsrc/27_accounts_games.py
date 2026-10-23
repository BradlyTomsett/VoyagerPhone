# === VOYAGER_DEV_MODULE: accounts_games ===
_account_command_scope=contextvars.ContextVar('voyager_account_command',default=None)


def _account_registry(state):
    reg=state.get('engine_runtime',{}).get('account_registry_v1')
    if not isinstance(reg,dict) or reg.get('schema')!='ACCOUNT_REGISTRY_V1':raise EngineError('ACCOUNT_REGISTRY_REQUIRED')
    return reg


def _account_record(state,account_id):
    rec=_account_registry(state)['accounts'].get(account_id)
    if not isinstance(rec,dict):raise EngineError('ACCOUNT_NOT_FOUND:'+str(account_id))
    return rec


def _account_units(state,account_id,currency):
    rec=_account_record(state,account_id)
    if currency not in rec['currencies']:raise EngineError('ACCOUNT_CURRENCY_MISMATCH')
    if rec.get('balance_ref'):value=get_by_path(state,rec['balance_ref'])[currency]
    else:value=rec['balances'][currency]
    if type(value) is not int or value<0:raise EngineError('ACCOUNT_UNITS_INVALID')
    return value


def _account_reserved(state,account_id,currency):
    games=state.get('engine_runtime',{}).get('minigame_runtime_v1',{}).get('sessions',{})
    return sum(r['stake_units'] for r in games.values() if r.get('account_id')==account_id and r.get('currency')==currency and r.get('status') in ('reserved','played'))


def _account_sync_views(state,account_id):
    rec=_account_record(state,account_id)
    for view in rec.get('legacy_read_only_views',[]):
        units=_account_units(state,account_id,view['currency']);scale=view.get('units_per_value',1)
        if view.get('available_only'):units-=_account_reserved(state,account_id,view['currency'])
        value=Decimal(units)/Decimal(scale)
        if view.get('format')=='integer':value=int(value)
        elif view.get('format')=='decimal_text':value=_account_decimal_text(units,scale)
        else:
            text=_price_text(value);number=float(text);value=number if Decimal(str(number))==value else text
        parent,key=_dot_parent(state,view['path']);parent[key]=value


def _accounts_record_cash(state,account_id,currency,delta,before,after):
    if type(delta) is not int or after!=before+delta:raise EngineError('ACCOUNT_LEDGER_DELTA_INVALID')
    reg=_account_registry(state);rows=reg['ledger'];seq=len(rows)+1
    row={'seq':seq,'account_id':account_id,'currency':currency,'delta_units':delta,'before_units':before,'after_units':after,
         'game_time':state['game_time'],'command_id':_account_command_scope.get() or 'SYSTEM:engine_credit','source':'current_engine_transaction'}
    row['entry_id']='CASH-'+_repair_digest(row)[:24];rows.append(row)
    return row


def _account_post(state,account_id,currency,delta):
    if type(delta) is not int:raise EngineError('ACCOUNT_INTEGER_DELTA_REQUIRED')
    rec=_account_record(state,account_id)
    if rec.get('status')!='active':raise EngineError('ACCOUNT_CLOSED')
    scale=rec.get('units_per_currency',{}).get(currency)
    quantum=scale//100 if currency=='grey' and type(scale) is int and scale>=100 else 1
    if currency=='grey' and (scale!=MONEY_SCALE or delta%quantum):raise EngineError('ACCOUNT_GREY_QUANTUM_OR_SCALE')
    before=_account_units(state,account_id,currency);after=before+delta
    if after<0:raise EngineError('ACCOUNT_INSUFFICIENT_BALANCE')
    if delta<0 and after<_account_reserved(state,account_id,currency):raise EngineError('ACCOUNT_RESERVED_FUNDS')
    if rec.get('balance_ref'):
        entry=_finance_credit(state,currency,_account_decimal_text(delta,scale))
    else:
        rec['balances'][currency]=after;entry=_accounts_record_cash(state,account_id,currency,delta,before,after)
        _account_sync_views(state,account_id)
    return entry


def _five_account_balances(state):
    specs=(('main_gold','fleet','gold'),('main_grey','fleet','grey'),('covert_copper','covert','copper'),('covert_grey','covert','grey'),('shop_copper','shop','copper'))
    result={}
    for key,aid,cur in specs:
        rec=_account_record(state,aid)
        if cur not in rec.get('currencies',[]):
            result[key]={'status':'NOT_REGISTERED','account_id':aid,'currency':cur,'amount':None};continue
        units=_account_units(state,aid,cur);scale=rec['units_per_currency'][cur]
        result[key]={'status':'CONFIRMED_CURRENT','account_id':aid,'currency':cur,'amount':_account_decimal_text(units,scale),'integer_units':str(units),'units_per_currency':scale,'reserved_units':str(_account_reserved(state,aid,cur))}
        evidence=_business_balance_evidence(state,aid)
        if evidence:
            result[key]['balance_evidence']=evidence
            if evidence['contains_authorized_simulation']:result[key]['status']='ACCEPTED_SIMULATED_BOOK_BALANCE'
        if cur=='copper':result[key]['display']={'gold':units//10000,'silver':units%10000//100,'copper':units%100}
    return result


def _account_transfer_amount(payload):
    cur=payload.get('currency');amount=payload.get('amount')
    if cur not in ('gold','grey','copper') or not isinstance(amount,(str,int)) or isinstance(amount,bool):raise EngineError('ACCOUNT_TRANSFER_EXACT_AMOUNT_REQUIRED')
    scale=1 if cur=='copper' else MONEY_SCALE;raw=_price_decimal(amount)*scale
    if raw!=raw.to_integral_value() or raw<=0:raise EngineError('ACCOUNT_TRANSFER_QUANTUM')
    units=int(raw)
    if cur=='grey' and units%100:raise EngineError('ACCOUNT_GREY_QUANTUM_OR_SCALE')
    return cur,units,scale


def _account_transfer_apply(state,payload):
    cur,units,scale=_account_transfer_amount(payload);src=payload['source_account'];dst=payload['destination_account']
    if src==dst:raise EngineError('ACCOUNT_TRANSFER_SAME_ACCOUNT')
    for aid in (src,dst):
        rec=_account_record(state,aid)
        if cur not in rec.get('currencies',[]) or rec.get('units_per_currency',{}).get(cur)!=scale:raise EngineError('ACCOUNT_TRANSFER_CURRENCY_OR_SCALE_MISMATCH')
        if rec.get('status')!='active':raise EngineError('ACCOUNT_CLOSED')
    if _account_units(state,src,cur)-_account_reserved(state,src,cur)<units:raise EngineError('ACCOUNT_INSUFFICIENT_AVAILABLE_BALANCE')
    debit=_account_post(state,src,cur,-units);credit=_account_post(state,dst,cur,units)
    return {'kind':'account_transfer','currency':cur,'amount':_account_decimal_text(units,scale),'source_account':src,'destination_account':dst,'cash_receipts':[debit,credit],'income_created':False,'entries':[x for aid,x in ((src,debit),(dst,credit)) if aid=='fleet'],'changes':[{'target':'state:engine_runtime.account_registry_v1','action':'internal_transfer_not_operating_income'}]+([{'target':'state:engine_runtime.finance_runtime','action':'transfer_main_account_units'},{'target':'state:summary.funds','action':'derive_main_account_balance'}] if 'fleet' in (src,dst) else [])+[{'target':'state:'+v['path'],'action':'derive_account_view'} for aid in (src,dst) for v in _account_record(state,aid).get('legacy_read_only_views',[])]}


def account_query_packet(base:Path=ROOT,account_id:Optional[str]=None):
    ensure_source_ready(base);state=read_json_view(Path(base)/'state.json');reg=_account_registry(state);rows=[]
    for aid,rec in reg['accounts'].items():
        if account_id and aid!=account_id:continue
        balances={}
        for cur in rec['currencies']:
            units=_account_units(state,aid,cur);reserved=_account_reserved(state,aid,cur);scale=rec['units_per_currency'][cur]
            balances[cur]={'integer_units':str(units),'amount':_account_decimal_text(units,scale),'reserved_units':str(reserved),'available_units':str(units-reserved),'units_per_currency':scale}
        rows.append({'account_id':aid,'status':rec['status'],'owner':copy.deepcopy(rec['owner']),'balance_evidence':_business_balance_evidence(state,aid),'balances':balances,'authority':rec.get('balance_ref') or 'state:engine_runtime.account_registry_v1.accounts.'+aid+'.balances'})
    return {'packet':'ACCOUNT_QUERY_V1','status':'COMPLETE' if rows else 'NOT_FOUND','accounts':rows,'five_balances':_five_account_balances(state) if account_id is None else None,'save_set_id':read_json_view(Path(base)/'manifest.json')['save_set_id']}


def accounts_integrity_report(state):
    reg=state.get('engine_runtime',{}).get('account_registry_v1')
    if reg is None:return {'status':'LEGACY','errors':[]}
    errors=[]
    try:
        _account_registry(state);last={}
        for i,row in enumerate(reg['ledger'],1):
            key=(row['account_id'],row['currency'])
            body={k:v for k,v in row.items() if k!='entry_id'}
            if row.get('entry_id')!='CASH-'+_repair_digest(body)[:24]:errors.append('LEDGER_RECEIPT_HASH')
            if key not in last and row['before_units']!=reg.get('opening_units',{}).get(row['account_id'],{}).get(row['currency']):errors.append('LEDGER_OPENING_BALANCE')
            if row['seq']!=i or row['after_units']!=row['before_units']+row['delta_units']:errors.append('LEDGER_SEQUENCE_OR_AMOUNT')
            if key in last and row['before_units']!=last[key]:errors.append('LEDGER_CHAIN')
            last[key]=row['after_units']
        for aid,rec in reg['accounts'].items():
            if len(rec['currencies'])!=len(set(rec['currencies'])):errors.append('ACCOUNT_DUPLICATE_CURRENCY:'+aid)
            for cur in rec['currencies']:
                units=_account_units(state,aid,cur)
                scale=rec.get('units_per_currency',{}).get(cur)
                if type(scale) is not int or scale<=0 or (cur=='grey' and (scale!=MONEY_SCALE or units%100)):errors.append('ACCOUNT_CURRENCY_SCALE_OR_QUANTUM:'+aid)
                if _account_reserved(state,aid,cur)>units:errors.append('RESERVATION_EXCEEDS_BALANCE:'+aid)
                expected=last.get((aid,cur),reg.get('opening_units',{}).get(aid,{}).get(cur))
                if units!=expected:errors.append('LEDGER_BALANCE:'+aid)
            for view in rec.get('legacy_read_only_views',[]):
                actual=_price_decimal(get_by_path(state,view['path']))*view.get('units_per_value',1)
                if actual!=_account_units(state,aid,view['currency'])-(_account_reserved(state,aid,view['currency']) if view.get('available_only') else 0):errors.append('ACCOUNT_LEGACY_VIEW:'+view['path'])
        for sid,game in state.get('engine_runtime',{}).get('minigame_runtime_v1',{}).get('sessions',{}).items():
            if game.get('status') not in ('reserved','played','settled','cancelled') or game.get('session_id')!=sid or type(game.get('stake_units')) is not int or game['stake_units']<=0:errors.append('GAME_STATE:'+sid)
            if game.get('status') in ('played','settled'):
                expected=_game_result(state,game)
                if game.get('result')!=expected:errors.append('GAME_RESULT:'+sid)
    except Exception as ex:errors.append(str(ex))
    return {'status':'FAIL' if errors else 'PASS','errors':errors}


def _game_result(state,session):
    seed=state['engine_runtime']['seed_anchor'];basis=[seed,'coinflip_v1',session['session_id'],session['reserve_command_id']]
    outcome='heads' if int(_repair_digest(basis),16)%2==0 else 'tails'
    payout=session['stake_units']*2 if outcome==session['choice'] else 0
    return {'outcome':outcome,'payout_units':payout,'proof':_repair_digest({'basis_sha256':_repair_digest(basis),'outcome':outcome,'payout_units':payout})}


def _game_session_apply(state,tasks,payload):
    sid=payload['session_id'];action=payload['game_action'];aid=payload['account_id'];currency=payload['currency']
    if not isinstance(sid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',sid):raise EngineError('GAME_SESSION_ID_INVALID')
    rt=state['engine_runtime']['minigame_runtime_v1'];sessions=rt['sessions'];rec=sessions.get(sid);entries=[]
    _account_units(state,aid,currency)
    if action=='reserve':
        if rec is not None:raise EngineError('GAME_SESSION_ALREADY_EXISTS')
        stake=payload.get('stake_units');choice=payload.get('choice')
        if type(stake) is not int or stake<=0 or choice not in ('heads','tails'):raise EngineError('GAME_RESERVATION_INVALID')
        if currency=='grey' and stake%100:raise EngineError('GAME_GREY_QUANTUM')
        if _account_record(state,aid)['status']!='active' or stake>_account_units(state,aid,currency)-_account_reserved(state,aid,currency):raise EngineError('GAME_INSUFFICIENT_AVAILABLE_FUNDS')
        sessions[sid]={'session_id':sid,'rule_id':'MINIGAME-COINFLIP-V1','account_id':aid,'currency':currency,'stake_units':stake,'choice':choice,'status':'reserved','reserve_command_id':payload['command_id'],'reserved_at':state['game_time']}
        rec=sessions[sid]
    else:
        if not isinstance(rec,dict) or rec['account_id']!=aid or rec['currency']!=currency:raise EngineError('GAME_SESSION_ACCOUNT_MISMATCH')
        if action=='play':
            if rec['status']!='reserved':raise EngineError('GAME_PLAY_TRANSITION')
            rec.update(status='played',result=_game_result(state,rec),play_command_id=payload['command_id'])
        elif action=='settle':
            if rec['status']!='played':raise EngineError('GAME_SETTLE_TRANSITION')
            if rec['result']!=_game_result(state,rec):raise EngineError('GAME_RESULT_TAMPERED')
            delta=rec['result']['payout_units']-rec['stake_units']
            rec['status']='settled'
            try:entry=_account_post(state,aid,currency,delta)
            except BaseException:
                rec['status']='played';raise
            if aid=='fleet':entries.append(entry)
            rec.update(status='settled',settle_command_id=payload['command_id'],settled_at=state['game_time'],delta_units=delta)
        elif action=='cancel':
            if rec['status']!='reserved':raise EngineError('GAME_CANCEL_TRANSITION')
            rec.update(status='cancelled',cancel_command_id=payload['command_id'])
        else:raise EngineError('GAME_ACTION_INVALID')
    _account_sync_views(state,aid)
    return {'kind':'game_session','session':copy.deepcopy(rec),'entries':entries,'changes':[{'target':'state:engine_runtime.minigame_runtime_v1.sessions.'+sid,'action':action},{'target':'state:engine_runtime.account_registry_v1','action':'atomic_account_receipt'}]}


def _batch_b_command_targets(payload):
    kind=payload.get('kind')
    if kind=='account_transfer':
        cur,_,_=_account_transfer_amount(payload)
        return ['state:account:'+str(payload[k])+':'+cur for k in ('source_account','destination_account')]
    if kind=='business_day_record':
        return ['tasks:task:'+str(payload['task_id']),'state:engine_runtime.business_runtime_v1','state:account:'+str(payload['account_id'])+':copper']
    if kind=='game_session':return ['state:engine_runtime.minigame_runtime_v1.sessions.'+str(payload['session_id']),'state:account:'+str(payload['account_id'])+':'+str(payload['currency'])]
    if kind=='settle_price' and payload.get('delivery'):
        return [_pricing_account_target(payload),'state:engine_runtime.pricing_runtime.settlements.'+str(payload['settlement_id']),payload['delivery']['inventory_ref']]
    if kind=='content_install':return ['catalog:content_packages_v1.packages.'+str(payload['package'].get('package_id'))]
    return None


def _batch_b_command_cost(payload):
    if payload.get('kind')=='account_transfer':
        cur,units,_=_account_transfer_amount(payload)
        return {'uses':1,'gold_units':units if cur in ('gold','copper') else 0,'grey_units':units if cur=='grey' else 0,'quantity':units}
    if payload.get('kind')=='business_day_record':
        debit=_business_integer(payload.get('cash_debit_limit_copper'),'cash_debit_limit_copper')
        return {'uses':1,'gold_units':debit,'grey_units':0,'quantity':1}
    if payload.get('kind')!='game_session':return None
    out={'uses':1,'gold_units':0,'grey_units':0,'quantity':0}
    if payload['game_action']=='reserve':
        stake=payload.get('stake_units')
        if type(stake) is not int or stake<=0:raise EngineError('GAME_INTEGER_STAKE_REQUIRED')
        out['quantity']=stake
        if payload['currency'] in ('gold','grey'):out[payload['currency']+'_units']=stake
        elif payload['currency']=='copper':out['gold_units']=stake
    return out


def _batch_b_apply_command(stage,state,tasks,payload,implementation):
    token=_account_command_scope.set(payload['command_id'])
    try:
        if payload['kind']=='game_session':return _game_session_apply(state,tasks,payload)
        if payload['kind']=='content_install':return _content_install(stage,payload)
        if payload['kind']=='account_transfer':return _account_transfer_apply(state,payload)
        if payload['kind']=='business_day_record':return _business_day_record(state,tasks,payload)
        return implementation(stage,state,tasks,payload)
    finally:_account_command_scope.reset(token)


def _settlement_inventory_delivery(state,quote,payload,confirmed):
    tx=quote['request']['transaction_type']
    if tx not in ('purchase','sale','liquidation'):return []
    delivery=payload.get('delivery')
    if not isinstance(delivery,dict) or delivery!=confirmed.get('inventory_delivery'):raise EngineError('SETTLEMENT_MATCHING_DELIVERY_REQUIRED')
    item=quote['request'].get('item_id');routes={'SUPPLY-FOOD':'food','SUPPLY-WATER':'water','SUPPLY-PARTS':'maintenance_parts','SUPPLY-AIR':'compressed_air','SUPPLY-FUEL':'fuel','SUPPLY-MEDICAL':'medical_kits'}
    ref=delivery.get('inventory_ref','');prefix='state:inventories.supply_inventory.fleets.'
    if item not in routes or not ref.startswith(prefix):raise EngineError('SETTLEMENT_TYPED_INVENTORY_ROUTE_REQUIRED')
    tail=ref[len(prefix):].split('.')
    if len(tail)!=3 or tail[0] not in ('voyager','jinchuan') or tail[1]!=routes[item] or tail[2]!='value':raise EngineError('SETTLEMENT_ITEM_INVENTORY_MISMATCH')
    qty=_price_decimal(quote['quantity']);delta=qty if tx=='purchase' else -qty
    if delta!=delta.to_integral_value() or _price_decimal(delivery.get('delta'))!=delta:raise EngineError('SETTLEMENT_QUANTITY_MISMATCH')
    leaf=get_by_path(state,ref[6:].rsplit('.',1)[0])
    if delivery.get('unit')!=leaf['unit'] or quote['unit']!=leaf['unit']:raise EngineError('SETTLEMENT_DELIVERY_UNIT_MISMATCH')
    before=leaf['value'];after=before+int(delta)
    if type(before) is not int or after<0:raise EngineError('SETTLEMENT_INVENTORY_BALANCE_INVALID')
    leaf['value']=after
    return [{'target':ref,'action':'verified_atomic_inventory_delivery','before':before,'after':after,'source_event_id':payload['source_event_id']}]


def _account_decimal_text(units,scale):
    if type(units) is not int or scale not in (1,10,100,1000,10000):raise EngineError('ACCOUNT_EXACT_UNITS_REQUIRED')
    whole,frac=divmod(abs(units),scale);sign='-' if units<0 else ''
    return sign+str(whole)+('.'+str(frac).zfill(len(str(scale))-1).rstrip('0') if frac else '')

_batch_b_account_query=account_query_packet
