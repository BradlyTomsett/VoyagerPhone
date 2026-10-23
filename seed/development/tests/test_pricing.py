#!/usr/bin/env python3
"""Meaningful pricing acceptance tests. All mutations use disposable save copies."""
import sys
sys.dont_write_bytecode=True
import pathlib,importlib.util,tempfile,shutil,json,os,copy,hashlib,sys,traceback
BASE=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else pathlib.Path(__file__).resolve().parents[2]).resolve()
os.environ['VOYAGER_ROOT']=str(BASE);os.environ['VOYAGER_DEVELOPER_MODE']='1';os.environ['VOYAGER_DIAGNOSTIC_CONTEXT']='gm';os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None)
spec=importlib.util.spec_from_file_location('pricing_acceptance_engine',BASE/'engine.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
results=[]
def case(name,fn):
 try:
  detail=fn();results.append({'name':name,'status':'PASS','detail':detail})
 except Exception as ex:
  results.append({'name':name,'status':'FAIL','detail':str(ex),'trace':traceback.format_exc()});print('FAIL',name,str(ex),flush=True)
def assert_eq(x,y):
 assert x==y,(x,y)
 return x
def expect_error(fn,token=None):
 try:fn()
 except Exception as ex:
  if token:assert token in str(ex),(token,str(ex))
  return str(ex)
 raise AssertionError('expected rejection')
def quote(item='XILU-ORDINARY_ROOM_NIGHT',**kwargs):
 req={'item_id':item,'unit':'晚' if item.startswith('XILU') else '份','quantity':1,'currency':'gold','region':'熄炉-9','transaction_type':'service'};req.update(kwargs);return m.calculate_price_quote(req,BASE)
def reject(item='XILU-ORDINARY_ROOM_NIGHT',**kwargs):return assert_eq(quote(item,**kwargs)['status'],'OUT_OF_POLICY')
def core_hash(root):return {fn:hashlib.sha256((root/fn).read_bytes()).hexdigest() for fn in m.COMPONENT_FILES}
def write(root,name,obj):m._write_authority_json(root/name,obj)
def rebind(root):return m._component_write_manifest_native(root,'V14.21',m.read_json(root/'manifest.json').get('parent_save_set_id'))
def request(**kwargs):
 x={'item_id':'XILU-ORDINARY_ROOM_NIGHT','region':'熄炉-9','quantity':7,'unit':'晚','currency':'gold','transaction_type':'service'};x.update(kwargs);return x
class Save:
 def __enter__(self):
  self.temp=tempfile.TemporaryDirectory(prefix='voyager_pricing_test_');self.root=pathlib.Path(self.temp.name)
  for fn in m.COMPONENT_FILES:shutil.copy2(BASE/fn,self.root/fn)
  shutil.copytree(BASE/'archives',self.root/'archives');self.oldroot=m.ROOT;m.ROOT=self.root;return self.root
 def __exit__(self,*args):m.ROOT=self.oldroot;self.temp.cleanup()
def grant(root,kind,targets,limit=10000,quantity=100,actor='TEST-ACTOR'):
 state=m.read_json(root/'state.json');state['standing_authorizations']['TEST-GRANT']={'status':'active','machine_grant':{'schema':'DOMAIN_MACHINE_GRANT_V1','grant_id':'TEST-GRANT','subject_id':actor,'action_kinds':[kind],'targets':targets,'valid_from':state['game_time'],'valid_until':'8364-09-18T12:28:00','max_uses':4,'max_gold_units':limit,'max_grey_units':10000,'max_quantity':quantity}};write(root,'state.json',state);rebind(root)
def append(root,event):
 e={'event_id':'TEST-EVENT','game_time':m.read_json(root/'state.json')['game_time'],'type':'system','source':'pricing acceptance fixture','summary':'disposable acceptance evidence','changes':[]};e.update(event);m._append_engine_history(root/'events.jsonl',e);rebind(root)
def command(root,kind,**fields):
 return {'schema':m.DOMAIN_COMMAND_SCHEMA,'kind':kind,'command_id':'TEST-COMMAND','base_save_set_id':m.read_json(root/'manifest.json')['save_set_id'],'authorization':'standing_authorization','authorization_ref':'TEST-GRANT','actor_id':'TEST-ACTOR',**fields}
def settlement_fixture(root,account='fleet',direction='debit',req=None,limit=10000):
 req=req or request();q=m.calculate_price_quote(req,root);assert_eq(q['status'],'VALID');sid='TEST-SETTLEMENT';target='state:summary.funds.'+q['total']['currency'] if account=='fleet' else 'state:'+m.PRICE_SILVER_ACCOUNT+'.cash_silver'
 grant(root,'settle_price',[target,'state:engine_runtime.pricing_runtime.settlements.'+sid],limit=limit)
 append(root,{'confirmed_price_settlement':{'settlement_id':sid,'quote_id':q['quote_id'],'binding_sha256':q['binding_sha256'],'direction':direction,'account':account,'status':'completed','cash_amount':q['total'],'asset_disposition_verified':True}})
 q=m.calculate_price_quote(req,root);return command(root,'settle_price',settlement_id=sid,quote=q,account=account,direction=direction,source_event_id='TEST-EVENT')
case('C08 alias path resolves current 45',lambda:assert_eq(m.price_query_packet(BASE,{'source_ref':'state:world_state_overrides.exploration_and_science.beastring11_sample_research_current.sale_status'})['prices'][0]['range'],['45','45']))
case('B16 standard ammunition not recharged',lambda:reject('OWN-RIFLE',unit='支',modifiers=[{'kind':'standard_ammunition','multiplier':'1.1'}]))
case('A17 fixed finance does not round through float',lambda:assert_eq(m._money_units_currency('10000000000000.0001','gold'),100000000000000001))
case('A18 large exact conversion keeps final copper',lambda:assert_eq(m.convert_money_exact('10000000000000.0001','gold','gold',BASE),'10000000000000.0001'))
case('A01 20 copper exact gold',lambda:assert_eq(m.convert_money_exact(20,'copper','gold',BASE),'0.002'))
case('A02 20 copper exact silver',lambda:assert_eq(m.convert_money_exact(20,'copper','silver',BASE),'0.2'))
case('A03 seven nights 140 copper',lambda:assert_eq(quote(quantity=7,currency='copper')['total'],{'amount':'140','currency':'copper'}))
case('A04 seven nights 1.4 silver',lambda:assert_eq(quote(quantity=7,currency='silver')['total']['amount'],'1.4'))
case('A05 seven nights .014 gold',lambda:assert_eq(quote(quantity=7)['total']['amount'],'0.014'))
case('A06 wrong 20 gold refused',lambda:reject(quoted_unit_price={'amount':20,'currency':'gold'}))
case('A07 tonne cannot be crate',lambda:reject('TITANIUM-CONCENTRATE46',unit='箱',region=None))
case('A08 missing currency refused',lambda:reject(currency=None))
case('A09 bare numeric amount refused',lambda:reject(quoted_unit_price=20))
case('A10 NaN refused',lambda:reject(quantity='NaN'))
case('A11 indivisible item fractional refused',lambda:reject('DATA-BEASTRING11-PUBLIC',quantity='.5',unit='份'))
case('A12 rounded nonzero is not free',lambda:reject(currency='grey',quantity='.001'))
case('A13 exact grey source avoids inverse approximation',lambda:assert_eq(m.convert_money_exact('27.78','grey','gold',BASE,False),'1.00008'))
case('A15 metric mass normalized exactly',lambda:assert_eq(quote('TITANIUM-CONCENTRATE46',unit='kg',quantity=1000)['total']['amount'],'0.0189'))
case('A16 converted ask unit cannot be ambiguous',lambda:reject('TITANIUM-CONCENTRATE46',unit='kg',quantity=1000,quoted_unit_price={'amount':188.7,'currency':'copper'}))
case('A14 display change cannot alter amount',lambda:assert_eq(quote(quantity=7)['total']['amount'],'0.014'))
case('B01 sand dune fixed 100',lambda:assert_eq(quote('OWN-SANDDUNE',unit='台')['total']['amount'],'100'))
case('B02 sand dune 105 refused',lambda:reject('OWN-SANDDUNE',unit='台',quoted_unit_price={'amount':105,'currency':'gold'}))
case('B03 star chart 51 grey refused',lambda:reject('STAR-CHART',unit='份',currency='grey',channel='grey',quoted_unit_price={'amount':51,'currency':'grey'}))
case('B04 star chart 2 gold equivalent refused',lambda:reject('STAR-CHART',unit='份',channel='legal',quoted_unit_price={'amount':2,'currency':'gold'}))
case('B05 star chart 30 lacks exception',lambda:reject('STAR-CHART',unit='份',currency='grey',channel='grey',quoted_unit_price={'amount':30,'currency':'grey'}))
case('B06 legal chart grey currency refused',lambda:reject('STAR-CHART',unit='份',currency='grey',channel='legal',quoted_unit_price={'amount':20,'currency':'grey'}))
case('B07 supply +20 percent valid',lambda:assert_eq(quote('SUPPLY-FOOD',unit='包',modifiers=[{'kind':'supply_demand','multiplier':'1.2'}])['total']['amount'],'0.024'))
case('B08 supply +21 percent needs evidence',lambda:reject('SUPPLY-FOOD',unit='包',modifiers=[{'kind':'supply_demand','multiplier':'1.21'}]))
case('B09 supply modifier not world-wide',lambda:reject(modifiers=[{'kind':'supply_demand','multiplier':'1.2'}]))
case('B10 ship length not charged twice',lambda:reject('CARGO-500',unit='艘',quoted_unit_price={'amount':40000,'currency':'gold'},modifiers=[{'kind':'length','multiplier':'1.5'}]))
case('B11 native armament not charged twice',lambda:reject('OWN-HUMMINGBIRD',unit='架',modifiers=[{'kind':'armament','multiplier':'1.2'}]))
case('B12 owned reference no used discount',lambda:reject('OWN-RIFLE',unit='支',modifiers=[{'kind':'external_used','multiplier':'.3'}]))
case('B13 combat strength not price ratio',lambda:reject('OWN-RIFLE',unit='支',modifiers=[{'kind':'combat_ratio','multiplier':'.7'}]))
case('B14 external used separate rule',lambda:assert_eq(quote('EXT-RIFLE',unit='支',specification={'condition':'used'},modifiers=[{'kind':'external_used','multiplier':'.4'}])['total']['amount'],'0.3'))
case('B15 duplicate supply multiplier refused',lambda:reject('SUPPLY-FOOD',unit='包',modifiers=[{'kind':'supply_demand','multiplier':'1.1'}]*2))
def research_all():
 rows=m._price_records(m._pricing_documents(BASE));items=[r['item_id'] for r in rows.values() if r['category']=='research'];assert_eq(len(items),87)
 for item in items:assert_eq(quote(item,unit='份')['total']['amount'],'45')
 return len(items)
case('C01 all 87 packages use current 45 policy',research_all)
def withdrawn():
 docs=m._pricing_documents(BASE);docs['state']['world_state_overrides']['markets_and_procurement']['research_data_sales_program']['packages']['DATA-BEASTRING11-PUBLIC']['status']='withdrawn';return assert_eq(m.calculate_price_quote(request(item_id='DATA-BEASTRING11-PUBLIC',unit='份',quantity=1),documents=docs)['status'],'NEEDS_EVIDENCE')
case('C07 withdrawn package not an active offer',withdrawn)
case('C02 research 4500 refused',lambda:reject('DATA-BEASTRING11-PUBLIC',unit='份',quoted_unit_price={'amount':4500,'currency':'gold'}))
def research_policy_gate():
 state=m.read_json(BASE/'state.json');p=m.get_by_path(state,m.PRICE_RESEARCH_PATH);p['packages']['DATA-BEASTRING11-PUBLIC']['price_gold_per_copy']=4500
 return expect_error(lambda:m._catalog_sales_inputs({'catalog_source':'state:'+m.PRICE_RESEARCH_PATH+'.packages'},state,m.parse_iso(state['game_time'])),'PRICE_RESEARCH_POLICY_CONFLICT')
case('C03 business sales input policy gate',research_policy_gate)
def aliases():
 docs=m._pricing_documents(BASE)
 for a in m._pricing_runtime(docs['state'])['aliases']:
  obj=m._pricing_source_value(docs,a['path']);assert a['legacy_field'] not in obj;assert_eq(obj['legacy_price_record']['value'],25);assert_eq(m._price_anchor_value(m._price_records(docs)[a['price_id']],docs),(m.Decimal(45),m.Decimal(45)))
 return len(m._pricing_runtime(docs['state'])['aliases'])
case('C04 all three old 25 current displays reference 45',aliases)
def readonly():
 before=core_hash(BASE);a=m.price_quote_packet(BASE,request());b=m.price_quote_packet(BASE,request());assert_eq(a,b);m.price_query_packet(BASE,{'region':'熄炉-9'});assert_eq(core_hash(BASE),before);return a['quote_id']
case('D01 readonly stable repeat no RNG or component write',readonly)
case('D02 unknown has no invented precise price',lambda:assert_eq(quote('UNKNOWN',unit='件')['status'],'NEEDS_EVIDENCE'))
case('D03 range has no invented midpoint',lambda:assert_eq(quote('XILU-CHEAP_HOT_MEAL',unit='份')['status'],'PROVISIONAL'))
case('D04 narrative inflation not accepted',lambda:reject(quoted_unit_price={'amount':200,'currency':'copper'}))
case('D05 caller verified claim refused',lambda:reject(verified=True))
case('D06 range valid specified price',lambda:assert_eq(quote('XILU-CHEAP_HOT_MEAL',unit='份',quoted_unit_price={'amount':7,'currency':'copper'})['total']['amount'],'0.0007'))
def fake_quote():
 q=quote(quantity=7);q['total']['amount']='20';return expect_error(lambda:m.validate_price_quote(q,BASE),'PRICE_STALE_OR_TAMPERED')
case('E17 public renderer rejects status-only forgery',lambda:expect_error(lambda:m.render_price_quote({'status':'VALID','unit_price':{'amount':'4500','currency':'gold'},'total':{'amount':'4500','currency':'gold'},'unit':'份','quantity':'1'},BASE)))
case('E01 invalid quote rejected',fake_quote)
case('E02 business market missing context rejected',lambda:expect_error(lambda:m.market_offer_packet({'ask_price':20,'offer_price':10,'floor_price':9},BASE),'PRICE_VALID_QUOTE_REQUIRED'))
case('E03 mathematical negotiation kept',lambda:assert_eq(m.market_offer_packet({'ask_price':20,'offer_price':20,'floor_price':15})['result'],'ACCEPT'))
def debit_and_retry():
 with Save() as root:
  p=settlement_fixture(root);before=m.read_json(root/'state.json')['engine_runtime']['finance_runtime']['funds_units']['gold'];preview=m.domain_command_packet(root,p,None,'test preview',True);assert_eq(preview['status'],'DRY_RUN');assert_eq(m.read_json(root/'state.json')['engine_runtime']['finance_runtime']['funds_units']['gold'],before)
  result=m.domain_command_packet(root,p,'V14.22','pricing acceptance debit',False);assert_eq(result['status'],'SAVED');after=m.read_json(root/'state.json')['engine_runtime']['finance_runtime']['funds_units']['gold'];assert_eq(after,before-140)
  retry=m.domain_command_packet(root,p,'V14.23','retry',False);assert_eq(retry['status'],'ALREADY_APPLIED');assert_eq(m.read_json(root/'state.json')['engine_runtime']['finance_runtime']['funds_units']['gold'],after);assert_eq(m.run_checks(root,full=True)['status'],'PASS')
  return {'debit_units':140,'retry':retry['status']}
case('E04 real preview commit and idempotent retry',debit_and_retry)
def denied(kind):
 with Save() as root:
  req=request(transaction_type='estimate') if kind=='estimate' else None;p=settlement_fixture(root,req=req,limit=139 if kind=='budget' else 10000);before=core_hash(root)
  if kind=='commander':p['authorization']='commander'
  if kind=='actor':p['actor_id']='OTHER'
  if kind=='tamper':p['quote']['total']['amount']='1'
  if kind=='unconfirmed':p['source_event_id']='MISSING'
  if kind=='direction':p['direction']='credit'
  err=expect_error(lambda:m.domain_command_packet(root,p,'V14.22','reject test',False));assert_eq(core_hash(root),before);return err
for kind in ['commander','actor','budget','estimate','tamper','unconfirmed','direction']:case('E05 denied '+kind,lambda kind=kind:denied(kind))
def silver_debit():
 with Save() as root:
  p=settlement_fixture(root,account='xilu9_shop',req=request(currency='silver'));state=m.read_json(root/'state.json');before=copy.deepcopy(state['engine_runtime']['finance_runtime']);m.domain_command_packet(root,p,'V14.22','independent silver acceptance',False);state=m.read_json(root/'state.json');assert_eq(state['engine_runtime']['finance_runtime'],before);acct=m.get_by_path(state,m.PRICE_SILVER_ACCOUNT);assert_eq(str(acct['cash_silver']),'84.58');assert_eq(str(acct['free_operating_cash_silver']),'79.38');return acct['cash_silver']
case('E06 independent silver stays separate',silver_debit)
def scene_test():
 with Save() as root:
  sid='TEST-SCENE';grant(root,'scene_record',['state:engine_runtime.scene_registry_v1.records.'+sid]);q=m.calculate_price_quote(request(),root);tasks=m.read_json(root/'tasks.json');tid=next(t['task_id'] for t in tasks['active_tasks'] if t['task_id']!=m._PATROL_TASK_ID)
  p=command(root,'scene_record',scene_id=sid,scene_action='create',task_id=tid,scene_type='test',title='test scene',participants=[],facts=[{'fact_id':'ROOM','value':'placeholder','epistemic':'confirmed'}],economic_fact_refs={'ROOM':q})
  result=m.domain_command_packet(root,p,'V14.22','scene pricing acceptance');assert_eq(result['status'],'SAVED');rec=m.read_json(root/'state.json')['engine_runtime']['scene_registry_v1']['records'][sid];assert_eq(rec['facts']['ROOM']['value'],m._pricing_render_template(q));player=m.scene_query_packet(root,sid);assert_eq(player['value']['confirmed_facts'],[]);assert_eq(player['value'].get('economic_fact_refs'),{});return rec['economic_fact_refs']['ROOM']['quote_id']
case('E07 structured scene template and hidden quote',scene_test)
case('E08 unstructured scene money refused',lambda:expect_error(lambda:m._pricing_scene_refs(BASE,{'facts':[{'fact_id':'ROOM','value':'20金币房费','epistemic':'confirmed'}]}),'STRUCTURED_QUOTE'))
def stage_patch(path,value,effects=None,reg=None):
 with Save() as root:
  stage=pathlib.Path(m.create_stage(root,'session_pricing_test')['staging']);m._copy_declared_cold_archives(root,stage,m.read_json(root/'manifest.json'))
  patch={'format':m.PATCH_FORMAT,'operations':[{'op':'set','file':'state.json','path':path,'value':value,'allow_create':True}]}
  if effects:patch['economic_effects']=effects
  if reg:patch['price_registrations']=reg
  pf=root/'test_patch.json';pf.write_text(json.dumps(patch));before=core_hash(stage)
  err=expect_error(lambda:m.apply_patch(stage,pf));assert_eq(core_hash(stage),before);return err
case('E09 session protects cash and rolls back',lambda:stage_patch('/summary/funds/gold',999))
case('E10 session new unquoted price refused and rolls back',lambda:stage_patch('/world_state_overrides/new_test_price_gold',9000))
case('E11 session blocks price authority direct edit',lambda:stage_patch('/commander_runtime_rules/parameters/research_data_uniform_price_gold',4500))
def changed_check():
 with Save() as root:
  parent=root/'parent';parent.mkdir()
  for fn in m.COMPONENT_FILES:shutil.copy2(root/fn,parent/fn)
  shutil.copytree(root/'archives',parent/'archives');state=m.read_json(root/'state.json');state['world_state_overrides']['unquoted_price_gold']=9000;write(root,'state.json',state);report=m.pricing_transaction_report(root,parent);assert_eq(report['status'],'FAIL');return report['errors']
case('E12 final transaction catches unquoted price',changed_check)
def stale():
 q=quote(quantity=7);q['save_set_id']='OLD';return assert_eq(m.price_quote_packet(BASE,{'revalidate':q})['status'],'STALE')
case('D07 stale SAVESET quote explicitly stale',stale)
def scoped_evidence():
 docs=m._pricing_documents(BASE);row=m.resolve_price_authority({'item_id':'SUPPLY-FOOD','unit':'包','quantity':1,'currency':'gold'},documents=docs);ref='state:game_time';ev={'evidence_id':'WAR','purpose':'modifier','factor_id':'WAR-FOOD','status':'active','category':'supply','item_id':'SUPPLY-FOOD','scope':{'region':'TEST-WAR-ZONE'},'source_ref':ref,'source_sha256':m._price_digest(m._pricing_source_value(docs,ref)),'multiplier':'2','rule_id':'RULE-SUPPLY-INVENTORY-01','explanation':'disposable war evidence fixture'};ev.pop('category');m._pricing_runtime(docs['state'])['evidence']['WAR']=ev
 req={'item_id':'SUPPLY-FOOD','unit':'包','quantity':1,'currency':'gold','region':'TEST-WAR-ZONE','modifiers':[{'kind':'war','multiplier':2,'evidence_id':'WAR'}]};assert_eq(m.calculate_price_quote(req,documents=docs)['total']['amount'],'0.04')
 req['item_id']='SUPPLY-WATER';assert_eq(m.calculate_price_quote(req,documents=docs)['status'],'OUT_OF_POLICY');req['item_id']='SUPPLY-FOOD';req['region']='OTHER';assert_eq(m.calculate_price_quote(req,documents=docs)['status'],'OUT_OF_POLICY');req['region']='TEST-WAR-ZONE';req['modifiers'].append({'kind':'transport','multiplier':2,'evidence_id':'WAR'});assert_eq(m.calculate_price_quote(req,documents=docs)['status'],'OUT_OF_POLICY');return 'scoped, no cross-item, no double event'
case('D08 scoped exception and duplicate event blocked',scoped_evidence)
def loader_parity():
 spec=importlib.util.spec_from_file_location('dev_runtime_pricing',BASE/'development/devsrc/runtime.py');rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt);api,modules=rt.load(BASE/'engine.py');assert_eq(api.price_quote_packet(BASE,request()),m.price_quote_packet(BASE,request()));assert_eq(api.domain_command_catalog(BASE)['kinds'],m.domain_command_catalog(BASE)['kinds']);return len(modules)
