#!/usr/bin/env python3
"""Unprofiled I/O counts without writing sample records inside measured scope."""
import argparse,ast,copy,importlib.util,json,os,pathlib,shutil,sys,time
sys.dont_write_bytecode=True
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--performance-root',type=P,required=True);p.add_argument('--output',type=P,required=True);ns=p.parse_args();source=ns.source.resolve();perf=ns.performance_root.resolve();out=ns.output.resolve();out.mkdir(parents=True,exist_ok=False)
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
# Reuse precisely the instrumenter shipped with the timing companion. The
# supplied operation does no benchmark report writes; records are saved after it.
module=ast.parse((P(__file__).parent/'batch2_followup_benchmark.py').read_text());function=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='io_measured');exec(compile(ast.Module(body=[function],type_ignores=[]),str(P(__file__)), 'exec'))
h=load(source/'development/tests/stage1_v1453.py','h');result={'schema':'BATCH2_IO_CLEAN_V1','scope':'current Python process file streams/fsync; benchmark records written strictly after measurement; Guard subprocess not instrumented; OS block output separately reported; n=1 per operation/version on existing warmed object pools','samples':[]}
for label in ['V14.58','V14.59']:
 r=perf/(label+'_round_1');a=h.load_api(r,'io_'+label);a.ensure_source_ready(r)
 command=h.command(a,r,'account_transfer','SYNTHETIC-IO-MEASUREMENT',source_account='covert',destination_account='fleet',currency='grey',amount='1.23',reason='SYNTHETIC I/O measurement');envelope=h.envelope(a,r,command)
 response,counts=io_measured(a,lambda:a.host_intent_command(r,envelope,'V14.84'));assert response['status']=='SAVED'
 result['samples'].append({'version':label,'kind':'transfer',**counts})
 home=r/'.runtime/consistency_repairs/SYNTHETIC-IO-CLEAN';manifest=h.read(r/'manifest.json')
 def repair():a._repair_snapshot_copy(r,home/'parent',manifest);a._repair_snapshot_copy(r,home/'target',manifest)
 _,counts=io_measured(a,repair);result['samples'].append({'version':label,'kind':'repair_two_snapshots',**counts});(out/'io.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('PASS',label,'clean I/O',flush=True)
result['status']='PASS';(out/'io.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
