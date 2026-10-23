#!/usr/bin/env python3
"""Run the 14 established suites with rebased test-only versions and codec-aware proofs.
Adapted scripts are materialized outside the frozen source, which is never edited.
"""
import argparse,hashlib,json,os,pathlib,re,shutil,subprocess,sys,time
sys.dont_write_bytecode=True
P=pathlib.Path
parser=argparse.ArgumentParser();parser.add_argument('--source',type=P,default=P(__file__).resolve().parents[3]);parser.add_argument('--output',type=P,required=True)
suites=('core','accounts','goods','reads','stories','story_integration','story_faults','policy','concurrency','matrix','repair','release_contracts','domain_contracts','rollback')
parser.add_argument('--only',default=','.join(suites));args=parser.parse_args();source=args.source.resolve();out=args.output.resolve()
if out==source or source in out.parents:raise SystemExit('Output must be outside supplied source')
out.mkdir(parents=True,exist_ok=False);frozen=out/'input';scripts=out/'scripts';scripts.mkdir()
shutil.copytree(source,frozen,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((frozen/'manifest.json').read_text());before={n:sha(frozen/n) for n in ('manifest.json',*manifest['components'])}
shift=int(manifest['save_version'].split('.')[1])-49
shutil.copyfile(source/'development/tests/v1450/common.py',scripts/'common.py')
env=dict(os.environ,VOYAGER_TEST_SOURCE=str(frozen),VOYAGER_ROOT=str(frozen),PYTHONDONTWRITEBYTECODE='1',VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm');env.pop('VOYAGER_DEV_SOURCE_DIR',None)
rows=[]
for name in args.only.split(','):
    if name not in suites:raise SystemExit('Unknown suite')
    original=source/'development/tests/v1449'/(name+'.py');text=original.read_text()
    text=re.sub(r'V14\.(49|50|51|52|53)\b',lambda m:'V14.'+str(int(m[1])+shift),text)
    if name=='accounts':text=text.replace("('reserve','play','settle'),50)","('reserve','play','settle'),"+str(50+shift)+")")
    if name=='rollback':text=text.replace('restore_previous.py','restore_v1449.py').replace("=='V14.48'","=='V14.49'")
    script=scripts/(name+'.py');script.write_text(text);target=out/name;cmd=[sys.executable,str(script)]
    if name=='core':cmd+=['--source',str(frozen),'--output',str(target),'--group','all']
    e=dict(env,VOYAGER_BATCH_B_OUTPUT=str(target),VOYAGER_BATCH_C_OUTPUT=str(target),VOYAGER_EXTRA_OUTPUT=str(target),VOYAGER_STEP18_OUTPUT=str(target),VOYAGER_REPAIR_OUTPUT=str(target))
    start=time.monotonic()
    with (out/(name+'.stdout')).open('w') as log,(out/(name+'.stderr')).open('w') as err:cp=subprocess.run(cmd,env=e,stdout=log,stderr=err,timeout=1800)
    result=json.loads((target/'results.json').read_text()) if (target/'results.json').exists() else {'status':'NO_RESULT'}
    rows.append({'suite':name,'status':'PASS' if cp.returncode==0 and result.get('status')=='PASS' else 'FAIL','returncode':cp.returncode,
        'seconds':round(time.monotonic()-start,3),'upstream_script_sha256':sha(original),'adapted_script_sha256':sha(script),'result':result})
    report={'schema':'V1450_COMPATIBILITY_V1','status':'PASS' if all(x['status']=='PASS' for x in rows) else 'FAIL',
        'save_set_id':manifest['save_set_id'],'manifest_sha256':sha(frozen/'manifest.json'),'engine_sha256':sha(frozen/'engine.py'),
        'guard_sha256':sha(frozen/'guard.py'),'source_components_unchanged':before=={n:sha(frozen/n) for n in before},'suites':rows}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(rows[-1]['status'],name,rows[-1]['seconds'],flush=True)
assert report['source_components_unchanged']
raise SystemExit(0 if report['status']=='PASS' else 1)