case('F01 development loader release parity',loader_parity)
case('F02 current full check',lambda:assert_eq(m.run_checks(BASE,full=True)['status'],'PASS'))
case('F03 reference integrity',lambda:assert_eq(m.reference_integrity_packet(BASE)['status'],'PASS'))
case('F04 cold startup stays <=3500 bytes',lambda:assert_eq(m.cold_start_packet(BASE)['context_bytes']<=3500,True))
case('F05 changed random clock cannot inherit warning',lambda:assert_eq(m._pricing_preserved_gap(dict(m.read_json(BASE/'state.json'),game_time='8363-09-18T12:29:00')),False))
def policy_update_test():
 with Save() as root:
  quote_before=m.calculate_price_quote(request(item_id='DATA-BEASTRING11-PUBLIC',unit='份',quantity=1,transaction_type='sale'),root)
  ref='state:commander_runtime_rules.parameters.research_data_uniform_price_gold';grant(root,'price_policy_update',[ref,'state:'+m.PRICE_RESEARCH_PATH+'.packages'])
  append(root,{'confirmed_price_policy':{'policy_ref':ref,'old_amount':'45','new_amount':'50','currency':'gold','authorization_ref':'TEST-GRANT'}})
  before=m.read_json(root/'state.json');q=m.calculate_price_quote(request(item_id='DATA-BEASTRING11-PUBLIC',unit='份',quantity=1,transaction_type='sale'),root)
  p=command(root,'price_policy_update',policy_ref=ref,unit_price={'amount':'50','currency':'gold'},source_event_id='TEST-EVENT');out=m.domain_command_packet(root,p,'V14.22','authorized future price policy test');assert_eq(out['status'],'SAVED')
  after=m.read_json(root/'state.json');assert_eq(before['engine_runtime']['finance_runtime'],after['engine_runtime']['finance_runtime']);program=m.get_by_path(after,m.PRICE_RESEARCH_PATH)
  for row in program['packages'].values():
   if row.get('status') in ['on_sale','active_nonexclusive_digital_backup']:assert_eq(row['price_gold_per_copy'],50.0)
  assert_eq(m.calculate_price_quote(request(item_id='DATA-BEASTRING11-PUBLIC',unit='份',quantity=1),root)['total']['amount'],'50')
  for key in ['sales_cumulative','copies_sold_cumulative','gold_booked_cumulative']:assert_eq(m.get_by_path(before,m.PRICE_RESEARCH_PATH).get(key),program.get(key))
  assert_eq(m.price_quote_packet(root,{'revalidate':q})['status'],'STALE');return 'authorized current catalog 50, history and cash unchanged'
