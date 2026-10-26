// Real unchanged native engine, fresh test copy. No network or player data.
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {loadPyodide} from '../docs/vendor/pyodide/pyodide.mjs';
try{
 const py=await loadPyodide({indexURL:fileURLToPath(new URL('../docs/vendor/pyodide/',import.meta.url))});
 await py.loadPackage(['sqlite3','lzma']);
 py.unpackArchive(new Uint8Array(fs.readFileSync('docs/engine-bundle.zip')),'zip',{extractDir:'/app'});
 py.runPython(`import sys,json,hashlib
sys.path.insert(0,'/app')
from pathlib import Path
from browser.runtime_host import BrowserHost
host=BrowserHost();root=host.game.bridge.root
actor='PER-HAWK-MALEN-01'
def world():return {n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['manifest.json','state.json','tasks.json','events.jsonl']}
before=world();time_before=host.state()['game_time']
for index,scene in enumerate([None,'',' ','　','\\t\\n']):
 req={'client_id':'WEB-empty-scene-'+str(index),'mode':'action','intent':'SYNTHETIC optional scene','actor_id':actor,'scene_id':scene}
 result=host.begin(req)
 assert result['packet']['context']['status']=='NO_OPEN_SCENE',result
 assert result['job']['request']['scene_id'] is None
 host.fail(req['client_id'],'SYNTHETIC_FINISHED')
assert world()==before,'Request preparation must not change world state'
sid='SCENE-SYNTHETIC-AUTO-CURRENT'
req={'client_id':'WEB-auto-scene-setup','mode':'action','intent':'SYNTHETIC establish remote scene','actor_id':actor,'scene_id':None}
host.begin(req)
actions=[{'type':'life_control','entity_id':actor,'operation':'take','reason':'SYNTHETIC selected perspective'},
 {'type':'scene_open','scene_id':sid,'task_id':None,'family':'conversation','title':'SYNTHETIC automatic scene','location_ref':'LOC-FREEPORT-XILU9-SEVENDOCK','participants':[actor],'presence_mode':'remote','visible_to':['player']},
 {'type':'scene_phase','scene_id':sid,'phase':'open'},{'type':'scene_focus_v2','scene_id':sid}]
host.accept_plan(req['client_id'],{'kind':'setup','message':'SYNTHETIC ONLY','payload_json':json.dumps({'actions':actions}),'choices':[]},{})
ready=host.accept_review(req['client_id'],{'status':'PASS','reasons':[]},{})
host.confirm_prepare(req['client_id'],ready['plan_hash']);saved=host.confirm_commit(req['client_id'])
assert saved['status']=='SAVED',saved
after_setup=world()
req.update(client_id='WEB-auto-current-followup',intent='SYNTHETIC continue current scene',scene_id=' ')
result=host.begin(req)
assert result['packet']['context']['prepare']['scene_id']==sid,result['packet']['context']
assert result['job']['request']['scene_id'] is None
host.fail(req['client_id'],'SYNTHETIC_FINISHED')
assert world()==after_setup and host.state()['game_time']==time_before
print('PASS real WASM: empty/whitespace scene accepted with Hawk, no scene opens automatically, confirmed active scene followed without manual ID, no request-side world/time mutation')
`);
}catch(error){console.error(String(error.stack||error).slice(-7000));process.exitCode=1;}
