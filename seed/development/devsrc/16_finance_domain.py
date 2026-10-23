# === VOYAGER_DEV_MODULE: finance_domain ===
def _money_units4(value:Any)->int:
    """Convert a decimal-compatible value to exact 1/10000 units.

    All arithmetic that can change a committed balance passes through integer units.
    Legacy JSON numeric fields remain a compatibility view, never the arithmetic source.
    """
    from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, localcontext
    try:
        raw=Decimal(str(value))
        if not raw.is_finite():raise EngineError('MONEY_NOT_FINITE')
        with localcontext() as ctx:
            ctx.prec=max(80,len(raw.as_tuple().digits)+abs(raw.adjusted())+20)
            if ctx.prec>4096:raise EngineError('MONEY_PRECISION_LIMIT')
            q=(raw*MONEY_SCALE).quantize(Decimal('1'),rounding=ROUND_HALF_UP)
    except (InvalidOperation,ValueError,TypeError) as ex:raise EngineError(f'MONEY_INVALID:{value!r}') from ex
    if not q.is_finite():raise EngineError('MONEY_NOT_FINITE')
    return int(q)

def _money_value4(units:int):
    if not isinstance(units,int) or isinstance(units,bool):raise EngineError('MONEY_UNITS_INTEGER_REQUIRED')
    whole,frac=divmod(abs(units),MONEY_SCALE);sign='-' if units<0 else ''
    if frac==0:return -whole if units<0 else whole
    # JSON compatibility view only. The exact committed arithmetic authority is integer units.
    text=f'{sign}{whole}.{frac:04d}';value=float(text)
    try:return value if math.isfinite(value) and _money_units4(value)==units else text
    except EngineError:return text

def _money4(value):
    return _money_value4(_money_units4(value))

def _money_currency(value:Any,currency:str):
    """Quantize a currency value to its authoritative decimal precision."""
    from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, localcontext
    if currency not in MONEY_DECIMAL_PLACES:raise EngineError(f'MONEY_CURRENCY_INVALID:{currency}')
    places=int(MONEY_DECIMAL_PLACES[currency]);quant=Decimal('1').scaleb(-places)
    try:
        raw=Decimal(str(value))
        if not raw.is_finite():raise EngineError('MONEY_NOT_FINITE')
        with localcontext() as ctx:
            ctx.prec=max(80,len(raw.as_tuple().digits)+abs(raw.adjusted())+20)
            if ctx.prec>4096:raise EngineError('MONEY_PRECISION_LIMIT')
            q=raw.quantize(quant,rounding=ROUND_HALF_UP)
    except (InvalidOperation,ValueError,TypeError) as ex:raise EngineError(f'MONEY_INVALID:{value!r}') from ex
    if not q.is_finite():raise EngineError('MONEY_NOT_FINITE')
    if q==q.to_integral_value():return int(q)
    text=format(q,f'.{places}f');value=float(text)
    return value if Decimal(str(value))==q else text

def _money_units_currency(value:Any,currency:str)->int:
    from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, localcontext
    if currency not in MONEY_DECIMAL_PLACES:raise EngineError(f'MONEY_CURRENCY_INVALID:{currency}')
    try:
        raw=Decimal(str(value))
        if not raw.is_finite():raise EngineError('MONEY_NOT_FINITE')
        with localcontext() as ctx:
            ctx.prec=max(80,len(raw.as_tuple().digits)+abs(raw.adjusted())+20)
            if ctx.prec>4096:raise EngineError('MONEY_PRECISION_LIMIT')
            quant=Decimal(1).scaleb(-MONEY_DECIMAL_PLACES[currency]);rounded=raw.quantize(quant,rounding=ROUND_HALF_UP);units=int(rounded*MONEY_SCALE)
    except (InvalidOperation,ValueError,TypeError) as ex:raise EngineError(f'MONEY_INVALID:{value!r}') from ex
    quantum=int(MONEY_QUANTUM_UNITS[currency])
    if units%quantum:raise EngineError(f'MONEY_QUANTUM_VIOLATION:{currency}:{units}:{quantum}')
    return units

def _money_value_currency(units:int,currency:str):
    quantum=int(MONEY_QUANTUM_UNITS[currency])
    if not isinstance(units,int) or isinstance(units,bool):raise EngineError('MONEY_UNITS_INTEGER_REQUIRED')
    if units%quantum:raise EngineError(f'MONEY_QUANTUM_VIOLATION:{currency}:{units}:{quantum}')
    return _money_value4(units)

def _money_add4(a,b):
    return _money_value4(_money_units4(a)+_money_units4(b))

def _money_mul4(a,b):
    from decimal import Decimal, ROUND_HALF_UP
    q=(Decimal(str(a))*Decimal(str(b))*MONEY_SCALE).quantize(Decimal('1'),rounding=ROUND_HALF_UP)
    if not q.is_finite():raise EngineError('MONEY_NOT_FINITE')
    return _money_value4(int(q))

