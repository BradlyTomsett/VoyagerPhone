# === VOYAGER_DEV_MODULE: domain_commands ===
def _domain_runtime(state:dict,create:bool=False)->Optional[dict]:
    er=state.setdefault('engine_runtime',{}) if create else (state.get('engine_runtime') or {})
    dr=er.get('domain_command_runtime')
    if dr is None:
        if not create:return None
        dr={'schema':DOMAIN_COMMAND_RUNTIME_SCHEMA,'max_receipts':DOMAIN_COMMAND_MAX_RECEIPTS,'applied':{},'order':[]}
        er['domain_command_runtime']=dr
    if not isinstance(dr,dict) or dr.get('schema')!=DOMAIN_COMMAND_RUNTIME_SCHEMA:raise EngineError('DOMAIN_COMMAND_RUNTIME_INVALID')
    if not isinstance(dr.get('applied'),dict) or not isinstance(dr.get('order'),list):raise EngineError('DOMAIN_COMMAND_RUNTIME_INDEX_INVALID')
    return dr

def _domain_payload_digest(payload:dict)->str:
    obj=copy.deepcopy(payload);return sha256_bytes(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))

def _domain_register_receipt(state:dict,payload:dict,effect:dict,parent_sid:str)->dict:
    dr=_domain_runtime(state,create=True);cid=str(payload.get('command_id') or '');digest=_domain_payload_digest(payload);applied=dr['applied']
    old=applied.get(cid)
    if isinstance(old,dict):
        if old.get('payload_sha256')!=digest:raise EngineError(f'DOMAIN_COMMAND_ID_REUSED_WITH_DIFFERENT_PAYLOAD:{cid}')
        return copy.deepcopy(old)
    rec={'command_id':cid,'kind':payload.get('kind'),'payload_sha256':digest,'applied_at':state.get('game_time'),'parent_save_set_id':parent_sid,'effect':copy.deepcopy(effect)}
    applied[cid]=rec;dr['order'].append(cid)
    limit=int(dr.get('max_receipts') or DOMAIN_COMMAND_MAX_RECEIPTS)
    while len(dr['order'])>limit:
        old_id=dr['order'].pop(0);applied.pop(old_id,None)
    return rec

def _domain_existing_receipt(state:dict,payload:dict)->Optional[dict]:
    dr=_domain_runtime(state,create=False);cid=str(payload.get('command_id') or '')
    if dr is None:return None
    rec=(dr.get('applied') or {}).get(cid)
    if not isinstance(rec,dict):return None
    if rec.get('payload_sha256')!=_domain_payload_digest(payload):raise EngineError(f'DOMAIN_COMMAND_ID_REUSED_WITH_DIFFERENT_PAYLOAD:{cid}')
    return copy.deepcopy(rec)

def _domain_number_add(a:Any,b:Any):
    from decimal import Decimal
    q=Decimal(str(a))+Decimal(str(b))
    if not q.is_finite():raise EngineError('DOMAIN_QUANTITY_NONFINITE')
    if q==q.to_integral_value():return int(q)
    return float(str(q.normalize()))

def _domain_adjust_funds(state:dict,tasks:dict,payload:dict)->dict:
    reason=str(payload.get('reason') or '').strip()
    if not reason:raise EngineError('DOMAIN_FINANCE_REASON_REQUIRED')
    deltas={k:_money_currency(payload.get(k+'_delta',0) or 0,k) for k in ('gold','grey')}
    if not any(_money_units_currency(v,k) for k,v in deltas.items()):raise EngineError('DOMAIN_FINANCE_NONZERO_DELTA_REQUIRED')
    if any(_money_units_currency(v,k)<0 for k,v in deltas.items()):
        auth=str(payload.get('authorization') or '')
        if auth not in {'commander','standing_authorization'}:raise EngineError('DOMAIN_FINANCE_NEGATIVE_REQUIRES_AUTHORIZATION')
        if auth=='standing_authorization' and not str(payload.get('authorization_ref') or '').strip():raise EngineError('DOMAIN_FINANCE_AUTHORIZATION_REF_REQUIRED')
    rows=[]
    for cur,delta in deltas.items():
        if _money_units_currency(delta,cur):rows.append(_finance_credit(state,cur,delta))
    return {'kind':'adjust_funds','reason':reason,'entries':rows,'changes':[{'target':'STATE.engine_runtime.finance_runtime.funds_units','action':'fixed_point_adjust_funds'},{'target':'STATE.summary.funds','action':'sync_compatibility_view'}]}

def _domain_asset_record_identity(parent:dict,key:str)->Optional[str]:
    if not isinstance(parent,dict):return None
    for field in ('asset_type_id','item_id','model_id','equipment_id','model','name','type'):
        v=parent.get(field)
        if isinstance(v,str) and v.strip():return field+':'+v.strip()
    return None

