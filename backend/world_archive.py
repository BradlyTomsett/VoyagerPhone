"""Player-facing navigation over the original save; provenance stays in RPC data."""
import json
import re
from backend.source_library import LABELS, compact

# Routing, storage and implementation metadata are not game information.
INTERNAL = re.compile(r'(^internal_logistics_current$|^internal_transfer_current$|^\$|^_|schema|(?:^|_)version$|(?:^|_)revision$|^migration$|^manifest|^authority$|^authority_mode$|^implementation_status$|^lifecycle_status$|^scope$|^domain$|^asset_type_id$|^quantity_path$|^unit_status$|^managed_by$|^source_path$|^state_path$|^codec$|sha256|^compressed_|^uncompressed_|_refs?$|_ids?$|^refs?$|^id$|^entity_type$|^source_kind$|^visibility$|^knowledge_scope$)')
MACHINE = re.compile(r'^ITEM-[a-f0-9]+$|^(?:state|rules|catalog|tasks|engine|manifest)(?:\.json)?[:.#/]|^(?:archives|development)/|^[a-f0-9]{40,64}$|^(?:ASSET|RULE|SAVESET|CLM|EVT|CMD|TSK|LOC|PER|VES|ORG|CLS|EQP|FORCE)-[A-Z0-9_-]+$')
STATUS = {'active':'生效','operational':'运行中','completed_operational':'已完工并投入使用',
 'commissioned':'已到岗','completed':'已完成','cancelled':'已取消','available':'可用',
 'active_standing_voyager_fleet_ground_mobile_force':'远航者常设地面机动力量',
 'available_for_base_defense_and_shadow_public_inventory':'可用于基地防卫及暗影公共库存',
 'gold':'金币','silver':'银币','copper':'铜币','grey':'灰币','new':'全新','unspecified':None,'active_shadow_service':'暗影现役','semantic_only':None,'current_authority':None,'general':None}
OPAQUE = re.compile(r'^[A-Za-z][A-Za-z0-9]*(?:[_.][A-Za-z0-9]+)+$')

def player_value(value, names=None):
    """A display projection only. Keep zero/False; omit null/empty and machine fields."""
    names=names or {}
    if isinstance(value,dict):
        out={}
        for key,item in value.items():
            if INTERNAL.search(key) or key in ('source_role','semantic_notes'):continue
            if key=='status' and isinstance(item,str) and OPAQUE.fullmatch(item) and item not in STATUS:
                words=item.lower().split('_')
                translated=next((v for k,v in [('cancelled','已取消'),('completed','已完成'),('active','执行中'),('available','可用'),('pending','待处理')] if k in words),None)
                if translated:out[key]=translated
                continue
            shown=player_value(item,names)
            if shown is not None:out[names.get(key,key)]=shown
        if 'rule_id' in value and not any(k not in ('title','name','status','as_of') for k in out):return None
        return out or None
    if isinstance(value,list):
        out=[v for item in value if (v:=player_value(item,names)) is not None]
        return out or None
    if isinstance(value,str):
        if not value.strip():return None
        if value in names:return names[value]
        if value in STATUS:return STATUS[value]
        if MACHINE.search(value):return None
        if re.match(r'^(?:static_catalog|catalog_registry|rule_registry|world_state_overrides|inventories|engine_runtime|runtime_rules|document_segments)[.\[/#]',value):return None
        if OPAQUE.fullmatch(value):return None
        # Embedded identifiers are replaced by names; design-table ID columns are removed.
        if '\n' in value and '|' in value:
            lines=value.splitlines();remove=[];result=[]
            for line in lines:
                if line.strip().startswith('|'):
                    cells=[c.strip() for c in line.strip().strip('|').split('|')]
                    if any(re.search(r'ID|编号',c) for c in cells):remove=[i for i,c in enumerate(cells) if re.search(r'ID|编号',c)]
                    if remove:line='| '+' | '.join(c for i,c in enumerate(cells) if i not in remove)+' |'
                else:remove=[]
                result.append(line)
            value='\n'.join(result)
        value=re.sub(r'\b(?:ASSET|RULE|SAVESET|CLM|EVT|CMD|TSK|LOC|PER|VES|ORG|CLS|EQP|FORCE)-[A-Z0-9_-]+',lambda m:names.get(m[0],''),value)
        return value
    return value

