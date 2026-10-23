#!/usr/bin/env python3
"""Restore the exact previous source files into a NEW directory; no in-place rollback."""
import argparse,hashlib,importlib.util,json,pathlib,sys
sys.dont_write_bytecode=True
P=pathlib.Path
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def restore(source,output):
 source=P(source).resolve();output=P(output).resolve()
 if output.exists() or output==source or source in output.parents:raise ValueError('NEW_EXTERNAL_OUTPUT_REQUIRED')
 m=json.loads((source/'development/evidence/step18_input_manifest.json').read_text())
 if m['save_set_id']!='SAVESET-V14.47-cdf55a13d2da9684':raise ValueError('UNSUPPORTED_ROLLBACK_BASE')
 for name,sha in m['authority_components'].items():
  if digest(source/name)!=sha:raise ValueError('NEW_GAME_FACTS_REQUIRE_COMPATIBLE_MIGRATION:'+name)
 spec=importlib.util.spec_from_file_location('rollback_guard',source/'guard.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
 current,errors=g.validate_dir(source,strict=True)
 if not current or errors or not g.development_intact(source,current):raise ValueError('CURRENT_SOURCE_NOT_INTACT:'+str(errors))
 files={**m['components'],**{v['path']:v['file_sha256'] for v in m['cold_archives'].values()},**m['development_sources']['files']};resolved={}
 for name,sha in files.items():
  origin=source/('development/HISTORICAL_README_V14.47.md' if name=='development/README.md' else name)
  if origin.is_symlink() or not origin.is_file() or digest(origin)!=sha:raise ValueError('PREVIOUS_SOURCE_BYTES_UNAVAILABLE:'+name)
  resolved[name]=origin
 output.mkdir(parents=True)
 for name,origin in resolved.items():
  p=output/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(origin.read_bytes())
 (output/'manifest.json').write_bytes((source/'development/evidence/step18_input_manifest.json').read_bytes())
 bound,errors=g.validate_dir(output,strict=True)
 if not bound or errors or not g.development_intact(output,bound):raise ValueError('RESTORED_SOURCE_INVALID:'+str(errors))
 return {'status':'RESTORED_PREVIOUS_COPY','save_set_id':m['save_set_id'],'files':len(files)+1,'game_time':m['game_time'],'original_zip_container_bytes_reproduced':False,'source_component_and_declared_development_bytes_exact':True}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=P,default=P(__file__).resolve().parent.parent);p.add_argument('--output',type=P,required=True);args=p.parse_args()
 try:print(json.dumps(restore(args.source,args.output),ensure_ascii=False))
 except Exception as ex:print(json.dumps({'status':'REFUSED','error':str(ex)},ensure_ascii=False));raise SystemExit(1)
