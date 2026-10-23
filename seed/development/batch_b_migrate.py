#!/usr/bin/env python3
"""Exact V14.45 -> V14.46 zero-time maintenance, never a gameplay patch API."""
import copy,gzip,shutil,hashlib,importlib.util,json,os,pathlib,sys
P=pathlib.Path

def digest(o):return hashlib.sha256(json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def load(p):return json.loads(p.read_text())
def write(p,o):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fp(r):return {str(p.relative_to(r)):sha(p) for p in sorted(r.rglob('*')) if p.is_file() and not any(x.startswith('.') or x=='__pycache__' for x in p.relative_to(r).parts)}
def migrate(source,target,audit):
 source=source.resolve();target=target.resolve();m=load(source/'manifest.json')
 assert m['save_set_id']=='SAVESET-V14.45-27b38347304e1566' and m['save_version']=='V14.45','SOURCE_BASELINE_MISMATCH'
 spec=importlib.util.spec_from_file_location('parent_guard',source/'guard.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g);bound,errors=g.validate_dir(source,strict=True);assert bound and not errors and g.development_intact(source,bound),errors
 for name in ('state.json','tasks.json','rules.json','catalog.json','manifest.json','events.jsonl'):shutil.copy2(source/name,target/name)
 for archive in (target/'archives').iterdir():
  if not (source/'archives'/archive.name).exists():archive.unlink()
 before=fp(source);s=load(source/'state.json');t=load(source/'tasks.json');catalog=load(source/'catalog.json');er=s['engine_runtime'];w=s['world_state_overrides'];now=s['game_time'];assert now==t['game_time']=='8363-12-02T22:45:00'
 def view(path,currency,scale=1,available=False):return {'path':path,'currency':currency,'units_per_value':scale,'format':'integer' if scale==1 else 'decimal','available_only':available}
 acct={
 'fleet':{'owner':'commander_fleet','status':'active','currencies':['gold','grey'],'units_per_currency':{'gold':10000,'grey':10000},'balance_ref':'engine_runtime.finance_runtime.funds_units','legacy_read_only_views':[]},
 'covert':{'owner':'hawke_covert','status':'active','currencies':['copper'],'units_per_currency':{'copper':1},'balances':{'copper':6376963},'legacy_read_only_views':[view('world_state_overrides.freeport_xilu9_current.covert_account_current.cash_copper','copper'),view('world_state_overrides.current_handoff_snapshot.funds.covert_copper','copper')]},
 'shop':{'owner':'yuhuo_business','status':'active','currencies':['copper'],'units_per_currency':{'copper':1},'balances':{'copper':24530},'legacy_read_only_views':[view('world_state_overrides.freeport_xilu9_current.hawke_commercial_cover.cash_account.cash_silver','copper',100),view('world_state_overrides.freeport_xilu9_current.hawke_commercial_cover.cash_account.free_operating_cash_silver','copper',100,True),view('world_state_overrides.current_handoff_snapshot.funds.shop_copper','copper')]},
 'whitesleep_bridge':{'owner':'closed_case_pass_through','status':'closed','currencies':['copper'],'units_per_currency':{'copper':1},'balances':{'copper':0},'legacy_read_only_views':[]}}
 er['account_registry_v1']={'schema':'ACCOUNT_REGISTRY_V1','as_of':now,'accounts':acct,'ledger':[],
 'opening_units':{'fleet':copy.deepcopy(er['finance_runtime']['funds_units']),'covert':{'copper':6376963},'shop':{'copper':24530},'whitesleep_bridge':{'copper':0}},
 'opening_evidence':{'source_save_set_id':m['save_set_id'],'status':'accepted_existing_current_balances_not_replayed','source_refs':['state:engine_runtime.finance_runtime.funds_units','state:world_state_overrides.freeport_xilu9_current.covert_account_current','state:world_state_overrides.freeport_xilu9_current.hawke_commercial_cover.cash_account']},
 'historical_reconciliation':[{'id':'EXPLOSIVES-16G-ALREADY-PAID','gold_units':160000,'status':'paid_once_accepted_history','replay_allowed':False},{'id':'WHITESLEEP-11720-BRIDGE','in_copper':11720,'out_copper':11720,'net_copper':0,'status':'closed_accepted_history','replay_allowed':False}],
 'historical_views':{'task_allocations.TSK-YUHUO-OPERATIONS.cash_silver':{'classification':'historical_snapshot_not_balance_authority','recorded_value':330.49,'current_account_id':'shop'}},
 'precision_contract':'integer base units; exact decimal strings at query boundary; no currency conversion without typed settlement'}
 er['minigame_runtime_v1']={'schema':'MINIGAME_RUNTIME_V1','sessions':{},'contract':'reserve -> play -> settle OR reserve -> cancel; command receipts prevent replay'}
 random=load(audit/'original_random_data.json')
 core={'schema':'VOYAGER_CONTENT_PACKAGE_V1','schema_version':1,'package_id':'voyager.core.random','namespace':'voyager.core','version':'1.0.0','rule_version':'RANDOM_EVENT_FRAMEWORK_V3','source':'exact baseline ENGINE 2.60.0 _random_event_framework_v3_runtime_rules','visibility':'gm','dependencies':{},'definitions':[{'id':'voyager.core:random_tables','kind':'random_tables','resolver':'deterministic_hazard_tables_v3','data':random}]}
 example={'schema':'VOYAGER_CONTENT_PACKAGE_V1','schema_version':1,'package_id':'voyager.reference.demo','namespace':'voyager.reference','version':'1.0.0','rule_version':'content_contract_v1','source':'Batch B definition-only integration fixture; not a discovered world fact','visibility':'definition_only','dependencies':{'voyager.core.random':'1.0.0'},'definitions':[
 {'id':'voyager.reference:organization','kind':'organization','name':'资料包示例组织','epistemic':'definition_only'},
 {'id':'voyager.reference:location','kind':'location','name':'资料包示例地点','epistemic':'definition_only'},
 {'id':'voyager.reference:equipment','kind':'equipment','name':'资料包示例设备','unit':'台','ownership_effect':'definition_only'},
 {'id':'voyager.reference:scene','kind':'scene_family','name':'资料包示例场景','epistemic':'definition_only','auto_start':False},
 {'id':'voyager.reference:semantic','kind':'semantic_rule','implementation':'semantic_only','text':'该资料包只定义名词，不生成资产、人员或地点实例。'}]}
 catalog['content_packages_v1']={'schema':'CONTENT_PACKAGE_REGISTRY_V1','packages':{'voyager.core.random':core}}
 # Keep demo outside installed world definitions. It is independently installable data.
 write(target/'development/content_packages/example_definitions.json',example)
 coldpaths={};objects={};summaries={}
 # These sealed dated handoffs have no active task/rule binding. The current
 # 12/02 evidence and all closed-case terminal records remain directly available.
 keys=['handoff_snapshot_history','historical_handoff_83631105']+[k for k in w if k.startswith('campaign_continuity_836311')]
 def at(path):
  cur=s
  for k in path.split('.'):cur=cur[k]
  return cur
 def set_at(path,value):
  parent,key=path.rsplit('.',1);at(parent)[key]=value
 paths=['world_state_overrides.'+k for k in keys]+['world_state_overrides.freeport_xilu9_current.whitesleep_case_current.'+k for k in ('gm_private_initial_conditions','post_1200_timeline','briefing_wording_history')]
 for path in paths:
  objects[path]=copy.deepcopy(at(path));summaries[path]={'source_path':path,'classification':'dated_historical_handoff_or_closed_case_attachment','current_authority':False,'original_sha256':digest(at(path)),'source_event_ids':[],'source_save_set_id':m['save_set_id'],'provenance_note':'exact dated object from accepted source; no specific original event receipt asserted','epistemic':'historical_evidence_only'}
 payload={'schema':'VOYAGER_MEMORY_OBJECTS_V1','source_save_set_id':m['save_set_id'],'objects':objects};ph=digest(payload);rel='archives/memory_handoffs_V14.46_'+ph[:12]+'.json.gz';wrapper={'schema':'VOYAGER_COLD_ARCHIVE_V1','payload_sha256':ph,'payload':payload};dest=target/rel;dest.parent.mkdir(exist_ok=True)
 with dest.open('wb') as out:
  with gzip.GzipFile(filename='',fileobj=out,mode='wb',mtime=0) as gz:gz.write(json.dumps(wrapper,ensure_ascii=False,separators=(',',':')).encode())
 for path,obj in objects.items():
  summary=summaries[path];entry={'archive_ref':rel,'payload_sha256':ph,'object_sha256':digest(obj),'summary':summary,'source_event_ids':summary['source_event_ids']};coldpaths[path]=entry;set_at(path,{'$storage':'cold_archive','archive_ref':rel,'source_path':path,'object_sha256':entry['object_sha256'],'warm_summary_ref':'engine_runtime.memory_layers_v1.warm_summaries.'+path})
 er['memory_layers_v1']={'schema':'MEMORY_LAYERS_V1','hot_policy':'current facts, unresolved commitments and terminal case outcomes kept directly readable','warm_summaries':summaries,'cold_paths':coldpaths,'source_save_set_id':m['save_set_id'],'summary_rebuild':'derive original hash and dated classification from exact archived objects; never promote rumor to confirmed'}
 er['authority_map_v1']['accounts']='engine_runtime.account_registry_v1';er['authority_map_v1']['content']='catalog:content_packages_v1';er['authority_map_v1']['memory']='engine_runtime.memory_layers_v1'
 manifest=copy.deepcopy(m);manifest['cold_archives']['MEMORY_HANDOFFS_V14_46']={'schema':'VOYAGER_COLD_ARCHIVE_V1','archive_id':'MEMORY_HANDOFFS_V14_46','path':rel,'file_sha256':sha(dest),'payload_sha256':ph,'load_policy':'on_demand_exact_memory_read'}
 for name,data in [('state.json',s),('tasks.json',t),('catalog.json',catalog),('manifest.json',manifest)]:write(target/name,data)
 os.environ.update(VOYAGER_ROOT=str(target),VOYAGER_DEV_SOURCE_DIR=str(target),VOYAGER_DEVELOPER_MODE='1',VOYAGER_DIAGNOSTIC_CONTEXT='gm',PYTHONDONTWRITEBYTECODE='1')
 spec=importlib.util.spec_from_file_location('batch_b_candidate',target/'engine.py');api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
 plan={'schema':'BATCH_B_MAINTENANCE_PLAN_V1','source_save_set_id':m['save_set_id'],'source_fingerprint':before,'candidate_tools':{n:sha(target/n) for n in ('engine.py','guard.py')},'scope':'steps08-12','target_state_sha256':digest(s),'target_catalog_sha256':digest(catalog),'game_time_advanced':False,'archived_paths':paths};plan['plan_sha256']=digest(plan);write(audit/'maintenance_plan_final.json',plan)
 event={'event_id':'EVT-BATCH-B-'+plan['plan_sha256'][:24],'type':'system','subtype':'batch_b_maintenance','game_time':now,'zero_time':True,'summary':'Batch B accounts, services, verified read snapshots, exact memory tiers and data content contract. No cash, gameplay or risk simulation.','source':'GAME ENGINE 2.61.0 BATCH_B_MAINTENANCE_V1','changes':[{'target':'state:engine_runtime','action':'zero_time_service_contract_migration'},{'target':'catalog:content_packages_v1','action':'seal_existing_random_tables_as_data'}],'source_refs':['state:self','catalog:self','events:self','manifest:self'],'maintenance_plan':plan['plan_sha256']}
 api._append_engine_history(target/'events.jsonl',event)
 compaction=api._compact_history_file_to_epochs(target/'events.jsonl',keep_recent=64,force=True);write(audit/'history_compaction.json',compaction)
 facts=api._history_epoch_runtime_facts(target)
 s['engine_runtime']['scaling']['history_epoch'].update({k:facts[k] for k in ('compression_recommended','compression_applied')});write(target/'state.json',s)
 lineage={'from_save_set_id':m['save_set_id'],'from_layout':'native_eight_component_v4_tiered_history','to_layout':'native_eight_component_v4_tiered_history','game_time_advanced':False,'batch_b_plan_sha256':plan['plan_sha256']}
 targetm=api._component_write_manifest_native(target,'V14.46',m['save_set_id'],lineage)
 report=api.run_checks(target,full=True);write(audit/'maintenance_target_check.json',report)
 assert fp(source)==before,'SOURCE_CHANGED'
 print(json.dumps({'status':report['status'],'save_set_id':targetm['save_set_id'],'errors':report.get('errors',[])},ensure_ascii=False));return report
if __name__=='__main__':
 if len(sys.argv)!=4:raise SystemExit('usage: batch_b_migrate.py SOURCE CANDIDATE AUDIT')
 r=migrate(*(P(x) for x in sys.argv[1:]));raise SystemExit(0 if r['status']=='PASS' else 1)
