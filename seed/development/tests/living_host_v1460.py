#!/usr/bin/env python3
"""Exact-envelope setup host test; isolated SYNTHETIC fixture, no model approval."""
import argparse,hashlib,importlib.util,json,pathlib,shutil,sys
sys.dont_write_bytecode=True
P=pathlib.Path
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def run(source,out):
 source=source.resolve();out=out.resolve();out.mkdir(parents=True,exist_ok=False);h=load(source/'development/tests/stage1_v1453.py','host_lw_h');root=h.clone(source,out/'SYNTHETIC_HOST');a=h.load_api(root,'host_lw_engine');host=load(root/'development/host_session.py','host_lw_service')
 loc='LOC-FREEPORT-XILU9';command=h.command(a,root,'story_setup','SYNTHETIC-HOST-SETUP',actions=[{'type':'life_place','location_ref':loc,'expected_revision':0,'senses':{k:'合成测试中明确创作的感官设定' for k in a.LIVING_SENSES},'conditions':{k:'合成测试已知条件' for k in a.LIVING_CONDITIONS},'visible_to':['player'],'basis_refs':['synthetic:exact-host-test']}]);env=h.envelope(a,root,command);before={n:h.sha(root/n) for n in ('state.json','tasks.json','events.jsonl','manifest.json')}
 denied=host.HostSession(root,'SYNTHETIC-DENIED');r=denied.setup(env,'V14.61');assert r['status']=='NEEDS_AUTHORIZATION' and before=={n:h.sha(root/n) for n in before}
 def authorize_exact_fixture(payload):return root.name=='SYNTHETIC_HOST' and payload==env and payload['instruction_text'].startswith('SYNTHETIC TEST ONLY:')
 allowed=host.HostSession(root,'SYNTHETIC-EXACT',authorize=authorize_exact_fixture);r=allowed.setup(env,'V14.61');assert r['status']=='SAVED';saved={n:h.sha(root/n) for n in before};retry=allowed.setup(env,'V14.62');assert retry['status']=='ALREADY_APPLIED' and saved=={n:h.sha(root/n) for n in saved}
 assert allowed.metrics['engine_loads']==1 and allowed.metrics['setup_requests']==2
 report={'status':'PASS','engine_sha256':h.sha(root/'engine.py'),'tests':{'missing_authorizer_refuses_without_write':True,'exact_authenticated_setup_commits':True,'same_retry_returns_receipt_without_replay':True,'one_engine_load':True},'scope':'SYNTHETIC only; no production approval or installed ChatGPT host claimed'};(out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);a=p.parse_args();run(a.source,a.output)
