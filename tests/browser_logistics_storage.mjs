import assert from 'node:assert/strict';
import {BrowserGame} from '../browser/client.js';
const preview={request:{kind:'items',quantity:'2'},base_save_set_id:'TEST',preview_hash:'hash'};
function fixture(failAt=0){const calls=[];const g=new BrowserGame(()=>{},()=>calls.push('changed'));let n=0;
 g.rpc=async method=>{calls.push(method);if(method==='snapshot')return new Uint8Array([++n]);if(method==='transfer_commit')return {status:'SAVED'};return true;};
 g.store={write:async()=>{calls.push('durable');if(n===failAt)throw Error('quota');return true;}};return {g,calls};
}
{
 const {g,calls}=fixture();await g.transfer(preview,'MOVE-synthetic-001');
 assert.deepEqual(calls,['transfer_prepare','snapshot','durable','ack','transfer_commit','snapshot','durable','ack','changed']);assert.equal(g.frozen,false);
 // There is no model config or API key in this fixture.
}
{
 const {g,calls}=fixture(1);await assert.rejects(g.transfer(preview,'MOVE-synthetic-002'),/STORAGE_WRITE_FAILED/);
 assert.ok(!calls.includes('transfer_commit'));assert.ok(!calls.includes('changed'));assert.equal(g.frozen,true);
}
{
 const {g,calls}=fixture(2);await assert.rejects(g.transfer(preview,'MOVE-synthetic-003'),/STORAGE_WRITE_FAILED/);
 assert.equal(calls.filter(c=>c==='transfer_commit').length,1);assert.ok(!calls.includes('changed'));
 await assert.rejects(g.transfer(preview,'MOVE-synthetic-004'),/STORAGE_WRITE_FAILED/);
 assert.equal(calls.filter(c=>c==='transfer_commit').length,1);
}
console.log('PASS transfer durable-intent ordering, no AI config, quota failure before/after commit, frozen retry protection');
