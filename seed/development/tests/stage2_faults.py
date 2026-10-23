#!/usr/bin/env python3
"""Current-version native commit interruption matrix; isolated fixtures only."""
import argparse,pathlib,sys,os,json,subprocess,importlib.util,time,traceback
sys.dont_write_bytecode=True
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);ns=p.parse_args();source=ns.source.resolve();out=ns.output.resolve();out.mkdir(parents=True,exist_ok=False)
s=importlib.util.spec_from_file_location('h',source/'development/tests/stage1_v1453.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h);rows=[]
worker="""import os,pathlib,importlib.util,json
r=pathlib.Path(os.environ['VOYAGER_ROOT']);s=importlib.util.spec_from_file_location('h',r/'development/tests/stage1_v1453.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h);a=h.load_api(r);p=h.command(a,r,'account_transfer','TEST-STAGE2-FAULT',source_account='covert',destination_account='fleet',currency='grey',amount='1.23',reason='TEST ONLY interruption');a.host_intent_command(r,h.envelope(a,r,p),'V14.90')
"""
for phase,unknown in [(x,False) for x in ['after_journal','after_component','after_manifest','after_receipt','after_cleanup']]+[('after_component',True)]:
 name=phase+('_unknown' if unknown else '');t=time.perf_counter()
 try:
  r=h.clone(source,out/name);a=h.load_api(r,name);initial=a.read_json(r/'manifest.json');g=a._repair_guard_module(r)
  cp=subprocess.run([sys.executable,'-c',worker],env=dict(os.environ,VOYAGER_ROOT=str(r),VOYAGER_COMMIT_KILL=phase),capture_output=True,text=True,timeout=180)
  assert cp.returncode==86,cp.stderr[-2000:]+cp.stdout[-1000:]
  j=r/'.runtime/native_commit_journal.json';oldjournal=j.read_bytes() if j.exists() else None
  if unknown:(r/'tasks.json').write_bytes((r/'tasks.json').read_bytes()+b' ')
  before={n:h.sha(r/n) for n in a.COMPONENT_FILES}
  with g.guard_lock(r):
   m,errors=g.recover_interrupted_commit(r) if j.exists() else g.validate_dir(r,strict=True)
  if unknown:
   assert not m and any('UNKNOWN_MODIFICATION' in x for x in errors),errors
   assert before=={n:h.sha(r/n) for n in a.COMPONENT_FILES};detail={'unknown_bytes_preserved':True}
  else:
   assert m and not errors,errors;target=phase in ('after_manifest','after_receipt','after_cleanup');state=a.read_json(r/'state.json');assert a._account_units(state,'covert','grey')==(31200900 if target else 31213200)
   assert (m['save_set_id']!=initial['save_set_id'])==target
   assert not g.active_journal(r,'native_commit_journal.json')
   if target and oldjournal is not None:
    identities={n:h.sha(r/n) for n in a.COMPONENT_FILES};j.write_bytes(oldjournal)
    with g.guard_lock(r):again,errs=g.recover_interrupted_commit(r)
    assert again and not errs,errs
    assert identities=={n:h.sha(r/n) for n in a.COMPONENT_FILES} and not g.active_journal(r,'native_commit_journal.json')
   assert a.readiness_report(r)['status']=='READY_WITH_LIMITATIONS'
   # Exact retry uses the ORIGINAL base and command payload, not a newly invented ID.
   p={'schema':a.DOMAIN_COMMAND_SCHEMA,'command_id':'TEST-STAGE2-FAULT','base_save_set_id':initial['save_set_id'],'kind':'account_transfer','actor_id':'PER-COMMANDER-01','authorization':'host_intent','authorization_ref':'HOST:TEST-STAGE2-FAULT','source_account':'covert','destination_account':'fleet','currency':'grey','amount':'1.23','reason':'TEST ONLY interruption'}
   if target:
    result=a.host_intent_command(r,h.envelope(a,r,p),'V14.91');assert result['status']=='ALREADY_APPLIED'
   detail={'outcome':'target' if target else 'parent','whole_account_transfer':True,'completed_old_journal_no_replay':target and oldjournal is not None,'retry_same_receipt':target}
  row={'name':name,'status':'PASS','detail':detail}
 except Exception as e:row={'name':name,'status':'FAIL','error':str(e),'trace':traceback.format_exc()}
 row['seconds']=time.perf_counter()-t;rows.append(row);print(row['status'],name,row.get('error',''),flush=True)
 (out/'results.json').write_text(json.dumps({'status':'FAIL' if any(x['status']=='FAIL' for x in rows) else 'PASS','manifest_sha256':h.sha(source/'manifest.json'),'engine_sha256':h.sha(source/'engine.py'),'tests':rows},ensure_ascii=False,indent=2))
raise SystemExit(1 if any(x['status']=='FAIL' for x in rows) else 0)
