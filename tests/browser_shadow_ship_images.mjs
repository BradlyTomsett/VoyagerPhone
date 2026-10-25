import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {shipImages,shipImage,shipScale,maxShipLength} from '../browser/ship-images.js';
import {shadowShipImages} from '../browser/shadow-ship-image-data.js';

const json=path=>JSON.parse(readFileSync(new URL('../'+path,import.meta.url)));
const vessels=json('seed/state.json').shadow_fleet.vessels;
const manifest=json('browser/assets/ships/shadow/artwork-manifest.json');
assert.equal(manifest.artwork_count,18);assert.equal(manifest.vessel_count,19);
assert.equal(shipImages.length,31);assert.equal(new Set(shipImages.map(row=>row.id)).size,31);
assert.equal(shadowShipImages.length,19);
assert.deepEqual(shadowShipImages.map(row=>row.vessel_id).sort(),Object.keys(vessels).sort());
assert.equal(new Set(shadowShipImages.map(row=>row.original)).size,18);
let previewBytes=0;
for(const art of manifest.artworks){
 for(const folder of ['browser','docs']){
  for(const kind of ['original','preview']){
   const bytes=readFileSync(new URL('../'+folder+'/'+art[kind],import.meta.url));
   assert.equal(createHash('sha256').update(bytes).digest('hex'),art[kind+'_sha256']);
   if(kind==='original'){
    assert.equal(bytes.readUInt32BE(16),art.width);assert.equal(bytes.readUInt32BE(20),art.height);
   }else{assert.equal(bytes.toString('ascii',0,4),'RIFF');assert.equal(bytes.toString('ascii',8,12),'WEBP');}
  }
 }
 const original=readFileSync(new URL('../browser/'+art.original,import.meta.url));
 const preview=readFileSync(new URL('../browser/'+art.preview,import.meta.url));
 assert(preview.length<original.length/10);previewBytes+=preview.length;
 assert(art.frame_height>=400&&art.frame_height<=art.height);
 for(const binding of art.vessels){
  const source=vessels[binding.id],image=shipImage({id:binding.id});
  assert.equal(image.name,source.name);assert.equal(image.length,source.length_m||Number(source.type.match(/(\d+)\s*m/i)[1]));
  assert.equal(image.original,art.original);
  assert.equal(shipImage({vessel_id:binding.id,name:'调动后的舰名',fleet:'voyager'}),image);
  assert.equal(shipImage({entity_id:binding.id}),image);
 }
}
assert.equal(maxShipLength,920);assert(previewBytes<1200000);
assert.equal(shipImage({id:'VES-UNKNOWN',class_name:'中型护航舰'}),null);
assert.equal(shipImage({name:'暗鸦9号'}),null,'Shadow art requires hull identity, not an ambiguous name');
assert.equal(shipImage({class_id:'CLS-UNKNOWN',class_name:'秦锋号旗舰'}),null);
assert.equal(shipImage({id:'VES-UNKNOWN',class_id:'CLS-QINFENG'}).id,'CLS-QINFENG');
assert.equal(shipImage({id:'VES-ANYA11'}).length,294);
assert.equal(shipImage({id:'VES-ANYA12'}).length,289);
assert.equal(shipImage({id:'VES-ANYA11'}).original,shipImage({id:'VES-ANYA12'}).original);
assert.equal(shipScale({id:'VES-PRISON1'}),54/920);
assert.equal(vessels['VES-PRISON1'].active_service,false);
assert(Math.abs(shipScale({id:'VES-ANYA9'})/shipScale({id:'VES-ANYA12'})-624/289)<1e-12);
console.log('PASS 18 Shadow artworks / 19 hulls: exact source lengths, transfer-safe identities, shared escort variants, passive barge, scaled images and matching published bytes');
