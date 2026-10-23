# V14.57 forward suite: original suite remains byte-exact; only its version-bound migration fixture is replaced. Behavioral assertions are unchanged.
#!/usr/bin/env python3
"""Version-bound stage3 acceptance. Every host approval here is SYNTHETIC TEST
ONLY, on a new isolated clone. It is not an actual NPC/model generation proof.
"""
import argparse,pathlib,os,sys,json,importlib.util,shutil,time,traceback,copy,subprocess,statistics,io,contextlib
sys.dont_write_bytecode=True
P=pathlib.Path
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def run(source,out):
 source=source.resolve();out=out.resolve();out.mkdir(parents=True,exist_ok=False)
 h=load(source/'development/tests/stage1_v1453.py','stage3_helpers');a=h.load_api(source,'stage3_api');results=[];contract=h.read(source/'development/evidence/stage3_v1455_input_contract.json');source_before={n:h.sha(source/n) for n in contract['files'] if (source/n).is_file()}
 def case(name,fn):
  t=time.perf_counter()
  try:row={'name':name,'status':'PASS','detail':fn()}
  except (Exception,SystemExit) as e:row={'name':name,'status':'FAIL','error':str(e),'trace':traceback.format_exc()}
  row['seconds']=time.perf_counter()-t;results.append(row);report={'schema':'STAGE4_FORWARD_STORY_REGRESSION_V1','status':'PASS' if all(x['status']=='PASS' for x in results) else 'FAIL','engine_sha256':h.sha(source/'engine.py'),'manifest_sha256':h.sha(source/'manifest.json'),'save_set_id':h.read(source/'manifest.json')['save_set_id'],'tests':results};(out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str));print(row['status'],name,row.get('error',''),flush=True)
 class Fixture:
  def __init__(self,name):
   self.root=h.clone(source,out/name);self.a=h.load_api(self.root,'stage3_'+name);self.version=60;self.actor='PER-HAWK-MALEN-01';self.other='PER-NOVA-01';self.sid='TEST-'+name.upper();self.samples=[]
  def command(self,kind,cid,**fields):return h.command(self.a,self.root,kind,cid,**fields)
  def commit(self,kind,cid,**fields):
   command=self.command(kind,cid,**fields);env=h.envelope(self.a,self.root,command);env['limits']['uses']=100;env['valid_until']='8363-12-11T12:00:00';self.version=max(self.version,int(h.read(self.root/'manifest.json')['save_version'].split('.')[1]))+1;t=time.perf_counter();r=self.a.host_intent_command(self.root,env,'V14.'+str(self.version),False);self.samples.append({'command_id':cid,'seconds':time.perf_counter()-t,'status':r['status'],'canonical_output_bytes':len(json.dumps(r,ensure_ascii=False,separators=(',',':'),default=str).encode())});return command,env,r
  def setup(self,extra=None):
   actions=[{'type':'scene_open','scene_id':self.sid,'task_id':None,'family':'conversation','title':'SYNTHETIC TEST ONLY '+self.sid,'location_ref':'LOC-FREEPORT-XILU9','participants':[self.actor,self.other],'presence_mode':'remote','visible_to':['player','npc:'+self.actor,'npc:'+self.other]},{'type':'fact_append','scene_id':self.sid,'fact_id':'F-OPEN','subject_id':self.actor,'predicate':'statement','value':'合成测试中已授权的当前联络。','epistemic':'confirmed','source_category':'direct_observation'}]
   for viewer in ['player','npc:'+self.actor,'npc:'+self.other]:actions.append({'type':'knowledge_disclose','scene_id':self.sid,'fact_id':'F-OPEN','viewer_id':viewer,'channel':'observed','basis_event_id':'$current_transaction'})
   actions += [{'type':'scene_phase','scene_id':self.sid,'phase':'open'},{'type':'scene_focus_v2','scene_id':self.sid}]+(extra or [])
   return self.commit('story_setup','SETUP-'+self.sid,actions=actions)
  def proposal(self,cid,text='先核对事实，再等待指挥官选择。',**updates):
   c=self.a.prepare_turn(self.root,self.sid,self.actor,'player','合成测试当前意图',budget_bytes=16384)
   p={'schema':self.a.STORY_TURN_SCHEMA,'turn_id':cid,'base_identity':c['base_identity'],'scene_id':self.sid,'actor_id':self.actor,'viewer':'player','player_intent':'合成测试当前意图','intent_tags':['conversation'],'basis_refs':['fact/'+self.sid+'/F-OPEN'],'segments':[{'mode':'dialogue','speaker_id':self.actor,'text':text,'basis_refs':['fact/'+self.sid+'/F-OPEN'],'receipt_refs':[]}],'effects':[],'updates':[],'consequences':[],'claims':[],'public_reason':'按当前可见事实讨论，未预先执行机械效果。','candidates':['询问','等待','核对凭证']};p.update(updates);return p
  def turn(self,cid,**fields):p=self.proposal(cid,**fields);return p,self.commit('story_turn',cid,proposal=p)
 def migration():
  c=h.read(source/'development/evidence/performance_batch1_input_contract.json')
  for n in ('state.json','tasks.json','rules.json','catalog.json','guard.py'):assert h.sha(source/n)==c['files'][n]
  meta,events,raw=a.read_history_raw(source/'events.jsonl')
  assert len(events)==2615 and meta['next_seq']==2616
  assert h.read(source/'manifest.json')['parent_save_set_id']==c['input_save_set_id']
  assert events[-1]['subtype']=='performance_batch1_maintenance' and events[-1]['zero_time'] and events[-1]['changes']==[]
  return {'baseline':'actual V14.56 parent','four_JSON_and_Guard_byte_exact':True,'zero_time_maintenance_only':True}
 case('equivalent_zero_time_migration',migration)
 f=Fixture('multiround');f.setup();baseline=f.a._five_account_balances(f.a.read_json(f.root/'state.json'))
 def conversation():
  transcript=[]
  for i,text in enumerate(['这只是1000金币的报价，请先核对条款。','我听说报价可能改变，这仍是传闻。','先不成交，等你确认后再行动。']):
   p,(_,_,result)=f.turn('CHAT-'+str(i),text=text);report=f.a.turn_report(f.root,p['turn_id']);assert report['status']=='COMMITTED';assert all(not s['world_truth'] for s in report['segments']);transcript.append({'input':p,'report':report})
  assert f.a._five_account_balances(f.a.read_json(f.root/'state.json'))==baseline
  (out/'daily_business_multiround_SYNTHETIC.json').write_text(json.dumps({'generation_quality':'NOT_RUN','source':'fixed synthetic acceptance data, not autonomous generation','turns':transcript},ensure_ascii=False,indent=2));return {'rounds':3,'numeric_quote_rumor_accepted':True,'no_mechanical_change':True,'generation_quality':'NOT_RUN'}
 case('ordinary_conversation_and_numeric_quotes',conversation)
 def trade_retry():
  effect={'kind':'account_transfer','source_account':'covert','destination_account':'fleet','currency':'grey','amount':'1.23','reason':'SYNTHETIC TEST ONLY atomic transfer'}
  updates=[{'type':'fact_append','scene_id':f.sid,'fact_id':'F-RESPONSE','subject_id':f.actor,'predicate':'social_reaction','value':'他要求核对交易回执后再继续。','epistemic':'confirmed','source_category':'direct_observation'},{'type':'knowledge_disclose','scene_id':f.sid,'fact_id':'F-RESPONSE','viewer_id':'npc:'+f.other,'channel':'heard','basis_event_id':'$current_transaction'}]
  p=f.proposal('TRADE-1',effects=[effect],updates=updates,segments=[{'mode':'outcome','speaker_id':None,'text':'','basis_refs':[],'receipt_refs':['effect:0']}]);command,env,result=f.commit('story_turn',p['turn_id'],proposal=p)
  s=f.a.read_json(f.root/'state.json');after=f.a._five_account_balances(s);assert int(after['covert_grey']['integer_units'])==int(baseline['covert_grey']['integer_units'])-12300;assert 'F-RESPONSE' in f.a._knowledge_known(s,f.sid,'npc:'+f.other)
  retry=f.a.host_intent_command(f.root,env,'V14.99');assert retry['status']=='ALREADY_APPLIED';assert f.a._five_account_balances(f.a.read_json(f.root/'state.json'))==after
  altered=copy.deepcopy(command);altered['proposal']['public_reason']='different';h.reject(lambda:f.a.commit_turn(f.root,altered,'V14.99'),'DIFFERENT_PAYLOAD')
  report=f.a.turn_report(f.root,p['turn_id']);assert report['segments'][0]['world_truth'] and report['verified_results'][0]['effect']['amount']=='1.23'
  before=f.a._repair_digest(f.a.read_json(f.root/'state.json')['engine_runtime']['finance_runtime']);f.commit('story_setup','REWRITE-1',actions=[{'type':'turn_rewrite','turn_id':'TRADE-1','viewer':'player','segments':[{'mode':'outcome','speaker_id':None,'text':'','basis_refs':[],'receipt_refs':['effect:0']},{'mode':'dialogue','speaker_id':f.actor,'text':'回执已经核对，后续另行决定。','basis_refs':[],'receipt_refs':[]}]}]);assert f.a._repair_digest(f.a.read_json(f.root/'state.json')['engine_runtime']['finance_runtime'])==before
  (out/'trade_receipt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));return {'one_cash_effect':True,'reaction_and_learning_same_event':True,'same_retry_same_receipt':True,'different_payload_rejected':True,'rewrite_does_not_replay':True}
 case('atomic_trade_learning_receipt_retry_and_rewrite',trade_retry)
 def failed_all_or_nothing():
  before={n:h.sha(f.root/n) for n in ['state.json','tasks.json','events.jsonl','manifest.json']};p=f.proposal('BAD-TRADE',effects=[{'kind':'account_transfer','source_account':'covert','destination_account':'fleet','currency':'grey','amount':'2.00','reason':'TEST rollback'}],updates=[{'type':'knowledge_disclose','scene_id':f.sid,'fact_id':'DOES-NOT-EXIST','viewer_id':'player','channel':'heard','basis_event_id':'$current_transaction'}]);command=f.command('story_turn',p['turn_id'],proposal=p);env=h.envelope(f.a,f.root,command);env['limits']['uses']=100
  h.reject(lambda:f.a.host_intent_command(f.root,env,'V14.90'));assert before=={n:h.sha(f.root/n) for n in before}
  return {'mechanical_success_then_story_failure_rolls_back_everything':True}
 case('failed_story_cannot_leave_half_trade',failed_all_or_nothing)
 def fake_and_stale():
  p=f.proposal('FAKE',claims=[{'receipt_ref':'command:NONEXISTENT','expected_effect':{'kind':'account_transfer','amount':'1000'}}]);c=f.command('story_turn','FAKE',proposal=p);env=h.envelope(f.a,f.root,c);h.reject(lambda:f.a.host_intent_command(f.root,env,'V14.91'),'COMMITTED_RECEIPT')
  p=f.proposal('FAKE-TEXT',segments=[{'mode':'outcome','speaker_id':None,'text':'账户增加了一千金币','basis_refs':[],'receipt_refs':[]}]);assert f.a.validate_proposal(f.root,p)['status']=='INVALID'
  p=f.proposal('STALE');f.turn('CHANGE');assert f.a.validate_proposal(f.root,p)['status']=='STALE'
  p=f.proposal('UNKNOWN-MECHANIC',effects=[{'kind':'teleport_ship','target':'secret'}]);assert f.a.validate_proposal(f.root,p)['status']=='UNSUPPORTED'
  c=f.command('story_turn','NO-HOST',proposal=f.proposal('NO-HOST'));h.reject(lambda:f.a.commit_turn(f.root,c,'V14.92'),'TRUSTED_BOUNDARY')
  return {'fabricated_outcome_refused':True,'stale_refused':True,'unsupported_explicit':True,'prose_cannot_self_authorize':True}
 case('fabricated_results_stale_proposals_and_real_authorization',fake_and_stale)
 def secrets():
  actions=[{'type':'fact_append','scene_id':f.sid,'fact_id':'F-A-SECRET','subject_id':f.actor,'predicate':'intent','value':'SECRET_SENTINEL_A_DO_NOT_DISCLOSE','epistemic':'confirmed','source_category':'direct_observation'},{'type':'knowledge_disclose','scene_id':f.sid,'fact_id':'F-A-SECRET','viewer_id':'npc:'+f.actor,'channel':'observed','basis_event_id':'$current_transaction'}];f.commit('story_setup','SECRET-A',actions=actions)
  ca=f.a.prepare_turn(f.root,f.sid,f.actor,'npc:'+f.actor,'私下思考');cb=f.a.prepare_turn(f.root,f.sid,f.other,'npc:'+f.other,'私下思考',intent_tags=['patrol']);cp=f.a.prepare_turn(f.root,f.sid,f.actor,'player','继续联络');assert 'SECRET_SENTINEL' in json.dumps(ca) and 'SECRET_SENTINEL' not in json.dumps(cb) and 'SECRET_SENTINEL' not in json.dumps(cp);assert 'S-B5' not in json.dumps(cb,ensure_ascii=False)
  ca['facts'][0]['value']='POLLUTED';assert 'POLLUTED' not in json.dumps(f.a.prepare_turn(f.root,f.sid,f.actor,'npc:'+f.actor,'再次读取'))
  p=f.proposal('SECRET-LEAK',basis_refs=['fact/'+f.sid+'/F-A-SECRET']);assert f.a.validate_proposal(f.root,p)['status']=='NEEDS_INFORMATION'
  # Private turn remains unqueryable through a guessed ID/report.
  p=f.proposal('PRIVATE-A',viewer='npc:'+f.actor,basis_refs=['fact/'+f.sid+'/F-A-SECRET'],segments=[{'mode':'hypothesis','speaker_id':f.actor,'text':'仅记录角色自身的不确定推测。','basis_refs':['fact/'+f.sid+'/F-A-SECRET'],'receipt_refs':[]}]);f.commit('story_turn',p['turn_id'],proposal=p);assert f.a.turn_report(f.root,p['turn_id'],'npc:'+f.other)['status']=='NOT_FOUND';assert f.a.turn_report(f.root,p['turn_id'],'player')['status']=='NOT_FOUND'
  return {'actor_A_secret_absent_from_B_player_and_wrong_report':True,'return_alias_isolated':True}
 case('multi_role_context_cache_report_and_error_isolation',secrets)
 def temporal_beliefs():
  sid=f.sid;actions=[]
  for fid,value,epistemic in [('F-RUMOR','他似乎愿意考虑延期。','rumor'),('F-OBSERVED','他现在明确表示愿意考虑延期。','confirmed')]:
   actions.append({'type':'fact_append','scene_id':sid,'fact_id':fid,'subject_id':f.actor,'predicate':'intent','value':value,'epistemic':epistemic,'source_category':'npc_statement' if epistemic=='rumor' else 'direct_observation'})
   for viewer in ['player','npc:'+f.actor]:actions.append({'type':'knowledge_disclose','scene_id':sid,'fact_id':fid,'viewer_id':viewer,'channel':'heard','basis_event_id':'$current_transaction'})
  f.commit('story_setup','BELIEF-SOURCES',actions=actions);s=h.read(f.root/'state.json');original=copy.deepcopy(f.a._knowledge_facts(s,sid)['F-RUMOR']);report=[]
  for i,text in enumerate(['先把传闻标为未经证实。','以当前明确答复更新判断。','保留原来听说过的内容及其来源。']):
   updates=[{'type':'fact_revision','scene_id':sid,'fact_id':'F-CHANGED','prior_fact_id':'F-RUMOR','mode':'temporal_change','evidence_fact_id':'F-OBSERVED','value':'他现在明确表示愿意考虑延期。'}] if i==1 else []
   p=f.proposal('BELIEF-'+str(i),text=text,basis_refs=['fact/'+sid+'/F-OPEN','fact/'+sid+'/F-RUMOR','fact/'+sid+'/F-OBSERVED'],updates=updates);f.commit('story_turn',p['turn_id'],proposal=p);report.append(f.a.turn_report(f.root,p['turn_id']))
  s=h.read(f.root/'state.json');assert f.a._knowledge_facts(s,sid)['F-RUMOR']==original;assert f.a._knowledge_facts(s,sid)['F-CHANGED']['change_kind']=='temporal_change';assert f.a._knowledge_facts(s,sid)['F-RUMOR']['epistemic']=='rumor'
  (out/'secret_choice_multiround_SYNTHETIC.json').write_text(json.dumps({'generation_quality':'NOT_RUN','turns':report},ensure_ascii=False,indent=2));return {'rumor_not_promoted':True,'new_time_fact_does_not_rewrite_old_fact':True,'rounds':3,'generation_quality':'NOT_RUN'}
 case('belief_evolution_with_committed_evidence',temporal_beliefs)
 def price_trade():
  g=Fixture('price');g.setup();b=g.a;r=g.root;request={'item_id':'SUPPLY-FOOD','unit':'包','quantity':10,'currency':'grey','transaction_type':'purchase'};q=b.calculate_price_quote(request,r);assert q['status']=='VALID'
  delivery={'inventory_ref':'state:inventories.supply_inventory.fleets.voyager.food.value','delta':10,'unit':'包'}
  confirmed={'settlement_id':'STORY-PRICE-TEST','quote_id':q['quote_id'],'binding_sha256':q['binding_sha256'],'direction':'debit','account':'covert','status':'completed','cash_amount':q['total'],'asset_disposition_verified':True,'inventory_delivery':delivery}
  # A synthetic actual-delivery evidence record, never a signed authorization.
  # The command still goes through the real trusted-host permission boundary.
  b._append_engine_history(r/'events.jsonl',{'event_id':'SYNTHETIC-DELIVERY-ONLY','type':'system','game_time':h.read(r/'state.json')['game_time'],'summary':'SYNTHETIC ISOLATED TEST DELIVERY','confirmed_price_settlement':confirmed});m=h.read(r/'manifest.json');b._component_write_manifest_native(r,m['save_version'],m['parent_save_set_id'],m['migration_lineage']);q=b.calculate_price_quote(request,r)
  before=h.read(r/'state.json')['inventories']['supply_inventory']['fleets']['voyager']['food']['value'];effect={'kind':'settle_price','settlement_id':'STORY-PRICE-TEST','quote':q,'direction':'debit','account':'covert','source_event_id':'SYNTHETIC-DELIVERY-ONLY','delivery':delivery};p=g.proposal('PRICED-TURN',effects=[effect]);g.commit('story_turn',p['turn_id'],proposal=p);assert h.read(r/'state.json')['inventories']['supply_inventory']['fleets']['voyager']['food']['value']==before+10;check=b.run_checks(r,full=True);assert check['status']=='PASS',check['errors'];return {'price_source_units_asset_delivery_and_native_full_audit':True,'aggregate_receipt_not_a_temporary_receipt':True}
 case('priced_transaction_inventory_and_story_same_commit',price_trade)
 def autonomy():
  p=f.proposal('AUTO-1',viewer='npc:'+f.actor);c=f.command('story_turn','AUTO-1',proposal=p);c.update(actor_id=f.actor,authorization='standing_authorization',authorization_ref='TEST-NPC-POLICY');targets=f.a._domain_command_targets(c)
  targets+=['state:engine_runtime.story_turns_v1.turns.AUTO-SPEND','state:account:covert:grey','state:account:fleet:grey']
  grant={'schema':'DOMAIN_MACHINE_GRANT_V1','grant_id':'TEST-NPC-POLICY','subject_id':f.actor,'action_kinds':['story_turn','account_transfer'],'targets':targets,'valid_from':h.read(f.root/'state.json')['game_time'],'valid_until':'8363-12-11T12:00:00','max_uses':5,'max_gold_units':0,'max_grey_units':0,'max_quantity':12300}
  f.commit('npc_policy','REGISTER-POLICY',policy_id='TEST-NPC-POLICY',policy_action='register',grant=grant)
  # Registering a policy advances the SAVESET; prepare again, preserve exact turn target.
  c['base_save_set_id']=h.read(f.root/'manifest.json')['save_set_id'];c['proposal']=f.proposal('AUTO-1',viewer='npc:'+f.actor)
  stream=io.StringIO()
  with contextlib.redirect_stdout(stream):rc=f.a.main(['invoke','--input',json.dumps(c,ensure_ascii=False),'--version','V14.80'])
  r=json.loads(stream.getvalue());assert rc==0 and r.get('committed'),r
  serialized=json.dumps(r,ensure_ascii=False);assert all(s not in serialized for s in ['machine_grant','seed_anchor','historical_gaps','next_blocker','S-B5'])
  bad=copy.deepcopy(c);bad['command_id']='AUTO-2';bad['proposal']=f.proposal('AUTO-2',viewer='npc:'+f.actor);bad['base_save_set_id']=h.read(f.root/'manifest.json')['save_set_id'];h.reject(lambda:f.a.commit_turn(f.root,bad,'V14.81'),'TARGET_OUT_OF_SCOPE')
  spend=copy.deepcopy(bad);spend['command_id']='AUTO-SPEND';spend['proposal']=f.proposal('AUTO-SPEND',viewer='npc:'+f.actor,effects=[{'kind':'account_transfer','source_account':'covert','destination_account':'fleet','currency':'grey','amount':'1.23','reason':'SYNTHETIC deny spend'}]);h.reject(lambda:f.a.commit_turn(f.root,spend,'V14.81'),'BUDGET_EXCEEDED:grey_units')
  current=copy.deepcopy(c);current['command_id']='AUTO-1';current['proposal']['public_reason']='changed';h.reject(lambda:f.a.commit_turn(f.root,current,'V14.81'),'DIFFERENT_PAYLOAD')
  c2=f.command('npc_policy','SELF-GRANT',policy_id='BAD',policy_action='register',grant=grant);c2.update(authorization='standing_authorization',authorization_ref='TEST-NPC-POLICY',actor_id=f.actor);h.reject(lambda:f.a.domain_command_packet(f.root,c2,'V14.81','test'),'TRUSTED_HOST')
  return {'real_host_registered_finite_policy':True,'actual_CLI_allowed_NPC_turn_committed':True,'NPC_write_summary_has_no_commander_diagnostics':True,'wrong_target_refused':True,'grey_budget_refused':True,'autonomous_privilege_escalation_refused':True}
 case('finite_autonomy_uses_existing_authorization_ledger',autonomy)
 def timeline():
  g=Fixture('timeline');g.setup();now=h.read(g.root/'state.json')['game_time'];due='8363-12-10T17:30:00';end='8363-12-10T17:40:00'
  goal={'type':'npc_update','entity_id':g.actor,'operation':'goal','record':{'goal_id':'G-WAIT','priority':50,'deadline':'8363-12-10T18:00:00','status':'pending','preconditions':[],'description':'合成测试待办唤醒。','visible_to':['player','npc:'+g.actor]}}
  def cons(cid,mode='needs_ai',condition=None,effect=None):return {'type':'consequence_schedule','scene_id':g.sid,'consequence_id':cid,'subject_id':g.actor,'effect_type':'pending_reply','cause_event_id':'$current_transaction','not_before':due,'not_after':end,'visible_to':['player','npc:'+g.actor],'text':'合成测试延期答复，不含机械奖励。','mode':mode,'condition':condition or {'kind':'always'},'task_id':None,'effect':effect or {'kind':'await_ai'}}
  a1=cons('A-MECHANICAL','mechanical',effect={'kind':'goal_activate','entity_id':g.actor,'goal_id':'G-WAIT'});a2=cons('B-AI');a3=cons('C-CONDITION',condition={'kind':'fact_known','scene_id':g.sid,'fact_id':'F-NEVER','viewer_id':'npc:'+g.actor});g.commit('story_setup','SCHEDULE',actions=[goal,a1,a2,a3])
  state=h.read(g.root/'state.json');tasks=h.read(g.root/'tasks.json');rows=g.a._s3_pending_nodes(state,tasks,g.a.parse_iso(now),g.a.parse_iso(end));assert [r['consequence_id'] for r in rows]==['A-MECHANICAL','B-AI','C-CONDITION']
  plan=g.a.routineplan_packet(g.root,'8363-12-10T17:50:00');assert plan['semantic_barrier']['kind']=='story_consequence_ai' and plan['safe_until']==due
  preview=g.a.turn_packet(g.root,'preview','8363-12-10T17:50:00');assert any(r.get('source')=='story_consequence' for r in preview['candidate_events'])
  # One earlier deterministic consequence is at the same time as the AI barrier.
  # The engine must allow those ordered, already authorized nodes through.
  r=g.a.turn_session('start',until='8363-12-10T17:50:00',version='V14.85',scope='SYNTHETIC TEST consequence boundary');assert r['status']=='PAUSED_COMMITTED',r
  state=h.read(g.root/'state.json');assert state['game_time']==due;assert state['engine_runtime']['story_turns_v1']['npcs'][g.actor]['goals']['G-WAIT']['status']=='active'
  # Cancel the blocking reply, then advance past the inclusive last instant.
  g.version=85;g.commit('story_setup','CANCEL-B',actions=[{'type':'consequence_manage','scene_id':g.sid,'consequence_id':'B-AI','status':'cancelled','reason':'合成取消，不回填过去'}]);r=g.a.turn_session('start',until='8363-12-10T17:45:00',version='V14.88',scope='SYNTHETIC TEST expiry');state=h.read(g.root/'state.json');c=state['engine_runtime']['story_runtime_v1']['consequences'];assert c['A-MECHANICAL']['status']=='delivered' and c['B-AI']['status']=='cancelled' and c['C-CONDITION']['status']=='expired'
  (out/'deferred_promise_SYNTHETIC.json').write_text(json.dumps({'plan':plan,'state':c,'generation_quality':'NOT_RUN'},ensure_ascii=False,indent=2));return {'same_time_stable_order':True,'real_session_stops_for_AI':True,'pure_authorized_effect_once':True,'conditional_wait_no_busy_loop':True,'expiry_strictly_after_inclusive_end':True,'cancelled_not_delivered':True}
 case('unified_consequence_timeline_real_advance_and_expiry',timeline)
 def multiscene():
  root=f.root;before=h.read(root/'state.json');patrol=copy.deepcopy(before['world_state_overrides']['intelligence_and_security']['xianyue_asteroid_shadow_patrol_current']);other='TEST-INDEPENDENT-2';action={'type':'scene_open','scene_id':other,'task_id':None,'family':'negotiation','title':'合成多线谈判','location_ref':'LOC-FREEPORT-XILU9','participants':[f.actor],'presence_mode':'remote','visible_to':['player','npc:'+f.actor]};f.version=81;f.commit('story_setup','MULTISCENE',actions=[action,{'type':'scene_phase','scene_id':other,'phase':'open'},{'type':'scene_focus_v2','scene_id':other}]);after=h.read(root/'state.json');assert after['world_state_overrides']['intelligence_and_security']['xianyue_asteroid_shadow_patrol_current']==patrol
  action=copy.deepcopy(action);action.update(scene_id='BAD-PATROL',task_id=f.a._PATROL_TASK_ID);c=f.command('story_setup','BAD-PATROL',actions=[action]);env=h.envelope(f.a,root,c);h.reject(lambda:f.a.host_intent_command(root,env,'V14.95'),'STANDBY')
  closed=next(iter(after['engine_runtime']['scene_registry_v1']['legacy_closed']));action.update(scene_id=closed,task_id=None);c=f.command('story_setup','REOPEN-OLD',actions=[action]);env=h.envelope(f.a,root,c);h.reject(lambda:f.a.host_intent_command(root,env,'V14.95'),'ALREADY_USED')
  f.sid=other;f.commit('story_setup','NEGOTIATION-BASIS',actions=[{'type':'fact_append','scene_id':other,'fact_id':'F-OPEN','subject_id':f.actor,'predicate':'statement','value':'合成谈判当前联络。','epistemic':'confirmed','source_category':'direct_observation'}]+[{'type':'knowledge_disclose','scene_id':other,'fact_id':'F-OPEN','viewer_id':v,'channel':'heard','basis_event_id':'$current_transaction'} for v in ['player','npc:'+f.actor]])
  report=[]
  for i,text in enumerate(['双方的目的并不相同，先确认各自条件。','他提出延期方案，当前仍未签约。','保留分歧，等待指挥官最终决定。']):p,_=f.turn('NEGOTIATION-'+str(i),text=text);report.append(f.a.turn_report(root,p['turn_id']))
  (out/'conflict_negotiation_multiround_SYNTHETIC.json').write_text(json.dumps({'generation_quality':'NOT_RUN','turns':report},ensure_ascii=False,indent=2));return {'two_independent_scenes_run':True,'focus_explicit':True,'existing_hidden_standby_byte_values_unchanged':True,'old_case_cannot_reopen':True,'negotiation_rounds':3}
 case('independent_scenes_focus_and_existing_patrol_policy',multiscene)
 def budget_parity():
  p=f.a.prepare_turn(f.root,f.sid,f.actor,'npc:'+f.actor,'当前意图',budget_bytes=1024);assert p['budget_exceeded'];assert p['context_bytes']==len(json.dumps(p,ensure_ascii=False,separators=(',',':'),default=str).encode());assert p['hard_constraints'] and any(r['hard'] for r in p['rules'])
  dev=h.load_api(source,'stage3_dev',True);x=a.prepare_turn(source);y=dev.prepare_turn(source);assert x==y
  stdout=io.StringIO()
  with contextlib.redirect_stdout(stdout):rc=a.main(['storyschema','--base',str(source)])
  assert rc==0 and json.loads(stdout.getvalue())['proposal_schema']==a.STORY_TURN_SCHEMA
  (out/'ordinary_timing_samples.json').write_text(json.dumps(f.samples,ensure_ascii=False,indent=2));return {'hard_rules_not_truncated':True,'final_bytes_exact':True,'actual_cli_and_development_loader_match':True}
 case('budget_full_content_cli_and_development_release_parity',budget_parity)
 assert source_before=={n:h.sha(source/n) for n in source_before},'SOURCE_CHANGED_BY_TESTS'
 return all(x['status']=='PASS' for x in results)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);ns=p.parse_args();raise SystemExit(0 if run(ns.source,ns.output) else 1)