def _v130_layer__domain_transfer_asset_01(state:dict,tasks:dict,payload:dict)->dict:
    src=str(payload.get('source_path') or '');dst=str(payload.get('dest_path') or '');qty=payload.get('qty')
    if not src.startswith('STATE.inventories.') or not dst.startswith('STATE.inventories.') or src==dst:raise EngineError('DOMAIN_ASSET_PATHS_MUST_BE_DISTINCT_INVENTORY_PATHS')
    if not isinstance(qty,(int,float)) or isinstance(qty,bool) or not math.isfinite(float(qty)) or float(qty)<=0:raise EngineError('DOMAIN_ASSET_QTY_INVALID')
    try:sv=get_by_path(state,src[6:]);dv=get_by_path(state,dst[6:])
    except KeyError as ex:raise EngineError(f'DOMAIN_ASSET_PATH_MISSING:{ex}')
    if not isinstance(sv,(int,float)) or isinstance(sv,bool) or not isinstance(dv,(int,float)) or isinstance(dv,bool):raise EngineError('DOMAIN_ASSET_NUMERIC_LEAVES_REQUIRED')
    sparent,skey=_dot_parent(state,src[6:]);dparent,dkey=_dot_parent(state,dst[6:])
    scls,sreason,_=_asset_numeric_classification(src[6:].split('.')[:-1],skey,sparent);dcls,dreason,_=_asset_numeric_classification(dst[6:].split('.')[:-1],dkey,dparent)
    if scls!='quantity' or dcls!='quantity':raise EngineError(f'DOMAIN_ASSET_SEMANTIC_QUANTITY_REQUIRED:source={scls}:{sreason};dest={dcls}:{dreason}')
    if sparent is not dparent:
        si=_domain_asset_record_identity(sparent,skey);di=_domain_asset_record_identity(dparent,dkey)
        if not si or not di or si!=di:raise EngineError(f'DOMAIN_ASSET_IDENTITY_MISMATCH:{si}!={di}')
    if isinstance(sv,int) and not float(qty).is_integer():raise EngineError('DOMAIN_ASSET_INTEGER_SOURCE_REQUIRES_INTEGER_QTY')
    if float(sv)<float(qty):raise EngineError('DOMAIN_ASSET_INSUFFICIENT_SOURCE')
    sp,sk=_dot_parent(state,src[6:]);dp,dk=_dot_parent(state,dst[6:])
    sp[sk]=_domain_number_add(sv,-qty);dp[dk]=_domain_number_add(dv,qty)
    return {'kind':'transfer_asset','qty':qty,'source_path':src,'dest_path':dst,'source_before':sv,'source_after':sp[sk],'dest_before':dv,'dest_after':dp[dk],'changes':[{'target':src,'action':'decrement_asset_quantity'},{'target':dst,'action':'increment_asset_quantity'}]}

def _voyager_partition_vessels(part:dict)->set:
    out=set()
    for rec in (part.get('deployments') or {}).values():
        if isinstance(rec,dict):out.update(str(x) for x in (rec.get('vessels') or []))
    out.update(str(x) for x in ((part.get('transit') or {}).get('vessels') or []))
    return out

def _domain_deploy_ship(state:dict,tasks:dict,payload:dict)->dict:
    ship_id=str(payload.get('ship_id') or '').strip();dep_id=str(payload.get('deployment_id') or '').strip();status=str(payload.get('status') or '').strip()
    if not ship_id or not dep_id or not status:raise EngineError('DOMAIN_DEPLOY_SHIP_FIELDS_REQUIRED')
    vf=state.get('voyager_fleet') or {};roster={str(x.get('vessel_id')) for x in (vf.get('vessel_roster') or []) if isinstance(x,dict)}
    if ship_id not in roster:raise EngineError(f'DOMAIN_DEPLOY_SHIP_UNKNOWN:{ship_id}')
    part=vf.get('current_location_partition')
    if not isinstance(part,dict):raise EngineError('DOMAIN_VOYAGER_LOCATION_PARTITION_MISSING')
    if ship_id in _voyager_partition_vessels(part):raise EngineError(f'DOMAIN_DEPLOY_SHIP_ALREADY_AWAY:{ship_id}')
    base=part.get('at_voyager_base') or {};bc=int(base.get('ships',0) or 0)
    if bc<=0:raise EngineError('DOMAIN_DEPLOY_SHIP_BASE_COUNT_INVALID')
    deps=part.setdefault('deployments',{});rec=deps.get(dep_id)
    if rec is None:rec={'ships':0,'vessels':[],'status':status};deps[dep_id]=rec
    if not isinstance(rec,dict) or not isinstance(rec.get('vessels',[]),list):raise EngineError('DOMAIN_DEPLOYMENT_RECORD_INVALID')
    if ship_id in rec.get('vessels',[]):raise EngineError('DOMAIN_DEPLOY_SHIP_DUPLICATE')
    rec['vessels'].append(ship_id);rec['ships']=len(rec['vessels']);rec['status']=status;base['ships']=bc-1;base['status']=f"{base['ships']}舰驻远航者基地。";part['at_voyager_base']=base;part['as_of']=state.get('game_time')
    task_id=payload.get('task_id');mission=str(payload.get('mission') or status)
    if task_id:
        if not any(isinstance(t,dict) and str(t.get('task_id'))==str(task_id) for t in (tasks.get('active_tasks') or [])):raise EngineError(f'DOMAIN_DEPLOY_TASK_NOT_ACTIVE:{task_id}')
    named=(vf.get('named_vessels') or {}).get(ship_id)
    if isinstance(named,dict):
        named['current_assignment_task_id']=task_id or dep_id;named['current_mission']=mission
    return {'kind':'deploy_ship','ship_id':ship_id,'deployment_id':dep_id,'base_ships_after':base['ships'],'changes':[{'target':'STATE.voyager_fleet.current_location_partition','action':'deploy_ship_atomic'},{'target':f'STATE.voyager_fleet.named_vessels.{ship_id}','action':'sync_assignment_if_named'}]}

