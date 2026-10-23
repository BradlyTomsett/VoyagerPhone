# V14.59 forward fixture; original V14.58 suite retained.
#!/usr/bin/env python3
"""SYNTHETIC-only batch2 regression; formal authority is read-only."""
from pathlib import Path
import sys,os,json,copy,importlib.util,subprocess,time,traceback,hashlib,argparse
sys.dont_write_bytecode=True
P=Path
p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--parent',type=P,required=True);p.add_argument('--output',type=P,required=True);n=p.parse_args();source=n.source.resolve();parent=n.parent.resolve();out=n.output.resolve();out.mkdir(parents=True,exist_ok=False)
def load(path,name):
 ns={'__file__':str(path),'__name__':name};exec(compile(path.read_bytes(),str(path),'exec'),ns);return type('API',(),ns)
h=load(source/'development/tests/stage1_v1453.py','helper');a=h.load_api(source,'new');old=h.load_api(parent,'old');rows=[]
def case(name,fn):
 t=time.perf_counter()
 try:v={'name':name,'status':'PASS','detail':fn()}
 except Exception as ex:v={'name':name,'status':'FAIL','error':str(ex),'trace':traceback.format_exc()}
 v['seconds']=time.perf_counter()-t;rows.append(v);(out/'results.json').write_text(json.dumps({'status':'PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL','engine_sha256':h.sha(source/'engine.py'),'model_generation':'NOT_RUN','tests':rows},ensure_ascii=False,indent=2));print(v['status'],name,v.get('error',''),flush=True)
class Fixture:
 def __init__(self,name):self.root=h.clone(source,out/name);self.a=h.load_api(self.root,'fixture_'+name);self.actor='PER-HAWK-MALEN-01';self.sid='SYNTHETIC-'+name.upper();self.version=80
 def commit(self,kind,cid,**fields):
  c=h.command(self.a,self.root,kind,cid,**fields);env=h.envelope(self.a,self.root,c);env['limits']['uses']=1000;env['valid_until']='8363-12-11T12:00:00';self.version=max(self.version,int(h.read(self.root/'manifest.json')['save_version'].split('.')[1]))+1;return c,env,self.a.host_intent_command(self.root,env,'V14.'+str(self.version))
 def setup(self):
  actions=[{'type':'scene_open','scene_id':self.sid,'task_id':None,'family':'conversation','title':'SYNTHETIC ONLY','location_ref':'LOC-FREEPORT-XILU9','participants':[self.actor],'presence_mode':'remote','visible_to':['player','npc:'+self.actor]},{'type':'fact_append','scene_id':self.sid,'fact_id':'F-OPEN','subject_id':self.actor,'predicate':'statement','value':'固定合成事实。','epistemic':'rumor','source_category':'npc_statement'}]
  actions += [{'type':'knowledge_disclose','scene_id':self.sid,'fact_id':'F-OPEN','viewer_id':v,'channel':'heard','basis_event_id':'$current_transaction'} for v in ['player','npc:'+self.actor]];actions += [{'type':'scene_phase','scene_id':self.sid,'phase':'open'}];self.commit('story_setup','SETUP',actions=actions)
 def proposal(self,cid,viewer='player'):
  ctx=self.a.prepare_turn(self.root,self.sid,self.actor,viewer)
  return {'schema':self.a.STORY_TURN_SCHEMA,'turn_id':cid,'base_identity':ctx['base_identity'],'scene_id':self.sid,'actor_id':self.actor,'viewer':viewer,'player_intent':'固定合成对白','intent_tags':['conversation'],'basis_refs':['fact/'+self.sid+'/F-OPEN'],'segments':[{'mode':'dialogue','speaker_id':self.actor,'text':'核对事实，等待选择。','basis_refs':['fact/'+self.sid+'/F-OPEN'],'receipt_refs':[]}],'effects':[],'updates':[],'consequences':[],'claims':[],'public_reason':'SYNTHETIC no mechanical effects','candidates':['等待']}
def conservation():
 for name in ('state.json','tasks.json','rules.json','catalog.json','guard.py'):assert h.sha(source/name)==h.sha(parent/name)
 m,e,r=a.read_history_raw(source/'events.jsonl');om,oe,orr=old.read_history_raw(parent/'events.jsonl');assert r[:-1]==orr and e[:-1]==oe and e[-1]['changes']==[] and e[-1]['zero_time'];return {'four_JSON_and_Guard_byte_exact':True,'old_raw_events':len(orr)}
