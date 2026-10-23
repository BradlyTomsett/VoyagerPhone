# Step18 portable current-candidate regression. Adapted from test_batch_c.py; runtime code is unchanged.
#!/usr/bin/env python3
"""Batch C acceptance; all story/learning/commit effects are isolated fixtures."""
import sys
sys.dont_write_bytecode=True
import copy,contextlib,hashlib,importlib.util,io,json,os,pathlib,shutil,time,traceback
P=pathlib.Path;BASE=P(os.environ.get('VOYAGER_TEST_SOURCE',str(P(__file__).resolve().parents[2]))).resolve();OUT=P(os.environ.get('VOYAGER_BATCH_C_OUTPUT','batch_c/audit/regression')).resolve();OUT.mkdir(parents=True,exist_ok=True);ROWS=[]
os.environ.update(VOYAGER_ROOT=str(BASE),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm');os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None)
def load(r,name='engine'):
 os.environ['VOYAGER_ROOT']=str(r);s=importlib.util.spec_from_file_location(name+str(time.time_ns()),r/'engine.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a);return a
a=load(BASE)
def save():
 (OUT/'results.json').write_text(json.dumps({'schema':'BATCH_C_ACCEPTANCE_V1','status':'FAIL' if any(x['status']=='FAIL' for x in ROWS) else 'PASS','engine_sha256':hashlib.sha256((BASE/'engine.py').read_bytes()).hexdigest(),'source_save_set_id':json.loads((BASE/'manifest.json').read_text())['save_set_id'],'tests':ROWS},ensure_ascii=False,indent=2)+'\n')
def test(name,fn):
 st=time.monotonic()
 try:r=fn();ROWS.append({'name':name,'status':'PASS','detail':r,'seconds':round(time.monotonic()-st,3)});print('PASS',name,flush=True)
 except Exception as ex:ROWS.append({'name':name,'status':'FAIL','error':str(ex),'trace':traceback.format_exc(),'seconds':round(time.monotonic()-st,3)});print('FAIL',name,repr(ex),flush=True)
 save()
def reject(fn,token=None):
 try:fn()
 except Exception as ex:
  if token:assert token in str(ex),(token,str(ex))
  return
 raise AssertionError('expected rejection')
def clone(name):
 r=OUT/name;shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));return r

def protected():
 from common import protected as verify
 return verify(BASE)
test('every_gameplay_fact_and_old_event_byte_preserved',protected)

def original_visibility():
 sid='XILU9-WHITESLEEP-0317-83631202';packet=a.scene_query_packet(BASE,sid);facts=packet['value']['facts'];assert all(f['epistemic']=='confirmed' for f in packet['value']['confirmed_facts']);assert any(f['epistemic']=='hypothesis' for f in facts);assert 'world_truth' not in str(packet)
 out=a.player_output_policy({'secret':'GM-LEAK','world_truth':'GM-LEAK','value':None,'items':[{'visibility':'gm','value':'GM-LEAK'},{'name':'public','gm_private':'GM-LEAK'}]});assert 'GM-LEAK' not in str(out) and out['value'] is None
 assert 'migration_evidence' not in str(a.asset_query_packet(BASE));reject(lambda:a.price_query_packet(BASE,{'source_ref':'state:gm_private'}),'PRIVATE_REFERENCE')
 return 'legacy known hypothesis remains uncertain; null preserved; private metadata filtered across dedicated outputs'
test('historical_disclosures_and_central_visibility_filter',original_visibility)

r=clone('stories');b=load(r,'stories');version=int(json.loads((BASE/"manifest.json").read_text())["save_version"].split(".")[-1])+1;commits=[]
def send(cid,actions):
 global version
 m=b.read_json(r/'manifest.json');now=b.read_json(r/'state.json')['game_time'];c={'schema':b.DOMAIN_COMMAND_SCHEMA,'command_id':cid,'base_save_set_id':m['save_set_id'],'kind':'story_transaction','actions':actions,'authorization':'host_intent','authorization_ref':'HOST:'+cid,'actor_id':'PER-COMMANDER-01'}
 e={'schema':'HOST_COMMAND_INTENT_V1','command':c,'subject_id':c['actor_id'],'parent_save_set_id':m['save_set_id'],'instruction_text':'ISOLATED TEST WORLD: execute exactly these bounded story actions; no funds, travel, game time or fleet changes.','evidence_ref':'test-host:'+cid,'decision':'approved','targets':b._domain_command_targets(c),'valid_from':now,'valid_until':now,'limits':b._domain_authorization_cost(c)}
 result=b.host_intent_command(r,e,'V14.'+str(version));assert result['status']=='SAVED',result;version+=1;commits.append(result)
 before={n:b.sha256_file(r/n) for n in b.COMPONENT_FILES};again=b.host_intent_command(r,e,'V14.'+str(version));assert again['status']=='ALREADY_APPLIED' and before=={n:b.sha256_file(r/n) for n in b.COMPONENT_FILES}
 return result
