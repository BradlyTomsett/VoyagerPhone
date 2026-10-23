# === VOYAGER_DEV_MODULE: authorization_service ===
def _canonical_domain_payload(payload:dict)->dict:
    if not isinstance(payload,dict):raise EngineError('DOMAIN_ARGUMENT_OBJECT_REQUIRED')
    p=copy.deepcopy(payload);kind=p.get('kind')
    if not isinstance(kind,str):raise EngineError('DOMAIN_COMMAND_KIND_REQUIRED')
    p['kind']=DOMAIN_KIND_ALIASES.get(kind,kind)
    if p['kind'] not in DOMAIN_PUBLIC_KINDS:raise EngineError('DOMAIN_COMMAND_NOT_AVAILABLE:'+kind)
    for key in ('trusted','authorized','is_authorized','authorization_status'):
        if key in p:raise EngineError('DOMAIN_CALLER_AUTHORIZATION_CLAIM_FORBIDDEN:'+key)
    for key in DOMAIN_REQUIRED_FIELDS[p['kind']]:
        if key not in p or p[key] is None or p[key]=='':raise EngineError('DOMAIN_ARGUMENT_REQUIRED:'+key)
    if p['kind']=='create_task' and isinstance(p.get('task'),dict) and ((p['task'].get('task_data') or {}).get('domain_created') or str(p['task'].get('type') or '') in {'construction','manufacturing','research'}):raise EngineError('DOMAIN_PROJECT_USE_TYPED_START')
    if p['kind']=='start_repair' and not p.get('completion_actions'):raise EngineError('DOMAIN_REPAIR_VERIFIED_COMPLETION_ACTION_REQUIRED')
    return p


def _domain_command_targets_v1408(payload:dict)->list:
    kind=payload['kind']
    if kind=='settle_price':return [_pricing_account_target(payload),'state:engine_runtime.pricing_runtime.settlements.'+str(payload['settlement_id'])]
    if kind=='price_evidence_register':return ['state:engine_runtime.pricing_runtime.evidence.'+str(payload['evidence_id'])]
    if kind=='price_policy_update':return ['state:commander_runtime_rules.parameters.research_data_uniform_price_gold','state:'+PRICE_RESEARCH_PATH+'.packages']
    if kind=='adjust_funds':
        if any(_money_units_currency(payload.get(x+'_delta',0) or 0,x)>0 for x in ('gold','grey')):raise EngineError('DOMAIN_DIRECT_CREDIT_REQUIRES_VERIFIED_SETTLEMENT')
        return ['state:summary.funds.'+x for x in ('gold','grey') if _money_units_currency(payload.get(x+'_delta',0) or 0,x)]
    if kind=='transfer_asset':
        out=[str(payload[x]) for x in ('source_path','dest_path')]
        if any(not x.startswith('state:inventories.') for x in out):raise EngineError('DOMAIN_REFERENCE_NAMESPACE_INVALID')
        return out
    if kind in {'create_task','construct_facility','start_manufacturing','start_research'}:
        tid=str((payload.get('task') or {}).get('task_id') if kind=='create_task' else payload.get('task_id') or '')
        if not tid:raise EngineError('DOMAIN_TASK_ID_REQUIRED')
        return ['tasks:task:'+tid]
    if kind in {'cancel_task','complete_task'}:return ['tasks:task:'+str(payload['task_id'])]
    if kind in {'start_repair','start_medical_observation'}:
        out=['state:engine_runtime.maintenance_runtime.'+('repair_queue' if kind=='start_repair' else 'medical_queue')+'.job:'+str(payload['job_id'])]
        for action in payload.get('completion_actions') or []:
            if not isinstance(action,dict) or not str(action.get('path') or '').startswith('state:'):raise EngineError('DOMAIN_COMPLETION_ACTION_REFERENCE_INVALID')
            out.append(action['path'])
            if 'source_path' in action:
                if not str(action['source_path']).startswith('state:'):raise EngineError('DOMAIN_COMPLETION_SOURCE_REFERENCE_INVALID')
                out.append(action['source_path'])
        return out
    if kind in {'complete_repair','complete_medical','complete_maintenance'}:return ['state:engine_runtime.maintenance_runtime.job:'+str(payload['job_id'])]
    if kind in {'start_travel','arrive_location'}:return ['state:entity:'+str(payload['entity_id']),'state:location:'+str(payload['location_id'])]
    raise EngineError('DOMAIN_TARGET_RESOLVER_UNAVAILABLE:'+kind)


