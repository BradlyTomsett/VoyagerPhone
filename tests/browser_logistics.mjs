// Real native atomic saves under the pinned browser Python runtime.
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {loadPyodide} from '../docs/vendor/pyodide/pyodide.mjs';
try{
 const py=await loadPyodide({indexURL:fileURLToPath(new URL('../docs/vendor/pyodide/',import.meta.url))});
 await py.loadPackage(['sqlite3','lzma']);py.unpackArchive(new Uint8Array(fs.readFileSync('docs/engine-bundle.zip')),'zip',{extractDir:'/app'});
 py.runPython(`import sys,json,shutil
sys.path.insert(0,'/app')
from browser.runtime_host import BrowserHost,restore_snapshot,import_save
from backend.logistics import Logistics,KEY,ships
host=BrowserHost('/test-logistics')
root=host.game.bridge.root
original_time=host.state()['game_time']
def service():return Logistics(host.game.bridge.source_library())
def item(lid,name):return next(r['id'] for r in service().contents(lid)['items'] if r['name']==name)
def prepare(request,tag):
 p=host.transfer_preview(request)
 data={'id':'MOVE-SYNTHETIC-'+tag,'request':p['request'],'base_save_set_id':p['base_save_set_id'],'preview_hash':p['preview_hash']}
 host.transfer_prepare(data)
 return data
def finish(data):
 r=host.transfer_commit(data['id'])
 assert r['status']=='SAVED',r
 host.game.bridge.recover()
 assert host.state()['game_time']==original_time
 return r
data=prepare({'kind':'items','source':'voyager:warehouse','destination':'jinchuan:warehouse','item':item('voyager:warehouse','堡垒-6'),'quantity':'2'},'ITEM-0001')
# Crash after the durable confirmed intent, before native commit.
prepared=host.snapshot();host.game.process_lock.close();shutil.rmtree('/test-logistics')
restore_snapshot(prepared,'/test-logistics');host=BrowserHost('/test-logistics')
job=host.game.store.get(data['id'])
if job['status']!='SAVED':
 from backend.logistics import commit
 commit(host.game.bridge,service().plan(job['transfer_input']['request']),job['id'])
 raise AssertionError(job)
assert not host.transfer_history()['pending'],host.transfer_history()['pending']
assert next(r['quantity'] for r in service().contents('jinchuan:warehouse')['items'] if r['name']=='堡垒-6')=='2'
identity=host.state()['save_set_id'];finish(data);host.transfer_prepare(data)
assert host.state()['save_set_id']==identity
bad={**data,'request':{**data['request'],'quantity':'3'}}
try:host.transfer_prepare(bad);raise AssertionError('reused ID accepted')
except ValueError as ex:assert str(ex)=='TRANSFER_ID_REUSED'
print('PASS confirmed-intent recovery, duplicate retry, reused ID rejected',flush=True)
stale=host.transfer_preview({'kind':'items','source':'voyager:warehouse','destination':'shadow:warehouse','item':item('voyager:warehouse','堡垒-6'),'quantity':'1'})
finish(prepare({'kind':'personnel','source':'farstar','destination':'qrf','quantity':'10','personnel_group':'100'},'PEOPLE-0002'))
assert host.state()['core']['value']['fleet_core']['voyager']['personnel']==17193
assert service().contents('qrf')['cohorts'][-1]['T']==100
try:host.transfer_prepare({'id':'MOVE-SYNTHETIC-STALE-0001','request':stale['request'],'base_save_set_id':stale['base_save_set_id'],'preview_hash':stale['preview_hash']});raise AssertionError('stale accepted')
except ValueError as ex:assert str(ex)=='TRANSFER_STALE_PREVIEW'
print('PASS native personnel commit with mixed T, stale preview rejected',flush=True)
finish(prepare({'kind':'vessels','vessel':'VES-EXPLORER1','destination':'shadow'},'VESSEL-0003'))
assert host.state()['core']['value']['fleet_core']['voyager']['ships']==50
assert ships(service().state)['VES-EXPLORER1'][0]=='shadow'
assert service().contents('VES-EXPLORER1')['personnel']==120
finish(prepare({'kind':'items','source':'VES-EXPLORER1','destination':'shadow:warehouse','item':item('VES-EXPLORER1','SCV工程机器人'),'quantity':'1'},'CARRIED-0004'))
assert service().state['shadow_fleet']['vessels']['VES-EXPLORER1']['fixed_engineering_science_assets']['scv']==39
print('PASS native vessel transfer, attributes and rebound carried equipment',flush=True)
finish(prepare({'kind':'warehouse','name':'合成测试空仓','fleet':'jinchuan'},'WAREHOUSE-0005'))
saved=host.snapshot();host.game.process_lock.close();shutil.rmtree('/test-logistics')
restore_snapshot(saved,'/test-logistics');host=BrowserHost('/test-logistics')
assert len(host.transfer_history()['receipts'])==5
assert service().contents('VES-EXPLORER1')['personnel']==120
# Later native effects update the same physical ledger before domain validation.
import copy
candidate=copy.deepcopy(service().state);row=candidate['shadow_fleet']['vessels']['VES-ANYA1'];row['current_embarked_assets']['fortress6']-=1
native=host.game.bridge.host._engine();tasks=json.loads((host.game.bridge.root/'tasks.json').read_bytes())
native._phase2_domain_post_mutation_validate(candidate,tasks,candidate['game_time'])
assert row['current_combat_robot_count']==29
check=service().plan({'kind':'vessels','vessel':'VES-CHANGJI2','destination':'jinchuan'})['state']['voyager_fleet']
assert not native._validate_voyager_vessel_naming(check)
check['vessel_roster'][0]['name']='INVALID NAME'
assert native._validate_voyager_vessel_naming(check)
print('PASS later native effects reconcile, serial gaps retain identities, invalid names rejected',flush=True)
exported=host.export();host.game.bridge.host.close();host.game.process_lock.close()
import_save(exported,'/test-logistics');host=BrowserHost('/test-logistics')
assert len(host.transfer_history()['receipts'])==5
assert host.state()['game_time']==original_time
assert any(l['name']=='合成测试空仓' for l in service().catalogue()['locations'])
print('PASS snapshot reload and exported save import retain all transfers',flush=True)
`);
}catch(e){console.error(String(e.message).slice(-7000));process.exitCode=1;}
