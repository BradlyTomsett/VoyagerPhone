"""Read-only fleet dossiers derived from the current save and original designs."""
import re
from backend.source_library import compact, pointer

FLEETS = {'voyager': ('远航者舰队', 'voyager_fleet'),
          'jinchuan': ('金川舰队', 'jinchuan_fleet'),
          'shadow': ('暗影舰队', 'shadow_fleet')}
MODEL_NAMES = {
 'fortress4':'堡垒-4','fortress5':'堡垒-5','fortress6':'堡垒-6',
 'falcon2':'猎隼-2','falcon3':'猎隼-3','falcon4':'猎隼-4',
 'pioneer2':'先锋-2','pioneer3':'先锋-3','pioneer4':'先锋-4','pioneer5':'先锋-5',
 'hq_m2_marines':'M2动力甲','guardian1':'卫士1','rainbow1':'彩虹1',
 'scv':'SCV工程机器人','workbee11':'工蜂-11','bumblebee':'大黄蜂',
 'hummingbird':'蜂鸟穿梭机','nighthawk_shuttle':'夜鹰穿梭机',
 'hercules_light_landing_craft':'大力神轻型登陆艇','dragonfly_uav':'蜻蜓侦察无人机',
 'dune':'沙丘装甲车','yao3':'鹞-3','ninghang5':'宁航-5',
 'light_laser':'小口径激光炮','light_ship_laser':'小口径舰载激光炮',
 'small_caliber_railgun':'小口径电磁炮','small_em':'小口径电磁炮',
 'laser_ciws':'激光近防炮','light_shield':'轻型护盾','missile_system':'导弹系统'}


def model_name(name):
    key=re.sub(r'^external_', '', str(name))
    return MODEL_NAMES.get(key, name)


def normal(value):
    return re.sub(r'[\s_\-·号级公共库存型]', '', str(value)).casefold()


def table_rows(text):
    rows=[]
    for line in text.splitlines():
        if not line.strip().startswith('|'):continue
        cells=[c.strip().replace('**','') for c in line.strip().strip('|').split('|')]
        if all(re.fullmatch(r'[-: ]+',c) for c in cells):continue
        rows.append(cells)
    return rows


