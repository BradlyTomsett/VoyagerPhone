#!/usr/bin/env python3
"""Sequential backend comparison, V14.58 vs V14.59; no model/provider timing."""
import argparse,copy,importlib.util,json,os,pathlib,platform,shutil,statistics,subprocess,sys,time
sys.dont_write_bytecode=True
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--parent',type=P,required=True);p.add_argument('--output',type=P,required=True);p.add_argument('--write-samples',type=int,default=2);ns=p.parse_args();source=ns.source.resolve();parent=ns.parent.resolve();out=ns.output.resolve();out.mkdir(parents=True,exist_ok=False)
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=load(source/'development/tests/stage1_v1453.py','h');report={'schema':'BATCH2_FOLLOWUP_PERFORMANCE_V1','environment':{'python':sys.version,'platform':platform.platform(),'os_page_cache_flushed':False,'profiling':False,'concurrent_suites':False,'fsync_scope':'current Python process; Guard subprocess fsync not instrumented','write_bytes_scope':'bytes passed to Python file streams in current process; includes object/JSON writes, excludes Guard subprocess and pipe writes; OS output blocks separately recorded'},'scope':'actual supplied V14.58 direct baseline; V14.57 batch baseline unavailable, NOT_RUN','model_generation':'NOT_RUN','ChatGPT_tool_roundtrips':'NOT_CONNECTED','conditions':'sequential unprofiled wall time including final canonical JSON serialization; fixture cloning/setup excluded; import measured separately; read first cold-derived then five warm; write sample count explicit; backend API calls are not actual provider tool roundtrips','versions':{}}
def save():
 (out/'performance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
def timed(record,key,fn):
 t=time.perf_counter();v=fn();json.dumps(v,ensure_ascii=False,separators=(',',':'),default=str);dt=time.perf_counter()-t;record.setdefault('samples',{}).setdefault(key,[]).append(dt);save();return v
def io_measured(api,fn):
 stats={'durable_copy_requests':0,'durable_copy_source_bytes':0,'fsync_calls':0,'stream_write_bytes':0,'full_copy_data_bytes':0};sync=os.fsync;copyfileobj=shutil.copyfileobj;orig=api._native_durable_copy; namespace=orig.__globals__
 def fsync(fd):stats['fsync_calls']+=1;return sync(fd)
 def dur(src,dest):stats['durable_copy_requests']+=1;stats['durable_copy_source_bytes']+=P(src).stat().st_size;return orig(src,dest)
 def filecopy(src,dest,length=0):
  pos=src.tell();start=dest.tell();v=copyfileobj(src,dest,length);stats['full_copy_data_bytes']+=dest.tell()-start;return v
 import builtins
 pathopen=P.open; builtinopen=builtins.open; fdopen=os.fdopen
 class Writer:
  def __init__(self,stream):self.stream=stream
  def __getattr__(self,name):return getattr(self.stream,name)
  def __enter__(self):self.stream.__enter__();return self
  def __exit__(self,*args):return self.stream.__exit__(*args)
  def write(self,data):
   result=self.stream.write(data);stats['stream_write_bytes']+=len(data.encode(self.stream.encoding or 'utf-8') if isinstance(data,str) else data);return result
 def opened(opener,*args,**kwargs):
  stream=opener(*args,**kwargs);mode=kwargs.get('mode',args[1] if len(args)>1 else 'r')
  return Writer(stream) if isinstance(mode,str) and any(c in mode for c in 'wax+') else stream
 os.fsync=fsync;shutil.copyfileobj=filecopy;namespace['_native_durable_copy']=dur
 P.open=lambda *args,**kwargs:opened(pathopen,*args,**kwargs)
 builtins.open=lambda *args,**kwargs:opened(builtinopen,*args,**kwargs)
 os.fdopen=lambda *args,**kwargs:opened(fdopen,*args,**kwargs)
 try:
  before=__import__('resource').getrusage(__import__('resource').RUSAGE_SELF).ru_oublock;v=fn();after=__import__('resource').getrusage(__import__('resource').RUSAGE_SELF).ru_oublock;stats['os_block_output_512_bytes']=(after-before)*512
 finally:os.fsync=sync;shutil.copyfileobj=copyfileobj;namespace['_native_durable_copy']=orig;P.open=pathopen;builtins.open=builtinopen;os.fdopen=fdopen
 return v,stats
def footprint(root):
 seen=set();logical=blocks=files=0
 for p in root.rglob('*'):
  if not p.is_file():continue
  st=p.stat();files+=1;logical+=st.st_size;key=(st.st_dev,st.st_ino)
  if key not in seen:seen.add(key);blocks+=st.st_blocks*512
 return {'files':files,'logical_bytes':logical,'unique_inode_allocated_bytes':blocks}
actor='PER-HAWK-MALEN-01';sid='SYNTHETIC-BENCH-SCENE'
for label,src in [('V14.58',parent),('V14.59',source)]:
 rec=report['versions'][label]={'engine_sha256':h.sha(src/'engine.py'),'input_manifest_sha256':h.sha(src/'manifest.json'),'samples':{},'IO':[],'growth':[]};readroot=h.clone(src,out/(label+'_read'))
 t=time.perf_counter();a=h.load_api(readroot,'read_'+label);rec['engine_import_seconds']=time.perf_counter()-t
 timed(rec,'batch_cold_derived',lambda:a.visible_query_batch_packet(readroot,['五项余额','当前场景','当前金币余额']))
 for i in range(5):timed(rec,'batch_warm',lambda:a.visible_query_batch_packet(readroot,['五项余额','当前场景','当前金币余额']))
 for i in range(ns.write_samples):
  r=h.clone(src,out/(label+'_round_'+str(i)));a=h.load_api(r,'round_'+label+str(i));actions=[{'type':'scene_open','scene_id':sid,'task_id':None,'family':'conversation','title':'SYNTHETIC ONLY','location_ref':'LOC-FREEPORT-XILU9','participants':[actor],'presence_mode':'remote','visible_to':['player','npc:'+actor]},{'type':'fact_append','scene_id':sid,'fact_id':'F-OPEN','subject_id':actor,'predicate':'statement','value':'固定合成对白。','epistemic':'rumor','source_category':'npc_statement'},{'type':'knowledge_disclose','scene_id':sid,'fact_id':'F-OPEN','viewer_id':'player','channel':'heard','basis_event_id':'$current_transaction'},{'type':'knowledge_disclose','scene_id':sid,'fact_id':'F-OPEN','viewer_id':'npc:'+actor,'channel':'heard','basis_event_id':'$current_transaction'},{'type':'scene_phase','scene_id':sid,'phase':'open'}]
  c=h.command(a,r,'story_setup','SYNTHETIC-SETUP',actions=actions);a.host_intent_command(r,h.envelope(a,r,c),'V14.80');rec['growth'].append({'sample':i,'stage':'after_setup',**footprint(r)})
  host=load(src/'development/host_session.py','host_'+label+str(i));expected=[]
  def authorize(env):return bool(expected) and env==expected[0]
  session=host.HostSession(r,'SYNTHETIC-'+str(i),authorize=authorize);t=time.perf_counter();ctx=timed(rec,'prepare_with_session_load',lambda:session.prepare(scene_id=sid,actor_id=actor));loaded_round_start=t
  for q in range(5):timed(rec,'prepare_hot_session',lambda:session.prepare(scene_id=sid,actor_id=actor))
  # A complete warm backend round is exactly prepare + submit, excluding AI wait.
  round_counts_before=copy.deepcopy(session.metrics);start=time.perf_counter();ctx=timed(rec,'round_prepare',lambda:session.prepare(scene_id=sid,actor_id=actor))
  proposal={'schema':a.STORY_TURN_SCHEMA,'turn_id':'SYNTHETIC-DIALOGUE','base_identity':ctx['base_identity'],'scene_id':sid,'actor_id':actor,'viewer':'player','player_intent':'固定合成对白','intent_tags':['conversation'],'basis_refs':['fact/'+sid+'/F-OPEN'],'segments':[{'mode':'dialogue','speaker_id':actor,'text':'先核对事实，等待指挥官选择。','basis_refs':['fact/'+sid+'/F-OPEN'],'receipt_refs':[]}],'effects':[],'updates':[],'consequences':[],'claims':[],'public_reason':'SYNTHETIC no mechanical effects','candidates':['等待']};c=h.command(a,r,'story_turn','SYNTHETIC-DIALOGUE',proposal=proposal);env=h.envelope(a,r,c);expected[:]=[env]
  active=session._engine();v,stats=io_measured(active,lambda:timed(rec,'dialogue_submit_with_report',lambda:session.submit(env,'V14.81')));assert v['status']=='SAVED' and 'report' in v;rec.setdefault('full_round_counts',[]).append({k:session.metrics[k]-round_counts_before[k] for k in session.metrics});rec['samples'].setdefault('warm_backend_round_prepare_submit',[]).append(time.perf_counter()-start);rec['IO'].append({'sample':i,'kind':'dialogue',**stats});rec['growth'].append({'sample':i,'stage':'after_dialogue',**footprint(r)})
  timed(rec,'prepare_after_dialogue',lambda:session.prepare(scene_id=sid,actor_id=actor));retry=timed(rec,'dialogue_same_ID_retry',lambda:session.submit(env,'V14.82'));assert retry['receipt']==v['receipt']
  c=h.command(a,r,'account_transfer','SYNTHETIC-TRANSFER',source_account='covert',destination_account='fleet',currency='grey',amount='1.23',reason='SYNTHETIC ONLY');env2=h.envelope(a,r,c);v,stats=io_measured(a,lambda:timed(rec,'transfer_commit',lambda:a.host_intent_command(r,env2,'V14.82')));assert v['status']=='SAVED';rec['IO'].append({'sample':i,'kind':'transfer',**stats});rec['growth'].append({'sample':i,'stage':'after_transfer',**footprint(r)})
  assert timed(rec,'transfer_same_ID_retry',lambda:a.host_intent_command(r,env2,'V14.83'))['status']=='ALREADY_APPLIED';rec.setdefault('host_session_metrics',[]).append(copy.deepcopy(session.metrics))
  if i==0:
   # Count the repaired path as two complete snapshots, with identical authority.
   home=r/'.runtime/consistency_repairs/SYNTHETIC-BENCH';manifest=h.read(r/'manifest.json')
   def repair():a._repair_snapshot_copy(r,home/'parent',manifest);a._repair_snapshot_copy(r,home/'target',manifest);return {'complete_snapshots':2}
   _,stats=io_measured(a,lambda:timed(rec,'repair_parent_target_snapshots',repair));rec['IO'].append({'sample':i,'kind':'repair_two_snapshots',**stats});rec['growth'].append({'sample':i,'stage':'after_repair_snapshots',**footprint(r)})
   os.environ['VOYAGER_DELIVERY_ROOT']=str(out/(label+'_exports'));exported=timed(rec,'full_export_independent_coldboot',lambda:a.export_save_set(r,h.read(r/'manifest.json')['parent_save_set_id']));assert exported['status']=='READY' and exported['cold_boot']=='PASS',exported
 # Measure a fresh Guard process recovering an actual killed transaction.
 recovery=h.clone(src,out/(label+'_recovery'));ra=h.load_api(recovery,'recovery_'+label);before_recovery=h.read(recovery/'manifest.json')['save_set_id'];cmd=h.command(ra,recovery,'account_transfer','SYNTHETIC-RECOVERY',source_account='covert',destination_account='fleet',currency='grey',amount='1.23',reason='SYNTHETIC interrupted recovery benchmark');request=out/(label+'_recovery_request.json');request.write_text(json.dumps(h.envelope(ra,recovery,cmd),ensure_ascii=False))
 worker="import os,pathlib,importlib.util,json; r=pathlib.Path(os.environ['VOYAGER_ROOT']); spec=importlib.util.spec_from_file_location('helper',r/'development/tests/stage1_v1453.py'); h=importlib.util.module_from_spec(spec); spec.loader.exec_module(h); a=h.load_api(r); a.host_intent_command(r,json.loads(pathlib.Path(os.environ['SYNTHETIC_REQUEST']).read_text()),'V14.90')"
 killed=subprocess.run([sys.executable,'-c',worker],env=dict(os.environ,VOYAGER_ROOT=str(recovery),VOYAGER_COMMIT_KILL='after_component',SYNTHETIC_REQUEST=str(request)),capture_output=True,text=True,timeout=240);assert killed.returncode==86,killed.stdout+killed.stderr
 def recover():
  cp=subprocess.run([sys.executable,str(recovery/'guard.py'),'--check'],env=dict(os.environ,VOYAGER_ROOT=str(recovery)),capture_output=True,text=True,timeout=240);assert cp.returncode==0,cp.stdout+cp.stderr;return json.loads(cp.stdout)
 timed(rec,'cold_interrupted_recovery_guard_check',recover);assert h.read(recovery/'manifest.json')['save_set_id']==before_recovery
 rec['summary']={k:{'n':len(v),'median_seconds':statistics.median(v),'min_seconds':min(v),'max_seconds':max(v)} for k,v in rec['samples'].items()}
 # A new CLI process includes engine load and Guard validation, no previous runtime.
 cold=h.clone(src,out/(label+'_cold_guard'))
 for flag in ['--check','--resume']:
  def run(flag=flag):
   cp=subprocess.run([sys.executable,str(cold/'guard.py'),flag],env=dict(os.environ,VOYAGER_ROOT=str(cold)),capture_output=True,text=True,timeout=240);assert cp.returncode==0,cp.stdout+cp.stderr;return json.loads(cp.stdout)
  timed(rec,'cold_guard'+flag,run)
 rec['summary']={k:{'n':len(v),'median_seconds':statistics.median(v),'min_seconds':min(v),'max_seconds':max(v)} for k,v in rec['samples'].items()};save();print('PASS',label,'benchmark',flush=True)
report['status']='PASS';save()
