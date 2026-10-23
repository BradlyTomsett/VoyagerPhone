#!/usr/bin/env python3
"""V14.59 missing-path regression and growth metrics, isolated and source-bound."""
import argparse,copy,importlib.util,json,os,pathlib,statistics,sys,time,traceback
sys.dont_write_bytecode=True
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--parent',type=P,required=True);p.add_argument('--output',type=P,required=True);ns=p.parse_args();source=ns.source.resolve();parent=ns.parent.resolve();out=ns.output.resolve();out.mkdir(parents=True,exist_ok=False)
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=load(source/'development/tests/stage1_v1453.py','h');a=h.load_api(source,'current');old=h.load_api(parent,'parent');rows=[]
def case(name,fn):
 t=time.perf_counter()
 try:row={'name':name,'status':'PASS','detail':fn()}
 except Exception as ex:row={'name':name,'status':'FAIL','error':str(ex),'trace':traceback.format_exc()}
 row['seconds']=time.perf_counter()-t;rows.append(row);(out/'results.json').write_text(json.dumps({'schema':'BATCH2_FOLLOWUP_TARGETED_V1','status':'PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL','engine_sha256':h.sha(source/'engine.py'),'parent_engine_sha256':h.sha(parent/'engine.py'),'manifest_sha256':h.sha(source/'manifest.json'),'model_generation':'NOT_RUN','tests':rows},ensure_ascii=False,indent=2));print(row['status'],name,row.get('error',''),flush=True)
def queries():
 sid=next(iter(a._scene_registry(h.read(source/'state.json'))['records']))
 calls=[('batch',lambda b,r:b.visible_query_batch_packet(r,['五项余额','当前场景','当前金币余额'])),('knowledge',lambda b,r:b.knowledge_packet(r,sid)),('scene',lambda b,r:b.scene_query_packet(r,sid)),('account',lambda b,r:b.account_query_packet(r)),('content',lambda b,r:b.content_query_packet(r))]
 result=[]
 for name,fn in calls:
  previous=fn(old,parent)
  with a.SnapshotContext(source) as ctx:
   a.ensure_source_ready(source);before=ctx.metrics.get('state_mutable_copies',0);current=fn(a,source);copies=ctx.metrics.get('state_mutable_copies',0)-before;assert copies==0,(name,copies)
  def clean(x):
   if isinstance(x,dict):return {k:clean(v) for k,v in x.items() if k not in ('save_set_id','engine_version','readiness')}
   if isinstance(x,list):return [clean(v) for v in x]
   return x
  assert clean(current)==clean(previous),name
  # All returned containers support ordinary mutation, then a new request is clean.
  def touch(x):
   if isinstance(x,dict):x['SYNTHETIC-MUTATION']=True
   elif isinstance(x,list):x.append('SYNTHETIC-MUTATION')
  touch(current);assert 'SYNTHETIC-MUTATION' not in fn(a,source)
  result.append({'route':name,'post_validation_full_state_copies':copies})
 return result
case('pure_query_semantics_and_zero_full_state_copies',queries)
def growth():
 original=h.read(source/'state.json');sid=next(iter(a._scene_registry(original)['records']));result=[]
 for scenes,n,people in [(1,100,1),(4,250,4),(8,500,16)]:
  state=copy.deepcopy(original);records={};rt=a._story_runtime(state);rt['facts']={};rt['learning_events']=[];rt['legacy_viewer_bindings']={f'observer:OLD{i}':{'viewer_id':f'npc:SYNTHETIC-P{i}'} for i in range(people)}
  template=a._scene_registry(state)['records'][sid]
  for j in range(scenes):
   scene=sid+'-'+str(j);rec=copy.deepcopy(template);rec['scene_id']=scene;rec['facts']={};rec['disclosures']=[];records[scene]=rec
   for i in range(n):
    fid='F'+str(i);rec['facts'][fid]={'text':'SYNTHETIC '+str(i),'epistemic':'rumor','source_event_ids':[]}
    rec['disclosures'] += [{'viewer':v,'fact_id':fid,'basis':'SYNTHETIC'} for v in ('player',f'observer:OLD{i%people}')]
    if i%5==0:
     cf='C'+str(i);rt['facts'][scene+'/'+cf]={'scene_id':scene,'fact_id':cf,'subject_id':'SYNTHETIC-P0','value':'corrected','epistemic':'confirmed','valid_from':state['game_time'],'source_event_ids':[],'supersedes_fact_id':fid,'confidence_basis':'private','source_category':'direct_observation'}
     rt['learning_events'].append({'scene_id':scene,'fact_id':cf,'viewer_id':'player','learned_at':state['game_time']})
  a._scene_registry(state)['records']=records;viewers=['player','npc:SYNTHETIC-P0','observer:OLD0','gm'];baseline_start=time.perf_counter();expected={(s,v):old._knowledge_rows(state,s,v) for s in records for v in viewers};baseline_seconds=time.perf_counter()-baseline_start;samples=[]
  for repeat in range(3):
   with a.SnapshotContext(source) as ctx:
    frozen=a._stage2_freeze(state);t=time.perf_counter();actual={(s,v):a._knowledge_rows(frozen,s,v) for s in records for v in viewers};samples.append(time.perf_counter()-t);assert actual==expected
    assert ctx.metrics['knowledge_disclosures_indexed']==2*scenes*n
    before=ctx.metrics['knowledge_rows_builds'];one=a._knowledge_rows(frozen,next(iter(records)),'player');one[0]['value']='MUTATED';assert a._knowledge_rows(frozen,next(iter(records)),'player')[0]['value']!='MUTATED';assert ctx.metrics['knowledge_rows_builds']==before
    metrics=copy.deepcopy(ctx.metrics)
  result.append({'synthetic':True,'scenes':scenes,'people':people,'legacy_facts':scenes*n,'disclosures':2*scenes*n,'learning':len(rt['learning_events']),'viewers':len(viewers),'V1458_mutable_projection_seconds_n1':baseline_seconds,'timing_scope':'in-memory knowledge projection; excludes source validation, JSON parsing, freeze and model','seconds_samples':samples,'median_seconds':statistics.median(samples),'counts':metrics,'exact_V1458_semantics':True})
 return result