case('C05 authorized future policy works without hardcoded 45',policy_update_test)
def unauthorized_policy():
 with Save() as root:
  grant(root,'price_policy_update',['state:commander_runtime_rules.parameters.research_data_uniform_price_gold','state:'+m.PRICE_RESEARCH_PATH+'.packages']);p=command(root,'price_policy_update',policy_ref='state:commander_runtime_rules.parameters.research_data_uniform_price_gold',unit_price={'amount':4500,'currency':'gold'},source_event_id='MISSING');before=core_hash(root);expect_error(lambda:m.domain_command_packet(root,p,'V14.22','unauthorized policy test'));assert_eq(core_hash(root),before);return 'rejected and unchanged'
case('C06 policy mutation needs confirmed scoped authority',unauthorized_policy)
def evidence_registration():
 with Save() as root:
  eid='TEST-WAR';target='state:engine_runtime.pricing_runtime.evidence.'+eid;grant(root,'price_evidence_register',[target]);docs=m._pricing_documents(root)
  ev={'evidence_id':eid,'purpose':'modifier','factor_id':'WAR-FOOD-SHORTAGE','status':'active','item_id':'SUPPLY-FOOD','category':'supply','scope':{'region':'TEST-WAR-ZONE'},'source_ref':'state:game_time','source_sha256':m._price_digest(docs['state']['game_time']),'multiplier':'2','rule_id':'RULE-SUPPLY-INVENTORY-01','explanation':'disposable war-supply fixture; no actual player event'}
  append(root,{'confirmed_price_evidence':ev});p=command(root,'price_evidence_register',evidence_id=eid,evidence=ev,source_event_id='TEST-EVENT');m.domain_command_packet(root,p,'V14.22','register scoped price evidence test')
  req=request(item_id='SUPPLY-FOOD',unit='包',quantity=1,region='TEST-WAR-ZONE',modifiers=[{'kind':'war','multiplier':2,'evidence_id':eid}]);assert_eq(m.calculate_price_quote(req,root)['total']['amount'],'0.04');req['item_id']='SUPPLY-WATER';assert_eq(m.calculate_price_quote(req,root)['status'],'OUT_OF_POLICY');return 'formal evidence scope verified'
