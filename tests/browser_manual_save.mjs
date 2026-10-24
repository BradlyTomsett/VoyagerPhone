import assert from 'node:assert/strict';
import {BrowserGame} from '../browser/client.js';

function deferred(){let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}
function fixture(failAt){
 const calls=[],game=new BrowserGame(()=>{},()=>{});
 game.saved={savedAt:1};
 game.rpc=async method=>{calls.push(method);if(method===failAt)throw Error('synthetic failure');return new Uint8Array([4,2]);};
 game.store={write:async bytes=>{calls.push('write');assert.deepEqual([...bytes],[4,2]);if(failAt==='write')throw Error('quota');return {savedAt:123};}};
 return {game,calls};
}
{
 const {game,calls}=fixture(),gate=deferred();
 let resolved=false;
 game.store.write=async()=>{calls.push('write');await gate.promise;return {savedAt:456};};
 const result=game.save().then(value=>{resolved=true;return value;});
 await new Promise(setImmediate);
 assert.deepEqual(calls,['snapshot','write']);assert.equal(resolved,false);assert.equal(game.saved.savedAt,1);
 gate.resolve();assert.deepEqual(await result,{savedAt:456,reloadRequired:false});
 assert.deepEqual(calls,['snapshot','write','ack']);assert.equal(game.saved.savedAt,456);
}
{
 const {game,calls}=fixture(),gate=deferred();
 const mutation=game.mutate(async()=>{calls.push('confirm-start');await gate.promise;calls.push('confirm-finish');});
 const saved=game.save();await new Promise(setImmediate);
 assert.deepEqual(calls,['confirm-start']);gate.resolve();await mutation;await saved;
 assert.deepEqual(calls,['confirm-start','confirm-finish','snapshot','write','ack']);
}
for(const failAt of ['snapshot','write','ack']){
 const {game,calls}=fixture(failAt);
 await assert.rejects(game.save(),/STORAGE_WRITE_FAILED/);assert.equal(game.frozen,true);
 assert.equal(game.saved.savedAt,1,'A failed save must not report a new successful save time');
 const count=calls.length;await assert.rejects(game.mutate(()=>calls.push('unsafe-mutation')),/STORAGE_WRITE_FAILED/);assert.equal(calls.length,count);
 game.rpc=async method=>{calls.push(method);return new Uint8Array([4,2]);};
 game.store.write=async()=>({savedAt:789});
 assert.deepEqual(await game.save(),{savedAt:789,reloadRequired:true});assert.equal(game.frozen,false);
 // A failed write can interrupt an approved commit or generation. Reload the
 // durable journal before permitting new mutations, so no job is stranded.
 await assert.rejects(game.mutate(()=>calls.push('unsafe-mutation')),/STORAGE_RELOAD_REQUIRED/);
}
console.log('PASS manual save: durable completion, queue ordering, no draft submission, failure reporting and persistence retry');