def _domain_recall_ship(state:dict,tasks:dict,payload:dict)->dict:
    ship_id=str(payload.get('ship_id') or '').strip()
    if not ship_id:raise EngineError('DOMAIN_RECALL_SHIP_ID_REQUIRED')
    vf=state.get('voyager_fleet') or {};part=vf.get('current_location_partition')
    if not isinstance(part,dict):raise EngineError('DOMAIN_VOYAGER_LOCATION_PARTITION_MISSING')
    deps=part.get('deployments') or {};found=None
    for dep_id,rec in deps.items():
        if isinstance(rec,dict) and ship_id in (rec.get('vessels') or []):found=(dep_id,rec);break
    if found is None:raise EngineError(f'DOMAIN_RECALL_SHIP_NOT_DEPLOYED:{ship_id}')
    dep_id,rec=found;rec['vessels']=[x for x in rec.get('vessels',[]) if x!=ship_id];rec['ships']=len(rec['vessels'])
    if rec['ships']==0:deps.pop(dep_id,None)
    base=part.get('at_voyager_base') or {};base['ships']=int(base.get('ships',0) or 0)+1;base['status']=f"{base['ships']}舰驻远航者基地。";part['at_voyager_base']=base;part['as_of']=state.get('game_time')
    named=(vf.get('named_vessels') or {}).get(ship_id)
    if isinstance(named,dict):named['current_assignment_task_id']=None;named['current_mission']=str(payload.get('mission') or '已归建远航者基地。')
    return {'kind':'recall_ship','ship_id':ship_id,'deployment_id':dep_id,'base_ships_after':base['ships'],'changes':[{'target':'STATE.voyager_fleet.current_location_partition','action':'recall_ship_atomic'},{'target':f'STATE.voyager_fleet.named_vessels.{ship_id}','action':'clear_assignment_if_named'}]}

def _domain_complete_maintenance(stage:Path,state:dict,tasks:dict,payload:dict)->dict:
    job_id=str(payload.get('job_id') or '').strip()
    if not job_id:raise EngineError('DOMAIN_MAINTENANCE_JOB_ID_REQUIRED')
    mr=_maintenance_runtime(state,create=True);qname,idx,job=_maintenance_find_active(mr,job_id);tm=parse_iso(job.get('complete_at'));now=parse_iso(state.get('game_time'))
    if tm is None or now is None or tm>now:raise EngineError(f'DOMAIN_MAINTENANCE_NOT_DUE:{job_id}')
    event={'source':'maintenance_runtime','kind':'maintenance_completion','job_id':job_id,'maintenance_kind':job.get('kind'),'time':tm.strftime('%Y-%m-%dT%H:%M:%S'),'resolver':'maintenance_completion_v1'}
    out=_resolve_maintenance_event(stage,state,tasks,event,tm)
    if out.get('status')!='COMPLETED':raise EngineError('DOMAIN_MAINTENANCE_REQUIRES_SEMANTIC_REVIEW:'+json.dumps(out,ensure_ascii=False))
    out['kind']='complete_maintenance';out['changes']=(out.get('actions') or [])+out.get('changes',[]);return out


def _domain_quantity_effects(state:dict,payload:dict,mode:str)->dict:
    effects=payload.get('asset_effects')
    if not isinstance(effects,list) or not effects:raise EngineError('DOMAIN_ASSET_EFFECTS_REQUIRED')
    asset_id=str(payload.get('asset_id') or '').strip()
    if not asset_id:raise EngineError('DOMAIN_ASSET_ID_REQUIRED')
    changes=[];rows=[]
    for i,e in enumerate(effects):
        if not isinstance(e,dict):raise EngineError(f'DOMAIN_ASSET_EFFECT_INVALID:{i}')
        path=str(e.get('path') or '')
        delta=e.get('delta')
        if not path.startswith('STATE.inventories.'):raise EngineError(f'DOMAIN_ASSET_EFFECT_PATH_INVALID:{path}')
        if not isinstance(delta,(int,float)) or isinstance(delta,bool) or not math.isfinite(float(delta)) or float(delta)==0:raise EngineError(f'DOMAIN_ASSET_EFFECT_DELTA_INVALID:{path}')
        try:before=get_by_path(state,path[6:])
        except Exception:raise EngineError(f'DOMAIN_ASSET_EFFECT_PATH_MISSING:{path}')
        if not isinstance(before,(int,float)) or isinstance(before,bool):raise EngineError(f'DOMAIN_ASSET_EFFECT_NUMERIC_REQUIRED:{path}')
        parent,key=_dot_parent(state,path[6:]);cls,reason,_=_asset_numeric_classification(path[6:].split('.')[:-1],key,parent)
        if cls!='quantity':raise EngineError(f'DOMAIN_ASSET_EFFECT_QUANTITY_REQUIRED:{path}:{cls}:{reason}')
        if 'expected_before' not in e:raise EngineError(f'DOMAIN_ASSET_EFFECT_EXPECTED_BEFORE_REQUIRED:{path}')
        exp=e.get('expected_before')
        if _domain_number_add(before,0)!=_domain_number_add(exp,0):raise EngineError(f'DOMAIN_ASSET_EFFECT_EXPECT_MISMATCH:{path}:{exp}!={before}')
        declared=str(e.get('asset_id') or asset_id).strip()
        if declared!=asset_id:raise EngineError(f'DOMAIN_ASSET_EFFECT_ID_MISMATCH:{declared}!={asset_id}')
        identity=_domain_asset_record_identity(parent,key)
        if identity and e.get('record_identity') and str(e.get('record_identity'))!=identity:raise EngineError(f'DOMAIN_ASSET_RECORD_IDENTITY_MISMATCH:{path}:{e.get("record_identity")}!={identity}')
        after=_domain_number_add(before,delta)
        if float(after)<0:raise EngineError(f'DOMAIN_ASSET_EFFECT_NEGATIVE:{path}')
        if isinstance(before,int) and not float(delta).is_integer():raise EngineError(f'DOMAIN_ASSET_INTEGER_REQUIRES_INTEGER_DELTA:{path}')
        if isinstance(parent,list):raise EngineError('DOMAIN_ASSET_EFFECT_LIST_PARENT_UNSUPPORTED')
        if _asset_registry_entry(state,path) and 'reason_code' not in _asset_registry_entry(state,path):raise EngineError('DOMAIN_ASSET_DELTA_REQUIRES_VERIFIED_LEDGER_CONTRACT:'+path)
        parent[key]=after
        rows.append({'path':path,'asset_id':asset_id,'before':before,'delta':delta,'after':after,'record_identity':identity})
        changes.append({'target':path,'action':f'{mode}_asset_quantity'})
    return {'asset_id':asset_id,'asset_rows':rows,'changes':changes}


