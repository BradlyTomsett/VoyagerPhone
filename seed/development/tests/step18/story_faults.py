# Step18 portable current-candidate regression. Adapted from test_batch_c_faults.py; runtime code is unchanged.
import sys
sys.dont_write_bytecode=True
import copy,hashlib,importlib.util,json,os,pathlib,shutil,subprocess,time,traceback
P=pathlib.Path;BASE=P(os.environ['VOYAGER_TEST_SOURCE']).resolve();OUT=P(os.environ['VOYAGER_BATCH_C_OUTPUT']).resolve();OUT.mkdir(parents=True,exist_ok=True);rows=[]
os.environ.update(VOYAGER_ROOT=str(BASE),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm');os.environ.pop('VOYAGER_DEV_SOURCE_DIR',None)
s=importlib.util.spec_from_file_location('e',BASE/'engine.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
def case(phase,unknown=False):
 name=phase+('_unknown' if unknown else '');r=OUT/name;shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));m=a.read_json(r/'manifest.json');now=m['game_time'];actions=[{'type':'entity_register','entity_id':'NPC-FAULT','name':'米拉·德里斯'},{'type':'scene_create','scene_id':'FAULT-SCENE','task_id':'TSK-MIN-OPERATIONS','family':'rescue','title':'故障隔离测试','participants':['NPC-FAULT']}];c={'schema':a.DOMAIN_COMMAND_SCHEMA,'kind':'story_transaction','command_id':'FAULT-C','base_save_set_id':m['save_set_id'],'actions':actions,'authorization':'host_intent','authorization_ref':'HOST:FAULT','actor_id':'PER-COMMANDER-01'};e={'schema':'HOST_COMMAND_INTENT_V1','command':c,'subject_id':c['actor_id'],'parent_save_set_id':m['save_set_id'],'instruction_text':'Isolated fault injection only','evidence_ref':'fixture:fault','decision':'approved','targets':a._domain_command_targets(c),'valid_from':now,'valid_until':now,'limits':a._domain_authorization_cost(c)};request=OUT/(name+'.json');request.write_text(json.dumps(e))
 worker="import os,json,pathlib,importlib.util; r=pathlib.Path(os.environ['VOYAGER_ROOT']); s=importlib.util.spec_from_file_location('e',r/'engine.py'); a=importlib.util.module_from_spec(s);s.loader.exec_module(a); a.host_intent_command(r,json.loads(pathlib.Path(os.environ['REQUEST']).read_text()),'V14.49')"
 cp=subprocess.run([sys.executable,'-c',worker],env=dict(os.environ,VOYAGER_ROOT=str(r),REQUEST=str(request),VOYAGER_COMMIT_KILL=phase),capture_output=True,text=True,timeout=240);(OUT/(name+'.stderr')).write_text(cp.stderr);assert cp.returncode==86,cp.stderr[-2500:]
 g=a._repair_guard_module(r)
 if unknown:(r/'tasks.json').write_bytes((r/'tasks.json').read_bytes()+b' ')
 before={n:a.sha256_file(r/n) for n in a.COMPONENT_FILES}
 with g.guard_lock(r):manifest,errors=g.recover_interrupted_commit(r)
 if unknown:assert manifest is None and any('UNKNOWN_MODIFICATION' in x for x in errors) and before=={n:a.sha256_file(r/n) for n in a.COMPONENT_FILES};return {'unknown_bytes_protected':True}
 assert manifest and not errors,errors;state=a.read_json(r/'state.json');committed=phase=='after_manifest';assert ('NPC-FAULT' in state['entity_registry']['entities'])==committed;assert ('FAULT-SCENE' in state['engine_runtime']['scene_registry_v1']['records'])==committed;assert not g.active_journal(r,'native_commit_journal.json');assert a.readiness_report(r)['status']=='READY_WITH_LIMITATIONS';return {'atomic_outcome':'target' if committed else 'parent','no_partial_people_or_scenes':True,'readiness':'READY_WITH_LIMITATIONS'}
for phase,unknown in [('after_component',False),('after_manifest',False),('after_component',True)]:
 try:detail=case(phase,unknown);rows.append({'phase':phase,'unknown':unknown,'status':'PASS','detail':detail});print('PASS',phase,unknown,flush=True)
 except Exception as ex:rows.append({'phase':phase,'unknown':unknown,'status':'FAIL','error':str(ex),'trace':traceback.format_exc()});print('FAIL',phase,unknown,str(ex),flush=True)
 (OUT/'results.json').write_text(json.dumps({'status':'FAIL' if any(x['status']=='FAIL' for x in rows) else 'PASS','engine_sha256':a.sha256_file(BASE/'engine.py'),'tests':rows},ensure_ascii=False,indent=2)+'\n')
raise SystemExit(1 if any(x['status']=='FAIL' for x in rows) else 0)