case('D09 formal evidence registration actual commit',evidence_registration)
def successful_session():
 with Save() as root:
  stage=pathlib.Path(m.create_stage(root,'session_pricing_test')['staging']);m._copy_declared_cold_archives(root,stage,m.read_json(root/'manifest.json'));q=m.calculate_price_quote(request(quantity=1),stage);field='world_state_overrides.test_room_price_gold';patch={'format':m.PATCH_FORMAT,'operations':[{'op':'set','file':'state.json','path':'/'+field.replace('.','/'),'value':0.002,'allow_create':True}],'economic_effects':[{'target':'state:'+field,'currency':'gold','quote':q}]};pf=root/'test_patch.json';pf.write_text(json.dumps(patch));m.apply_patch(stage,pf);out=m.atomic_save(stage,'V14.22','structured economic fact acceptance',root,False,False);assert_eq(out.get('committed'),True);assert_eq(m.get_by_path(m.read_json(root/'state.json'),field),.002);return 'session fact validated and committed'
case('E13 session structured amount success actual commit',successful_session)
def automatic_comparable():
 with Save() as root:
  stage=pathlib.Path(m.create_stage(root,'session_pricing_test')['staging']);m._copy_declared_cold_archives(root,stage,m.read_json(root/'manifest.json'));rec={'price_id':'PRICE-TEST-ORDINARY-ROOM','item_id':'TEST-ORDINARY-ROOM','name':'same sealed room specification fixture','comparable_price_id':'PRICE-XILU-ORDINARY_ROOM_NIGHT','specification':{},'scope':{'region':'熄炉-9'},'comparability_basis':'same ordinary room specification and location; disposable fixture'};patch={'format':m.PATCH_FORMAT,'operations':[],'price_registrations':[rec]};pf=root/'test_patch.json';pf.write_text(json.dumps(patch));m.apply_patch(stage,pf);out=m.atomic_save(stage,'V14.22','existing missing price permission acceptance',root,False,False);assert_eq(out.get('committed'),True);req=request(item_id='TEST-ORDINARY-ROOM');assert_eq(m.calculate_price_quote(req,root)['total']['amount'],'0.014');assert_eq(m.price_quote_packet(root,req),m.price_quote_packet(root,req));return 'automatic existing permission, no new player confirmation'
