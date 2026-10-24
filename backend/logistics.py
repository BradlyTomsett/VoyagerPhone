"""Deterministic, commander-confirmed internal logistics. No model calls.

Current physical buckets are normalized once in the game copy. Historical plans,
prices, performance values and overlapping totals never become extra stock.
The original engine's staging/atomic-save protocol remains the commit boundary.
"""
import copy
import hashlib
import json
import re
import shutil
from types import SimpleNamespace
from decimal import Decimal, InvalidOperation
from pathlib import Path

from backend.engine import canonical, digest
from backend.fleet_archive import FleetArchive, FLEETS, model_name, table_rows

KEY='internal_logistics_v1'
FLEET_NAMES={k:v[0] for k,v in FLEETS.items()}
PERSON_KEYS={'voyager':'current_personnel','jinchuan':'personnel_total','shadow':'personnel_total'}
SKIP={'as_of','status','note','source','authority','scope_note','unit','precision','condition','condition_pct','total','physical_total','assigned_total','total_owned','nominal_ground_combat_power_each','added_ground_G','scientific_personnel','marines','crew','personnel'}
ALIASES={'制式步枪':'自有制式步枪','rifles':'步枪','external_rifles':'外购步枪','外来制式步枪':'外购步枪','外购手枪物理在仓':'外购手枪',
 'hq_m2_marines':'M2动力甲','guardian1':'卫士1','卫士1型作战机器人':'卫士1','卫士1公共库存':'卫士1','彩虹1公共库存':'彩虹1','彩虹1查打一体无人机':'彩虹1',
 '沙丘':'沙丘装甲车','沙丘全地形装甲车':'沙丘装甲车','沙丘装甲车公共库存':'沙丘装甲车','一次性反装甲发射器':'外购一次性反装甲火箭筒','一次性反装甲火箭筒':'外购一次性反装甲火箭筒',
 'food':'食物','water':'饮水','maintenance_parts':'维修备件','compressed_air':'压缩空气','fuel':'燃料','medical_kits':'医疗包','military_explosives_current':'军用炸药','engineering_explosives':'工程炸药',
 'scv_public':'SCV工程机器人','SCV':'SCV工程机器人','夜鹰':'夜鹰穿梭机','大力神':'大力神轻型登陆艇','蜻蜓':'蜻蜓侦察无人机','激光近防':'激光近防炮',
 'xuanwu_light_landers':'玄武轻型登陆艇','xuanwu_heavy_landers':'玄武重型登陆艇','hummingbird_shuttles':'蜂鸟穿梭机',
 'grenades':'多功能手雷','external_pistols':'外购手枪','individual_missiles':'单兵导弹','multifunction_grenades':'多功能手雷','powered_armor':'动力甲'}

def install_naming_extension(api, seed):
    """A transfer preserves a ship's registered name, including serial gaps.

    Native V14 naming assumes whole classes never split across fleets. Extend
    only that assumption for identities in the trusted original registration;
    keep its uniqueness, class counts, prefixes and registry checks intact.
    """
    scope=api.run_checks.__globals__
    if scope.get('_browser_transfer_naming_installed'):return
    original=scope['_validate_voyager_vessel_naming']
    trusted=ships(json.loads((Path(seed)/'state.json').read_bytes()))
    def validate(fleet):
        errors=original(fleet);registration=fleet.get('vessel_naming',{}).get('internal_transfer_registration',{})
        if not registration:return errors
        roster=fleet.get('vessel_roster',[]);out=[]
        for error in errors:
            if ' serials=' in error:
                cid=error.split(' serials=',1)[0];rows=[r for r in roster if r.get('class_id')==cid and not r.get('external_owned')]
                if rows and all(r['vessel_id'] in trusted and registration.get(r['vessel_id'],{}).get('name')==r['name']==trusted[r['vessel_id']][1]['name'] and r.get('serial')==trusted[r['vessel_id']][1].get('serial') for r in rows):continue
            if ' name mismatch:' in error:
                vid=error.split(' name mismatch:',1)[0];row=next((r for r in roster if r.get('vessel_id')==vid),{})
                if row.get('external_owned') and vid in trusted and row.get('name')==trusted[vid][1]['name']==registration.get(vid,{}).get('name'):continue
            out.append(error)
        return out
    scope['_validate_voyager_vessel_naming']=validate;api._validate_voyager_vessel_naming=validate
    original_resolver=scope['_robot_model_map_from_vessel'];original_report=scope['shadow_shipboard_asset_crosspath_report']
    def resolve(record):
        current=record.get('internal_logistics_current')
        if not current:return original_resolver(record)
        models=robot_models(current['assets']);return sum(models.values()),models,'commander_confirmed_current_manifest'
    def report(state):
        if KEY not in state.get('engine_runtime',{}):return original_report(state)
        errors=[];models={'fortress5':0,'fortress6':0};total=0
        for vid,row in scope['_shadow_active_mobile_vessels'](state).items():
            count,split,source=resolve(row)
            if count is None or sum(split.values())!=count:errors.append({'kind':'current_robot_model_unresolved','vessel_id':vid});continue
            if row.get('current_combat_robot_count')!=count:errors.append({'kind':'current_robot_count_mismatch','vessel_id':vid})
            total+=count
            for key,value in split.items():models[key]=models.get(key,0)+value
            for key,value in row.get('current_embarked_assets',{}).items():
                if key in ('fortress5','fortress6') and value!=split.get(key,0):errors.append({'kind':'current_manifest_robot_count','vessel_id':vid,'model':key})
        aggregate=state.get('shadow_fleet',{}).get('mobile_combat_assets_current',{}).get('shipboard_combat_robots',{})
        if aggregate.get('total')!=total or aggregate.get('models_exact_current')!=models:errors.append({'kind':'fleet_robot_projection_mismatch'})
        return {'status':'FAIL' if errors else 'PASS','errors':errors,'current_robot_total':total,'current_robot_models':models}
    for key,fn in [('_robot_model_map_from_vessel',resolve),('shadow_shipboard_asset_crosspath_report',report)]:scope[key]=fn;setattr(api,key,fn)
    catalog=json.loads((Path(seed)/'catalog.json').read_bytes());rules=json.loads((Path(seed)/'rules.json').read_bytes())
    def synchronize(state):
        if KEY not in state.get('engine_runtime',{}):return
        service=object.__new__(Logistics);service.state=state;service.catalog=catalog
        service.library=SimpleNamespace(documents={'state':state,'catalog':catalog,'rules':rules},root=Path(seed),manifest={})
        before=copy.deepcopy(state['engine_runtime'][KEY]);book=service.book(state)
        if before!=book:service.sync(state,book,before)
    original_post=scope['_phase2_domain_post_mutation_validate']
    def post(state,tasks,before_time):
        synchronize(state);return original_post(state,tasks,before_time)
    original_atomic=scope['atomic_save']
    def atomic(stage,*args,**kwargs):
        path=Path(stage)/'state.json';state=json.loads(path.read_bytes());before=copy.deepcopy(state)
        synchronize(state)
        if state!=before:scope['_write_authority_json'](path,state)
        return original_atomic(stage,*args,**kwargs)
    for key,fn in [('_phase2_domain_post_mutation_validate',post),('atomic_save',atomic)]:scope[key]=fn;setattr(api,key,fn)
    scope['_browser_transfer_naming_installed']=True