def _domain_authorization_cost(payload:dict)->dict:
    extra=_batch_b_command_cost(payload)
    if extra is not None:return extra
    out={'uses':1,'gold_units':0,'grey_units':0,'quantity':0}
    if payload['kind']=='settle_price':
        q=payload['quote'];cur=q['total']['currency'];amount=_price_decimal(q['total']['amount']);qvalue=_price_decimal(q['quantity']);out['quantity']=int(qvalue) if qvalue==qvalue.to_integral_value() else _price_text(qvalue)
        if payload['direction']=='debit':
            if cur in ('gold','grey'):out[cur+'_units']=_money_units_currency(amount,cur)
            elif cur=='silver':out['gold_units']=_money_units_currency(amount*Decimal('.01'),'gold')
            else:raise EngineError('PRICE_SETTLEMENT_CURRENCY_UNSUPPORTED')
    if payload['kind']=='adjust_funds':
        for cur in ('gold','grey'):out[cur+'_units']=max(0,-_money_units_currency(payload.get(cur+'_delta',0) or 0,cur))
    if payload['kind']=='transfer_asset':
        q=payload.get('qty')
        if not isinstance(q,(int,float)) or isinstance(q,bool) or not math.isfinite(float(q)) or q<=0:raise EngineError('DOMAIN_ASSET_QTY_INVALID')
        out['quantity']=float(q)
    return out


