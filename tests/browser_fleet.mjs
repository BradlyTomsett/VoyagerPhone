import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {loadPyodide} from '../docs/vendor/pyodide/pyodide.mjs';
try{
 const p=await loadPyodide({indexURL:fileURLToPath(new URL('../docs/vendor/pyodide/',import.meta.url))});
 await p.loadPackage(['sqlite3','lzma']);
 p.unpackArchive(new Uint8Array(fs.readFileSync('docs/engine-bundle.zip')),'zip',{extractDir:'/app'});
 p.runPython(`import sys,json,hashlib
sys.path.insert(0,'/app')
from browser.runtime_host import BrowserHost
host=BrowserHost()
root=host.game.bridge.root
before={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['state.json','tasks.json','events.jsonl','manifest.json']}
for fleet,count,active in [('voyager',51,51),('jinchuan',9,9),('shadow',19,18)]:
 overview=host.dispatch('fleet_overview',{'fleet':fleet})
 assert len(overview['ships'])==count
 assert overview['active_count']==active
 ship=host.dispatch('fleet_ship',{'fleet':fleet,'vessel':overview['ships'][0]['id']})
 assert ship['records']
 inventory=host.dispatch('fleet_inventory',{'fleet':fleet})
 assert inventory['groups'] and inventory['models']
 records=host.dispatch('fleet_records',{'fleet':fleet})
 assert records['records']
 json.dumps([ship,inventory,records],ensure_ascii=False)
assert '920m' in json.dumps(host.dispatch('fleet_ship',{'fleet':'voyager','vessel':'VES-QINFENG1'}),ensure_ascii=False)
equipment=host.dispatch('fleet_equipment',{'query':'猎隼-4'})
assert any(r['value'].get('immutable_specs',{}).get('g_range')==[1100,1300] for r in equipment['specifications'])
assert any(r['value'].get('完好名义航空A')==32.5 for r in equipment['specifications'])
grenade=host.dispatch('fleet_equipment',{'query':'多功能手雷'})
assert len(grenade['specifications'][0]['value']['现行多功能手雷模式'])==6
assert len(host.dispatch('fleet_inventory',{'fleet':'voyager'})['weapons'])==12
after={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in before}
assert before==after,'Fleet browsing must never write world facts'
print('PASS: real WASM fleet RPCs; 51/9/19 named records, active/owned scopes, ship designs/armament, inventories, performance, all fields, read-only world')
`);
}catch(e){console.error(String(e.message).slice(-6500));process.exitCode=1;}
