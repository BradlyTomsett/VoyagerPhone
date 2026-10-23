#!/usr/bin/env python3
"""Current-parent acceptance; every transaction/fault is confined to SYNTHETIC clones."""
import argparse,copy,contextlib,importlib.util,io,json,os,pathlib,sys,time,traceback,hmac
sys.dont_write_bytecode=True
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('--source',type=P,required=True);p.add_argument('--parent',type=P,required=True);p.add_argument('--output',type=P,required=True);ns=p.parse_args();source=ns.source.resolve();parent=ns.parent.resolve();out=ns.output.resolve();out.mkdir(parents=True,exist_ok=False)
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=load(source/'development/tests/stage1_v1453.py','helper');a=h.load_api(source,'acceptance');rows=[]
def case(name,fn):
 t=time.perf_counter()
 try:row={'name':name,'status':'PASS','detail':fn()}
 except (Exception,SystemExit) as e:row={'name':name,'status':'FAIL','error':str(e),'trace':traceback.format_exc()}
 row['seconds']=time.perf_counter()-t;rows.append(row);(out/'results.json').write_text(json.dumps({'status':'PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL','engine_sha256':h.sha(source/'engine.py'),'manifest_sha256':h.sha(source/'manifest.json'),'model_generation':'NOT_RUN','tests':rows},ensure_ascii=False,indent=2,default=str));print(row['status'],name,row.get('error',''),flush=True)
def clone(n):return h.clone(source,out/n)
def command(b,r,cid):return h.command(b,r,'account_transfer',cid,source_account='covert',destination_account='fleet',currency='grey',amount='1.23',reason='SYNTHETIC TEST ONLY')
def conservation():
 old=h.load_api(parent,'parent');m,ev,raw=a.read_history_raw(source/'events.jsonl');om,oe,orr=old.read_history_raw(parent/'events.jsonl')
 for n in ('state.json','tasks.json','rules.json','catalog.json','guard.py'):assert h.sha(source/n)==h.sha(parent/n)
 assert raw[:-1]==orr and len(ev)==len(oe)+1 and m['next_seq']==om['next_seq']+1
 assert ev[-1]['zero_time'] and ev[-1]['changes']==[] and ev[-1]['subtype']=='performance_batch2_maintenance'
 assert (source/'events.jsonl').read_bytes().splitlines()[1:-1]==(parent/'events.jsonl').read_bytes().splitlines()[1:]
 assert a.readiness_report(source)['status']=='READY_WITH_LIMITATIONS'
 return {'four_authority_JSON_and_Guard_byte_exact':True,'old_logical_and_physical_history_byte_exact':len(oe),'maintenance_events':1}
case('actual_parent_conservation',conservation)
def ownership():
 for scope in (contextlib.nullcontext(),a.SnapshotContext(source),a.TransactionValidationContext(source)):
  with scope:
   m,e,r=a.read_history_view(source/'events.jsonl');mm,ee,rr=a.read_history_raw(source/'events.jsonl');assert (m,e,r)==(mm,ee,rr)
   ee[0]['summary']='BAD';ee.append({});mm['next_seq']=0;rr.clear();assert a.read_history_view(source/'events.jsonl')==(m,e,r)
   for fn in (lambda:e.append({}),lambda:e[0].update(summary='bad'),lambda:e.__init__([]),lambda:e[0].__init__({}),lambda:r.clear()):h.reject(fn,'IMMUTABLE')
   m['next_seq']=0;assert a.read_history_view(source/'events.jsonl')[0]['next_seq']!=0
 return {'no_scope_snapshot_transaction':True,'mutable_public_results_isolated':True,'private_metadata_and_readonly_nested_tree':True}