class FleetArchive:
    def __init__(self,library):
        self.library=library
        self.state=library.documents['state'];self.catalog=library.documents['catalog']
        self.entities=self.catalog.get('catalog_registry',{}).get('entities',{})
        self.segments={s['order']:s for s in self.catalog.get('document_segments',[])}
        self.segment_paths={s['order']:'/document_segments/'+str(i) for i,s in enumerate(self.catalog.get('document_segments',[]))}

    def _fleet(self,fleet):
        if fleet not in FLEETS:raise ValueError('FLEET_NOT_FOUND')
        return self.state.get(FLEETS[fleet][1],{})

    def _record(self,title,path,value,source='state.json',kind='当前存档记录'):
        return {'title':title,'ref':source+'#'+path,'value':value,'kind':kind,
                'as_of':value.get('as_of') if isinstance(value,dict) else None}

    def _ships(self,fleet):
        data=self._fleet(fleet);root='/'+FLEETS[fleet][1]
        ships={}
        if fleet=='voyager':
            for i,row in enumerate(data.get('vessel_roster',[])):
                ships[row['vessel_id']]={'data':dict(row),'records':[self._record('舰船名册',root+'/vessel_roster/'+str(i),row)]}
            for vid,row in data.get('named_vessels',{}).items():
                ship=ships.setdefault(vid,{'data':{},'records':[]})
                ship['data'].update(row);ship['records'].append(self._record('单舰补充记录',root+'/named_vessels/'+vid,row))
        else:
            for vid,row in data.get('vessels',{}).items():
                ships[vid]={'data':dict(row),'records':[self._record('单舰原档',root+'/vessels/'+vid,row)]}
        return ships

    def overview(self,fleet):
        data=self._fleet(fleet);ships=[]
        for vid,item in self._ships(fleet).items():
            d=item['data'];design=self.entities.get(d.get('class_id'),{})
            specs=design.get('immutable_specs',{})
            length=str(d['length_m'])+'m' if 'length_m' in d else specs.get('length')
            if not length:
                written=re.search(r'(\d+(?:\.\d+)?)\s*(?:m|米)',d.get('type',''),re.I)
                if written:length=written.group(1)+'m'
            ships.append({'id':vid,'name':d.get('name',vid),'class_name':design.get('name') or d.get('type') or '原文未注明舰级',
                          'length':length or '原文未单列',
                          'status':d.get('status','在名册中；以当前调度记录为准'),
                          'active_service':d.get('active_service'), 'class_id':d.get('class_id'),
                          'ref':item['records'][0]['ref']})
        return {'fleet':fleet,'name':FLEETS[fleet][0],'game_time':self.library.manifest['game_time'],
                'ships':ships,'record_count':len(ships),'class_counts':data.get('class_counts',[]),
                'active_count':data.get('ship_count_active',data.get('ship_count')),
                'owned_count':data.get('vessels_owned_total'),
                'notice':'现役总数、持有总数与具名单舰记录是不同口径。舰级设计是固定模板；当前改装、损伤、配属和位置以有日期的现行记录为准。未记录的性能不补造。'}

    def ship(self,fleet,vessel):
        ships=self._ships(fleet)
        if vessel not in ships:raise ValueError('VESSEL_NOT_FOUND')
        item=ships[vessel];d=item['data'];data=self._fleet(fleet);records=[]
        class_id=d.get('class_id');design=self.entities.get(class_id,{})
        if design:
            records.append(self._record('舰级固定设计','/catalog_registry/entities/'+class_id,design,'catalog.json','永久设计；不代表当前实装'))
            class_name=design.get('name','')
            for i,row in enumerate(table_rows(self.segments.get(57,{}).get('markdown',''))[1:]):
                base=normal(row[0]);target=normal(class_name)
                if base and base in target:
                    records.append(self._record('固定武器与防护',self.segment_paths[57]+'/markdown',
                        dict(zip(['舰级','主副武器','导弹与近防','护盾与装甲'],row)),'catalog.json','永久设计；不代表当前实装'))
            combat=data.get('class_combat_power_snapshot',{})
            if class_name in combat.get('classes',{}):
                records.append(self._record('舰级战力封板','/'+FLEETS[fleet][1]+'/class_combat_power_snapshot',
                    {'as_of':combat.get('as_of'),'口径':combat.get('rule'),'单舰参数':combat['classes'][class_name],'说明':combat.get('inventory_exclusion')}))
        audit=data.get('armament_audit_current',{})
        aliases=[d.get('name',''),d.get('former_name',''),*d.get('former_names',[])]
        for name,values in audit.get('ships',{}).items():
            if any(normal(name)==normal(alias) for alias in aliases if alias):
                records.append(self._record('现行武备审计','/'+FLEETS[fleet][1]+'/armament_audit_current/ships/'+name,
                    {'as_of':audit.get('as_of'),**values}))
        for key,title in [('current_location_partition','舰队位置与外派'),('current_location','当前舰队部署'),
                          ('current_uav_loadout','现行舰载无人机'),('fleet_navigation','航行与任务位置')]:
            value=data.get(key)
            if value:records.append(self._record(title,'/'+FLEETS[fleet][1]+'/'+key,value))
        records+=item['records']
        return {'id':vessel,'name':d.get('name',vessel),'records':records,
                'notice':'固定设计、武备审计和单舰原档分别列出；原档中的 planned、历史改装与旧任务字段保留追溯，不自动覆盖现行配装。'}

    def inventory(self,fleet):
        data=self._fleet(fleet);root='/'+FLEETS[fleet][1];groups=[]
        def group(title,path,values,as_of=None):
            if not isinstance(values,dict):return
            rows=[]
            for name,value in values.items():
                if name in ('as_of','note','authority','status','location','scope_note','personnel','classification_rule','reporting_policy'):continue
                nested={'robots':'机器人','engineering_robots':'工程机器人','uavs':'无人机','armored_vehicles':'装甲车辆','power_armor':'动力甲','shuttles_unassigned':'未配属穿梭机','armory':'军械'}
                if isinstance(value,dict) and (name in nested or (fleet=='jinchuan' and '/current_uav_loadout' in path)):
                    group(title+' · '+nested.get(name,name),path+pointer([name]),value,as_of);continue
                rows.append({'name':str(model_name(name)),'key':name,'value':value,'ref':'state.json#'+path+pointer([name]),'as_of':as_of})
            if rows:groups.append({'title':title,'rows':rows,'ref':'state.json#'+path,'as_of':as_of})
        if fleet=='voyager':
            inv=self.state.get('inventories',{});net=inv.get('current_voyager_weapon_inventory_net',{})
            for key,title in [('self_owned_public','自有公共装备与常设配属'),('external_current_owned','外购装备当前产权')]:
                group(title,'/inventories/current_voyager_weapon_inventory_net/'+key,net.get(key),net.get('as_of'))
            v=inv.get('current_voyager_armored_vehicle_inventory_net',{})
            group('外购装甲车辆','/inventories/current_voyager_armored_vehicle_inventory_net/models',v.get('models'),v.get('as_of'))
            group('非武器库存',root+'/nonweapon_inventory_current',data.get('nonweapon_inventory_current'),data.get('nonweapon_inventory_current',{}).get('as_of'))
            group('公共工程资产',root+'/public_engineering_assets_current',data.get('public_engineering_assets_current'))
        elif fleet=='shadow':
            inv=data.get('inventory_summary_current',{})
            for key,title in [('shipboard','舰载固定装备'),('qrf','快反部队配属'),('public','公共产权记录（含另列领用）'),
                              ('public_warehouse_current','公共仓库实物分布'),('engineering_support','工程支援分布'),('field_allocated','外勤临时携行')]:
                group(title,root+'/inventory_summary_current/'+key,inv.get(key),inv.get('as_of'))
        else:
            for vid,item in self._ships(fleet).items():
                for key,title in [('aviation_engineering','航空与工程'),('combat_equipment','地面装备'),('weapons_defense','武器与防护')]:
                    group(item['data'].get('name',vid)+' · '+title,root+'/vessels/'+vid+'/'+key,item['data'].get(key))
            group('现行舰载无人机（优先于旧改装计划）',root+'/current_uav_loadout',data.get('current_uav_loadout'),data.get('current_uav_loadout',{}).get('as_of'))
        models={e.get('name') for eid,e in self.entities.items() if eid.startswith('EQP-') and e.get('name')}
        models.update(row['name'] for g in groups for row in g['rows'])
        return {'groups':groups,'models':sorted(models),'notice':'各表按原档位置、产权与用途分别列示，不跨表相加。总量、可用、配属、待修、领用与在仓数量保留各自口径。舰级固定装备另见舰级配置；尚未验收的采购另见全部记录。'}

    def equipment(self,query,offset=0):
        query=str(query).strip()[:150];target=normal(model_name(query));records=[]
        for eid,entity in self.entities.items():
            if not eid.startswith('EQP-'):continue
            names=[entity.get('name',''),*entity.get('aliases',[])]
            if target and any(target in normal(n) or normal(n) in target for n in names if n):
                records.append(self._record(entity.get('name',eid),'/catalog_registry/entities/'+eid,entity,'catalog.json','型号设定；数量以当前存档为准'))
        matches=self.library.search(str(model_name(query)),offset=offset,limit=16,category='world')
        return {'query':query,'specifications':records,'references':matches,
                'notice':'A为空战指标、G为地面战力；其他系数保留原文解释。这里只展示原档已有性能与设定，旧价格或持有量说明不覆盖当前库存。'}

    def records(self,fleet):
        data=self._fleet(fleet);root='/'+FLEETS[fleet][1]
        records=[self._record(k,root+'/'+k,v) for k,v in data.items()]
        records += [self._record('共享库存原档（按产权区分） · '+k,'/inventories/'+k,v) for k,v in self.state.get('inventories',{}).items()]
        for key in ('fleet_and_logistics','engineering_and_maintenance'):
            records.append(self._record('关联地区与设施 · '+key,'/world_state_overrides/'+key,self.state.get('world_state_overrides',{}).get(key,{})))
        records.append(self._record('固定性能参数','/static_catalog',self.catalog.get('static_catalog',{}),'catalog.json','永久设定'))
        for order in (56,57,58,59):
            segment=self.segments.get(order)
            if segment:records.append(self._record('舰船与装备设计原文 · '+str(order),self.segment_paths[order],segment,'catalog.json','永久设计'))
        records.append(self._record('性能与航行规则（完整）','',self.library.documents['rules'],'rules.json','游戏规则'))
        return {'records':records,'notice':'完整展开原档各字段。历史、计划、旧盘点与更正可能同时存在，按日期、原文权威说明及现行引擎口径判断；不要把所有数字相加。'}