def _domain_commercial_asset(state:dict,tasks:dict,payload:dict,kind:str)->dict:
    reason=str(payload.get('reason') or '').strip()
    if not reason:raise EngineError('DOMAIN_COMMERCIAL_REASON_REQUIRED')
    out=_domain_quantity_effects(state,payload,kind)
    finance=[]
    sign=-1 if kind=='purchase_asset' else 1 if kind=='sell_asset' else -1 if kind=='manufacture_asset' else 0
    for cur in ('gold','grey'):
        key=('price_'+cur) if kind in {'purchase_asset','sell_asset'} else ('cost_'+cur)
        amt=payload.get(key,0) or 0
        units=_money_units4(amt)
        if units<0:raise EngineError(f'DOMAIN_COMMERCIAL_AMOUNT_NEGATIVE:{key}')
        if units and sign:
            if sign<0:
                auth=str(payload.get('authorization') or '')
                if auth not in {'commander','standing_authorization'}:raise EngineError('DOMAIN_COMMERCIAL_SPEND_REQUIRES_AUTHORIZATION')
                if auth=='standing_authorization' and not str(payload.get('authorization_ref') or '').strip():raise EngineError('DOMAIN_COMMERCIAL_AUTHORIZATION_REF_REQUIRED')
            finance.append(_finance_credit(state,cur,_money_value4(sign*units)))
    if kind=='purchase_asset' and not any(float(r.get('delta') or 0)>0 for r in out['asset_rows']):raise EngineError('DOMAIN_PURCHASE_REQUIRES_POSITIVE_ASSET_EFFECT')
    if kind=='sell_asset' and not any(float(r.get('delta') or 0)<0 for r in out['asset_rows']):raise EngineError('DOMAIN_SALE_REQUIRES_NEGATIVE_ASSET_EFFECT')
    if kind=='manufacture_asset' and not any(float(r.get('delta') or 0)>0 for r in out['asset_rows']):raise EngineError('DOMAIN_MANUFACTURE_REQUIRES_POSITIVE_ASSET_EFFECT')
    out.update({'kind':kind,'reason':reason,'finance_entries':finance});out['changes']+=([{'target':'STATE.engine_runtime.finance_runtime.funds_units','action':'fixed_point_commercial_settlement'},{'target':'STATE.summary.funds','action':'sync_compatibility_view'}] if finance else [])
    return out


def _domain_capture_asset(state:dict,tasks:dict,payload:dict)->dict:
    if not str(payload.get('source_event_id') or '').strip():raise EngineError('DOMAIN_CAPTURE_SOURCE_EVENT_REQUIRED')
    out=_domain_quantity_effects(state,payload,'capture')
    if not any(float(r.get('delta') or 0)>0 for r in out['asset_rows']):raise EngineError('DOMAIN_CAPTURE_REQUIRES_POSITIVE_ASSET_EFFECT')
    out.update({'kind':'capture_asset','source_event_id':payload.get('source_event_id')});return out


def _domain_transfer_ownership(state:dict,tasks:dict,payload:dict)->dict:
    src=str(payload.get('source_path') or '');dst=str(payload.get('dest_path') or '')
    q=payload.get('qty');p=dict(payload);p['kind']='transfer_asset'
    effect=_domain_transfer_asset(state,tasks,p)
    effect['kind']='transfer_ownership';effect['ownership_transfer']={'asset_id':payload.get('asset_id'),'from_owner':payload.get('from_owner'),'to_owner':payload.get('to_owner'),'qty':q,'source_path':src,'dest_path':dst}
    if not str(payload.get('from_owner') or '').strip() or not str(payload.get('to_owner') or '').strip() or payload.get('from_owner')==payload.get('to_owner'):raise EngineError('DOMAIN_OWNERSHIP_OWNER_IDS_REQUIRED')
    return effect


def _domain_task_lookup(tasks:dict,task_id:str):
    for bucket in ('active_tasks','queued_tasks'):
        arr=tasks.get(bucket) or []
        for i,t in enumerate(arr):
            if isinstance(t,dict) and str(t.get('task_id'))==task_id:return bucket,i,t
    return None,None,None


