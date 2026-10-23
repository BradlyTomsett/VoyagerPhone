#!/usr/bin/env python3
"""Build an independent zero-time V14.66 maintenance from supplied V14.65.
The parent is read-only. Candidate code must already be built from devsrc.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,sys
sys.dont_write_bytecode=True

def load(path,name):
    sp=importlib.util.spec_from_file_location(name,path);a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a);return a

def refresh(parent,root):
    parent=parent.resolve();root=root.resolve()
    if parent==root or parent in root.parents:raise ValueError('INDEPENDENT_CANDIDATE_REQUIRED')
    gm=load(parent/'guard.py','parent_guard');pm,errs=gm.validate_dir(parent,strict=True)
    if errs or not pm or not gm.development_intact(parent,pm):raise ValueError('INVALID_PARENT:'+str(errs))
    if pm['save_version']!='V14.65':raise ValueError('V14.65_PARENT_REQUIRED')
    for name in ('state.json','tasks.json','rules.json','catalog.json','guard.py'):
        if (parent/name).read_bytes()!=(root/name).read_bytes():raise ValueError('ZERO_TIME_CONSERVATION:'+name)
    for rel in gm.cold_archives(pm):
        if (parent/rel).read_bytes()!=(root/rel).read_bytes():raise ValueError('ARCHIVE_CONSERVATION:'+rel)
    os.environ['VOYAGER_ROOT']=str(root);a=load(root/'engine.py','accelerated_release');assert a.ENGINE_VERSION=='2.74.0'
    # The complete parent prefix is immutable, even on a refresh after new tests/docs.
    old=(parent/'events.jsonl').read_bytes().splitlines();rows=(root/'events.jsonl').read_bytes().splitlines();eid='MAINT-V1466-FAST-PLAY'
    if rows==old:
        a._append_engine_history(root/'events.jsonl',{'event_id':eid,'type':'system','subtype':'fast_play_performance_maintenance','game_time':pm['game_time'],'zero_time':True,'summary':'加速每轮读取、纯历史解码与完整验证；新增playcontext批量入口。游戏时间、账户、资产和任务不变。','changes':[],'authority_files':[],'source':'GAME ENGINE 2.74.0','parent_save_set_id':pm['save_set_id']})
    rows=(root/'events.jsonl').read_bytes().splitlines()
    if rows[1:-1]!=old[1:] or len(rows)!=len(old)+1 or json.loads(rows[-1])['event_id']!=eid:raise ValueError('HISTORY_PREFIX_CONSERVATION')
    files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'development').rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    m=a._component_write_manifest_native(root,'V14.66',pm['save_set_id'],{'from_save_set_id':pm['save_set_id'],'from_layout':'native_eight_component_v4_tiered_history','to_layout':'native_eight_component_v4_tiered_history','game_time_advanced':False,'method':'fast_play_zero_time_maintenance'},frozen_development_sources={'schema':'VOYAGER_DEV_SOURCES_V1','files':files,'build_command':'python3 development/build.py --output engine.py'})
    m['current_guide']={'path':'development/CONTINUE_V14_66.md','sha256':files['development/CONTINUE_V14_66.md'],'role':'only_current_continuation_guide'}
    (root/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    return {'status':'BUILT','save_set_id':m['save_set_id'],'game_time':m['game_time'],'parent_save_set_id':pm['save_set_id'],'zero_time':True}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);ns=p.parse_args();print(json.dumps(refresh(ns.parent,ns.candidate),ensure_ascii=False))
