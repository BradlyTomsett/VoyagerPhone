import argparse,pathlib,os,sys,json,importlib.util,shutil,time,traceback,contextlib,io,concurrent.futures,subprocess
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--output',type=P,required=True);ns=p.parse_args();source=ns.source.resolve();out=ns.output.resolve();out.mkdir(parents=True,exist_ok=False)
s=importlib.util.spec_from_file_location('h',source/'development/tests/stage1_v1453.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h);a=h.load_api(source,'stage2_tests');rows=[]
def case(name,f):
 t=time.perf_counter()
 try:v=f();row={'name':name,'status':'PASS','detail':v}
 except Exception as e:row={'name':name,'status':'FAIL','error':str(e),'trace':traceback.format_exc()}
 row['seconds']=time.perf_counter()-t;rows.append(row);(out/'results.json').write_text(json.dumps({'status':'FAIL' if any(x['status']=='FAIL' for x in rows) else 'PASS','manifest_sha256':h.sha(source/'manifest.json'),'engine_sha256':h.sha(source/'engine.py'),'tests':rows},ensure_ascii=False,indent=2,default=str));print(row['status'],name,row.get('error',''),flush=True)
def clone(n):return h.clone(source,out/n)
def invoke(mod,args):
 b=io.StringIO()
 with contextlib.redirect_stdout(b):rc=mod.main(args)
 return rc,json.loads(b.getvalue())
def batch():
 with a.SnapshotContext(source) as ctx:
  r=a.round_context_packet(source);m=ctx.manifest
  assert r['save_set_id']==m['save_set_id'];assert r['source_context']['save_set_id']==m['save_set_id']
  assert all(v.get('save_set_id',m['save_set_id'])==m['save_set_id'] for v in r['results'])
  h.reject(lambda:a.round_context_packet(source,['五项余额'],audience='observer',observer_id='HAWKE'),'OBSERVER')
  r['results'][0]['value']['covert_grey']['amount']='CORRUPT'
  assert a._account_units(a.read_json(source/'state.json'),'covert','grey')==31213200
  meta,e,raw=a.read_history_raw(source/'events.jsonl');e[0]['summary']='mutation'
  assert a.read_history_view(source/'events.jsonl')[1][0]['summary']!='mutation'
  v=a.read_history_view(source/'events.jsonl')[1];h.reject(lambda:v[0].update(summary='bad'),'IMMUTABLE')
 return {'single_save_set':True,'viewer_checked':True,'public_return_isolated':True,'internal_views_immutable':True}
case('batch_viewer_and_alias_isolation',batch)
def frozen_game_facts():
 c=a.read_json(source/'development/evidence/stage3_v1455_input_contract.json')
 for n in ('tasks.json','rules.json','catalog.json','guard.py'):assert h.sha(source/n)==c['files'][n],n
 state=a.read_json(source/'state.json');state['engine_runtime'].pop('story_turns_v1')
 assert a._repair_digest(state)==a.read_json(source/'development/evidence/stage3_v1455_parent_state_digest.json')['canonical_parent_state_sha256']
 meta,events,raw=a.read_history_raw(source/'events.jsonl');n=c['logical_history_count']
 assert len(events)==n+2 and meta['next_seq']==c['history_next_seq']+2
 assert a.sha256_bytes(b'\n'.join(raw[:n])+b'\n')==c['logical_history_raw_sha256']
 assert all(e['zero_time'] for e in events[n:])
 assert {(r['file'],r['path']) for r in events[-1]['field_changes']}=={('state.json','/engine_runtime/story_turns_v1')}
 return {'original_state_exact_except_declared_reference_branch':True,'old_events_byte_exact':n,'zero_time_events':2,'guard_byte_exact':True}
case('frozen_game_facts_and_history',frozen_game_facts)

def schema():
 for cmd in [['query','当前金币余额','--detail','exact'],['turn','--mode','preview','--until','8363-12-11T12:00:00'],['routineplan','--until','8363-12-11T12:00:00'],['reportframe','--since','8363-12-10T17:20:00'],['startup']]:
  rc,small=invoke(a,cmd+['--base',str(source)]);assert rc==0,small
  rc,full=invoke(a,cmd+['--base',str(source),'--presentation','full']);assert rc==0,full
  assert small['readiness']['status']=='READY_WITH_LIMITATIONS'
  assert small['context_bytes']==len(json.dumps(small,ensure_ascii=False,separators=(',',':')).encode())
  if cmd==['startup']:assert small['context_bytes']<=3500 and small['context_budget_bytes']==3500
  # Domain keys must be byte/value equivalent after removing ONLY presentation diagnostics.
  clean={k:v for k,v in small.items() if k not in {'readiness','source_ready','presentation_version','source_context','context_bytes','context_budget_bytes','budget_exceeded','budget_status'}}
  for k,v in clean.items():assert k in full and full[k]==v,(cmd,k)
 _,tiny=invoke(a,['roundcontext','--budget-bytes','512']);assert tiny['budget_exceeded'] and tiny['budget_status']=='EXCEEDED_REQUIRES_PAGINATION'
 with a.SnapshotContext(source) as context:
  business={'value':{'readiness':{'weapons':'unknown'},'source_ready':{'business_value':'retained'}}}
  projected=a.compact_packet(business,context)
  assert projected['value']==business['value'],'Business fields with diagnostic-like names must remain unchanged'
 ref=small['source_context']['diagnostic_ref'];assert a.snapshot_diagnostics(source,ref)['readiness']['status']=='READY_WITH_LIMITATIONS'
 h.reject(lambda:a.snapshot_diagnostics(source,{**ref,'manifest_sha256':'0'*64}),'STALE')
 h.reject(lambda:a.snapshot_diagnostics(source,ref,audience='observer',observer_id='HAWKE'),'VIEWER')
 return {'compact_full_domain_equivalence':True,'final_bytes_exact':True,'hard_constraints_not_truncated':True,'version_bound_diagnostics':True}
case('compact_full_contract_and_budget',schema)
def observer_diagnostics():
 packet=a.round_context_packet(source,['当前场景'],audience='observer',observer_id='HAWKE')
 assert packet['viewer']=='observer:HAWKE'
 for value in [packet]+[invoke(a,['query','当前场景','--audience','observer','--observer-id','HAWKE','--presentation',mode,'--base',str(source)])[1] for mode in ('compact','full')]:
  raw=json.dumps(value,ensure_ascii=False)
  assert 'TSK-YUHUO' not in raw and '29398' not in raw and 'acknowledged_gaps' not in raw and 'next_blocker' not in raw,raw
  assert value['readiness']['status']=='READY_WITH_LIMITATIONS'
 for command in ('startup','startupfull','accountquery','readiness','experience','storyprojection','businessquery'):
  rc,value=invoke(a,[command,'--audience','observer','--observer-id','HAWKE','--presentation','full','--base',str(source)])
  assert rc==1 and value.get('error')=='VISIBILITY_OBSERVER_PRIVATE_ROUTE_DENIED',value
 return {'observer_batch_compact_and_full_no_private_diagnostics':True,'global_integrity_status_preserved':True,'unscoped_player_routes_denied_to_observer':True}
case('observer_diagnostics_do_not_leak_world_state',observer_diagnostics)

def mutation():
 result=[]
 for name,rel,replace_inode in [('state_same_mtime','state.json',False),('inode_replacement','state.json',True),('cold_same_mtime',next(iter(a._component_cold_archives(a.read_json(source/'manifest.json')))),False),('development','development/README.md',False),('rules_permission','rules.json',False)]:
  r=clone(name);b=h.load_api(r,name);assert b.readiness_report(r)['status']=='READY_WITH_LIMITATIONS';p=r/rel;st=p.stat();raw=p.read_bytes();idx=next((i for i,x in enumerate(raw) if x not in (9,10,13,32)),0);changed=raw[:idx]+bytes([raw[idx]^1])+raw[idx+1:]
  if replace_inode:q=p.with_name(p.name+'.swap');q.write_bytes(changed);q.replace(p)
  else:p.write_bytes(changed)
  os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns));rc,pkt=invoke(b,['query','当前金币余额','--base',str(r)]);assert rc!=0,(name,pkt);result.append(name)
 return result