TOPICS = [
 ('bases','基地与总部','远航基地、暗影基地、基地人员、防卫与支援'),
 ('army','远航者舰队 · 远星军','所属人员编制、常设装备、调派与战损口径'),
 ('people','人物与岗位','舰队负责人、人物关系与身份记录'),
 ('xilu','熄炉与余火','店铺、员工、经营、家庭、社区及本地案件'),
 ('industry','产业与采矿','多国产业、矿业、打捞、资源储备及收入'),
 ('science','探索与科研','探索发现、科研目录、样本、医疗与隔离设施'),
 ('logistics','部署与后勤','当前驻泊、外派、航线、维修与补给'),
 ('market','市场与采购','在售资产、订购、采购与交付记录'),
 ('organizations','组织与地区','各国组织、自治地区、苇桥、基金会和夜校'),
 ('security','情报与案件','反恐、灰链、地区调查、外部势力及结案记录'),
 ('inventory','全部库存','各舰队、总部、公共仓库和实物补给分账'),
 ('tasks','任务与调拨','现行任务、任务配属与已完成任务'),
 ('continuity','故事与经营记录','最新交接、经营记录、场景、人物近况和历史摘要'),
 ('designs','世界与型号设定','完整原文、舰级、装备、世界地理及组织设定'),
 ('rules','游戏规则','原文规则、性能公式、指挥官约定与适用条件'),
 ('other','其他存档记录','其余世界状态及审计说明，保留各自记录日期')]