def _phase2_domain_authorization(state:dict,payload:dict,consume:bool=False)->dict:
    if payload.get('authorization')!='standing_authorization':
        if payload.get('authorization')=='commander':raise EngineError('DOMAIN_COMMANDER_PROOF_UNAVAILABLE_USE_VERIFIED_GRANT')
        raise EngineError('DOMAIN_COMMAND_AUTHORIZATION_REQUIRED')
    ref=str(payload.get('authorization_ref') or '').strip()
    if not ref:raise EngineError('DOMAIN_COMMAND_AUTHORIZATION_REF_REQUIRED')
    rec=(state.get('standing_authorizations') or {}).get(ref)
    if not isinstance(rec,dict):raise EngineError('DOMAIN_AUTHORIZATION_NOT_FOUND:'+ref)
    if rec.get('status')!='active' or rec.get('revoked') is True:raise EngineError('DOMAIN_AUTHORIZATION_REVOKED_OR_INACTIVE:'+ref)
    grant=rec.get('machine_grant')
    fields=('grant_id','subject_id','action_kinds','targets','valid_from','valid_until','max_uses','max_gold_units','max_grey_units','max_quantity')
    if not isinstance(grant,dict) or grant.get('schema')!='DOMAIN_MACHINE_GRANT_V1' or any(k not in grant for k in fields):raise EngineError('DOMAIN_AUTHORIZATION_SCOPE_UNVERIFIABLE:'+ref)
    if grant['grant_id']!=ref or not isinstance(grant['action_kinds'],list) or not isinstance(grant['targets'],list):raise EngineError('DOMAIN_AUTHORIZATION_GRANT_INVALID:'+ref)
    if not isinstance(payload.get('actor_id'),str) or payload.get('actor_id')!=grant['subject_id']:raise EngineError('DOMAIN_AUTHORIZATION_SUBJECT_MISMATCH')
    now=parse_iso(state.get('game_time'));lo=parse_iso(grant['valid_from']);hi=parse_iso(grant['valid_until'])
    if now is None or lo is None or hi is None or not lo<=now<=hi:raise EngineError('DOMAIN_AUTHORIZATION_EXPIRED_OR_NOT_YET_VALID')
    if payload['kind'] not in grant['action_kinds']:raise EngineError('DOMAIN_AUTHORIZATION_ACTION_OUT_OF_SCOPE')
    targets=_domain_command_targets(payload)
    if any(t not in grant['targets'] for t in targets):raise EngineError('DOMAIN_AUTHORIZATION_TARGET_OUT_OF_SCOPE')
    cost=_domain_authorization_cost(payload);ledger=state.setdefault('engine_runtime',{}).setdefault('domain_authorization_ledger',{'schema':'DOMAIN_AUTHORIZATION_LEDGER_V1','grants':{}})
    spent=ledger['grants'].get(ref) or {}
    for k,m in [('uses','max_uses'),('gold_units','max_gold_units'),('grey_units','max_grey_units'),('quantity','max_quantity')]:
        limit=grant[m]
        if not isinstance(limit,(int,float)) or isinstance(limit,bool) or not math.isfinite(float(limit)) or limit<0:raise EngineError('DOMAIN_AUTHORIZATION_LIMIT_INVALID:'+m)
        if _price_decimal(spent.get(k,0))+_price_decimal(cost[k])>_price_decimal(limit):raise EngineError('DOMAIN_AUTHORIZATION_BUDGET_EXCEEDED:'+k)
    if consume:
        row=ledger['grants'].setdefault(ref,{'uses':0,'gold_units':0,'grey_units':0,'quantity':0})
        for k,v in cost.items():
            total=_price_decimal(row[k])+_price_decimal(v);row[k]=int(total) if total==total.to_integral_value() else _price_text(total)
    return {'schema':DOMAIN_AUTHORIZATION_SCHEMA,'status':'verified','authority':'standing_authorization','authorization_ref':ref,'subject_id':grant['subject_id'],'grant_sha256':sha256_bytes(json.dumps(grant,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()),'targets':targets,'cost':cost}


def _phase2_domain_event_receipt(events_path:Path,payload:dict)->Optional[dict]:
    cid=str(payload.get('command_id') or '');digest=_domain_payload_digest(payload)
    found=history_lookup(Path(events_path).parent,command_id=cid)
    for ev in ([found] if found else []):
        if str(ev.get('command_id') or '')!=cid:continue
        er=(ev.get('receipt') or {}) if isinstance(ev,dict) else {}
        old_digest=str(er.get('payload_sha256') or ev.get('payload_sha256') or '')
        if not old_digest:
            # Pre-V2 receipt events cannot prove payload identity; fail closed rather than replay.
            raise EngineError('DOMAIN_COMMAND_HISTORICAL_RECEIPT_UNVERIFIABLE:'+cid)
        if old_digest!=digest:raise EngineError(f'DOMAIN_COMMAND_ID_REUSED_WITH_DIFFERENT_PAYLOAD:{cid}')
        if isinstance(er,dict) and er:return copy.deepcopy(er)
        return {'command_id':cid,'kind':ev.get('domain_kind'),'payload_sha256':old_digest,'applied_at':ev.get('game_time'),'event_id':ev.get('event_id'),'effect':copy.deepcopy(ev.get('domain_effect') or {})}
    return None


def _phase2_domain_existing_receipt(root:Path,state:dict,payload:dict)->Optional[dict]:
    cached=_domain_existing_receipt(state,payload)
    hist=_phase2_domain_event_receipt(Path(root)/'events.jsonl',payload)
    if cached and hist and cached.get('payload_sha256')!=hist.get('payload_sha256'):raise EngineError('DOMAIN_RECEIPT_CACHE_HISTORY_MISMATCH')
    return hist or cached


