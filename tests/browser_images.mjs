import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {equipmentImages} from '../browser/equipment-image-data.js';
import {matchingImages} from '../browser/equipment-images.js';

const source=JSON.parse(readFileSync(new URL('../seed/development/visual_assets/image_source_index.json',import.meta.url)));
assert.equal(equipmentImages.length,20);
assert.equal(new Set(equipmentImages.map(i=>i.original)).size,20);
for(const image of equipmentImages){
 const name=image.original.split('/').at(-1);
 assert.equal(image.sha256,source.assets[name].sha256);
 for(const folder of ['browser','docs']){
  const original=readFileSync(new URL('../'+folder+'/'+image.original,import.meta.url));
  assert.equal(createHash('sha256').update(original).digest('hex'),image.sha256);
  assert.ok(readFileSync(new URL('../'+folder+'/'+image.preview,import.meta.url)).length<original.length/4);
 }
 assert.ok(matchingImages(image.name).some(i=>i.original===image.original),image.name);
}
for(const [query,file] of [['卫士1型作战机器人','guardian_1'],['彩虹１查打一体无人机','rainbow_1'],['赤原－4全地形装甲车','chiyuan_4'],['沙丘150','dune'],['堡垒6型','fortress_6']]){
 assert.equal(matchingImages(query).length,1,query);assert.ok(matchingImages(query)[0].original.includes(file));
}
for(const query of ['堡垒-44','猎隼-40','卫士12','先锋-4','步枪',''])assert.equal(matchingImages(query).length,0,query);
assert.equal(matchingImages('路狐-4').length,2);
assert.equal(matchingImages('余火路狐4')[0].name,'余火 · 路狐-4 配送摩托');
assert.equal(matchingImages('霍克组路狐4').length,1);
assert.equal(matchingImages('路狐4','余火咖啡').length,1);
assert.ok(matchingImages('路狐4','余火咖啡')[0].original.includes('yuhuo_'));
console.log('PASS: all 20 lossless originals match source checksums and published copies; aliases, numeric model boundaries and owner-specific variants map correctly.');