def _domain_authorize_task(state:dict,tasks:dict,payload:dict)->dict:
    tid=str(payload.get('task_id') or '').strip();auth=str(payload.get('authorization') or '').strip()
    if not tid or auth not in {'commander','standing_authorization'}:raise EngineError('DOMAIN_TASK_AUTHORIZATION_REQUIRED')
    bucket,i,t=_domain_task_lookup(tasks,tid)
    if t is None:raise EngineError('DOMAIN_TASK_NOT_FOUND:'+tid)
    ref=str(payload.get('authorization_ref') or '').strip()
    if auth=='standing_authorization' and not ref:raise EngineError('DOMAIN_TASK_AUTHORIZATION_REF_REQUIRED')
    t['authorization']={'status':'authorized','authority':auth,'authorization_ref':ref or None,'authorized_at':state.get('game_time')}
    return {'kind':'authorize_task','task_id':tid,'changes':[{'target':f'TASKS.{bucket}.task:{tid}.authorization','action':'authorize_task'}]}


def _domain_complete_task(state:dict,tasks:dict,payload:dict)->dict:
    tid=str(payload.get('task_id') or '').strip();evidence=payload.get('completion_evidence')
    if not tid or not isinstance(evidence,dict) or not evidence:raise EngineError('DOMAIN_TASK_COMPLETION_EVIDENCE_REQUIRED')
    bucket,i,t=_domain_task_lookup(tasks,tid)
    if t is None:raise EngineError('DOMAIN_TASK_NOT_FOUND_OR_ALREADY_CLOSED:'+tid)
    if bucket!='active_tasks':raise EngineError('DOMAIN_TASK_COMPLETION_REQUIRES_ACTIVE_TASK')
    td=t.get('task_data') or {}
    if str(t.get('type') or '') in {'construction','manufacturing','research'}:
        if (td.get('progress') or 0)<100 or not td.get('verified_resource_settlement') or not td.get('verified_completion_at') or parse_iso(td['verified_completion_at'])>parse_iso(state['game_time']):raise EngineError('DOMAIN_PROJECT_COMPLETION_NOT_VERIFIED')
    elif not (t.get('runtime_policy') or {}).get('verified_completion_contract'):
        raise EngineError('DOMAIN_TASK_COMPLETION_NOT_ENGINE_VERIFIED')
    if bool((t.get('authorization') or {}).get('requires_player_authorization')) and (t.get('authorization') or {}).get('status')!='authorized':raise EngineError('DOMAIN_TASK_COMPLETION_AUTHORIZATION_MISSING')
    done=copy.deepcopy(t);done['phase']='completed';done['completed_at']=state.get('game_time');done['completion_evidence']=copy.deepcopy(evidence)
    tasks['active_tasks'].pop(i);tasks.setdefault('recent_completed_tasks',[]).append(done)
    return {'kind':'complete_task','task_id':tid,'changes':[{'target':f'TASKS.active_tasks.task:{tid}','action':'remove_completed_task'},{'target':f'TASKS.recent_completed_tasks.task:{tid}','action':'append_completed_task'}]}


def _domain_complete_maintenance_typed(stage:Path,state:dict,tasks:dict,payload:dict,expected_kind:str,domain_kind:str)->dict:
    job_id=str(payload.get('job_id') or '').strip();mr=_maintenance_runtime(state,create=True);qname,idx,job=_maintenance_find_active(mr,job_id)
    actual=str(job.get('kind') or '')
    if expected_kind=='repair' and 'repair' not in actual:raise EngineError(f'DOMAIN_REPAIR_JOB_KIND_MISMATCH:{actual}')
    if expected_kind=='medical' and 'medical' not in actual and 'observation' not in actual and 'treatment' not in actual:raise EngineError(f'DOMAIN_MEDICAL_JOB_KIND_MISMATCH:{actual}')
    out=_domain_complete_maintenance(stage,state,tasks,payload);out['kind']=domain_kind;return out



def _v130_layer__apply_domain_command_01(stage:Path,state:dict,tasks:dict,payload:dict)->dict:
    kind=str(payload.get('kind') or '')
    if kind not in DOMAIN_COMMAND_KINDS:raise EngineError(f'DOMAIN_COMMAND_KIND_INVALID:{kind}')
    if kind=='adjust_funds':return _domain_adjust_funds(state,tasks,payload)
    if kind=='transfer_asset':return _domain_transfer_asset(state,tasks,payload)
    if kind=='deploy_ship':return _domain_deploy_ship(state,tasks,payload)
    if kind=='recall_ship':return _domain_recall_ship(state,tasks,payload)
    if kind=='purchase_asset':return _domain_commercial_asset(state,tasks,payload,'purchase_asset')
    if kind=='sell_asset':return _domain_commercial_asset(state,tasks,payload,'sell_asset')
    if kind=='manufacture_asset':return _domain_commercial_asset(state,tasks,payload,'manufacture_asset')
    if kind=='capture_asset':return _domain_capture_asset(state,tasks,payload)
    if kind=='transfer_ownership':return _domain_transfer_ownership(state,tasks,payload)
    if kind=='authorize_task':return _domain_authorize_task(state,tasks,payload)
    if kind=='complete_task':return _domain_complete_task(state,tasks,payload)
    if kind=='complete_repair':return _domain_complete_maintenance_typed(stage,state,tasks,payload,'repair','complete_repair')
    if kind=='complete_medical':return _domain_complete_maintenance_typed(stage,state,tasks,payload,'medical','complete_medical')
    return _domain_complete_maintenance(stage,state,tasks,payload)

