import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {loadPyodide} from '../docs/vendor/pyodide/pyodide.mjs';
try{
 const py=await loadPyodide({indexURL:fileURLToPath(new URL('../docs/vendor/pyodide/',import.meta.url))});
 await py.loadPackage(['sqlite3','lzma']);py.unpackArchive(new Uint8Array(fs.readFileSync('docs/engine-bundle.zip')),'zip',{extractDir:'/app'});
 py.runPython(`import sys,json,shutil
sys.path.insert(0,'/app')
from browser.runtime_host import BrowserHost,restore_snapshot,import_save
from backend.logistics import Logistics,QRF_GROUP,KEY,commit
host=BrowserHost('/qrf-group-test')
time=host.state()['game_time']
def service():return Logistics(host.game.bridge.source_library())
def move(request,tag):
 preview=host.dispatch('transfer_preview',request)
 data={'id':'MOVE-SYNTHETIC-DARK1-'+tag,'request':preview['request'],'base_save_set_id':preview['base_save_set_id'],'preview_hash':preview['preview_hash']}
 host.transfer_prepare(data);result=host.transfer_commit(data['id'])
 if result['status']!='SAVED':
  commit(host.game.bridge,service().plan(request),data['id'])
  raise AssertionError(result)
 host.game.bridge.recover();assert host.state()['game_time']==time
 return data
cat=host.dispatch('transfer_catalog',{})
assert next(l for l in cat['locations'] if l['id']==QRF_GROUP)['parent']=='qrf'
contents=host.dispatch('transfer_contents',{'location':QRF_GROUP})
assert contents['personnel']==460
item=next(i for i in contents['items'] if i['name']=='堡垒-5')
assert item['quantity']=='657'
data=move({'kind':'items','source':QRF_GROUP,'destination':'shadow:warehouse','item':item['id'],'quantity':'1'},'ITEM-001')
state=service().state;q=state['shadow_fleet']['quick_reaction_force_current']
assert q['equipment']['堡垒-5']['usable']==1326
assert q['equipment']['堡垒-5']['allocation']=={'S-B5':670,'暗反1组':656}
assert host.transfer_commit(data['id'])['status']=='SAVED'
assert next(i['quantity'] for i in service().contents(QRF_GROUP)['items'] if i['name']=='堡垒-5')=='656'
print('PASS dark1 native equipment debit, whole-QRF mirrors, retry once',flush=True)
move({'kind':'personnel','source':QRF_GROUP,'destination':'farstar','quantity':'10','personnel_group':'70'},'PEOPLE-002')
state=service().state;q=state['shadow_fleet']['quick_reaction_force_current']
assert (q['personnel'],q['deployed_group_current']['qrf_personnel'])==(2643,450)
assert state['summary']['personnel']['total_player_active']==23946
assert host.dispatch('fleet_personnel',{'subject':'shadow_qrf'})['personnel']==2643
saved=host.snapshot();host.game.bridge.host.close();host.game.process_lock.close();shutil.rmtree('/qrf-group-test')
restore_snapshot(saved,'/qrf-group-test');host=BrowserHost('/qrf-group-test')
assert service().contents(QRF_GROUP)['personnel']==450
exported=host.export();host.game.bridge.host.close();host.game.process_lock.close()
import_save(exported,'/qrf-group-test');host=BrowserHost('/qrf-group-test')
assert service().contents(QRF_GROUP)['personnel']==450
assert next(i['quantity'] for i in service().contents(QRF_GROUP)['items'] if i['name']=='堡垒-5')=='656'
print('PASS dark1 personnel T preserved, snapshot reload and export/import',flush=True)
`);
}catch(e){console.error(String(e.message).slice(-7000));process.exitCode=1;}
