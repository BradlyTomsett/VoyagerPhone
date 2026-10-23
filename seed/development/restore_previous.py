#!/usr/bin/env python3
"""Create an exact V14.48 source copy; never overwrite current or discard new facts."""
import argparse,hashlib,importlib.util,json,pathlib,sys
sys.dont_write_bytecode=True
P=pathlib.Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load_guard(path):
 s=importlib.util.spec_from_file_location('restore_guard',path);g=importlib.util.module_from_spec(s);s.loader.exec_module(g);return g
def restore(source,output):
 source=P(source).resolve();output=P(output).resolve();backup=source/'development/evidence/v1448_backup'
 if output.exists() or output==source or source in output.parents:raise ValueError('NEW_EXTERNAL_OUTPUT_REQUIRED')
 previous=json.loads((backup/'manifest.json').read_text())
 if previous['save_set_id']!='SAVESET-V14.48-cdf55a13d2da9684':raise ValueError('ROLLBACK_BASE_UNSUPPORTED')
 for name,digest in previous['authority_components'].items():
  if sha(source/name)!=digest:raise ValueError('NEW_GAME_FACTS_REQUIRE_COMPATIBLE_MIGRATION:'+name)
 g=load_guard(source/'guard.py');current,errors=g.validate_dir(source,strict=True)
 if errors or not current or not g.development_intact(source,current):raise ValueError('CURRENT_SOURCE_NOT_INTACT')
 files={**previous['components'],**{v['path']:v['file_sha256'] for v in previous['cold_archives'].values()},**previous['development_sources']['files']};resolved={}
 for name,digest in files.items():
  origin=backup/name if (backup/name).is_file() else source/name
  if origin.is_symlink() or not origin.is_file() or sha(origin)!=digest:raise ValueError('PREVIOUS_SOURCE_BYTES_UNAVAILABLE:'+name)
  resolved[name]=origin
 output.mkdir(parents=True)
 for name,origin in resolved.items():
  p=output/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(origin.read_bytes())
 (output/'manifest.json').write_bytes((backup/'manifest.json').read_bytes());old=load_guard(output/'guard.py');m,errors=old.validate_dir(output,strict=True)
 if not m or errors or not old.development_intact(output,m):raise ValueError('RESTORED_SOURCE_NOT_INTACT')
 return {'status':'RESTORED_PREVIOUS_COPY','save_set_id':m['save_set_id'],'files':len(files)+1,'source_bytes_exact':True}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=P,default=P(__file__).resolve().parents[1]);p.add_argument('--output',type=P,required=True);args=p.parse_args()
 try:print(json.dumps(restore(args.source,args.output),ensure_ascii=False))
 except Exception as ex:print(json.dumps({'status':'REFUSED','error':str(ex)},ensure_ascii=False));raise SystemExit(1)
