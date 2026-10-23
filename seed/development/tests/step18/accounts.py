# Step18 portable current-candidate regression. Adapted from test_batch_b.py; runtime code is unchanged.
#!/usr/bin/env python3
"""Batch B behavioral verification. All writes are confined to isolated clones."""
import copy,gzip,hashlib,importlib.util,json,os,pathlib,shutil,sys,time
P=pathlib.Path;BASE=P(os.environ.get('VOYAGER_TEST_SOURCE',str(P(__file__).resolve().parents[2]))).resolve();OUT=P(os.environ.get('VOYAGER_BATCH_B_OUTPUT','batch_b/audit/regression')).resolve();OUT.mkdir(parents=True,exist_ok=True);ROWS=[]
os.environ.update(PYTHONDONTWRITEBYTECODE='1',VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm')
def api(root):
 os.environ['VOYAGER_ROOT']=str(root);spec=importlib.util.spec_from_file_location('engine_'+str(time.time_ns()),root/'engine.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a);return a
a=api(BASE)
def record(name,fn):
 try:detail=fn();ROWS.append({'name':name,'status':'PASS','detail':detail});print('PASS',name,flush=True)
 except Exception as ex:ROWS.append({'name':name,'status':'FAIL','error':str(ex)});print('FAIL',name,repr(ex),flush=True)
 (OUT/'results.json').write_text(json.dumps({'status':'FAIL' if any(x['status']=='FAIL' for x in ROWS) else 'PASS','tests':ROWS,'source_save_set_id':json.loads((BASE/'manifest.json').read_text())['save_set_id']},ensure_ascii=False,indent=2)+'\n')
def reject(fn):
 try:fn()
 except Exception:return True
 raise AssertionError('expected rejection')
def clone(name):
 r=OUT/name
 if r.exists():shutil.rmtree(r)
 shutil.copytree(BASE,r,ignore=shutil.ignore_patterns('.runtime','__pycache__','.game_engine.lock'));return r

def protected():
 from common import protected as verify
 return verify(BASE)
record('preserve_every_current_fact_and_old_logical_event_byte',protected)

def transitions():
 state=a.read_json(BASE/'state.json');tasks=a.read_json(BASE/'tasks.json');before=copy.deepcopy(state)
 def cmd(action,aid='covert',sid='DIRECT',**kw):return {'session_id':sid,'game_action':action,'account_id':aid,'currency':'copper','command_id':'T-'+action+sid,**kw}
 reserve=cmd('reserve',stake_units=100,choice='heads');a._game_session_apply(state,tasks,reserve);assert a._account_units(state,'covert','copper')==6376963 and a._account_reserved(state,'covert','copper')==100
 reject(lambda:a._game_session_apply(state,tasks,cmd('settle')));a._game_session_apply(state,tasks,cmd('play'));reject(lambda:a._game_session_apply(state,tasks,cmd('cancel')));out=a._game_session_apply(state,tasks,cmd('settle'));balance=a._account_units(state,'covert','copper');reject(lambda:a._game_session_apply(state,tasks,cmd('settle')));assert balance==a._account_units(state,'covert','copper') and a.accounts_integrity_report(state)['status']=='PASS'
 a._game_session_apply(state,tasks,cmd('reserve',sid='CANCEL',stake_units=200,choice='tails'));a._game_session_apply(state,tasks,cmd('cancel',sid='CANCEL'));assert a._account_reserved(state,'covert','copper')==0 and balance==a._account_units(state,'covert','copper')
 for invalid in (True,1.5,-1,0,'10'):reject(lambda:a._game_session_apply(state,tasks,cmd('reserve',sid='INVALID',stake_units=invalid,choice='heads')))
 reject(lambda:a._game_session_apply(state,tasks,cmd('reserve',aid='whitesleep_bridge',sid='CLOSED',stake_units=1,choice='heads')))
 assert state['engine_runtime']['long_horizon']==before['engine_runtime']['long_horizon'] and state['game_time']==before['game_time'] and state['summary']==before['summary']
 bad=copy.deepcopy(state);bad['engine_runtime']['account_registry_v1']['ledger'][0]['delta_units']+=1;assert a.accounts_integrity_report(bad)['status']=='FAIL'
 return {'final_balance':balance,'exactly_one_cash_receipt':len(state['engine_runtime']['account_registry_v1']['ledger']),'cancel_refund':0,'invalid_amounts_rejected':5}
record('minigame_transitions_reservations_replay_and_precision',transitions)

def precision():
 for units in (529278749984573,900719925474099312345,10**35+4321,-(10**35+4321)):
  assert a._money_units4(a._money_value4(units))==units,units
 return 'integer/decimal roundtrip including values beyond binary-float precision'
record('huge_money_exact_roundtrip',precision)

def content():
 installed=a.read_json(BASE/'catalog.json')['content_packages_v1']['packages'];p=a.read_json(BASE/'development/content_packages/example_definitions.json');r=a.validate_content_package(p,installed);assert r['world_instances_created']==0
 for mutate in (lambda q:q.update(dependencies={'missing':'1.0.0'}),lambda q:q['definitions'][0].update(unit='unknown'),lambda q:q['definitions'][0].update(code='bad'),lambda q:q['definitions'][4].update(implementation='mechanical')):
  bad=copy.deepcopy(p);mutate(bad);reject(lambda:a.validate_content_package(bad,installed))
 duplicate=copy.deepcopy(p);duplicate['definitions'].append(copy.deepcopy(duplicate['definitions'][0]));reject(lambda:a.validate_content_package(duplicate,installed))
 for seed in ('seedA','seedB'):
  old=json.loads((BASE/'development/evidence/step18_random_tables.json').read_text());assert a._registered_random_data()==old
 return {'valid_definitions':r['definitions'],'invalid_packages_rejected':5,'random_table_rows_weights_order_unchanged':True}
record('data_only_content_contract',content)

def memory():
 reg=a.read_json(BASE/'state.json')['engine_runtime']['memory_layers_v1'];count=0
 for path in reg['cold_paths']:
  player=a.memory_read_packet(BASE,path);assert player['status']=='REFERENCE_ONLY' and 'value' not in player
  gm=a.memory_read_packet(BASE,path,'gm');assert a._repair_digest(gm['value'])==reg['cold_paths'][path]['object_sha256'];count+=1
 return {'exact_objects':count,'player_disclosure':'summary/reference only'}
record('memory_exact_retrieval_and_visibility',memory)

def caches():
 r=clone('cache');b=api(r)
 with b.SnapshotContext(r) as ctx:assert ctx.validated_report()['status']=='READY_WITH_LIMITATIONS'
 with b.SnapshotContext(r) as ctx:assert ctx.validated_report()['status']=='READY_WITH_LIMITATIONS';assert ctx.metrics['semantic_cache_hits']==1 and ctx.metrics['history_decodes']==0
 c=r/'.runtime/read_semantics_v2.json';raw=c.read_bytes();c.write_bytes(raw.replace(b'READY_WITH_LIMITATIONS',b'BLOCKED'))
 with b.SnapshotContext(r) as ctx:assert ctx.validated_report()['status']=='READY_WITH_LIMITATIONS' and ctx.metrics['full_semantic_checks']==1
 c.unlink()
 with b.SnapshotContext(r) as ctx:assert ctx.validated_report()['status']=='READY_WITH_LIMITATIONS' and ctx.metrics['full_semantic_checks']==1
 archive=next((r/'archives').iterdir());old=archive.read_bytes();archive.write_bytes(bytes([old[0]^1])+old[1:])
 with b.SnapshotContext(r) as ctx:assert ctx.validated_report()['status']=='BLOCKED'
 archive.write_bytes(old)
 reject(lambda:changed_read(b,r))
 return 'warm=zero history decompression; cache corruption/deletion rebuild; same-size cold tamper blocked; closing barrier detects in-flight mutation'
def changed_read(b,r):
 with b.SnapshotContext(r):
  p=r/'state.json';p.write_bytes(p.read_bytes()+b' ')
record('verified_cache_invalidation_and_closing_barrier',caches)

def locators():
 r=clone('locators');b=api(r);meta,events,raws=b._history_read_verified(r/'events.jsonl');index=b.history_locator_index(r)
 for event in (events[0],events[1899],events[2474],events[-1]):assert b.history_lookup(r,event_id=event['event_id'])==event
 cache=r/'.runtime/history_locator_v2.json';cache.write_text('{"fake":true}');assert b.history_lookup(r,event_id=events[0]['event_id'])==events[0]
 # Append changes metadata width/source digest; old byte offsets are adjusted.
 b._append_engine_history(r/'events.jsonl',{'event_id':'INDEX-APPEND','type':'system','game_time':b.read_json(r/'state.json')['game_time'],'summary':'isolated index append'})
 with b.SnapshotContext(r) as ctx:
  assert b.history_lookup(r,event_id=events[-1]['event_id'])==events[-1];assert b.history_lookup(r,event_id='INDEX-APPEND')['event_id']=='INDEX-APPEND';assert ctx.metrics['history_index_incremental']==1
 return {'cold_and_hot_exact_matches':4,'corrupt_index_rebuilt':True,'incremental_append':True}
record('cold_hot_history_locators_and_incremental_append',locators)

def envelope(b,r,action,cid,sid='ENDTOEND'):
 m=b.read_json(r/'manifest.json');now=b.read_json(r/'state.json')['game_time'];c={'schema':b.DOMAIN_COMMAND_SCHEMA,'command_id':cid,'base_save_set_id':m['save_set_id'],'kind':'game_session','session_id':sid,'game_action':action,'account_id':'covert','currency':'copper','authorization':'host_intent','authorization_ref':'HOST:'+cid,'actor_id':'PER-COMMANDER-01'}
 if action=='reserve':c.update(stake_units=100,choice='heads')
 return {'schema':'HOST_COMMAND_INTENT_V1','command':c,'subject_id':c['actor_id'],'parent_save_set_id':m['save_set_id'],'instruction_text':'isolated explicit game action test','evidence_ref':'test-authenticated-host','decision':'approved','targets':b._domain_command_targets(c),'valid_from':now,'valid_until':now,'limits':b._domain_authorization_cost(c)}
def endtoend():
 r=clone('commands');b=api(r);initial=b.read_json(r/'state.json');receipt=None
 for n,action in enumerate(('reserve','play','settle'),49):
  env=envelope(b,r,action,'E2E-'+action);result=b.host_intent_command(r,env,'V14.'+str(n));assert result['status']=='SAVED',result
  again=b.host_intent_command(r,env,'V14.'+str(n+1));assert again['status']=='ALREADY_APPLIED',again
  if action=='settle':receipt=result
 state=b.read_json(r/'state.json');assert state['game_time']==initial['game_time'] and state['engine_runtime']['finance_runtime']==initial['engine_runtime']['finance_runtime'];assert len(state['engine_runtime']['account_registry_v1']['ledger'])==1
 check=b.run_checks(r,full=True);assert check['status']=='PASS',check['errors'];assert b.readiness_report(r)['status']=='READY_WITH_LIMITATIONS'
 # Definitions can be installed through the same authorized transaction, without code changes or assets.
 env=envelope(b,r,'reserve','E2E-content');cmd=env['command'];cmd.clear();cmd.update(schema=b.DOMAIN_COMMAND_SCHEMA,command_id='E2E-content',base_save_set_id=env['parent_save_set_id'],kind='content_install',package=b.read_json(r/'development/content_packages/example_definitions.json'),authorization='host_intent',authorization_ref='HOST:E2E-content',actor_id=env['subject_id']);env['targets']=b._domain_command_targets(cmd);env['limits']=b._domain_authorization_cost(cmd)
 inventories=copy.deepcopy(state['inventories']);engine_sha=b.sha256_file(r/'engine.py');result=b.host_intent_command(r,env,'V14.52');assert result['status']=='SAVED',result;assert b.sha256_file(r/'engine.py')==engine_sha and b.read_json(r/'state.json')['inventories']==inventories
 return {'four_authorized_commits':True,'three_command_replays_no_effect':True,'one_cash_posting':True,'content_install_no_code_or_assets':True}
record('authorized_engine_commands_replay_and_data_install',endtoend)
raise SystemExit(1 if any(r['status']=='FAIL' for r in ROWS) else 0)
