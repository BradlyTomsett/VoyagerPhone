#!/usr/bin/env python3
"""Sequential unprofiled supplied V14.65 vs V14.66 wall-time benchmark.
Synthetic fixtures only; model wait and real ChatGPT tool transport are NOT_RUN.
"""
import argparse,ast,copy,importlib.util,json,os,pathlib,shutil,statistics,subprocess,sys,time
sys.dont_write_bytecode=True
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('--parent',type=P,required=True);p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);ns=p.parse_args();out=ns.output.resolve();out.mkdir(parents=True,exist_ok=False)

def load(path,name):
 sp=importlib.util.spec_from_file_location(name,path);a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a);return a
h=load(ns.source.resolve()/'development/tests/stage1_v1453.py','bench_helpers');rep={'schema':'FAST_PLAY_PERFORMANCE_V1','measurement':'sequential unprofiled wall time; clone/setup excluded; Python JSON encoding included; page cache not flushed; same machine','real_AI_generation':'NOT_RUN','ChatGPT_tool_transport':'NOT_CONNECTED','versions':{}}
def save(): (out/'performance.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n')
def timed(rec,key,fn):
 t=time.perf_counter();v=fn();raw=json.dumps(v,ensure_ascii=False,separators=(',',':'),default=str);dt=time.perf_counter()-t
 rec.setdefault('samples_ms',{}).setdefault(key,[]).append(round(dt*1000,3));save();print(key,round(dt*1000,2),flush=True);return v

def cli(root,argv):
 cp=subprocess.run([sys.executable,str(root/'engine.py'),*argv],env=dict(os.environ,VOYAGER_ROOT=str(root),PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=180)
 assert cp.returncode==0,cp.stdout+cp.stderr
 return json.loads(cp.stdout)
for label,src in [('V14.65',ns.parent.resolve()),('V14.66',ns.source.resolve())]:
 print(label,flush=True);rec=rep['versions'][label]={'engine_sha256':h.sha(src/'engine.py')};root=h.clone(src,out/(label+'_read'));a=h.load_api(root,'bench_'+label)
 # Fresh CLI processes: one read command vs same command, then same requested
 # prepare + overview + day-plan via 3 old commands versus one new command.
 timed(rec,'cold_cli_prepare',lambda:cli(root,['storyprepare']))
 timed(rec,'cold_cli_business',lambda:cli(root,['businessquery']))
 for i in range(3):
  fn=(lambda:[cli(root,['storyprepare']),cli(root,['roundcontext']),cli(root,['routineplan','--until','8363-12-12T08:00:00'])]) if label=='V14.65' else (lambda:cli(root,['playcontext','--until','8363-12-12T08:00:00']))
  timed(rec,'cli_prepare_overview_plan',fn)
 # Warm process APIs, same semantic work, process caches warm-up excluded.
 fn=(lambda:[a.prepare_turn(root),a.round_context_packet(root),a.routineplan_packet(root,'8363-12-12T08:00:00')]) if label=='V14.65' else (lambda:a.play_context_packet(root,until='8363-12-12T08:00:00'))
 fn()
 for i in range(5):timed(rec,'warm_api_prepare_overview_plan',fn)
 for i in range(3):
  r=h.clone(src,out/(label+'_advance_'+str(i)));b=h.load_api(r,'advance_'+label+str(i));v=timed(rec,'advance_24h_commit',lambda:b.autoadvance(r,'8363-12-12T08:00:00','V14.70','SYNTHETIC benchmark only'));assert v['status']=='SAVED',v
 # Create complete lived scene with original historical regression fixture data.
 r=h.clone(src,out/(label+'_round'));a=h.load_api(r,'round_'+label)
 tree=ast.parse((src/'development/tests/living_world_v1460.py').read_text());run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run');cls=next(n for n in run.body if isinstance(n,ast.ClassDef) and n.name=='Fixture');env={'h':h,'source':r,'out':out/(label+'_fixture'),'copy':copy};exec(compile(ast.Module(body=[cls],type_ignores=[]),'synthetic_fixture','exec'),env);Base=env['Fixture']
 # Base expects to clone the source at construction; keep fixture output separate.
 env['out'].mkdir();f=Base();a=f.a;f.setup();state=h.read(f.root/'state.json');cmd=h.command(a,f.root,'story_setup','SYNTHETIC-CONTROL',actions=[{'type':'life_control','entity_id':f.actor,'operation':'take','reason':'SYNTHETIC explicit fixture control'}]);a.host_intent_command(f.root,h.envelope(a,f.root,cmd),'V14.68')
 host=load(src/'development/host_session.py','host_'+label);expected=[]
 def authorize_exact_fixture(e):return len(expected)==1 and e==expected[0] and e['instruction_text'].startswith('SYNTHETIC TEST ONLY:')
 def reviewed_fixture(p):return {'status':'PASS','criteria':['living_prose','voice_and_knowledge','sensory_grounding','player_agency'],'source':'SYNTHETIC_FIXED_PROSE_NOT_MODEL_QUALITY'}
 session=host.HostSession(f.root,'SYNTHETIC-BENCH',authorize=authorize_exact_fixture,review_narrative=reviewed_fixture);session.prepare(scene_id=f.sid,actor_id=f.actor)
 for i in range(3):
  start=time.perf_counter();ctx=session.prepare(scene_id=f.sid,actor_id=f.actor);proposal=f.proposal('SYNTHETIC-ROUND-'+str(i),returning=i>0);proposal['elapsed_seconds']=60;proposal['base_identity']=ctx['base_identity'];cmd=h.command(a,f.root,'story_turn',proposal['turn_id'],proposal=proposal);envp=h.envelope(a,f.root,cmd);expected[:]=[envp]
  # Build fixture outside measurement; separately timed real prepare and submit.
  begin=time.perf_counter();session.prepare(scene_id=f.sid,actor_id=f.actor);result=session.submit(envp,'V14.'+str(71+i));json.dumps(result,ensure_ascii=False,separators=(',',':'));elapsed=time.perf_counter()-begin
  assert result['status']=='SAVED' and 'report' in result,result;rec.setdefault('samples_ms',{}).setdefault('warm_story_round_prepare_submit',[]).append(round(elapsed*1000,3));save();print('warm_story_round_prepare_submit',round(elapsed*1000,2),flush=True)
 for key,values in rec['samples_ms'].items():rec.setdefault('medians_ms',{})[key]=round(statistics.median(values),3)
 save()
old,new=[rep['versions'][k]['medians_ms'] for k in ('V14.65','V14.66')];rep['speedup']={k:{'old_ms':old[k],'new_ms':new[k],'factor':round(old[k]/new[k],3),'reduction_percent':round((1-new[k]/old[k])*100,1)} for k in old};save();print(json.dumps(rep['speedup'],ensure_ascii=False,indent=2),flush=True)
