import {SaveStore,takeLock} from './storage.js';
import {modelCall,validateSettings} from './model.js';
export class BrowserGame{
 constructor(onprogress,onchange){this.onprogress=onprogress;this.onchange=onchange;this.waiting=new Map();this.serial=Promise.resolve();this.next=0;this.frozen=false;}
 rpc(method,data){const id=++this.next;return new Promise((resolve,reject)=>{this.waiting.set(id,{resolve,reject});this.worker.postMessage({id,method,data});});}
 makeWorker(){this.worker=new Worker(new URL('./worker.js',import.meta.url),{type:'module'});this.worker.onmessage=({data})=>{if(data.progress){this.onprogress(data.progress);return;}const p=this.waiting.get(data.id);if(!p)return;this.waiting.delete(data.id);data.error?p.reject(Error(data.error)):p.resolve(data.result);};this.worker.onerror=()=>{for(const p of this.waiting.values())p.reject(Error('WORKER_LOAD_FAILED'));this.waiting.clear();};}
 async init(){await takeLock();this.store=new SaveStore();await this.store.open();this.contract=await (await fetch('./model-contract.json')).json();let rec;try{rec=await this.store.read();}catch(e){this.backupAvailable=!!await this.store.read('previous');throw e;}this.makeWorker();await this.rpc('init',{snapshot:rec?.bytes});await this.checkpoint();navigator.storage?.persist?.().catch(()=>{});return this.rpc('state');}
 async checkpoint(){try{const bytes=await this.rpc('snapshot');this.saved=await this.store.write(bytes);await this.rpc('ack');this.frozen=false;}catch{this.frozen=true;throw Error('STORAGE_WRITE_FAILED');}}
 mutate(fn){const result=this.serial.then(async()=>{if(this.frozen)throw Error('STORAGE_WRITE_FAILED');return fn();});this.serial=result.catch(()=>{});return result;}
 async generation(id,packet,config){try{let p=await modelCall(config,this.contract.generation,packet);const r=await this.mutate(async()=>{const r=await this.rpc('plan',{id,plan:p.result,usage:p.usage});await this.checkpoint();return r;});this.onchange();if(r.review_packet){const v=await modelCall(config,this.contract.review,r.review_packet,true);await this.mutate(async()=>{await this.rpc('review',{id,verdict:v.result,usage:v.usage});await this.checkpoint();});this.onchange();}}catch(e){if(!this.frozen){await this.mutate(async()=>{await this.rpc('fail',{id,code:/^[A-Z0-9_]+$/.test(e.message)?e.message:'MODEL_REQUEST_FAILED'});await this.checkpoint();}).catch(()=>{});}this.onchange();}}
 async api(path,options={}){
  if(path==='/api/state')return this.rpc('state');if(path==='/api/turns'&&!options.method)return this.rpc('jobs');
  if(path==='/api/export')return new Blob([await this.rpc('export')],{type:'application/zip'});
  const data=options.body?JSON.parse(options.body):{};
  if(path==='/api/turns')return this.mutate(async()=>{const c=validateSettings(this.config);let r;try{r=await this.rpc('begin',data);}catch(e){await this.rpc('fail',{id:data.client_id,code:e.message});await this.checkpoint();throw e;}await this.checkpoint();if(r.packet)this.generation(r.job.id,r.packet,{...c});return r.job;});
  const m=path.match(/^\/api\/turns\/([^/]+)\/(confirm|cancel|recover)$/);if(!m)throw Error('BROWSER_METHOD_UNKNOWN');
  return this.mutate(async()=>{const id=m[1];if(m[2]==='cancel'){const r=await this.rpc('cancel',{id});await this.checkpoint();return r;}
   await this.rpc(m[2]==='confirm'?'confirm_prepare':'recover',{id,...data});await this.checkpoint();const r=await this.rpc('confirm_commit',{id});await this.checkpoint();return r;});
 }
 async import(bytes){return this.mutate(async()=>{const original=await this.store.read();try{await this.rpc('import',bytes);await this.checkpoint();}catch(e){this.worker.terminate();this.makeWorker();await this.rpc('init',{snapshot:original.bytes});throw e;}});}
 async restorePrevious(){const previous=await this.store.read('previous');if(!previous)throw Error('NO_PREVIOUS_SAVE');await this.store.write(previous.bytes);location.reload();}
}