def _domain_runtime_integrity_report(state:dict)->dict:
    dr=_domain_runtime(state,create=False)
    if dr is None:return {'active':False,'status':'LEGACY'}
    errs=[];ap=dr.get('applied') or {};order=dr.get('order') or []
    if len(order)!=len(set(order)):errs.append('order_duplicate')
    if any(x not in ap for x in order):errs.append('order_missing_receipt')
    if len(order)>int(dr.get('max_receipts') or DOMAIN_COMMAND_MAX_RECEIPTS):errs.append('receipt_limit_exceeded')
    for cid,rec in ap.items():
        if not isinstance(cid,str) or not cid or not isinstance(rec,dict):errs.append('receipt_invalid');continue
        if rec.get('command_id')!=cid or rec.get('kind') not in DOMAIN_COMMAND_KINDS or not re.fullmatch(r'[0-9a-f]{64}',str(rec.get('payload_sha256') or '')):errs.append('receipt_fields_invalid:'+cid)
    return {'active':True,'status':'PASS' if not errs else 'FAIL','errors':errs,'receipt_count':len(order)}

def _v130_layer_domain_command_status_01(base:Path=ROOT)->dict:
    ensure_source_ready(base);state=read_json(base/'state.json');dr=_domain_runtime(state,create=False) or {'applied':{},'order':[]}
    order=list(dr.get('order') or []);ap=dr.get('applied') or {};rows=[copy.deepcopy(ap[x]) for x in order[-20:] if x in ap]
    return {'packet':'DOMAIN_COMMAND_STATUS_V1','engine_version':ENGINE_VERSION,'schema':DOMAIN_COMMAND_SCHEMA,'supported_kinds':sorted(DOMAIN_COMMAND_KINDS),'receipt_count':len(order),'recent_receipts':rows}

def _domain_command_packet_unlocked(root:Path,payload:dict,version:Optional[str],scope:str,dry_run:bool=False)->dict:
    guard(root,restore=True,restore_tool_files=False);ensure_source_ready(root,allow_cache=False)
    if not isinstance(payload,dict) or payload.get('schema')!=DOMAIN_COMMAND_SCHEMA:raise EngineError(f'DOMAIN_COMMAND_SCHEMA_REQUIRED:{DOMAIN_COMMAND_SCHEMA}')
    cid=str(payload.get('command_id') or '').strip()
    if not cid or len(cid)>160:raise EngineError('DOMAIN_COMMAND_ID_INVALID')
    auth=validate_authority_set(root) or {};current_sid=str(auth.get('save_set_id') or '')
    current_state=read_json(root/'state.json');old=_domain_existing_receipt(current_state,payload)
    if old is not None:return {'packet':'DOMAIN_COMMAND_RESULT_V1','status':'ALREADY_APPLIED','command_id':cid,'receipt':old,'save_set_id':current_sid,'saved':False}
    base_sid=str(payload.get('base_save_set_id') or '')
    if base_sid!=current_sid:raise EngineError(f'DOMAIN_COMMAND_STALE_BASE:{base_sid}!={current_sid}')
    if dry_run:
        state=copy.deepcopy(current_state);tasks=read_json(root/'tasks.json')
        with tempfile.TemporaryDirectory(prefix='voyager_domain_preview_') as td:
            tp=Path(td);shutil.copy2(root/'events.jsonl',tp/'events.jsonl');effect=_apply_domain_command(tp,state,tasks,payload)
        return {'packet':'DOMAIN_COMMAND_RESULT_V1','status':'DRY_RUN','command_id':cid,'kind':payload.get('kind'),'effect':effect,'saved':False,'committed':False,'save_set_id':current_sid,'export_status':'NOT_REQUESTED','retry_action':'submit_with_version'}
    if not version:raise EngineError('DOMAIN_COMMAND_VERSION_REQUIRED')
    info=create_stage(root,'domain_command');stage=Path(info['staging'])
    try:
        state=read_json(stage/'state.json');tasks=read_json(stage/'tasks.json');effect=_apply_domain_command(stage,state,tasks,payload);receipt=_domain_register_receipt(state,payload,effect,current_sid);gt=str(state.get('game_time') or '')
        _write_authority_json(stage/'state.json',state);_write_authority_json(stage/'tasks.json',tasks)
        _changes=copy.deepcopy(effect.get('changes') or [])+[{'target':'STATE.engine_runtime.domain_command_runtime','action':'record_idempotency_receipt'}]
        _af=['state.json']
        if any(str(x.get('target') or '').upper().startswith('TASKS') for x in _changes if isinstance(x,dict)):_af.append('tasks.json')
        hev={'event_id':f'DOMAIN-{cid}-{sha256_bytes(receipt["payload_sha256"].encode())[:8]}','game_time':gt,'type':'system','subtype':'domain_command_commit','summary':f'GAME ENGINE v{ENGINE_VERSION}原子执行领域命令{payload.get("kind")}（{cid}）。','changes':_changes,'source':f'GAME ENGINE v{ENGINE_VERSION} {DOMAIN_COMMAND_SCHEMA}','authority_files':_af,'command_id':cid,'domain_kind':payload.get('kind'),'zero_time':True}
        _finrows=(effect.get('entries') or [])+(effect.get('finance_entries') or [])
        if _finrows:
            fg=sum(_money_units_currency(x.get('delta',0),'gold') for x in _finrows if x.get('currency')=='gold');fr=sum(_money_units_currency(x.get('delta',0),'grey') for x in _finrows if x.get('currency')=='grey')
            hev['finance']={'account':'domain_command:'+str(payload.get('reason') or cid),'gold':_money_value_currency(fg,'gold'),'grey':_money_value_currency(fr,'grey')}
        _append_engine_history(stage/'events.jsonl',hev)
        saved=atomic_save(stage,version,scope,root,False,False)
        return {'packet':'DOMAIN_COMMAND_RESULT_V1','status':'SAVED','command_id':cid,'kind':payload.get('kind'),'effect':effect,'receipt':receipt,'save':saved}
    except Exception:
        try:writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
        except Exception:pass
        raise