def robot_models(assets):
    out={}
    for name,row in assets.items():
        if not re.search('堡垒|卫士|战斗机器人',name):continue
        key={'堡垒-4':'fortress4','堡垒-5':'fortress5','堡垒-6':'fortress6','卫士1':'guardian1'}.get(name,name)
        n=int(number(row['quantity']))
        if n:out[key]=out.get(key,0)+n
    return out

def number(value,positive=False):
    if isinstance(value,bool):raise ValueError('TRANSFER_QUANTITY_INVALID')
    try:n=Decimal(str(value))
    except (InvalidOperation,ValueError):raise ValueError('TRANSFER_QUANTITY_INVALID') from None
    if not n.is_finite() or n<0 or positive and n<=0:raise ValueError('TRANSFER_QUANTITY_INVALID')
    return n

def textnum(value):
    raw=format(number(value),'f');return raw.rstrip('0').rstrip('.') if '.' in raw else raw

def jsonnum(value):
    n=number(value);return int(n) if n==n.to_integral_value() else float(n)

def at(state,path):
    value=state
    for key in path:value=value[key]
    return value

def put(state,path,value):
    parent=state
    for key in path[:-1]:parent=parent[key]
    parent[path[-1]]=value

def remap_refs(value,routes):
    if isinstance(value,dict):return {k:remap_refs(v,routes) for k,v in value.items()}
    if isinstance(value,list):return [remap_refs(v,routes) for v in value]
    if isinstance(value,str):
        for old,new in routes:
            for prefix in ('state:','STATE.','state.',''):
                start=prefix+old
                if value==start or value.startswith(start+'.'):return prefix+new+value[len(start):]
    return value

def ships(state):
    out={}
    for fleet in FLEETS:
        d=state[FLEETS[fleet][1]]
        if fleet=='voyager':
            for i,row in enumerate(d.get('vessel_roster',[])):
                vid=row['vessel_id'];data={**row,**d.get('named_vessels',{}).get(vid,{})}
                path=[FLEETS[fleet][1],'named_vessels',vid] if vid in d.get('named_vessels',{}) else [FLEETS[fleet][1],'vessel_roster',i]
                out[vid]=(fleet,data,path)
        else:
            for vid,row in d.get('vessels',{}).items():out[vid]=(fleet,{**row,'vessel_id':vid},[FLEETS[fleet][1],'vessels',vid])
    return out

def quantity(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool):return value,[]
    if isinstance(value,dict):
        for key in ('available','usable','value','qty','count'):
            if isinstance(value.get(key),(int,float)) and not isinstance(value[key],bool):return value[key],[key]
    return None,None

