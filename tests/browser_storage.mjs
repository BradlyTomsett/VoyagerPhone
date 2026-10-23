import assert from 'node:assert/strict';
import {takeLock} from '../browser/storage.js';

// Every URL that opens the same IndexedDB save must contend for the same lock.
const names=[];
Object.defineProperty(globalThis,'navigator',{value:{locks:{request:async(name,options,callback)=>{names.push(name);assert.equal(options.ifAvailable,true);callback({});}}},configurable:true});
globalThis.location={pathname:'/VoyagerPhone/'};
await takeLock();
location.pathname='/VoyagerPhone/index.html';
await takeLock();
assert.equal(names[0],names[1]);
location.pathname='/different-game/';
await takeLock();
assert.notEqual(names[0],names[2]);
navigator.locks.request=async(name,options,callback)=>callback(null);
await assert.rejects(takeLock,/GAME_OPEN_IN_ANOTHER_TAB/);
delete navigator.locks;
await assert.rejects(takeLock,/WEB_LOCKS_REQUIRED/);
console.log('PASS: equivalent save URLs share one lock, other games are isolated, contention is rejected');