case('actual_byte_cache_invalidation',mutation)
def changed_read():
 r=clone('read_changed');b=h.load_api(r,'changed');orig=b._stage2_previous_main
 def hooked(args):
  result=orig(args);p=r/'tasks.json';raw=p.read_bytes();p.write_bytes(raw+b' ');return result
 b._stage2_previous_main=hooked
 rc,pkt=invoke(b,['query','当前金币余额','--base',str(r)]);assert rc==1 and 'SNAPSHOT_CHANGED' in pkt['error'] and 'value' not in pkt,pkt
 r=clone('recovery_during_read');b=h.load_api(r,'recovery_read');orig=b._stage2_previous_main
 def hook2(args):
  result=orig(args);p=r/'.runtime/native_commit_journal.json';p.parent.mkdir(exist_ok=True);p.write_text('{}');return result
 b._stage2_previous_main=hook2
 rc,pkt=invoke(b,['query','当前金币余额','--base',str(r)]);assert rc==1 and 'value' not in pkt,pkt
 return {'whole_result_buffered_and_discarded':True,'recovery_intent_checked_at_exit':True}
case('no_mixed_snapshot_output',changed_read)
def exact_bytes_parsed():
 r=clone('transient_read_bytes');b=h.load_api(r,'transient');assert b.readiness_report(r)['status']=='READY_WITH_LIMITATIONS'
 original=P.read_bytes;target=r/'state.json';raw=original(target);changed=raw.replace(b'105498180590158',b'105498180590159');assert changed!=raw
 def transient(path):return changed if path==target else original(path)
 P.read_bytes=transient
 try:rc,pkt=invoke(b,['query','当前金币余额','--base',str(r)])
 finally:P.read_bytes=original
 assert rc==1 and 'value' not in pkt and 'BOUND' in pkt.get('error',''),pkt
 hist=r/'events.jsonl';reads=[0]
 def counted(path):
  if path==hist:reads[0]+=1
  return original(path)
 with b.SnapshotContext(r):
  P.read_bytes=counted
  try:meta,events,raws=b._stage2_history_value(hist)
  finally:P.read_bytes=original
 assert reads[0]==1,reads
 return {'transient_JSON_bytes_cannot_escape_snapshot_binding':True,'history_cache_key_binds_exact_single_parse_input':True}
