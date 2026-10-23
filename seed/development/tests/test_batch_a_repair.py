import pathlib,json,os,sys,subprocess,importlib.util,shutil,hashlib
BASE=pathlib.Path(os.environ.get('VOYAGER_TEST_SOURCE',str(pathlib.Path(__file__).resolve().parents[2]))).resolve();OUT=pathlib.Path(os.environ.get('VOYAGER_REPAIR_OUTPUT','audit/repair_final')).resolve();OUT.mkdir(parents=True,exist_ok=True)
os.environ.update(VOYAGER_ROOT=str(BASE),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm',PYTHONDONTWRITEBYTECODE='1')
spec=importlib.util.spec_from_file_location('repair_test',BASE/'engine.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a);tests=[]
def h(r):return {n:a.sha256_file(r/n) for n in a.COMPONENT_FILES}
def fixture(name):
 r=OUT/name;shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));m,e,_=a.read_history_raw(r/'events.jsonl');m['next_seq']-=1;a._native_durable_replace_bytes(r/'events.jsonl',a._history_replace_metadata_bytes((r/'events.jsonl').read_bytes(),m));mf=a.strict_json_load(r/'manifest.json');a._component_write_manifest_native(r,mf['save_version'],mf.get('parent_save_set_id'),mf.get('migration_lineage'));return r
for phase in ['repair_after_events.jsonl','repair_after_manifest']:
 try:
  r=fixture(phase);before=h(r);plan=a.consistency_repair_plan(r);path=OUT/(phase+'.plan.json');path.write_text(json.dumps(plan,ensure_ascii=False));cp=subprocess.run([sys.executable,str(r/'engine.py'),'repairapply','--plan',str(path)],env=dict(os.environ,VOYAGER_ROOT=str(r),VOYAGER_COMMIT_KILL=phase),capture_output=True,text=True,timeout=180);assert cp.returncode==86,(cp.stdout,cp.stderr)
  g=a._repair_guard_module(r)
  with g.guard_lock(r):recovered=g.recover_consistency_repair(r)
  assert recovered['outcome']==('target' if phase=='repair_after_manifest' else 'parent'),recovered
  if phase=='repair_after_events.jsonl':assert h(r)==before
  else:
   p=a.consistency_repair_plan(r);assert not p['changes'];assert a.consistency_repair_apply(r,p)['status']=='NO_CHANGE';assert a.readiness_report(r)['status']!='BLOCKED'
  tests.append({'name':phase,'status':'PASS','outcome':recovered['outcome']});print('PASS',phase,flush=True)
 except Exception as ex:tests.append({'name':phase,'status':'FAIL','error':str(ex)});print('FAIL',phase,str(ex),flush=True)
 (OUT/'results.json').write_text(json.dumps({'status':'FAIL' if any(t['status']!='PASS' for t in tests) else 'PASS','engine_sha256':a.sha256_file(BASE/'engine.py'),'guard_sha256':a.sha256_file(BASE/'guard.py'),'source_save_set_id':a.strict_json_load(BASE/'manifest.json')['save_set_id'],'tests':tests},ensure_ascii=False,indent=2))
raise SystemExit(any(t['status']!='PASS' for t in tests))
