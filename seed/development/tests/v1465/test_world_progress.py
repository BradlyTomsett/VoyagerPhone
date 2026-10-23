#!/usr/bin/env python3
"""Full world chronology in an isolated copy, preserving all original hazard clocks."""
import os,sys,json,shutil,argparse,tempfile,importlib.util
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='world_chronology_',dir=str(a.output.resolve().parent)) as td:
 root=Path(td)/'world';shutil.copytree(a.base.resolve(),root,ignore=shutil.ignore_patterns('.runtime','__pycache__'))
 os.environ.update(VOYAGER_ROOT=str(root),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm')
 spec=importlib.util.spec_from_file_location('world_chronology',root/'engine.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);rows=[];checkpoint=None
 for version,target in [('V14.66','8363-12-12T08:00:00'),('V14.67','8363-12-13T08:00:00')]:
  r=m.autoadvance(root,target,version,'Isolated world chronology test');rows.append(r)
  if r.get('status') not in ('SAVED','COMMITTED'):
   meta=m._read_turn_session_meta(r['session_id'],root);stage=m._validated_turn_session_stage(meta,r['session_id'],root);cs=m.read_json(stage/'state.json');ct=m.read_json(stage/'tasks.json')
   checkpoint={'game_time':cs['game_time'],'business_closes':list(cs['engine_runtime']['business_runtime_v1']['businesses']['YUHUO']['settlements']),'npc_background_reviews':list(cs['engine_runtime']['living_world_v1']['background_routine_v1']['reviews']),'accounts_integrity':m.accounts_integrity_report(cs),'business_integrity':m.business_integrity_report(cs,ct,stage),'recoverable':bool(r.get('recovery_checkpoint'))}
   break
 state=m.read_json(root/'state.json');full=m.run_checks(root,full=True);coverage=m._scheduler_coverage(state,m.read_json(root/'tasks.json'))
 expected=rows[-1].get('semantic_barrier',{}).get('kind')=='hazard' and rows[-1].get('semantic_barrier',{}).get('event',{}).get('template_id')=='unidentified_probe'
 ok=full['status']=='PASS' and expected and state['game_time']=='8363-12-12T08:00:00' and checkpoint and len(checkpoint['business_closes'])==3 and len(checkpoint['npc_background_reviews'])==2 and checkpoint['business_integrity']['status']=='PASS' and checkpoint['accounts_integrity']['status']=='PASS'
 out={'status':'PASS' if ok else 'FAIL','scenario':'isolated_copy_not_official_save','results':rows,'committed_test_time':state['game_time'],'recoverable_checkpoint':checkpoint,'full_check':full,'coverage':coverage,'business_closes':list(state['engine_runtime']['business_runtime_v1']['businesses']['YUHUO']['settlements']),'original_hazard_preserved':expected}
 a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps({'status':out['status'],'committed_test_time':out['committed_test_time'],'recoverable_checkpoint':checkpoint},ensure_ascii=False));sys.exit(0 if ok else 1)
