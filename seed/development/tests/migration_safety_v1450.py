#!/usr/bin/env python3
"""Exercise real legacy conversion, concurrent source changes and copy publication."""
import argparse,hashlib,importlib.util,json,os,pathlib,shutil,sys,time,traceback
sys.dont_write_bytecode=True
P=pathlib.Path;p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);args=p.parse_args();BASE=args.source.resolve();OUT=args.output.resolve()
if OUT==BASE or BASE in OUT.parents:p.error('External new output required')
OUT.mkdir(parents=True,exist_ok=False);os.environ.update(VOYAGER_ROOT=str(BASE),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm');os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None)
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
api=load(BASE/'engine.py','safety_api');t=load(BASE/'development/transcode_history.py','safety_tool');restore=load(BASE/'development/restore_v1449.py','safety_restore');rows=[]
manifest=json.loads((BASE/'manifest.json').read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
before={n:sha(BASE/n) for n in ('manifest.json',*manifest['components'])}
def test(name,fn):
 started=time.monotonic()
 try:detail=fn();row={'name':name,'status':'PASS','detail':detail}
 except Exception as ex:row={'name':name,'status':'FAIL','error':str(ex),'trace':traceback.format_exc()}
 row['seconds']=round(time.monotonic()-started,3);rows.append(row);print(row['status'],name,flush=True)
 result={'schema':'V1450_MIGRATION_SAFETY_V1','status':'PASS' if all(x['status']=='PASS' for x in rows) else 'FAIL',
  'engine_sha256':sha(BASE/'engine.py'),'guard_sha256':sha(BASE/'guard.py'),'tool_sha256':sha(BASE/'development/transcode_history.py'),
  'test_sha256':sha(P(__file__)),'source_components_unchanged':before=={n:sha(BASE/n) for n in before},'tests':rows}
 (OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
def clone(name):
 r=OUT/name;shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));return r
def reject(fn,token):
 try:fn()
 except Exception as ex:assert token in str(ex),(token,str(ex));return str(ex)
 raise AssertionError('Unexpected acceptance')
def real():
 old=OUT/'original_v1449';restore.restore(BASE,old);previous=json.loads((old/'manifest.json').read_text());legacy=OUT/'legacy_compatible_tools'
 for name in ['manifest.json',*manifest['components'],*manifest['development_sources']['files']]:
  dest=legacy/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/name,dest)
 for rec in previous['cold_archives'].values():
  dest=legacy/rec['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old/rec['path'],dest)
 shutil.copyfile(old/'events.jsonl',legacy/'events.jsonl');m=dict(manifest,cold_archives=previous['cold_archives']);(legacy/'manifest.json').write_text(json.dumps(m));api._component_write_manifest_native(legacy,'V14.49',previous['parent_save_set_id'],previous['migration_lineage'])
 result=t.transcode_copy(legacy,OUT/'converted','V14.50');target=OUT/'converted';m=json.loads((target/'manifest.json').read_text())
 assert (target/'events.jsonl').read_bytes()==(BASE/'events.jsonl').read_bytes()
 assert {str(p.relative_to(target)) for p in (target/'archives').rglob('*') if p.is_file()}=={r['path'] for r in m['cold_archives'].values()}
 assert len(result['segments'])==19 and len(m['cold_archives'])==22 and result['logical_bytes_exact'] and result['new_logical_events']==0
 return {'status':'PASS','converted_segments':19,'cold_archives':22,'no_unbound_archive_files':True,'logical_bytes_exact':True,
         'cold_history_bytes_before':result['cold_history_bytes_before'],'cold_history_bytes_after':result['cold_history_bytes_after']}
test('actual_legacy_to_xz_copy_contains_only_declared_archives',real)
def late_manifest():
 r=clone('manifest_writer');original_load=t.load;fired=[]
 def injected_load(path):
  module=original_load(path)
  if path.name=='engine.py':
   original=module._component_write_manifest_native
   def write(*args,**kw):
    result=original(*args,**kw);m=json.loads((r/'manifest.json').read_text());m['isolated_external_writer']=True;(r/'manifest.json').write_text(json.dumps(m));fired.append(True);return result
   module._component_write_manifest_native=write
  return module
 t.load=injected_load
 try:reject(lambda:t.transcode_copy(r,OUT/'forbidden_late_writer','V14.51'),'SOURCE_CHANGED_DURING_MIGRATION')
 finally:t.load=original_load
 assert fired and not (OUT/'forbidden_late_writer').exists();return 'late uncooperative source manifest change rejected before target directory publication'
test('closing_barrier_rejects_source_change_without_publishing',late_manifest)
def journal():
 r=clone('unfinished_journal');runtime=r/'.runtime';runtime.mkdir();(runtime/'native_commit_journal.json').write_text('{"isolated_fixture":true}')
 reject(lambda:t.transcode_copy(r,OUT/'forbidden_recovery','V14.51'),'SOURCE_RECOVERY_REQUIRED');assert not (OUT/'forbidden_recovery').exists();return 'source with pending recovery refused without copying game facts'
test('active_recovery_source_refused',journal)
def version():
 reject(lambda:t.transcode_copy(BASE,OUT/'forbidden_old_version',manifest['save_version']),'NEWER_SAVE_VERSION_REQUIRED')
 reject(lambda:t.transcode_copy(BASE,BASE,'V14.51'),'NEW_EXTERNAL_OUTPUT_REQUIRED')
 assert not (OUT/'forbidden_old_version').exists();return 'same/older version and in-place target refused'
test('newer_version_and_external_target_required',version)
assert before=={n:sha(BASE/n) for n in before}
raise SystemExit(0 if all(r['status']=='PASS' for r in rows) else 1)