class Logistics:
    def __init__(self,library):
        # Display sources are redacted. Mutation must retain the complete trusted
        # document, including engine anchors and GM facts that never enter the UI.
        self.library=library;self.state=json.loads((library.root/'state.json').read_bytes());self.catalog=library.documents['catalog']

    def book(self,state=None):
        state=state or self.state
        if KEY in state.get('engine_runtime',{}):
            book=copy.deepcopy(state['engine_runtime'][KEY]);self.reconcile(book,state);return book
        return self.initial(state)

    def initial(self,state):
        book={'schema':'VOYAGER_INTERNAL_LOGISTICS_V1','revision':0,'locations':{},'items':{},'stock':{},'people':{},'receipts':{}}
        loc=book['locations'];stock=book['stock']
        def location(lid,name,fleet,kind):
            loc[lid]={'id':lid,'name':name,'fleet':fleet,'kind':kind};stock[lid]={};book['people'][lid]=[]
        for fleet in FLEETS:
            location(fleet+':warehouse',FLEET_NAMES[fleet]+' · 公共库存',fleet,'warehouse')
            location(fleet+':other',FLEET_NAMES[fleet]+' · 其他在编人员／外勤',fleet,'personnel')
        location('headquarters','总部库存','voyager','warehouse')
        location('voyager:base','远航基地 · 独立仓库','voyager','warehouse')
        loc['shadow:warehouse']['name']='暗影基地 · 公共库存'
        location('farstar','远星军','voyager','force');location('qrf','暗影快反部队','shadow','force')
        location('shadow:base','S-B5暗影基地固定人员','shadow','personnel')
        vesselmap=ships(state)
        for vid,(fleet,data,path) in vesselmap.items():location(vid,data.get('name',vid),fleet,'vessel')
        def add(lid,name,value,path=None,unit=None,basis='当前存档',scale=1):
            if value is None:return
            name=str(ALIASES.get(name,model_name(name)));name=ALIASES.get(name,name)
            name=name.replace('公共库存','').strip();name=ALIASES.get(name,name)
            if unit=='吨':unit='kg';scale=number(scale)*1000
            if unit in ('艘','台','架','辆','套','支','件','具','发','枚'):
                unit=None # Stable model units across alternate source presentations.
            if not unit:
                unit=('支' if re.search('步枪|手枪|霰弹枪',name) else '套' if re.search('动力甲|先锋-',name) else '架' if re.search('猎隼|彩虹|夜鹰|大力神|蓝鲸|雷电|无人机|战机|蜂鸟|玄武|南燕|宁航|鹞-|大黄蜂',name) else '台' if re.search('堡垒|卫士|SCV|工蜂|机器人',name) else '辆' if re.search('装甲车|北陆|边盾|老兵|赤原|磐石',name) else '枚' if '手雷' in name else '发' if '单兵导弹' in name else '具' if '火箭筒' in name else '件')
            itemid='ITEM-'+hashlib.sha256((name+'\0'+unit).encode()).hexdigest()[:18]
            book['items'].setdefault(itemid,{'id':itemid,'name':name,'unit':unit})
            row=stock[lid].get(itemid)
            if row is not None:
                # Alternate current mirrors are bindings, never additional goods.
                if path and number(row['quantity'])==number(value)*number(scale) and not any(b['path']==path for b in row['bindings']):row['bindings'].append({'path':path,'scale':str(scale),'last':textnum(value)})
                return
            props={}
            if path:
                try:
                    parent=at(state,path[:-1])
                    if isinstance(parent,dict):props={k:v for k,v in parent.items() if k in ('condition','condition_pct','age_years','model','source_type') and isinstance(v,(str,int,float))}
                except (KeyError,TypeError,IndexError):pass
            row={'quantity':textnum(number(value)*number(scale)),'basis':basis,'bindings':[],
                 'batches':[{'quantity':textnum(number(value)*number(scale)),'properties':props,'basis':basis}]}
            if path:row['bindings'].append({'path':path,'scale':str(scale),'last':textnum(value)})
            stock[lid][itemid]=row
        def container(lid,obj,path,prefix='',basis='当前实物记录'):
            if not isinstance(obj,dict):return
            for key,value in obj.items():
                if key in SKIP or re.search(r'price|cost|age|power|combat|condition|capacity|percent|_G|_A|planned|history|purchase|reserved',key):continue
                n,suffix=quantity(value)
                if n is not None:add(lid,prefix+str(key),n,path+[key]+suffix,value.get('unit') if isinstance(value,dict) else None,basis)
                elif isinstance(value,dict):container(lid,value,path+[key],prefix,basis)
        net=state.get('inventories',{}).get('current_voyager_weapon_inventory_net',{})
        for group in ('self_owned_public','external_current_owned'):
            for name,row in net.get(group,{}).items():
                n,suffix=quantity(row)
                if n is not None:add('voyager:warehouse',name,n,['inventories','current_voyager_weapon_inventory_net',group,name]+suffix,basis='当前公共可用量；配属另列')
        armored=state.get('inventories',{}).get('current_voyager_armored_vehicle_inventory_net',{}).get('models',{})
        container('voyager:warehouse',armored,['inventories','current_voyager_armored_vehicle_inventory_net','models'])
        container('voyager:warehouse',state['voyager_fleet'].get('nonweapon_inventory_current',{}),['voyager_fleet','nonweapon_inventory_current'])
        container('voyager:warehouse',state['voyager_fleet'].get('public_engineering_assets_current',{}),['voyager_fleet','public_engineering_assets_current'])
        container('voyager:warehouse',state.get('inventories',{}).get('support_inventory',{}).get('self_owned',{}),['inventories','support_inventory','self_owned'])
        container('headquarters',state.get('inventories',{}).get('headquarters',{}),['inventories','headquarters'])
        army=state['voyager_fleet'].get('farstar_army_current',{})
        for group in ('standard_personal_equipment','organic_assets'):container('farstar',army.get(group,{}),['voyager_fleet','farstar_army_current',group])
        shadow=state['shadow_fleet'];inv=shadow.get('inventory_summary_current',{})
        container('shadow:warehouse',inv.get('public_warehouse_current',{}),['shadow_fleet','inventory_summary_current','public_warehouse_current'])
        if not inv.get('public_warehouse_current'):container('shadow:warehouse',inv.get('public',{}),['shadow_fleet','inventory_summary_current','public'])
        qrf=shadow.get('quick_reaction_force_current',{})
        for name,row in qrf.get('equipment',{}).items():
            n,suffix=quantity(row)
            if n is None and isinstance(row,dict) and isinstance(row.get('assigned'),int):n,suffix=row['assigned'],['assigned']
            if n is not None:add('qrf',name,n,['shadow_fleet','quick_reaction_force_current','equipment',name]+suffix,basis='快反编制；内部分组不重复计数')
        for name,n in qrf.get('power_armor_current',{}).get('equipped',{}).items():
            if name!='total':add('qrf',name,n,['shadow_fleet','quick_reaction_force_current','power_armor_current','equipped',name])
        supply=state.get('inventories',{}).get('supply_inventory',{}).get('fleets',{})
        for fleet,values in supply.items():
            if fleet in FLEETS:container(fleet+':warehouse',values,['inventories','supply_inventory','fleets',fleet])
        container('shadow:warehouse',state.get('inventories',{}).get('shadow_supply_inventory',{}).get('goods',{}),['inventories','shadow_supply_inventory','goods'])
        exp=shadow.get('explosives_inventory_current',{})
        add('shadow:warehouse','军用炸药',exp.get('military',{}).get('stock_kg'),['shadow_fleet','explosives_inventory_current','military','stock_kg'],'kg')
        add('shadow:warehouse','工业炸药',exp.get('industrial',{}).get('public_stock_kg'),['shadow_fleet','explosives_inventory_current','industrial','public_stock_kg'],'kg')
        for place,n in exp.get('industrial',{}).get('hawke_team',{}).items():
            lid='field:'+place;location(lid,place+' · 霍克组携行','shadow','warehouse');add(lid,'工业炸药',n,['shadow_fleet','explosives_inventory_current','industrial','hawke_team',place],'kg')
        classes=self.catalog.get('catalog_registry',{}).get('entities',{})
        def parse_text(lid,raw,fallback=None):
            for part in re.split('[；;/]',str(raw).replace('**','')):
                part=part.strip();m=re.fullmatch(r'(.+?)[x×](\d+)',part,re.I) or re.fullmatch(r'([^\d]+)(\d+)',part)
                if not m:continue
                name=m[1].strip();name={'无人机':'舰载无人机（型号未单列）','战机':'舰载战机（型号未单列）','导弹':'舰载导弹发射单元','近防':'激光近防炮','重型盾':'重型护盾','轻型盾':'轻型护盾','中型盾':'中型护盾'}.get(name,name)
                if fallback and re.fullmatch(r'[A-Z]-\d+',name):name+=' '+str(model_name(fallback))
                add(lid,name,int(m[2]),basis='原档固定编制／明确数量；型号未单列的保持泛型')
        people=book['people']
        def persons(lid,count,t,basis):
            if count is not None and number(count)>0:people[lid]=[{'quantity':int(count),'T':t,'basis':basis}]
        for vid,(fleet,data,path) in vesselmap.items():
            if data.get('active_service') is False:continue
            spec=classes.get(data.get('class_id'),{}).get('immutable_specs',{})
            current=data.get('current_personnel') or data.get('personnel') or data.get('personnel_complement') or {}
            count=current if isinstance(current,int) else next((current[k] for k in ('current_onboard','total','total_final') if isinstance(current.get(k),int)),None)
            if count is None and fleet=='voyager' and spec.get('nominal_personnel_marines'):
                raw=spec['nominal_personnel_marines'];nums=[int(n) for n in re.findall(r'\d+',raw)]
                count=sum(nums[:2]) if '/' in raw and '(' not in raw and '（' not in raw else nums[0]
            persons(vid,count,100 if fleet=='voyager' else None,'当前在舰人数／远航者封板固定编制')
            for key in ('current_embarked_assets','current_armored_vehicles','aviation_engineering','combat_equipment','accepted_loadout','fixed_security_assets','fixed_transport_assets','fixed_engineering_science_assets'):
                fieldpath=path+[key]
                if fleet=='voyager' and key not in at(state,path) and key in state['voyager_fleet'].get('named_vessels',{}).get(vid,{}):fieldpath=['voyager_fleet','named_vessels',vid,key]
                container(vid,data.get(key,{}),fieldpath)
                if key=='accepted_loadout':
                    for name,value in data.get(key,{}).items():
                        if isinstance(value,str):parse_text(vid,value,name)
            if fleet=='voyager' and spec:
                parse_text(vid,spec.get('air_vehicle_complement',''))
                robots=spec.get('robots','')
                if re.fullmatch(r'\d+/\d+',robots):
                    combat,engineering=map(int,robots.split('/'));add(vid,'舰载战斗机器人（型号未单列）',combat,basis='舰级固定编制');add(vid,'SCV工程机器人',engineering,basis='舰级固定编制')
                else:parse_text(vid,robots)
                class_name=classes[data['class_id']].get('name','')
                for row in table_rows(FleetArchive(self.library).segments.get(57,{}).get('markdown',''))[1:]:
                    if row[0].replace('号','') in class_name:
                        for value in row[1:]:parse_text(vid,value)
            for key in ('weapons_defense','personnel_loadout'):
                for name,value in data.get(key,{}).items():
                    if isinstance(value,(int,float)):add(vid,name,value,path+[key,name])
                    elif isinstance(value,str):parse_text(vid,value,name)
        params=state.get('commander_runtime_rules',{}).get('parameters',{})
        persons('farstar',army.get('personnel'),params.get('farstar_voyager_personnel_T_100_v1439',{}).get('base_personal_T'),'远星军现行封板')
        persons('qrf',qrf.get('personnel'),qrf.get('training',{}).get('external_armed_personal_combat_power'),'快反现行训练记录')
        persons('shadow:base',shadow.get('shadow_base_personnel_current',{}).get('personnel'),None,'基地固定指挥与保障人员')
        for fleet in FLEETS:
            used=sum(sum(p['quantity'] for p in people[lid]) for lid,l in loc.items() if l['fleet']==fleet)
            total=state[FLEETS[fleet][1]][PERSON_KEYS[fleet]]
            if used>total:raise ValueError('TRANSFER_PERSONNEL_SOURCE_CONFLICT')
            persons(fleet+':other',total-used,100 if fleet=='voyager' else None,'舰队总人数减已单列编制；包含外勤，不重复计入单舰')
        # Link free stock and its explicit standing allocation to one public pool.
        for item,row in stock['voyager:warehouse'].items():
            if any(b['path'][:2]==['inventories','current_voyager_weapon_inventory_net'] for b in row['bindings']):
                for lid in ('voyager:warehouse','farstar'):
                    for batch in stock[lid].get(item,{}).get('batches',[]):batch['pool']=item
        book['personnel_totals_last']={f:state[FLEETS[f][1]][PERSON_KEYS[f]] for f in FLEETS}
        return book

    def reconcile(self,book,state):
        for rows in book['stock'].values():
            for item,row in rows.items():
                if not row.get('bindings'):continue
                binding=row['bindings'][0]
                try:now=number(at(state,binding['path']))
                except (KeyError,IndexError,TypeError):continue
                delta=(now-number(binding['last']))*number(binding['scale'])
                row['quantity']=textnum(number(row['quantity'])+delta)
                batches=row.setdefault('batches',[])
                if delta>0:
                    batch={'quantity':textnum(delta),'properties':{},'basis':'引擎后续入库记录'}
                    if binding['path'][:2]==['inventories','current_voyager_weapon_inventory_net']:batch['pool']=item
                    batches.append(batch)
                elif delta<0:
                    remaining=-delta
                    for batch in batches:
                        n=min(number(batch['quantity']),remaining);batch['quantity']=textnum(number(batch['quantity'])-n);remaining-=n
                    if remaining:raise ValueError('TRANSFER_STOCK_SOURCE_CONFLICT')
                row['batches']=[b for b in batches if number(b['quantity'])]
                binding['last']=textnum(now)
        def adjust_people(lid,count):
            delta=count-sum(r['quantity'] for r in book['people'][lid]);rows=book['people'][lid]
            if delta>0:rows.append({'quantity':delta,'T':None,'basis':'后续引擎人员增量；T未单列'})
            elif delta<0:
                remaining=-delta
                for row in rows:
                    n=min(row['quantity'],remaining);row['quantity']-=n;remaining-=n
                if remaining:raise ValueError('TRANSFER_PERSONNEL_SOURCE_CONFLICT')
                book['people'][lid]=[r for r in rows if r['quantity']]
        for vid,(fleet,data,path) in ships(state).items():
            if vid not in book['locations']:
                fresh=self.initial(state);book['locations'][vid]=fresh['locations'][vid];book['stock'][vid]=fresh['stock'][vid];book['people'][vid]=fresh['people'][vid];book['items'].update(fresh['items'])
            book['locations'][vid]['fleet']=fleet
            raw=data.get('current_personnel')
            if raw is None:
                detail=data.get('personnel') or data.get('personnel_complement') or {}
                if isinstance(detail,dict):raw=next((detail[k] for k in ('current_onboard','total','total_final') if isinstance(detail.get(k),int)),None)
            if isinstance(raw,int) and data.get('active_service') is not False:adjust_people(vid,raw)
        for lid,path in [('farstar',['voyager_fleet','farstar_army_current','personnel']),('qrf',['shadow_fleet','quick_reaction_force_current','personnel']),('shadow:base',['shadow_fleet','shadow_base_personnel_current','personnel'])]:adjust_people(lid,at(state,path))
        # A later native turn can change totals. Account for its remaining delta
        # explicitly without recreating the pre-transfer cached pools.
        for fleet in FLEETS:
            total=state[FLEETS[fleet][1]][PERSON_KEYS[fleet]]
            assigned=sum(r['quantity'] for lid,rows in book['people'].items() if book['locations'][lid]['fleet']==fleet and lid!=fleet+':other' for r in rows)
            if assigned>total:raise ValueError('TRANSFER_PERSONNEL_SOURCE_CONFLICT')
            adjust_people(fleet+':other',total-assigned)
            book.setdefault('personnel_totals_last',{})[fleet]=total

    def catalogue(self):
        book=self.book();return {'save_set_id':self.library.manifest['save_set_id'],'locations':list(book['locations'].values()),'items':list(book['items'].values()),
          'vessels':[{'id':vid,'name':d.get('name',vid),'fleet':f,'active':d.get('active_service') is not False} for vid,(f,d,p) in ships(self.state).items()],
          'notice':'内部调动立即调整编制和库存，不推进游戏时间，不调用AI。先核对调出/接收数量，再执行。'}

    def contents(self,location):
        book=self.book()
        if location not in book['locations']:raise ValueError('TRANSFER_LOCATION_NOT_FOUND')
        return {'location':book['locations'][location],'items':[{**book['items'][key],'quantity':row['quantity'],'basis':row['basis'],'batches':row.get('batches',[])} for key,row in book['stock'][location].items()],
                'personnel':sum(p['quantity'] for p in book['people'][location]),'cohorts':book['people'][location]}

    def plan(self,request):
        if not isinstance(request,dict) or set(request)-{'kind','source','destination','item','quantity','vessel','note','name','fleet','personnel_group'}:raise ValueError('TRANSFER_REQUEST_INVALID')
        if len(str(request.get('note','')))>300:raise ValueError('TRANSFER_REQUEST_INVALID')
        book=self.book();baseline=copy.deepcopy(book);state=copy.deepcopy(self.state);before=self.totals(book,state)
        kind=request.get('kind');src=request.get('source');dst=request.get('destination')
        if src==dst and kind!='warehouse':raise ValueError('TRANSFER_SAME_LOCATION')
        if kind in ('items','personnel'):
            if src not in book['locations'] or dst not in book['locations']:raise ValueError('TRANSFER_LOCATION_NOT_FOUND')
            qty=number(request.get('quantity'),True)
            if qty.as_tuple().exponent < -6:raise ValueError('TRANSFER_QUANTITY_PRECISION')
            if kind=='items':
                item=request.get('item')
                if item not in book['items']:raise ValueError('TRANSFER_ITEM_NOT_FOUND')
                if book['items'][item]['unit']!='kg' and qty!=qty.to_integral_value():raise ValueError('TRANSFER_INTEGER_REQUIRED')
                old=book['stock'][src].get(item,{});sv=number(old.get('quantity',0));dv=number(book['stock'][dst].get(item,{}).get('quantity',0))
                if qty>sv:raise ValueError('TRANSFER_INSUFFICIENT_STOCK')
                book['stock'][src][item]['quantity']=textnum(sv-qty)
                target=book['stock'][dst].setdefault(item,{'quantity':'0','basis':'指挥官内部调拨','bindings':[]});target['quantity']=textnum(dv+qty)
                remaining=qty;moved=[]
                for batch in old.get('batches',[{'quantity':textnum(sv),'properties':{},'basis':old.get('basis','当前存档')} ]):
                    n=min(number(batch['quantity']),remaining)
                    if n:moved.append({**copy.deepcopy(batch),'quantity':textnum(n)});batch['quantity']=textnum(number(batch['quantity'])-n);remaining-=n
                old['batches']=[p for p in old.get('batches',[]) if number(p['quantity'])]
                target.setdefault('batches',[]).extend(moved)
                for binding in target.get('bindings',[]):
                    if binding['path'][:2]==['inventories','current_voyager_weapon_inventory_net']:
                        for batch in moved:batch['pool']=item
                description=book['items'][item]['name'];unit=book['items'][item]['unit']
            else:
                if qty!=qty.to_integral_value():raise ValueError('TRANSFER_INTEGER_REQUIRED')
                sv=sum(p['quantity'] for p in book['people'][src]);dv=sum(p['quantity'] for p in book['people'][dst])
                if qty>sv:raise ValueError('TRANSFER_INSUFFICIENT_PERSONNEL')
                remaining=int(qty);moved=[]
                for cohort in book['people'][src]:
                    if request.get('personnel_group','all')!='all' and str(cohort.get('T'))!=request['personnel_group']:continue
                    n=min(cohort['quantity'],remaining)
                    if n:moved.append({**cohort,'quantity':n});cohort['quantity']-=n;remaining-=n
                if remaining:raise ValueError('TRANSFER_INSUFFICIENT_PERSONNEL')
                book['people'][src]=[p for p in book['people'][src] if p['quantity']]
                book['people'][dst]+=moved;description='人员（保留原T记录）';unit='人'
            preview={'description':description,'unit':unit,'quantity':textnum(qty),'source':book['locations'][src]['name'],'destination':book['locations'][dst]['name'],
                'source_before':textnum(sv),'source_after':textnum(number(sv)-qty),'destination_before':textnum(dv),'destination_after':textnum(number(dv)+qty)}
            preview['batches' if kind=='items' else 'cohorts']=moved
        elif kind=='vessels':
            vid=request.get('vessel');vmap=ships(state)
            if vid not in vmap or dst not in FLEETS:raise ValueError('TRANSFER_VESSEL_NOT_FOUND')
            src,data,path=vmap[vid]
            if data.get('active_service') is False:raise ValueError('TRANSFER_VESSEL_INACTIVE')
            if src==dst:raise ValueError('TRANSFER_SAME_LOCATION')
            self.move_vessel(state,book,vid,src,dst,data)
            preview={'description':data.get('name',vid),'unit':'艘','quantity':'1','source':FLEET_NAMES[src],'destination':FLEET_NAMES[dst],
                'source_before':str(sum(f==src and d.get('active_service') is not False for f,d,p in vmap.values())),'source_after':str(sum(f==src and d.get('active_service') is not False for f,d,p in vmap.values())-1),
                'destination_before':str(sum(f==dst and d.get('active_service') is not False for f,d,p in vmap.values())),'destination_after':str(sum(f==dst and d.get('active_service') is not False for f,d,p in vmap.values())+1),
                'carried_personnel':sum(p['quantity'] for p in book['people'][vid]),'carried_items':sum(number(row['quantity'])>0 for row in book['stock'][vid].values()),
                'note':'整舰转隶，保留舰名、属性与既有任务记录；已登记随舰人员和物资随舰转属。未登记人员不补造。'}
        elif kind=='warehouse':
            name=str(request.get('name','')).strip();fleet=request.get('fleet')
            if fleet not in FLEETS or not name or len(name)>50 or any(ord(c)<32 for c in name):raise ValueError('TRANSFER_WAREHOUSE_INVALID')
            if any(l['name']==name and l['fleet']==fleet for l in book['locations'].values()):raise ValueError('TRANSFER_WAREHOUSE_EXISTS')
            lid='warehouse:'+digest({'name':name,'fleet':fleet})[:18]
            book['locations'][lid]={'id':lid,'name':name,'fleet':fleet,'kind':'warehouse'};book['stock'][lid]={};book['people'][lid]=[]
            preview={'description':'建立空仓库','quantity':'1','unit':'个','source':FLEET_NAMES[fleet],'destination':name,'source_before':'0','source_after':'0','destination_before':'0','destination_after':'0','note':'新仓库初始为空；可从既有舰船、编制或仓库调入物资和人员。'}
        else:raise ValueError('TRANSFER_KIND_INVALID')
        book.setdefault('changed_locations',[])
        for lid in (src,dst,request.get('vessel')):
            if lid in book['locations'] and lid not in book['changed_locations']:book['changed_locations'].append(lid)
        routes=[]
        if kind=='vessels':
            oldmap=ships(self.state);newmap=ships(state)
            routes=[('.'.join(map(str,oldmap[v][2])),'.'.join(map(str,newmap[v][2]))) for v in oldmap if oldmap[v][2]!=newmap[v][2]]
            for key in ('entity_registry','task_allocations'):
                if key in state:state[key]=remap_refs(state[key],routes)
            state['engine_runtime']=remap_refs(state['engine_runtime'],routes)
        self.sync(state,book,baseline)
        after=self.totals(book,state)
        if before!=after:raise ValueError('TRANSFER_CONSERVATION_FAILED')
        return {'state':state,'book':book,'preview':preview,'routes':routes,'base_save_set_id':self.library.manifest['save_set_id'],'request':request,'request_hash':digest(request)}

    def totals(self,book,state):
        assets={key:textnum(sum((number(rows.get(key,{}).get('quantity',0)) for rows in book['stock'].values()),Decimal(0))) for key in book['items']}
        return {'assets':assets,'personnel':sum(p['quantity'] for rows in book['people'].values() for p in rows),'ships':sorted(ships(state))}

    def move_vessel(self,state,book,vid,src,dst,data):
        old_paths={key:path for key,(fleet,record,path) in ships(state).items()}
        source=state[FLEETS[src][1]];target=state[FLEETS[dst][1]]
        if src=='voyager':
            source['vessel_roster']=[r for r in source['vessel_roster'] if r['vessel_id']!=vid];source.get('named_vessels',{}).pop(vid,None)
        else:source['vessels'].pop(vid)
        data=copy.deepcopy(data);data['internal_transfer_current']={'from_fleet':src,'to_fleet':dst,'as_of':state['game_time']}
        registration=state['voyager_fleet']['vessel_naming'].setdefault('internal_transfer_registration',{})
        for key,(fleet,record,recordpath) in ships(self.state).items():
            registration.setdefault(key,{k:record[k] for k in ('name','class_id','serial','naming_prefix') if k in record})
        # Reassignment preserves physical position; it does not teleport a ship.
        position={'location_name':data.get('current_location') or data.get('location') or data.get('location_id') or ('远航者基地' if src=='voyager' else '原记录位置未单列'),'location_id':data.get('location_id')}
        for partkey,basekey in [('current_location_partition','at_voyager_base'),('current_location','at_shadow_base')]:
            part=source.get(partkey)
            if not isinstance(part,dict):continue
            found=False
            for section in [*part.get('deployments',{}).values(),part.get('transit',{})]:
                if not isinstance(section,dict) or vid not in section.get('vessels',[]):continue
                position={k:section[k] for k in ('location_name','location_id') if k in section};section['vessels'].remove(vid);section['ships']=len(section['vessels']);found=True
            base=part.get(basekey,{})
            if vid in base.get('vessels',[]):base['vessels'].remove(vid);base['ships']=len(base['vessels']);found=True;position={'location_name':'S-B5暗影基地','location_id':part.get('homeport')}
            if src=='voyager' and not found:base['ships']=max(0,base.get('ships',0)-1)
        data['internal_transfer_current']['position_preserved']=position
        if dst=='shadow':
            data['active_service']=data.get('active_service',True)
            part=target.setdefault('current_location',{});part.setdefault('deployments',{})['internal_'+vid]={'ships':1 if data.get('active_service') is not False else 0,'vessels':[vid] if data.get('active_service') is not False else [],**position,'status':'内部转隶；保持原物理位置','as_of':state['game_time']}
        if dst=='voyager':
            part=target['current_location_partition'];part.setdefault('deployments',{})['internal_'+vid]={'ships':1,'vessels':[vid],**position,'status':'内部转隶；保持原物理位置','as_of':state['game_time']}
            # Voyager's location partition is the sole location authority.
            # Preserve the former per-ship fields inside the transfer receipt.
            for key in ('location_id','location_name','location','current_location','current_location_status'):
                if key in data:data['internal_transfer_current'].setdefault('previous_location_fields',{})[key]=data.pop(key)
            if str(data.get('status','')).startswith('at_'):data['status']='active_voyager_service_internal_transfer'
            # Voyager requires a naming registration even for received foreign hulls.
            if data.get('class_id') not in {r['class_id'] for r in target['class_counts']}:
                data['class_id']=data.get('class_id') or 'INTERNAL-FOREIGN-'+vid
                data['external_owned']=True;data['serial']=data.get('serial') or int(re.search(r'(\d+)(?:号)?$',data['name'])[1]) if re.search(r'(\d+)(?:号)?$',data['name']) else 1
                data['naming_prefix']=data.get('naming_prefix') or re.sub(r'[-\d号]+$','',data['name'])
                data['registered_class_name']=data['naming_prefix']+'级'
        data['current_control']={'voyager':'PER-COMMANDER-01','jinchuan':'PER-DANIEL-01','shadow':'PER-NOVA-01'}[dst]
        if dst=='voyager':
            target.setdefault('vessel_roster',[]).append({k:v for k,v in data.items() if k in ('vessel_id','name','class_id','serial','naming_prefix','external_owned','registered_class_name','active_service')})
            target.setdefault('named_vessels',{})[vid]=data
        else:target.setdefault('vessels',{})[vid]=data
        book['locations'][vid]['fleet']=dst
        new_paths={key:path for key,(fleet,record,path) in ships(state).items()}
        # Roster removal shifts array indices; rebind every vessel, not only the moved one.
        for vessel,old in old_paths.items():
            new=new_paths[vessel]
            for row in book['stock'][vessel].values():
                for binding in row['bindings']:
                    if binding['path'][:len(old)]==old:binding['path']=new+binding['path'][len(old):]
                    elif vessel==vid and binding['path'][:3]==['voyager_fleet','named_vessels',vid]:binding['path']=new+binding['path'][3:]
        if src=='shadow':source['vessels_owned_total']-=1
        if dst=='shadow':target['vessels_owned_total']+=1
        registry=state.get('entity_registry',{}).get('entities',{}).get(vid)
        if registry:
            registry['state_path']=FLEETS[dst][1]+('.named_vessels.' if dst=='voyager' else '.vessels.')+vid

    def sync(self,state,book,baseline):
        for rows in book['stock'].values():
            for row in rows.values():
                for binding in row['bindings']:
                    try:at(state,binding['path'])
                    except (KeyError,IndexError,TypeError):continue
                    value=number(row['quantity'])/number(binding['scale']);old=number(at(state,binding['path']));delta=value-old
                    put(state,binding['path'],jsonnum(value));binding['last']=textnum(value)
                    parent=at(state,binding['path'][:-1])
                    # Native inventory identity: owned = available + allocated + reserved.
                    # A free-stock transfer changes owned by exactly the same amount.
                    if binding['path'][-1]=='available' and isinstance(parent,dict):
                        for total in ('total_owned','qty'):
                            if isinstance(parent.get(total),(int,float)):parent[total]=jsonnum(number(parent[total])+delta)
        # Rebuild just the public-pool projection. Ship fixed complements have
        # their own accounting and never get added to this public total.
        mirrors={'制式步枪':'service_rifles','霰弹枪':'shotguns','手枪':'pistols','一次性火箭筒':'disposable_rocket_launchers','单兵导弹':'individual_missiles','多功能手雷':'grenades','M2动力甲':'m2_exoskeletons','卫士1公共库存':'guardian1_public','彩虹1公共库存':'rainbow1_strike_uav_public','沙丘装甲车公共库存':'dune_armored_vehicles_public'}
        for item,row in book['stock']['voyager:warehouse'].items():
            for binding in row['bindings']:
                path=binding['path']
                if path[:2]!=['inventories','current_voyager_weapon_inventory_net']:continue
                parent=at(state,path[:-1]);alloc={}
                for lid,rows in book['stock'].items():
                    if lid=='voyager:warehouse' or book['locations'][lid]['fleet']!='voyager':continue
                    n=sum((number(b['quantity']) for b in rows.get(item,{}).get('batches',[]) if b.get('pool')==item),Decimal(0))
                    if n:alloc[book['locations'][lid]['name']]=jsonnum(n)
                if not isinstance(parent,dict):continue
                total=number(row['quantity'])+sum((number(n) for n in alloc.values()),Decimal(0))
                if 'available' in parent or alloc:
                    parent['available']=jsonnum(row['quantity']);parent['allocated']=alloc
                    if path[-1]=='qty':binding['path']=path[:-1]+['available'];binding['last']=row['quantity']
                for key in ('total_owned','qty'):
                    if key in parent:parent[key]=jsonnum(total)
                name=path[-2]
                mirror=state.get('inventories',{}).get('weapon_inventory',{}).get('self_owned',{}).get(mirrors.get(name))
                if mirror:mirror['value']=jsonnum(total)
        army=state['voyager_fleet'].get('farstar_army_current',{});army['personnel']=sum(p['quantity'] for p in book['people']['farstar'])
        qrf=state['shadow_fleet'].get('quick_reaction_force_current',{});qrf['personnel']=sum(p['quantity'] for p in book['people']['qrf'])
        base=state['shadow_fleet'].get('shadow_base_personnel_current',{});base['personnel']=sum(p['quantity'] for p in book['people']['shadow:base'])
        public=state['shadow_fleet'].get('inventory_summary_current',{}).get('public',{})
        armory=state['shadow_fleet'].get('general_armory',{})
        armory_keys={'外购步枪':'external_rifles','外购手枪':'external_pistols','单兵导弹':'individual_missiles','外购一次性反装甲火箭筒':'disposable_antiarmor_launchers','多功能手雷':'multifunction_grenades','电击棒':'electric_batons_usable'}
        for item,row in book['stock']['shadow:warehouse'].items():
            delta=number(row['quantity'])-number(baseline['stock']['shadow:warehouse'].get(item,{}).get('quantity',0))
            name=book['items'][item]['name'];original=next((k for k in public if ALIASES.get(k,k)==name),None)
            if original and isinstance(public[original],(int,float)):public[original]=jsonnum(number(public[original])+delta)
            key=armory_keys.get(name)
            if key in armory and isinstance(armory[key],(int,float)):armory[key]=jsonnum(number(armory[key])+delta)
        for item,row in book['stock']['qrf'].items():
            name=book['items'][item]['name']
            for key in ('robots','uavs'):
                if name in qrf.get(key,{}):qrf[key][name]=jsonnum(row['quantity'])
        equipped=qrf.get('power_armor_current',{}).get('equipped',{})
        if equipped:equipped['total']=sum(v for k,v in equipped.items() if k!='total' and isinstance(v,(int,float)))
        military=state['shadow_fleet'].get('explosives_inventory_current',{}).get('military',{})
        if 'stock_kg' in military and 'stock_t' in military:military['stock_t']=jsonnum(number(military['stock_kg'])/1000)
        for vid,(fleet,data,path) in ships(state).items():
            row=at(state,path);count=sum(p['quantity'] for p in book['people'][vid])
            oldcount=sum(p['quantity'] for p in baseline['people'][vid])
            if count!=oldcount:
                row['current_personnel']=count
                detail=row.get('personnel') or row.get('personnel_complement')
                if isinstance(detail,dict):
                    for key in ('current_onboard','total','total_final'):
                        if key in detail:detail[key]=count
                row['personnel_composition_note']='人数已由内部调动更新；原岗位细分为此前记录，现行T分组见调动后人员。'
            row['internal_logistics_current']={'as_of':state['game_time'],'personnel':count,'personnel_cohorts':copy.deepcopy(book['people'][vid]),
                'assets':{book['items'][key]['name']:{'quantity':jsonnum(value['quantity']),'unit':book['items'][key]['unit']} for key,value in book['stock'][vid].items()}}
            if fleet=='shadow':row['current_combat_robot_count']=sum(robot_models(row['internal_logistics_current']['assets']).values())
        summary=state['summary'];fleet_people={}
        for fleet in FLEETS:
            d=state[FLEETS[fleet][1]];people=sum(p['quantity'] for lid,rows in book['people'].items() if book['locations'][lid]['fleet']==fleet for p in rows)
            d[PERSON_KEYS[fleet]]=people
            if 'current_personnel' in d:d['current_personnel']=people
            fleet_people[fleet]=people;summary['personnel'][fleet]=people
            current=[r for f,r,p in ships(state).values() if f==fleet];active=sum(r.get('active_service') is not False for r in current)
            if fleet=='shadow':d['ship_count_active']=active;summary['ships']['shadow_active']=active
            else:d['ship_count']=active;summary['ships'][fleet]=active
        voyager=state['voyager_fleet'];classes={}
        for row in voyager.get('vessel_roster',[]):
            if row.get('class_id'):classes[row['class_id']]=classes.get(row['class_id'],0)+1
        for row in voyager.get('class_counts',[]):row['count']=classes.get(row['class_id'],0)
        voyager['standard_class_ship_count']=sum(r['count'] for r in voyager['class_counts']);voyager['external_owned_ship_count']=voyager['ship_count']-voyager['standard_class_ship_count']
        rule=voyager['vessel_naming'];rule['current_external_classes']={r['vessel_id']:{'registered_class_name':r.get('registered_class_name'),'naming_prefix':r.get('naming_prefix'),'serial':r.get('serial'),'formal_name':r['name']} for r in voyager['vessel_roster'] if r.get('external_owned')}
        structure=state['shadow_fleet'].get('personnel_structure_current',{})
        structure.update(shipboard_personnel=sum(sum(p['quantity'] for p in book['people'][vid]) for vid,(fleet,data,path) in ships(state).items() if fleet=='shadow'),quick_reaction_force=qrf['personnel'],shadow_base_personnel=base['personnel'],total=fleet_people['shadow'],as_of=state['game_time'])
        summary['personnel']['total']=fleet_people['voyager']+fleet_people['jinchuan'];summary['personnel']['total_player_active']=sum(fleet_people.values())
        summary['ships']['total']=summary['ships']['voyager']+summary['ships']['jinchuan'];summary['ships']['total_player_active']=summary['ships']['total']+summary['ships']['shadow_active']
        shadow=state['shadow_fleet']
        models={'fortress5':0,'fortress6':0}
        for vid,(fleet,data,path) in ships(state).items():
            if fleet!='shadow' or data.get('active_service') is False:continue
            for name,n in robot_models(at(state,path)['internal_logistics_current']['assets']).items():models[name]=models.get(name,0)+n
        aggregate=shadow.setdefault('mobile_combat_assets_current',{}).setdefault('shipboard_combat_robots',{})
        aggregate.update(total=sum(models.values()),models_exact_current=models,as_of=state['game_time'])
        # This is explicitly a rebuildable report, not quantity authority.
        if book['stock']!=baseline['stock'] or book['people']!=baseline['people'] or book['locations']!=baseline['locations']:shadow.pop('ground_power_snapshot',None)
        if isinstance(shadow.get('personnel'),dict):shadow['personnel'].update(total=fleet_people['shadow'],quick_reaction_force=qrf['personnel'],shadow_base_personnel=base['personnel'])
        if 'authoritative_total' in state['jinchuan_fleet'].get('personnel_reconciliation',{}):state['jinchuan_fleet']['personnel_reconciliation']['authoritative_total']=fleet_people['jinchuan']
        book['personnel_totals_last']=fleet_people
        # Existing canonical asset-ledger projections must remain compatible.
        for asset in state.get('asset_ledger_v1',{}).get('assets',{}).values():
            for path in asset.get('source_paths',[]):
                try:value=at(state,path.split('.'))
                except (KeyError,TypeError):continue
                if isinstance(value,(int,float)):asset.setdefault('fields',{})['quantity']=value
        book['revision']+=1;state.setdefault('engine_runtime',{})[KEY]=book


