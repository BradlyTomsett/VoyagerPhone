# === VOYAGER_DEV_MODULE: mechanics_hazards ===
def _record_mechanical_hazards(stage:Path,state:dict,events:List[dict])->List[dict]:
    out=[];recent=state.setdefault("engine_runtime",{}).setdefault("random_events",{}).setdefault("recent",[])
    for ev in events or []:
        if ev.get("requires_simulation",True):continue
        rec={k:copy.deepcopy(ev.get(k)) for k in ("event_id","family","time","severity","scope","table_id","template_id","mechanical_payload","materialization_mode")}
        recent.append(rec);del recent[:-16]
        extra_changes=_apply_mechanical_political_hazard_state(state,ev)
        changes=_routine_time_changes()+[{"target":"STATE.engine_runtime.random_events.recent","action":"append_mechanical_random_event"}]+extra_changes
        _append_engine_history(stage/"events.jsonl",{"event_id":str(ev.get("event_id")),"game_time":str(ev.get("time")),"type":"random_event_mechanical","summary":f"GAME ENGINE v{ENGINE_VERSION}表驱动物化机械随机事件：{ev.get('family')} / {ev.get('template_id')}。","changes":changes,"source":f"GAME ENGINE v{ENGINE_VERSION} random_event_table","authority_files":["state.json","tasks.json"],"random_event":True,"family":ev.get("family"),"mechanical_payload":copy.deepcopy(ev.get("mechanical_payload") or {})})
        out.append(rec)
    return out


