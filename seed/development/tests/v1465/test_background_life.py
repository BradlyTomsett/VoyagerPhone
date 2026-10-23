#!/usr/bin/env python3
"""Read-only source checks and isolated fixture tests for ordinary NPC background scheduling."""
import argparse,os,sys,json,copy,importlib.util,tempfile,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=a.base.resolve()
os.environ.update(VOYAGER_ROOT=str(root),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm')
spec=importlib.util.spec_from_file_location('background_tests',root/'engine.py');e=importlib.util.module_from_spec(spec);sys.modules[spec.name]=e;spec.loader.exec_module(e)
s=json.loads((root/'state.json').read_text());t=json.loads((root/'tasks.json').read_text());rows=[]
def run(name,f):
 try:assert f();rows.append({'name':name,'status':'PASS'})
 except Exception as ex:rows.append({'name':name,'status':'FAIL','error':str(ex)})
rt=s['engine_runtime']['living_world_v1'];when=e.parse_iso(rt['background_routine_v1']['next_review_at']);now=e.parse_iso(s['game_time'])
run('Incomplete biographies remain incomplete',lambda:len(rt['profiles'])==16 and all(p['revision']==0 and not e._lw_complete(p) for p in rt['profiles'].values()))
run('Routine review is present in the shared event queue',lambda:any(x.get('resolver')=='npc_background_routine_v1' and x['time']==when.isoformat() for x in e.deterministic_event_queue(s,t,now,when)))
run('Routine background planning does not ask for full private biographies',lambda:e._next_ai_monitor_time(t,now,when,s) is None)
def major():
 ss=copy.deepcopy(s);eid=next(iter(rt['profiles']));ss['engine_runtime']['living_world_v1']['profiles'][eid]['major_review_required']=True
 return e._next_ai_monitor_time(t,now,when,ss)['kind']=='npc_life_profile'
run('Major NPC review remains a barrier',major)
def skip():
 try:e._lw_background_check_time(s,when+e.dt.timedelta(seconds=1))
 except e.EngineError as ex:return str(ex)=='BACKGROUND_ROUTINE_DUE_USE_SHARED_SCHEDULER'
 return False
run('Routine events cannot be silently skipped',skip)
with tempfile.TemporaryDirectory(dir=str(a.output.parent),prefix='npc_fixture_') as td:
 stage=Path(td);shutil.copyfile(root/'events.jsonl',stage/'events.jsonl');shutil.copyfile(root/'state.json',stage/'state.json');shutil.copyfile(root/'tasks.json',stage/'tasks.json');shutil.copytree(root/'archives',stage/'archives')
 ss=copy.deepcopy(s);tt=copy.deepcopy(t);ss['game_time']=when.isoformat();profiles=copy.deepcopy(rt['profiles']);accounts=copy.deepcopy(s['engine_runtime']['account_registry_v1']);event={'source':'npc_background_routine'}
 out=e._bg_resolve(stage,ss,tt,event,when)
 run('Routine review changes no profiles positions or accounts',lambda:ss['engine_runtime']['living_world_v1']['profiles']==profiles and ss['engine_runtime']['account_registry_v1']==accounts and ss['engine_runtime']['story_turns_v1']==s['engine_runtime']['story_turns_v1'] and out['reviewed_people']==16)
 before=copy.deepcopy(ss);history=(stage/'events.jsonl').read_bytes();again=e._bg_resolve(stage,ss,tt,event,when)
 run('Repeated NPC routine review is idempotent',lambda:again['status']=='ALREADY_APPLIED' and ss==before and (stage/'events.jsonl').read_bytes()==history)
result={'status':'PASS' if all(x['status']=='PASS' for x in rows) else 'FAIL','passed':sum(x['status']=='PASS' for x in rows),'total':len(rows),'checks':rows};a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False));sys.exit(0 if result['status']=='PASS' else 1)
