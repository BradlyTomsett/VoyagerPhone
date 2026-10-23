#!/usr/bin/env python3
"""Real content upgrade publication killed in subprocess; clone-only synthetic input."""
import pathlib,os,sys,json,importlib.util,argparse,copy,subprocess,time,traceback
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);ns=p.parse_args();source=ns.source.resolve();out=ns.output.resolve();out.mkdir(parents=True,exist_ok=False)
s=importlib.util.spec_from_file_location('h',source/'development/tests/stage1_v1453.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
prepared=h.clone(source,out/'prepared');a=h.load_api(prepared,'content_fault_setup');package=h.read(source/'development/examples/content_v2/demo_adjutant_1_0_0.json');plan=a.content_upgrade_preview(prepared,package);command=h.command(a,prepared,'content_upgrade','SYNTHETIC-INSTALL',package=package,plan=plan);a.host_intent_command(prepared,h.envelope(a,prepared,command),'V14.60')
package=h.read(source/'development/examples/content_v2/demo_adjutant_1_1_0.json');plan=a.content_upgrade_preview(prepared,package);command=h.command(a,prepared,'content_upgrade','SYNTHETIC-UPGRADE-FAULT',package=package,plan=plan);env=h.envelope(a,prepared,command);request=out/'synthetic_upgrade_request.json';request.write_text(json.dumps(env,ensure_ascii=False))
worker="""import os,json,pathlib,importlib.util
r=pathlib.Path(os.environ['VOYAGER_ROOT']);s=importlib.util.spec_from_file_location('h',r/'development/tests/stage1_v1453.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h);a=h.load_api(r);a.host_intent_command(r,json.loads(pathlib.Path(os.environ['CONTENT_FAULT_REQUEST']).read_text()),'V14.61')
"""
rows=[]
for phase,unknown in [('after_component',False),('after_manifest',False),('after_component',True)]:
 name=phase+('_unknown' if unknown else '');started=time.perf_counter()
 try:
  r=h.clone(prepared,out/name);a=h.load_api(r,name);before_balance=a._five_account_balances(a.read_json(r/'state.json'));cp=subprocess.run([sys.executable,'-c',worker],env=dict(os.environ,VOYAGER_ROOT=str(r),CONTENT_FAULT_REQUEST=str(request),VOYAGER_COMMIT_KILL=phase),capture_output=True,text=True,timeout=240);assert cp.returncode==86,cp.stderr[-2000:]
  if unknown:(r/'catalog.json').write_bytes((r/'catalog.json').read_bytes()+b' ')
  before={n:h.sha(r/n) for n in a.COMPONENT_FILES};g=a._repair_guard_module(r)
  with g.guard_lock(r):m,errors=g.recover_interrupted_commit(r)
  if unknown:
   assert not m and any('UNKNOWN_MODIFICATION' in s for s in errors);assert before=={n:h.sha(r/n) for n in a.COMPONENT_FILES};detail={'unknown_catalog_bytes_preserved':True}
  else:
   assert m and not errors,errors;target=phase=='after_manifest';reg=a.read_json(r/'catalog.json')['content_versions_v2']['packages']['demo.adjutant'];assert reg['active_version']==('1.1.0' if target else '1.0.0');assert ('1.1.0' in reg['versions'])==target;assert a._five_account_balances(a.read_json(r/'state.json'))==before_balance
   stability_refusal=False;unchanged={n:h.sha(r/n) for n in a.COMPONENT_FILES}
   try:result=a.host_intent_command(r,env,'V14.62')
   except a.EngineError as ex:
    if str(ex)!='SOURCE_CHANGED_DURING_COMPONENT_CHECK':raise
    assert unchanged=={n:h.sha(r/n) for n in a.COMPONENT_FILES}
    with g.guard_lock(r):stable,errs=g.validate_dir(r,strict=True)
    assert stable and not errs and g.development_intact(r,stable) and not g.active_journal(r,'native_commit_journal.json');stability_refusal=True;result=a.host_intent_command(r,env,'V14.62')
   assert result['status']==('ALREADY_APPLIED' if target else 'SAVED');events=a.read_history_raw(r/'events.jsonl')[1];assert len([x for x in events if x.get('command_id')==command['command_id']])==1;assert a.run_checks(r,full=True)['status']=='PASS'
   detail={'recovered_to':'target' if target else 'parent','versions_and_receipt_atomic':True,'original_retry_once':True,'world_balances_unchanged':True,'source_stability_refusal_then_separate_Guard_validated_retry':stability_refusal}
  row={'name':name,'status':'PASS','detail':detail}
 except Exception as ex:row={'name':name,'status':'FAIL','error':str(ex),'trace':traceback.format_exc()}
 row['seconds']=time.perf_counter()-started;rows.append(row);(out/'results.json').write_text(json.dumps({'schema':'STAGE4_CONTENT_FAULTS_V1','status':'FAIL' if any(r['status']=='FAIL' for r in rows) else 'PASS','manifest_sha256':h.sha(source/'manifest.json'),'engine_sha256':h.sha(source/'engine.py'),'tests':rows},ensure_ascii=False,indent=2));print(row['status'],name,row.get('error',''),flush=True)
raise SystemExit(1 if any(r['status']=='FAIL' for r in rows) else 0)
