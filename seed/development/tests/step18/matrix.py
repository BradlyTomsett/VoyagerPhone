import sys
sys.dont_write_bytecode=True
import copy,hashlib,importlib.util,json,os,pathlib,shutil,time,traceback
P=pathlib.Path;BASE=P(os.environ['VOYAGER_TEST_SOURCE']);OUT=P(os.environ['VOYAGER_STEP18_OUTPUT']);OUT.mkdir();rows=[]
def load(path):
 s=importlib.util.spec_from_file_location('m'+str(time.time_ns()),path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
a=load(BASE/'engine.py');g=load(BASE/'guard.py')
def test(name,fn):
 try:detail=fn();rows.append({'name':name,'status':'PASS','detail':detail})
 except Exception as ex:rows.append({'name':name,'status':'FAIL','error':str(ex),'trace':traceback.format_exc()})
 print(rows[-1]['status'],name,flush=True);(OUT/'results.json').write_text(json.dumps({'status':'FAIL' if any(x['status']=='FAIL' for x in rows) else 'PASS','tests':rows},ensure_ascii=False,indent=2)+'\n')
def clone(n):
 r=OUT/n;shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));return r
def rebind(r):
 m=a.read_json(r/'manifest.json');a._component_write_manifest_native(r,m['save_version'],m.get('parent_save_set_id'),m.get('migration_lineage'))
def reject(fn):
 try:fn()
 except Exception:return
 raise AssertionError('expected rejection')
def source():
 assert not g.validate_dir(BASE)[1]
 for name,fn in [('missing',lambda r:(r/'tasks.json').unlink()),('engine',lambda r:(r/'engine.py').write_bytes((r/'engine.py').read_bytes()+b'\n# changed\n')),('guard',lambda r:(r/'guard.py').write_bytes((r/'guard.py').read_bytes()+b'\n# changed\n'))]:
  r=clone('source_'+name);fn(r);assert g.validate_dir(r)[1],name
 r=clone('development');p=r/'development/tests/step18/common.py';p.write_text(p.read_text()+'\n#changed\n');assert not g.development_intact(r,a.read_json(r/'manifest.json'))
 return 'valid source accepted; missing component, changed tools, changed materialized development rejected'
test('source_binding_and_missing_members',source)
def history():
 for name,mode in [('duplicate','id'),('cold_missing','missing'),('cold_payload','payload')]:
  r=clone(name)
  if mode=='id':
   lines=(r/'events.jsonl').read_bytes().splitlines();e=json.loads(lines[-1]);e['event_id']=json.loads(lines[-2])['event_id'];lines[-1]=json.dumps(e).encode();(r/'events.jsonl').write_bytes(b'\n'.join(lines)+b'\n');rebind(r)
  else:
   p=next((r/'archives').glob('history*'))
   if mode=='missing':p.unlink()
   else:
    data=p.read_bytes();p.write_bytes(data[:20]+bytes([data[20]^1])+data[21:])
  try:report=a.readiness_report(r)
  except (FileNotFoundError,OSError):
   assert mode=='missing' and g.validate_dir(r)[1]
  else:assert report['status']=='BLOCKED',name
 return 'duplicate event ID, missing epoch and corrupted compressed payload refused; missing file may raise explicit file exception'
test('logical_history_damage_is_blocking',history)
def prices():
 request={'item_id':'SUPPLY-FOOD','unit':'包','quantity':1,'currency':'gold','transaction_type':'purchase'};q=a.calculate_price_quote(request,BASE);assert q['status']=='VALID' and q['authorized'] is False,q
 missing=a.calculate_price_quote({**request,'item_id':'UNKNOWN-UNPRICED'},BASE);assert missing['status']!='VALID'
 bad=a.calculate_price_quote({**request,'unit':'艘'},BASE);assert bad['status']!='VALID'
 docs=a._pricing_documents(BASE);docs['state']['game_time']='8363-12-02T22:45:01';reject(lambda:a.validate_price_quote(q,BASE,docs))
 docs=a._pricing_documents(BASE);ranges=[x for x in a._price_records(docs).values() if x['price_kind']=='reference_range']
 seen=[]
 for row in ranges:
  p={'price_id':row['price_id'],'unit':row['unit'],'quantity':1,'currency':row['currency'],'region':row.get('scope',{}).get('region'),'transaction_type':'purchase'}
  res=a.calculate_price_quote(p,BASE)
  if res['status']=='PROVISIONAL':seen.append(row['price_id']);break
 assert seen,'no usable reference-range fixture'
 return {'fixed_quote_no_authorization':True,'unpriced_and_wrong_unit_rejected':True,'old_time_quote_rejected':True,'unagreed_reference_range':seen}
