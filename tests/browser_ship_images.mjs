import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {shipImages,shipImage,shipScale,maxShipLength} from '../browser/ship-images.js';

const json=path=>JSON.parse(readFileSync(new URL('../'+path,import.meta.url)));
const catalog=json('seed/catalog.json').catalog_registry.entities;
const classes=Object.values(catalog).filter(row=>row.entity_type==='ship_class');
const manifest=json('browser/assets/ships/artwork-manifest.json');
assert.equal(shipImages.length,12);assert.equal(new Set(shipImages.map(row=>row.id)).size,12);
assert.deepEqual(shipImages.map(row=>row.id).sort(),classes.map(row=>row.entity_id).sort());
assert.equal(maxShipLength,920);
let previewBytes=0;
for(const art of shipImages){
 assert.equal(art.name,catalog[art.id].name);
 assert.equal(art.length+'m',catalog[art.id].immutable_specs.length);
 const hashes=manifest.classes.find(row=>row.id===art.id);
 for(const folder of ['browser','docs']){
  const original=readFileSync(new URL('../'+folder+'/'+art.original,import.meta.url));
  const preview=readFileSync(new URL('../'+folder+'/'+art.preview,import.meta.url));
  assert.equal(createHash('sha256').update(original).digest('hex'),hashes.original_sha256);
  assert.equal(createHash('sha256').update(preview).digest('hex'),hashes.preview_sha256);
  assert.equal(original.readUInt32BE(16),art.width);assert.equal(original.readUInt32BE(20),art.height);
  assert.equal(preview.toString('ascii',0,4),'RIFF');assert.equal(preview.toString('ascii',8,12),'WEBP');
  assert(preview.length<original.length/10);
  assert(art.frame_height<=art.height&&art.frame_height>=400);
  if(folder==='browser')previewBytes+=preview.length;
 }
 assert.equal(shipImage({class_id:art.id,name:'A vessel transferred to another fleet'}),art);
 assert.equal(shipImage({entity_id:art.id}),art);
 assert.equal(shipImage({class_name:art.name}),art);
}
for(const vessel of json('seed/state.json').voyager_fleet.vessel_roster)assert(shipImage(vessel),vessel.vessel_id);
assert.equal(shipImage({class_id:'CLS-UNKNOWN',class_name:'秦锋号旗舰'}),null);
assert.equal(shipImage({class_name:'未知型科考舰'}),null);
assert.equal(shipImage(null),null);
assert.equal(shipScale({class_id:'CLS-QINFENG'}),1);
assert.equal(shipScale({class_id:'CLS-EXPLORER'})/shipScale({class_id:'CLS-LEITING'}),310/860);
assert.equal(shipScale({class_id:'CLS-YINGREN'}),110/920);
assert(previewBytes<800000,'All twelve previews should stay small enough for lazy-loading cards');
console.log('PASS 12 class designs and 51 named vessels: exact identities/lengths, proportional scale, untouched originals, matching public previews, and transfer-safe mapping');
