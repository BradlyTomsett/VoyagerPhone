// Run with: node tests/browser_wasm.mjs (after build).
// Uses the real pinned WebAssembly runtime and a synthetic native fixture.
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {loadPyodide} from '../docs/vendor/pyodide/pyodide.mjs';
try{
const p=await loadPyodide({indexURL:fileURLToPath(new URL('../docs/vendor/pyodide/',import.meta.url))});
await p.loadPackage(['sqlite3','lzma']);
p.unpackArchive(new Uint8Array(fs.readFileSync('docs/engine-bundle.zip')),'zip',{extractDir:'/app'});
p.runPython("import sys,json,shutil\nsys.path.insert(0,'/app')\nfrom browser.runtime_host import BrowserHost,restore_snapshot,import_save\nfrom pathlib import Path");
// Build the synthetic fixture in WASM, so Windows needs no native fcntl.
p.runPython("import os\nos.chdir('/app')");
p.runPython(fs.readFileSync('tests/prepare_browser_fixture.py','utf8'));
p.unpackArchive(p.FS.readFile('/app/.qa/native-fixture.zip'),'zip',{extractDir:'/voyager'});
p.globals.set('proposal_text',p.FS.readFile('/app/.qa/proposal.json',{encoding:'utf8'}));
p.runPython(`host=BrowserHost()\np=json.loads(proposal_text)\nrequest={'client_id':p['turn_id'],'mode':'action','intent':p['player_intent'],'actor_id':p['actor_id'],'scene_id':p['scene_id']}\ninitial=host.state()['game_time']\nb=host.begin(request)\nassert b['job']['status']=='GENERATING'\nplan={'kind':'turn','message':'SYNTHETIC TEST ONLY','payload_json':json.dumps(p),'choices':[]}\nr=host.accept_plan(p['turn_id'],plan,{})\nassert r['job']['status']=='REVIEWING'\nr=host.accept_review(p['turn_id'],{'status':'PASS','reasons':[]},{})\nassert r['status']=='AWAITING_CONFIRMATION',r\nassert host.state()['game_time']==initial\nplan_hash=r['plan_hash']\nhost.confirm_prepare(p['turn_id'],plan_hash)\nprepared=host.snapshot()\nhost.game.process_lock.close()\nshutil.rmtree('/voyager')\nrestore_snapshot(prepared)\nhost=BrowserHost()\nassert host.jobs()[-1]['status']=='SAVED',host.jobs()\nassert host.state()['game_time']=='8363-12-11T08:00:10',host.state()['game_time']\nhost.confirm_prepare(p['turn_id'],plan_hash)\nhost.confirm_commit(p['turn_id'])\nassert host.state()['game_time']=='8363-12-11T08:00:10'\nfinished=host.snapshot()\nhost.checkpoint_ack()\nhost.game.process_lock.close()\nshutil.rmtree('/voyager')\nrestore_snapshot(finished)\nhost=BrowserHost()\nhost.confirm_prepare(p['turn_id'],plan_hash)\nhost.confirm_commit(p['turn_id'])\nassert host.state()['game_time']=='8363-12-11T08:00:10'\nexported=host.export()\nassert len(exported)>1000000\nimport_save(exported)\nhost=BrowserHost()\nassert host.state()['game_time']=='8363-12-11T08:00:10'\n# A query never changes world time; interrupted generation is not auto-retried.\nq={'client_id':'WEB-query123456','mode':'query','intent':'SYNTHETIC status','actor_id':None,'scene_id':None}\nhost.begin(q)\nhost.accept_plan(q['client_id'],{'kind':'answer','message':'SYNTHETIC','payload_json':'{}','choices':[]},{})\nassert host.state()['game_time']=='8363-12-11T08:00:10'\nq['client_id']='WEB-interrupt123456'\nhost.begin(q)\ncheckpoint=host.snapshot()\nhost.game.process_lock.close()\nshutil.rmtree('/voyager')\nrestore_snapshot(checkpoint)\nhost=BrowserHost()\nassert any(j['status']=='INTERRUPTED' for j in host.jobs())\n`);
console.log('PASS: real WASM validate, confirm, crash recovery, retry once, snapshot reload, export');
console.log('snapshot bytes',p.runPython('len(finished)'));
}catch(e){console.error(String(e.message).slice(-7000));process.exitCode=1;}