case('legacy_alias_correction_growth_and_same_snapshot_reuse',growth)
def repair_pool():
 r=h.clone(source,out/'repair_pool');b=h.load_api(r,'repair_pool');manifest=h.read(r/'manifest.json');home=r/'.runtime/consistency_repairs'/'SYNTHETIC';parent_snap=home/'parent';target_snap=home/'target';b._repair_snapshot_copy(r,parent_snap,manifest);b._repair_snapshot_copy(r,target_snap,manifest)
 files=manifest['development_sources']['files'];pool=r/'.runtime/development_objects';count=0
 for rel,digest in files.items():
  obj=pool/digest;pp=parent_snap/rel;tp=target_snap/rel
  assert obj.is_file() and obj.stat().st_ino==pp.stat().st_ino==tp.stat().st_ino and obj.stat().st_ino!=(r/rel).stat().st_ino
  assert not obj.stat().st_mode&0o222;count+=1
 rel='development/README.md';raw=(r/rel).read_bytes();(r/rel).write_bytes(raw+b'SYNTHETIC');assert (parent_snap/rel).read_bytes()==raw;b._native_durable_replace_bytes(r/rel,raw)
 # A corrupt pool object must never be silently linked or repaired from another version.
 obj=pool/files[rel];os.chmod(obj,0o644);obj.write_bytes(raw+b'BAD');dest=r/'.runtime/consistency_repairs/SYNTHETIC/third'/rel;dest.parent.mkdir(parents=True)
 h.reject(lambda:b._native_durable_copy(r/rel,dest),'DEVELOPMENT_OBJECT_NOT_IMMUTABLE_OR_BOUND')
 return {'development_files_shared':count,'both_repair_snapshots_use_verified_pool':True,'worktree_inode_isolated':True,'corrupt_object_refused':True}
case('real_consistency_repair_paths_share_immutable_objects',repair_pool)
def host_reload():
 r=h.clone(parent,out/'host_upgrade');other=h.clone(source,out/'host_other');host=load(source/'development/host_session.py','host')
 ss=host.HostSession(r,'SYNTHETIC-UPGRADE');assert ss.prepare()['status']=='NO_OPEN_SCENE';assert ss.metrics['engine_loads']==1
 for rel in ['engine.py','guard.py','events.jsonl','manifest.json',*h.read(source/'manifest.json')['development_sources']['files']]:
  dest=r/rel;dest.parent.mkdir(parents=True,exist_ok=True);__import__('shutil').copyfile(source/rel,dest)
 assert ss.prepare()['status']=='NO_OPEN_SCENE' and ss.metrics['engine_loads']==2
 assert ss.prepare()['status']=='NO_OPEN_SCENE' and ss.metrics['engine_loads']==2
 separate=host.HostSession(other,'SYNTHETIC-OTHER');assert separate.prepare()['base_identity']==ss.prepare()['base_identity'];assert separate._api is not ss._api
 restarted=host.HostSession(r,'SYNTHETIC-UPGRADE');assert restarted.prepare()['base_identity']==ss.prepare()['base_identity'];assert restarted.metrics['engine_loads']==1
 moved=r.with_name(r.name+'_moved');r.rename(moved);__import__('shutil').copytree(other,r,ignore=__import__('shutil').ignore_patterns('.runtime','__pycache__','.game_engine.lock'));h.reject(ss.prepare,'HOST_ROOT_REPLACED')
 return {'engine_upgrade_reloads':2,'new_process_style_instance_coldloads':1,'two_roots_separate_namespaces':True,'replaced_root_inode_refused':True,'ChatGPT_tool_wiring':'NOT_CONNECTED'}
case('host_upgrade_restart_and_distinct_root_isolation',host_reload)
raise SystemExit(0 if all(r['status']=='PASS' for r in rows) else 1)
