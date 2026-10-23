# === VOYAGER_DEV_MODULE: pricing_domain ===
# Price authority and exact quotes. Monetary mutations use finance_domain.
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

PRICING_SCHEMA='PRICING_RUNTIME_V1'
PRICE_KINDS={'fixed_price','reference_range','formula','seller_quote','agreed_price','historical_price','provisional_estimate'}
PRICE_STATUS={'active','pending','expired','superseded'}
PRICE_CURRENCY={'金币':'gold','银币':'silver','铜币':'copper','灰币':'grey','gold':'gold','silver':'silver','copper':'copper','grey':'grey'}
PRICE_UNITS={'每件':'件','每架':'架','每吨':'吨','每箱':'箱','每人':'人','每晚':'晚','每一天':'天','每天':'天','每年':'年','每份':'份','每批':'批','ton':'吨','kg':'千克','night':'晚','copy':'份'}
PRICE_RESEARCH_PATH='world_state_overrides.markets_and_procurement.research_data_sales_program'
PRICE_SILVER_ACCOUNT='world_state_overrides.freeport_xilu9_current.hawke_commercial_cover.cash_account'

def _price_decimal(value):
    if isinstance(value,bool) or value is None:raise EngineError('PRICE_NUMBER_REQUIRED')
    try:d=Decimal(str(value))
    except (InvalidOperation,ValueError):raise EngineError('PRICE_NUMBER_INVALID')
    if not d.is_finite():raise EngineError('PRICE_NUMBER_NOT_FINITE')
    return d