def _advance_cap(state, target, origin=None):
    now=parse_iso(state.get('game_time'))
    if target is None or now is None or not _mobile_contract(state):return target
    start=parse_iso(origin) if origin else now
    if start is None or start>now:raise EngineError('TURN_ORIGIN_INVALID')
    return min(target,start+dt.timedelta(hours=24))

def _select_root_import(root_auth, active):
    if not root_auth or root_auth.get('save_set_id')==active.get('save_set_id'):return False
    if root_auth['version']==active['version']:raise ForkError('PROJECT_SOURCE_SAME_VERSION_FORK')
    if root_auth['version']<active['version']:return False
    parent=(root_auth.get('index') or {}).get('parent_save_set_id')
    if parent!=active['save_set_id']:
        raise ForkError('PROJECT_SOURCE_LINEAGE_CONFLICT: newer source must descend directly from active save; use a clean seven-file environment for a separately verified recovery anchor')
    return True

def _mobile_fleet_core(state):
    sm=state.get('summary') or {};ships=sm.get('ships') or {};persons=sm.get('personnel') or {}
    registry=(((state.get('engine_runtime') or {}).get('player_fleet_registry') or {}).get('fleets') or {})
    out={}
    for fid,b in registry.items():
        if b.get('retired') is True:continue
        sp=b.get('primary_ship_count_path');pp=b.get('primary_personnel_path')
        try:nships=get_by_path(state,sp[6:]) if sp else ships.get('shadow_active' if fid=='shadow' else fid)
        except (KeyError,TypeError):nships=None
        try:npeople=get_by_path(state,pp[6:]) if pp else persons.get(fid)
        except (KeyError,TypeError):npeople=None
        out[fid]={'ships':nships,'personnel':npeople,'display_name':b.get('display_name') or fid,'source_paths':[sp,pp],'complete':nships is not None and npeople is not None}
    if not out:
        for fid in ('voyager','jinchuan','shadow'):out[fid]={'ships':ships.get('shadow_active' if fid=='shadow' else fid),'personnel':persons.get(fid)}
    out.update({k:(sm.get('funds') or {}).get(k) for k in ('gold','grey')})
    if state.get('engine_runtime',{}).get('account_registry_v1'):out['five_balances']=_five_account_balances(state)
    return out

def _v130_layer__catalog_sales_inputs_01(cfg,state,when):
    path=str(cfg.get('catalog_source') or '')
    if not path.startswith(('STATE.','state:')):raise EngineError('SALES_CATALOG_SOURCE_INVALID')
    catalog=get_by_path(state,path[6:])
    if not isinstance(catalog,dict):raise EngineError('SALES_CATALOG_NOT_OBJECT')
    statuses=set(cfg.get('eligible_statuses') or ['on_sale','active_nonexclusive_digital_backup'])
    items=[];ranges={};prices={}
    for pid,rec in catalog.items():
        if not isinstance(rec,dict) or rec.get('status') not in statuses:continue
        start=parse_iso(rec.get('mechanical_sales_from')) if rec.get('mechanical_sales_from') else None
        if start and when<start:continue
        rr=rec.get('sales_range')
        if not isinstance(rr,list) or len(rr)!=2 or any(isinstance(x,bool) or not isinstance(x,int) for x in rr) or rr[0]<0 or rr[1]<rr[0]:raise EngineError('SALES_CATALOG_RANGE_INVALID:'+pid)
        price=rec.get('price_gold_per_copy')
        if isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or price<0:raise EngineError('SALES_CATALOG_PRICE_INVALID:'+pid)
        items.append(pid);ranges[pid]=rr;prices[pid]=_money4(price)
    return items,ranges,prices

def _v130_layer_evidence_packet_01(base,source,path,offset=0,limit=4000):
    ready=ensure_source_ready(base)
    if not isinstance(offset,int) or offset<0 or not 1<=limit<=16000:raise EngineError('EVIDENCE_PAGE_INVALID')
    if source=='STATE':
        state=read_json(base/'state.json');resolved=resolve_state_ref(state,path.removeprefix('STATE.'));value=get_by_path(state,resolved)
        raw=json.dumps(value,ensure_ascii=False,separators=(',',':'))
    elif source=='WORLD':
        world=_authority_world_text(base);raw,meta=_world_rule_from_index(base,world,path,1000000);resolved=path
        if raw is None:raise EngineError('EVIDENCE_RULE_NOT_FOUND:'+path)
    else:raise EngineError('EVIDENCE_SOURCE_INVALID')
    end=min(len(raw),offset+limit)
    return {'packet':'EVIDENCE_PAGE_V1','save_set_id':ready.get('save_set_id'),'source':source,'path':resolved,'offset':offset,'text':raw[offset:end],'total_chars':len(raw),'next_offset':end if end<len(raw) else None,'status':'TRUNCATED' if end<len(raw) else 'COMPLETE','usage':'Pages are slices of one bound source; join all pages before interpreting incomplete JSON or a truncated rule.'}

def _v1403_previous_query_batch_packet(base,topics,detail='compact'):
    if not isinstance(topics,list) or not 1<=len(topics)<=8 or any(not isinstance(t,str) or not t.strip() for t in topics):raise EngineError('QUERY_BATCH_REQUIRES_1_TO_8_TOPICS')
    with engine_lock(base,exclusive=True):
        ready=ensure_source_ready(base);results=[query_packet(base,t,detail=detail) for t in topics]
        after=ensure_source_ready(base)
        if ready.get('save_set_id')!=after.get('save_set_id'):raise EngineError('QUERY_BATCH_SOURCE_CHANGED')
        return {'packet':'QUERY_BATCH_V1','save_set_id':ready.get('save_set_id'),'results':results}

