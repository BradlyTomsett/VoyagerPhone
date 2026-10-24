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
topics=host.dispatch('library_topics',{})
assert len(topics)==16
bases=host.dispatch('fleet_domain',{'domain':'bases'})
assert bases['highlights'][0]['metrics']['berths']==70
for fleet,parent,base,other in [('voyager','远航者舰队','远航基地','shadow_base'),('shadow','暗影舰队','暗影基地','voyager_base')]:
 scoped=host.dispatch('fleet_domain',{'domain':'bases','fleet':fleet})
 assert scoped['parent_fleet']==fleet
 assert len(scoped['highlights'])==1 and scoped['highlights'][0]['title']==base
 assert scoped['highlights'][0]['parent']==parent+'下属基地'
 assert all(other not in r['ref'] for r in scoped['records'])
army=host.dispatch('fleet_domain',{'domain':'army'})
assert army['highlights'][0]['metrics']['人员（人）']==4234
assert army['parent_fleet']=='voyager'
qrf=host.dispatch('fleet_domain',{'fleet':'shadow','domain':'qrf'})
assert qrf['parent_fleet']=='shadow'
assert qrf['highlights'][0]['metrics']['人员（人）']==2653
for subject,t,count in [('farstar',100,4234),('shadow_qrf',70,2653)]:
 detail=host.dispatch('fleet_personnel',{'subject':subject})
 assert detail['T']==t and detail['personnel']==count
for query in ['远航基地','暗影基地','远星军','余火']:
 result=host.dispatch('library_browse',{'query':query})
 assert result['total']>0
 assert all('value' in row for row in result['results'])
 assert '"implementation_status"' not in json.dumps([r['value'] for r in result['results']])
after={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in before}
assert before==after,'Fleet browsing must never write world facts'
print('PASS: real WASM fleet RPCs; 51/9/19 named records, active/owned scopes, ship designs/armament, inventories, performance, all fields, read-only world')
`);
}catch(e){console.error(String(e.message).slice(-6500));process.exitCode=1;}
