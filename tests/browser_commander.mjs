// Verify the missing commander on the original seed, in the real WASM engine.
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {loadPyodide} from '../docs/vendor/pyodide/pyodide.mjs';
try {
 const p=await loadPyodide({indexURL:fileURLToPath(new URL('../docs/vendor/pyodide/',import.meta.url))});
 await p.loadPackage(['sqlite3','lzma']);
 p.unpackArchive(new Uint8Array(fs.readFileSync('docs/engine-bundle.zip')),'zip',{extractDir:'/app'});
 p.runPython(`import sys,json
sys.path.insert(0,'/app')
from browser.runtime_host import BrowserHost,COMMANDER_ID
from pathlib import Path
host=BrowserHost()
root=host.game.bridge.root
def read_state(): return json.loads((root/'state.json').read_text())
before=read_state()
assert COMMANDER_ID not in before['entity_registry']['entities']
assert host.choices()['actors'][0]=={'id':COMMANDER_ID,'name':'指挥官'}
assert len({r['id'] for r in host.choices()['actors']})==len(host.choices()['actors'])
request={'client_id':'WEB-commandersetup1','mode':'action','intent':'SYNTHETIC TEST ONLY: confirm existing commander identity and player perspective','actor_id':COMMANDER_ID,'scene_id':None}
begun=host.begin(request)
assert begun['packet']['selected_actor_identity']['name']=='指挥官'
assert begun['packet']['context']['status']=='NO_OPEN_SCENE'
plan={'kind':'setup','message':'SYNTHETIC TEST ONLY','payload_json':json.dumps({'actions':[{'type':'life_control','entity_id':COMMANDER_ID,'operation':'take','reason':'SYNTHETIC explicit choice of commander perspective'}]}),'choices':[]}
accepted=host.accept_plan(request['client_id'],plan,{})
payload=accepted['job']['payload']
assert [a['type'] for a in payload['actions']]==['entity_register','life_control']
assert payload['actions'][0]['name']=='指挥官'
ready=host.accept_review(request['client_id'],{'status':'PASS','reasons':[]},{})
assert ready['status']=='AWAITING_CONFIRMATION'
assert read_state()==before, 'Opening choices and reviewing a setup must not mutate the world'
host.confirm_prepare(request['client_id'],ready['plan_hash'])
saved=host.confirm_commit(request['client_id'])
assert saved['status']=='SAVED', saved
after=read_state()
assert after['entity_registry']['entities'][COMMANDER_ID]['canonical_name']=='指挥官'
assert COMMANDER_ID in after['engine_runtime']['living_world_v1']['player_characters']
assert after['game_time']==before['game_time']
assert len([a for a in host.choices()['actors'] if a['id']==COMMANDER_ID])==1
request['client_id']='WEB-commandersetup2'
begun=host.begin(request)
accepted=host.accept_plan(request['client_id'],plan,{})
assert [a['type'] for a in accepted['job']['payload']['actions']]==['life_control'], 'Never register the same identity twice'
print('PASS: commander listed first, exact identity reviewed, confirmation required, real engine registration/control, no time advance, no duplicate registration')
`);
} catch(e) { console.error(String(e.message).slice(-6000));process.exitCode=1; }