case('conservation',conservation)
f=Fixture('round');f.setup()
def ownership_growth():
 with a.SnapshotContext(source):
  frozen=a.read_json_view(source/'state.json');assert a.read_json_view(source/'state.json') is frozen
  mutable=a.read_json(source/'state.json');mutable['engine_runtime']['BAD']=True;assert 'BAD' not in frozen['engine_runtime'];h.reject(lambda:frozen['engine_runtime'].update(BAD=True),'IMMUTABLE')
 result=[];state=f.a.read_json(f.root/'state.json');rt=state['engine_runtime']['story_runtime_v1'];template=copy.deepcopy(state['engine_runtime']['scene_registry_v1']['records'][f.sid])
 for scenes,per_scene in [(1,50),(4,250),(8,500)]:
  state=copy.deepcopy(state);rt=state['engine_runtime']['story_runtime_v1'];rt['facts']={};rt['learning_events']=[];records={}
  rt['legacy_viewer_bindings']={'observer:OLD':{'viewer_id':'npc:'+f.actor}}
  for j in range(scenes):
   sid='SYN-'+str(j);rec=copy.deepcopy(template);rec.update(scene_id=sid,facts={},disclosures=[]);records[sid]=rec
   for i in range(per_scene):
    fid='F-'+str(i);rt['facts'][sid+'/'+fid]={'scene_id':sid,'fact_id':fid,'subject_id':f.actor,'predicate':'statement','value':'合成'+str(i),'epistemic':'rumor','valid_from':state['game_time'],'source_event_ids':['SYNTHETIC-EVENT'],'supersedes_fact_id':'F-'+str(i-1) if i%7==0 and i else None,'confidence_basis':'private','source_category':'npc_statement'}
    for v in ('player','npc:'+f.actor):
     if i%3 or v=='player':rt['learning_events'].append({'scene_id':sid,'fact_id':fid,'viewer_id':v,'learned_at':state['game_time'],'channel':'heard','basis_event_id':'SYNTHETIC-EVENT','record_event_id':'SYNTHETIC-EVENT'})
  state['engine_runtime']['scene_registry_v1']['records']=records;viewers=['player','npc:'+f.actor,'observer:OLD','gm'];expected={(s,v):old._knowledge_rows(state,s,v) for s in records for v in viewers}
  with a.SnapshotContext(source) as ctx:
   frozen=a._stage2_freeze(state);actual={(s,v):a._knowledge_rows(frozen,s,v) for s in records for v in viewers};assert actual==expected;assert ctx.metrics['knowledge_index_builds']==1
  result.append({'scenes':scenes,'facts':scenes*per_scene,'learning':len(rt['learning_events']),'viewers':len(viewers),'exact_equal':True})
 return result
