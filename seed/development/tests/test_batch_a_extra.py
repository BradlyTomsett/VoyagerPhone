import os,sys,json,pathlib,importlib.util,shutil,subprocess,tempfile,time,pty,select
BASE=pathlib.Path(os.environ.get('VOYAGER_TEST_SOURCE',str(pathlib.Path(__file__).resolve().parents[2]))).resolve();OUT=pathlib.Path(os.environ.get('VOYAGER_EXTRA_OUTPUT','audit/extra')).resolve();OUT.mkdir(parents=True,exist_ok=True)
os.environ.update(VOYAGER_ROOT=str(BASE),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm',PYTHONDONTWRITEBYTECODE='1')
spec=importlib.util.spec_from_file_location('e',BASE/'engine.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
rows=[]
def record(name,fn):
 try:r=fn();rows.append({'name':name,'status':'PASS','detail':r});print('PASS',name,flush=True)
 except Exception as ex:rows.append({'name':name,'status':'FAIL','error':str(ex)});print('FAIL',name,str(ex),flush=True)
 (OUT/'results.json').write_text(json.dumps({'status':'FAIL' if any(r['status']!='PASS' for r in rows) else 'PASS','tests':rows,'source_save_set_id':a.strict_json_load(BASE/'manifest.json')['save_set_id'],'engine_sha256':a.sha256_file(BASE/'engine.py'),'guard_sha256':a.sha256_file(BASE/'guard.py')},ensure_ascii=False,indent=2))
def clone(name):
 r=OUT/name;shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));return r
def envelope(r,cid):
 sid=a.strict_json_load(r/'manifest.json')['save_set_id'];now=a.strict_json_load(r/'state.json')['game_time'];c={'schema':a.DOMAIN_COMMAND_SCHEMA,'command_id':cid,'base_save_set_id':sid,'kind':'create_task','task':{'task_id':'TSK-'+cid,'title':'隔离测试任务','type':'manual','status':'queued'},'authorization':'host_intent','authorization_ref':'HOST:'+cid,'actor_id':'PER-COMMANDER-01'}
 return {'schema':'HOST_COMMAND_INTENT_V1','command':c,'subject_id':c['actor_id'],'parent_save_set_id':sid,'instruction_text':'建立隔离测试任务，不推进时间。','evidence_ref':'test-authenticated-host','decision':'approved','targets':a._domain_command_targets(c),'valid_from':now,'valid_until':now,'limits':{'uses':1,'gold_units':0,'grey_units':0,'quantity':0}}
worker="import importlib.util,json,pathlib,os; r=pathlib.Path(os.environ['VOYAGER_ROOT']); s=importlib.util.spec_from_file_location('e',r/'engine.py'); a=importlib.util.module_from_spec(s);s.loader.exec_module(a);print(json.dumps(a.host_intent_command(r,json.loads(pathlib.Path(os.environ['REQUEST']).read_text()),'V14.46')))"
def concurrent():
 r=clone('concurrent');e=envelope(r,'CONCURRENT');p=OUT/'concurrent.json';p.write_text(json.dumps(e));env=dict(os.environ,VOYAGER_ROOT=str(r),REQUEST=str(p));one=subprocess.Popen([sys.executable,'-c',worker],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);two=subprocess.Popen([sys.executable,'-c',worker],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);res=[one.communicate(timeout=240),two.communicate(timeout=240)];(OUT/'concurrent_workers.json').write_text(json.dumps(res));assert one.returncode==two.returncode==0,res
 kinds=sorted(json.loads(x[0])['status'] for x in res);assert kinds==['ALREADY_APPLIED','SAVED'],kinds
 t=a.strict_json_load(r/'tasks.json');assert sum(x['task_id']=='TSK-CONCURRENT' for x in t['queued_tasks'])==1;return kinds
record('two_concurrent_writers_once_only',concurrent)
def gateway():
 r=clone('gateway');e=envelope(r,'HUMAN-GATEWAY');p=OUT/'gateway_request.json';p.write_text(json.dumps(e));master,slave=pty.openpty();proc=subprocess.Popen([sys.executable,str(r/'development/interaction_gateway.py'),'--request',str(p),'--version','V14.46'],env=dict(os.environ,VOYAGER_ROOT=str(r)),stdin=slave,stdout=slave,stderr=slave);os.close(slave);buf=b'';sent=False;deadline=time.monotonic()+240
 try:
  while time.monotonic()<deadline:
   ready,_,_=select.select([master],[],[],1)
   if ready:
    try:data=os.read(master,65536)
    except OSError:break
    if not data:break
    buf+=data
    if not sent and '确认：'.encode() in buf:os.write(master,'执行 HUMAN-GATEWAY\n'.encode());sent=True
   if proc.poll() is not None and not ready:break
  proc.wait(timeout=5);(OUT/'gateway_transcript.txt').write_bytes(buf);assert proc.returncode==0,buf.decode(errors='replace')[-2000:];assert sent;assert any(x['task_id']=='TSK-HUMAN-GATEWAY' for x in a.strict_json_load(r/'tasks.json')['queued_tasks']);return 'TTY review -> signed inherited pipe -> exact command -> committed task'
 finally:
  os.close(master)
  if proc.poll() is None:proc.kill();proc.wait()
record('human_gateway_end_to_end',gateway)
raise SystemExit(1 if any(r['status']!='PASS' for r in rows) else 0)
