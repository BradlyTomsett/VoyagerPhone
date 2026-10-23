import sys
sys.dont_write_bytecode=True
import copy,importlib.util,json,os,pathlib,time,traceback
P=pathlib.Path;BASE=P(os.environ['VOYAGER_TEST_SOURCE']);OUT=P(os.environ['VOYAGER_STEP18_OUTPUT']);OUT.mkdir();rows=[]
s=importlib.util.spec_from_file_location('e',BASE/'engine.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
def reject(fn,token):
 try:fn()
 except Exception as ex:assert token in str(ex),(token,str(ex));return
 raise AssertionError('expected rejection')
def test(name,fn):
 try:detail=fn();rows.append({'name':name,'status':'PASS','detail':detail})
 except Exception as ex:rows.append({'name':name,'status':'FAIL','error':str(ex),'trace':traceback.format_exc()})
 print(rows[-1]['status'],name,flush=True);(OUT/'results.json').write_text(json.dumps({'status':'FAIL' if any(x['status']=='FAIL' for x in rows) else 'PASS','tests':rows},ensure_ascii=False,indent=2)+'\n')
def standing_grants():
 state=a.read_json(BASE/'state.json');now=state['game_time'];c={'kind':'create_task','command_id':'GRANT-ISOLATED','task':{'task_id':'TSK-GRANT-ISOLATED'},'authorization':'standing_authorization','authorization_ref':'FIXTURE-GRANT','actor_id':'PER-COMMANDER-01'}
 grant={'schema':'DOMAIN_MACHINE_GRANT_V1','grant_id':'FIXTURE-GRANT','subject_id':c['actor_id'],'action_kinds':['create_task'],'targets':a._domain_command_targets(c),'valid_from':now,'valid_until':now,'max_uses':1,'max_gold_units':0,'max_grey_units':0,'max_quantity':0};state['standing_authorizations']['FIXTURE-GRANT']={'status':'active','machine_grant':grant}
 assert a._phase2_domain_authorization(state,c)['status']=='verified'
 for key,value,token in [('status','revoked','REVOKED'),('revoked',True,'REVOKED')]:
  b=copy.deepcopy(state);b['standing_authorizations']['FIXTURE-GRANT'][key]=value;reject(lambda:a._phase2_domain_authorization(b,c),'REVOKED')
 for key,value,token in [('subject_id','WRONG','SUBJECT'),('valid_until','8363-12-01T00:00:00','EXPIRED'),('targets',[],'TARGET'),('max_uses',0,'BUDGET')]:
  b=copy.deepcopy(state);b['standing_authorizations']['FIXTURE-GRANT']['machine_grant'][key]=value;reject(lambda:a._phase2_domain_authorization(b,c),token)
 a._phase2_domain_authorization(state,c,True);reject(lambda:a._phase2_domain_authorization(state,c,True),'BUDGET')
 return 'synthetic in-memory standing grant: exact active scope, revoked/inactive/expired/wrong actor/target/budget, one-use consumption'
test('standing_grant_revocation_scope_and_consumption',standing_grants)
def assets():
 state=a.read_json(BASE/'state.json');tasks=a.read_json(BASE/'tasks.json');paths=[];records=[]
 for rec in state['asset_ledger_v1']['assets'].values():
  if isinstance(rec.get('fields',{}).get('quantity'),int) and rec['fields']['quantity']>0 and rec.get('source_paths'):paths.append(rec['source_paths'][0])
  if len(paths)==2:break
 assert len(paths)==2
 for path in paths:
  row,rec,qty,_,role=a._asset_ledger_mapped_row(state,'state:'+path);records.append((rec,role,qty))
 # Explicit synthetic identity/unit proof, confined to memory; never imputed to live assets.
 for rec,role,qty in records:rec.update(asset_type_id='FIXTURE-FOOD',unit='包',owner_ref='fixture:same-owner')
 payload={'source_path':'state:'+paths[0],'dest_path':'state:'+paths[1],'qty':1};before=sum(x[2] for x in records);a._domain_transfer_asset(state,tasks,payload);assert sum(a.get_by_path(state,p) for p in paths)==before
 reject(lambda:a._domain_transfer_asset(state,tasks,{**payload,'qty':10**30}),'INSUFFICIENT');reject(lambda:a._domain_transfer_asset(state,tasks,{**payload,'qty':-1}),'QTY')
 records[1][0]['owner_ref']='fixture:other-owner';reject(lambda:a._domain_transfer_asset(state,tasks,payload),'OWNERSHIP')
 assert a.read_json(BASE/'state.json')['inventories']!=state['inventories']
 return {'in_memory_synthetic_verified_buckets':True,'transfer_conservation':True,'no_negative_stock':True,'ownership_change_requires_contract':True,'live_source_unchanged':True,'limitation':'unverified identity/unit in live source remains unverified, not filled by this fixture'}
test('asset_conservation_units_ownership_and_negative_stock',assets)
raise SystemExit(1 if any(x['status']=='FAIL' for x in rows) else 0)