case('D10 missing ordinary service reuses applicable anchor automatically',automatic_comparable)
def scene_disclosure():
 with Save() as root:
  sid='TEST-DISCLOSE';grant(root,'scene_record',['state:engine_runtime.scene_registry_v1.records.'+sid]);q=m.calculate_price_quote(request(),root);tid=next(t['task_id'] for t in m.read_json(root/'tasks.json')['active_tasks'] if t['task_id']!=m._PATROL_TASK_ID)
  create=command(root,'scene_record',scene_id=sid,scene_action='create',task_id=tid,scene_type='test',title='quote fixture',participants=[],facts=[{'fact_id':'ROOM','value':'placeholder','epistemic':'confirmed'}],economic_fact_refs={'ROOM':q});m.domain_command_packet(root,create,'V14.22','scene create disclosure fixture')
  p=command(root,'scene_record',scene_id=sid,scene_action='reveal',fact_id='ROOM',viewer='player');p['command_id']='TEST-DISCLOSE-COMMAND';m.domain_command_packet(root,p,'V14.23','authorized quote disclosure fixture');view=m.scene_query_packet(root,sid)['value'];assert_eq(len(view['confirmed_facts']),1);assert_eq(view['economic_fact_refs']['ROOM']['quote_id'],q['quote_id']);observer=m.scene_query_packet(root,sid,audience='observer',observer_id='OTHER');assert_eq(observer['status'],'NOT_FOUND');return 'disclosed quote visible to player only'