def commit(bridge,plan,command_id):
    """Commit one exact confirmed plan through the original native atomic saver."""
    if not re.fullmatch(r'MOVE-[A-Za-z0-9-]{8,100}',command_id):raise ValueError('TRANSFER_ID_INVALID')
    with bridge.lock:
        a=bridge.host._engine();root=bridge.root
        current=json.loads((root/'state.json').read_bytes());manifest=json.loads((root/'manifest.json').read_bytes())
        old=current.get('engine_runtime',{}).get(KEY,{}).get('receipts',{}).get(command_id)
        if old:
            if old['request_hash']!=plan['request_hash']:raise ValueError('TRANSFER_ID_REUSED')
            return {'status':'SAVED','already_applied':True,'receipt':old}
        if manifest['save_set_id']!=plan['base_save_set_id']:raise ValueError('TRANSFER_STALE_PREVIEW')
        info=a.create_stage(root,'internal_transfer');stage=Path(info['staging'])
        try:
            state=copy.deepcopy(plan['state']);receipt={'id':command_id,'request_hash':plan['request_hash'],'request':plan['request'],'preview':plan['preview'],'game_time':state['game_time']}
            state['engine_runtime'][KEY]['receipts'][command_id]=receipt
            a._write_authority_json(stage/'state.json',state)
            if plan.get('routes'):
                tasks=json.loads((stage/'tasks.json').read_bytes());a._write_authority_json(stage/'tasks.json',remap_refs(tasks,plan['routes']))
            a._append_engine_history(stage/'events.jsonl',{'event_id':'INTERNAL-'+command_id,'game_time':state['game_time'],'recorded_at':state['game_time'],'type':'system','subtype':'commander_internal_transfer','summary':plan['preview']['source']+' → '+plan['preview']['destination']+'：'+plan['preview']['description']+' '+plan['preview']['quantity']+plan['preview']['unit'],
                'source':'浏览器内部调动工具 · 指挥官确认','authority_files':['state.json'],'zero_time':True,'changes':[{'target':'state:engine_runtime.'+KEY,'action':'conserved_internal_transfer'}],'receipt':receipt})
            result=a.atomic_save(stage,bridge.next_version(),'内部调动',root,False,False)
            return {'status':'SAVED','receipt':receipt,'save_set_id':result.get('save_set_id')}
        except Exception:
            if stage.exists():a.writable_tree(stage);shutil.rmtree(stage,ignore_errors=True)
            raise