def _roll_daily(ts: dt.datetime) -> str:
    return (ts+dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")


def _resolver_calder(stage: Path, state: dict, tasks: dict, task: dict, when: dt.datetime) -> dict:
    raise EngineError("CALDER_552_INDEPENDENT_RESOLVER_RETIRED: use the current MULTINATIONAL_INDUSTRY_CURRENT SETTLEMENT_RULE_V1")


def _sync_jinchuan_resource_network_current(state: dict, task: dict, iso: str, next_iso: Optional[str]=None, settlement: bool=False) -> dict:
    """Synchronize the canonical JinChuan resource-network mirror from the active task.

    The task carries the currently authorized mechanical daily totals; the resource-network
    object is a current-state query surface and must never lag behind the resolver that books
    those totals. Construction events may update capacity before settlement; daily settlement
    additionally rolls last/next timestamps.
    """
    td=task.setdefault("task_data",{})
    try:rn=get_by_path(state,"world_state_overrides.mining_and_industry.jinchuan_resource_network_current")
    except Exception as ex:raise EngineError(f"JINCHUAN_RESOURCE_NETWORK_CURRENT_MISSING:{ex}")
    if not isinstance(rn,dict):raise EngineError("JINCHUAN_RESOURCE_NETWORK_CURRENT_INVALID")
    gold=_money_currency(td.get("daily_gold",td.get("last_total_gold",0)) or 0,'gold');grey=_money_currency(td.get("daily_grey",td.get("last_total_grey",0)) or 0,'grey')
    mb=int(td.get("mining_bases",rn.get("mining_base_count",0)) or 0);sb=int(td.get("fixed_salvage_bases",rn.get("fixed_salvage_base_count",0)) or 0)
    rn.update({"as_of":iso,"mining_base_count":mb,"fixed_salvage_base_count":sb,"unified_daily_gold":gold,"unified_daily_grey":grey})
    if settlement:
        if not next_iso:raise EngineError("JINCHUAN_RESOURCE_NETWORK_NEXT_SETTLEMENT_REQUIRED")
        rn["last_settlement_at"]=iso;rn["next_settlement_at"]=next_iso
    return rn


def _resolver_jinchuan(stage: Path, state: dict, tasks: dict, task: dict, when: dt.datetime) -> dict:
    td=task.setdefault("task_data",{});gold=_money_currency(td.get("daily_gold",td.get("last_total_gold",200435.2995)) or 0,'gold');grey=_money_currency(td.get("daily_grey",td.get("last_total_grey",52878)) or 0,'grey');iso=when.strftime("%Y-%m-%dT%H:%M:%S");nxt=_roll_daily(when)
    _finance_credit(state,"gold",gold);_finance_credit(state,"grey",grey)
    jf=state.setdefault("jinchuan_fleet",{});jf["latest_daily_financial_settlement"]={"at":iso,"total_gold":gold,"total_grey":grey,"gold":gold,"grey":grey,"status":"booked","note":f"{when.strftime('%m-%d %H:%M')}：GAME ENGINE自动统一日结；无已确认重大事故/显著资源衰减。"}
    td.update({"last_settlement_at":iso,"last_total_gold":gold,"last_total_grey":grey,"next_settlement_at":nxt});mb=int(td.get("mining_bases",0) or 0);sb=int(td.get("fixed_salvage_bases",0) or 0)
    if not _task_uses_derived_view(task):
        task["current_status"]=f"{when.strftime('%m-%d %H:%M')}金川{mb}矿+{sb}固定打捞自动日结完成，+{gold:,.4f}金币/+{grey}灰币.";task["next_trigger"]=f"{(when+dt.timedelta(days=1)).strftime('%Y-%m-%d %H:%M')}下一次自动日结；重大异常由事件机制另行触发。"
    mon=task["runtime_policy"]["monitor"];mon["last_reviewed_at"]=iso;mon["next_review_at"]=nxt
    _sync_jinchuan_resource_network_current(state,task,iso,nxt,settlement=True)
    _append_engine_history(stage/"events.jsonl",{"event_id":f"AUTO-JINCHUAN-{when.strftime('%Y%m%d-%H%M')}","game_time":iso,"type":"economic_settlement","summary":f"GAME ENGINE v{ENGINE_VERSION}自动结算金川商业矿业与固定打捞，+{gold:,.4f}金币/+{grey}灰币。","changes":_routine_time_changes()+[{"target":"STATE.summary.funds","action":"add_jinchuan_daily_income"},{"target":"STATE.jinchuan_fleet.latest_daily_financial_settlement","action":"record_daily_settlement"},{"target":"STATE.world_state_overrides.mining_and_industry.jinchuan_resource_network_current","action":"sync_current_resource_network"},{"target":"TASKS.active_tasks","action":"roll_deterministic_resolver"}],"source":f"GAME ENGINE v{ENGINE_VERSION} resolver jinchuan_daily_settlement_v1","authority_files":["state.json","tasks.json"],"source_task_id":task.get("task_id"),"finance":{"account":"jinchuan_operations","fleet":"jinchuan","gold":gold,"grey":grey,"realized":True}})
    return {"task_id":task.get("task_id"),"resolver":"jinchuan_daily_settlement_v1","gold":gold,"grey":grey}


def _deterministic_range(key: str, lo: int, hi: int) -> int:
    if hi<lo:lo,hi=hi,lo
    n=int(sha256_bytes(key.encode("utf-8"))[:16],16);return lo+(n%(hi-lo+1))


def _resolver_research_sales(stage: Path, state: dict, tasks: dict, task: dict, when: dt.datetime) -> dict:
    td=task.setdefault("task_data",{});price=_money4(td.get("price_gold_per_copy",25) or 25);pids=list(td.get("packages") or []);ranges=td.get("sales_ranges") or {};iso=when.strftime("%Y-%m-%dT%H:%M:%S");nxt=_roll_daily(when)
    prog=get_by_path(state,"world_state_overrides.markets_and_procurement.research_data_sales_program");cum=prog.setdefault("sales_cumulative",{});by=cum.setdefault("by_package",{});rounds={};total=0
    for pid in pids:
        rr=ranges.get(pid) or [8,16];lo=int(rr[0]);hi=int(rr[1]);cnt=_deterministic_range(f"RESEARCH_SALES_V1|{iso}|{pid}",lo,hi);rounds[pid]=cnt;total+=cnt
        rec=by.setdefault(pid,{"copies":0,"gold":0,"buyers_breakdown":{}});rec["copies"]=int(rec.get("copies",0) or 0)+cnt;rec["gold"]=_money_add4(rec.get("gold",0) or 0,_money_mul4(cnt,price))
    gold=_money_mul4(total,price);_finance_credit(state,"gold",gold);cum["copies"]=int(cum.get("copies",0) or 0)+total;cum["gold"]=_money_add4(cum.get("gold",0) or 0,gold);cum["as_of"]=iso;cum["last_round"]={**rounds,"at":iso,"copies":total,"gold":gold,"note":f"GAME ENGINE v{ENGINE_VERSION} deterministic research_sales_daily_v1；仅售既有授权去敏数字备份。"};prog["next_review_at"]=nxt
    td["copies_sold_cumulative"]=cum["copies"];td["gold_booked_cumulative"]=cum["gold"];td["last_review_at"]=iso
    if not _task_uses_derived_view(task):
        task["current_status"]=f"{when.strftime('%m-%d %H:%M')}科研数据自动销售完成：{total}份、+{gold:,.0f}金币；累计{cum['copies']}份/{cum['gold']:,.0f}金币。";task["next_trigger"]=f"{(when+dt.timedelta(days=1)).strftime('%Y-%m-%d %H:%M')}下一轮自动销售汇总。"
    mon=task["runtime_policy"]["monitor"];mon["last_reviewed_at"]=iso;mon["next_review_at"]=nxt
    _append_engine_history(stage/"events.jsonl",{"event_id":f"AUTO-RESEARCH-SALES-{when.strftime('%Y%m%d-%H%M')}","game_time":iso,"type":"economic_settlement","summary":f"GAME ENGINE v{ENGINE_VERSION}自动完成8类科研数据销售，共{total}份、+{gold:,.0f}金币。","changes":_routine_time_changes()+[{"target":"STATE.summary.funds","action":"add_research_sales"},{"target":"STATE.world_state_overrides.markets_and_procurement.research_data_sales_program","action":"roll_deterministic_sales"},{"target":"TASKS.active_tasks","action":"roll_deterministic_resolver"}],"source":f"GAME ENGINE v{ENGINE_VERSION} resolver research_sales_daily_v1","authority_files":["state.json","tasks.json"],"source_task_id":task.get("task_id"),"finance":{"account":"voyager_research_data_sales","fleet":"voyager","gold":gold,"grey":0,"realized":True}})
    return {"task_id":task.get("task_id"),"resolver":"research_sales_daily_v1","gold":gold,"grey":0,"copies":total,"by_package":rounds}



SETTLEMENT_RULE_SCHEMA="SETTLEMENT_RULE_V1"

def _v130_layer__settlement_state_change_targets_01(rule:dict)->List[str]:
    """Enumerate STATE roots that a SETTLEMENT_RULE_V1 resolver may mutate.

    Authority coverage is fail-closed, so every data-rule write must be surfaced in
    the resolver's HISTORY event instead of relying on broad fund/task summaries.
    """
    out=[]
    for upd in rule.get('updates',[]) or []:
        if isinstance(upd,dict):
            t=str(upd.get('target') or '')
            if t.startswith(('STATE.','state:')):out.append(t)
    snap=str(rule.get('snapshot_target') or '')
    if snap.startswith(('STATE.','state:')):out.append(snap)
    ds=rule.get('deterministic_unit_sales') or {}
    if isinstance(ds,dict):
        for k in ('ledger_target','authoritative_cumulative_qty_target','authoritative_cumulative_gold_target','current_round_target','last_round_target','last_sales_target','next_sales_target'):
            target=str(ds.get(k) or '')
            if target.startswith(('STATE.','state:')):out.append(target)
    return list(dict.fromkeys(out))

def _v130_layer__settlement_read_value_01(spec:Any,state:dict,tasks:dict,task:dict,vars:dict):
    if isinstance(spec,(int,float)) and not isinstance(spec,bool):return spec
    if isinstance(spec,dict):
        if 'var' in spec:return vars.get(str(spec['var']))
        if 'from' in spec:
            src=str(spec['from'])
            if src.startswith(('STATE.','state:')):return get_by_path(state,src[6:])
            if src.startswith(('TASKS.self.task_data.','tasks:self.task_data.')):
                return get_by_path(task.setdefault('task_data',{}),src[len('TASKS.self.task_data.'):])
    raise EngineError(f'SETTLEMENT_VALUE_INVALID:{spec!r}')

def _v130_layer__settlement_set_path_01(target:str,value:Any,state:dict,tasks:dict,task:dict)->None:
    if target.startswith(('STATE.','state:')):root,path=state,target[6:]
    elif target.startswith(('TASKS.self.task_data.','tasks:self.task_data.')):root,path=task.setdefault('task_data',{}),target[len('TASKS.self.task_data.'):]
    else:raise EngineError(f'SETTLEMENT_TARGET_INVALID:{target}')
    par,key=_dot_parent(root,path);par[key]=copy.deepcopy(value)

def _v130_layer__settlement_target_read_01(target:str,state:dict,tasks:dict,task:dict):
    if target.startswith(("STATE.","state:")):return get_by_path(state,target[6:])
    if target.startswith(("TASKS.self.task_data.","tasks:self.task_data.")):return get_by_path(task.setdefault("task_data",{}),target[len("TASKS.self.task_data."):])
    raise EngineError(f"SETTLEMENT_TARGET_INVALID:{target}")


def _settlement_deterministic_unit_sales(rule:dict,state:dict,tasks:dict,task:dict,when:dt.datetime,vars:dict)->Optional[dict]:
    cfg=rule.get("deterministic_unit_sales")
    if not isinstance(cfg,dict):return None
    prices=None
    if cfg.get('catalog_source'):
        items,ranges,prices=_catalog_sales_inputs(cfg,state,when);unit_price=next(iter(prices.values()),0)
    else:
        items=_settlement_read_value(cfg.get("items"),state,tasks,task,vars);ranges=_settlement_read_value(cfg.get("ranges"),state,tasks,task,vars);unit_price=float(_settlement_read_value(cfg.get("unit_price"),state,tasks,task,vars) or 0)
    if not isinstance(items,list) or not all(isinstance(x,str) and x for x in items):raise EngineError("SETTLEMENT_UNIT_SALES_ITEMS_INVALID")
    if not isinstance(ranges,dict):raise EngineError("SETTLEMENT_UNIT_SALES_RANGES_INVALID")
    namespace=str(cfg.get("namespace") or "DETERMINISTIC_UNIT_SALES_V1");iso=str(vars["iso"]);by_round={};total=0
    ledger_target=str(cfg.get("ledger_target") or "")
    if not ledger_target.startswith(("STATE.","state:")):raise EngineError("SETTLEMENT_UNIT_SALES_LEDGER_TARGET_REQUIRED")
    ledger=get_by_path(state,ledger_target[6:])
    if not isinstance(ledger,dict):raise EngineError("SETTLEMENT_UNIT_SALES_LEDGER_NOT_OBJECT")
    cum=ledger.setdefault("sales_cumulative",{});by=cum.setdefault("by_package",{})
    aq=str(cfg.get("authoritative_cumulative_qty_target") or "");ag=str(cfg.get("authoritative_cumulative_gold_target") or "")
    overall_copies_before=int(_settlement_target_read(aq,state,tasks,task) or 0) if aq else int(cum.get("copies",0) or 0)
    overall_gold_before=_money4(_settlement_target_read(ag,state,tasks,task) or 0) if ag else _money4(cum.get("gold",0) or 0)
    item_gold={}
    for item in items:
        unit_price=prices[item] if prices is not None else unit_price
        rr=ranges.get(item)
        if not isinstance(rr,list) or len(rr)!=2:raise EngineError(f"SETTLEMENT_UNIT_SALES_RANGE_INVALID:{item}")
        lo=int(rr[0]);hi=int(rr[1]);cnt=_deterministic_range(f"{namespace}|{iso}|{item}",lo,hi);by_round[item]=cnt;total+=cnt
        rec=by.setdefault(item,{"copies":0,"gold":0,"buyers_breakdown":{}});rec["copies"]=int(rec.get("copies",0) or 0)+cnt;rec["gold"]=_money_add4(rec.get("gold",0) or 0,_money_mul4(cnt,unit_price))
        item_gold[item]=_money_mul4(cnt,unit_price)
    gold=_money_value4(sum(_money_units4(x) for x in item_gold.values()))
    cum["copies"]=int(cum.get("copies",0) or 0)+total;cum["gold"]=_money_add4(cum.get("gold",0) or 0,gold);cum["as_of"]=iso
    round_note=str(cfg.get("round_note") or f"GAME ENGINE v{ENGINE_VERSION} deterministic unit sales data rule.")
    cum["last_round"]={**by_round,"at":iso,"copies":total,"gold":gold,"note":round_note};ledger["next_review_at"]=str(vars["next_iso"])
    overall_copies=overall_copies_before+total;overall_gold=_money_add4(overall_gold_before,gold)
    if aq:_settlement_set_path(aq,overall_copies,state,tasks,task)
    if ag:_settlement_set_path(ag,overall_gold,state,tasks,task)
    round_obj={"at":iso,"copies":total,"gold":gold,"status":"booked","note":round_note}
    for k,value in (("current_round_target",round_obj),("last_round_target",round_obj),("last_sales_target",iso),("next_sales_target",str(vars["next_iso"]))):
        target=str(cfg.get(k) or "")
        if target:_settlement_set_path(target,value,state,tasks,task)
    qty_for_task=overall_copies if aq else cum["copies"];gold_for_task=overall_gold if ag else cum["gold"]
    for target,value in ((cfg.get("task_cumulative_qty_target"),qty_for_task),(cfg.get("task_cumulative_gold_target"),gold_for_task),(cfg.get("task_last_review_target"),iso)):
        if isinstance(target,str) and target:_settlement_set_path(target,value,state,tasks,task)
    return {"copies":total,"gold":gold,"by_item":by_round,"item_count":len(items),"unit_price":unit_price if prices is None or len(set(prices.values()))<=1 else None,"by_item_gold":item_gold,"namespace":namespace,"cumulative_copies":qty_for_task,"cumulative_gold":gold_for_task}

def _resolver_settlement_rule(stage:Path,state:dict,tasks:dict,task:dict,when:dt.datetime)->dict:
    rp=task.get('runtime_policy') or {};rule=rp.get('settlement_rule') or (task.get('task_data') or {}).get('settlement_rule')
    if not isinstance(rule,dict) or rule.get('schema')!=SETTLEMENT_RULE_SCHEMA:raise EngineError(f'SETTLEMENT_RULE_MISSING:{task.get("task_id")}')
    iso=when.strftime('%Y-%m-%dT%H:%M:%S');repeat=int(rule.get('repeat_seconds') or 86400);nxt=(when+dt.timedelta(seconds=repeat)).strftime('%Y-%m-%dT%H:%M:%S');vars={'iso':iso,'next_iso':nxt}
    series=_settlement_deterministic_unit_sales(rule,state,tasks,task,when,vars)
    if series:vars.update({'series_gold':series['gold'],'series_qty':series['copies'],'series_by_item':series['by_item'],'series_item_count':series['item_count']})
    amounts=rule.get('amounts') or {};gold=_money_currency(_settlement_read_value(amounts.get('gold',0),state,tasks,task,vars) or 0,'gold');grey=_money_currency(_settlement_read_value(amounts.get('grey',0),state,tasks,task,vars) or 0,'grey');vars.update({'gold':gold,'grey':grey})
    template_vars=rule.get('template_vars') or {}
    if not isinstance(template_vars,dict):raise EngineError('SETTLEMENT_TEMPLATE_VARS_INVALID')
    for name,spec in template_vars.items():
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',str(name)):raise EngineError('SETTLEMENT_TEMPLATE_VAR_NAME_INVALID:'+str(name))
        vars[str(name)]=_settlement_read_value(spec,state,tasks,task,vars)
    _finance_credit(state,'gold',gold);_finance_credit(state,'grey',grey)
    for upd in rule.get('updates',[]) or []:
        if not isinstance(upd,dict):continue
        val=_settlement_read_value(upd.get('value'),state,tasks,task,vars) if isinstance(upd.get('value'),dict) else upd.get('value');_settlement_set_path(str(upd.get('target') or ''),val,state,tasks,task)
    snap_target=rule.get('snapshot_target')
    if isinstance(snap_target,str) and snap_target:
        snap={'at':iso,'total_gold':gold,'total_grey':int(grey) if float(grey).is_integer() else grey,'gold':gold,'grey':int(grey) if float(grey).is_integer() else grey,'status':'booked','note':str(rule.get('snapshot_note') or f'{when.strftime("%m-%d %H:%M")}：GAME ENGINE数据规则自动日结。')};_settlement_set_path(snap_target,snap,state,tasks,task)
    mon=task.setdefault('runtime_policy',{}).setdefault('monitor',{});mon['last_reviewed_at']=iso;mon['next_review_at']=nxt
    td=task.get('task_data') or {}
    for key in ('last_settlement_at','latest_settlement_at','last_review_at'):
        if key in td:td[key]=iso
    for key in ('next_settlement_at','next_review_at'):
        if key in td:td[key]=nxt
    # This older current mirror has a historical as_of but a live scheduler pointer.
    if task.get('task_id')=='TSK-CALDER-INDUSTRIES-302':
        mirror=get_by_path(state,'world_state_overrides.mining_and_industry.multinational_industry_current')
        mirror['next_settlement_at']=nxt
    fmt={'gold':f'{gold:,.4f}','grey':f'{grey:g}','time':when.strftime('%m-%d %H:%M'),'next_time':(when+dt.timedelta(seconds=repeat)).strftime('%Y-%m-%d %H:%M'),'copies':int((series or {}).get('copies',0)),'item_count':int((series or {}).get('item_count',0))}
    fmt.update({k:v for k,v in vars.items() if k not in {'gold','grey','iso','next_iso'}})
    if not _task_uses_derived_view(task):
        task['current_status']=str(rule.get('status_template') or '自动日结完成：+{gold}金币/+{grey}灰币。').format(**fmt);task['next_trigger']=str(rule.get('next_trigger_template') or '{next_time}下一次自动日结。').format(**fmt)
    account=str((rule.get('finance') or {}).get('account') or 'automation_settlement');fleet=(rule.get('finance') or {}).get('fleet');fin={'account':account,'gold':gold,'grey':grey,'realized':True}
    if fleet:fin['fleet']=fleet
    changes=_routine_time_changes()+[{'target':'STATE.summary.funds','action':'data_rule_settlement'},{'target':'TASKS.active_tasks','action':'roll_deterministic_resolver'}]
    for target in _settlement_state_change_targets(rule):
        changes.append({'target':target,'action':'deterministic_settlement_rule_write'})
    if task.get('task_id')=='TSK-CALDER-INDUSTRIES-302':changes.append({'target':'state:world_state_overrides.mining_and_industry.multinational_industry_current.next_settlement_at','action':'derive_live_schedule_only_preserve_historical_as_of'})
    _append_engine_history(stage/'events.jsonl',{'event_id':f'AUTO-SETTLE-{task.get("task_id")}-{when.strftime("%Y%m%d-%H%M")}', 'game_time':iso,'type':'economic_settlement','summary':str(rule.get('history_summary_template') or 'GAME ENGINE数据规则自动结算：+{gold}金币/+{grey}灰币。').format(**fmt),'changes':changes,'source':f'GAME ENGINE v{ENGINE_VERSION} {SETTLEMENT_RULE_SCHEMA}','authority_files':['state.json','tasks.json'],'source_task_id':task.get('task_id'),'finance':fin,'deterministic_series':series})
    return {'task_id':task.get('task_id'),'resolver':'settlement_rule_v1','gold':gold,'grey':grey,'time':iso,'deterministic_series':series}

AUTOMATION_RULE_SCHEMA="AUTOMATION_RULE_V1"
AUTOMATION_PRIMITIVES={"set","increment","append","transfer","consume","schedule","compare_set","emit_history"}

def _dot_parent(root_obj:dict,path:str):
    parts=[p for p in str(path).split('.') if p]
    if not parts:raise EngineError("AUTOMATION_PATH_EMPTY")
    cur=root_obj
    for p in parts[:-1]:
        if not isinstance(cur,dict) or p not in cur:raise EngineError(f"AUTOMATION_PATH_MISSING:{path}")
        cur=cur[p]
    if not isinstance(cur,dict):raise EngineError(f"AUTOMATION_PARENT_NOT_OBJECT:{path}")
    return cur,parts[-1]

def _automation_root(state:dict,tasks:dict,target:str):
    if target.startswith(("STATE.","state:")):return state,target[6:]
    if target.startswith('TASKS.task:'):
        tid,sep,path=target[len('TASKS.task:'):].partition('.')
        found=[t for t in tasks.get('active_tasks',[]) if t.get('task_id')==tid]
        if len(found)!=1 or not sep:raise EngineError('AUTOMATION_TASK_ID_UNRESOLVED:'+tid)
        return found[0],path
    if target.startswith(("TASKS.","tasks:")):return tasks,target[6:]
    raise EngineError(f"AUTOMATION_TARGET_FORBIDDEN:{target}")

def _automation_value(spec:Any,state:dict,tasks:dict):
    if isinstance(spec,dict) and set(spec)=={"from"}:
        root,path=_automation_root(state,tasks,str(spec["from"]));return get_by_path(root,path)
    return copy.deepcopy(spec)

def _apply_automation_action(action:dict,state:dict,tasks:dict)->dict:
    op=str(action.get("op") or "");target=str(action.get("target") or "")
    if op not in AUTOMATION_PRIMITIVES:raise EngineError(f"AUTOMATION_OP_INVALID:{op}")
    if _finance_runtime(state,create=False) is not None and (target.startswith('STATE.summary.funds') or str(action.get('dest') or '').startswith('STATE.summary.funds')):
        raise EngineError('AUTOMATION_FINANCE_DIRECT_WRITE_FORBIDDEN_USE_SETTLEMENT_OR_DOMAIN_COMMAND')
    if op=="emit_history":return {"op":op}
    root,path=_automation_root(state,tasks,target);parent,key=_dot_parent(root,path)
    if op=="set":parent[key]=_automation_value(action.get("value"),state,tasks)
    elif op=="increment":
        old=parent.get(key);val=_automation_value(action.get("value"),state,tasks)
        if not isinstance(old,(int,float)) or isinstance(old,bool) or not isinstance(val,(int,float)) or isinstance(val,bool):raise EngineError(f"AUTOMATION_INCREMENT_NUMERIC:{target}")
        parent[key]=old+val
    elif op=="append":
        if not isinstance(parent.get(key),list):raise EngineError(f"AUTOMATION_APPEND_LIST:{target}")
        parent[key].append(_automation_value(action.get("value"),state,tasks))
    elif op in {"consume","transfer"}:
        qty=_automation_value(action.get("qty"),state,tasks)
        if not isinstance(qty,(int,float)) or qty<0:raise EngineError("AUTOMATION_QTY_INVALID")
        old=parent.get(key)
        if not isinstance(old,(int,float)) or old<qty:raise EngineError(f"AUTOMATION_INSUFFICIENT:{target}")
        parent[key]=old-qty
        if op=="transfer":
            dest=str(action.get("dest") or "");dr,dp=_automation_root(state,tasks,dest);dpar,dk=_dot_parent(dr,dp);dv=dpar.get(dk)
            if not isinstance(dv,(int,float)):raise EngineError(f"AUTOMATION_DEST_NUMERIC:{dest}")
            dpar[dk]=dv+qty
    elif op=="schedule":
        base=parse_iso(action.get("from_time") or state.get("game_time"));seconds=int(action.get("after_seconds") or 0)
        if base is None or seconds<0:raise EngineError("AUTOMATION_SCHEDULE_INVALID")
        parent[key]=(base+dt.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S")
    elif op=="compare_set":
        cur=parent.get(key);cmp=action.get("compare","gte");threshold=_automation_value(action.get("threshold"),state,tasks)
        import operator
        fn={'gte':operator.ge,'gt':operator.gt,'lte':operator.le,'lt':operator.lt,'eq':operator.eq}.get(cmp)
        ok=fn(cur,threshold) if fn is not None else None
        if ok is None:raise EngineError("AUTOMATION_COMPARE_INVALID")
        if ok:parent[key]=_automation_value(action.get("value"),state,tasks)
    return {"op":op,"target":target}

def _apply_task_self_update(task:dict,upd:dict,state:dict,tasks:dict)->dict:
    op=str(upd.get("op") or "set");path=str(upd.get("path") or "").strip()
    if op not in {"set","increment","schedule"}:raise EngineError(f"AUTOMATION_SELF_OP_INVALID:{op}")
    if not path:raise EngineError("AUTOMATION_SELF_PATH_EMPTY")
    par,key=_dot_parent(task,path)
    if op=="set":par[key]=_automation_value(upd.get("value"),state,tasks)
    elif op=="increment":
        old=par.get(key);val=_automation_value(upd.get("value"),state,tasks)
        if not isinstance(old,(int,float)) or isinstance(old,bool) or not isinstance(val,(int,float)) or isinstance(val,bool):raise EngineError(f"AUTOMATION_SELF_INCREMENT_NUMERIC:{path}")
        par[key]=old+val
    else:
        base=parse_iso(upd.get("from_time") or state.get("game_time"));seconds=int(upd.get("after_seconds") or 0)
        if base is None or seconds<0:raise EngineError("AUTOMATION_SELF_SCHEDULE_INVALID")
        par[key]=(base+dt.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S")
    return {"op":f"self_{op}","target":f"TASKS.self.{path}"}

def _resolver_automation(stage:Path,state:dict,tasks:dict,task:dict,when:dt.datetime)->dict:
    rp=task.get("runtime_policy") or {};rule=rp.get("automation") or (task.get("task_data") or {}).get("automation")
    if not isinstance(rule,dict) or rule.get("schema")!=AUTOMATION_RULE_SCHEMA:raise EngineError(f"AUTOMATION_RULE_MISSING:{task.get('task_id')}")
    actions=rule.get("actions") or []
    if not isinstance(actions,list) or not actions:raise EngineError("AUTOMATION_ACTIONS_EMPTY")
    changes=[]
    for a in actions:
        if not isinstance(a,dict):raise EngineError("AUTOMATION_ACTION_NOT_OBJECT")
        changes.append(_apply_automation_action(a,state,tasks))
    for upd in rule.get("self_updates",[]) or []:
        if not isinstance(upd,dict):raise EngineError("AUTOMATION_SELF_UPDATE_NOT_OBJECT")
        changes.append(_apply_task_self_update(task,upd,state,tasks))
    mon=task.setdefault("runtime_policy",{}).setdefault("monitor",{});interval=int(rule.get("repeat_seconds") or 0)
    if interval>0:
        iso=when.strftime("%Y-%m-%dT%H:%M:%S");next_iso=(when+dt.timedelta(seconds=interval)).strftime("%Y-%m-%dT%H:%M:%S");mon["last_reviewed_at"]=iso;mon["next_review_at"]=next_iso
        fmt={"time":when.strftime("%m-%d %H:%M"),"next_time":(when+dt.timedelta(seconds=interval)).strftime("%Y-%m-%d %H:%M"),"iso":iso,"next_iso":next_iso}
        if not _task_uses_derived_view(task):
            if rule.get("status_template") is not None:task["current_status"]=str(rule.get("status_template")).format(**fmt)
            if rule.get("next_trigger_template") is not None:task["next_trigger"]=str(rule.get("next_trigger_template")).format(**fmt)
    summary=str(rule.get("history_summary") or f"GAME ENGINE v{ENGINE_VERSION}执行自动化规则{task.get('task_id')}。")
    audit_changes=_routine_time_changes()+[{"target":x.get("target") or "automation","action":x.get("op")} for x in changes if x.get("op")!="emit_history"]
    if any(str(x.get("target") or "").startswith("TASKS.self.") for x in changes) or interval>0 or rule.get("status_template") is not None or rule.get("next_trigger_template") is not None:
        audit_changes.append({"target":"TASKS.active_tasks","action":"roll_automation_task_current_state"})
    _append_engine_history(stage/"events.jsonl",{"event_id":f"AUTO-RULE-{task.get('task_id')}-{when.strftime('%Y%m%d-%H%M%S')}","game_time":when.strftime("%Y-%m-%dT%H:%M:%S"),"type":"automation_rule","summary":summary,"changes":audit_changes,"source":f"GAME ENGINE v{ENGINE_VERSION} {rule.get('schema')}","authority_files":["state.json","tasks.json"],"source_task_id":task.get("task_id")})
    return {"task_id":task.get("task_id"),"resolver":str(mon.get("resolver") or "automation_rule_v1"),"actions":changes}



def _validate_mechanical_condition(cond:Any)->List[str]:
    if not isinstance(cond,dict):return ["condition_not_object"]
    path=cond.get("path");op=cond.get("op");errs=[]
    if not isinstance(path,str) or not (path.startswith(("STATE.","state:")) or path.startswith(("TASKS.","tasks:"))):errs.append("condition_path_must_be_STATE_or_TASKS")
    if op not in {"eq","ne","gt","gte","lt","lte"}:errs.append("condition_op_invalid")
    if "value" not in cond:errs.append("condition_value_missing")
    return errs


def _validate_world_process_rule(rule:Any)->List[str]:
    """Validate a sealed, data-only world-state transition table.

    No implicit probabilities, rates or narrative facts are allowed. Every transition must
    have explicit mechanical conditions/actions already supported by AUTOMATION_RULE_V1.
    """
    if not isinstance(rule,dict) or rule.get("schema")!=WORLD_PROCESS_RULE_SCHEMA:return [f"world_process_rule_v1 requires {WORLD_PROCESS_RULE_SCHEMA}"]
    errs=[];trans=rule.get("transitions")
    if not isinstance(trans,list) or not trans:errs.append("world_process_rule.transitions_empty")
    else:
        ids=[]
        for i,tr in enumerate(trans):
            if not isinstance(tr,dict):errs.append(f"world_process_rule.transitions[{i}]_not_object");continue
            tid=tr.get("id")
            if not isinstance(tid,str) or not tid:errs.append(f"world_process_rule.transitions[{i}].id_invalid")
            else:ids.append(tid)
            conds=tr.get("when") or []
            if not isinstance(conds,list):errs.append(f"world_process_rule.transitions[{i}].when_invalid")
            else:
                for ce in conds:
                    errs += [f"world_process_rule.transitions[{i}].{x}" for x in _validate_mechanical_condition(ce)]
            acts=tr.get("actions") or []
            if not isinstance(acts,list) or not acts:errs.append(f"world_process_rule.transitions[{i}].actions_empty")
            else:
                for a in acts:
                    if not isinstance(a,dict) or a.get("op") not in AUTOMATION_PRIMITIVES:errs.append(f"world_process_rule.transitions[{i}].action_invalid")
                    elif a.get("op")=="emit_history":pass
                    elif not isinstance(a.get("target"),str) or not (str(a.get("target")).startswith(("STATE.","state:")) or str(a.get("target")).startswith(("TASKS.","tasks:"))):errs.append(f"world_process_rule.transitions[{i}].action_target_invalid")
        if len(ids)!=len(set(ids)):errs.append("world_process_rule.transition_ids_duplicate")
    if rule.get("repeat_seconds") is not None:
        x=rule.get("repeat_seconds")
        if not isinstance(x,int) or isinstance(x,bool) or x<=0:errs.append("world_process_rule.repeat_seconds_invalid")
    return errs


def _task_numeric_progress_fields(task:Any)->List[dict]:
    """Return explicit numeric progress surfaces from task_data.

    This deliberately keys on field semantics instead of task type.  A task that owns an
    exact progress/completion percentage is claiming a mechanical current fact; from
    V10.148 onward that fact must not be advanced by a semantic watcher.
    """
    td=(task or {}).get("task_data") if isinstance(task,dict) else None
    out=[]
    def walk(obj:Any,path:str,depth:int)->None:
        if depth>5:return
        if isinstance(obj,dict):
            for k,v in obj.items():
                kp=f"{path}.{k}" if path else str(k)
                _ks=str(k)
                _historical_prefix=_ks.lower().startswith(("final_","last_","initial_","previous_","confirmed_final_"))
                if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v)) and PROGRESS_NUMERIC_FIELD_RE.search(_ks) and not _historical_prefix:
                    out.append({"path":kp,"value":float(v)})
                elif isinstance(v,(dict,list)):walk(v,kp,depth+1)
        elif isinstance(obj,list):
            for i,v in enumerate(obj):
                if isinstance(v,(dict,list)):walk(v,f"{path}[{i}]",depth+1)
    walk(td,"task_data",0)
    return out


def _continuous_progress_contract_enabled(tasks_doc:Any)->bool:
    """Return whether the current save has activated the V1 continuous-progress contract.

    New engine upgrades write an explicit capability marker.  The save-version fallback
    keeps packages already created by v2.18.6 at V10.148+ compatible without relying on
    a project-specific absolute version for future upgrades.
    """
    if not isinstance(tasks_doc,dict):return False
    auto=tasks_doc.get("automation_schema") or {}
    if isinstance(auto,dict) and auto.get("continuous_progress_contract")==CONTINUOUS_PROGRESS_CONTRACT_SCHEMA:return True
    try:return parse_version(str(tasks_doc.get("save_version") or ('V99.99' if tasks_doc.get('manifest_ref') else 'V0.0')))>=CONTINUOUS_PROGRESS_LEGACY_SAVE_FALLBACK
    except Exception:return False


def _continuous_progress_legacy_signature(task:Any)->str:
    if not isinstance(task,dict):return ""
    rp=task.get("runtime_policy") or {};mon=rp.get("monitor") or {}
    payload={"task_id":task.get("task_id"),"resolver":mon.get("resolver"),"mode":mon.get("mode"),"requires_ai_review":mon.get("requires_ai_review"),"fields":_task_numeric_progress_fields(task)}
    return sha256_bytes(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8"))


def _continuous_progress_contract_errors(task:Any,enforce:bool=True)->List[str]:
    """Fail closed when ongoing exact progress is modeled as an AI watcher or TASKS mirror.

    Saves activate this contract through an explicit automation-schema marker.  During
    upgrade, pre-contract semantic progress tasks with no sealed mechanical rate receive
    a signature-bound legacy exemption; any material edit invalidates that exemption.
    """
    if not enforce or not isinstance(task,dict):return []
    if str(task.get("status") or "").lower() not in {"active","running","in_progress","monitoring"}:return []
    rp=task.get("runtime_policy") or {};mon=rp.get("monitor") or {};resolver=str(mon.get("resolver") or "")
    legacy=rp.get("continuous_progress_legacy_exemption")
    if isinstance(legacy,dict) and legacy.get("schema")==CONTINUOUS_PROGRESS_LEGACY_EXEMPTION_SCHEMA and legacy.get("signature")==_continuous_progress_legacy_signature(task):return []
    pr=rp.get("progress_rule") or (task.get("task_data") or {}).get("progress_rule")
    fields=_task_numeric_progress_fields(task)
    task_semantics=" ".join(str(task.get(k) or "") for k in ("type","title","name","phase"))
    in_scope=(resolver=="progress_rule_v1" or isinstance(pr,dict) or mon.get("mode")=="continuous" or bool(CONTINUOUS_PROGRESS_TASK_HINT_RE.search(task_semantics)))
    if not in_scope:return []
    incomplete=[f for f in fields if f.get("value",0)<100]
    progress_claimed=bool(incomplete or resolver=="progress_rule_v1" or isinstance(pr,dict))
    # Exact ongoing progress is a STATE current fact. Keeping another numeric copy in
    # task_data recreates the stale-mirror failure that caused the Blueash-9 incident.
    errs=[]
    if fields and progress_claimed:errs.append("continuous_numeric_progress_current_fact_must_live_in_STATE_not_task_data")
    if not progress_claimed:return errs
    if resolver!="progress_rule_v1":errs.append("continuous_numeric_progress_requires_progress_rule_v1")
    if mon.get("requires_ai_review") is not False:errs.append("continuous_numeric_progress_requires_ai_review_false; use a separate semantic anomaly watcher")
    if mon.get("mode") not in {"continuous","on_advance","scheduled"}:errs.append("continuous_numeric_progress_monitor_mode_invalid")
    if parse_iso(mon.get("last_reviewed_at")) is None:errs.append("continuous_numeric_progress_requires_last_reviewed_at_clock_origin")
    if resolver=="progress_rule_v1":
        errs.extend(_validate_progress_rule(pr))
        if isinstance(pr,dict) and isinstance(pr.get("target"),str) and not pr.get("target").startswith(("STATE.","state:")):
            errs.append("continuous_numeric_progress_target_must_be_canonical_STATE")
    return errs


def _activate_continuous_progress_contract(tasks:dict,source_save_version:str)->dict:
    """Activate the contract and grandfather only unchanged pre-contract semantic tasks."""
    auto=tasks.setdefault("automation_schema",{})
    auto["continuous_progress_contract"]=CONTINUOUS_PROGRESS_CONTRACT_SCHEMA
    exempted=[]
    for task in tasks.get("active_tasks",[]) or []:
        if not isinstance(task,dict):continue
        errs=_continuous_progress_contract_errors(task,True)
        if not errs:continue
        rp=task.get("runtime_policy") or {};mon=rp.get("monitor") or {};resolver=str(mon.get("resolver") or "")
        pr=rp.get("progress_rule") or (task.get("task_data") or {}).get("progress_rule")
        fields=_task_numeric_progress_fields(task)
        # A legacy semantic watcher may be preserved because no historical rate can be
        # invented. Malformed mechanical progress rules are never grandfathered.
        if fields and resolver!="progress_rule_v1" and not isinstance(pr,dict) and mon.get("mode") in {"continuous","on_advance"}:
            rp=task.setdefault("runtime_policy",{})
            rec={"schema":CONTINUOUS_PROGRESS_LEGACY_EXEMPTION_SCHEMA,"imported_from_save":str(source_save_version),"reason":"pre_contract_progress_without_sealed_rate"}
            rp["continuous_progress_legacy_exemption"]=rec
            rec["signature"]=_continuous_progress_legacy_signature(task)
            exempted.append(str(task.get("task_id") or ""))
    return {"schema":CONTINUOUS_PROGRESS_CONTRACT_SCHEMA,"legacy_exempted_task_ids":exempted}


def _validate_progress_rule(rule:Any)->List[str]:
    """Validate a fixed-rate progress rule; missing rate/bounds is a hard semantic barrier."""
    if not isinstance(rule,dict) or rule.get("schema")!=PROGRESS_RULE_SCHEMA:return [f"progress_rule_v1 requires {PROGRESS_RULE_SCHEMA}"]
    errs=[];target=rule.get("target");rate=rule.get("rate_per_second")
    if not isinstance(target,str) or not (target.startswith(("STATE.","state:")) or target.startswith(("TASKS.","tasks:"))):errs.append("progress_rule.target_invalid")
    if not isinstance(rate,(int,float)) or isinstance(rate,bool) or not math.isfinite(float(rate)) or float(rate)==0:errs.append("progress_rule.rate_per_second_invalid")
    for fld in ("minimum","maximum"):
        v=rule.get(fld)
        if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(float(v)):errs.append(f"progress_rule.{fld}_required_numeric")
    if isinstance(rule.get("minimum"),(int,float)) and isinstance(rule.get("maximum"),(int,float)) and float(rule["minimum"])>float(rule["maximum"]):errs.append("progress_rule.bounds_invalid")
    repeat=rule.get("repeat_seconds")
    if repeat is not None and (not isinstance(repeat,int) or isinstance(repeat,bool) or repeat<=0):errs.append("progress_rule.repeat_seconds_invalid")
    ms=rule.get("milestones",[])
    if not isinstance(ms,list):errs.append("progress_rule.milestones_invalid")
    else:
        for i,m in enumerate(ms):
            if not isinstance(m,dict) or not isinstance(m.get("threshold"),(int,float)) or isinstance(m.get("threshold"),bool) or not math.isfinite(float(m.get("threshold"))):errs.append(f"progress_rule.milestones[{i}]_invalid");continue
            acts=m.get("actions",[])
            if not isinstance(acts,list):errs.append(f"progress_rule.milestones[{i}].actions_invalid")
            else:
                for a in acts:
                    if not isinstance(a,dict) or a.get("op") not in AUTOMATION_PRIMITIVES:errs.append(f"progress_rule.milestones[{i}].action_invalid")
    return errs


def _condition_matches(cond:dict,state:dict,tasks:dict)->bool:
    root,path=_automation_root(state,tasks,str(cond.get("path") or ""));cur=get_by_path(root,path);val=_automation_value(cond.get("value"),state,tasks);op=cond.get("op")
    return {"eq":cur==val,"ne":cur!=val,"gt":cur>val,"gte":cur>=val,"lt":cur<val,"lte":cur<=val}[op]


def _resolver_world_process(stage:Path,state:dict,tasks:dict,task:dict,when:dt.datetime)->dict:
    rp=task.get("runtime_policy") or {};rule=rp.get("world_process_rule") or (task.get("task_data") or {}).get("world_process_rule")
    errs=_validate_world_process_rule(rule)
    if errs:raise EngineError("WORLD_PROCESS_RULE_INVALID:"+";".join(errs))
    selected=None
    for tr in rule.get("transitions") or []:
        if all(_condition_matches(c,state,tasks) for c in (tr.get("when") or [])):
            selected=tr;break
    changes=[]
    if selected:
        for a in selected.get("actions") or []:changes.append(_apply_automation_action(a,state,tasks))
    mon=task.setdefault("runtime_policy",{}).setdefault("monitor",{});iso=when.strftime("%Y-%m-%dT%H:%M:%S");mon["last_reviewed_at"]=iso
    interval=int(rule.get("repeat_seconds") or 0)
    if interval>0:mon["next_review_at"]=(when+dt.timedelta(seconds=interval)).strftime("%Y-%m-%dT%H:%M:%S")
    _append_engine_history(stage/"events.jsonl",{"event_id":f"AUTO-WORLD-PROCESS-{task.get('task_id')}-{when.strftime('%Y%m%d-%H%M%S')}","game_time":iso,"type":"world_process_rule","summary":str((selected or {}).get("history_summary") or rule.get("history_summary") or f"GAME ENGINE v{ENGINE_VERSION}执行封板世界过程规则；未生成自由叙事事实。"),"changes":_routine_time_changes()+[{"target":x.get("target") or "world_process","action":x.get("op")} for x in changes if x.get("op")!="emit_history"]+[{"target":"TASKS.active_tasks","action":"roll_world_process_monitor"}],"source":f"GAME ENGINE v{ENGINE_VERSION} {WORLD_PROCESS_RULE_SCHEMA}","authority_files":["state.json","tasks.json"],"source_task_id":task.get("task_id"),"transition_id":selected.get("id") if selected else None})
    return {"task_id":task.get("task_id"),"resolver":"world_process_rule_v1","transition_id":selected.get("id") if selected else None,"actions":changes}


def _resolver_progress_rule(stage:Path,state:dict,tasks:dict,task:dict,when:dt.datetime)->dict:
    rp=task.get("runtime_policy") or {};rule=rp.get("progress_rule") or (task.get("task_data") or {}).get("progress_rule")
    errs=_validate_progress_rule(rule)
    if errs:raise EngineError("PROGRESS_RULE_INVALID:"+";".join(errs))
    mon=task.setdefault("runtime_policy",{}).setdefault("monitor",{});last=parse_iso(mon.get("last_reviewed_at") or state.get("game_time"));iso=when.strftime("%Y-%m-%dT%H:%M:%S")
    if last is None or when<last:raise EngineError("PROGRESS_RULE_TIME_INVALID")
    root,path=_automation_root(state,tasks,rule["target"]);parent,key=_dot_parent(root,path);old=parent.get(key)
    if not isinstance(old,(int,float)) or isinstance(old,bool):raise EngineError("PROGRESS_RULE_TARGET_NOT_NUMERIC")
    delta=(when-last).total_seconds()*float(rule["rate_per_second"]);new=float(old)+delta
    if rule.get("minimum") is not None:new=max(new,float(rule["minimum"]))
    if rule.get("maximum") is not None:new=min(new,float(rule["maximum"]))
    parent[key]=new
    changes=[{"op":"progress","target":rule["target"],"old":old,"new":new}]
    fired=[]
    for i,m in enumerate(rule.get("milestones") or []):
        th=float(m["threshold"]);crossed=(float(old)<th<=new) if new>=float(old) else (float(old)>th>=new)
        if crossed:
            for a in m.get("actions") or []:changes.append(_apply_automation_action(a,state,tasks))
            fired.append(str(m.get("id") or i))
    mon["last_reviewed_at"]=iso
    interval=int(rule.get("repeat_seconds") or 0)
    if interval>0:mon["next_review_at"]=(when+dt.timedelta(seconds=interval)).strftime("%Y-%m-%dT%H:%M:%S")
    archived_task=None
    bound=float(rule['maximum'] if float(rule['rate_per_second'])>0 else rule['minimum'])
    if rule.get('close_on_completion') is True and new==bound:
        archived_task=copy.deepcopy(task);archived_task['status']='completed';archived_task['completed_at']=iso
        tasks['active_tasks']=[t for t in tasks.get('active_tasks',[]) if t.get('task_id')!=task.get('task_id')]
    _append_engine_history(stage/"events.jsonl",{"event_id":f"AUTO-PROGRESS-{task.get('task_id')}-{when.strftime('%Y%m%d-%H%M%S')}","game_time":iso,"type":"progress_rule","summary":str(rule.get("history_summary") or f"GAME ENGINE v{ENGINE_VERSION}按封板固定速率推进结构化进度。"),"changes":_routine_time_changes()+[{"target":rule["target"],"action":"fixed_rate_progress"}]+[{"target":x.get("target"),"action":x.get("op")} for x in changes[1:] if x.get("target")]+[{"target":"TASKS.active_tasks","action":"roll_progress_monitor"}],"source":f"GAME ENGINE v{ENGINE_VERSION} {PROGRESS_RULE_SCHEMA}","authority_files":["state.json","tasks.json"],"source_task_id":task.get("task_id"),"old":old,"new":new,"milestones":fired,"completed_task_archive":archived_task})
    return {"task_id":task.get("task_id"),"resolver":"progress_rule_v1","old":old,"new":new,"milestones":fired}

def market_offer_packet(payload:dict,base:Optional[Path]=None)->dict:
    context=None
    if base is not None:
        context=validate_price_quote(payload.get("price_context"),base)
        for key in ('offer_price','floor_price','counter_step','seller_urgency','seller_patience'):
            if key in payload:_price_decimal(payload[key])
        if payload.get("currency")!=context["total"]["currency"] or _price_decimal(payload.get("ask_price"))!=_price_decimal(context["total"]["amount"]):raise EngineError("PRICE_MARKET_ASK_CONTEXT_MISMATCH")
    ask=float(payload.get("ask_price"));offer=float(payload.get("offer_price"));floor=float(payload.get("floor_price",ask));step=float(payload.get("counter_step",max(0.01,(ask-floor)/2)));urg=float(payload.get("seller_urgency",0.5));pat=float(payload.get("seller_patience",0.5))
    effective_floor=max(0.0,floor*(1.0-0.05*max(0,min(1,urg))))
    if offer>=effective_floor:return _pricing_market_result({"packet":"MARKET_OFFER_V1","result":"ACCEPT","price":offer,"ask":ask,"effective_floor":round(effective_floor,6)},context,base,payload)
    counter=max(effective_floor,ask-step*(0.5+0.5*max(0,min(1,pat))))
    if offer>=effective_floor*0.85:return _pricing_market_result({"packet":"MARKET_OFFER_V1","result":"COUNTER","counter_price":round(counter,6),"ask":ask,"effective_floor":round(effective_floor,6)},context,base,payload)
    return _pricing_market_result({"packet":"MARKET_OFFER_V1","result":"REJECT","ask":ask,"effective_floor":round(effective_floor,6)},context,base,payload)

def automation_candidate_packet(base:Path=ROOT,min_count:int=3)->dict:
    ensure_source_ready(base);state=read_json(base/'state.json');_,events,_=read_history_view(base/'events.jsonl');sig={};window=events[-400:];recent_ids={str(e.get('event_id')) for e in events[-100:] if isinstance(e,dict)}
    banned_tokens=('current_continuity_checkpoint','continuation_checkpoint','current_bridge','narrative_state')
    def target_current_valid(target:str)->bool:
        t=str(target or '')
        if any(x in t for x in banned_tokens) or re.search(r'_current_v\d+',t,re.I):return False
        if t.startswith(('STATE.','state:')):
            try:get_by_path(state,t[6:]);return True
            except Exception:return False
        return True
    for e in window:
        if str(e.get('source') or '').lower().startswith('game engine') or e.get('type') in {'architecture_migration','transaction_changeset','time_advance','turn_pause'}:continue
        ch=e.get('changes') or []
        if isinstance(ch,dict):ch=[ch]
        pairs=[]
        for x in ch:
            if isinstance(x,dict):
                target=str(x.get('target') or '');action=str(x.get('action') or '')
                if target_current_valid(target):pairs.append((target,action))
        key=tuple(sorted(p for p in pairs if any(p)))
        if key:sig.setdefault(key,[]).append(e)
    rows=[]
    for k,evs in sig.items():
        recent=sum(1 for x in evs if str(x.get('event_id')) in recent_ids)
        if len(evs)>=min_count and recent>0:
            risk='low' if all(a in {'set','increment','append','transfer','consume','schedule','compare_set'} for _,a in k if a) else 'review'
            rows.append({'count':len(evs),'recent_count':recent,'risk':risk,'signature':[{'target':a,'action':b} for a,b in k],'examples':[x.get('event_id') for x in evs[-3:]],'eligibility':'current_targets_and_recent_evidence'})
    rows.sort(key=lambda x:(x['recent_count'],x['count']),reverse=True)
    return {'packet':'AUTOMATION_CANDIDATES_V2','engine_version':ENGINE_VERSION,'minimum_repeat':min_count,'history_window':len(window),'recent_window_events':min(100,len(events)),'candidates':rows[:20]}

RESOLVER_FUNCTIONS={"jinchuan_daily_settlement_v1":_resolver_jinchuan,"research_sales_daily_v1":_resolver_research_sales,"settlement_rule_v1":_resolver_settlement_rule,"world_process_rule_v1":_resolver_world_process,"progress_rule_v1":_resolver_progress_rule}
for _r in DETERMINISTIC_RESOLVERS-{"passive_event_v1","jinchuan_daily_settlement_v1","research_sales_daily_v1","settlement_rule_v1","world_process_rule_v1","progress_rule_v1"}:RESOLVER_FUNCTIONS[_r]=_resolver_automation



MAINTENANCE_KINDS={"repair","medical"}
MAINTENANCE_MAX_SECONDS=30*24*60*60
BATTLE_EQUIPMENT_REPAIR_SECONDS=60*60
BATTLE_REPAIR_ELIGIBLE_ASSET_CLASSES={'weapon','uav','combat_aircraft','shuttle','landing_craft','robot','armored_vehicle','power_armor','removable_ship_module','equipment'}
BATTLE_REPAIR_EXCLUDED_ASSET_CLASSES={'warship','ship_hull','base_structure','facility','building'}
MAINTENANCE_SENSITIVE_PATH_TOKENS=(".funds.",".inventories.",".personnel", ".ownership", ".owner", ".gold", ".grey", ".gray")


def _player_fleet_registry(state:dict)->dict:
    er=state.get("engine_runtime") or {};reg=er.get("player_fleet_registry") or {}
    if not isinstance(reg,dict):raise EngineError("PLAYER_FLEET_REGISTRY_INVALID")
    if reg and reg.get("schema")!=PLAYER_FLEET_REGISTRY_SCHEMA:raise EngineError("PLAYER_FLEET_REGISTRY_SCHEMA_INVALID")
    fleets=reg.get("fleets") or {}
    if not isinstance(fleets,dict):raise EngineError("PLAYER_FLEET_REGISTRY_FLEETS_INVALID")
    return reg


def _maintenance_runtime(state:dict,create:bool=False)->dict:
    er=state.setdefault("engine_runtime",{}) if create else (state.get("engine_runtime") or {})
    mr=er.get("maintenance_runtime")
    if mr is None:
        if not create:return {"schema":MAINTENANCE_RUNTIME_SCHEMA,"repair_queue":[],"medical_queue":[],"completed_jobs":{},"blocked_jobs":{},"pending_replenishment":[]}
        mr={"schema":MAINTENANCE_RUNTIME_SCHEMA,"repair_queue":[],"medical_queue":[],"completed_jobs":{},"blocked_jobs":{},"pending_replenishment":[]};er["maintenance_runtime"]=mr
    if not isinstance(mr,dict) or mr.get("schema")!=MAINTENANCE_RUNTIME_SCHEMA:raise EngineError("MAINTENANCE_RUNTIME_INVALID")
    for k,default in (("repair_queue",[]),("medical_queue",[]),("completed_jobs",{}),("blocked_jobs",{}),("pending_replenishment",[])):
        if k not in mr and create:mr[k]=copy.deepcopy(default)
    if not isinstance(mr.get("repair_queue",[]),list) or not isinstance(mr.get("medical_queue",[]),list):raise EngineError("MAINTENANCE_QUEUE_INVALID")
    if not isinstance(mr.get("completed_jobs",{}),dict) or not isinstance(mr.get("blocked_jobs",{}),dict):raise EngineError("MAINTENANCE_JOB_INDEX_INVALID")
    if not isinstance(mr.get("pending_replenishment",[]),list):raise EngineError("REPLENISHMENT_PENDING_INVALID")
    return mr


def _maintenance_job_exists(mr:dict,job_id:str)->bool:
    if job_id in (mr.get("completed_jobs") or {}) or job_id in (mr.get("blocked_jobs") or {}):return True
    return any(isinstance(x,dict) and str(x.get("job_id"))==job_id for q in ("repair_queue","medical_queue") for x in (mr.get(q) or []))


def _maintenance_validate_action(state:dict,kind:str,action:dict)->dict:
    if not isinstance(action,dict):raise EngineError("MAINTENANCE_ACTION_NOT_OBJECT")
    op=str(action.get("op") or "").strip();path=str(action.get("path") or "").strip()
    if op not in {"restore_pct_100","restore_from_path","set_status","clear_flag"}:raise EngineError(f"MAINTENANCE_ACTION_OP_INVALID:{op}")
    if not path.startswith(("STATE.","state:")):raise EngineError(f"MAINTENANCE_ACTION_STATE_PATH_REQUIRED:{path}")
    lp=path.lower()
    if any(tok in lp for tok in MAINTENANCE_SENSITIVE_PATH_TOKENS):raise EngineError(f"MAINTENANCE_ACTION_SENSITIVE_PATH:{path}")
    if not any(lp.startswith(prefix+root) for prefix in ('state.','state:') for root in ("voyager_fleet","jinchuan_fleet","shadow_fleet","world_state_overrides")):raise EngineError(f"MAINTENANCE_ACTION_ROOT_FORBIDDEN:{path}")
    try:before=copy.deepcopy(get_by_path(state,path[6:]))
    except KeyError:raise EngineError(f"MAINTENANCE_ACTION_PATH_MISSING:{path}")
    out={"op":op,"path":path,"expected_before":before}
    if op=="restore_pct_100":
        if not isinstance(before,(int,float)) or isinstance(before,bool) or not (0<=float(before)<=100):raise EngineError(f"MAINTENANCE_RESTORE_PCT_INVALID:{path}")
        if not any(tok in lp for tok in ("condition","integrity","complete","health","damage","repair")):raise EngineError(f"MAINTENANCE_RESTORE_PCT_SEMANTIC_PATH:{path}")
        out["value"]=100 if isinstance(before,int) else 100.0
    elif op=="restore_from_path":
        src=str(action.get("source_path") or "").strip()
        if not src.startswith(("STATE.","state:")):raise EngineError("MAINTENANCE_RESTORE_SOURCE_PATH_REQUIRED")
        try:value=copy.deepcopy(get_by_path(state,src[6:]))
        except KeyError:raise EngineError(f"MAINTENANCE_RESTORE_SOURCE_MISSING:{src}")
        if isinstance(before,(dict,list)) or isinstance(value,(dict,list)) or type(before) is not type(value):raise EngineError("MAINTENANCE_RESTORE_TYPE_MISMATCH")
        out["source_path"]=src;out["source_value_at_enqueue"]=value;out["value"]=value
    elif op=="set_status":
        value=action.get("value")
        if not isinstance(value,str) or not value.strip() or len(value)>120:raise EngineError("MAINTENANCE_STATUS_VALUE_INVALID")
        if not (lp.endswith("status") or lp.endswith("_status") or ".status" in lp):raise EngineError(f"MAINTENANCE_STATUS_PATH_INVALID:{path}")
        out["value"]=value
    else:
        if not isinstance(before,bool):raise EngineError(f"MAINTENANCE_CLEAR_FLAG_BOOL_REQUIRED:{path}")
        out["value"]=False
    if kind=="medical" and not any(tok in lp for tok in ("medical","health","treat","recover","wound","injur","status")):raise EngineError(f"MEDICAL_ACTION_PATH_NOT_MEDICAL:{path}")
    return out


def _normalize_maintenance_job(state:dict,raw:dict,now:dt.datetime,source_battle_id:Optional[str]=None)->dict:
    if not isinstance(raw,dict):raise EngineError("MAINTENANCE_JOB_NOT_OBJECT")
    forbidden={"cost","gold","grey","gray","medical_kit","medkit","supply_cost","purchase"}
    if any(k in raw for k in forbidden):raise EngineError("MAINTENANCE_JOB_FORBIDDEN_COST_OR_SUPPLY_FIELD")
    kind=str(raw.get("kind") or "").strip();job_id=str(raw.get("job_id") or "").strip()
    if kind not in MAINTENANCE_KINDS:raise EngineError(f"MAINTENANCE_KIND_INVALID:{kind}")
    if not job_id or len(job_id)>160:raise EngineError("MAINTENANCE_JOB_ID_INVALID")
    start=parse_iso(raw.get("started_at")) if raw.get("started_at") else now;complete=parse_iso(raw.get("complete_at"))
    if start is None or complete is None:raise EngineError(f"MAINTENANCE_JOB_TIME_REQUIRED:{job_id}")
    if start!=now:raise EngineError(f"MAINTENANCE_JOB_START_MUST_EQUAL_CURRENT_GAME_TIME:{job_id}")
    delta=(complete-start).total_seconds()
    if delta<=0 or delta>MAINTENANCE_MAX_SECONDS:raise EngineError(f"MAINTENANCE_JOB_DURATION_INVALID:{job_id}:{int(delta)}")
    fleet_id=str(raw.get("fleet_id") or "").strip() or None
    if fleet_id:
        fleets=(_player_fleet_registry(state).get("fleets") or {})
        if fleet_id not in fleets:raise EngineError(f"MAINTENANCE_FLEET_UNKNOWN:{fleet_id}")
    actions=[_maintenance_validate_action(state,kind,a) for a in (raw.get("completion_actions") or [])]
    job={"schema":MAINTENANCE_JOB_SCHEMA,"job_id":job_id,"kind":kind,"status":"active","fleet_id":fleet_id,"target_id":raw.get("target_id"),"asset_class":raw.get("asset_class"),"started_at":start.strftime("%Y-%m-%dT%H:%M:%S"),"complete_at":complete.strftime("%Y-%m-%dT%H:%M:%S"),"completion_actions":actions,"source_battle_id":source_battle_id or raw.get("source_battle_id"),"source_event_id":raw.get("source_event_id"),"severity":raw.get("severity"),"tracked_count":int(raw.get("tracked_count",0) or 0),"policy":{"max_days":30,"extra_gold_cost":False,"auto_medkit_consumption":False,"parallel_queue":True}}
    if job["tracked_count"]<0:raise EngineError("MAINTENANCE_TRACKED_COUNT_NEGATIVE")
    return job


def _enqueue_maintenance_jobs(state:dict,jobs:list,now:dt.datetime,source_battle_id:Optional[str]=None)->list:
    if not isinstance(jobs,list):raise EngineError("MAINTENANCE_JOBS_LIST_REQUIRED")
    mr=_maintenance_runtime(state,create=True);added=[]
    for raw in jobs:
        job=_normalize_maintenance_job(state,raw,now,source_battle_id)
        if _maintenance_job_exists(mr,job["job_id"]):raise EngineError(f"MAINTENANCE_JOB_DUPLICATE:{job['job_id']}")
        mr["repair_queue" if job["kind"]=="repair" else "medical_queue"].append(job);added.append(copy.deepcopy(job))
    return added


def maintenance_event_queue(state:dict,now:dt.datetime,horizon:dt.datetime)->List[dict]:
    mr=_maintenance_runtime(state,create=False);out=[]
    for qname,kind in (("repair_queue","repair"),("medical_queue","medical")):
        for job in mr.get(qname,[]) or []:
            if not isinstance(job,dict) or job.get("status")!="active":continue
            tm=parse_iso(job.get("complete_at"))
            if tm is not None and now<=tm<=horizon:out.append({"source":"maintenance_runtime","kind":"maintenance_completion","job_id":job.get("job_id"),"maintenance_kind":kind,"time":tm.strftime("%Y-%m-%dT%H:%M:%S"),"resolver":"maintenance_completion_v1","title":job.get("target_id") or job.get("job_id")})
    return sorted(out,key=lambda e:(e["time"],e.get("job_id") or ""))


def _maintenance_find_active(mr:dict,job_id:str)->Tuple[str,int,dict]:
    for qname in ("repair_queue","medical_queue"):
        q=mr.get(qname) or []
        for i,j in enumerate(q):
            if isinstance(j,dict) and str(j.get("job_id"))==job_id:return qname,i,j
    raise EngineError(f"MAINTENANCE_JOB_NOT_ACTIVE:{job_id}")


def _resolve_maintenance_event(stage:Path,state:dict,tasks:dict,event:dict,when:dt.datetime)->dict:
    mr=_maintenance_runtime(state,create=True);qname,idx,job=_maintenance_find_active(mr,str(event.get("job_id") or ""))
    tm=parse_iso(job.get("complete_at"))
    if tm!=when:raise EngineError(f"MAINTENANCE_EVENT_TIME_MISMATCH:{job.get('job_id')}")
    da=job.get('domain_authorization')
    if da:
        rec=(state.get('standing_authorizations') or {}).get(da['authorization_ref']) or {};grant=rec.get('machine_grant')
        digest=sha256_bytes(json.dumps(grant,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()) if isinstance(grant,dict) else None
        if rec.get('status')!='active' or rec.get('revoked') is True or digest!=da.get('grant_sha256') or parse_iso((grant or {}).get('valid_until')) is None or when>parse_iso(grant['valid_until']):
            blocked=copy.deepcopy(job);blocked['status']='blocked_authorization_changed';blocked['blocked_at']=when.strftime('%Y-%m-%dT%H:%M:%S')
            mr[qname].pop(idx);mr['blocked_jobs'][blocked['job_id']]=blocked
            _append_engine_history(stage/'events.jsonl',{'event_id':f"MAINT-AUTH-BLOCK-{blocked['job_id']}-{when.strftime('%Y%m%d-%H%M%S')}",'game_time':blocked['blocked_at'],'type':'maintenance_completion_blocked','summary':f"GAME ENGINE v{ENGINE_VERSION}暂停到期维修/医疗任务{blocked['job_id']}：持续授权在实际执行时已失效。未执行completion action。",'changes':[{'target':'STATE.engine_runtime.maintenance_runtime.blocked_jobs','action':'authorization_invalid'}],'source':f'GAME ENGINE v{ENGINE_VERSION} {MAINTENANCE_RUNTIME_SCHEMA}','authority_files':['state.json'],'source_job_id':blocked['job_id']})
            return {'source':'maintenance_runtime','job_id':blocked['job_id'],'status':'AI_REQUIRED','semantic_barrier':{'kind':'maintenance_authorization_invalid','job_id':blocked['job_id'],'authorization_ref':da['authorization_ref']}}
    # All completion actions are compare-and-set as one unit. A changed target becomes a semantic barrier,
    # never a partial repair writeback.
    conflicts=[]
    for a in job.get("completion_actions") or []:
        try:cur=get_by_path(state,str(a.get("path"))[6:])
        except Exception:cur=None
        if cur!=a.get("expected_before"):conflicts.append({"path":a.get("path"),"expected":a.get("expected_before"),"current":cur})
        if a.get("op")=="restore_from_path":
            try:src=get_by_path(state,str(a.get("source_path"))[6:])
            except Exception:src=None
            if src!=a.get("source_value_at_enqueue"):conflicts.append({"path":a.get("source_path"),"expected":a.get("source_value_at_enqueue"),"current":src})
    if conflicts:
        blocked=copy.deepcopy(job);blocked["status"]="blocked_authority_changed";blocked["blocked_at"]=when.strftime("%Y-%m-%dT%H:%M:%S");blocked["conflicts"]=conflicts
        mr[qname].pop(idx);mr["blocked_jobs"][blocked["job_id"]]=blocked
        _append_engine_history(stage/"events.jsonl",{"event_id":f"MAINT-BLOCK-{blocked['job_id']}-{when.strftime('%Y%m%d-%H%M%S')}","game_time":when.strftime("%Y-%m-%dT%H:%M:%S"),"type":"maintenance_completion_blocked","summary":f"GAME ENGINE v{ENGINE_VERSION}检测到维修/医疗任务{blocked['job_id']}完成写回目标已改变，已停在语义审计门，未执行任何completion action。","changes":[{"target":"STATE.engine_runtime.maintenance_runtime.blocked_jobs","action":"compare_and_set_conflict"}],"source":f"GAME ENGINE v{ENGINE_VERSION} {MAINTENANCE_RUNTIME_SCHEMA}","authority_files":["state.json"],"zero_time":False})
        return {"source":"maintenance_runtime","job_id":blocked["job_id"],"maintenance_kind":blocked["kind"],"status":"AI_REQUIRED","semantic_barrier":{"kind":"maintenance_authority_conflict","job_id":blocked["job_id"],"time":blocked["blocked_at"],"conflicts":conflicts}}
    changes=[]
    for a in job.get("completion_actions") or []:
        parent,key=_dot_parent(state,str(a["path"])[6:]);parent[key]=copy.deepcopy(a.get("value"));changes.append({"target":a["path"],"action":a["op"]})
    done=copy.deepcopy(job);done["status"]="completed";done["completed_at"]=when.strftime("%Y-%m-%dT%H:%M:%S")
    mr[qname].pop(idx);mr["completed_jobs"][done["job_id"]]=done
    changes.append({"target":f"STATE.engine_runtime.maintenance_runtime.{qname}","action":"complete_and_move_to_completed_jobs"})
    _append_engine_history(stage/"events.jsonl",{"event_id":f"MAINT-DONE-{done['job_id']}-{when.strftime('%Y%m%d-%H%M%S')}","game_time":when.strftime("%Y-%m-%dT%H:%M:%S"),"type":f"{done['kind']}_completion","summary":f"GAME ENGINE v{ENGINE_VERSION}按封板ETA自动完成{done['kind']}任务{done['job_id']}；不生成额外金币费用，医疗任务不自动消耗医疗包。","changes":changes,"source":f"GAME ENGINE v{ENGINE_VERSION} {MAINTENANCE_RUNTIME_SCHEMA}","authority_files":["state.json"],"source_battle_id":done.get("source_battle_id")})
    return {"source":"maintenance_runtime","job_id":done["job_id"],"maintenance_kind":done["kind"],"status":"COMPLETED","actions":changes}


def deterministic_event_queue(state:dict,tasks_doc:dict,now:dt.datetime,horizon:dt.datetime)->List[dict]:
    task_rows=[]
    for row in deterministic_task_queue(tasks_doc,now,horizon,state):
        x=copy.deepcopy(row);x.setdefault("source","task");task_rows.append(x)
    out=task_rows+maintenance_event_queue(state,now,horizon)
    return sorted(out,key=lambda e:(e.get("time") or "",e.get("source") or "",e.get("task_id") or e.get("job_id") or ""))


def _resolve_deterministic_event(stage:Path,state:dict,tasks:dict,event:dict,when:dt.datetime)->dict:
    if event.get("source")=="maintenance_runtime":return _resolve_maintenance_event(stage,state,tasks,event,when)
    task=_task_by_id(tasks,event["task_id"]);fn=RESOLVER_FUNCTIONS[event["resolver"]];return fn(stage,state,tasks,task,when)

def _progress_rule_due_time(task:dict,state:Optional[dict],tasks_doc:dict,now:dt.datetime,horizon:dt.datetime)->Optional[dt.datetime]:
    """Earliest deterministic progress checkpoint in (now, horizon].

    Continuous progress must not depend on an author remembering next_review_at.  We
    schedule the earliest of an explicit review, repeat interval, next milestone/bound,
    or the requested time-advance horizon so the numeric state is always current.
    """
    if state is None or horizon<=now:return None
    rp=task.get("runtime_policy") or {};mon=rp.get("monitor") or {};rule=rp.get("progress_rule") or (task.get("task_data") or {}).get("progress_rule")
    if _validate_progress_rule(rule):return None
    try:
        root,path=_automation_root(state,tasks_doc,rule["target"]);parent,key=_dot_parent(root,path);cur=parent.get(key)
    except Exception:
        return None
    if not isinstance(cur,(int,float)) or isinstance(cur,bool) or not math.isfinite(float(cur)):return None
    rate=float(rule["rate_per_second"]);cur=float(cur);candidates=[]
    origin=parse_iso(mon.get("last_reviewed_at")) or now
    nr=parse_iso(mon.get("next_review_at")) if mon.get("next_review_at") else None
    if nr is not None and now<nr<=horizon:candidates.append(nr)
    repeat=rule.get("repeat_seconds")
    if isinstance(repeat,int) and not isinstance(repeat,bool) and repeat>0:
        last=origin
        nxt=last+dt.timedelta(seconds=repeat)
        if nxt<=now:
            steps=int((now-last).total_seconds()//repeat)+1;nxt=last+dt.timedelta(seconds=steps*repeat)
        if now<nxt<=horizon:candidates.append(nxt)
    thresholds=[]
    for m in rule.get("milestones") or []:
        if isinstance(m,dict) and isinstance(m.get("threshold"),(int,float)) and not isinstance(m.get("threshold"),bool):thresholds.append(float(m["threshold"]))
    bound=float(rule["maximum"] if rate>0 else rule["minimum"]);thresholds.append(bound)
    for th in thresholds:
        dist=(th-cur)/rate
        if dist>0:
            # Authority timestamps are second-granular.  Round crossing times upward;
            # flooring a fractional crossing can reschedule the same pre-threshold second
            # forever (for example 0 -> 1 at 0.3 units/s crosses at 3.333s).
            whole_seconds=max(1,int(math.ceil(dist-1e-12)))
            when=origin+dt.timedelta(seconds=whole_seconds)
            if when<=now:candidates.append(now)
            elif when<=horizon:candidates.append(when)
    # Always materialize current progress at the requested horizon when movement remains.
    if (rate>0 and cur<float(rule["maximum"])) or (rate<0 and cur>float(rule["minimum"])):
        candidates.append(horizon)
    return min(candidates) if candidates else None


def _deterministic_event_precedes_barrier(event:dict,event_time:dt.datetime,hard:dt.datetime,barrier:Optional[dict])->bool:
    """Continuous mechanical progress accrues through the exact semantic-boundary instant."""
    if barrier is None:return event_time<=hard
    if event_time<hard:return True
    return event_time==hard and str(event.get("resolver") or "")=="progress_rule_v1"


def deterministic_task_queue(tasks_doc: dict, now: dt.datetime, horizon: dt.datetime, state: Optional[dict]=None) -> List[dict]:
    out=[]
    for t in tasks_doc.get("active_tasks",[]) or []:
        mon=_task_monitor(tasks_doc,t);resolver=str(mon.get("resolver") or "")
        if mon.get("requires_ai_review") is not False or not callable(RESOLVER_FUNCTIONS.get(resolver)):continue
        if _task_execution_coverage(state,tasks_doc,t,now,horizon):continue
        if resolver=="progress_rule_v1":
            due=_progress_rule_due_time(t,state,tasks_doc,now,horizon)
            if due is not None:out.append({"task_id":t.get("task_id"),"time":due.strftime("%Y-%m-%dT%H:%M:%S"),"resolver":resolver,"title":t.get("title")})
            continue
        nr=parse_iso(mon.get("next_review_at")) if mon.get("next_review_at") else None
        if nr is not None and now <= nr <= horizon:out.append({"task_id":t.get("task_id"),"time":nr.strftime("%Y-%m-%dT%H:%M:%S"),"resolver":resolver,"title":t.get("title")})
    return sorted(out,key=lambda e:(e["time"],e.get("task_id") or ""))


def _next_ai_monitor_time(tasks_doc: dict, now: dt.datetime, horizon: dt.datetime, state: Optional[dict]=None) -> Optional[dict]:
    vals=[]
    for t in tasks_doc.get("active_tasks",[]) or []:
        mon=_task_monitor(tasks_doc,t)
        coverage=_task_execution_coverage(state,tasks_doc,t,now,horizon)
        if coverage:vals.append(coverage)
        if _task_player_decision_gate_open(t):
            vals.append({"time":now,"task_id":t.get("task_id"),"title":t.get("title"),"kind":"task_player_decision_gate","decision_gate":_compact_value(t.get("decision_gate"),320),"resolution_required":"Commander decision is explicitly required before time advance may continue; Engine must not infer or auto-resolve the choice."})
        if not mon.get("requires_ai_review",True):
            due=parse_iso(mon.get('next_review_at')) if mon.get('next_review_at') else None
            if due and due<now and mon.get('resolver') in RESOLVER_FUNCTIONS and mon.get('resolver')!='progress_rule_v1':
                vals.append({'time':now,'task_id':t.get('task_id'),'title':t.get('title'),'kind':'task_overdue_reconciliation','scheduled_time':due.isoformat(),'resolution_required':'Reconcile HISTORY and last reviewed time before explicitly catching up or rescheduling; never silently skip or invent historical income.'})
            continue
        watch=_watch_condition_status(state,t)
        if watch.get("configured"):
            if watch.get("triggered"):
                vals.append({"time":now,"task_id":t.get("task_id"),"title":t.get("title"),"kind":"task_watch_condition","watch_condition":copy.deepcopy(watch),"resolution_required":"AI must review the changed canonical STATE. Before continuing, an authoritative task patch must rebase watch_condition.baseline_digest to current_digest (or explicitly replace/retire the watcher); Engine never auto-acknowledges a changed watcher."})
            continue
        nr=parse_iso(mon.get("next_review_at")) if mon.get("next_review_at") else None
        if nr is not None:
            if now < nr <= horizon:vals.append({"time":nr,"task_id":t.get("task_id"),"title":t.get("title"),"kind":"task_ai_review"})
            elif nr <= now:vals.append({"time":now,"task_id":t.get("task_id"),"title":t.get("title"),"kind":"task_ai_review_now"})
            continue
        if mon.get("review_on_time_advance") and mon.get("mode") in {"on_advance","continuous","external_wait"}:
            vals.append({"time":now,"task_id":t.get("task_id"),"title":t.get("title"),"kind":"task_ai_review_now"})
    return min(vals,key=lambda x:(x["time"],x.get("task_id") or "")) if vals else None


