import {loadPyodide} from './vendor/pyodide/pyodide.mjs';
let py, host;
function progress(message){postMessage({progress:message});}
function pythonBytes(expression){const value=py.runPython(expression);try{return new Uint8Array(value.toJs());}finally{value.destroy();}}
function binary(data){py.FS.writeFile('/tmp/browser-input',new Uint8Array(data));}
async function dispatch(method,data){
 if(method==='init'){
  progress('载入浏览器引擎，首次约需下载 20 MB…');
  py=await loadPyodide({indexURL:new URL('./vendor/pyodide/',import.meta.url).href});
  await py.loadPackage(['sqlite3','lzma']);
  const manifest=await (await fetch('./asset-manifest.json')).json();
  const raw=new Uint8Array(await (await fetch('./engine-bundle.zip')).arrayBuffer());
  const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(x=>x.toString(16).padStart(2,'0')).join('');
  if(hash!==manifest.files['engine-bundle.zip'])throw Error('BUNDLE_INTEGRITY_FAILED');
  py.unpackArchive(raw,'zip',{extractDir:'/app'});
  py.runPython("import sys,json,shutil\nsys.path.insert(0,'/app')\nfrom browser.runtime_host import BrowserHost,restore_snapshot,import_save\nfrom pathlib import Path");
  progress('校验原始存档与历史归档…');
  if(data?.snapshot){binary(data.snapshot);py.runPython("restore_snapshot(Path('/tmp/browser-input').read_bytes())");}
  py.runPython('host=BrowserHost()');
  return true;
 }
 if(method==='snapshot')return pythonBytes('host.snapshot()');
 if(method==='export')return pythonBytes('host.export()');
 if(method==='import'){
  binary(data);
  // The caller keeps the last durable snapshot; an import failure reloads it.
  py.runPython("host.game.bridge.host.close()\nhost.game.process_lock.close()\nimport_save(Path('/tmp/browser-input').read_bytes())\nhost=BrowserHost()");
  return true;
 }
 py.globals.set('browser_method',method);py.globals.set('browser_data',JSON.stringify(data??{}));
 return JSON.parse(py.runPython('json.dumps(host.dispatch(browser_method,json.loads(browser_data)),ensure_ascii=False)'));
}
let queue=Promise.resolve();
onmessage=({data:{id,method,data}})=>{queue=queue.then(async()=>{try{const result=await dispatch(method,data);if(result instanceof Uint8Array)postMessage({id,result},[result.buffer]);else postMessage({id,result});}catch(error){const msg=String(error.message||error);const matches=[...msg.matchAll(/(?:ValueError|RuntimeError): ([A-Z][A-Z0-9_]+)/g)];postMessage({id,error:matches.at(-1)?.[1]||'ENGINE_REQUEST_FAILED'});}});};
