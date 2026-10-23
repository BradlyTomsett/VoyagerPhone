#!/usr/bin/env python3
"""Content binding, nonmutation, cache invalidation, visibility and split source QA.
All corruptions and write scenarios are isolated; supplied parent is read-only.
"""
import argparse,copy,hashlib,importlib.util,json,os,pathlib,shutil,sys,time,traceback
sys.dont_write_bytecode=True
P=pathlib.Path

def load(path,name):
 sp=importlib.util.spec_from_file_location(name,path);a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a);return a

def sha(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()

def run(parent,source,out):
 parent=parent.resolve();source=source.resolve();out=out.resolve();out.mkdir(parents=True,exist_ok=False)
 h=load(source/'development/tests/stage1_v1453.py','fast_helpers');a=h.load_api(source,'fast_release');old=h.load_api(parent,'fast_parent');rows=[]
 def case(name,fn):
  start=time.perf_counter()
  try:detail=fn();row={'name':name,'status':'PASS','detail':detail}
  except Exception as ex:row={'name':name,'status':'FAIL','error':str(ex),'traceback':traceback.format_exc()}
  row['seconds']=round(time.perf_counter()-start,4);rows.append(row)
  (out/'results.json').write_text(json.dumps({'status':'PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL','tests':rows},ensure_ascii=False,indent=2)+'\n');print(row['status'],name,row.get('error',''),flush=True)
 def require(value):
  assert value
  return True
 def conserved():
  assert all((parent/n).read_bytes()==(source/n).read_bytes() for n in ('state.json','tasks.json','rules.json','catalog.json','guard.py'))
  assert all(p.read_bytes()==(source/'archives'/p.name).read_bytes() for p in (parent/'archives').iterdir())
  _,pe,praw=old.read_history_raw(parent/'events.jsonl');_,ne,nraw=a.read_history_raw(source/'events.jsonl');assert nraw[:-1]==praw and ne[:-1]==pe and len(ne)==len(pe)+1
  return {'old_events':len(pe),'new_events':len(ne),'game_time':h.read(source/'state.json')['game_time'],'authority_and_archives_byte_exact':True}
 case('zero_time_byte_exact_conservation',conserved)
 def queries():
  before={n:sha(source/n) for n in a.COMPONENT_FILES}
  got=a.play_context_packet(source,player_intent='看看当前情况',until='8363-12-12T08:00:00')
  assert got['status']=='NO_OPEN_SCENE' and got['prepare']['base_identity']['save_set_id']==got['save_set_id']
  assert got['advance_plan']==a.routineplan_packet(source,'8363-12-12T08:00:00')
  baseline=old.business_query_packet(parent);actual=a.business_query_packet(source)
  baseline.pop('save_set_id');actual.pop('save_set_id');assert actual==baseline
  assert before=={n:sha(source/n) for n in before}
  assert got['context_bytes']==len(json.dumps(got,ensure_ascii=False,separators=(',',':'),default=str).encode()) and not got['budget_exceeded']
  return {'same_business_facts':True,'combined_snapshot_identity':True,'no_time_or_authority_write':True,'bytes':got['context_bytes']}
 case('one_read_context_parity_and_exact_budget',queries)
 def boundaries():
  with old.SnapshotContext(source) as o:layout=o.boundary_layout()
  with a.SnapshotContext(source) as n:assert layout==n.boundary_layout()
  x=old._stage2_dependencies(source);y=a._stage2_dependencies(source);assert x[1:]==y[1:]
  return {'legacy_layout_and_dependency_semantics_identical':True}
 case('boundary_and_dependency_equivalence',boundaries)
 def cache():
  with a._stage2_epoch_process_lock:a._stage2_epoch_process_cache.clear()
  stats=[]
  for i in range(2):
   with a.SnapshotContext(source) as snap:
    meta,events,raws=a.read_history_view(source/'events.jsonl');assert len(events)==2637
    try:events[0]['seq']=99
    except a.EngineError:pass
    else:raise AssertionError('MUTABLE_HISTORY_VIEW')
    stats.append(copy.deepcopy(snap.metrics))
  assert stats[0]['history_decodes']>0 and stats[1].get('history_decodes',0)==0 and stats[1]['epoch_process_hits']>0
  assert len(a._stage2_epoch_process_cache)<=a._STAGE2_EPOCH_PROCESS_ENTRIES
  return {'first_decodes':stats[0]['history_decodes'],'second_decodes':stats[1].get('history_decodes',0),'second_process_hits':stats[1]['epoch_process_hits'],'immutable':True}
 case('verified_epoch_reuse_without_mutable_sharing',cache)
 def invalidation():
  root=h.clone(source,out/'SYNTHETIC-TAMPER');b=h.load_api(root,'tamper')
  with b.SnapshotContext(root):b.read_history_view(root/'events.jsonl')
  rel=next(rel for rel,rec in b._component_cold_archives(h.read(root/'manifest.json')).items() if 'seq_start' in rec);p=root/rel;raw=p.read_bytes();st=p.stat();p.write_bytes(bytes([raw[0]^1])+raw[1:]);os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
  try:
   with b.SnapshotContext(root):b.read_history_view(root/'events.jsonl')
  except Exception:pass
  else:raise AssertionError('CORRUPTION_CACHE_HIT')
  assert b.readiness_report(root)['status']=='BLOCKED';p.write_bytes(raw)
  assert b.readiness_report(root)['status']!='BLOCKED'
  return {'same_size_same_mtime_archive_damage_rejected':True,'repair_revalidates':True}
 case('actual_bytes_invalidate_cache_after_hidden_timestamp_tamper',invalidation)
 def disabled():
  normal=a.play_context_packet(source,player_intent='读取');os.environ['VOYAGER_DISABLE_VALIDATION_REUSE']='1';os.environ['VOYAGER_DISABLE_DERIVED_CACHE']='1'
  try:slow=a.play_context_packet(source,player_intent='读取')
  finally:os.environ.pop('VOYAGER_DISABLE_VALIDATION_REUSE');os.environ.pop('VOYAGER_DISABLE_DERIVED_CACHE')
  assert normal==slow
  return {'all_cache_off_same_public_result':True}
 case('cache_disabled_fallback_parity',disabled)
 def split():
  os.environ['VOYAGER_ROOT']=str(source);loader=load(source/'development/devsrc/runtime.py','split');d,modules=loader.load(source/'engine.py')
  assert d.business_query_packet(source)==a.business_query_packet(source)
  assert d.play_context_packet(source)==a.play_context_packet(source)
  return {'modules':len(modules),'release_and_split_api_equal':True}
 case('editable_split_source_and_built_engine_parity',split)
 def roles():
  # No player account batch can be requested through the NPC scoped route.
  h.reject(lambda:a.play_context_packet(source,viewer='npc:PER-NOVA-01',topics=['五项余额']),'PLAYER_TOPICS_DENIED')
  host=load(source/'development/host_session.py','host');session=host.HostSession(source,'SYNTHETIC-READ')
  ctx=session.context();assert ctx['status']=='NO_OPEN_SCENE'
  assert session.prepare()['status']=='NO_OPEN_SCENE' and session.metrics['engine_loads']==1
  h.reject(lambda:session.context(viewer='npc:PER-NOVA-01'),'VIEWER_MISMATCH')
  return {'no_cross_viewer_batch':True,'host_context_one_engine_load':True}
 case('role_isolation_and_reused_host_context',roles)
 def transfer():
  root=h.clone(source,out/'SYNTHETIC-TRANSFER');b=h.load_api(root,'transfer');c=h.command(b,root,'account_transfer','FAST-TRANSFER',source_account='covert',destination_account='fleet',currency='grey',amount='1.23',reason='SYNTHETIC exact receipt test');env=h.envelope(b,root,c)
  host=load(root/'development/host_session.py','host_write');denied=host.HostSession(root,'SYNTHETIC-DENIED');before={n:sha(root/n) for n in b.COMPONENT_FILES}
  # setup only accepts story_setup, while the direct domain route still requires
  # verified authority; JSON saying approved is never a trusted invocation.
  h.reject(lambda:b.domain_command_packet(root,c,'V14.67','SYNTHETIC authorization rejection'),'HOST_INTENT')
  assert before=={n:sha(root/n) for n in before}
  saved=b.host_intent_command(root,env,'V14.67');assert saved['status']=='SAVED';after={n:sha(root/n) for n in b.COMPONENT_FILES}
  assert b.host_intent_command(root,env,'V14.68')['status']=='ALREADY_APPLIED' and after=={n:sha(root/n) for n in after}
  full=b.run_checks(root,full=True);assert full['status']=='PASS',full['errors']
  return {'fake_host_json_rejected':True,'one_transfer_one_receipt':True,'same_ID_no_replay':True,'full':'PASS'}
 case('exact_transfer_authorization_commit_and_idempotent_retry',transfer)
 return all(r['status']=='PASS' for r in rows)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--parent',type=P,required=True);p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);n=p.parse_args();raise SystemExit(0 if run(n.parent,n.source,n.output) else 1)