test('pricing_fixed_range_missing_unit_stale',prices)
def time_edges():
 s=a.read_json(BASE/'state.json');t=a.read_json(BASE/'tasks.json');now=a.parse_iso(s['game_time']);due=a.parse_iso('8363-12-03T00:20:00');queue=a.deterministic_task_queue(t,now,due,s);assert queue,queue
 target=queue[0];task=next(x for x in t['active_tasks'] if x['task_id']==target['task_id']);other=copy.deepcopy(task);other['task_id']='TSK-ISOLATED-SAME-TIME';t['active_tasks'].append(other)
 assert not a.deterministic_task_queue(t,now,due-a.dt.timedelta(seconds=1),s)
 at=a.deterministic_task_queue(t,now,due,s);assert len([x for x in at if x['time']=='8363-12-03T00:20:00'])>=2
 barrier={'kind':'semantic'};assert not a._deterministic_event_precedes_barrier({'resolver':target['resolver']},due,due,barrier);assert a._deterministic_event_precedes_barrier({'resolver':'progress_rule_v1'},due,due,barrier)
 return {'before_due':0,'same_instant_candidates':len(at),'semantic_barrier_requires_decision':True,'scope':'queue and boundary contract; no live settlement/time advance'}
test('second_boundaries_same_time_and_semantic_stop',time_edges)
def cached_receipt():
 r=clone('receipt_eviction');b=load(r/'engine.py');state=b.read_json(r/'state.json');b._domain_runtime(state,True)['max_receipts']=1;b._write_authority_json(r/'state.json',state);rebind(r);m=b.read_json(r/'manifest.json');now=m['game_time'];c={'schema':b.DOMAIN_COMMAND_SCHEMA,'command_id':'EVICT-REPLAY','kind':'create_task','base_save_set_id':m['save_set_id'],'task':{'task_id':'TSK-EVICT-REPLAY','type':'manual','title':'隔离幂等缓存测试','status':'queued'},'authorization':'host_intent','authorization_ref':'HOST:EVICT','actor_id':'PER-COMMANDER-01'};e={'schema':'HOST_COMMAND_INTENT_V1','command':c,'subject_id':c['actor_id'],'parent_save_set_id':m['save_set_id'],'instruction_text':'Isolated task; exact one action','evidence_ref':'fixture:EVICT','decision':'approved','targets':b._domain_command_targets(c),'limits':b._domain_authorization_cost(c),'valid_from':now,'valid_until':now}
 result=b.host_intent_command(r,e,'V14.49');assert result['status']=='SAVED'
 e2=copy.deepcopy(e);m=b.read_json(r/'manifest.json');e2['parent_save_set_id']=e2['command']['base_save_set_id']=m['save_set_id'];e2['command']['command_id']='EVICT-SECOND';e2['command']['task']['task_id']='TSK-EVICT-SECOND';e2['targets']=b._domain_command_targets(e2['command']);assert b.host_intent_command(r,e2,'V14.50')['status']=='SAVED';state=b.read_json(r/'state.json');assert 'EVICT-REPLAY' not in state['engine_runtime']['domain_command_runtime']['applied']
 before={n:b.sha256_file(r/n) for n in b.COMPONENT_FILES};assert b.host_intent_command(r,e,'V14.51')['status']=='ALREADY_APPLIED';assert before=={n:b.sha256_file(r/n) for n in b.COMPONENT_FILES}
 changed=copy.deepcopy(e);changed['command']['task']['title']='different';reject(lambda:b.host_intent_command(r,changed,'V14.51'))
 return 'permanent event receipt survives in-state hot receipt eviction; conflicting payload denied'
test('idempotence_after_receipt_cache_eviction',cached_receipt)
raise SystemExit(1 if any(x['status']=='FAIL' for x in rows) else 0)