case('E14 actual reveal respects quote visibility',scene_disclosure)
def changed_clock():
 s=m.read_json(BASE/'state.json');clock=next(iter(s['engine_runtime']['long_horizon']['hazard_clocks'].values()));clock['test_mutation']=True;assert_eq(m._pricing_preserved_gap(s),False);return 'fingerprint change rejected'
case('F06 altered random clock has no migration exemption',changed_clock)
def raw_adjust():
 with Save() as root:
  grant(root,'adjust_funds',['state:summary.funds.gold']);p=command(root,'adjust_funds',reason='fixture',gold_delta=-.014);before=core_hash(root);expect_error(lambda:m.domain_command_packet(root,p,'V14.22','raw spend denied'));assert_eq(core_hash(root),before);return 'valid budget cannot bypass price validation'
case('E15 existing adjust funds cannot bypass quote',raw_adjust)
def insufficient():
 docs=m._pricing_documents(BASE);state=docs['state'];rt=state['engine_runtime']['finance_runtime'];rt['funds_units']['gold']=1;m._finance_sync_view(state)
 return expect_error(lambda:m._finance_credit(state,'gold',-.014),'NEGATIVE_BALANCE')
case('E16 fixed integer finance refuses insufficient cash',insufficient)


def market_cap():
 req=request(item_id='STAR-CHART',unit='份',quantity=1,currency='grey',channel='grey',quoted_unit_price={'amount':20,'currency':'grey'});q=m.calculate_price_quote(req,BASE);out=m.market_offer_packet({'ask_price':20,'offer_price':5000,'floor_price':20,'currency':'grey','price_context':q},BASE);assert_eq(out['result'],'PRICE_REJECTED');return out['proposal_validation']
