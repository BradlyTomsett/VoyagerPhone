// Real native setup rejection and old browser-journal migration; no model calls.
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {loadPyodide} from '../docs/vendor/pyodide/pyodide.mjs';
try{
 const py=await loadPyodide({indexURL:fileURLToPath(new URL('../docs/vendor/pyodide/',import.meta.url))});
 await py.loadPackage(['sqlite3','lzma']);
 py.unpackArchive(new Uint8Array(fs.readFileSync('docs/engine-bundle.zip')),'zip',{extractDir:'/app'});
 py.runPython(`import sys,json,hashlib,shutil
sys.path.insert(0,'/app')
from pathlib import Path
from browser.runtime_host import BrowserHost,restore_snapshot
from backend.engine import digest
from backend.model import CRITERIA
host=BrowserHost()
root=host.game.bridge.root
before={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['manifest.json','state.json','tasks.json','events.jsonl']}
base=host.game.bridge.identity()
actor='PER-HAWK-MALEN-01'
request={'client_id':'WEB-synthetic-preflight','mode':'action','intent':'SYNTHETIC scene check','actor_id':actor,'scene_id':None}
packet=host.begin(request)
assert packet['packet']['native_schema']['existing_entities']
bad={'actions':[{'type':'scene_open','scene_id':'SCENE-SYNTHETIC-INVALID','task_id':None,'family':'conversation','title':'SYNTHETIC invalid scene','location_ref':'LOC-FREEPORT-XILU9-SEVENDOCK','participants':['PER-SYNTHETIC-MISSING',actor],'presence_mode':'remote','visible_to':['player']}]}
try:host.accept_plan(request['client_id'],{'kind':'setup','message':'SYNTHETIC draft','payload_json':json.dumps(bad),'choices':[]},{})
except ValueError as error:assert str(error)=='SETUP_REFERENCE_UNAVAILABLE',error
else:raise AssertionError('Unknown participant passed setup preflight')
host.fail(request['client_id'],'SETUP_REFERENCE_UNAVAILABLE')
assert host.jobs()[-1]['status']=='FAILED'
# Bypass the new preflight solely to reproduce the native failure produced by old clients.
request['client_id']='WEB-synthetic-legacy-setup'
host.begin(request)
job=host.game.store.get(request['client_id'])
job.update(kind='setup',payload=bad,plan_hash=digest(bad),review={'status':'PASS','criteria':CRITERIA,'reasons':[]},status='AWAITING_CONFIRMATION',
 message='背景清单：仅供测试。\\n\\n**现场开场**\\n货架边传来纸箱摩擦声。霍克停在门口，看见工人把同一只箱子登记了两次。\\n“这箱先放着。”他放低了声音。\\n\\n**提交内容**\\nscene_id=SCENE-SYNTHETIC-INVALID；location_ref=LOC-INVALID。')
host.game.store.save(job)
host.confirm_prepare(job['id'],job['plan_hash'])
result=host.confirm_commit(job['id'])
assert result['status']=='BLOCKED' and result['uncommitted'],result
assert result['error']=='STORY_ENTITY_UNAVAILABLE',result
assert host.game.bridge.identity()==base
assert before=={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in before}
# Persist precisely the old erroneous status and prove that restarting repairs it.
job=host.game.store.get(job['id']);job.update(status='RECOVERY_REQUIRED');job.pop('uncommitted',None);host.game.store.save(job)
snapshot=host.snapshot()
Path('/tmp/legacy-setup-snapshot.zip').write_bytes(snapshot)
host.game.process_lock.close();shutil.rmtree('/voyager');restore_snapshot(snapshot)
host=BrowserHost()
repaired=host.game.store.get(job['id'])
assert repaired['status']=='BLOCKED' and repaired['uncommitted'],repaired
assert host.game.bridge.identity()==base
assert before=={n:hashlib.sha256((host.game.bridge.root/n).read_bytes()).hexdigest() for n in before}
new=host.begin({'client_id':'WEB-synthetic-unblocked','mode':'query','intent':'SYNTHETIC status after repair','actor_id':None,'scene_id':None})
assert new['job']['status']=='GENERATING'
host.fail(new['job']['id'],'SYNTHETIC_TEST_FINISHED')
# A changed save identity cannot prove that an old command did not commit.
repaired.update(status='RECOVERY_REQUIRED',base_identity={**base,'save_set_id':'SYNTHETIC-OTHER-BASE'})
host.game.store.save(repaired)
uncertain=host.snapshot();host.game.process_lock.close();shutil.rmtree('/voyager');restore_snapshot(uncertain)
host=BrowserHost()
assert host.game.store.get(job['id'])['status']=='RECOVERY_REQUIRED'
`);
 fs.writeFileSync('.qa/legacy-setup-snapshot.zip',py.FS.readFile('/tmp/legacy-setup-snapshot.zip'));
 console.log('PASS real WASM: setup reference preflight, native unchanged rejection, exact old-snapshot repair, no world/time changes, new request accepted, uncertain commit retained');
}catch(error){console.error(String(error.message).slice(-8000));process.exitCode=1;}