def _price_text(value):
    text=format(_price_decimal(value),'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text

def _price_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def _pricing_documents(base):
    b=Path(base)
    return {k:read_json(b/(k+'.json')) for k in ('rules','catalog','state','manifest')}

def _pricing_runtime(state):
    rt=(state.get('engine_runtime') or {}).get('pricing_runtime')
    if not isinstance(rt,dict) or rt.get('schema')!=PRICING_SCHEMA:raise EngineError('PRICING_RUNTIME_NOT_ADOPTED')
    return rt

def _pricing_source_value(docs,ref):
    if not isinstance(ref,str) or ':' not in ref:raise EngineError('PRICE_SOURCE_REFERENCE_REQUIRED')
    head,path=ref.split(':',1)
    if head not in docs:raise EngineError('PRICE_SOURCE_NAMESPACE_INVALID')
    x=docs[head]
    if path.startswith('document_segments.order='):
        match=re.fullmatch(r'document_segments\.order=(\d+)\.markdown',path)
        if not match:raise EngineError('PRICE_DOCUMENT_REFERENCE_INVALID')
        return next(row['markdown'] for row in x['document_segments'] if row['order']==int(match[1]))
    for key,index in re.findall(r'([^.[\]]+)|\[(\d+)\]',path):
        try:x=x[int(index)] if index else x[key]
        except (KeyError,IndexError,TypeError):raise EngineError('PRICE_SOURCE_MISSING:'+ref)
    return x

def _pricing_set_value(docs,ref,value):
    head,path=ref.split(':',1);parts=list(re.findall(r'([^.[\]]+)|\[(\d+)\]',path));x=docs[head]
    for key,index in parts[:-1]:x=x[int(index)] if index else x[key]
    key,index=parts[-1];x[int(index) if index else key]=value

def _pricing_policy(docs):
    policy=docs['rules']['runtime_rules'].get('pricing_contract')
    if not isinstance(policy,dict) or policy.get('schema')!='PRICING_CONTRACT_V1':raise EngineError('PRICING_CONTRACT_MISSING')
    if policy['currency_precision'].get('gold')!=MONEY_DECIMAL_PLACES['gold'] or policy['currency_precision'].get('grey')!=MONEY_DECIMAL_PLACES['grey']:raise EngineError('PRICE_FINANCE_PRECISION_CONFLICT')
    grey=_price_decimal(_pricing_source_value(docs,policy['grey_rate_ref']))
    if grey<=0:raise EngineError('PRICE_GREY_EXCHANGE_INVALID')
    return policy

def _price_rates(docs):
    policy=_pricing_policy(docs);rates={k:_price_decimal(v) for k,v in policy['currency_gold_rates'].items()};rates['grey']=_price_decimal(_pricing_source_value(docs,policy['grey_rate_ref']))
    if rates.get('gold')!=1 or rates.get('silver')!=Decimal('.01') or rates.get('copper')!=Decimal('.0001'):raise EngineError('PRICE_CURRENCY_RATIO_CONFLICT')
    return rates

def convert_money_exact(amount,currency,target_currency,base=ROOT,round_result=True,documents=None):
    docs=documents or _pricing_documents(base);currency=PRICE_CURRENCY.get(currency);target_currency=PRICE_CURRENCY.get(target_currency)
    if not currency or not target_currency:raise EngineError('PRICE_CURRENCY_REQUIRED')
    result=_price_decimal(amount)*_price_rates(docs)[currency]/_price_rates(docs)[target_currency]
    if round_result:
        if target_currency in {'gold','grey'}:return _price_text(Decimal(_money_units_currency(result,target_currency))/MONEY_SCALE)
        result=result.quantize(Decimal(1).scaleb(-_pricing_policy(docs)['currency_precision'][target_currency]),rounding=ROUND_HALF_UP)
    return _price_text(result)

def normalize_price_request(request):
    if not isinstance(request,dict):raise EngineError('PRICE_REQUEST_OBJECT_REQUIRED')
    p=copy.deepcopy(request)
    for k in ('trusted','verified','authorized','is_authorized','authorization_status'):
        if k in p:raise EngineError('PRICE_CALLER_CLAIM_FORBIDDEN:'+k)
    if not isinstance(p.get('item_id') or p.get('price_id'),str):raise EngineError('PRICE_ITEM_ID_REQUIRED')
    q=_price_decimal(p.get('quantity'))
    if q<=0:raise EngineError('PRICE_QUANTITY_POSITIVE_REQUIRED')
    p['quantity']=_price_text(q)
    if not isinstance(p.get('unit'),str) or not p['unit']:raise EngineError('PRICE_UNIT_REQUIRED')
    p['unit']=PRICE_UNITS.get(p['unit'],p['unit'])
    cur=PRICE_CURRENCY.get(p.get('currency'))
    if not cur:raise EngineError('PRICE_CURRENCY_REQUIRED')
    p['currency']=cur;p.setdefault('specification',{});p.setdefault('modifiers',[]);p.setdefault('transaction_type','reference')
    if not isinstance(p['specification'],dict) or not isinstance(p['modifiers'],list):raise EngineError('PRICE_SPECIFICATION_INVALID')
    if p['transaction_type'] not in {'reference','purchase','sale','service','wage','estimate','liquidation'}:raise EngineError('PRICE_TRANSACTION_TYPE_INVALID')
    for key in ('quoted_unit_price','claimed_total'):
        if key in p:
            v=p[key]
            if not isinstance(v,dict) or set(v) not in ({'amount','currency'},{'amount','currency','unit'}) or not PRICE_CURRENCY.get(v['currency']):raise EngineError('PRICE_TYPED_MONEY_REQUIRED:'+key)
            amount=_price_decimal(v['amount'])
            if amount<0:raise EngineError('PRICE_NEGATIVE_AMOUNT')
            p[key]={'amount':_price_text(amount),'currency':PRICE_CURRENCY[v['currency']],**({'unit':PRICE_UNITS.get(v['unit'],v['unit'])} if 'unit' in v else {})}
    return p

def _price_records(docs):
    records=copy.deepcopy(docs['catalog'].get('price_registry_v1',{}).get('records',{}));rt=_pricing_runtime(docs['state'])
    for pid,row in rt['registered_prices'].items():
        if pid in records:raise EngineError('PRICE_DUPLICATE_ID:'+pid)
        records[pid]=copy.deepcopy(row)
    program=get_by_path(docs['state'],PRICE_RESEARCH_PATH);policy=_pricing_policy(docs)
    for row in records.values():
        if row.get('category')=='research' and program['packages'].get(row['item_id'],{}).get('status') not in {'on_sale','active_nonexclusive_digital_backup'}:row['status']='expired'
    for item,row in program['packages'].items():
        if row.get('status') not in {'on_sale','active_nonexclusive_digital_backup'}:continue
        pid='PRICE-'+item
        if pid not in records:
            template=copy.deepcopy(records['PRICE-RESEARCH-POLICY']);template.update({'price_id':pid,'item_id':item,'name':row.get('name',item),'category':'research','value_ref':'state:'+PRICE_RESEARCH_PATH+'.packages.'+item+'.price_gold_per_copy','source_ref':'state:'+PRICE_RESEARCH_PATH+'.packages.'+item+'.price_gold_per_copy','policy_ref':policy['research_policy_ref']});records[pid]=template
        records[pid]['price_version']=1+len(rt['policy_updates'])
    return records

def _price_scope_match(row,request,docs=None):
    if row.get('status')!='active' or row.get('price_kind')=='historical_price':return False
    if not _pricing_price_visible(row,docs,request.get('audience')):return False
    for key,value in row.get('scope',{}).items():
        if request.get(key)!=value:return False
    # Explicit identity selects its sealed definition. Any supplied conflicting detail fails.
    for key,value in row.get('specification',{}).items():
        if key in request['specification'] and request['specification'][key]!=value:
            if not (key=='condition' and row['category']=='external_weapon' and request['specification'][key]=='used' and any(m.get('kind')=='external_used' for m in request['modifiers'] if isinstance(m,dict))):return False
    return True

def resolve_price_authority(request,base=ROOT,documents=None):
    docs=documents or _pricing_documents(base);p=normalize_price_request(_pricing_request_reference(request,docs));rows=_price_records(docs)
    if p.get('price_id'):
        row=rows.get(p['price_id']);candidates=[row] if row else []
    else:candidates=[r for r in rows.values() if r.get('item_id')==p['item_id']]
    valid=[];now=docs['state']['game_time']
    for row in candidates:
        if row is None or (p.get('item_id') and p['item_id']!=row['item_id']):continue
        if not _price_scope_match(row,p,docs):continue
        if row.get('valid_from') and now<row['valid_from'] or row.get('valid_until') and now>row['valid_until']:continue
        valid.append(row)
    if not valid:raise EngineError('PRICE_NEEDS_EVIDENCE_NO_APPLICABLE_AUTHORITY')
    superseded={pid for row in valid for pid in row.get('supersedes',[])};valid=[row for row in valid if row['price_id'] not in superseded]
    priority={'commander_override':5,'fixed_price':4,'formula':4,'agreed_price':4,'seller_quote':4,'reference_range':3,'provisional_estimate':2}
    top=max(priority.get(row.get('priority') or row['price_kind'],1) for row in valid);valid=[row for row in valid if priority.get(row.get('priority') or row['price_kind'],1)==top]
    if len(valid)!=1:raise EngineError('PRICE_NEEDS_EVIDENCE_AMBIGUOUS_AUTHORITY')
    return copy.deepcopy(valid[0])

def _price_anchor_value(row,docs,seen=None):
    seen=set(seen or [])
    if row['price_id'] in seen:raise EngineError('PRICE_FORMULA_CYCLE')
    seen.add(row['price_id']);_pricing_source_value(docs,row['source_ref'])
    if row['price_kind']=='formula':
        formula=row['formula'];parent=_price_records(docs).get(formula['base_price_id'])
        if not parent or parent['currency']!=row['currency']:raise EngineError('PRICE_FORMULA_BASE_INVALID')
        lo,hi=_price_anchor_value(parent,docs,seen);return lo*_price_decimal(formula['multiplier']),hi*_price_decimal(formula['multiplier'])
    value=_pricing_source_value(docs,row['value_ref']) if row.get('value_ref') else row.get('range',row.get('amount'))
    if isinstance(value,list):
        if len(value)!=2:raise EngineError('PRICE_RANGE_INVALID')
        lo,hi=map(_price_decimal,value)
    else:lo=hi=_price_decimal(value)
    if lo<0 or hi<lo:raise EngineError('PRICE_ANCHOR_INVALID')
    if row.get('policy_ref') and lo!=_price_decimal(_pricing_source_value(docs,row['policy_ref'])):raise EngineError('PRICE_RESEARCH_POLICY_CONFLICT')
    return lo,hi

def _pricing_evidence(docs,evidence_id,row,p,purpose):
    ev=_pricing_runtime(docs['state'])['evidence'].get(evidence_id)
    if not isinstance(ev,dict) or ev.get('status')!='active' or ev.get('purpose')!=purpose:raise EngineError('PRICE_EVIDENCE_MISSING_OR_INACTIVE')
    if ev.get('item_id') and ev['item_id']!=row['item_id'] or ev.get('category') and ev['category']!=row['category']:raise EngineError('PRICE_EVIDENCE_ITEM_OUT_OF_SCOPE')
    allowed={'supply':{'RULE-SUPPLY-INVENTORY-01','RULE-ECONOMY-01'},'star_chart':{'RULE-STAR-CHART-PRICE-01'},'own_equipment':{'RULE-EQUIPMENT-MARKET-REFERENCE-01'},'ship':{'RULE-SHIPMARKET-01','RULE-ECONOMY-01'},'local_service':{'RULE-UNSEALED-PRICE-REALISM-83630909','RULE-ECONOMY-01'}}
    if row['category'] in allowed and ev.get('rule_id') not in allowed[row['category']]:raise EngineError('PRICE_EXCEPTION_RULE_NOT_APPLICABLE')
    for key,val in ev.get('scope',{}).items():
        if p.get(key)!=val:raise EngineError('PRICE_EVIDENCE_SCOPE_MISMATCH')
    now=docs['state']['game_time']
    if ev.get('valid_from') and now<ev['valid_from'] or ev.get('valid_until') and now>ev['valid_until']:raise EngineError('PRICE_EVIDENCE_EXPIRED')
    if _price_digest(_pricing_source_value(docs,ev['source_ref']))!=ev['source_sha256']:raise EngineError('PRICE_EVIDENCE_SOURCE_CHANGED')
    return ev

def _price_modifier(mod,row,p,docs,seen):
    if not isinstance(mod,dict) or not isinstance(mod.get('kind'),str):raise EngineError('PRICE_MODIFIER_INVALID')
    kind=mod['kind'];event=mod.get('evidence_id')
    identity='evidence:'+str(event) if event else 'kind:'+kind
    risk=(_pricing_runtime(docs['state'])['evidence'].get(event) or {}).get('factor_id') if event else None
    if identity in seen or risk and 'factor:'+risk in seen:raise EngineError('PRICE_DUPLICATE_MODIFIER')
    seen.add(identity)
    if risk:seen.add('factor:'+risk)
    if kind in row.get('included_components',[]) or kind=='length' and 'length_adjustment' in row.get('included_components',[]) or kind=='armament' and 'native_armament' in row.get('included_components',[]):raise EngineError('PRICE_INCLUDED_COMPONENT_RECHARGED')
    if kind in {'combat_ratio','player_balance'}:raise EngineError('PRICE_INVALID_PRICING_BASIS')
    factor=_price_decimal(mod.get('multiplier'))
    if factor<=0:raise EngineError('PRICE_MULTIPLIER_INVALID')
    policy=_pricing_policy(docs);basis=None
    if kind=='supply_demand' and row['category']=='supply' and not event:
        lo,hi=map(_price_decimal,policy['supply_multiplier_range']);basis='RULE-SUPPLY-INVENTORY-01'
    elif kind=='black_new' and row['category'] in {'external_weapon','external_equipment'} and p.get('channel')=='black' and p['specification'].get('condition','new')=='new':
        lo,hi=map(_price_decimal,policy['black_new_multiplier_range']);basis='RULE-ECONOMY-01'
    elif kind=='external_used' and row['category']=='external_weapon' and p['specification'].get('condition')=='used':
        if row['item_id'].endswith('GRENADE'):lo=hi=Decimal('.7')
        elif row['item_id'].endswith('ROCKET'):lo=hi=Decimal('.5')
        elif row['item_id'].endswith('MISSILE'):lo=hi=Decimal('.2')
        else:lo,hi=map(_price_decimal,policy['external_used_weapon_range'])
        basis='RULE-ECONOMY-01'
    elif kind=='long_stay' and row['category']=='remote_lodging' and p.get('long_stay') is True:
        lo,hi=map(_price_decimal,_pricing_source_value(docs,'rules:runtime_rules.commander_sealed_runtime_policies.unsealed_price_generation_realism.lodging_anchor.long_stay_multiplier_range'));basis='RULE-UNSEALED-PRICE-REALISM-83630909'
    else:
        if row['category']=='own_equipment' and kind in {'external_used','age','secondhand'}:raise EngineError('PRICE_OWN_REFERENCE_NO_AGE_DISCOUNT')
        ev=_pricing_evidence(docs,event,row,p,'modifier');lo=hi=_price_decimal(ev['multiplier']);basis=ev['source_ref']
        if row['category']=='research':raise EngineError('PRICE_RESEARCH_REQUIRES_POLICY_UPDATE')
    if not lo<=factor<=hi:raise EngineError('PRICE_MODIFIER_OUT_OF_RANGE')
    return factor,{'kind':kind,'multiplier':_price_text(factor),'basis':basis,'evidence_id':event,'scope':copy.deepcopy(row.get('scope',{})),'included_in_base':False}

def calculate_price_quote(request,base=ROOT,documents=None):
    docs=documents or _pricing_documents(base)
    try:
        p=normalize_price_request(_pricing_request_reference(request,docs));row=resolve_price_authority(p,base,docs);lo,hi=_price_anchor_value(row,docs);policy=_pricing_policy(docs)
        qty=_price_decimal(p['quantity']);quantity_conversion=None
        if p['unit']!=row['unit']:
            conversion=next((c for c in policy.get('unit_conversions',[]) if c['from']==p['unit'] and c['to']==row['unit']),None)
            if not conversion:raise EngineError('PRICE_UNIT_MISMATCH_CONVERSION_EVIDENCE_REQUIRED')
            qty*=_price_decimal(conversion['factor']);quantity_conversion={**conversion,'input_quantity':p['quantity'],'anchor_quantity':_price_text(qty)}
            if 'quoted_unit_price' in p and p['quoted_unit_price'].get('unit')!=row['unit']:raise EngineError('PRICE_UNIT_PRICE_ANCHOR_UNIT_REQUIRED')
        if row['unit'] in {'件','架','箱','人','份','批','包','桶','罐','台','套','支','枚','发','具','门','座','单元','艘'} and qty!=qty.to_integral_value():raise EngineError('PRICE_INDIVISIBLE_QUANTITY')
        if row.get('quantity_ref') and qty>_price_decimal(_pricing_source_value(docs,row['quantity_ref'])):raise EngineError('PRICE_LISTING_QUANTITY_EXCEEDED')
        if row.get('unit_basis')=='duration unspecified':raise EngineError('PRICE_NEEDS_EVIDENCE_UNIT_NOT_SEALED')
        if row.get('source_record_ref'):
            current_record=_pricing_source_value(docs,row['source_record_ref'])
            for key,value in row.get('specification',{}).items():
                if key in current_record and current_record[key]!=value:raise EngineError('PRICE_NEEDS_EVIDENCE_CONFIGURATION_CHANGED')
        source_currency=row['currency'];unit_amount=lo;status='VALID';checks=[]
        if row['category']=='star_chart':
            if p.get('channel') not in {'legal','grey','black'}:raise EngineError('PRICE_STAR_CHANNEL_REQUIRED')
            if p.get('channel')=='legal' and p['currency'] not in {'gold','silver'} or p.get('channel') in {'grey','black'} and p['currency']!='grey':raise EngineError('PRICE_STAR_CHANNEL_CURRENCY_CONFLICT')
        if 'quoted_unit_price' in p:
            typed=p['quoted_unit_price']
            if typed.get('unit',row['unit'])!=row['unit']:raise EngineError('PRICE_UNIT_PRICE_UNIT_MISMATCH')
            unit_amount=_price_decimal(convert_money_exact(typed['amount'],typed['currency'],source_currency,base,False,docs))
            outside=not lo<=unit_amount<=hi
            if row['category']=='star_chart':
                if unit_amount>_price_decimal(policy['star_chart']['hard_max_grey']):raise EngineError('PRICE_STAR_HARD_CAP')
                if unit_amount>_price_decimal(policy['star_chart']['ordinary_max_grey']):_pricing_evidence(docs,p.get('special_evidence_id'),row,p,'star_chart_exception')
            elif outside:
                if row['price_kind']=='seller_quote' and p.get('special_evidence_id'):
                    ev=_pricing_evidence(docs,p['special_evidence_id'],row,p,'negotiated_price')
                    if ev.get('currency')!=row['currency'] or ev.get('unit')!=row['unit'] or unit_amount!=_price_decimal(ev.get('unit_amount')):raise EngineError('PRICE_NEGOTIATED_AMOUNT_MISMATCH')
                elif row['category']=='supply':
                    lower,upper=map(_price_decimal,policy['supply_multiplier_range'])
                    if not lo*lower<=unit_amount<=hi*upper:
                        ev=_pricing_evidence(docs,p.get('special_evidence_id'),row,p,'supply_exception')
                        if unit_amount!=_price_decimal(ev.get('unit_amount')):raise EngineError('PRICE_SUPPLY_EXCEPTION_AMOUNT_MISMATCH')
                elif row['price_kind'] in {'reference_range','provisional_estimate'} or row.get('anchor_role') in {'fixed_market_reference','market_guidance'}:
                    # Quoted deviation is pending a concrete seller/negotiation basis; do not change anchor.
                    if row['category']=='own_equipment':
                        ev=_pricing_evidence(docs,p.get('special_evidence_id'),row,p,'negotiated_price')
                        if unit_amount!=_price_decimal(ev.get('unit_amount')):raise EngineError('PRICE_NEGOTIATED_AMOUNT_MISMATCH')
                    else:status='PROVISIONAL';checks.append('reference_deviation_requires_concrete_transaction_basis')
                else:raise EngineError('PRICE_FIXED_OR_POLICY_MISMATCH')
        elif lo!=hi:status='PROVISIONAL';checks.append('range_without_agreed_unit_price')
        if row['price_kind']=='provisional_estimate':status='PROVISIONAL'
        seen=set();mods=[];factor=Decimal(1)
        for mod in p['modifiers']:
            f,m=_price_modifier(mod,row,p,docs,seen);factor*=f;mods.append(m)
        if 'quoted_unit_price' in p and p['modifiers']:raise EngineError('PRICE_INPUT_ASK_ALREADY_TOTALLED_USE_BASE_PLUS_MODIFIERS')
        unit_amount*=factor
        if row['category']=='star_chart':
            if unit_amount>_price_decimal(policy['star_chart']['hard_max_grey']):raise EngineError('PRICE_STAR_HARD_CAP')
            if unit_amount>_price_decimal(policy['star_chart']['ordinary_max_grey']):_pricing_evidence(docs,p.get('special_evidence_id'),row,p,'star_chart_exception')
        exact=unit_amount*qty;total=convert_money_exact(exact,source_currency,p['currency'],base,True,docs)
        if exact!=0 and _price_decimal(total)==0:raise EngineError('PRICE_ROUNDING_TO_ZERO_REQUIRES_EXPLICIT_HANDLING')
        if 'claimed_total' in p:
            claim=p['claimed_total']
            if claim['currency']!=p['currency'] or _price_decimal(claim['amount'])!=_price_decimal(total):raise EngineError('PRICE_TOTAL_MISMATCH')
        binding={'price_id':row['price_id'],'price_version':row['price_version'],'source_sha256':_price_digest(_pricing_source_value(docs,row['source_ref'])),'source_record_sha256':_price_digest(_pricing_source_value(docs,row['source_record_ref'])) if row.get('source_record_ref') else None,'specification':row['specification'],'included_components':row['included_components'],'anchor':[_price_text(lo),_price_text(hi)],'exchange_source':policy['grey_rate_ref'],'exchange_value':_price_text(_pricing_source_value(docs,policy['grey_rate_ref'])),'request':p,'game_time':docs['state']['game_time'],'modifiers':mods,'total':{'amount':total,'currency':p['currency']}}
        quote={'packet':'PRICE_QUOTE_V1','status':status,'quote_id':'QUOTE-'+_price_digest(binding)[:24],'binding_sha256':_price_digest(binding),'request':p,'price_id':row['price_id'],'item_id':row['item_id'],'specification':{k:p['specification'].get(k,v) for k,v in row['specification'].items()},'included_components':row['included_components'],'excluded_components':row.get('excluded_components',[]),'effective_conditions':row['effective_conditions'],'price_version':row['price_version'],'source_ref':row['source_ref'],'source_rule':row['source_rule'],'source_save_set_id':row['source_save_set_id'],'save_set_id':docs['manifest']['save_set_id'],'game_time':docs['state']['game_time'],'price_kind':row['price_kind'],'category':row['category'],'unit_price':{'amount':_price_text(unit_amount),'currency':source_currency},'range':{'min':_price_text(lo),'max':_price_text(hi),'currency':source_currency},'quantity':_price_text(qty),'unit':row['unit'],'quantity_conversion':quantity_conversion,'modifiers':mods,'total':{'amount':total,'currency':p['currency']},'checks':['source_exists','currency_complete','unit_matches','exact_arithmetic','scoped_policy']+checks,'conditions':copy.deepcopy(row['scope']),'binding':binding,'authorized':False}
        if status=='VALID':quote['display']=_pricing_render_template(quote)
        return quote
    except (EngineError,KeyError,ValueError,TypeError,StopIteration) as ex:
        msg=str(ex);return {'packet':'PRICE_QUOTE_V1','status':'NEEDS_EVIDENCE' if 'NEEDS_EVIDENCE' in msg or 'SOURCE_MISSING' in msg else 'OUT_OF_POLICY','errors':[msg],'authorized':False}

def _pricing_render_template(quote):
    if quote.get('status')!='VALID':raise EngineError('PRICE_RENDER_REQUIRES_VALID_QUOTE')
    money={'gold':'金币','silver':'银币','copper':'铜币','grey':'灰币'};unit=quote['unit_price'];total=quote['total']
    return f"单价{unit['amount']}{money[unit['currency']]}/{quote['unit']} × {quote['quantity']}{quote['unit']}；合计{total['amount']}{money[total['currency']]}。"

def validate_price_quote(quote,base=ROOT,documents=None,allow_rebind=False):
    docs=documents or _pricing_documents(base)
    if not isinstance(quote,dict) or quote.get('status')!='VALID':raise EngineError('PRICE_VALID_QUOTE_REQUIRED')
    recomputed=calculate_price_quote(quote.get('request'),base,docs)
    if recomputed.get('status')!='VALID':raise EngineError('PRICE_REVALIDATION_FAILED:'+str(recomputed.get('errors')))
    for k in ('quote_id','binding_sha256','price_id','price_version','item_id','specification','included_components','excluded_components','effective_conditions','source_ref','source_rule','price_kind','category','conditions','unit_price','quantity','unit','quantity_conversion','total','binding','display','game_time'):
        if quote.get(k)!=recomputed.get(k):raise EngineError('PRICE_STALE_OR_TAMPERED:'+k)
    if not allow_rebind and quote.get('save_set_id')!=docs['manifest']['save_set_id']:raise EngineError('PRICE_STALE_SAVESET')
    return recomputed

def price_quote_packet(base,request):
    with engine_lock(Path(base).resolve(),exclusive=False):
        ensure_source_ready(Path(base),allow_cache=True)
        if isinstance(request,dict) and 'revalidate' in request:
            try:return validate_price_quote(request['revalidate'],base)
            except EngineError as ex:return {'packet':'PRICE_QUOTE_V1','status':'STALE','errors':[str(ex)]}
        return calculate_price_quote(request,base)

def price_query_packet(base,request):
    with engine_lock(Path(base).resolve(),exclusive=False):
        ensure_source_ready(Path(base),allow_cache=True)
        if not isinstance(request,dict):raise EngineError('PRICE_QUERY_OBJECT_REQUIRED')
        docs=_pricing_documents(base)
        if request.get('source_ref'):
            request=_pricing_request_reference(request,docs)
        records=_price_records(docs);offset=int(request.get('offset',0));limit=int(request.get('limit',20))
        if offset<0 or not 1<=limit<=100:raise EngineError('PRICE_QUERY_PAGE_INVALID')
        rows=[]
        for pid,row in sorted(records.items()):
            if row.get('status')!='active' or row['price_kind']=='historical_price' or not _pricing_price_visible(row,docs,request.get('audience')):continue
            if request.get('item_id') and row['item_id']!=request['item_id'] or request.get('price_id') and pid!=request['price_id']:continue
            if request.get('region') and row['scope'].get('region') not in (None,request['region']):continue
            if request.get('search') and str(request['search']).casefold() not in (row['name']+' '+row['item_id']).casefold():continue
            if row['category'] not in {'local_service','remote_lodging','supply','research','research_policy','income_reference','wage','star_chart','ore','own_equipment','external_weapon','external_equipment','ship','uav_bulk','industrial_technology','generated_comparable','merchant_listing','commercial_asset'}:continue
            lo,hi=_price_anchor_value(row,docs)
            rows.append({k:row.get(k) for k in ('price_id','item_id','name','specification','scope','price_kind','currency','unit','price_version','source_ref','source_rule')} | {'range':[_price_text(lo),_price_text(hi)]})
        return {'packet':'PRICE_QUERY_V1','status':'COMPLETE','save_set_id':docs['manifest']['save_set_id'],'count':len(rows),'offset':offset,'prices':rows[offset:offset+limit],'more':len(rows)>offset+limit}

def _pricing_research_catalog_check(state):
    policy=_price_decimal(get_by_path(state,'commander_runtime_rules.parameters.research_data_uniform_price_gold'));program=get_by_path(state,PRICE_RESEARCH_PATH)
    for item,row in program['packages'].items():
        if row.get('status') in {'on_sale','active_nonexclusive_digital_backup'} and _price_decimal(row.get('price_gold_per_copy'))!=policy:raise EngineError('PRICE_RESEARCH_POLICY_CONFLICT:'+item)
    if _price_decimal(program['price_gold_per_copy'])!=policy:raise EngineError('PRICE_RESEARCH_PROGRAM_POLICY_CONFLICT')
    return True

def _pricing_confirmed_event(base,event_id,field):
    if not isinstance(event_id,str) or not event_id:raise EngineError('PRICE_CONFIRMED_SOURCE_EVENT_REQUIRED')
    event=history_lookup(Path(base),event_id=event_id)
    if not event or not isinstance(event.get(field),dict):raise EngineError('PRICE_CONFIRMED_TRANSACTION_NOT_FOUND')
    return event[field]

def _pricing_account_target(payload):
    account=payload.get('account','fleet')
    if account=='fleet':
        currency=(payload.get('quote') or {}).get('total',{}).get('currency')
        if currency not in {'gold','grey'}:raise EngineError('PRICE_FLEET_CURRENCY_MISMATCH')
        return 'state:summary.funds.'+currency
    if account=='xilu9_shop':return 'state:'+PRICE_SILVER_ACCOUNT+'.cash_silver'
    if account=='covert':
        if (payload.get('quote') or {}).get('total',{}).get('currency')!='grey':raise EngineError('PRICE_COVERT_GREY_REQUIRED')
        return 'state:account:covert:grey'
    raise EngineError('PRICE_ACCOUNT_UNSUPPORTED')

def _pricing_settlement_amounts(payload,docs):
    quote=validate_price_quote(payload.get('quote'),documents=docs)
    if quote['request']['transaction_type'] in {'estimate','reference'} or quote['category'] in {'research_policy','income_reference'}:raise EngineError('PRICE_ESTIMATE_IS_NOT_CASH')
    direction=payload.get('direction')
    if direction not in {'debit','credit'}:raise EngineError('PRICE_SETTLEMENT_DIRECTION_REQUIRED')
    if direction=='debit' and quote['request']['transaction_type'] not in {'purchase','service','wage'} or direction=='credit' and quote['request']['transaction_type'] not in {'sale','liquidation'}:raise EngineError('PRICE_TRANSACTION_DIRECTION_CONFLICT')
    target=_pricing_account_target(payload);currency=quote['total']['currency'];amount=_price_decimal(quote['total']['amount'])
    if payload.get('account','fleet')=='xilu9_shop' and currency!='silver':raise EngineError('PRICE_INDEPENDENT_ACCOUNT_CURRENCY_REQUIRED')
    if payload.get('account')=='covert' and currency!='grey':raise EngineError('PRICE_COVERT_GREY_REQUIRED')
    return quote,target,currency,amount

def _pricing_domain_settle(stage,state,payload):
    docs=_pricing_documents(stage);docs['state']=state;rt=_pricing_runtime(state);sid=payload.get('settlement_id')
    if not isinstance(sid,str) or not sid or '.' in sid:raise EngineError('PRICE_SETTLEMENT_ID_INVALID')
    if sid in rt['settlements']:raise EngineError('PRICE_SETTLEMENT_ALREADY_RECORDED')
    quote,target,currency,amount=_pricing_settlement_amounts(payload,docs)
    confirmed=_pricing_confirmed_event(stage,payload.get('source_event_id'),'confirmed_price_settlement')
    expected={'settlement_id':sid,'quote_id':quote['quote_id'],'binding_sha256':quote['binding_sha256'],'direction':payload['direction'],'account':payload.get('account','fleet')}
    if any(confirmed.get(k)!=v for k,v in expected.items()):raise EngineError('PRICE_CONFIRMED_SETTLEMENT_BINDING_MISMATCH')
    if confirmed.get('status')!='completed' or confirmed.get('cash_amount')!=quote['total']:raise EngineError('PRICE_COMPLETED_TRANSACTION_CASH_REQUIRED')
    if confirmed.get('asset_disposition_verified') is not True and quote['request']['transaction_type'] in {'purchase','sale','liquidation'}:raise EngineError('PRICE_EXISTING_ASSET_DISPOSITION_EVIDENCE_REQUIRED')
    delivery_changes=_settlement_inventory_delivery(state,quote,payload,confirmed) if state.get('engine_runtime',{}).get('account_registry_v1') else []
    sign=-1 if payload['direction']=='debit' else 1;entries=[]
    if payload.get('account','fleet')=='fleet':entries=[_finance_credit(state,currency,amount*sign)]
    elif payload.get('account')=='covert':_account_post(state,'covert','grey',_money_units_currency(amount*sign,'grey'))
    else:
        acct=get_by_path(state,PRICE_SILVER_ACCOUNT)
        if acct.get('fleet_accounting')!='independent_not_in_fleet_gold' or acct.get('currency')!='silver':raise EngineError('PRICE_ACCOUNT_OWNERSHIP_INVALID')
        before=_price_decimal(acct['cash_silver']);after=before+amount*sign;reserved=_price_decimal(acct['current_day_wages_reserved_silver'])
        if after<reserved:raise EngineError('PRICE_INDEPENDENT_ACCOUNT_INSUFFICIENT_FREE_CASH')
        if state.get('engine_runtime',{}).get('account_registry_v1'):
            delta=amount*sign*100
            if delta!=delta.to_integral_value():raise EngineError('ACCOUNT_COPPER_QUANTUM')
            _account_post(state,'shop','copper',int(delta))
        else:
            acct['cash_silver']=float(after);acct['free_operating_cash_silver']=float(after-reserved)
    receipt={**expected,'command_id':payload['command_id'],'quote':copy.deepcopy(quote),'amount':quote['total'],'source_event_id':payload['source_event_id'],'authorization_ref':payload['authorization_ref'],'game_time':state['game_time'],'inventory_delivery':copy.deepcopy(payload.get('delivery'))};rt['settlements'][sid]=receipt
    return {'kind':payload['kind'],'settlement':receipt,'finance_entries':entries,'changes':delivery_changes+[{'target':target,'action':'verified_price_settlement'},{'target':'state:engine_runtime.pricing_runtime.settlements.'+sid,'action':'record_settlement'}]+([{'target':'state:'+v['path'],'action':'derive_account_view'} for v in _account_record(state,'shop').get('legacy_read_only_views',[])] if currency=='silver' and state.get('engine_runtime',{}).get('account_registry_v1') else [])}

def _pricing_sync_price_views(docs):
    records=_price_records(docs)
    for row in _pricing_runtime(docs['state'])['mirrors']:
        lo,hi=_price_anchor_value(records[row['price_id']],docs)
        if lo!=hi:raise EngineError('PRICE_SCALAR_MIRROR_REQUIRES_SINGLE_VALUE')
        _pricing_set_value(docs,row['path'],float(lo) if lo!=lo.to_integral_value() else int(lo))

def _pricing_update_policy(stage,state,payload):
    docs=_pricing_documents(stage);docs['state']=state;policyref=_pricing_policy(docs)['research_policy_ref'];value=payload.get('unit_price')
    if payload.get('policy_ref')!=policyref or not isinstance(value,dict) or value.get('currency')!='gold':raise EngineError('PRICE_POLICY_UNSUPPORTED')
    new=_price_decimal(value.get('amount'))
    if new<=0 or Decimal(_money_units_currency(new,'gold'))/MONEY_SCALE!=new:raise EngineError('PRICE_POLICY_AMOUNT_INVALID')
    confirmed=_pricing_confirmed_event(stage,payload.get('source_event_id'),'confirmed_price_policy');old=_price_decimal(_pricing_source_value(docs,policyref))
    expected={'policy_ref':policyref,'old_amount':_price_text(old),'new_amount':_price_text(new),'currency':'gold','authorization_ref':payload['authorization_ref']}
    if any(confirmed.get(k)!=v for k,v in expected.items()):raise EngineError('PRICE_POLICY_CONFIRMED_BINDING_MISMATCH')
    _pricing_set_value(docs,policyref,float(new));program=get_by_path(state,PRICE_RESEARCH_PATH)
    for row in program['packages'].values():
        if row.get('status') in {'on_sale','active_nonexclusive_digital_backup'}:row['price_gold_per_copy']=float(new)
    _pricing_runtime(state)['policy_updates'].append({**expected,'command_id':payload['command_id'],'source_event_id':payload['source_event_id'],'game_time':state['game_time']})
    _pricing_sync_price_views(docs)
    return {'kind':'price_policy_update','changes':[{'target':policyref,'action':'verified_price_policy'},{'target':'state:'+PRICE_RESEARCH_PATH+'.packages','action':'derive_current_catalog_prices'},{'target':'state:engine_runtime.pricing_runtime.policy_updates','action':'record_policy_version'}]+[{'target':x['path'],'action':'derive_price_view'} for x in _pricing_runtime(state)['mirrors'] if x['price_id']=='PRICE-RESEARCH-POLICY']}

def _pricing_register_evidence(stage,state,payload):
    docs=_pricing_documents(stage);docs['state']=state;ev=copy.deepcopy(payload.get('evidence'));eid=payload.get('evidence_id')
    if not isinstance(ev,dict) or not isinstance(eid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}',eid):raise EngineError('PRICE_EVIDENCE_INVALID')
    confirmed=_pricing_confirmed_event(stage,payload.get('source_event_id'),'confirmed_price_evidence')
    if confirmed!=ev or ev.get('evidence_id')!=eid:raise EngineError('PRICE_EVIDENCE_CONFIRMED_BINDING_MISMATCH')
    if ev.get('purpose')=='modifier' and not ev.get('factor_id'):raise EngineError('PRICE_MODIFIER_FACTOR_ID_REQUIRED')
    if ev.get('purpose') not in {'modifier','star_chart_exception','supply_exception','negotiated_price'} or ev.get('status')!='active':raise EngineError('PRICE_EVIDENCE_PURPOSE_INVALID')
    if not ev.get('item_id') and not ev.get('category') or not isinstance(ev.get('scope'),dict) or not ev.get('explanation'):raise EngineError('PRICE_EVIDENCE_SCOPE_BASIS_REQUIRED')
    rid=ev.get('rule_id')
    if rid not in {'RULE-SUPPLY-INVENTORY-01','RULE-STAR-CHART-PRICE-01','RULE-EQUIPMENT-MARKET-REFERENCE-01','RULE-SHIPMARKET-01','RULE-ECONOMY-01','RULE-UNSEALED-PRICE-REALISM-83630909'}:raise EngineError('PRICE_EXCEPTION_EXISTING_RULE_REQUIRED')
    if _price_digest(_pricing_source_value(docs,ev['source_ref']))!=ev.get('source_sha256'):raise EngineError('PRICE_EVIDENCE_SOURCE_MISMATCH')
    rt=_pricing_runtime(state)
    if eid in rt['evidence']:raise EngineError('PRICE_EVIDENCE_ID_EXISTS')
    rt['evidence'][eid]=ev
    return {'kind':'price_evidence_register','changes':[{'target':'state:engine_runtime.pricing_runtime.evidence.'+eid,'action':'register_verified_existing_rule_evidence'}]}

def _pricing_register_comparable(docs,record,base=None):
    if not isinstance(record,dict) or not re.fullmatch(r'PRICE-[A-Za-z0-9_-]{1,100}',str(record.get('price_id',''))):raise EngineError('PRICE_NEW_RECORD_INVALID')
    records=_price_records(docs);pid=record['price_id'];item=record.get('item_id')
    if pid in records or any(r['item_id']==item and r['status']=='active' for r in records.values()):raise EngineError('PRICE_EXISTING_AUTHORITY_CANNOT_BE_OVERWRITTEN')
    parent=records.get(record.get('comparable_price_id'))
    if parent is None and record.get('external_source_event_id'):
        return _pricing_register_external_reference(docs,record,base)
    if not parent or parent['category'] in {'research','research_policy','income_reference','historical'} or not item or record.get('specification')!=parent['specification'] or record.get('scope')!=parent['scope'] or not record.get('comparability_basis'):raise EngineError('PRICE_SAME_SPEC_COMPARABLE_REQUIRED')
    row=copy.deepcopy(parent);row.update({'price_id':pid,'item_id':item,'name':record.get('name',item),'comparable_price_id':parent['price_id'],'comparability_basis':record['comparability_basis'],'price_version':1})
    _pricing_runtime(docs['state'])['registered_prices'][pid]=row
    return row

def validate_economic_change(docs,effects):
    if not isinstance(effects,list):raise EngineError('PRICE_ECONOMIC_EFFECTS_LIST_REQUIRED')
    covered=set()
    for effect in effects:
        if not isinstance(effect,dict) or effect.get('component','total') not in {'total','unit_price'}:raise EngineError('PRICE_ECONOMIC_EFFECT_INVALID')
        quote=validate_price_quote(effect.get('quote'),documents=docs,allow_rebind=True);ref=effect.get('target');amount=quote[effect.get('component','total')]
        if effect.get('currency')!=amount['currency'] or _price_decimal(_pricing_source_value(docs,ref))!=_price_decimal(amount['amount']):raise EngineError('PRICE_ECONOMIC_EFFECT_AMOUNT_MISMATCH')
        if ref.startswith(('state:summary.funds','state:engine_runtime.finance_runtime','state:'+PRICE_SILVER_ACCOUNT)):raise EngineError('PRICE_CASH_REQUIRES_DOMAIN_SETTLEMENT')
        covered.add(ref)
    return covered

def _pricing_changed_values(old,new,path='state:'):
    rows=[]
    if isinstance(new,dict):
        for key,val in new.items():
            ref=path+('.' if path not in {'state:','tasks:','rules:','catalog:'} else '')+str(key)
            prior=old.get(key) if isinstance(old,dict) else None
            if prior==val:continue
            if ref.startswith(('state:engine_runtime.pricing_runtime','state:engine_runtime.domain_command_runtime','state:engine_runtime.domain_authorization_ledger','state:engine_runtime.finance_runtime','state:standing_authorizations','state:summary.funds','state:'+PRICE_SILVER_ACCOUNT)) or 'legacy_price_record' in ref:continue
            if key=='price_version' or '.economic_fact_refs' in ref:continue
            if ref in {'state:world_state_overrides.current_handoff_snapshot.xilu9.shop.cash_silver','state:world_state_overrides.current_handoff_snapshot.xilu9.shop.free_cash_silver'}:continue
            if isinstance(val,(int,float,str)) and not isinstance(val,bool) and (re.search(r'price|wage|cost|fee|valuation|estimate|bounty|compensation',key,re.I) or prior is None and re.search(r'^(cash|balance|funds|revenue|potential_income|net_proceeds)_(gold|grey|silver|copper)$',key,re.I)):
                try:_price_decimal(val);rows.append(ref)
                except EngineError:pass
            else:rows.extend(_pricing_changed_values(prior,val,ref))
    elif isinstance(new,list):
        for i,val in enumerate(new):rows.extend(_pricing_changed_values(old[i] if isinstance(old,list) and i<len(old) else None,val,path+f'[{i}]'))
    return rows

def pricing_integrity_report(base=ROOT,documents=None):
    docs=documents or _pricing_documents(base);errors=[];records={}
    try:
        _pricing_policy(docs);records=_price_records(docs);rt=_pricing_runtime(docs['state']);_pricing_research_catalog_check(docs['state'])
        for pid,row in records.items():
            try:
                if pid!=row.get('price_id') or row.get('price_kind') not in PRICE_KINDS or row.get('status') not in PRICE_STATUS or row.get('currency') not in PRICE_CURRENCY or not row.get('unit'):raise EngineError('PRICE_RECORD_SCHEMA_INVALID')
                if row.get('status')=='active':_price_anchor_value(row,docs)
            except Exception as ex:errors.append(pid+':'+str(ex))
        for alias in rt['aliases']:
            obj=_pricing_source_value(docs,alias['path'])
            if obj.get('price_authority_ref')!=alias['price_id'] or alias['legacy_field'] in obj or obj['legacy_price_record'].get('status')!='superseded':errors.append('PRICE_ALIAS_CONFLICT:'+alias['path'])
        for view in rt['mirrors']:
            lo,hi=_price_anchor_value(records[view['price_id']],docs)
            if lo!=hi or _price_decimal(_pricing_source_value(docs,view['path']))!=lo:errors.append('PRICE_MIRROR_CONFLICT:'+view['path'])
    except Exception as ex:errors.append(str(ex))
    return {'status':'FAIL' if errors else 'PASS','errors':errors,'record_count':len(records),'research_count':sum(r.get('category')=='research' for r in records.values()),'pending_candidates':sum(r['classification']=='pending_review' for r in (docs['state'].get('engine_runtime',{}).get('pricing_runtime',{}).get('legacy_candidates',[])))}

def pricing_transaction_report(base,parent):
    docs=_pricing_documents(base);old=_pricing_documents(parent);errors=[];rt=_pricing_runtime(docs['state']);previous=old['state'].get('engine_runtime',{}).get('pricing_runtime')
    if previous and docs['catalog'].get('price_registry_v1')!=old['catalog'].get('price_registry_v1'):errors.append('PRICE_STATIC_REGISTRY_REQUIRES_FORMAL_MIGRATION')
    if previous and docs['rules']['runtime_rules'].get('pricing_contract')!=old['rules']['runtime_rules'].get('pricing_contract'):errors.append('PRICE_EXECUTABLE_POLICY_REQUIRES_FORMAL_MIGRATION')
    if not previous:
        for key in ('inventories','asset_ledger_v1','standing_authorizations','task_allocations','entity_registry','entity_lifecycle'):
            if docs['state'].get(key)!=old['state'].get(key):errors.append('PRICE_MIGRATION_PROTECTED_CHANGED:'+key)
        if docs['state']['game_time']!=old['state']['game_time'] or docs['state']['engine_runtime']['finance_runtime']!=old['state']['engine_runtime']['finance_runtime'] or get_by_path(docs['state'],PRICE_SILVER_ACCOUNT)!=get_by_path(old['state'],PRICE_SILVER_ACCOUNT):errors.append('PRICE_MIGRATION_TIME_OR_CASH_CHANGED')
        for key,val in old['state']['engine_runtime'].items():
            if re.search(r'seed|random|hazard|long_horizon|last_evaluated',key) and docs['state']['engine_runtime'].get(key)!=val:errors.append('PRICE_MIGRATION_RANDOM_CHANGED:'+key)
        if read_json(Path(base)/'tasks.json')!=read_json(Path(parent)/'tasks.json'):errors.append('PRICE_MIGRATION_TASKS_CHANGED')
        return {'status':'FAIL' if errors else 'PASS','errors':errors,'migration':True}
    for sid,row in previous['settlements'].items():
        if rt['settlements'].get(sid)!=row:errors.append('PRICE_SETTLEMENT_RECEIPT_IMMUTABLE:'+sid)
    fresh=[r for sid,r in rt['settlements'].items() if sid not in previous['settlements']]
    expected={'gold':0,'grey':0};independent={}
    for receipt in fresh:
        try:
            # Receipt was quoted at the parent snapshot; final SAVESET is deliberately different.
            quote=validate_price_quote(receipt['quote'],documents=old)
            confirmed=_pricing_confirmed_event(base,receipt['source_event_id'],'confirmed_price_settlement')
            if confirmed.get('quote_id')!=quote['quote_id'] or confirmed.get('binding_sha256')!=quote['binding_sha256'] or confirmed.get('status')!='completed' or confirmed.get('cash_amount')!=quote['total']:raise EngineError('PRICE_RECEIPT_TRANSACTION_BINDING_INVALID')
            if receipt.get('account') not in {'fleet','xilu9_shop','covert'} or receipt.get('direction') not in {'debit','credit'}:raise EngineError('PRICE_RECEIPT_ACCOUNT_OR_DIRECTION_INVALID')
            if any(confirmed.get(k)!=receipt.get(k) for k in ('settlement_id','account','direction')):raise EngineError('PRICE_RECEIPT_CONFIRMED_ACCOUNT_MISMATCH')
            if receipt['account']=='covert' and receipt['amount']['currency']!='grey':raise EngineError('PRICE_COVERT_GREY_REQUIRED')
            _,proof_events,_=read_history_view(Path(base)/'events.jsonl')
            matching=[ev for ev in _domain_evidence_events(proof_events) if ev.get('command_id')==receipt['command_id'] and ev.get('subtype')=='domain_command_commit' and (ev.get('domain_effect') or {}).get('settlement')==receipt]
            if len(matching)!=1 or (matching[0].get('domain_effect') or {}).get('settlement')!=receipt or (matching[0].get('authorization') or {}).get('status')!='verified':raise EngineError('PRICE_RECEIPT_VERIFIED_COMMAND_EVENT_REQUIRED')
            if receipt.get('amount')!=quote['total'] or receipt.get('game_time')!=old['state']['game_time']:raise EngineError('PRICE_RECEIPT_AMOUNT_MISMATCH')
            kind='settle_price';grant=(old['state'].get('standing_authorizations',{}).get(receipt['authorization_ref'],{}).get('machine_grant') or {})
            if kind not in grant.get('action_kinds',[]) and 'adjust_funds' not in grant.get('action_kinds',[]):
                proof=matching[0].get('authorization') or {};intent=proof.get('user_intent') or {}
                if proof.get('authority')!='host_intent' or proof.get('status')!='verified' or proof.get('decision_sha256')!=_repair_digest(intent) or intent.get('decision')!='approved' or intent.get('parent_save_set_id')!=old['manifest']['save_set_id'] or intent.get('command',{}).get('command_id')!=receipt['command_id'] or intent.get('evidence_ref')!=proof.get('evidence_ref'):raise EngineError('PRICE_RECEIPT_GRANT_INVALID')
            delta=_price_decimal(receipt['amount']['amount'])*(-1 if receipt['direction']=='debit' else 1)
            if receipt['account']=='fleet':expected[receipt['amount']['currency']]+=_money_units_currency(delta,receipt['amount']['currency'])
            else:
                key=('shop','copper') if receipt['account']=='xilu9_shop' else ('covert','grey')
                units=delta*100 if key[1]=='copper' else _money_units_currency(delta,'grey')
                if units!=int(units):raise EngineError('PRICE_INDEPENDENT_EXACT_UNITS')
                independent[key]=independent.get(key,0)+int(units)
        except Exception as ex:errors.append(str(ex))
    # Ordinary scheduler settlements remain supported by typed existing event finance records.
    _,events,_=read_history_view(Path(base)/'events.jsonl');events=_domain_evidence_events(events);_,old_events,_=read_history_view(Path(parent)/'events.jsonl');old_ids={ev.get('event_id') for ev in old_events}
    other={'gold':0,'grey':0};effects=[]
    for ev in events:
        if ev.get('event_id') in old_ids:continue
        effects.extend(ev.get('economic_effects') or [])
        finance=ev.get('finance') or {}
        if ev.get('domain_kind') in {'settle_price','adjust_funds'} and (ev.get('domain_effect') or {}).get('settlement'):continue
        if finance:
            for cur in other:other[cur]+=_money_units_currency(finance.get(cur,0),cur)
    before=_finance_runtime(old['state']);after=_finance_runtime(docs['state'])
    for cur in expected:
        if after['funds_units'][cur]-before['funds_units'][cur]!=expected[cur]+other[cur]:errors.append('PRICE_CASH_DELTA_WITHOUT_MATCHING_SETTLEMENT:'+cur)
    old_cash_rows=old['state'].get('engine_runtime',{}).get('account_registry_v1',{}).get('ledger',[])
    new_cash_rows=docs['state'].get('engine_runtime',{}).get('account_registry_v1',{}).get('ledger',[])
    new_events=[ev for ev in events if ev.get('event_id') not in old_ids]
    business_proofs={};business_covered=set()
    try:business_proofs,business_covered=_business_settlement_proofs(base,parent,old['state'],docs['state'],new_events)
    except Exception as ex:errors.append(str(ex))
    for row in new_cash_rows[len(old_cash_rows):]:
        if row['account_id']=='fleet':continue
        key=(row['account_id'],row['currency']);verified=False;already_priced=False
        if business_proofs.get(row['entry_id'])==row:verified=True
        for ev in new_events:
            if ev.get('command_id')!=row['command_id'] or ev.get('subtype')!='domain_command_commit' or ev.get('authorization',{}).get('status')!='verified':continue
            effect=ev.get('domain_effect') or {}
            if ev.get('domain_kind')=='account_transfer' and effect.get('income_created') is False and row in effect.get('cash_receipts',[]):verified=True
            elif ev.get('domain_kind')=='game_session':
                game=effect.get('session') or {}
                if game.get('status')=='settled' and (game.get('account_id'),game.get('currency'))==key and game.get('delta_units')==row['delta_units']:verified=True
            elif ev.get('domain_kind') in ('settle_price','adjust_funds'):
                receipt=effect.get('settlement')
                if receipt in fresh:
                    aid='shop' if receipt['account']=='xilu9_shop' else receipt['account']
                    currency='copper' if receipt['amount']['currency']=='silver' else receipt['amount']['currency']
                    delta=_price_decimal(receipt['amount']['amount'])*(-1 if receipt['direction']=='debit' else 1)
                    units=int(delta*100) if currency=='copper' else _money_units_currency(delta,currency)
                    if (aid,currency)==key and units==row['delta_units']:verified=True;already_priced=True
        if not verified:errors.append('PRICE_INDEPENDENT_LEDGER_WITHOUT_TYPED_RECEIPT:'+row['entry_id'])
        elif not already_priced:independent[key]=independent.get(key,0)+row['delta_units']
    old_registry=old['state'].get('engine_runtime',{}).get('account_registry_v1',{}).get('accounts',{})
    for aid,account in docs['state'].get('engine_runtime',{}).get('account_registry_v1',{}).get('accounts',{}).items():
        if aid=='fleet':continue
        for currency in account['currencies']:
            try:
                if currency in old_registry.get(aid,{}).get('currencies',[]):prior_units=_account_units(old['state'],aid,currency)
                else:
                    migrations=docs['state']['engine_runtime']['account_registry_v1'].get('opening_migrations_v1453',[])
                    proof=next((p for p in migrations if p.get('account_id')==aid and p.get('currency')==currency),None)
                    if not proof or proof.get('kind')!='accepted_existing_balance_not_income' or proof.get('source_save_set_id')!=old['manifest']['save_set_id']:raise EngineError('PRICE_NEW_ACCOUNT_OPENING_UNVERIFIED')
                    value=get_by_path(old['state'],proof['source_ref'][6:]);prior_units=value*proof['units_per_currency']//proof['source_units_per_currency']
                    if prior_units*proof['source_units_per_currency']!=value*proof['units_per_currency'] or str(prior_units)!=proof['integer_units']:raise EngineError('PRICE_OPENING_SCALE_MISMATCH')
                if _account_units(docs['state'],aid,currency)-prior_units!=independent.get((aid,currency),0):errors.append('PRICE_INDEPENDENT_CASH_DELTA_MISMATCH:'+aid+':'+currency)
            except Exception as ex:errors.append(str(ex))
    old_scenes=old['state'].get('engine_runtime',{}).get('scene_registry_v1',{}).get('records',{})
    for sid,scene in docs['state'].get('engine_runtime',{}).get('scene_registry_v1',{}).get('records',{}).items():
        old_refs=old_scenes.get(sid,{}).get('economic_fact_refs',{})
        for fid,ref in scene.get('economic_fact_refs',{}).items():
            try:
                if fid in old_refs:
                    if ref!=old_refs[fid]:raise EngineError('PRICE_HISTORICAL_SCENE_QUOTE_IMMUTABLE')
                else:validate_price_quote(ref['quote'],documents=docs,allow_rebind=True)
            except Exception as ex:errors.append(str(ex))
    updates=rt['policy_updates'][len(previous['policy_updates']):];covered=set()
    try:covered=validate_economic_change(docs,effects)
    except Exception as ex:errors.append(str(ex))
    covered.update(business_covered)
    changes=_pricing_changed_values(old['state'],docs['state'])
    for path in changes:
        policy_changed=updates and (path==_pricing_policy(docs)['research_policy_ref'] or path.startswith('state:'+PRICE_RESEARCH_PATH+'.') or any(path==m['path'] and m['price_id']=='PRICE-RESEARCH-POLICY' for m in rt['mirrors']))
        if path not in covered and not policy_changed:errors.append('PRICE_NEW_ECONOMIC_FACT_REQUIRES_QUOTE:'+path)
    for update in updates:
        try:
            confirmed=_pricing_confirmed_event(base,update['source_event_id'],'confirmed_price_policy')
            for k in ('policy_ref','old_amount','new_amount','currency','authorization_ref'):
                if confirmed.get(k)!=update.get(k):raise EngineError('PRICE_POLICY_CHANGE_BINDING_INVALID')
        except Exception as ex:errors.append(str(ex))
    return {'status':'FAIL' if errors else 'PASS','errors':errors,'new_settlements':len(fresh)}

def _pricing_scene_refs(base,payload):
    refs=payload.get('economic_fact_refs',{});facts=payload.get('facts',[])
    if not isinstance(refs,dict):raise EngineError('PRICE_SCENE_REFERENCE_TABLE_INVALID')
    out={};ids={f.get('fact_id') for f in facts if isinstance(f,dict)}
    if any(fid not in ids for fid in refs):raise EngineError('PRICE_SCENE_ORPHAN_REFERENCE')
    for fact in facts:
        fid=fact.get('fact_id')
        if fid in refs:
            quote=validate_price_quote(refs[fid],base);text=_pricing_render_template(quote);fact['value']=text;out[fid]={'quote_id':quote['quote_id'],'quote':quote,'render_sha256':_price_digest(text)}
        elif re.search(r'\d+(?:\.\d+)?\s*(?:金币|灰币|银币|铜币)',str(fact.get('value',''))):raise EngineError('PRICE_SCENE_STRUCTURED_QUOTE_REQUIRED')
    return out

def _pricing_scene_integrity(state):
    errors=[]
    for sid,rec in (state.get('engine_runtime',{}).get('scene_registry_v1',{}).get('records',{})).items():
        for fid,ref in rec.get('economic_fact_refs',{}).items():
            quote=ref.get('quote',{});fact=rec.get('facts',{}).get(fid)
            try:
                if not fact or ref.get('quote_id')!=quote.get('quote_id') or fact.get('value')!=_pricing_render_template(quote) or _price_digest(fact['value'])!=ref.get('render_sha256'):raise EngineError('PRICE_SCENE_REFERENCE_OR_RENDER_CONFLICT')
                if _price_digest(quote.get('binding'))!=quote.get('binding_sha256'):raise EngineError('PRICE_SCENE_QUOTE_CONTENT_CONFLICT')
            except Exception as ex:errors.append(sid+':'+fid+':'+str(ex))
    return errors

def _pricing_preserved_gap(state):
    gap=state.get('engine_runtime',{}).get('historical_runtime_gap',{})
    er=state.get('engine_runtime',{})
    return gap.get('schema')=='INHERITED_RUNTIME_GAP_V1' and gap.get('source_save_set_id')=='SAVESET-V14.20-9dae2d93810259aa' and gap.get('game_time')=='8363-09-18T12:28:00' and state.get('game_time')==gap['game_time'] and er.get('last_evaluated_game_time')==gap.get('last_evaluated_game_time')=='8363-09-12T10:06:00' and gap.get('hazard_clocks_sha256')==_price_digest(er.get('long_horizon',{}).get('hazard_clocks'))=='ab91202552e971f7203c66402ec5f71cff257f7a8bd75232688ca416ddb3ae12'

PRICING_INHERITED_ERRORS=['AUDIT_REGISTRY_SCHEMA: active contains terminal audit AUDIT-V1420-CURRENT-RECONCILIATION', 'CURRENT_STATE_TEMPORAL_HYGIENE: {"required": true, "minimum_version": "V9.54", "count": 1, "rows": [{"path": "STATE.world_state_overrides.mining_and_industry.jinchuan_resource_network_current.next_settlement_at", "value": "8363-09-13T08:20:00"}]}', "RUNTIME_ARCHITECTURE: ['STATE.engine_runtime.last_evaluated_game_time must equal STATE.game_time', 'hazard clock HZ-GLOBAL-SMALL-CONFLICT last_evaluated must equal STATE.game_time', 'hazard clock HZ-MAJOR-NATION-INSTABILITY last_evaluated must equal STATE.game_time', 'hazard clock HZ-MEDIUM-NATION-INSTABILITY last_evaluated must equal STATE.game_time', 'hazard clock HZ-SMALL-NATION-INSTABILITY last_evaluated must equal STATE.game_time', 'hazard clock HZ-DEEP-SPACE-ENCOUNTER last_evaluated must equal STATE.game_time', 'hazard clock HZ-PIRACY-CRIME-CONTACT last_evaluated must equal STATE.game_time', 'hazard clock HZ-SALVAGE-DISCOVERY last_evaluated must equal STATE.game_time', 'hazard clock HZ-SCIENTIFIC-ANOMALY last_evaluated must equal STATE.game_time', 'hazard clock HZ-MARKET-EVENT last_evaluated must equal STATE.game_time', 'hazard clock HZ-MINING-EVENT last_evaluated must equal STATE.game_time', 'hazard clock HZ-INTELLIGENCE-OPPORTUNITY last_evaluated must equal STATE.game_time', 'hazard clock HZ-RARE-MAJOR-EVENT last_evaluated must equal STATE.game_time']", 'SHADOW_LOCATION_PARTITION: [["as_of", "8363-09-12T10:06:00", "8363-09-18T12:28:00"]]']


def _pricing_adjust_payload(payload):
    q=payload.get('quote')
    if not isinstance(q,dict):raise EngineError('PRICE_ADJUST_FUNDS_REQUIRES_QUOTE')
    currency=q.get('total',{}).get('currency')
    if currency not in ('gold','grey'):raise EngineError('PRICE_ADJUST_FUNDS_CURRENCY_INVALID')
    for cur in ('gold','grey'):
        expected=-_price_decimal(q['total']['amount']) if cur==currency else Decimal(0)
        if _price_decimal(payload.get(cur+'_delta',0))!=expected:raise EngineError('PRICE_ADJUST_FUNDS_AMOUNT_MISMATCH')
    if not payload.get('settlement_id') or not payload.get('source_event_id'):raise EngineError('PRICE_ADJUST_FUNDS_CONFIRMED_TRANSACTION_REQUIRED')
    p=copy.deepcopy(payload);p['direction']='debit';p['account']='fleet';return p

def _pricing_apply_patch(stage,patch_path,implementation):
    patch=strict_json_load(patch_path);docs=_pricing_documents(stage);before=copy.deepcopy(docs);tasks_before=read_json(stage/'tasks.json');rt=_pricing_runtime(docs['state'])
    protected=['state:summary.funds','state:engine_runtime.finance_runtime','state:standing_authorizations','state:engine_runtime.domain_authorization_ledger','state:engine_runtime.pricing_runtime','state:engine_runtime.domain_command_runtime','state:'+PRICE_SILVER_ACCOUNT,'state:world_state_overrides.current_handoff_snapshot.xilu9.shop.cash_silver','state:world_state_overrides.current_handoff_snapshot.xilu9.shop.free_cash_silver']+[r['value_ref'] for r in _price_records(docs).values() if r.get('value_ref','').startswith('state:')]+[r['path'] for r in rt['mirrors']]
    for op in patch.get('operations',[]):
        if not isinstance(op,dict) or op.get('op')=='history_append':continue
        head=str(op.get('file','')).replace('.json','');path=str(op.get('path',''));ref=head+':'+path.strip('/').replace('/','.')
        if head in ('rules','catalog','manifest'):raise EngineError('PRICE_SOURCE_PATCH_REQUIRES_FORMAL_UPDATE')
        if any(ref==p or ref.startswith(p+'.') or p.startswith(ref+'.') or ref==head+':' for p in protected):raise EngineError('PRICE_AUTHORITY_OR_CASH_PATCH_FORBIDDEN:'+ref)
    backup={fn:(stage/fn).read_bytes() for fn in COMPONENT_FILES}
    try:
        registrations=patch.get('price_registrations',[])
        if registrations and not stage.name.startswith('.stage_session_'):raise EngineError('PRICE_AUTOGENERATION_EXISTING_SESSION_ONLY')
        for row in registrations:_pricing_register_comparable(docs,row,stage)
        if registrations:_write_authority_json(stage/'state.json',docs['state'])
        effects=copy.deepcopy(patch.get('economic_effects',[]))
        for effect in effects:
            if 'quote_request' in effect:
                effect['quote']=calculate_price_quote(effect.pop('quote_request'),documents=docs)
                if effect['quote'].get('status')!='VALID':raise EngineError('PRICE_SESSION_QUOTE_REQUEST_INVALID')
        generated=None
        normalized=copy.deepcopy(patch)
        if effects or registrations:
            generated=_event_v2_normalize({'event_id':'PRICE-SESSION-'+uuid.uuid4().hex,'game_time':docs['state']['game_time'],'type':'system','subtype':'price_session_evidence','summary':'既有缺价授权登记及结构化价格校验','source':'GAME ENGINE pricing_domain','authority_files':['state.json'],'economic_effects':effects,'changes':[{'target':x['target'],'action':'verified_economic_fact'} for x in effects]+([{'target':'state:engine_runtime.pricing_runtime.registered_prices','action':'reuse_evidenced_comparable'}] if registrations else [])})
            normalized['operations'].append({'op':'history_append','event':generated})
        temp=stage/'.pricing_validated_patch.json';temp.write_text(json.dumps(normalized,ensure_ascii=False,separators=(',',':'))+'\n')
        try:result=implementation(stage,temp)
        finally:temp.unlink(missing_ok=True)
        after=_pricing_documents(stage);covered=validate_economic_change(after,effects)
        for path in _pricing_changed_values(before['state'],after['state'])+_pricing_changed_values(tasks_before,read_json(stage/'tasks.json'),'tasks:'):
            if path not in covered:raise EngineError('PRICE_NEW_ECONOMIC_FACT_REQUIRES_QUOTE:'+path)
        report=pricing_integrity_report(stage,after)
        if report['status']!='PASS':raise EngineError('PRICE_PATCH_INTEGRITY:'+str(report['errors']))
        return result
    except Exception:
        for fn,data in backup.items():(stage/fn).write_bytes(data)
        raise

def _pricing_finish_checks(base,out,parent_snapshot):
    state=read_json(Path(base)/'state.json');active=bool(state.get('engine_runtime',{}).get('pricing_runtime'));manifest=read_json(Path(base)/'manifest.json')
    if active:
        integrity=pricing_integrity_report(base);out['pricing_integrity']=integrity;out['errors'].extend('PRICING:'+e for e in integrity['errors']);out['errors'].extend('PRICING:'+e for e in _pricing_scene_integrity(state))
        if parent_snapshot and parent_snapshot.get('dir'):
            trans=pricing_transaction_report(base,Path(parent_snapshot['dir']));out['pricing_transaction']=trans;out['errors'].extend('PRICING:'+e for e in trans['errors'])
        if _pricing_preserved_gap(state):
            exact=next(e for e in PRICING_INHERITED_ERRORS if e.startswith('RUNTIME_ARCHITECTURE:'))
            if exact in out['errors']:out['errors'].remove(exact);out.setdefault('warnings',[]).append('INHERITED_RUNTIME_CLOCK_GAP_PRESERVED_NO_REPLAY')
    elif manifest.get('save_set_id')=='SAVESET-V14.20-9dae2d93810259aa' and manifest.get('authority_bundle_sha256')=='9dae2d93810259aad5341859ba98048dea95ffdc6c1e37faa41bebcc3f347320':
        # Candidate upgrade preflight on exactly the immutable uploaded parent only.
        for error in PRICING_INHERITED_ERRORS:
            if error in out['errors']:out['errors'].remove(error);out.setdefault('warnings',[]).append('INHERITED_V1420_PARENT_DEFECT:'+error)


def _pricing_register_external_reference(docs,record,base):
    # The existing missing-price permission remains automatic. A model's memory
    # cannot supply this source: persist an actual retrieved reference first.
    if base is None:raise EngineError('PRICE_RETRIEVED_REFERENCE_EVENT_REQUIRED')
    source=_pricing_confirmed_event(base,record.get('external_source_event_id'),'retrieved_price_reference')
    required=('url','retrieved_at','item_id','specification','unit','usd_price','scope','comparison_basis','purchasing_power_ref')
    if any(k not in source for k in required) or not re.fullmatch(r'https://[^\s]+',str(source['url'])) or parse_iso(source['retrieved_at']) is None:raise EngineError('PRICE_CURRENT_EXTERNAL_SOURCE_INVALID')
    if source['item_id']!=record.get('item_id') or source['specification']!=record.get('specification') or source['scope']!=record.get('scope') or not source['comparison_basis']:raise EngineError('PRICE_EXTERNAL_SPECIFICATION_MISMATCH')
    _pricing_source_value(docs,source['purchasing_power_ref'])
    val=source['usd_price'];values=val if isinstance(val,list) else [val]
    if not values or len(values)>2 or any(_price_decimal(v)<0 for v in values):raise EngineError('PRICE_EXTERNAL_REFERENCE_AMOUNT_INVALID')
    eid=record['external_source_event_id'];rt=_pricing_runtime(docs['state']);rt.setdefault('reference_sources',{})[eid]=copy.deepcopy(source)
    row={'price_id':record['price_id'],'item_id':record['item_id'],'name':record.get('name',record['item_id']),'specification':source['specification'],'scope':source['scope'],'price_kind':'reference_range' if isinstance(val,list) else 'fixed_price','currency':'copper','unit':source['unit'],'status':'active','price_version':1,'source_ref':'state:engine_runtime.pricing_runtime.reference_sources.'+eid,'source_rule':'RULE-ECONOMY-01','source_save_set_id':docs['manifest']['save_set_id'],'effective_conditions':[],'included_components':source.get('included_components',[]),'inclusion_status':'documented' if source.get('included_components') else 'unspecified','supersedes':[],'override_rules':[],'exception_basis_ref':None,'category':'generated_comparable','external_source_event_id':eid,'comparability_basis':source['comparison_basis'],'anchor_role':'market_guidance'}
    row['range' if isinstance(val,list) else 'amount']=[_price_text(v) for v in val] if isinstance(val,list) else _price_text(val)
    rt['registered_prices'][row['price_id']]=row
    return row


def _pricing_request_reference(request,docs):
    if not isinstance(request,dict) or not request.get('source_ref'):return request
    p=copy.deepcopy(request);ref=p['source_ref'];rt=_pricing_runtime(docs['state'])
    alias=next((a for a in rt['aliases'] if a['path']==ref),None)
    mirror=next((a for a in rt['mirrors'] if a['path']==ref),None)
    if alias:
        obj=_pricing_source_value(docs,ref)
        if obj.get('price_authority_ref')!=alias['price_id']:raise EngineError('PRICE_ALIAS_CONFLICT')
        pid=obj['price_authority_ref']
    elif mirror:pid=mirror['price_id']
    else:raise EngineError('PRICE_NEEDS_EVIDENCE_UNREGISTERED_REFERENCE')
    if p.get('price_id') and p['price_id']!=pid:raise EngineError('PRICE_REFERENCE_ID_CONFLICT')
    p['price_id']=pid
    return p


def render_price_quote(quote,base=None):
    return _pricing_render_template(validate_price_quote(quote,base or ROOT))

def _pricing_price_visible(row,docs,audience=None):
    if row.get('audience') in (None,'public'):return True
    if audience=='gm' and os.environ.get('VOYAGER_DEVELOPER_MODE')=='1' and os.environ.get('VOYAGER_DIAGNOSTIC_CONTEXT')=='gm':return True
    if not docs:return False
    for scene in docs['state'].get('engine_runtime',{}).get('scene_registry_v1',{}).get('records',{}).values():
        disclosed={d['fact_id'] for d in scene.get('disclosures',[]) if d.get('viewer')=='player'}
        if any(fid in disclosed and ref.get('quote',{}).get('price_id')==row['price_id'] for fid,ref in scene.get('economic_fact_refs',{}).items()):return True
    return False


def _pricing_market_result(packet,context,base,payload):
    if context is None:return packet
    packet['currency']=context['total']['currency'];packet['quantity']=context['quantity'];packet['unit']=context['unit'];packet['price_context_id']=context['quote_id'];packet['settlement_status']='REQUIRES_EXISTING_TRANSACTION_AUTHORIZATION'
    if packet['result']=='REJECT':return packet
    amount=packet.get('price',packet.get('counter_price'));request=copy.deepcopy(context['request'])
    if _price_decimal(amount)==_price_decimal(context['total']['amount']):proposal=context
    else:
        request.pop('claimed_total',None);request['modifiers']=[]
        # An offer is a proposal, not evidence for rewriting the existing anchor.
        unit_amount=_price_decimal(amount)/_price_decimal(context['quantity'])
        request['quoted_unit_price']={'amount':_price_text(unit_amount),'currency':context['total']['currency'],'unit':context['unit']}
        if payload.get('negotiation_evidence_id'):request['special_evidence_id']=payload['negotiation_evidence_id']
        proposal=calculate_price_quote(request,base)
    packet['proposal_validation']=proposal['status'];packet['mathematical_result']=packet['result']
    if proposal['status']=='VALID':packet['validated_quote']=proposal
    else:
        packet['result']='PROVISIONAL_'+packet['result'] if proposal['status'] in {'PROVISIONAL','NEEDS_EVIDENCE'} else 'PRICE_REJECTED'
        packet['proposal_errors']=proposal.get('errors',proposal.get('checks',[]))
    return packet