case('history_ownership',ownership)
def batch():
 d=out/'tiny';d.mkdir();hp=d/'events.jsonl'
 def init(n=2):hp.write_text(json.dumps({'record_type':'metadata','next_seq':n})+'\n'+json.dumps({'seq':1,'event_id':'OLD','x':{'y':[1]}})+'\n')
 init()
 with a.TransactionValidationContext(source) as ctx:
  with a._history_append_batch(hp):
   a._append_engine_history(hp,{'event_id':'A'})
   try:
    with a._history_append_batch(hp):a._append_engine_history(hp,{'event_id':'ROLLBACK'});raise ValueError('nested')
   except ValueError:pass
   a._append_engine_history(hp,{'event_id':'B'})
  assert ctx.metrics.get('history_full_copies',0)==0
 assert [e['event_id'] for e in a.read_history_raw(hp)[1]]==['OLD','A','B']
 before=hp.read_bytes();h.reject(lambda:a._append_engine_history(hp,{'event_id':'OLD'}),'DUPLICATE');assert hp.read_bytes()==before
 init(999);h.reject(lambda:a._history_next_seq(hp),'next_seq mismatch');init();before=hp.read_bytes()
 try:
  with a._history_append_batch(hp):a._append_engine_history(hp,{'event_id':'NO'});raise RuntimeError('outer')
 except RuntimeError:pass
 assert hp.read_bytes()==before and not a._HISTORY_APPEND_BATCHES
 try:
  with a._history_append_batch(hp):a._append_engine_history(hp,{'event_id':'NO'});hp.write_bytes(hp.read_bytes()+b' ')
 except a.EngineError as ex:assert 'SOURCE_CHANGED' in str(ex)
 else:raise AssertionError('accepted concurrent mutation')
 assert hp.read_bytes().endswith(b' ') and not a._HISTORY_APPEND_BATCHES
 return {'append_duplicate_next_seq_nested_outer_rollback_concurrent_change':True,'full_history_copies':0}
case('history_batch_faults',batch)
def archives():
 r=clone('archive');b=h.load_api(r,'archive');rel=next(n for n,v in b._component_cold_archives(h.read(r/'manifest.json')).items() if v.get('seq_start'));path=r/rel;raw=path.read_bytes();st=path.stat();changed=raw[:-1]+bytes([raw[-1]^1])
 with b.TransactionValidationContext(r):
  value=b.read_history_view(r/'events.jsonl');path.write_bytes(changed);os.utime(path,ns=(st.st_atime_ns,st.st_mtime_ns));h.reject(lambda:b.read_history_view(r/'events.jsonl'));assert b._batch_b_readiness(r)['status']=='BLOCKED';path.write_bytes(raw)
  hp=r/'events.jsonl';original=hp.read_bytes();escaped=original.replace(b'"archive_ref"',b'"archive\\u005fref"',1);assert escaped!=original;hp.write_bytes(escaped);assert b.read_history_view(hp)==value
  path.write_bytes(changed);h.reject(lambda:b.read_history_view(hp));path.write_bytes(raw);hp.write_bytes(original)
 with b.SnapshotContext(r):
  orig=P.read_bytes;counts={}
  def tracked(p):counts[str(p)]=counts.get(str(p),0)+1;return orig(p)
  P.read_bytes=tracked
  try:b.read_history_view(r/'events.jsonl')
  finally:P.read_bytes=orig
  assert counts[str(path)]==1 and counts[str(r/'events.jsonl')]==1
 return {'same_size_mtime_corruption_rejected':True,'escaped_JSON_dependency_bound':True,'one_read_per_history_and_archive_input':True}
