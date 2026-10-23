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
summary=host.dispatch('library_summary',{})
assert summary['history_archives']==22
assert summary['indexed_records']>1000
for name in ['余火','熄炉-9','韩默','伊沃','马洛','雷托']:
 assert host.dispatch('library_search',{'query':name})['total']>0,name
job=host.begin({'client_id':'WEB-source-query123','mode':'query','intent':'余火店多少员工、都是谁、店铺面积，熄炉-9现状，以及韩默、伊沃、马洛、雷托分别是谁？','actor_id':None,'scene_id':None})
packet=job['packet']['context']['source_library']
text=json.dumps(packet,ensure_ascii=False)
for value in ['270','莉娅·莫恩','格伦·萨克','妮卡·维尔','托马·里恩','韩默','伊沃','马洛','雷托','1000']:
 assert value in text,value
assert packet['audience']=='commander_reference_only'
assert packet['bytes']<=30000
after={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in before}
assert before==after,'Browsing and query preparation cannot modify game facts'
history=host.dispatch('library_search',{'query':'灰烬帮','history':True})
assert any(r['source'].startswith('archives/') for r in history['results'])
print('PASS: real browser worker source RPC, original shop/local people/city in model context, read-only world, nested cold archive retrieval')
print('indexed records',summary['indexed_records'],'cold archives',summary['history_archives'])
`);
}catch(e){console.error(String(e.message).slice(-6500));process.exitCode=1;}
