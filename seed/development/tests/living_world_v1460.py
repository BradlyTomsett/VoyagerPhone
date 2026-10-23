#!/usr/bin/env python3
"""Meaningful lived-world acceptance on isolated SYNTHETIC fixtures only."""
import argparse,copy,hashlib,importlib.util,json,os,pathlib,shutil,sys,time,traceback
sys.dont_write_bytecode=True
P=pathlib.Path
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def run(source,out):
 source=source.resolve();out=out.resolve();out.mkdir(parents=True,exist_ok=False)
 h=load(source/'development/tests/stage1_v1453.py','lw_helpers');a=h.load_api(source,'lw_acceptance');results=[]
 before={n:h.sha(source/n) for n in ['state.json','tasks.json','rules.json','catalog.json','events.jsonl','manifest.json']}
 def case(name,fn):
  started=time.perf_counter()
  try:row={'name':name,'status':'PASS','detail':fn()}
  except BaseException as ex:row={'name':name,'status':'FAIL','error':str(ex),'traceback':traceback.format_exc()}
  row['seconds']=round(time.perf_counter()-started,3);results.append(row)
  (out/'results.json').write_text(json.dumps({'status':'PASS' if all(r['status']=='PASS' for r in results) else 'FAIL','engine_sha256':h.sha(source/'engine.py'),'generation_quality':'fixed prose reviewed by assertions; no live model or unattended process tested','tests':results},ensure_ascii=False,indent=2)+'\n');print(row['status'],name,row.get('error',''),flush=True)
 def migration():
  s=h.read(source/'state.json');rt=a._lw_runtime(s);assert len(rt['profiles'])==16 and not rt['life_nodes'] and not rt['visits'] and not rt['experience_receipts'];assert s['game_time']=='8363-12-10T17:20:00' and s['voyage_day']==691
  assert all(p['revision']==0 and p['background']['age'] is None for p in rt['profiles'].values())
  boot=a.cold_start_packet(source);assert boot['lived_experience_policy']['enabled']
  assert a.prepare_turn(source)['status']=='NO_OPEN_SCENE';d=h.load_api(source,'lw_development',True);assert d.living_world_packet(source)==a.living_world_packet(source);assert d.story_schema_packet()==a.story_schema_packet()
  initial=a.parse_iso(rt['initial_review_at']);assert a._next_ai_monitor_time({'active_tasks':[]},a.parse_iso(s['game_time']),initial,state=s)['kind']=='npc_life_profile'
  return {'unencountered_NPCs_get_global_initialization':True,'legacy_identity_profiles':16,'no_fabricated_age_or_history':True,'current_game_time_preserved':True,'development_release_parity':True,'cold_boot_policy':True}
 case('zero_time_migration_cold_boot_and_source_parity',migration)
 class Fixture:
  def __init__(self):
   self.root=h.clone(source,out/'SYNTHETIC');self.a=h.load_api(self.root,'lw_fixture');self.actor='PER-HAWK-MALEN-01';self.other='PER-NOVA-01';self.loc='LOC-FREEPORT-XILU9';self.sid='LIVED-SYNTHETIC';self.version=60
  def commit(self,kind,cid,**fields):
   c=h.command(self.a,self.root,kind,cid,**fields);e=h.envelope(self.a,self.root,c);e['limits']['uses']=100;self.version=max(self.version,int(h.read(self.root/'manifest.json')['save_version'].split('.')[1]))+1
   r=self.a.host_intent_command(self.root,e,'V14.'+str(self.version));assert r['status']=='SAVED',r;return c,e,r
  def setup(self):
   acts=[];state=h.read(self.root/'state.json')
   for eid in (self.actor,self.other):
    bg={k:'合成测试：普通码头居民；此字段有明确日常内容。' for k in self.a.LIVING_BACKGROUND};bg.update(name=state['entity_registry']['entities'][eid]['canonical_name'],age='34岁（合成夹具）',education='地方基础学校，熟悉装卸工作',occupation='码头检修工',family='与家人合租，不涉及真实存档经历',memories='记得当前同事和已明确学到的消息')
    voice={k:'合成测试：朴素口语、短句，不使用生僻理论术语。' for k in self.a.LIVING_VOICE};voice.update(catchphrases=('偶尔说先核一下，不强制重复' if eid==self.actor else '偶尔说先瞧瞧，不强制重复'),dialect='轻微码头用语',angry='短促少修饰',tired='含糊省略',relaxed='随意带玩笑',nervous='拘谨，短暂停顿')
    record={'important':True,'background':bg,'voice':voice,'public_fields':['name','occupation'],'voice_visible_to':['player'],'daily_routine':[{'start_minute':480,'end_minute':1080,'activity':'码头轮班检修'},{'start_minute':1320,'end_minute':360,'activity':'回住所睡觉'}],'basis_refs':['state:entity_registry.entities.'+eid],'source_kind':'authored_consistent_extension'}
    acts += [{'type':'life_profile','entity_id':eid,'expected_revision':0,'record':record},{'type':'life_position','entity_id':eid,'location_ref':self.loc,'basis_refs':['synthetic:explicit_fixture'],'reason':'合成测试初始在场位置'}]
   acts.append({'type':'life_place','location_ref':self.loc,'expected_revision':0,'senses':{'visual':'狭长的灰色接待廊，灯罩积尘','auditory':'通风机低鸣','olfactory':'过滤空气中淡淡的清洁剂味','tactile':'扶手冰凉，地板轻振','atmosphere':'换班前的倦意与谨慎'},'conditions':{'facilities':'有重力与通风，照明正常','weather':'密封室内，无直接室外天气感知','society':'普通换班，未处于警戒','perception':'熟悉码头日常，但不了解隐藏动机'},'visible_to':['player','npc:'+self.actor,'npc:'+self.other],'basis_refs':['synthetic:explicit_fixture']})
   acts += [{'type':'scene_open','scene_id':self.sid,'task_id':None,'family':'conversation','title':'SYNTHETIC 生活化验收','location_ref':self.loc,'participants':[self.actor,self.other],'presence_mode':'present','visible_to':['player','npc:'+self.actor,'npc:'+self.other]},{'type':'fact_append','scene_id':self.sid,'fact_id':'F-OPEN','subject_id':self.actor,'predicate':'statement','value':'合成夹具的接待廊交谈。','epistemic':'confirmed','source_category':'direct_observation'}]
   for v in ('player','npc:'+self.actor,'npc:'+self.other):acts.append({'type':'knowledge_disclose','scene_id':self.sid,'fact_id':'F-OPEN','viewer_id':v,'channel':'observed','basis_event_id':'$current_transaction'})
   acts += [{'type':'scene_phase','scene_id':self.sid,'phase':'open'},{'type':'scene_focus_v2','scene_id':self.sid}]
   return self.commit('story_setup','SETUP-LIVED',actions=acts)
  def proposal(self,cid,returning=False):
   packet=self.a.prepare_turn(self.root,self.sid,self.actor,'player','看看接待廊，听对方说话。',budget_bytes=65536);v=packet['lived_experience']['visit'];assert packet.get('budget_exceeded') is not True
   first='你推开接待廊的门，门轴在掌下轻轻一震。灰灯把积尘的墙角照得发白，扶手贴着手心，凉意顺着指节停了一瞬。通风机在头顶低鸣，过滤空气里有一点清洁剂的味道。窄廊里挤着换班的人，旧工作服的袖口擦过你身边；有人把水杯往窗台挪了挪，给后来的人腾出地方。诺娃抬眼看你，手里的小螺丝刀却没有放下。你原本急着开口，看到她发红的指节，喉咙里的话又缓了半拍。'
   repeat='你在窗边停了一步，诺娃把杯子从右手换到左手，灯下能看见杯沿新沾的水渍。通风机忽然低了一个调子。你听着，肩头绷紧的那一点劲慢慢松开，她却仍在等你先把问题说清楚。'
   text=repeat if returning else first
   seg=[{'mode':'description','speaker_id':None,'text':text,'basis_refs':[],'receipt_refs':[]},{'mode':'dialogue','speaker_id':self.other,'text':'先坐会儿……你要问哪一段？我手头这点活还没收。','basis_refs':[],'receipt_refs':[]}]
   def anchor(q):return {'segment':0,'quote':q}
   if returning:anchors={'action':anchor('你在窗边停了一步'),'environment':anchor('通风机忽然低了一个调子'),'detail':anchor('杯沿新沾的水渍'),'response':anchor('她却仍在等你先把问题说清楚'),'inner':anchor('肩头绷紧的那一点劲慢慢松开')};senses={'auditory':anchor('通风机忽然低了一个调子')}
   else:anchors={'action':anchor('你推开接待廊的门'),'environment':anchor('灰灯把积尘的墙角照得发白'),'detail':anchor('给后来的人腾出地方'),'response':anchor('诺娃抬眼看你'),'inner':anchor('喉咙里的话又缓了半拍')};senses={'visual':anchor('灰灯把积尘的墙角照得发白'),'auditory':anchor('通风机在头顶低鸣'),'olfactory':anchor('清洁剂的味道'),'tactile':anchor('扶手贴着手心'),'atmosphere':anchor('窄廊里挤着换班的人')}
   p={'schema':self.a.STORY_TURN_SCHEMA,'turn_id':cid,'base_identity':packet['base_identity'],'scene_id':self.sid,'actor_id':self.actor,'viewer':'player','player_intent':'看看接待廊，听对方说话。','intent_tags':['conversation'],'basis_refs':['fact/'+self.sid+'/F-OPEN'],'segments':seg,'effects':[],'updates':[],'consequences':[],'claims':[],'public_reason':'场景与对白依据合成夹具，玩家未作承诺。','candidates':['询问','等待'],'experience':{'schema':'LIVED_EXPERIENCE_V1','location_ref':self.loc,'visit_mode':v['mode'],'frame':v['frame'],'anchors':anchors,'senses':senses,'dialogue_mode':'exchange','voices':[{'segment':1,'entity_id':self.other,'profile_revision':1,'emotion':'tired','disclosure':'partial'}],'agency':{'decisions_left_to_player':True,'feelings_are_suggestions':True},'player_speech':'none'}}
   return p
 f=Fixture()
 def setup():
  f.setup();p=f.proposal('UNCOMMITTED');assert f.a.validate_proposal(f.root,p)['status']=='NEEDS_AUTHORIZATION';s=h.read(f.root/'state.json');assert not f.a._lw_runtime(s)['visits'];c1=f.a.prepare_turn(f.root,f.sid,f.actor,'player','看一眼',budget_bytes=1024);assert c1['budget_exceeded'] and c1['generation_blocked'];assert '家人合租' not in json.dumps(c1,ensure_ascii=False)
  return {'full_profiles_and_voice_required':True,'queries_do_not_count_as_visits':True,'private_family_not_in_player_context':True,'undersized_context_blocks_generation':True}
 case('actual_setup_private_biographies_and_query_idempotency',setup)
 def rejects():
  p=f.proposal('BAD');bad=copy.deepcopy(p);bad.pop('experience');assert f.a.validate_proposal(f.root,bad)['status']=='INVALID'
  bad=copy.deepcopy(p);bad['experience']['senses'].pop('olfactory');assert 'FIVE_SENSES' in f.a.validate_proposal(f.root,bad)['code']
  bad=copy.deepcopy(p);bad['experience']['anchors']['inner']['quote']='这不是正文中的话';assert 'ANCHOR' in f.a.validate_proposal(f.root,bad)['code']
  bad=copy.deepcopy(p);bad['segments'][0]['text']+='你决定答应了她的要求。';assert 'FORCED_PLAYER' in f.a.validate_proposal(f.root,bad)['code']
  bad=copy.deepcopy(p);bad['experience']['voices'][0]['disclosure']='all';assert 'INFORMATION_DUMP' in f.a.validate_proposal(f.root,bad)['code']
  bad=copy.deepcopy(p);bad['segments'][1]['speaker_id']=f.actor;bad['experience']['voices'][0]['entity_id']=f.actor;assert 'SPEECH_NOT_AUTHORIZED' in f.a.validate_proposal(f.root,bad)['code']
  bad=copy.deepcopy(p);bad['experience']['frame']['weather']='擅改天气';assert 'FRAME_STALE' in f.a.validate_proposal(f.root,bad)['code']
  return {'status_report_missing_experience_rejected':True,'sensory_omission_rejected':True,'fake_checklist_anchor_rejected':True,'forced_choice_rejected':True,'unauthorized_player_dialogue_rejected':True,'information_dump_and_stale_environment_rejected':True}
 case('reject_unlived_reports_missing_senses_and_forced_choices',rejects)
 def turns():
  p=f.proposal('LIVED-FIRST');c,e,r=f.commit('story_turn',p['turn_id'],proposal=p);s=h.read(f.root/'state.json');rt=f.a._lw_runtime(s);assert rt['visits'][f.actor+'@'+f.loc]['count']==1
  assert f.a.host_intent_command(f.root,e,'V14.99')['status']=='ALREADY_APPLIED';assert f.a._lw_runtime(h.read(f.root/'state.json'))['visits'][f.actor+'@'+f.loc]['count']==1
  repeat=f.proposal('LIVED-CONTINUE',True);assert repeat['experience']['visit_mode']=='continuing';f.commit('story_turn',repeat['turn_id'],proposal=repeat)
  assert f.a._lw_runtime(h.read(f.root/'state.json'))['visits'][f.actor+'@'+f.loc]['count']==1
  assert len(f.a._lw_runtime(h.read(f.root/'state.json'))['portrayal_snapshots'])==2
  report=f.a.turn_report(f.root,p['turn_id']);assert '清洁剂的味道' in report['prose'];assert report['experience_review']['structural']=='PASS'
  (out/'SYNTHETIC_first_and_continuing_prose.json').write_text(json.dumps({'first':report,'continuing':f.a.turn_report(f.root,repeat['turn_id'])},ensure_ascii=False,indent=2))
  f.commit('story_setup','REWRITE-LIVED',actions=[{'type':'turn_rewrite','turn_id':p['turn_id'],'viewer':'player','segments':p['segments'],'experience':p['experience']}]);assert f.a._lw_runtime(h.read(f.root/'state.json'))['visits'][f.actor+'@'+f.loc]['count']==1
  return {'atomic_first_and_continuing':True,'same_retry_one_visit':True,'rewrite_no_replayed_effect_or_visit':True,'readable_prose_report':True}
 case('first_visit_continuing_retry_rewrite_and_prose_report',turns)
 def memory():
  f.commit('story_setup','FORGET',actions=[{'type':'life_memory','entity_id':f.other,'scene_id':f.sid,'fact_id':'F-OPEN','operation':'forget','reason':'合成测试：记忆淡化，保留历史学习证据'}]);s=h.read(f.root/'state.json');assert 'F-OPEN' not in f.a._knowledge_known(s,f.sid,'npc:'+f.other);assert 'F-OPEN' in f.a._knowledge_known(s,f.sid,'npc:'+f.actor);assert 'F-OPEN' not in {r['fact_id'] for r in f.a.prepare_turn(f.root,f.sid,f.other,'npc:'+f.other,'尝试回忆',budget_bytes=65536)['facts']}
  f.commit('story_setup','RECALL',actions=[{'type':'life_memory','entity_id':f.other,'scene_id':f.sid,'fact_id':'F-OPEN','operation':'recall','reason':'合成测试：提醒后回想起来'}]);assert 'F-OPEN' in f.a._knowledge_known(h.read(f.root/'state.json'),f.sid,'npc:'+f.other)
  return {'forgetting_affects_actual_NPC_knowledge_selection':True,'other_person_memory_unchanged':True,'original_learning_evidence_retained':True,'recall_supported':True}
 case('actual_forgetting_and_recall_without_erasing_history',memory)
 def revisit():
  s=h.read(f.root/'state.json');rt=f.a._lw_runtime(s);rt['last_presence'][f.actor]={'scene_id':'OTHER-SCENE','location_ref':'OTHER-LOCATION'}
  v=f.a._lw_visit(s,f.sid,f.actor);assert v['mode']=='return' and v['prior_visits']==1
  rt['places'][f.loc]['conditions']['weather']='室内通道有雨水带入';rt['places'][f.loc]['revision']+=1;v=f.a._lw_visit(s,f.sid,f.actor);assert 'weather' in v['changed_fields']
  st=copy.deepcopy(s);rt2=f.a._lw_runtime(st);rt2['life_nodes']['OVERDUE']={'node_id':'OVERDUE','entity_id':f.other,'due_at':st['game_time'],'status':'pending','source_event_id':'synthetic:due'};assert f.a._lw_integrity(st,h.read(f.root/'tasks.json'))['status']=='FAIL'
  return {'new_scene_same_place_is_return_visit':True,'changed_weather_tracked':True,'due_boundary_cannot_be_committed_without_resolution':True}
 case('return_visits_track_changes_and_due_boundary_is_a_gate',revisit)
 def autonomy():
  s=h.read(f.root/'state.json');p=f.a._lw_runtime(s)['profiles'][f.other];due='8363-12-10T17:21:00'
  f.commit('story_setup','LIFE-PLAN',actions=[{'type':'life_schedule','node_id':'LIFE-JOB','entity_id':f.other,'due_at':due,'category':'work','changes':{'current_life':'换班后回家，与玩家行动无关'},'expected':{'current_life':p['background']['current_life']},'status_after':None,'reason':'合成测试：正常下班节点','visible_to':[],'location_after':'LOC-FREEPORT-XILU9-SEVENDOCK'},{'type':'scene_phase','scene_id':f.sid,'phase':'resolved'},{'type':'scene_phase','scene_id':f.sid,'phase':'closed'}])
  s=h.read(f.root/'state.json');q=f.a.deterministic_event_queue(s,h.read(f.root/'tasks.json'),f.a.parse_iso(s['game_time']),f.a.parse_iso(due));assert any(r.get('node_id')=='LIFE-JOB' for r in q)
  res=f.a.turn_session('start',until=due,version='V14.90',scope='SYNTHETIC waiting; NPC world continues');assert res['status']=='COMMITTED',res
  s=h.read(f.root/'state.json');p=f.a._lw_runtime(s)['profiles'][f.other];n=f.a._lw_runtime(s)['life_nodes']['LIFE-JOB'];assert n['status']=='delivered' and p['background']['current_life']=='换班后回家，与玩家行动无关';assert f.a._s3_runtime(s)['npcs'][f.other]['location_ref']=='LOC-FREEPORT-XILU9-SEVENDOCK'
  assert f.a._lw_routine(p,f.a.parse_iso('8363-12-10T23:00:00'))=='回住所睡觉'
  events=f.a.read_history_view(f.root/'events.jsonl')[1];assert sum(e.get('type')=='npc_autonomous_life' and e.get('node_id')=='LIFE-JOB' for e in events)==1
  future=f.a.parse_iso(p['next_review_at']);review_state=copy.deepcopy(s);review_state['engine_runtime']['living_world_v1']['profiles']={eid:p for eid,p in f.a._lw_runtime(s)['profiles'].items() if f.a._lw_complete(p)};barrier=f.a._next_ai_monitor_time({'active_tasks':[]},future,future,state=review_state);assert barrier['kind']=='npc_life_review'
  return {'real_shared_scheduler_committed_NPC_life':True,'closed_scene_did_not_cancel_NPC_life':True,'no_current_player_presence_needed':True,'exactly_once_history':True,'autonomous_position_used_by_presence_checks':True,'routine_at_night':True,'life_review_at_long_absence_frontier':True}
 case('world_continues_during_wait_and_after_scene_closure',autonomy)
 def faults():
  s=h.read(f.root/'state.json');rt=f.a._lw_runtime(s);before={n:h.sha(f.root/n) for n in ['state.json','tasks.json','events.jsonl','manifest.json']};p=rt['profiles'][f.actor]
  h.reject(lambda:f.commit('story_setup','PLAYER-AUTO',actions=[{'type':'life_schedule','node_id':'CONTROL-PLAYER','entity_id':f.actor,'due_at':'8363-12-10T17:22:00','category':'relationship','changes':{'relations':'擅自承诺结盟'},'expected':{'relations':p['background']['relations']},'status_after':None,'reason':'无效夹具','visible_to':[]}]),'CANNOT_CONTROL_PLAYER')
  assert before=={n:h.sha(f.root/n) for n in before}
  clone=copy.deepcopy(s);npc=f.other;p=rt['profiles'][npc];rt2=f.a._lw_runtime(clone);rt2['life_nodes']['CONFLICT']={'node_id':'CONFLICT','entity_id':npc,'due_at':s['game_time'],'status':'pending','changes':{'occupation':'另一份工作'},'expected':{'occupation':'已经过时的职业'},'status_after':None,'source_event_id':'SYNTHETIC-CONFLICT'}
  stage=h.clone(f.root,out/'resolver-synthetic');r=f.a._lw_resolve(stage,clone,h.read(f.root/'tasks.json'),{'source':'npc_life','node_id':'CONFLICT'},f.a.parse_iso(s['game_time']));assert r['outcome']=='superseded' and rt2['profiles'][npc]['background']['occupation']==p['background']['occupation']
  full=f.a.run_checks(f.root,full=True);(out/'fixture_fullcheck.json').write_text(json.dumps(full,ensure_ascii=False,indent=2));assert full['status']=='PASS',full['errors']
  return {'player_autonomy_denied':True,'failed_command_leaves_no_authority_write':True,'old_plan_cannot_overwrite_changed_life':True,'native_fullcheck_after_all_actions':'PASS'}
 case('rollback_player_agency_conflicting_plans_and_native_fullcheck',faults)
 def finance():
  before=f.a._five_account_balances(h.read(f.root/'state.json'));c,e,r=f.commit('account_transfer','LIVING-FINANCE-REGRESSION',source_account='covert',destination_account='fleet',currency='grey',amount='0.01',reason='SYNTHETIC exact financial regression')
  after=f.a._five_account_balances(h.read(f.root/'state.json'));assert int(after['covert_grey']['integer_units'])==int(before['covert_grey']['integer_units'])-100
  assert f.a.host_intent_command(f.root,e,'V14.99')['status']=='ALREADY_APPLIED';assert f.a._five_account_balances(h.read(f.root/'state.json'))==after
  return {'fixed_point_balance_correct':True,'same_retry_no_second_debit':True,'new_living_wrapper_preserves_existing_mechanics':True}
 case('existing_financial_command_and_idempotent_receipt_regression',finance)
 assert before=={n:h.sha(source/n) for n in before},'RELEASE_CHANGED_BY_TESTS'
 return all(r['status']=='PASS' for r in results)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);a=p.parse_args();raise SystemExit(0 if run(a.source,a.output) else 1)
