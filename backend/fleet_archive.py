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
 'laser_ciws':'激光近防炮','light_shield':'轻型护盾','missile_system':'导弹系统',
 'missile_launcher_units':'导弹发射单元','engineering_explosives':'工程炸药',
 'military_explosives_current':'军用炸药','scv_public':'SCV公共库存',
 'industrial':'工业炸药','military':'军用炸药','shuttles_unassigned':'未配属穿梭机',
 'small_em_cannon':'小口径电磁炮'}
WEAPON_DIRECTORY = ['步枪','手枪','霰弹枪','多功能手雷','一次性火箭筒','单兵导弹',
 '小口径激光炮','中口径激光炮','大口径激光炮','小口径等离子炮','中口径等离子炮','大口径等离子炮',
 '小口径电磁炮','中口径电磁炮','大口径电磁炮','激光近防炮','导弹发射单元',
 '轻型护盾','中型护盾','重型护盾','军用炸药','工程炸药']
SCALE_RULE='RULE-COMBAT-TWO-SCALE-83630910'
RANGE_RULE='RULE-PLAYER-FULL-INTEGRITY-RANGE-UPPER-01'
GRENADE_RULE='RULE-MULTIFUNCTION-GRENADE-SIX-MODES-83631202'


def model_name(name):
    key=re.sub(r'^external_', '', str(name))
    vintage=re.fullmatch(r'(.+)_used_(\d+)y',key)
    if vintage:return str(MODEL_NAMES.get(vintage[1],vintage[1]))+'（服役'+vintage[2]+'年）'
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
        self.rules=library.documents['rules']
        self.rule_registry=self.rules.get('rule_registry',{}).get('rules',{})
        self.segments={s['order']:s for s in self.catalog.get('document_segments',[])}
        self.segment_paths={s['order']:'/document_segments/'+str(i) for i,s in enumerate(self.catalog.get('document_segments',[]))}

    def _fleet(self,fleet):
        if fleet not in FLEETS:raise ValueError('FLEET_NOT_FOUND')
        return self.state.get(FLEETS[fleet][1],{})

    def _record(self,title,path,value,source='state.json',kind='当前存档记录'):
        return {'title':title,'ref':source+'#'+path,'value':value,'kind':kind,
                'as_of':value.get('as_of') if isinstance(value,dict) else None}

    def _rule(self,rid):
        value=self.rule_registry.get(rid)
        return self._record(value.get('title',rid),'/rule_registry/rules/'+rid,value,'rules.json','现行规则') if value else None

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
        scale=self._rule(SCALE_RULE)
        if scale:records.append(scale)
        records+=item['records']
        return {'id':vessel,'name':d.get('name',vessel),'records':records,
                'notice':'固定设计、武备审计和单舰原档分别列出；原档中的计划配装、历史改装与旧任务保留追溯，不自动覆盖现行配装。'}

    def inventory(self,fleet):
        data=self._fleet(fleet);root='/'+FLEETS[fleet][1];groups=[]
        def group(title,path,values,as_of=None):
            if not isinstance(values,dict):return
            rows=[]
            for name,value in values.items():
                if name in ('as_of','note','authority','status','location','scope_note','personnel','classification_rule','reporting_policy','owner','source','separation','delivery'):continue
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
            group('保障装备与爆破物（公共／舰载数量不合并）','/inventories/support_inventory/self_owned',inv.get('support_inventory',{}).get('self_owned'))
        elif fleet=='shadow':
            inv=data.get('inventory_summary_current',{})
            for key,title in [('shipboard','舰载固定装备'),('qrf','快反部队配属'),('public','公共产权记录（含另列领用）'),
                              ('public_warehouse_current','公共仓库实物分布'),('engineering_support','工程支援分布'),('field_allocated','外勤临时携行')]:
                group(title,root+'/inventory_summary_current/'+key,inv.get(key),inv.get('as_of'))
            group('军用与工业爆破物分账',root+'/explosives_inventory_current',data.get('explosives_inventory_current'),data.get('explosives_inventory_current',{}).get('as_of'))
        else:
            for vid,item in self._ships(fleet).items():
                for key,title in [('aviation_engineering','航空与工程'),('combat_equipment','地面装备'),('weapons_defense','武器与防护')]:
                    group(item['data'].get('name',vid)+' · '+title,root+'/vessels/'+vid+'/'+key,item['data'].get(key))
            group('现行舰载无人机（优先于旧改装计划）',root+'/current_uav_loadout',data.get('current_uav_loadout'),data.get('current_uav_loadout',{}).get('as_of'))
        models={e.get('name') for eid,e in self.entities.items() if eid.startswith('EQP-') and e.get('name')}
        models.update(WEAPON_DIRECTORY)
        models.update(row['name'] for g in groups for row in g['rows'])
        weapons=[]
        if fleet=='voyager':
            for row in data.get('class_counts',[]):
                ship=next((s for s in self._ships(fleet).values() if s['data'].get('class_id')==row['class_id']),None)
                if not ship:continue
                for record in self.ship(fleet,ship['data']['vessel_id'])['records']:
                    if record['title']=='固定武器与防护':
                        weapons.append({**record,'title':row['name']+' · '+str(row['count'])+'艘 · 单舰固定设计'})
        elif fleet=='shadow':
            audit=data.get('armament_audit_current',{})
            for name,value in audit.get('ships',{}).items():
                weapons.append(self._record(name+' · 武备审计',root+'/armament_audit_current/ships/'+name,{'as_of':audit.get('as_of'),**value}))
        else:
            for vid,ship in self._ships(fleet).items():
                if ship['data'].get('weapons_defense'):
                    weapons.append(self._record(ship['data'].get('name',vid)+' · 武器与防护',root+'/vessels/'+vid+'/weapons_defense',ship['data']['weapons_defense']))
        return {'groups':groups,'models':sorted(models),'weapons':weapons,
                'notice':'各表按产权、位置、用途和日期分别列示，不跨表相加。总量、可用、配属、待修、领用与在仓保留各自口径。普通子弹、普通舰炮炮弹与普通舰载导弹不独立计库存；手雷、一次性火箭筒和单兵导弹按实际使用扣减。'}

    def equipment(self,query,offset=0):
        query=str(query).strip()[:150];target=normal(model_name(query));records=[]
        if query=='战机':target=normal('战斗机')
        ground=self.rules.get('runtime_rules',{}).get('combat_evaluation',{}).get('ground',{})
        for name,key in [('步枪','rifle'),('霰弹枪','shotgun'),('手枪','pistol')]:
            if name in query:
                own=ground.get('weapon_coefficients',{}).get(key)
                external=ground.get('weapon_source_factors',{}).get('external_military_firearm_nominal_w',{}).get(key)
                records.append(self._record(name+' · 武器系数与弹药口径','/runtime_rules/combat_evaluation/ground',
                    {'枪械类别':name,'自有军用武器系数W':own,'外部军用武器系数W':external,
                     '外部民用武器系数W':external*0.5 if external is not None else None,
                     '说明':'枪械使用标准无限弹药，不设子弹库存；W不是独立人员战力，实际按人员T与完好率Q套用原公式。',
                     '公式':'P = T × (0.30 + 0.70 × W × Q)'},'rules.json','现行武器参数'))
        for name,key in [('手雷','grenade'),('火箭筒','rocket'),('单兵导弹','missile')]:
            if name in query:
                value={'自有单次爆发参数':ground.get('burst_values',{}).get(key),
                       '外部顶尖单次爆发参数':ground.get('external_top_cap_burst_values',{}).get(key),
                       '外部普通单次爆发参数':ground.get('external_regular_burst_values',{}).get(key),
                       '扣减口径':'按实际消耗扣所属库存，不把全部库存默认投入战斗。'}
                rule=self._rule(GRENADE_RULE) if key=='grenade' else None
                if rule:value['现行多功能手雷模式']=rule['value'].get('parameters',{}).get('modes',[])
                records.append(self._record(name+' · 单次爆发与消耗','/runtime_rules/combat_evaluation/ground',value,'rules.json','现行武器参数'))
                if rule:records.append(rule)
        ship_base=self.catalog.get('static_catalog',{}).get('combat',{}).get('ship',{})
        for family,label in [('laser','激光炮'),('plasma','等离子炮'),('electromagnetic','电磁炮')]:
            for size,word in [('small','小口径'),('medium','中口径'),('heavy','大口径')]:
                if word+label in query.replace('舰载',''):
                    records.append(self._record(word+label+' · 基础火力','/static_catalog/combat/ship/weapon_base/'+family,
                        {'基础火力参数':ship_base.get('weapon_base',{}).get(family,{}).get(size),
                         '说明':'单件基础参数，整舰航空A还包含来源／型号、完好率、护盾与固定航空等；不直接当作整舰A。'},'catalog.json','原档基础参数'))
        for name,size in [('轻型护盾','light'),('中型护盾','medium'),('重型护盾','heavy')]:
            if name in query:
                records.append(self._record(name+' · 基础护盾值','/static_catalog/combat/ship/shields',
                    {'基础护盾值':ship_base.get('shields',{}).get(size),'具体系统型号':ship_base.get('specific_models',{}),
                     '说明':'具体型号、来源和当前完好率另行适用；不把通用基准强加给较弱的具体型号。'},'catalog.json','原档基础参数'))
        for name,key in [('激光近防炮','point_defense'),('导弹发射单元','missile_cell')]:
            if name in query:
                records.append(self._record(name+' · 基础参数','/static_catalog/combat/ship/weapon_base',
                    {'单件基础参数':ship_base.get('weapon_base',{}).get(key),'说明':'发射单元是武器硬件，普通舰载导弹弹药不另列库存；整舰航空A按既有封板。'},'catalog.json','原档基础参数'))
        for eid,entity in self.entities.items():
            if not eid.startswith('EQP-'):continue
            names=[entity.get('name',''),*entity.get('aliases',[])]
            if target and any(target in normal(n) or normal(n) in target for n in names if n):
                specs=entity.get('immutable_specs',{})
                if RANGE_RULE in self.rule_registry and any(k in specs for k in ('a_range','g_range')):
                    current={}
                    for key,label in [('a','完好名义航空A'),('g','完好名义地面G')]:
                        current[label]=max(specs[key+'_range']) if key+'_range' in specs else specs.get(key)
                    current['适用范围']='玩家拥有且100%完好的本型号；实际战损按原规则另算。保留原始区间，不取更宽泛的外部通用上限。'
                    records.append(self._record(entity.get('name',eid)+' · 玩家完好名义值','/rule_registry/rules/'+RANGE_RULE,current,'rules.json','现行区间取上限规则'))
                records.append(self._record(entity.get('name',eid),'/catalog_registry/entities/'+eid,entity,'catalog.json','型号设定；数量以当前存档为准'))
        scale=self._rule(SCALE_RULE)
        if scale:records.append(scale)
        from backend.world_archive import WorldArchive
        matches=WorldArchive(self.library).browse(str(model_name(query)),offset=offset,limit=16,category='world')
        return {'query':query,'specifications':records,'references':matches,
                'notice':'现行口径只比较航空A／地面G，整舰航空A包含已封板的固定航空战力；已经计入整舰A的固定舰载机不再次叠加。区间型号按现行规则显示玩家完好名义值，实际战损另算。旧价格和旧持有量不覆盖当前库存。'}

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
