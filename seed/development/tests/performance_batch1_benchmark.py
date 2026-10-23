#!/usr/bin/env python3
import argparse,pathlib,importlib.util,json,os,sys,time,statistics,platform,subprocess,shutil
sys.dont_write_bytecode=True
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);ns=p.parse_args();source=ns.source.resolve();out=ns.output.resolve();out.mkdir(parents=True,exist_ok=False)
s=importlib.util.spec_from_file_location('h',source/'development/tests/stage1_v1453.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
report={'source':str(source),'environment':{'python':sys.version,'implementation':sys.implementation.name,'platform':platform.platform(),'cpu_count':os.cpu_count()},'source_sha256':{n:h.sha(source/n) for n in ('engine.py','guard.py','manifest.json')},'mode':'no profiler; wall time through usable receipt plus canonical JSON serialization; same Python process, fresh engine module and runtime-free clone per commit; batch read first cold derived cache then five warm samples; clone/import/fixture setup excluded; OS page cache uncontrolled','model_generation':'NOT_RUN','samples':{}}
def save():
 report['summary']={k:{'median':statistics.median(v),'min':min(v),'max':max(v),'n':len(v)} for k,v in report['samples'].items() if v};(out/'performance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
def timed(key,fn):
 t=time.perf_counter();v=fn();json.dumps(v,ensure_ascii=False,separators=(',',':'),default=str);elapsed=time.perf_counter()-t;report['samples'].setdefault(key,[]).append(elapsed);save();print(key,len(report['samples'][key]),round(elapsed,4),flush=True);return v
def clone(n):return h.clone(source,out/n)
r=clone('read');a=h.load_api(r,'reads')
for i in range(6):
 v=timed('batch_read_cold' if i==0 else 'batch_read_warm',lambda:a.round_context_packet(r));assert v['readiness']['status']=='READY_WITH_LIMITATIONS'
for i in range(3):
 r=clone('transfer'+str(i));a=h.load_api(r,'transfer'+str(i));c=h.command(a,r,'account_transfer','SYNTHETIC-TRANSFER',source_account='covert',destination_account='fleet',currency='grey',amount='1.23',reason='SYNTHETIC BENCH ONLY');env=h.envelope(a,r,c)
 assert timed('transfer_commit',lambda:a.host_intent_command(r,env,'V14.90'))['status']=='SAVED'
 assert timed('transfer_original_ID_retry',lambda:a.host_intent_command(r,env,'V14.91'))['status']=='ALREADY_APPLIED'
actor='PER-HAWK-MALEN-01';sid='SYNTHETIC-BENCH-SCENE'
for i in range(3):
 r=clone('dialogue'+str(i));a=h.load_api(r,'dialogue'+str(i))
 actions=[{'type':'scene_open','scene_id':sid,'task_id':None,'family':'conversation','title':'SYNTHETIC BENCH ONLY','location_ref':'LOC-FREEPORT-XILU9','participants':[actor],'presence_mode':'remote','visible_to':['player','npc:'+actor]},{'type':'fact_append','scene_id':sid,'fact_id':'F-OPEN','subject_id':actor,'predicate':'statement','value':'固定合成对白性能夹具。','epistemic':'confirmed','source_category':'direct_observation'}]+[{'type':'knowledge_disclose','scene_id':sid,'fact_id':'F-OPEN','viewer_id':v,'channel':'heard','basis_event_id':'$current_transaction'} for v in ['player','npc:'+actor]]+[{'type':'scene_phase','scene_id':sid,'phase':'open'}]
 c=h.command(a,r,'story_setup','SYNTHETIC-SETUP',actions=actions);a.host_intent_command(r,h.envelope(a,r,c),'V14.80');ctx=a.prepare_turn(r,sid,actor,'player','固定合成对白')
 proposal={'schema':a.STORY_TURN_SCHEMA,'turn_id':'SYNTHETIC-DIALOGUE','base_identity':ctx['base_identity'],'scene_id':sid,'actor_id':actor,'viewer':'player','player_intent':'固定合成对白','intent_tags':['conversation'],'basis_refs':['fact/'+sid+'/F-OPEN'],'segments':[{'mode':'dialogue','speaker_id':actor,'text':'先核对事实，再等待指挥官选择。','basis_refs':['fact/'+sid+'/F-OPEN'],'receipt_refs':[]}],'effects':[],'updates':[],'consequences':[],'claims':[],'public_reason':'固定合成文本，无机械效果。','candidates':['询问','等待']}
 c=h.command(a,r,'story_turn',proposal['turn_id'],proposal=proposal);env=h.envelope(a,r,c)
 assert timed('dialogue_commit',lambda:a.host_intent_command(r,env,'V14.90'))['status']=='SAVED'
 timed('next_prepare_after_dialogue',lambda:a.prepare_turn(r,sid,actor,'player','继续固定合成测试'))
 assert timed('dialogue_original_ID_retry',lambda:a.host_intent_command(r,env,'V14.91'))['status']=='ALREADY_APPLIED'
r=clone('cold_guard')
for key,flag in [('cold_directory_guard_check','--check'),('guard_resume_after_check','--resume')]:
 def call():
  cp=subprocess.run([sys.executable,str(r/'guard.py'),flag],env=dict(os.environ,VOYAGER_ROOT=str(r)),text=True,capture_output=True,timeout=240);assert cp.returncode==0,cp.stderr+cp.stdout;v=json.loads(cp.stdout);assert v.get('readiness',{}).get('status','READY_WITH_LIMITATIONS')!='BLOCKED';return v
 timed(key,call)
save()