case('B17 mathematical accept cannot bypass star cap',market_cap)
def valid_market():
 q=quote(quantity=7);out=m.market_offer_packet({'ask_price':.014,'offer_price':.014,'floor_price':.014,'currency':'gold','price_context':q},BASE);assert_eq(out['result'],'ACCEPT');assert_eq(out['validated_quote']['total']['amount'],'0.014');return 'valid proposal still not settlement authority'
case('E18 verified business offer preserves arithmetic',valid_market)
def precise_quantity_budget():
 with Save() as root:
  p=settlement_fixture(root,req=request(quantity='1.0000000000000000001'));state=m.read_json(root/'state.json');state['standing_authorizations']['TEST-GRANT']['machine_grant']['max_quantity']=1;write(root,'state.json',state);rebind(root);p['base_save_set_id']=m.read_json(root/'manifest.json')['save_set_id'];p['quote']=m.calculate_price_quote(p['quote']['request'],root);before=core_hash(root);expect_error(lambda:m.domain_command_packet(root,p,'V14.22','exact quantity budget rejection'),'BUDGET_EXCEEDED:quantity');assert_eq(core_hash(root),before);return 'no floating-point quantity undercount'
case('E19 quantity budget uses exact decimal',precise_quantity_budget)

output={'status':'PASS' if all(r['status']=='PASS' for r in results) else 'FAIL','passed':sum(r['status']=='PASS' for r in results),'total':len(results),'tests':results};target=pathlib.Path(os.environ.get('PRICING_TEST_OUTPUT',str(BASE.parent/'pricing_acceptance_results.json')));target.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':output['status'],'passed':output['passed'],'total':output['total'],'output':str(target)},ensure_ascii=False));sys.exit(0 if output['status']=='PASS' else 1)
