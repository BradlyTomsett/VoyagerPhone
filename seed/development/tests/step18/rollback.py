import sys
sys.dont_write_bytecode=True
import importlib.util,json,os,pathlib,shutil,subprocess
P=pathlib.Path;BASE=P(os.environ['VOYAGER_TEST_SOURCE']);OUT=P(os.environ['VOYAGER_STEP18_OUTPUT']);OUT.mkdir();rows=[]
def test(name,fn):
 try:detail=fn();rows.append({'name':name,'status':'PASS','detail':detail})
 except Exception as ex:rows.append({'name':name,'status':'FAIL','error':str(ex)})
 print(rows[-1]['status'],name,flush=True);(OUT/'results.json').write_text(json.dumps({'status':'FAIL' if any(x['status']=='FAIL' for x in rows) else 'PASS','tests':rows},ensure_ascii=False,indent=2)+'\n')
def execute(source,target):return subprocess.run([sys.executable,str(BASE/'development/restore_v1447.py'),'--source',str(source),'--output',str(target)],env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True)
def good():
 target=OUT/'previous';cp=execute(BASE,target);assert cp.returncode==0,(cp.stdout,cp.stderr);m=json.loads((target/'manifest.json').read_text());assert m['save_version']=='V14.47'
 cp=subprocess.run([sys.executable,str(target/'guard.py'),'--resume'],env=dict(os.environ,VOYAGER_ROOT=str(target),PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True);assert cp.returncode==0,(cp.stdout,cp.stderr);assert json.loads(cp.stdout)['readiness']['status']=='READY_WITH_LIMITATIONS'
 return {'previous_complete_declared_source_restored':True,'previous_guard_cold_resume':'READY_WITH_LIMITATIONS','old_zip_required':False}
test('previous_complete_source_restored_without_old_zip',good)
def changed():
 r=OUT/'new_facts';shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));p=r/'state.json';p.write_bytes(p.read_bytes()+b' ');cp=execute(r,OUT/'forbidden');assert cp.returncode!=0 and 'NEW_GAME_FACTS_REQUIRE_COMPATIBLE_MIGRATION' in cp.stdout;assert not (OUT/'forbidden').exists();cp=execute(BASE,BASE);assert cp.returncode!=0 and 'NEW_EXTERNAL_OUTPUT_REQUIRED' in cp.stdout;return 'changed authority and in-place rollback refused before writing'
test('new_authority_bytes_and_inplace_rollback_refused',changed)
raise SystemExit(1 if any(x['status']=='FAIL' for x in rows) else 0)
