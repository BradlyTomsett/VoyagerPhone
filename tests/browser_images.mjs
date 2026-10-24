import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {equipmentImages} from '../browser/equipment-image-data.js';
import {matchingImages,equipmentLookup,equipmentImageQuery,equipmentSearchText,equipmentImages as allImages} from '../browser/equipment-images.js';
import {uploadedEquipmentImages} from '../browser/equipment-upload-data.js';

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
for(const query of ['堡垒-44','猎隼-40','卫士12','步枪',''])assert.equal(matchingImages(query).length,0,query);
assert.equal(matchingImages('路狐-4').length,2);
assert.equal(matchingImages('余火路狐4')[0].name,'余火 · 路狐-4 配送摩托');
assert.equal(matchingImages('霍克组路狐4').length,1);
assert.equal(matchingImages('路狐4','余火咖啡').length,1);
assert.ok(matchingImages('路狐4','余火咖啡')[0].original.includes('yuhuo_'));
assert.equal(equipmentLookup('余火 · 路狐-4 配送摩托'),'路狐4');
assert.equal(equipmentLookup('霍克组 · 林舟-4 轿车'),'林舟4');
assert.equal(allImages.length,29);
for(const image of uploadedEquipmentImages){for(const folder of ['browser','docs']){const bytes=readFileSync(new URL('../'+folder+'/'+image.original,import.meta.url));assert.equal(createHash('sha256').update(bytes).digest('hex'),image.sha256);assert.ok(readFileSync(new URL('../'+folder+'/'+image.preview,import.meta.url)).length<bytes.length/4);}}
for(const query of ['M1','M-1','M１动力甲','M1型动力甲']){assert.equal(matchingImages(query).length,1,query);assert.equal(matchingImages(query)[0].name,'M1动力甲');}
for(const query of ['M2动力甲','M10动力甲','XM1动力甲','M1A动力甲'])assert.equal(matchingImages(query).length,0,query);
assert.equal(equipmentLookup('M1'),'M1动力甲');
for(const query of ['先锋-5','先锋5','先锋－５动力甲','先锋5型动力甲']){assert.equal(matchingImages(query).length,1,query);assert.equal(matchingImages(query)[0].name,'先锋-5动力甲');}
for(const query of ['先锋-50动力甲'])assert.equal(matchingImages(query).length,0,query);
assert.equal(equipmentLookup('先锋-5动力甲'),'先锋-5');
for(const query of ['先锋-4','先锋4','先锋－４动力甲','先锋4型动力甲']){assert.equal(matchingImages(query).length,1,query);assert.equal(matchingImages(query)[0].name,'先锋-4动力甲');}
assert.equal(matchingImages('先锋-40动力甲').length,0);
assert.equal(equipmentLookup('先锋-4动力甲'),'先锋-4');
assert.notEqual(matchingImages('先锋-4')[0].sha256,matchingImages('先锋-5')[0].sha256);
for(const query of ['先锋-3','先锋3','先锋－３动力甲','先锋3型动力甲']){assert.equal(matchingImages(query).length,1,query);assert.equal(matchingImages(query)[0].name,'先锋-3动力甲');}
assert.equal(matchingImages('先锋-30动力甲').length,0);
assert.equal(equipmentLookup('先锋-3动力甲'),'先锋-3');
assert.notEqual(matchingImages('先锋-3')[0].sha256,matchingImages('先锋-4')[0].sha256);
for(const query of ['先锋-2','先锋2','先锋－２动力甲','先锋2型动力甲']){assert.equal(matchingImages(query).length,1,query);assert.equal(matchingImages(query)[0].name,'先锋-2动力甲');}
assert.equal(matchingImages('先锋-20动力甲').length,0);
assert.equal(equipmentLookup('先锋-2动力甲'),'先锋-2');
assert.notEqual(matchingImages('先锋-2')[0].sha256,matchingImages('先锋-3')[0].sha256);
for(const query of ['自有步枪','自有制式步枪','自有军用步枪']){assert.equal(matchingImages(query).length,1,query);assert.equal(matchingImages(query)[0].name,'自有步枪');}
for(const query of ['外购民用步枪','外部民用步枪','制式步枪','步枪'])assert.equal(matchingImages(query).length,0,query);
assert.equal(equipmentImageQuery('制式步枪','自有公共装备与常设配属'),'自有制式步枪');
assert.equal(equipmentImageQuery('制式步枪','外购装备当前产权'),'制式步枪');
assert.equal(equipmentLookup('自有制式步枪'),'自有步枪');
for(const query of ['外购军用步枪','外购步枪','外部军用步枪','外购军用制式步枪']){assert.equal(matchingImages(query).length,1,query);assert.equal(matchingImages(query)[0].name,'外购军用步枪');}
assert.equal(matchingImages('外购步枪（民用）').length,0);
assert.equal(matchingImages('外购步枪','民用库存').length,0);
assert.equal(equipmentImageQuery('外购步枪','民用库存'),'外购民用步枪');
assert.equal(equipmentLookup('外购步枪'),'外购军用步枪');
assert.ok(equipmentSearchText('外购步枪').includes('外购军用步枪'));
assert.notEqual(matchingImages('外购步枪')[0].sha256,matchingImages('自有步枪')[0].sha256);
for(const query of ['自有手枪','自有制式手枪','自有军用手枪']){assert.equal(matchingImages(query).length,1,query);assert.equal(matchingImages(query)[0].name,'自有手枪');}
for(const query of ['外购民用手枪','外部民用手枪','手枪'])assert.equal(matchingImages(query).length,0,query);
assert.equal(equipmentImageQuery('手枪','自有公共装备与常设配属'),'自有手枪');
assert.equal(equipmentImageQuery('手枪','远航者舰队 · 公共库存 · 当前实物'),'自有手枪');
assert.equal(equipmentImageQuery('外购手枪','远航者舰队 · 公共库存 · 当前实物'),'外购手枪');
assert.equal(equipmentImageQuery('手枪','外购装备当前产权'),'手枪');
assert.equal(equipmentLookup('自有制式手枪'),'自有手枪');
for(const query of ['外购军用手枪','外购手枪','外购手枪物理在仓','外部军用手枪','外购军用制式手枪']){assert.equal(matchingImages(query).length,1,query);assert.equal(matchingImages(query)[0].name,'外购军用手枪');}
assert.equal(matchingImages('外购手枪（民用）').length,0);
assert.equal(matchingImages('外购手枪','民用库存').length,0);
assert.equal(equipmentImageQuery('外购手枪','民用库存'),'外购民用手枪');
assert.equal(equipmentImageQuery('外购手枪物理在仓','民用库存'),'外购民用手枪物理在仓');
assert.equal(equipmentLookup('外购手枪'),'外购军用手枪');
assert.ok(equipmentSearchText('外购手枪物理在仓').includes('外购军用手枪'));
assert.notEqual(matchingImages('外购手枪')[0].sha256,matchingImages('自有手枪')[0].sha256);
console.log('PASS: 20 archived posters and all player-supplied images preserve original hashes; model aliases, number boundaries and owner variants map correctly.');
