// A real source-backed NPC setup and native commit. No model calls or user saves.
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
from backend.setup_references import source_people
host=BrowserHost();root=host.game.bridge.root
def state():return json.loads((root/'state.json').read_text())
before=state();people=source_people(before)
ids={row['canonical_name']:eid for eid,row in people.items()}
assert len(people)==9
assert all(ids[name] in {r['id'] for r in host.choices()['actors']} for name in ['Q3','托马·里恩','雷托'])
actor=ids['Q3'];sid='SCENE-SYNTHETIC-SOURCE-PEOPLE'
req={'client_id':'WEB-synthetic-source-people','mode':'action','intent':'SYNTHETIC ONLY: establish remote contact scene, no relocation','actor_id':actor,'scene_id':None}
packet=host.begin(req);assert packet['packet']['native_schema']['source_people']
actions=[{'type':'life_control','entity_id':actor,'operation':'take','reason':'SYNTHETIC explicit selection'},
 {'type':'scene_open','scene_id':sid,'task_id':None,'family':'conversation','title':'SYNTHETIC remote contact','location_ref':'七码头','participants':['Q3','托马','霍克'],'presence_mode':'remote','visible_to':['player']},
 {'type':'scene_phase','scene_id':sid,'phase':'open'},{'type':'scene_focus_v2','scene_id':sid}]
plan={'kind':'setup','message':'SYNTHETIC TEST ONLY','payload_json':json.dumps({'actions':actions}),'choices':[]}
accepted=host.accept_plan(req['client_id'],plan,{})
assert {r['name'] for r in accepted['job']['payload']['actions'] if r['type']=='entity_register'}=={'Q3','托马·里恩'}
ready=host.accept_review(req['client_id'],{'status':'PASS','reasons':[]},{})
assert ready['status']=='AWAITING_CONFIRMATION' and state()==before
host.confirm_prepare(req['client_id'],ready['plan_hash']);saved=host.confirm_commit(req['client_id'])
assert saved['status']=='SAVED',saved
after=state();assert after['game_time']==before['game_time']
assert after['world_state_overrides']==before['world_state_overrides']
assert after['entity_registry']['entities'][actor]['canonical_name']=='Q3'
assert after['engine_runtime']['story_turns_v1']['npcs'][actor]['location_ref'] is None
assert actor in after['engine_runtime']['living_world_v1']['player_characters']
assert len([r for r in host.choices()['actors'] if r['name']=='Q3'])==1
assert actor not in source_people(after)
assert len([r for r in host.choices()['places'] if r['name']=='余火咖啡'])==0,'organization is not a scene location'
print('PASS real WASM: known Q3 and shop staff, exact name resolution, reviewed registration, confirmed scene, no time/movement/history mutation or duplicate people')
`);
}catch(error){console.error(String(error.stack||error).slice(-8000));process.exitCode=1;}
