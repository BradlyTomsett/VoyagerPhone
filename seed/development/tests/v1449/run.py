#!/usr/bin/env python3
"""Portable Step18 acceptance. Test mutations never touch the supplied save."""
import argparse,hashlib,json,os,pathlib,shutil,subprocess,sys,time
sys.dont_write_bytecode=True
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('--source',type=P,default=P(__file__).resolve().parents[3]);p.add_argument('--output',type=P,required=True);p.add_argument('--only',default='core,accounts,goods,reads,stories,story_integration,story_faults,policy,concurrency,matrix,repair,release_contracts,domain_contracts,rollback');args=p.parse_args()
source=args.source.resolve();out=args.output.resolve()
if source==out or source in out.parents:raise SystemExit('Output must be outside the supplied source tree')
out.mkdir(parents=True,exist_ok=False);frozen=out/'input';shutil.copytree(source,frozen,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((frozen/'manifest.json').read_text());before={n:sha(frozen/n) for n in ('manifest.json',*m['components'])};rows=[]
env=dict(os.environ,VOYAGER_TEST_SOURCE=str(frozen),VOYAGER_ROOT=str(frozen),PYTHONDONTWRITEBYTECODE='1',VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm');env.pop('VOYAGER_DEV_SOURCE_DIR',None)
for name in args.only.split(','):
 script=frozen/'development/tests/v1449'/(name+'.py')
 if name not in ('core','accounts','goods','reads','stories','story_integration','story_faults','policy','concurrency','matrix','repair','release_contracts','domain_contracts','rollback'):raise SystemExit('Unknown suite')
 target=out/name;cmd=[sys.executable,str(script)];e=dict(env,VOYAGER_BATCH_B_OUTPUT=str(target),VOYAGER_BATCH_C_OUTPUT=str(target),VOYAGER_EXTRA_OUTPUT=str(target),VOYAGER_STEP18_OUTPUT=str(target),VOYAGER_REPAIR_OUTPUT=str(target))
 if name=='core':cmd+=['--source',str(frozen),'--output',str(target),'--group','all']
 start=time.monotonic()
 with (out/(name+'.stdout')).open('w') as log,(out/(name+'.stderr')).open('w') as err:cp=subprocess.run(cmd,env=e,stdout=log,stderr=err,timeout=1800)
 result=json.loads((target/'results.json').read_text()) if (target/'results.json').exists() else {'status':'NO_RESULT'}
 rows.append({'suite':name,'status':'PASS' if cp.returncode==0 and result.get('status')=='PASS' else 'FAIL','returncode':cp.returncode,'seconds':round(time.monotonic()-start,3),'script_sha256':sha(script),'result':result})
 print(rows[-1]['status'],name,rows[-1]['seconds'],flush=True)
 report={'schema':'V1449_COMPATIBILITY_V1','status':'PASS' if all(x['status']=='PASS' for x in rows) else 'FAIL','save_set_id':m['save_set_id'],'engine_sha256':sha(frozen/'engine.py'),'guard_sha256':sha(frozen/'guard.py'),'manifest_sha256':sha(frozen/'manifest.json'),'python':sys.version,'source_components_unchanged':before=={n:sha(frozen/n) for n in before},'suites':rows,'scope':'V14.49 bugfix compatibility; full UI/original-image feature upgrade excluded'}
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
assert report['source_components_unchanged']
raise SystemExit(0 if report['status']=='PASS' else 1)