class WorldArchive:
    def __init__(self,library):
        self.library=library;self.state=library.documents['state'];self.names={}
        def collect(value,key=''):
            if isinstance(value,dict):
                name=value.get('canonical_name') or value.get('name')
                if isinstance(name,str):
                    if MACHINE.match(key):self.names[key]=name
                    for field in ('entity_id','vessel_id','id'):
                        if isinstance(value.get(field),str):self.names[value[field]]=name
                for k,v in value.items():collect(v,k)
            elif isinstance(value,list):
                for v in value:collect(v)
        collect(self.state);collect(library.documents['catalog'])
        self.names.update({'PER-COMMANDER-01':'指挥官','PER-NOVA-01':'诺娃','ORG-SHADOW-FLEET-01':'暗影舰队'})

    def entries(self):
        entries=[]
        def add(topic,title,path,value,source='state.json'):
            if value is not None:entries.append({'topic':topic,'title':title,'ref':source+'#'+path,'value':value,'as_of':value.get('as_of') if isinstance(value,dict) else None,'kind':'存档记录' if source=='state.json' else '原文规则与设定'})
        w=self.state.get('world_state_overrides',{})
        for k,v in w.items():
            if k=='_structure':continue
            if k=='fleet_and_logistics':
                for name,item in v.items():add('bases' if 'base' in name or 'headquarters' in name else 'logistics',LABELS.get(name,name),'/world_state_overrides/'+k+'/'+name,item)
                continue
            topic=('xilu' if 'xilu' in k else 'industry' if any(s in k for s in ('industry','mining','jinchuan_ethide')) else 'science' if 'exploration' in k or 'waughn' in k else 'market' if 'market' in k else 'organizations' if any(s in k for s in ('organizations','politics','nation','weibridge','autonomous')) else 'security' if any(s in k for s in ('security','intelligence','greychain','ash_network','counterterror','case','mirrorcoffin')) else 'continuity' if any(s in k for s in ('handoff','continuity','continuation','snapshot')) else 'logistics' if 'maintenance' in k or 'shadow_deployment' in k or 'shadow_group' in k else 'tasks' if 'task_termination' in k else 'rules' if 'directives' in k else 'other')
            add(topic,LABELS.get(k,k),'/world_state_overrides/'+k,v)
        for k,v in self.state.get('voyager_fleet',{}).items():
            if k=='farstar_army_current':add('army','远星军','/voyager_fleet/'+k,v)
            elif 'isolation' in k:add('science',k,'/voyager_fleet/'+k,v)
        shadow=self.state.get('shadow_fleet',{})
        for k in ('shadow_base_personnel_current','personnel_structure_current'):
            add('bases',k,'/shadow_fleet/'+k,shadow.get(k))
        for k in ('key_personnel_current_roles','external_force_registry','inventories','task_allocations','commander_runtime_rules','audits','entity_lifecycle'):
            topic={'key_personnel_current_roles':'people','external_force_registry':'security','inventories':'inventory','task_allocations':'tasks','commander_runtime_rules':'rules'}.get(k,'other')
            for name,v in self.state.get(k,{}).items():add(topic,self.names.get(name,LABELS.get(name,name)),'/'+k+'/'+name,v)
        # Gameplay records hidden among runtime registries need their own reader.
        for k,v in self.state.get('engine_runtime',{}).items():
            if any(s in k for s in ('business_runtime','story_turns','story_runtime','living_world','memory_layers','knowledge_layer','random_events','combat_runtime','maintenance_runtime','catchup','continuation','recovery_replay')):
                add('continuity',k,'/engine_runtime/'+k,v)
        for name in ('catalog','rules'):
            d=self.library.documents[name]
            add('designs' if name=='catalog' else 'rules','完整原文设定' if name=='catalog' else '完整原文规则','/document_segments',d.get('document_segments'),name+'.json')
            add('designs' if name=='catalog' else 'rules','型号与世界设定' if name=='catalog' else '现行规则参数','/static_catalog' if name=='catalog' else '/runtime_rules',d.get('static_catalog' if name=='catalog' else 'runtime_rules'),name+'.json')
            add('designs' if name=='catalog' else 'rules','舰级与装备型号' if name=='catalog' else '规则补充与最新更正','/catalog_registry/entities' if name=='catalog' else '/rule_registry/rules',d.get('catalog_registry' if name=='catalog' else 'rule_registry',{}).get('entities' if name=='catalog' else 'rules'),name+'.json')
        for k,v in self.library.documents['tasks'].items():add('tasks',k,'/'+k,v,'tasks.json')
        return entries

    def topics(self):
        entries=self.entries()
        return [{'id':key,'title':title,'description':description,'records':sum(e['topic']==key for e in entries)} for key,title,description in TOPICS]

    def topic(self,topic):
        spec=next((t for t in TOPICS if t[0]==topic),None)
        if not spec:raise ValueError('TOPIC_NOT_FOUND')
        highlights=[]
        w=self.state.get('world_state_overrides',{}).get('fleet_and_logistics',{})
        if topic=='army':
            army=self.state.get('voyager_fleet',{}).get('farstar_army_current',{})
            highlights=[{'title':'远星军','parent':'远航者舰队直属地面部队','personnel_subject':'farstar','as_of':army.get('as_of'),'metrics':{'人员（人）':army.get('personnel'),**army.get('standard_personal_equipment',{}),**army.get('organic_assets',{})},'note':army.get('personnel_accounting')}]
        elif topic=='bases':
            for key,title,fields in [('voyager_base_current','远航基地',['berths','full_service_repair_bays','normal_population_capacity','emergency_capacity','high_security_detention_capacity','medical_bays']),('shadow_base_current','暗影基地',['staff_recruitment','armored_vehicle_pool','combat_robot_pool'])]:
                base=w.get(key,{})
                metrics={k:base[k] for k in fields if k in base and not isinstance(base[k],dict)}
                if key=='shadow_base_current':
                    staff=base.get('staff_recruitment',{})
                    metrics={'招募工作人员（人）':staff.get('staff'),'招募武装警卫（人）':staff.get('armed_guards'),'招募合计（人）':staff.get('total'), '边盾-6（辆）':base.get('armored_vehicle_pool',{}).get('边盾-6')}
                highlights.append({'title':title,'as_of':base.get('as_of'),'metrics':metrics,'note':base.get('idle_homeport_rule') or base.get('note')})
        return {'title':spec[1],'parent_fleet':'voyager' if topic=='army' else None,'highlights':highlights,'records':[self.display_record(r) for r in self.entries() if r['topic']==topic and player_value(r['value'],self.names) is not None],
                'notice':'按原档日期分别列出。旧快照、历史案件和已取消事项保留原状态；不以旧值覆盖最新存档。'}

    def force(self,fleet,unit):
        if fleet=='voyager' and unit=='army':return self.topic('army')
        if fleet!='shadow' or unit!='qrf':raise ValueError('FORCE_NOT_FOUND')
        qrf=self.state.get('shadow_fleet',{}).get('quick_reaction_force_current',{})
        metrics={'人员（人）':qrf.get('personnel')}
        metrics.update(qrf.get('robots',{}));metrics.update(qrf.get('uavs',{}))
        return {'title':'暗影舰队 · 快反部队','parent_fleet':'shadow',
                'highlights':[{'title':'快反部队','parent':'暗影舰队所属地面机动力量','personnel_subject':'shadow_qrf',
                    'as_of':qrf.get('as_of'),'metrics':metrics,
                    'note':'快反人员包含在暗影舰队总人数内；霍克五人和暗反1组属于快反编制，按当前分组记录查看，不重复加总。'}],
                'records':[self.display_record({'title':'快反部队现状','value':qrf,'ref':'state.json#/shadow_fleet/quick_reaction_force_current','as_of':qrf.get('as_of'),'kind':'当前存档记录'})],
                'notice':'快反部队隶属暗影舰队。编制总数、分组、外派人员和所属装备分别列示；同一人员与资产不重复计数。'}

    def personnel(self,subject):
        params=self.state.get('commander_runtime_rules',{}).get('parameters',{})
        if subject=='farstar':
            force=self.state.get('voyager_fleet',{}).get('farstar_army_current',{})
            rule=params.get('farstar_voyager_personnel_T_100_v1439',{})
            title='远星军';parent='远航者舰队';t=rule.get('base_personal_T')
            scope=rule.get('scope');as_of=rule.get('issued_game_time')
            source='/commander_runtime_rules/parameters/farstar_voyager_personnel_T_100_v1439'
            note=force.get('personnel_accounting');exception=rule.get('exclude')
        elif subject=='shadow_qrf':
            force=self.state.get('shadow_fleet',{}).get('quick_reaction_force_current',{})
            title='快反部队';parent='暗影舰队'
            t=force.get('training',{}).get('external_armed_personal_combat_power')
            scope='暗影快反编制；霍克、Q2、Q3、Q4、Q5继续按各自现行封板T=70。'
            as_of=force.get('as_of');source='/shadow_fleet/quick_reaction_force_current/training'
            note='人数已包含在暗影舰队总人数内；当前小组、舰上分队与本地潜伏人员按配属记录查看。'
            exception='远航者与远星军的T=100封板不覆盖暗影快反编制。'
        else:raise ValueError('PERSONNEL_NOT_FOUND')
        if not isinstance(t,(int,float)) or isinstance(t,bool):t=None
        book=self.state.get('engine_runtime',{}).get('internal_logistics_v1',{})
        cohorts=book.get('people',{}).get('farstar' if subject=='farstar' else 'qrf')
        if cohorts is not None:
            values={r.get('T') for r in cohorts if r['quantity']}
            t=next(iter(values)) if len(values)==1 else None
        value={'所属舰队':parent,'编制':title,'人数（人）':force.get('personnel'),
               '基础人员战斗力T（每人）':t,'适用人群':scope,'T值记录日期':as_of,
               '编制人数记录日期':force.get('as_of'),'人员计数口径':note,'适用边界':exception}
        if t is None:value['T值说明']='当前记录未给出该编制统一的人员T值。'
        if cohorts is not None:
            value['调动后人员T分组']=[{'人数':r['quantity'],'每人T':r.get('T'),'口径':r.get('basis')} for r in cohorts if r['quantity']]
            value['T值说明']='调入人员保留原T记录；不同T分别列示，未记录的保持未知。'
        record={'title':'人员与现行T值','value':value,'ref':'state.json#'+source,'as_of':as_of,'kind':'现行人员口径'}
        return {'title':title+' · 人员与战斗力T','parent':parent,'personnel':force.get('personnel'),'T':t,
                'as_of':as_of,'records':[record],
                'notice':'T表示每名人员的基础战斗力；有效人员战力另按实际主武器、装备完好率和动力甲计算。人数保持原存档口径。'}

    def display_record(self,record):
        return {**record,'value':player_value(record['value'],self.names)}

    def browse(self,query='',offset=0,limit=16,history=False,category='all'):
        # Search all source rows before paging, so metadata-only rows never create blank pages.
        if history and query:self.library._load_archives(query)
        originals=self.library.rows;history_rows=self.library.history_rows
        def prepare(rows):
            joined={};out=[]
            for row in rows:joined.setdefault(row['ref'].split('@')[0],[]).append(row)
            for parts in joined.values():
                row=parts[0]
                if re.search(r'/asset_ledger|/entity_registry|/asset_mapping|/asset_semantic|/.*_contract(?:/|$)|/state_refs|/\$storage',row['path']):continue
                if row['path'].startswith('/engine_runtime/') and not any(s in row['path'] for s in ('business_runtime','story_turns','story_runtime','living_world','memory_layers','knowledge_layer','random_events','combat_runtime','maintenance_runtime','catchup','continuation','recovery_replay')):continue
                if '/migration/' in row['path']:continue
                text=''.join(p['text'] for p in sorted(parts,key=lambda p:p['part']))
                try:value=json.loads(text)
                except ValueError:value=text
                value=player_value(value,self.names)
                if value is None:continue
                item={**row,'value':value,'text':compact(value),'parts':1,'part':1}
                item['_search']=(row['label']+' '+compact(value)+' '+row['path']).casefold()
                out.append(item)
            return out
        if not hasattr(self,'_prepared'):self._prepared=prepare(originals)
        try:
            self.library.rows=self._prepared;self.library.history_rows=prepare(history_rows) if history and query else []
            result=self.library.search(query,offset,limit,False,category) if not history else self._search_with_history(query,offset,limit,category)
            result['history_included']=history
            return result
        finally:self.library.rows=originals;self.library.history_rows=history_rows

    def _search_with_history(self,query,offset,limit,category):
        # Already decoded/filtered; avoid a second archive decode in search().
        rows=self.library.rows;self.library.rows=rows+self.library.history_rows
        try:return self.library.search(query,offset,limit,False,category)
        finally:self.library.rows=rows
