#!/usr/bin/env python3
"""V14.66 forward fixture for native lived-world regressions. Synthetic copies only.
Historical V14.60 fixture prose is reused as data; no production NPC is advanced.
"""
import argparse,ast,copy,hashlib,importlib.util,json,pathlib,sys,time,traceback
from contextlib import nullcontext
sys.dont_write_bytecode=True
P=pathlib.Path
CRITERIA=['living_prose','voice_and_knowledge','sensory_grounding','player_agency']
def load(path,name):
 sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
def fixture_review(p):
 # Test-only deterministic stand-in for independent review, deliberately rejects
 # the demonstrated false promise. Production must use an actual independent AI.
 text=''.join(s['text'] for s in p['segments'])
 if '永远服从' in text or '全部积蓄' in text:return {'status':'FAIL','criteria':CRITERIA}
 return {'status':'PASS','criteria':CRITERIA,'reviewer':'SYNTHETIC_FIXTURE_ONLY'}
def run(source,out,groups=None):
 source=source.resolve();source_hashes={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file() and '.runtime' not in p.parts and '__pycache__' not in p.parts and p.name!='.game_engine.lock'};out=out.resolve();assert not out.exists() and source not in out.parents;out.mkdir(parents=True)
 h=load(source/'development/tests/stage1_v1453.py','h1461')
 tree=ast.parse((source/'development/tests/living_world_v1460.py').read_text());run_node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run');cls=next(n for n in run_node.body if isinstance(n,ast.ClassDef) and n.name=='Fixture')
 ns={'h':h,'source':source,'out':out,'copy':copy};exec(compile(ast.Module(body=[cls],type_ignores=[]),'historical_fixture','exec'),ns);Base=ns['Fixture']
 class Fixture(Base):
  def commit(self,kind,cid,**fields):
   if cid=='SETUP-LIVED':fields['actions'].append({'type':'life_control','entity_id':self.actor,'operation':'take','reason':'合成测试明确玩家控制者，不通过公共actor推断'})
   p=fields.get('proposal');rewrite=next((a for a in fields.get('actions',[]) if a['type']=='turn_rewrite'),None)
   if rewrite:
    p=copy.deepcopy(self.a._s3_runtime(h.read(self.root/'state.json'))['turns'][rewrite['turn_id']]['proposal']);p.update(segments=rewrite['segments'],experience=rewrite['experience'])
   with self.a.narrative_review_context(p,fixture_review) if p and p.get('viewer')=='player' else nullcontext():return super().commit(kind,cid,**fields)
  def proposal(self,cid,returning=False):
   s=h.read(self.root/'state.json');mode=self.a._lw_visit(s,self.sid,self.actor)['mode'];p=super().proposal(cid,mode!='first');p['elapsed_seconds']=1
   for v in p['experience']['voices']:v['profile_revision']=self.a._lw_runtime(s)['profiles'][v['entity_id']]['revision']
   return p
 f=Fixture();a=f.a;rows=[]
 def case(name,fn):
  if groups and name not in groups and name!='setup_explicit_control_and_complete_profiles':return
  started=time.perf_counter()
  try:detail=fn();row={'name':name,'status':'PASS','detail':detail}
  except BaseException as ex:row={'name':name,'status':'FAIL','error':str(ex),'traceback':traceback.format_exc()}
  row['seconds']=round(time.perf_counter()-started,3);rows.append(row);(out/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');print(json.dumps(row,ensure_ascii=False),flush=True)
 def state():return h.read(f.root/'state.json')
 def rt():return a._lw_runtime(state())
 def frozen():return {n:h.sha(f.root/n) for n in ('state.json','tasks.json','events.jsonl','manifest.json')}
 def expect(fn,part):
  before=frozen();error=h.reject(fn,part);assert frozen()==before;return error
 def act(cid,actions):return f.commit('story_setup',cid,actions=actions)
 def rec(eid):return {k:copy.deepcopy(rt()['profiles'][eid][k]) for k in ('important','background','voice','public_fields','voice_visible_to','daily_routine','basis_refs','source_kind')}
 def position(eid,loc):return {'type':'life_position','entity_id':eid,'location_ref':loc,'basis_refs':['synthetic:position'],'reason':'合成测试明确位置'}
 def memory(operation):return {'type':'life_memory','entity_id':f.other,'scene_id':f.sid,'fact_id':'F-OPEN','operation':operation,'reason':'合成测试保留历史学习证据'}
 def schedule(nid,eid,seconds,category,changes,**extra):return {'type':'life_schedule','node_id':nid,'entity_id':eid,'due_at':(a.parse_iso(state()['game_time'])+a.dt.timedelta(seconds=seconds)).isoformat(),'category':category,'changes':changes,'expected':{k:rt()['profiles'][eid]['background'][k] for k in changes},'status_after':None,'reason':'合成测试独立人生节点','visible_to':[],**extra}
 case('setup_explicit_control_and_complete_profiles',lambda:(f.setup() and {'control':rt()['controls'][f.actor]['active']}))
 def boot():
  b=a.cold_start_packet(source);raw=json.dumps(b,ensure_ascii=False,separators=(',',':'),default=str).encode();assert b['context_bytes']==len(raw);assert b['budget_exceeded']==(len(raw)>b['context_budget_bytes']);assert not b['budget_exceeded']
  return {'actual_bytes':len(raw),'budget':b['context_budget_bytes'],'honest_exceeded':b['budget_exceeded']}
 case('11_boot_actual_size_and_budget',boot)
 def review_gate():
  p=f.proposal('REVIEW');
  schema=h.read(source/'development/schemas/story_turn_v3.json');assert set(schema['required'])<=set(p);assert schema['properties']['schema']['const']==p['schema'];assert schema['properties']['experience']['properties']['frame']['properties']['perception']['type']=='object'
  bad_duration=copy.deepcopy(p);bad_duration['elapsed_seconds']=0;assert 'DURATION_REQUIRED' in a.validate_proposal(f.root,bad_duration)['code']
  assert a.validate_proposal(f.root,p)['status']=='NEEDS_NARRATIVE_REVIEW'
  bad=copy.deepcopy(p);bad['experience']['anchors']={k:{'segment':0,'quote':'系统状态正常'} for k in bad['experience']['anchors']};bad['segments'][0]['text']='系统状态正常'*30
  assert 'ANCHORS_MUST_BE_DISTINCT' in a.validate_proposal(f.root,bad)['code']
  bad=copy.deepcopy(p);bad['segments'].append({'mode':'dialogue','speaker_id':f.actor,'text':'我把全部积蓄给你，永远服从。','basis_refs':[],'receipt_refs':[]});bad['experience']['voices'].append({'segment':2,'entity_id':f.actor,'profile_revision':rt()['profiles'][f.actor]['revision'],'emotion':'neutral','disclosure':'partial'});bad['experience']['player_speech']='intent_faithful'
  expect(lambda:f.commit('story_turn','REVIEW',proposal=bad),'NARRATIVE_REVIEW')
  with a.narrative_review_context(p,fixture_review):
   changed=copy.deepcopy(p);changed['player_intent']+='篡改';assert 'NARRATIVE_REVIEW' in a.validate_proposal(f.root,changed)['code']
  return {'self_flags_rejected':True,'status_report_rejected':True,'unrequested_promise_rejected_by_independent_review':True,'hash_bound_review':True}
 case('15_distinct_evidence_and_independent_review_gate',review_gate)
 def interiors():
  act('INNER',[{'type':'life_inner','entity_id':e,'body':'口渴','emotion':'不安','cognition':'秘密内心-'+e,'impulse':'先等一等','basis_refs':['synthetic:inner']} for e in (f.actor,f.other)])
  hostmod=load(source/'development/host_session.py','host1461');host=hostmod.HostSession(f.root,'privacy','player')
  packet=host.prepare(scene_id=f.sid,actor_id=f.other,budget_bytes=65536);assert '秘密内心-'+f.other not in json.dumps(packet,ensure_ascii=False)
  packet=host.prepare(scene_id=f.sid,actor_id=f.actor,budget_bytes=65536);l=packet['lived_experience'];assert l['interior']['cognition']=='秘密内心-'+f.actor
  me=next(x for x in l['people'] if x['entity_id']==f.actor);assert me['background']['education']==rt()['profiles'][f.actor]['background']['education'];assert l['visit']['frame']['perception']['actor_id']==f.actor;assert '熟悉码头日常，但不了解隐藏动机' not in json.dumps(l,ensure_ascii=False)
  return {'other_private_inner_hidden':True,'controlled_self_education_and_inner_available':True,'actor_specific_perception':True}
 case('04_14_private_interior_and_actor_cognition',interiors)
 def clock_and_retry():
  p=f.proposal('FIRST-CLOCK');p['elapsed_seconds']=10;before=state()['game_time'];c,e,r=f.commit('story_turn',p['turn_id'],proposal=p);after=state()['game_time'];assert a.parse_iso(after)-a.parse_iso(before)==a.dt.timedelta(seconds=10)
  hashes=frozen();assert a.host_intent_command(f.root,e,'V14.999')['status']=='ALREADY_APPLIED';assert frozen()==hashes
  f.first=p;clock=a.turn_report(f.root,p['turn_id'])['clock'];assert clock['elapsed_seconds']==10 and 'executed' not in clock
  return {'single_atomic_clock_seconds':10,'retry_no_time_or_effect_replay':True}
 case('13_duration_commits_atomically_and_retry_is_idempotent',clock_and_retry)
 def forgotten():
  token=a._s3_view_scope.set('npc:'+f.other)
  try:
   assert a.memory_search(f.root,'npc:'+f.other,scene_id=f.sid)['total']==1
   act('FORGET',[memory('forget')]);assert a.memory_search(f.root,'npc:'+f.other,scene_id=f.sid)['total']==0
   old=copy.deepcopy(rt()['profiles'][f.other]);r=rec(f.other);r['voice']['catchphrases']='合成：先放一放再谈。'
   act('PROFILE-VOICE',[{'type':'life_profile','entity_id':f.other,'expected_revision':old['revision'],'record':r}]);new=rt()['profiles'][f.other]
   for k in ('forgotten','location_ref','life_status'):assert old[k]==new[k],k
   assert a.memory_search(f.root,'npc:'+f.other,scene_id=f.sid)['total']==0
   act('RECALL',[memory('recall')]);assert a.memory_search(f.root,'npc:'+f.other,scene_id=f.sid)['total']==1
  finally:a._s3_view_scope.reset(token)
  return {'warm_cache_forget_and_recall':True,'profile_voice_edit_preserves_dynamic_fields':True}
 case('02_03_memory_cache_and_profile_update_after_forgetting',forgotten)
 def rewrite():
  p=f.proposal('HISTORICAL-FACT');p['segments'][1]['basis_refs']=['fact/'+f.sid+'/F-OPEN'];f.commit('story_turn',p['turn_id'],proposal=p)
  act('FORGET-REWRITE',[memory('forget')]);before=state()['game_time'];count=rt()['visits'][f.actor+'@'+f.loc]['count']
  act('REWRITE-OLD',[{'type':'turn_rewrite','turn_id':p['turn_id'],'viewer':'player','segments':p['segments'],'experience':p['experience']}]);assert state()['game_time']==before and rt()['visits'][f.actor+'@'+f.loc]['count']==count
  act('RECALL-AGAIN',[memory('recall')]);return {'historical_speech_survives_current_forgetting':True,'no_time_or_visit_replay':True}
 case('08_rewrite_uses_original_speaker_knowledge',rewrite)
 def correction():
  old=rt()['profiles'][f.other];r=rec(f.other);r['background']['past']='更正后的既往背景';r['source_kind']='confirmed_evidence';r['basis_refs']=['nonexistent:invented']
  expect(lambda:act('FAKE-PAST',[{'type':'life_profile','entity_id':f.other,'expected_revision':old['revision'],'record':r}]),'COMMITTED_EVIDENCE_REQUIRED')
  evidence=json.dumps({'profile_field':'past','value':r['background']['past']},ensure_ascii=False)
  act('REAL-EVIDENCE',[{'type':'fact_append','scene_id':f.sid,'fact_id':'F-CORRECTION','subject_id':f.other,'predicate':'statement','value':evidence,'epistemic':'confirmed','source_category':'direct_observation'}]);r['basis_refs']=['fact/'+f.sid+'/F-CORRECTION']
  act('VALID-CORRECTION',[{'type':'life_profile','entity_id':f.other,'expected_revision':old['revision'],'record':r}]);assert rt()['profiles'][f.other]['corrections'][-1]['after']['past']==r['background']['past']
  return {'fake_reference_denied':True,'matching_committed_evidence_accepted_and_audited':True}
 case('07_real_evidence_required_for_biography_correction',correction)
 def legacy():
  for kind,eid in [('story_action','PER-LEGACY-A'),('story_transaction','PER-LEGACY-B')]:
   action={'type':'entity_register','entity_id':eid,'name':'合成人物'+eid[-1],'aliases':[],'role':'普通居民'};f.commit(kind,'REGISTER-'+eid,**({'action':action} if kind=='story_action' else {'actions':[action]}));assert eid in rt()['profiles'] and eid in a._s3_runtime(state())['npcs'];act('POSITION-'+eid,[position(eid,f.loc)])
  return {'both_legacy_registration_paths_initialized_and_positionable':True}
 case('06_legacy_registration_initializes_all_layers',legacy)
 def visits():
  sid='LIVED-SAME-PLACE';act('NEW-SAME-PLACE',[{'type':'scene_open','scene_id':sid,'task_id':None,'family':'conversation','title':'同地点新场景','location_ref':f.loc,'participants':[f.actor],'presence_mode':'present','visible_to':['player']},{'type':'scene_phase','scene_id':sid,'phase':'open'}]);assert a._lw_visit(state(),sid,f.actor)['mode']=='continuing'
  loc=next(e for e,x in state()['entity_registry']['entities'].items() if e!=f.loc and x['entity_type']=='location')
  act('LEAVE-RETURN',[position(f.actor,loc),position(f.actor,f.loc)]);assert a._lw_visit(state(),f.sid,f.actor)['mode']=='return'
  p=f.proposal('RETURN-CLOCK');f.commit('story_turn',p['turn_id'],proposal=p);assert rt()['visits'][f.actor+'@'+f.loc]['count']==2
  f.alt=loc;return {'new_scene_same_entry_continuing':True,'leave_and_return_same_scene_counted':True}
 case('10_physical_visit_epochs_instead_of_scene_ids',visits)
 def absence():
  act('OTHER-LEAVES',[position(f.other,f.alt)]);expect(lambda:a.prepare_turn(f.root,f.sid,f.other,'player',budget_bytes=65536),'LOCATION_NEEDS_INFORMATION')
  p=f.proposal('ABSENT-SPEAKER');assert 'LOCATION_NEEDS_INFORMATION' in a.validate_proposal(f.root,p)['code']
  p['segments']=p['segments'][:1];p['segments'][0]['text']='你在窗边停了一步，诺娃留下的空杯靠着窗框，杯沿还挂着水渍。通风机仍在头顶低鸣。你抬手碰了碰扶手，冰凉的触感让肩头绷紧的那一点劲慢慢松开；走廊另一端的工人侧了侧身，给你让出一条道。';p['experience']['anchors']={k:{'segment':0,'quote':q} for k,q in {'action':'你在窗边停了一步','environment':'通风机仍在头顶低鸣','detail':'杯沿还挂着水渍','response':'走廊另一端的工人侧了侧身','inner':'肩头绷紧的那一点劲慢慢松开'}.items()};p['experience']['senses']={'auditory':{'segment':0,'quote':'通风机仍在头顶低鸣'}};p['experience']['voices']=[];p['experience']['dialogue_mode']='alone';f.commit('story_turn',p['turn_id'],proposal=p)
  act('OTHER-RETURNS',[position(f.other,f.loc)]);return {'moved_actor_and_speaker_denied':True,'historical_participant_not_forced_to_speak':True}
 case('05_revalidate_live_presence_each_turn',absence)
 def control():
  # Public NPC queries and role release do not turn a person permanently into a player.
  assert not a._lw_controlled(state(),f.other)
  act('TAKE-OTHER',[{'type':'life_control','entity_id':f.other,'operation':'take','reason':'临时玩家角色'}]);assert a._lw_controlled(state(),f.other)
  act('RELEASE-OTHER',[{'type':'life_control','entity_id':f.other,'operation':'release','reason':'交回自主生活'}]);node=schedule('RETIRE',f.other,5,'retirement',{'occupation':'已退休','current_life':'在家休息'})
  act('PLAN-RETIRE',[node]);p=f.proposal('RETIRE-CLOCK');p['elapsed_seconds']=6;f.commit('story_turn',p['turn_id'],proposal=p);profile=rt()['profiles'][f.other];assert profile['background']['occupation']=='已退休' and profile['daily_routine']==[];assert '轮班' not in a._lw_routine(profile,a.parse_iso(state()['game_time']))
  return {'explicit_take_and_release':True,'NPC_autonomy_resumes':True,'retirement_clears_old_shift':True}
 case('09_12_retirement_routine_and_revocable_player_control',control)
 def death():
  eid='PER-MORTAL-TEST';r=rec(f.other);r['background']['name']='合成普通居民';r['voice']['catchphrases']='合成：我在这边。';r['source_kind']='authored_consistent_extension';r['basis_refs']=['state:entity_registry.entities.'+eid]
  act('MORTAL',[{'type':'entity_register','entity_id':eid,'name':'合成普通居民','aliases':[],'role':'普通居民'},{'type':'life_profile','entity_id':eid,'expected_revision':0,'record':r},position(eid,f.loc),{'type':'fact_append','scene_id':f.sid,'fact_id':'F-MORTAL','subject_id':eid,'predicate':'statement','value':'普通居民过去在附近工作。','epistemic':'confirmed','source_category':'direct_observation'}]);act('DEATH-NODE',[schedule('DEATH',eid,3,'death',{'current_life':'已死亡，保留历史'},status_after='dead')]);p=f.proposal('DEATH-CLOCK');p['elapsed_seconds']=4;f.commit('story_turn',p['turn_id'],proposal=p)
  assert state()['entity_registry']['entities'][eid]['status']=='dead';assert a._knowledge_facts(state(),f.sid)['F-MORTAL']['subject_id']==eid;assert a._story_integrity(state(),h.read(f.root/'tasks.json'))['status']=='PASS';return {'death_commits_and_keeps_history':True}
 case('01_death_preserves_historical_identity_and_clock_commit',death)
 def rollback():
  # V14.65 ordinary existing NPCs use autonomous background reviews. A NEW
  # fully authored synthetic person is outside that standing policy, so their
  # explicit review is a real AI barrier, rather than an obsolete fixture gate.
  eid='PER-REVIEW-TEST';record=rec(f.other);record['background']['name']='合成复核居民';record['voice']['catchphrases']='合成复核：先让我想想。';record['basis_refs']=['state:entity_registry.entities.'+eid]
  act('REVIEW-PERSON',[{'type':'entity_register','entity_id':eid,'name':'合成复核居民','aliases':[],'role':'普通居民'},{'type':'life_profile','entity_id':eid,'expected_revision':0,'record':record}])
  at=(a.parse_iso(state()['game_time'])+a.dt.timedelta(seconds=2)).isoformat();act('EARLY-REVIEW',[{'type':'life_review','entity_id':eid,'next_review_at':at,'reason':'合成测试实际AI复核门'}]);p=f.proposal('BLOCKED-CLOCK');p['elapsed_seconds']=3;p['effects']=[{'kind':'account_transfer','source_account':'covert','destination_account':'fleet','currency':'grey','amount':'1.00','reason':'SYNTHETIC rollback test'}]
  expect(lambda:f.commit('story_turn',p['turn_id'],proposal=p),'STORY_TIME_NEEDS_AI');assert p['turn_id'] not in a._s3_runtime(state())['turns'];return {'mechanical_money_narrative_visit_and_clock_rollback_together':True,'barrier_not_covered_by_ordinary_background_policy':True}
 case('13_barrier_rolls_back_whole_combined_transaction',rollback)
 def parity_and_full():
  release=a.prepare_turn(f.root,f.sid,f.actor,'player','看一眼',budget_bytes=65536);d=h.load_api(f.root,'dev1461',True);assert d.prepare_turn(f.root,f.sid,f.actor,'player','看一眼',budget_bytes=65536)==release
  full=a.run_checks(f.root,full=True);(out/'full.json').write_text(json.dumps(full,ensure_ascii=False,indent=2));assert full['status']=='PASS',full['errors'];assert all(h.sha(source/n)==v for n,v in source_hashes.items());facts=a._history_epoch_runtime_facts(f.root);assert rt()['policy_version']==2;assert state()['engine_runtime']['scaling']['history_epoch']['compression_recommended']==facts['compression_recommended'];return {'active_scene_module_release_parity':True,'full_passed':full['passed_count'],'history_threshold_flag_matches_final_audit_bytes':True,'source_files_unchanged':len(source_hashes)}
 case('module_loader_active_scene_and_full_integrity',parity_and_full)
 failed=sum(r['status']!='PASS' for r in rows);result={'status':'FAIL' if failed else 'PASS','passed':len(rows)-failed,'failed':failed,'rows':rows};(out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);p.add_argument('--groups',default='');n=p.parse_args();r=run(n.source,n.output,set(filter(None,n.groups.split(','))));print(r['status'],r['passed'],r['failed']);raise SystemExit(bool(r['failed']))