case('archive_byte_binding',archives)
def static():
 d=out/'static';d.mkdir();path=d/'test.py';path.write_bytes(b'x=1\n')
 with a.TransactionValidationContext(source) as tx:
  a._stage2_static_cache.clear();a._stage2_validate_tool_compile(path.read_bytes(),str(path));a._stage2_validate_tool_compile(path.read_bytes(),'another.py');assert tx.metrics['compile_proof_hits']==1
  st=path.stat();path.write_bytes(b'x=;\n');os.utime(path,ns=(st.st_atime_ns,st.st_mtime_ns));h.reject(lambda:a._stage2_validate_tool_compile(path.read_bytes(),str(path)),'syntax');path.write_bytes(b'x=2\n');a._stage2_validate_tool_compile(path.read_bytes(),str(path))
  before=tx.metrics['compile_executions'];a._stage2_validate_tool_compile(path.read_bytes(),str(path),optimize=1);assert tx.metrics['compile_executions']==before+1
  rule=a._STAGE2_COMPILE_RULE_VERSION;a._STAGE2_COMPILE_RULE_VERSION='fixture';a._stage2_validate_tool_compile(path.read_bytes(),str(path));a._STAGE2_COMPILE_RULE_VERSION=rule
  a._stage2_static_cache.clear();path.write_text('def f():pass\n');assert a._v130_ast_structure_report(path)['status']=='PASS';assert a._v130_ast_structure_report(path)['status']=='PASS';assert tx.metrics['ast_proof_hits']==1
  st=path.stat();path.write_text('def f();pass\n');os.utime(path,ns=(st.st_atime_ns,st.st_mtime_ns));assert a._v130_ast_structure_report(path)['status']=='FAIL'
  path.write_text('def f():pass\ndef f():pass\n');assert a._v130_ast_structure_report(path)['status']=='FAIL';path.write_text('def f():pass\ndef g():pass\n');assert a._v130_ast_structure_report(path)['status']=='PASS'
  rule=a._STAGE2_AST_RULE_VERSION;a._STAGE2_AST_RULE_VERSION='fixture';before=tx.metrics['ast_parse_executions'];assert a._v130_ast_structure_report(path)['status']=='PASS';assert tx.metrics['ast_parse_executions']==before+1;a._STAGE2_AST_RULE_VERSION=rule
  key=a._stage2_static_key('ast',path.read_bytes(),rule);a._stage2_static_cache[key]={'corrupt':True};assert a._v130_ast_structure_report(path)['status']=='PASS';return copy.deepcopy(tx.metrics)