def _finance_runtime(state:dict,create:bool=False)->Optional[dict]:
    er=state.setdefault('engine_runtime',{}) if create else (state.get('engine_runtime') or {})
    fr=er.get('finance_runtime')
    if fr is None:
        if not create:return None
        funds=((state.get('summary') or {}).get('funds') or {})
        fr={'schema':MONEY_MODEL_SCHEMA,'scale':MONEY_SCALE,'currency_decimal_places':copy.deepcopy(MONEY_DECIMAL_PLACES),'currency_quantum_units':copy.deepcopy(MONEY_QUANTUM_UNITS),'authority':'integer_units','compatibility_view':'STATE.summary.funds','funds_units':{k:_money_units_currency(funds.get(k,0),k) for k in ('gold','grey')}}
        er['finance_runtime']=fr
    if not isinstance(fr,dict) or fr.get('schema')!=MONEY_MODEL_SCHEMA or fr.get('scale')!=MONEY_SCALE:raise EngineError('FINANCE_RUNTIME_INVALID')
    if fr.get('currency_decimal_places')!=MONEY_DECIMAL_PLACES or fr.get('currency_quantum_units')!=MONEY_QUANTUM_UNITS:raise EngineError('FINANCE_RUNTIME_PRECISION_PROFILE_INVALID')
    fu=fr.get('funds_units')
    if not isinstance(fu,dict) or any(not isinstance(fu.get(k),int) or isinstance(fu.get(k),bool) for k in ('gold','grey')):raise EngineError('FINANCE_RUNTIME_UNITS_INVALID')
    for k in ('gold','grey'):
        if fu[k]%int(MONEY_QUANTUM_UNITS[k]):raise EngineError(f'FINANCE_RUNTIME_QUANTUM_INVALID:{k}')
    return fr

def _finance_sync_view(state:dict)->dict:
    fr=_finance_runtime(state,create=True);funds=state.setdefault('summary',{}).setdefault('funds',{})
    for k in ('gold','grey'):funds[k]=_money_value_currency(fr['funds_units'][k],k)
    return funds

def _finance_activate(state:dict)->dict:
    existed=_finance_runtime(state,create=False) is not None
    fr=_finance_runtime(state,create=True);_finance_sync_view(state)
    return {'schema':MONEY_MODEL_SCHEMA,'activated':not existed,'scale':MONEY_SCALE,'currency_decimal_places':copy.deepcopy(MONEY_DECIMAL_PLACES),'funds_units':copy.deepcopy(fr['funds_units'])}

def _finance_credit(state:dict,currency:str,delta:Any)->dict:
    if currency not in {'gold','grey'}:raise EngineError(f'FINANCE_CURRENCY_INVALID:{currency}')
    fr=_finance_runtime(state,create=True);du=_money_units_currency(delta,currency);before=int(fr['funds_units'][currency]);after=before+du
    if after<0:raise EngineError(f'FINANCE_NEGATIVE_BALANCE:{currency}')
    fr['funds_units'][currency]=after;_finance_sync_view(state)
    if state.get('engine_runtime',{}).get('account_registry_v1'):_accounts_record_cash(state,'fleet',currency,du,before,after)
    return {'currency':currency,'delta_units':du,'before_units':before,'after_units':after,'delta':_money_value_currency(du,currency),'before':_money_value_currency(before,currency),'after':_money_value_currency(after,currency)}

def _finance_integrity_report(state:dict)->dict:
    fr=_finance_runtime(state,create=False)
    if fr is None:return {'active':False,'status':'LEGACY'}
    errs=[];funds=((state.get('summary') or {}).get('funds') or {})
    try:
        if fr.get('scale')!=MONEY_SCALE:errs.append('scale_mismatch')
        if fr.get('currency_decimal_places')!=MONEY_DECIMAL_PLACES:errs.append('currency_decimal_places_mismatch')
        if fr.get('currency_quantum_units')!=MONEY_QUANTUM_UNITS:errs.append('currency_quantum_units_mismatch')
        for k in ('gold','grey'):
            u=(fr.get('funds_units') or {}).get(k)
            if not isinstance(u,int) or isinstance(u,bool):errs.append(f'{k}_units_invalid');continue
            if u%int(MONEY_QUANTUM_UNITS[k]):errs.append(f'{k}_quantum_invalid')
            try:vu=_money_units_currency(funds.get(k),k)
            except Exception as ex:errs.append(f'{k}_view_invalid:{ex}');continue
            if vu!=u:errs.append(f'{k}_view_mismatch:{vu}!={u}')
            if u<0:errs.append(f'{k}_negative')
    except Exception as ex:errs.append(str(ex))
    return {'active':True,'status':'PASS' if not errs else 'FAIL','errors':errs,'schema':MONEY_MODEL_SCHEMA,'scale':MONEY_SCALE,'currency_decimal_places':copy.deepcopy(MONEY_DECIMAL_PLACES)}