case('exact_parsed_bytes_match_the_proof',exact_bytes_parsed)

def cache_faults():
 r=clone('cache_faults');b=h.load_api(r,'cache_faults');assert b.readiness_report(r)['status']=='READY_WITH_LIMITATIONS';runtime=r/'.runtime'
 for p in runtime.glob('*cache*'):p.unlink()
 (runtime/'read_semantics_v2.json').write_text('{bad');assert b.readiness_report(r)['status']=='READY_WITH_LIMITATIONS'
 shutil.rmtree(runtime)
 def call():return subprocess.run([sys.executable,str(r/'engine.py'),'roundcontext','--base',str(r)],env=dict(os.environ,VOYAGER_ROOT=str(r)),capture_output=True)
 with concurrent.futures.ThreadPoolExecutor(4) as ex:values=list(ex.map(lambda _:call(),range(4)))
 assert all(v.returncode==0 for v in values),[v.stdout.decode() for v in values]
 # Explicitly inject EACCES because this runtime may run as root, bypassing chmod.
 original=b._native_atomic_json
 def denied(*args,**kwargs):raise PermissionError('TEST optional derived cache unwritable')
 b._native_atomic_json=denied;(runtime/'read_semantics_v2.json').unlink(missing_ok=True)
 assert b.readiness_report(r)['status']=='READY_WITH_LIMITATIONS';b._native_atomic_json=original
 return {'deleted_corrupt_unwritable':True,'first_creation_concurrent_readers':4}