case('static_content_options_rules_corruption_repair',static)
def transaction():
 r=clone('transaction');b=h.load_api(r,'tx');c=command(b,r,'SYNTHETIC-PROOF');env=h.envelope(b,r,c)
 with b.TransactionValidationContext(r) as ctx:
  result=b.host_intent_command(r,env,'V14.90');assert result['status']=='SAVED' and result.get('presentation_status') is None,result
  assert ctx.stage_evidence and ctx.published_evidence and ctx.metrics.get('published_readiness_proof_hits',0)>0
  original_compact=b.compact_packet;projections=[0]
  def projection(*args,**kw):projections[0]+=1;return original_compact(*args,**kw)
  b.compact_packet=projection
  try:
   cached=b._stage2_present_write(result,r,'compact');assert projections[0]==0 and cached['save_set_id']==result['save_set_id']
   stale_compact={**result,'save_set_id':'SAVESET-OLD'};assert b._stage2_present_write(stale_compact,r,'compact')['presentation_status']=='RESULT_VERSION_ALREADY_ADVANCED'
  finally:b.compact_packet=original_compact
  assert ctx.metrics.get('history_full_copies',0)==0
  risk=b._risk_window_report;calls=[0]
  def counted(s):calls[0]+=1;return risk(s)
  b._risk_window_report=counted;optimized=b._batch_b_readiness(r);assert calls[0]==0
  proof=ctx.published_evidence;ctx.published_evidence=None;full=b._batch_b_readiness(r);ctx.published_evidence=proof;assert optimized==full and calls[0]==1;b._risk_window_report=risk
  before={n:h.sha(r/n) for n in b.COMPONENT_FILES}
  original=b.SnapshotContext
  def unavailable(*args,**kw):raise OSError('SYNTHETIC display failure')
  b.SnapshotContext=unavailable
  try:fallback=b._stage2_present_write({k:v for k,v in result.items() if k!='presentation_version'},r,'compact')
  finally:b.SnapshotContext=original
  assert fallback['committed'] and fallback['command_id']==c['command_id'] and fallback['status']=='SAVED' and fallback['presentation_status']=='FULL_FALLBACK'
  retry=b.host_intent_command(r,env,'V14.91');assert retry['status']=='ALREADY_APPLIED' and retry['receipt']['event_id']==result['receipt']['event_id'];assert before=={n:h.sha(r/n) for n in b.COMPONENT_FILES}
  old={**result,'save_set_id':'SAVESET-OLD','presentation_version':None};assert b._stage2_present_write(old,r,'compact')['presentation_status']=='RESULT_VERSION_ALREADY_ADVANCED'
  for rel,inode in [('state.json',False),('tasks.json',True),('development/README.md',False)]:
   path=r/rel;raw=path.read_bytes();st=path.stat();i=raw.find(b' ');i=i if i>=0 else 0;changed=raw[:i]+(b'\t' if raw[i:i+1]==b' ' else bytes([raw[i]^1]))+raw[i+1:]
   if inode:q=path.with_name(path.name+'.swap');q.write_bytes(changed);q.replace(path)
   else:path.write_bytes(changed)
   os.utime(path,ns=(st.st_atime_ns,st.st_mtime_ns));assert ctx.readiness_reuse(r) is None and b._batch_b_readiness(r)['status']=='BLOCKED';path.write_bytes(raw);os.chmod(path,st.st_mode)
  metrics=copy.deepcopy(ctx.metrics)
 assert not ctx.proofs and ctx.published_evidence is None
 # Destructive recovery-intent injection owns a DIFFERENT clone, never the retry fixture.
 jroot=clone('active_journal');japi=h.load_api(jroot,'journal');j=jroot/'.runtime/native_commit_journal.json';j.parent.mkdir(exist_ok=True);j.write_text('{}')
 assert japi._batch_b_readiness(jroot)['status']=='BLOCKED';japi._stage2_present_write({'status':'SAVED','committed':True,'command_id':'ORIGINAL'},jroot,'compact')
 assert j.exists() and j.read_text()=='{}'
 return {'metrics':metrics,'full_report_equivalence':True,'published_semantic_risk_calls':0,'missing_evidence_runs_full_check':True,'stale_bytes_inode_development_and_journal_blocked':True,'original_ID_after_display_failure_exactly_once':True,'version_separation':True}
case('transaction_proof_boundaries_and_receipts',transaction)
def cli():
 r=clone('cli');b=h.load_api(r,'cli');c=command(b,r,'SYNTHETIC-CLI');env=h.envelope(b,r,c);key=os.urandom(32);(r/'.runtime').mkdir(exist_ok=True);(r/'.runtime/host_gateway.key').write_bytes(key);env['received_at_unix']=time.time();env['_gateway_proof']=hmac.new(key,json.dumps(env,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode(),'sha256').hexdigest();readfd,writefd=os.pipe();os.write(writefd,json.dumps(env).encode());os.close(writefd)
 original=b.compact_packet;count=[0]
 def compact(*args,**kw):count[0]+=1;return original(*args,**kw)
 b.compact_packet=compact;stream=io.StringIO()
 with contextlib.redirect_stdout(stream):rc=b.main(['hostinvoke','--intent-fd',str(readfd),'--version','V14.90'])
 result=json.loads(stream.getvalue());assert rc==0 and result['status']=='SAVED' and count[0]==1,result;assert result['context_bytes']==len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode());return {'projection_count':1,'final_JSON_bytes':result['context_bytes']}
case('real_signed_pipe_CLI_projects_once',cli)
def dev():
 d=h.load_api(source,'dev',True);assert d.round_context_packet(source)==a.round_context_packet(source);assert d.ENGINE_VERSION==a.ENGINE_VERSION=='2.69.0';return True
case('development_release_parity',dev)
raise SystemExit(1 if any(r['status']=='FAIL' for r in rows) else 0)
