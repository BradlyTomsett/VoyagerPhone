import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
const text=path=>readFileSync(new URL('../'+path,import.meta.url),'utf8');
const manifest=JSON.parse(text('docs/asset-manifest.json')),version=manifest.app_version;
const html=text('docs/index.html');
assert(html.includes('./app.js?v='+version));assert(html.includes('./styles.css?v='+version));
assert(!html.includes('voyager-fixture.invalid'),'Test injection must never be published');
assert(!html.includes('id="scene-id"'));assert(html.includes('id="scene-status"'));
for(const name of readdirSync(new URL('../docs/',import.meta.url)).filter(n=>n.endsWith('.js'))){
 const source=text('docs/'+name);
 assert(!/['"]\.\/[A-Za-z0-9_-]+\.js['"]/.test(source),name+' has an unversioned module edge');
}
assert(text('docs/client.js').includes('./worker.js?v='+version));
assert(text('docs/worker.js').includes("fetch('./asset-manifest.json',{cache:'no-store'})"));
assert(text('docs/worker.js').includes('engine-bundle.zip?sha='));
assert(text('docs/client.js').includes("fetch('./model-contract.json',{cache:'no-store'})"));
for(const [path,hash] of Object.entries(manifest.files)){
 assert.equal(createHash('sha256').update(readFileSync(new URL('../docs/'+path,import.meta.url))).digest('hex'),hash,path);
}
console.log('PASS release graph is versioned end-to-end, engine bundle uses verified content identity, cached old modules cannot mask a new HTML release');