def _mobile_contract_errors(base,state,tasks,parent_snapshot=None):
    if not _mobile_contract(state):return []
    errors=[]
    for task in tasks.get('active_tasks') or []:
        mon=_task_monitor(tasks,task);tid=task.get('task_id');cond=mon.get('watch_condition')
        if mon.get('event_driven') and mon.get('mode')=='external_wait':
            if not isinstance(cond,dict) or cond.get('schema')!='WATCH_CONDITION_V1' or cond.get('operator')!='fingerprint_changed' or not cond.get('sources') or not mon.get('requires_ai_review'):errors.append('WATCH_SIGNAL_CONTRACT:'+str(tid))
            elif not re.fullmatch('[0-9a-f]{64}',str(cond.get('baseline_digest') or '')):errors.append('WATCH_BASELINE_INVALID:'+str(tid))
            else:
                try:_watch_condition_digest(state,cond)
                except Exception:errors.append('WATCH_SOURCE_MISSING:'+str(tid))
        rule=(task.get('runtime_policy') or {}).get('settlement_rule') or {};cfg=rule.get('deterministic_unit_sales') or {}
        if cfg.get('catalog_source'):
            try:_catalog_sales_inputs(cfg,state,parse_iso(state['game_time']))
            except Exception as exc:errors.append(str(exc))
        if mon.get('resolver')=='progress_rule_v1':
            pr=(task.get('runtime_policy') or {}).get('progress_rule')
            errors.extend(_validate_progress_rule(pr))
            try:
                obj,p=_automation_root(state,tasks,pr['target']);v=get_by_path(obj,p)
                if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v):errors.append('PROGRESS_TARGET_NOT_NUMERIC:'+str(tid))
            except Exception:errors.append('PROGRESS_TARGET_MISSING:'+str(tid))
    if parent_snapshot:
        old=read_json(Path(parent_snapshot['dir'])/'state.json');a=parse_iso(old.get('game_time'));b=parse_iso(state.get('game_time'))
        if a and b and b-a>dt.timedelta(hours=24):errors.append('SINGLE_ADVANCE_HARD_MAX_24H')
    pending=(state.get('engine_runtime') or {}).get('pending_turn')
    if pending:
        a=parse_iso(pending.get('started_at'));b=parse_iso(pending.get('requested_until'));now=parse_iso(state.get('game_time'))
        if pending.get('schema')!='PENDING_TURN_V1' or not a or not b or not now or not a<=now<=b or b-a>dt.timedelta(hours=24):errors.append('PENDING_TURN_WINDOW_INVALID')
    funds=(state.get('summary') or {}).get('funds') or {}
    for key in ('gold','grey'):
        val=funds.get(key)
        if isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val):errors.append('FUNDS_INVALID:'+key)
        elif abs(val-_money_currency(val,key))>1e-7:errors.append('FUNDS_PRECISION_'+str(MONEY_DECIMAL_PLACES[key])+':'+key)
    core=_mobile_fleet_core(state)
    for key,row in core.items():
        if isinstance(row,dict) and not row.get('complete',True):errors.append('FLEET_REPORT_BINDING_INCOMPLETE:'+key)
    return errors

def _session_persist_barrier(session_id,meta,stage,advance_result,version,scope,publish):
    state=read_json(stage/'state.json')
    if not _mobile_contract(state) and (meta.get('barrier') or {}).get('kind') not in {'scheduler_continuation','business_reconciliation','task_execution_uncovered','story_consequence_ai','story_consequence_authorization'}:return advance_result
    pending={'schema':'PENDING_TURN_V1','started_at':meta['started_game_time'],'requested_until':meta['requested_until'],'report_since_seq':meta.get('report_since_seq'), 'report_since_time':meta.get('started_game_time'),'barrier':meta.get('barrier'),'status':'WAITING_SEMANTIC_RESOLUTION'}
    state.setdefault('engine_runtime',{})['pending_turn']=pending;_write_authority_json(stage/'state.json',state)
    _append_engine_history(stage/'events.jsonl',{'event_id':'PAUSE-'+session_id+'-'+uuid.uuid4().hex[:8],'game_time':state['game_time'],'type':'turn_pause','summary':'保存已执行部分与待处理语义屏障；不代表屏障已解决。','source':f'GAME ENGINE v{ENGINE_VERSION} session','changes':[{'target':'STATE.engine_runtime.pending_turn','action':'persist_pending_turn'}],'authority_files':['state.json']})
    meta['status']='READY_TO_COMMIT';_write_turn_session_meta(session_id,meta)
    result=_turn_session_commit_ready(session_id,meta,stage,version,scope,publish)
    if result.get('status') in ('COMMITTED','PAUSED_COMMITTED'):
        result.update({'status':'PAUSED_COMMITTED','pending_turn':pending,'semantic_barrier':meta.get('barrier'),'next_action':'session resume; resolve returned barrier with session apply; then session advance','source_sync':_source_transport_sync_status(ROOT,(result.get('save') or {}).get('save_set_id') if isinstance(result.get('save'),dict) else None)})
        if (meta.get('barrier') or {}).get('kind') in ('story_consequence_ai','story_consequence_authorization'):result['next_action']='storyprepare; authorized story_turn/story_setup resolves the node; session resume re-evaluates the current timeline'
    return result

