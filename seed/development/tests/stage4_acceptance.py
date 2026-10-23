#!/usr/bin/env python3
"""Version-bound fourth-stage acceptance; synthetic approvals only on clones."""
import pathlib,importlib.util,json,os,copy,shutil,time,traceback,argparse,sys,subprocess
sys.dont_write_bytecode=True
P=pathlib.Path
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def run(source,out):
 source=source.resolve();out=out.resolve();out.mkdir(parents=True,exist_ok=False);h=load(source/'development/tests/stage1_v1453.py','stage4helpers');a=h.load_api(source,'stage4source');rows=[]
 def case(name,fn):
  t=time.perf_counter()
  try:r={'name':name,'status':'PASS','detail':fn()}
  except (Exception,SystemExit) as ex:r={'name':name,'status':'FAIL','error':str(ex),'trace':traceback.format_exc()}
  r['seconds']=time.perf_counter()-t;rows.append(r);(out/'results.json').write_text(json.dumps({'schema':'STAGE4_ACCEPTANCE_V1','status':'FAIL' if any(r['status']=='FAIL' for r in rows) else 'PASS','save_set_id':h.read(source/'manifest.json')['save_set_id'],'manifest_sha256':h.sha(source/'manifest.json'),'engine_sha256':h.sha(source/'engine.py'),'tests':rows},ensure_ascii=False,indent=2));print(r['status'],name,r.get('error',''),flush=True)
 class Fixture:
  def __init__(self,name):self.root=h.clone(source,out/name);self.a=h.load_api(self.root,'fixture_'+name);self.version=60;self.actor='PER-HAWK-MALEN-01';self.sid='TEST-STAGE4-'+name.upper()
  def command(self,kind,cid,**f):return h.command(self.a,self.root,kind,cid,**f)
  def execute(self,c):
   env=h.envelope(self.a,self.root,c);env['limits']['uses']=1000;env['valid_until']='8363-12-11T12:00:00';self.version=max(self.version,int(h.read(self.root/'manifest.json')['save_version'].split('.')[1]))+1;r=self.a.host_intent_command(self.root,env,'V14.'+str(self.version));return env,r
  def commit(self,kind,cid,**fields):c=self.command(kind,cid,**fields);env,r=self.execute(c);return c,env,r
  def package(self,i):return h.read(source/'development/examples/content_v2'/('demo_adjutant_1_'+str(i)+'_0.json'))
  def seal(self,p):p['content_sha256']=self.a._s4_package_digest(p);return p
  def install(self,p,cid):plan=self.a.content_upgrade_preview(self.root,p);return self.commit('content_upgrade',cid,package=p,plan=plan)
  def frozen(self):return {n:h.sha(self.root/n) for n in self.a.COMPONENT_FILES}
  def reject_unchanged(self,c,part=None):
   before=self.frozen();env=h.envelope(self.a,self.root,c);env['limits']['uses']=1000;h.reject(lambda:self.a.host_intent_command(self.root,env,'V14.99'),part);assert before==self.frozen()
  def proposal(self,cid,**kw):
   p={'schema':self.a.STORY_TURN_SCHEMA,'turn_id':cid,'base_identity':self.a._s3_identity(self.root),'scene_id':self.sid,'actor_id':self.actor,'viewer':'player','player_intent':'KEY-NEED','intent_tags':['conversation'],'basis_refs':[],'segments':[{'mode':'dialogue','speaker_id':self.actor,'text':'合成测试：先核对当前已知资料。','basis_refs':[],'receipt_refs':[]}],'effects':[],'updates':[],'consequences':[],'claims':[],'public_reason':'合成测试，不预先认定机械结果。','candidates':['核对','等待']};p.update(kw);return p
 def maintenance():
  c=h.read(source/'development/evidence/stage4_input_contract.json')
  for n in ('state.json','tasks.json','rules.json','catalog.json','guard.py'):assert h.sha(source/n)==c['files'][n]
  _,ev,raw=a.read_history_raw(source/'events.jsonl');assert len(ev)==2614 and a.sha256_bytes(b'\n'.join(raw[:2613])+b'\n')==c['logical_history_raw_sha256'];assert len(raw[2613:])==1 and ev[-1]['zero_time'] and ev[-1]['changes']==[]
  return {'state_data_byte_exact':True,'old_events_byte_exact':2613,'maintenance_events':1,'game_events_added':0}
 case('exact_maintenance_no_world_mutation',maintenance)
 def dependency():
  order=a.ExtensionServices.check_dependencies(a.ExtensionServices.dependencies);h.reject(lambda:a.ExtensionServices.check_dependencies({'x':['y'],'y':['x']}),'CYCLE');h.reject(lambda:a.ExtensionServices.check_dependencies({'x':['missing']}),'MISSING')
  dev=h.load_api(source,'s4dev',dev=True);assert dev.service_contracts()==a.service_contracts();assert dev.rule_coverage(source)==a.rule_coverage(source)
  assert a._v130_layer_component_source_check_04 is a._v130_layer_component_source_check_02 and dev._v130_layer_component_source_check_04 is dev._v130_layer_component_source_check_02
  assert dev._domain_command_targets({'kind':'content_upgrade','package':{'package_id':'demo.adjutant'}})==a._domain_command_targets({'kind':'content_upgrade','package':{'package_id':'demo.adjutant'}})
  assert set(h.read(source/'development/dependency_inventory.json')['active_extension_dispatch']['previous_legacy_fallbacks'])=={'_s3_previous_apply','_s3_previous_targets','_s3_previous_cost'}
  return {'DAG_checked':True,'cycles_missing_rejected':True,'real_development_release_contract_matrix_equal':True,'service_order':order}
 case('explicit_dispatch_dependencies_and_development_parity',dependency)
 f=Fixture('content');saved={};old_world=h.read(f.root/'state.json');oldtasks=h.sha(f.root/'tasks.json')
 def continuous():
  for i in range(3):
   p=f.package(i);c,env,r=f.install(p,'CONTENT-'+str(i));assert r['status']=='SAVED';saved[i]={'package':p,'command':c,'envelope':env}
   if i==0:
    ref={'package_id':p['package_id'],'version':p['version'],'definition_id':'demo.adjutant:conversation','package_sha256':p['content_sha256']};saved['ref']=ref
    action={'type':'scene_open','scene_id':f.sid,'task_id':None,'family':'conversation','title':'SYNTHETIC version-pinned scene','location_ref':'LOC-FREEPORT-XILU9','participants':[f.actor],'presence_mode':'remote','visible_to':['player','npc:'+f.actor]}
    f.commit('content_scene_open','CONTENT-SCENE',definition_ref=ref,scene=action);f.commit('story_setup','CONTENT-OPEN',actions=[{'type':'scene_phase','scene_id':f.sid,'phase':'open'}])
  assert f.a.content_resolve(f.root,saved['ref'])['definition']==saved[0]['package']['definitions'][0]
  assert f.a._five_account_balances(h.read(f.root/'state.json'))==f.a._five_account_balances(old_world);assert h.sha(f.root/'tasks.json')==oldtasks;assert h.read(f.root/'state.json')['inventories']==old_world['inventories']
  ctx=f.a.prepare_turn(f.root,f.sid,f.actor,'player','普通交谈');assert ctx['content_definitions'][0]['binding']['version']=='1.0.0';assert next(r for r in ctx['rules'] if r['rule_id']=='demo.adjutant:style')['version']=='1.0.0'
  reg=h.read(f.root/'catalog.json')['content_versions_v2'];assert set(reg['packages']['demo.adjutant']['versions'])=={'1.0.0','1.1.0','1.2.0'}
  assert f.a.run_checks(f.root,full=True)['status']=='PASS';(out/'content_continuity.json').write_text(json.dumps({'installed_versions':['1.0.0','1.1.0','1.2.0'],'pinned_scene_definition':ctx['content_definitions'],'pinned_rules':[r for r in ctx['rules'] if r['rule_id'].startswith('demo.')],'actual_catalog_registry':reg,'synthetic':True},ensure_ascii=False,indent=2))
  return {'first_install_two_upgrades':True,'old_scene_and_rules_pinned':'1.0.0','old_equipment_inventory_task_prices_RNG_unchanged':True,'definitions_not_assets':True}
 case('real_install_two_upgrades_and_old_instance_compatibility',continuous)
 def retain_migration():
  g=object.__new__(Fixture);g.root=h.clone(f.root,out/'breaking_migration');g.a=h.load_api(g.root,'breaking_migration');g.version=80;g.actor=f.actor;g.sid=f.sid
  major=g.package(2);major['version']='2.0.0';major['definitions'][1]['data']['unit']='箱';major['migrations']=[{'op':'retain_version','definition_id':'demo.adjutant:lamp','from_version':'1.2.0'}];g.seal(major);plan=g.a.content_upgrade_preview(g.root,major);assert plan['breaking']==['demo.adjutant:lamp'];g.install(major,'DECLARED-RETAIN-MIGRATION')
  ref={'package_id':'demo.adjutant','version':'1.2.0','definition_id':'demo.adjutant:lamp','package_sha256':g.package(2)['content_sha256']};assert g.a.content_resolve(g.root,ref)['definition']['data']['unit']=='台';assert g.a.content_resolve(g.root,saved['ref'])['definition']==saved[0]['package']['definitions'][0];assert g.a.run_checks(g.root,full=True)['status']=='PASS'
  return {'explicit_breaking_migration_executed':True,'old_unit_definition_pinned':True,'old_scene_readable':True,'arbitrary_world_migration_not_supported':True}
 case('declared_retain_version_migration_real_commit',retain_migration)
 def legacy_compatibility():
  g=object.__new__(Fixture);g.root=h.clone(f.root,out/'legacy_install');g.a=h.load_api(g.root,'legacy_install');g.version=80
  package={'schema':'VOYAGER_CONTENT_PACKAGE_V1','schema_version':1,'package_id':'demo.legacy','namespace':'demo.legacy','version':'1.0.0','dependencies':{},'rule_version':1,'source':'SYNTHETIC legacy compatibility','visibility':'definition_only','definitions':[{'id':'demo.legacy:location','kind':'location','description':'纯数据旧接口测试，不授予地点。'}]};c=g.command('content_install','LEGACY-INSTALL',package=package);assert g.a._domain_command_targets(c)==g.a._s3_previous_targets(c) and g.a._domain_authorization_cost(c)==g.a._s3_previous_cost(c);g.execute(c);assert g.a.run_checks(g.root,full=True)['status']=='PASS'
  return {'V1_first_install_after_V2_registry':True,'legacy_exact_targets_cost_preserved':True,'no_legacy_upgrade_shortcut':True}
 case('legacy_content_first_install_service_compatibility',legacy_compatibility)
 def invalid_packages():
  good=f.package(2);cases=[]
  for label,change,part in [
   ('same_version',lambda p:p['definitions'][0]['data'].update(description='different'),'SAME_VERSION'),
   ('arbitrary_code',lambda p:p['definitions'][0]['data'].update(code='print(1)'),'DATA_ONLY'),
   ('price_claim',lambda p:p['definitions'][1]['data'].update(price_gold=10000),'DATA_ONLY'),
   ('missing_dep',lambda p:p.update(version='1.3.0',dependencies={'absent.package':'>=1.0.0'}),'DEPENDENCY'),
   ('used_delete',lambda p:p.update(version='1.3.0',definitions=p['definitions'][1:]),'CANNOT_DELETE'),
   ('unsupported_migration',lambda p:p.update(version='1.3.0',migrations=[{'op':'set_path','definition_id':'demo.adjutant:lamp','from_version':'1.2.0'}]),'MIGRATION_UNSUPPORTED'),
   ('breaking_no_migration',lambda p:(p.update(version='1.3.0'),p['definitions'][1]['data'].update(unit='箱')),'BREAKING'),
   ('downgrade',lambda p:p.update(version='0.9.0'),'DOWNGRADE'),
   ('conflicting_rules',lambda p:(p.update(version='1.3.0'),p['definitions'][0].update(conflict_key='conflict'),p['definitions'][1].update(conflict_key='conflict')),'CONFLICT')]:
   p=copy.deepcopy(good);change(p);f.seal(p);before=f.frozen();h.reject(lambda:f.a.content_upgrade_preview(f.root,p),part);assert before==f.frozen();cases.append(label)
  p=copy.deepcopy(good);p['version']='1.3.0';p['definitions'][0]['title']='new';h.reject(lambda:f.a.content_upgrade_preview(f.root,p),'DIGEST')
  return {'rejected':cases+['wrong_digest'],'all_authority_unchanged':True}
 case('data_only_digest_used_deletion_bad_migration_atomic_refusals',invalid_packages)
 def dependencies_stale():
  p=f.package(2);p['version']='1.3.0';f.seal(p);stale=f.a.content_upgrade_preview(f.root,p)
  dep=f.package(0);dep.update(package_id='demo.dependent',namespace='demo.dependent',dependencies={'demo.adjutant':'>=1.0.0,<2.0.0'});
  for d in dep['definitions']:d['id']=d['id'].replace('demo.adjutant:','demo.dependent:')
  f.seal(dep);f.install(dep,'CONTENT-DEPENDENT')
  f.reject_unchanged(f.command('content_upgrade','STALE-PLAN',package=p,plan=stale),'STALE_OR_TAMPERED')
  cycle=copy.deepcopy(p);cycle['dependencies']={'demo.dependent':'>=1.0.0'};f.seal(cycle);h.reject(lambda:f.a.content_upgrade_preview(f.root,cycle),'CYCLE')
  major=f.package(2);major['version']='2.0.0';major['definitions'][1]['data']['unit']='箱';major['migrations']=[{'op':'retain_version','definition_id':'demo.adjutant:lamp','from_version':'1.2.0'}];f.seal(major);h.reject(lambda:f.a.content_upgrade_preview(f.root,major),'DEPENDENCY_CONFLICT')
  env=saved[2]['envelope'];r=f.a.host_intent_command(f.root,env,'V14.99');assert r['status']=='ALREADY_APPLIED'
  nohost=f.command('content_upgrade','NO-HOST',package=p,plan=f.a.content_upgrade_preview(f.root,p));h.reject(lambda:f.a.domain_command_packet(f.root,nohost,'V14.99','synthetic'),'TRUSTED_BOUNDARY')
  return {'reverse_dependency_conflict':True,'upgrade_cycle':True,'actual_source_changed_stale_plan':True,'same_command_same_receipt':True,'ordinary_payload_cannot_self_authorize':True}
 case('dependency_conflicts_cycles_stale_plan_retry_and_auth',dependencies_stale)
 def memory_setup():
  actions=[]
  for i in range(3):
   fid='MEM-'+str(i);value='KEY-NEED 当前承诺需要原始资料。' if i==2 else '合成已知资料'+str(i)
   actions += [{'type':'fact_append','scene_id':f.sid,'fact_id':fid,'subject_id':f.actor,'predicate':'statement','value':value,'epistemic':'confirmed','source_category':'direct_observation'}]+[{'type':'knowledge_disclose','scene_id':f.sid,'fact_id':fid,'viewer_id':v,'channel':'heard','basis_event_id':'$current_transaction'} for v in ['player','npc:'+f.actor]]
  actions += [{'type':'fact_append','scene_id':f.sid,'fact_id':'PRIVATE','subject_id':f.actor,'predicate':'intent','value':'SECRET-S4-NPC-ONLY','epistemic':'confirmed','source_category':'direct_observation'},{'type':'knowledge_disclose','scene_id':f.sid,'fact_id':'PRIVATE','viewer_id':'npc:'+f.actor,'channel':'observed','basis_event_id':'$current_transaction'}];f.commit('story_setup','MEMORY-SOURCES',actions=actions)
  player=f.a.memory_search(f.root,'player','KEY-NEED',scene_id=f.sid);npc=f.a.memory_search(f.root,'npc:'+f.actor,'SECRET',scene_id=f.sid);assert len(player['rows'])==1 and len(npc['rows'])==1;assert 'SECRET-S4' not in json.dumps(f.a.memory_search(f.root,'player'))
  ev=f.a.memory_evidence(f.root,player['rows'][0]['ref'],'player');assert ev['sources'] and all(x['full_event'] is None for x in ev['sources']);assert f.a.memory_evidence(f.root,'fact/'+f.sid+'/PRIVATE','player')['status']=='NOT_FOUND'
  before=player['rows'];cache=next((f.root/'.runtime').glob('memory_v2_'+f.a.sha256_bytes(b'player')[:24]+'.json'));cache.write_text('{broken');assert f.a.memory_search(f.root,'player','KEY-NEED',scene_id=f.sid)['rows']==before;cache.unlink();assert f.a.memory_search(f.root,'player','KEY-NEED',scene_id=f.sid)['rows']==before
  oldpaths=h.read(f.root/'state.json')['engine_runtime']['memory_layers_v1']['cold_paths'];path=next(iter(oldpaths));full=f.a.memory_evidence(f.root,'legacy:'+path,'gm');assert full['status']=='COMPLETE';assert f.a.memory_evidence(f.root,'legacy:'+path,'npc:'+f.actor)['status']=='NOT_FOUND'
  return {'role_isolated_index_summary_pagination':True,'corrupt_deleted_cache_fallback':True,'legacy_redirect_payload_hash_verified':True,'source_preserved':True}
 case('layered_memory_source_permissions_and_cache_rebuild',memory_setup)
 def machine_experience():
  before=f.a.prepare_turn(f.root,f.sid,f.actor,'player','KEY-NEED');assert before['facts'][0]['fact_id']!='MEM-2';events=[]
  for i in range(2):
   p=f.proposal('PROBE-P-'+str(i),basis_refs=['fact/'+f.sid+'/DOES-NOT-EXIST-'+str(i)])
   c,env,r=f.commit('experience_probe','OBS-'+str(i),viewer='player',scope='conversation',probe={'kind':'proposal_validation','input':p},valid_until='8363-12-11T00:00:00');assert r['status']=='SAVED'
  after=f.a.prepare_turn(f.root,f.sid,f.actor,'player','KEY-NEED');strategy=after['interaction_strategy'];assert 'known_basis_first' in strategy['hints'] and after['facts'][0]['fact_id']=='MEM-2';assert len(strategy['machine_evidence_events'])==2
  assert f.a._five_account_balances(h.read(f.root/'state.json'))==f.a._five_account_balances(old_world);assert h.sha(f.root/'tasks.json')==oldtasks
  p=f.proposal('DECISION-STRATEGY');f.commit('story_turn',p['turn_id'],proposal=p);decision=f.a.turn_report(f.root,p['turn_id'])['decision_record'];assert decision['strategy']['policy_version']==f.a.EXPERIENCE_V2_POLICY
  evidence={'schema':'FIXED_STRATEGY_EVAL_V1','synthetic':True,'initial_context_fact_ids':[r['fact_id'] for r in before['facts']],'after_fact_ids':[r['fact_id'] for r in after['facts']],'retrieval_recall_at_1_before':0,'retrieval_recall_at_1_after':1,'proposals_automatically_retried':0,'strategy':strategy,'actual_observations':f.a.experience_v2(f.root)['records'],'decision':decision,'model_quality':'NOT_RUN','limitation':'deterministic ranking fixture, not model accuracy or conversational intelligence'};(out/'fixed_strategy_eval.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
  # An actual accepted validation is a counterexample, disabling the failure run.
  p=f.proposal('ACCEPTED-P');f.commit('experience_probe','OBS-SUCCESS',viewer='player',scope='conversation',probe={'kind':'proposal_validation','input':p},valid_until='8363-12-11T00:00:00');assert not f.a.ObservedExperienceService.strategy(f.root,'player','conversation')['hints']
  return {'two_actual_unique_failed_validations_required':True,'bounded_rank_change_recall_at_1':'0 -> 1 on synthetic fixture','actual_success_resets_failure_run':True,'no_mechanical_change':True,'model_quality':'NOT_RUN'}
 case('observed_experience_threshold_effect_counterexample_and_decision',machine_experience)
 def explicit_preferences():
  c,env,r=f.commit('experience_control','PREFERENCE-1',viewer='player',scope='conversation',instruction_ref='fixture:stage1-acceptance',valid_until='8363-12-11T00:00:00',control={'op':'preference','feedback':'合成用户明确反馈：优先查看KEY-NEED，并放慢节奏。','preference':{'topic':'KEY-NEED','pace':'slow'}});view=f.a.experience_v2(f.root);assert any(x['op']=='preference' and x['feedback'] for x in view['records']);assert f.a.ObservedExperienceService.strategy(f.root,'player','conversation')['preferred_pace']=='slow'
  f.commit('experience_control','REVOKE-PREFERENCE',viewer='player',scope='conversation',instruction_ref='fixture:stage1-acceptance',valid_until='8363-12-11T00:00:00',control={'op':'revoke','entry_id':'PREFERENCE-1','reason':'合成显式撤销。'});assert f.a.ObservedExperienceService.strategy(f.root,'player','conversation')['preferred_topic'] is None
  f.commit('experience_control','DISABLE-MACHINE',viewer='player',scope='conversation',instruction_ref='fixture:stage1-acceptance',valid_until='8363-12-11T00:00:00',control={'op':'disable'});assert not f.a.ObservedExperienceService.strategy(f.root,'player','conversation')['machine_enabled']
  p=f.proposal('OFF-UNSUPPORTED',effects=[{'kind':'arbitrary_code','code':'change_money'}]);assert f.a.validate_proposal(f.root,p)['status']=='UNSUPPORTED'
  c=f.command('experience_control','NPC-TEXT-NOT-USER',viewer='player',scope='conversation',instruction_ref='NPC:dialogue',valid_until='8363-12-11T00:00:00',control={'op':'enable'});f.reject_unchanged(c,'USER_EVIDENCE')
  c=f.command('experience_probe','SELF-REPORT',viewer='player',scope='conversation',valid_until='8363-12-11T00:00:00',probe={'kind':'caller_reports_success','input':{'success':True}});f.reject_unchanged(c,'UNSUPPORTED')
  return {'original_feedback_kept':True,'explicit_revoke':True,'scoped_disable_still_safe':True,'NPC_text_not_user_feedback':True,'caller_self_assessed_success_refused':True}
 case('explicit_preference_revocation_and_policy_off_safety',explicit_preferences)
 def matrix_cli():
  matrix=f.a.rule_coverage(f.root);registered=set(h.read(f.root/'rules.json')['rule_registry']['rules']);assert len(registered)==202 and registered<={r['rule_id'] for r in matrix['rows']};assert matrix['counts']['semantic_only']>170
  for row in matrix['rows']:
   if row.get('entry') and row['entry']!='_s4_content_rules':assert callable(getattr(f.a,row['entry']))
  cp=subprocess.run([sys.executable,str(source/'engine.py'),'servicecontracts','--base',str(source)],capture_output=True,text=True,env=dict(os.environ,VOYAGER_ROOT=str(source)));assert cp.returncode==0 and json.loads(cp.stdout)==a.service_contracts()
  (out/'rule_coverage.json').write_text(json.dumps(matrix,ensure_ascii=False,indent=2));return {'all_202_registry_rules_classified':True,'not_promoted_to_executable_by_label':True,'CLI_real':True}
 case('version_bound_coverage_matrix_and_real_cli',matrix_cli)
 return 1 if any(r['status']=='FAIL' for r in rows) else 0
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);n=p.parse_args();raise SystemExit(run(n.source,n.output))