case('optional_cache_faults',cache_faults)
def validation_reuse():
 r=clone('proof_invalidation');b=h.load_api(r,'proof')
 with b.TransactionValidationContext(r) as ctx:
  assert b.component_source_check(r,False)['status']=='PASS';assert b.component_source_check(r,False)['status']=='PASS';assert ctx.metrics['component_proof_hits']>=1
  raw=(r/'rules.json').read_bytes();st=(r/'rules.json').stat();(r/'rules.json').write_bytes(raw.replace(b' ',b'\t',1));os.utime(r/'rules.json',ns=(st.st_atime_ns,st.st_mtime_ns));assert b.component_source_check(r,False)['status']=='FAIL'
  (r/'rules.json').write_bytes(raw)
  b._stage2_validate_tool_compile(b'x=1','tool.py');h.reject(lambda:b._stage2_validate_tool_compile(b'x=;','tool.py'),'syntax')
 assert not ctx.proofs
 return {'proof_hit_then_actual_change_revalidated':True,'compile_digest_invalidated':True,'scope_discarded':True}
case('transaction_validation_dependencies',validation_reuse)
def report():
 b=a
 with b.SnapshotContext(source):r1=b.reportframe_packet(source,since='8363-12-10T17:20:00')
 with b.SnapshotContext(source) as ctx:r2=b.reportframe_packet(source,since='8363-12-10T17:20:00');assert ctx.metrics.get('history_decodes',0)==0,ctx.metrics
 assert r1==r2
 full=b.reportframe_packet(source,since='8363-12-01T00:00:00');assert full['finance']['coverage_status']=='PARTIAL_LEGACY_UNSTRUCTURED' and full['finance']['gold_delta'] is None
 return {'warm_zero_interval_no_cold_decodes':True,'legacy_unknown_preserved':True}
case('zero_interval_report_and_legacy_coverage',report)
def parity():
 d=h.load_api(source,'stage2_dev',True)
 assert d.routineplan_packet(source,'8363-12-11T12:00:00')==a.routineplan_packet(source,'8363-12-11T12:00:00')
 rc,p1=invoke(a,['roundcontext','--base',str(source)]);rd,p2=invoke(d,['roundcontext','--base',str(source)]);assert rc==rd==0 and p1==p2
 return {'release_development_main_and_services':True}
case('development_release_parity',parity)
def write_presentation():
 outputs=[];states=[]
 for mode in ('compact','full'):
  r=clone('write_'+mode)
  cp=subprocess.run([sys.executable,str(r/'engine.py'),'session','start','--until','8363-12-10T18:20:00','--version','V14.70','--scope','TEST ONLY presentation','--presentation',mode],env=dict(os.environ,VOYAGER_ROOT=str(r)),capture_output=True,text=True,timeout=180)
  assert cp.returncode==0,cp.stderr+cp.stdout[-1500:]
  packet=json.loads(cp.stdout);assert packet['status']=='COMMITTED';outputs.append(packet);states.append(h.read(r/'state.json'))
 assert states[0]==states[1]
 small,full=outputs
 assert small['presentation_version']=='compact_v2' and 'presentation_version' not in full
 assert small['context_bytes']==len(json.dumps(small,ensure_ascii=False,separators=(',',':')).encode())
 assert len(json.dumps(small,ensure_ascii=False))<len(json.dumps(full,ensure_ascii=False))
 original=a.SnapshotContext
 def unavailable(*args,**kwargs):raise OSError('TEST optional readback unavailable')
 a.SnapshotContext=unavailable
 try:fallback=a._stage2_present_write(full,source,'compact')
 finally:a.SnapshotContext=original
 assert fallback['status']=='COMMITTED' and fallback['presentation_status']=='FULL_FALLBACK'
 return {'real_CLI_compact_full_same_state':True,'compact_bytes':small['context_bytes'],'full_json_bytes':len(json.dumps(full,ensure_ascii=False,separators=(',',':')).encode()),'presentation_failure_never_invites_gameplay_retry':True}
case('committed_write_output_contract',write_presentation)

raise SystemExit(1 if any(r['status']=='FAIL' for r in rows) else 0)