case('immutable_ownership_growth_and_unknown_correction',ownership_growth)
def host():
 host=load(source/'development/host_session.py','host');ss=host.HostSession(f.root,'SYNTHETIC',authorize=lambda e:e['evidence_ref']=='fixture:stage1-acceptance');ctx=ss.prepare(scene_id=f.sid,actor_id=f.actor);proposal=f.proposal('ROUND');proposal['base_identity']=ctx['base_identity'];cmd=h.command(f.a,f.root,'story_turn','ROUND',proposal=proposal);env=h.envelope(f.a,f.root,cmd)
 assert host.HostSession(f.root,'DENIED').submit(env,'V14.90')['status']=='NEEDS_AUTHORIZATION';result=ss.submit(env,'V14.90');assert result['status']=='SAVED' and result['report']==f.a.turn_report(f.root,'ROUND');retry=ss.submit(env,'V14.91');assert retry['receipt']==result['receipt'];assert ss.metrics['engine_loads']==1
 changed=copy.deepcopy(env);changed['command']['proposal']['public_reason']='different';h.reject(lambda:ss.submit(changed,'V14.91'),'DIFFERENT_PAYLOAD')
 assert host.HostSession(source,'OTHER').prepare()['status']=='NO_OPEN_SCENE';prior=ss.root;ss.root=source;h.reject(ss.prepare,'IMMUTABLE');ss.root=prior
 for key in ('VOYAGER_DEVELOPER_MODE','VOYAGER_DIAGNOSTIC_CONTEXT'):os.environ.pop(key,None)
 try:
  npc=host.HostSession(f.root,'NPC',viewer='npc:'+f.actor,authorize=lambda e:True,authorize_viewer=lambda r,s,v:r==f.root and v=='npc:'+f.actor);ctx=npc.prepare(scene_id=f.sid,actor_id=f.actor);assert ctx['viewer']=='npc:'+f.actor and 'five_balances' not in ctx
  assert host.HostSession(f.root,'UNTRUSTED',viewer='npc:'+f.actor).prepare()['status']=='NEEDS_AUTHORIZATION'
 finally:os.environ.update(VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm')
 return {'backend_requests':2,'engine_loads':1,'same_ID_original_receipt':True,'viewer_and_root_isolated':True,'ChatGPT_tool_wiring':'NOT_CONNECTED'}
case('host_two_calls_roles_and_retry',host)
def memory():
 b=f.a;r=f.root;first=b.memory_search(r,scene_id=f.sid);assert b.memory_search(r,scene_id=f.sid)['cache_hit'];f.commit('account_transfer','UNRELATED',source_account='covert',destination_account='fleet',currency='grey',amount='1.23',reason='SYNTHETIC')
 second=b.memory_search(r,scene_id=f.sid);assert second['cache_hit'] and second['rows']==first['rows'] and second['base_identity']!=first['base_identity']
 caches=list((r/'.runtime').glob('memory_v2_*.json'));assert caches;caches[0].write_text('broken');assert b.memory_search(r,scene_id=f.sid)['rows']==first['rows'];caches[0].unlink();assert b.memory_search(r,scene_id=f.sid)['rows']==first['rows']
 return {'unrelated_balance_reuses_content':True,'identity_current':True,'bad_cache_rebuilds':True}
case('memory_dependencies_and_cache_faults',memory)
def experience():
 b=f.a;r=f.root
 f.commit('experience_control','DISABLE',viewer='player',scope='conversation',instruction_ref='fixture:stage1-acceptance',valid_until='8363-12-10T17:20:30',control={'op':'disable'})
 assert b.experience_v2(r)['scope_enabled']['conversation'] is False
 with b.SnapshotContext(r):b.ensure_source_ready(r);b.experience_v2(r)
 f.commit('account_transfer','XP-TAIL',source_account='covert',destination_account='fleet',currency='grey',amount='1.23',reason='SYNTHETIC')
 with b.SnapshotContext(r) as ctx:
  b.ensure_source_ready(r);before=ctx.metrics.get('history_decodes',0);b.experience_v2(r);assert ctx.metrics['experience_prefix_hits'] and ctx.metrics['experience_events_examined']<10;assert ctx.metrics.get('history_decodes',0)==before;count=ctx.metrics['experience_events_examined']
 b.turn_session('start',until='8363-12-10T17:21:00',version='V14.95',scope='SYNTHETIC expiry');assert h.read(r/'state.json')['game_time']=='8363-12-10T17:21:00';assert b.experience_v2(r)['scope_enabled']['conversation'] is True
 return {'tail_events':count,'no_extra_full_decode_on_proven_prefix':True,'actual_clock_expiry':True}
case('experience_prefix_and_actual_time_expiry',experience)
def pool():
 b=f.a;r=f.root;objects=list((r/'.runtime/development_objects').glob('*'));assert objects and any(p.stat().st_nlink>1 for p in objects);assert all(not p.is_symlink() and not p.stat().st_mode&0o222 for p in objects)
 rel='development/README.md';raw=(r/rel).read_bytes();digest=b.sha256_bytes(raw);obj=r/'.runtime/development_objects'/digest;snapshots=list((r/'.runtime/snapshots').glob('*/'+rel));assert snapshots and obj.is_file();assert all((r/rel).stat().st_ino!=p.stat().st_ino for p in snapshots)
 (r/rel).write_bytes(raw+b'\nSYNTHETIC in-place modification');assert obj.read_bytes()==raw and all(p.read_bytes()==raw for p in snapshots);b._native_durable_replace_bytes(r/rel,raw)
 original=os.link
 def unsupported(src,dst,*args,**kwargs):
  if P(src).parent.name=='development_objects':raise OSError(95,'SYNTHETIC no link')
  return original(src,dst,*args,**kwargs)
 os.link=unsupported
 try:_,_,result=f.commit('account_transfer','FALLBACK',source_account='covert',destination_account='fleet',currency='grey',amount='1.23',reason='SYNTHETIC')
 finally:os.link=original
 assert result['status']=='SAVED';g=b._repair_guard_module(r);assert g.validate_dir(r)[1]==[]
 return {'pool_objects':len(objects),'independent_working_inodes':True,'inplace_working_change_does_not_pollute_snapshots':True,'unsupported_link_full_copy_fallback':True,'Guard_original_format':True}
case('immutable_development_pool_and_fallback',pool)
def export():
 b=f.a;r=f.root;sid=h.read(r/'manifest.json')['parent_save_set_id'];os.environ['VOYAGER_DELIVERY_ROOT']=str(out/'exports');packet=b.export_save_set(r,sid);assert packet['status']=='READY' and packet['cold_boot']=='PASS',packet;return packet
case('historical_snapshot_export_independent_cold_boot',export)
raise SystemExit(0 if all(r['status']=='PASS' for r in rows) else 1)