families=['rescue','ordinary_life','discovery'];taskids=['TSK-MIN-OPERATIONS','TSK-YUHUO-OPERATIONS','TSK-CALDER-INDUSTRIES-302'];SIDS=['DEMO-RESCUE','DEMO-DAILY','DEMO-DISCOVERY'];PEOPLE=['NPC-DEMO-ANA','NPC-DEMO-BELA','NPC-DEMO-CYRA']
def setup():
 actions=[]
 for i,(sid,eid,tid,family) in enumerate(zip(SIDS,PEOPLE,taskids,families)):
  actions+=[{'type':'entity_register','entity_id':eid,'name':['安娜·维斯','贝拉·凯恩','希拉·诺尔'][i],'role':['求救的普通旅人','社区值班者','谨慎的研究访客'][i]}, {'type':'scene_create','scene_id':sid,'task_id':tid,'family':family,'title':['隔门呼声','门厅的纸条','旧观测窗'][i],'participants':[eid],'location_label':['测试加压走廊','测试社区门厅','测试观测室'][i]}]
  for fid,value,epistemic in [('KNOWN',['希望先确认家人安全','想让交接班平稳结束','想弄清旧观察记录的来历'][i],'confirmed'),('RUMOR','据说侧门暂时不能通行','rumor'),('HIDDEN','打算先与私人联系人核对信息','confirmed')]:
   actions.append({'type':'fact_append','scene_id':sid,'fact_id':fid,'subject_id':eid,'predicate':'goal' if fid=='KNOWN' else 'statement','value':value,'epistemic':epistemic,'source_category':'creative_setting'})
  for viewer in ('player','npc:'+eid):actions.append({'type':'knowledge_disclose','scene_id':sid,'fact_id':'KNOWN','viewer_id':viewer,'channel':'heard','basis_event_id':'$current_transaction'})
  actions+=[{'type':'knowledge_disclose','scene_id':sid,'fact_id':'RUMOR','viewer_id':'player','channel':'reported','basis_event_id':'$current_transaction'},{'type':'scene_phase','scene_id':sid,'phase':'open'}]
 result=send('SETUP',actions);state=b.read_json(r/'state.json');cur=b._story_current_summary(state);assert cur['status']=='FOCUS_REQUIRED' and len(cur['candidates'])==3
 assert b.knowledge_packet(r,SIDS[0],'npc:'+PEOPLE[1])['facts']==[]
 for sid in SIDS:
  player=b.scene_query_packet(r,sid);assert 'HIDDEN' not in json.dumps(player);assert len(player['value']['uncertain_facts'])==1;context=b.narrative_context_packet(r,sid);assert context['status']=='COMPLETE' and 'HIDDEN' not in json.dumps(context)
 (OUT/'setup_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return {'parallel_scenes':3,'duplicate_command_replay_no_effect':True,'no_automatic_focus':True,'different_npc_knows_nothing':True}
test('authorized_parallel_scenes_entities_and_separate_knowledge',setup)

DRAFTS=[
 '走廊灯光被薄雾揉开，安娜把手按在门边，想先确认家人平安。你停下听她说明后，她放慢语速，把担心的缘由讲清；等你作答，她愿意继续交流。',
 '门厅的纸张被风口轻轻掀起，贝拉希望交接班平稳结束。你选择先听值班者的困难，她把原本攥着的纸条摊开；这次回应让她愿意把误会留在谈话里解决。',
 '旧观测窗映出柔暗的反光，希拉想核对一段观察记录的来历。你请她区分亲眼所见与猜测，她认真做了区分；接下来的讨论因此有了可以追问的线索。']
def proposal(sid,i,ref):
 now=b.read_json(r/'state.json')['game_time'];return {'schema':'NARRATIVE_PROPOSAL_V1','base_save_set_id':b.read_json(r/'manifest.json')['save_set_id'],'scene_id':sid,'audience':'player','intent_ref':ref,'basis_refs':['fact/'+sid+'/KNOWN'],'draft_text':DRAFTS[i],'new_facts':[{'fact_id':'REACTION','subject_id':PEOPLE[i],'predicate':'social_reaction','value':'愿意继续耐心说明','epistemic':'confirmed','source_category':'creative_setting','confidence_basis':'explicit authorized reaction to the freeform player choice','known_by':['player','npc:'+PEOPLE[i]]}],'claims':[{'speaker_id':PEOPLE[i],'text':'我仍有些担心，但愿意先说清楚。','epistemic':'hypothesis','basis_fact_ids':['KNOWN']}],'action_requests':[{'command_id':'SETUP','effect_sha256':b._repair_digest(commits[0]['effect'])}],'consequence_requests':[{'consequence_id':'CONSEQ-'+str(i),'subject_id':PEOPLE[i],'effect_type':'pending_reply','cause_event_id':commits[0]['event_id'],'not_before':now,'not_after':'8363-12-02T23:00:00','visible_to':['player'],'text':'对方愿意在谈话中补充说明'}],'required_unknowns':['未核验的传言仍待现场观察'],'narrative_tags':[families[i],'noncombat','freeform_response']}
def negative_proposals():
 p=proposal(SIDS[0],0,'HOST:DEMO');bad=copy.deepcopy(p);bad['basis_refs']=['fact/'+SIDS[0]+'/HIDDEN'];reject(lambda:b.validate_narrative_proposal(r,bad),'HIDDEN')
 for text in ('已支付10金币','已经击毁敌舰','获得100金币'):
  bad=copy.deepcopy(p);bad['draft_text']=text;reject(lambda:b.validate_narrative_proposal(r,bad),'HARD_OUTCOME')
 bad=copy.deepcopy(p);bad['new_facts'][0]['predicate']='gold_balance';reject(lambda:b.validate_narrative_proposal(r,bad),'MECHANICAL')
 bad=copy.deepcopy(p);bad['claims'][0]['basis_fact_ids']=['HIDDEN'];reject(lambda:b.validate_narrative_proposal(r,bad),'UNKNOWABLE')
 bad=copy.deepcopy(p);bad['action_requests'][0]['effect_sha256']='0'*64;reject(lambda:b.validate_narrative_proposal(r,bad),'NOT_VERIFIED')
 bad=copy.deepcopy(p);bad['consequence_requests'][0]['not_before']='8363-12-02T10:00:00';reject(lambda:b.validate_narrative_proposal(r,bad),'TIME_WINDOW')
 os.environ['VOYAGER_DIRECTOR']='0'
 try:reject(lambda:b.validate_narrative_proposal(r,p),'DISABLED')
 finally:os.environ.pop('VOYAGER_DIRECTOR')
 assert b.readiness_report(r)['status']=='READY_WITH_LIMITATIONS'
 return {'hidden_fact_hard_cash_combat_mechanical_fact_unknown_npc_forged_effect_and_time_rejected':True,'director_switch_does_not_disable_engine':True}
test('narrative_authority_knowledge_and_hard_effect_negative_matrix',negative_proposals)

def narratives():
 actions=[{'type':'decision_open','scene_id':SIDS[0],'decision_id':'FREE-CHOICE','prompt':'你准备如何回应？'},{'type':'decision_resolve','scene_id':SIDS[0],'decision_id':'FREE-CHOICE','player_action':'我先听她完整说完，再询问哪些是亲眼所见。'}]
 for i,sid in enumerate(SIDS):actions.append({'type':'narrative_commit','scene_id':sid,'proposal_id':'PROP-'+str(i),'proposal':proposal(sid,i,'HOST:DEMO')})
 before=b.read_json(r/'state.json');send('DEMO',actions);after=b.read_json(r/'state.json');assert before['inventories']==after['inventories'] and before['engine_runtime']['finance_runtime']==after['engine_runtime']['finance_runtime'] and before['engine_runtime']['long_horizon']==after['engine_runtime']['long_horizon']
 samples=[]
 for i,sid in enumerate(SIDS):
  row=b.narrative_report_packet(r,'PROP-'+str(i));assert row['verified_results'] and row['claims'][0]['epistemic']=='hypothesis';assert 'HIDDEN' not in json.dumps(row);samples.append({'family':families[i],'hard_constraints':'PASS','soft_review':{'environment':True,'character_goal':True,'player_response':True,'causal_followup':True,'forced_options':False,'combat_required':False},'draft_text':DRAFTS[i]})
 (OUT/'narrative_quality_samples.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2)+'\n');return {'end_to_end_families':families,'freeform_choice':True,'hard_effects_reused_not_executed':True,'soft_quality_is_separate_fixture_review':True}
test('three_story_families_freeform_choice_causal_consequences',narratives)

def correction_experience():
 actions=[{'type':'fact_correct','scene_id':SIDS[0],'fact_id':'CORRECTION','subject_id':PEOPLE[0],'predicate':'appearance','value':'现有路牌指向检修出口','epistemic':'confirmed','source_category':'direct_observation','supersedes_fact_id':'RUMOR'}, {'type':'knowledge_disclose','scene_id':SIDS[0],'fact_id':'CORRECTION','viewer_id':'player','channel':'observed','basis_event_id':'$current_transaction'}, {'type':'scene_focus','scene_id':SIDS[0]}, {'type':'narrative_rewrite','scene_id':SIDS[0],'proposal_id':'PROP-0','draft_text':'灯影落在门边。安娜听见你的耐心回应，愿意把担忧讲得更清楚，等候你继续询问。'}]
 for i,sid in enumerate(SIDS):actions.append({'type':'consequence_resolve','scene_id':sid,'consequence_id':'CONSEQ-'+str(i),'status':'delivered'})
 entries=[{'entry_id':'LEARN-ALIAS','object_type':'intent_alias','value':{'alias':'手头钱','canonical_topic':'当前金币余额'},'instruction_ref':'test-host:LEARN'}, {'entry_id':'LEARN-PREF','object_type':'explicit_preference','value':{'genre':'ordinary_life','pace':'slow'},'instruction_ref':'test-host:LEARN'}, {'entry_id':'LEARN-PATTERN','object_type':'pattern_feedback','value':{'tag':'rescue','rating':'repetitive'},'instruction_ref':'test-host:LEARN'}]
 actions += [{'type':'experience_record','entry':e} for e in entries];before=b.read_json(r/'state.json');send('LEARN',actions);after=b.read_json(r/'state.json');assert before['engine_runtime']['finance_runtime']==after['engine_runtime']['finance_runtime'] and before['engine_runtime']['seed_anchor']==after['engine_runtime']['seed_anchor']
 known=b.knowledge_packet(r,SIDS[0]);old=next(f for f in known['facts'] if f['fact_id']=='RUMOR');assert old['epistemic']=='rumor' and old['superseded_by']==['CORRECTION'];assert b._story_current_summary(after)['scene_id']==SIDS[0]
 exact=b.visible_query_packet(r,'手头钱');assert exact['status']=='COMPLETE';view=b.experience_packet(r);strategy=b._experience_strategy(view,'rescue');assert strategy['preferred_pace']=='slow' and strategy['suggested_families'][0]=='ordinary_life' and 'rescue' in strategy['avoid_repeating_tags']
 (r/'.runtime/experience_v1.json').unlink();assert b.experience_packet(r)['records']==view['records']
 os.environ['VOYAGER_EXPERIENCE']='0'
 try:assert b.experience_packet(r)['records']==[] and b.visible_query_packet(r,'手头钱')['status']=='VISIBILITY_UNCLASSIFIED_QUERY'
 finally:os.environ.pop('VOYAGER_EXPERIENCE')
 return {'old_rumor_retained_correction_learned':True,'rewrite_no_cash_rng_effect':True,'alias_before':'unclassified','alias_after':'exact_current_balance','repetition_feedback_changes_context_rank_not_randomness':True,'cache_deletion_and_switch':True}
test('knowledge_correction_story_rewrite_and_reversible_experience',correction_experience)

def close_and_negative():
 actions=[]
 for sid in SIDS:actions += [{'type':'scene_phase','scene_id':sid,'phase':'resolved'},{'type':'scene_phase','scene_id':sid,'phase':'closed'}]
 actions += [{'type':'experience_revoke','entry_id':eid,'reason':'explicit isolated test rollback'} for eid in ('LEARN-ALIAS','LEARN-PREF','LEARN-PATTERN')];send('CLOSE',actions);state=b.read_json(r/'state.json');assert b._story_current_summary(state)['status']=='NO_OPEN_SCENE' and b.experience_packet(r)['records']==[]
 before=copy.deepcopy(state)
 def direct(actions):
  payload={'kind':'story_transaction','command_id':'NEGATIVE','authorization_ref':'HOST:NEGATIVE','actions':actions};return b._story_actions_apply(r,copy.deepcopy(before),b.read_json(r/'tasks.json'),payload)
 reject(lambda:direct([{'type':'scene_phase','scene_id':SIDS[0],'phase':'open'}]),'TERMINAL')
 reject(lambda:direct([{'type':'knowledge_disclose','scene_id':SIDS[0],'fact_id':'HIDDEN','viewer_id':'player','channel':'reported','basis_event_id':commits[0]['event_id']}]),'HISTORICAL_DISCLOSURE')
 reject(lambda:direct([{'type':'entity_register','entity_id':'OTHER-ID','name':'安娜·维斯'}]),'NAME_EXISTS')
 reject(lambda:direct([{'type':'fact_append','scene_id':SIDS[1],'fact_id':'BAD','subject_id':PEOPLE[1],'predicate':'gold_balance','value':'free','epistemic':'confirmed','source_category':'creative_setting'}]),'TERMINAL')
 reject(lambda:direct([{'type':'scene_focus','scene_id':SIDS[0],'gold_delta':100}]),'SCHEMA')
 reject(lambda:direct([{'type':'consequence_resolve','scene_id':SIDS[0],'consequence_id':'CONSEQ-0','status':'delivered'}]),'NOT_PENDING')
 original=b.read_json(BASE/'state.json');assert state['summary']==original['summary'] and state['inventories']==original['inventories'] and state['shadow_fleet']==original['shadow_fleet'] and state['engine_runtime']['long_horizon']==original['engine_runtime']['long_horizon']
 report=b.run_checks(r,full=True);assert report['status']=='PASS',report['errors'];return {'closed_not_reopened':True,'history_disclosure_requires_real_evidence':True,'names_not_duplicated':True,'consequence_once_only':True,'experience_revoke_rebuildable':True,'all_original_mechanics_preserved':True,'fullcheck':'PASS'}
test('terminal_scenes_evidence_identity_and_revoke_protection',close_and_negative)

def reload_and_views():
 c=load(r,'reloaded');assert c.readiness_report(r)['status']=='READY_WITH_LIMITATIONS';assert c.narrative_report_packet(r,'PROP-0')['revisions']==1;os.environ['VOYAGER_ROOT']=str(r)
 spec=importlib.util.spec_from_file_location('dev',r/'development/devsrc/runtime.py');dev=importlib.util.module_from_spec(spec);spec.loader.exec_module(dev);d,_=dev.load(r/'engine.py');assert d.knowledge_packet(r,SIDS[0])==c.knowledge_packet(r,SIDS[0]);assert d.story_projection_packet(r)==c.story_projection_packet(r)
 for api in (c,d):
  out=io.StringIO()
  with contextlib.redirect_stdout(out):assert api.main(['sceneindex'])==0
  assert 'HIDDEN' not in out.getvalue()
 reject(lambda:c._phase2_domain_authorization(c.read_json(r/'state.json'),{'authorization':'host_intent'},False),'TRUSTED_BOUNDARY')
 cache=r/'.runtime/experience_v1.json';cache.write_text('{"fake":"world money"}');assert c.experience_packet(r)['records']==[]
 (OUT/'final_test_world_fullcheck.json').write_text(json.dumps(c.run_checks(r,full=True),ensure_ascii=False,indent=2)+'\n');return {'reload_character_and_consequence_continuity':True,'development_release_equal':True,'sceneindex_no_hidden_fact':True,'forged_authorization_rejected':True,'corrupt_learning_cache_rebuilt':True}
test('cold_reload_dev_release_views_and_authorization_boundary',reload_and_views)
raise SystemExit(1 if any(x['status']=='FAIL' for x in ROWS) else 0)
