import {equipmentImages as sourceImages} from './equipment-image-data.js';
import {uploadedEquipmentImages} from './equipment-upload-data.js';
export const equipmentImages=[...sourceImages,...uploadedEquipmentImages];

const normal=value=>String(value||'').normalize('NFKC').toLowerCase().replace(/[\s·\-－—_]/g,'');
export function matchingImages(query,context=''){
 const text=normal(equipmentImageQuery(query,context)),owner=normal(query+' '+context),civilian=normal(query).includes('民用')||(context.includes('民用')&&!context.endsWith(' · 当前实物'));
 if(!text)return [];
 const contains=alias=>{const key=normal(alias);let at=text.indexOf(key);while(at>=0){const before=text[at-1]||'',after=text[at+key.length]||'';if(!(/[a-z0-9]/.test(key[0])&&/[a-z0-9]/.test(before))&&(!/\d/.test(key.at(-1))||!/[0-9]/.test(after))&&(!/^[a-z]+\d+$/.test(key)||!/[a-z0-9]/.test(after)))return true;at=text.indexOf(key,at+1);}return false;};
 return equipmentImages.filter(image=>[image.name,...image.aliases].some(contains)).filter(image=>{
  if(image.scope==='external_military'&&civilian&&!text.includes('军用'))return false;
  if(!image.original.includes('roadfox4'))return true;
  if(owner.includes('余火')&&!owner.includes('霍克'))return image.original.includes('yuhuo_');
  if(owner.includes('霍克')&&!owner.includes('余火'))return image.original.includes('hawk_team_');
  return true;
 });
}
export function equipmentSearchText(query){return [query,...matchingImages(query).flatMap(image=>[image.name,...image.aliases])].join(' ').toLocaleLowerCase();}
export function equipmentImageQuery(query,context=''){
 const text=normal(query),marked=text.match(/^(外购|外部|外来|自有)?(步枪|手枪)(物理在仓)?\(民用\)$/);
 if(marked)return (marked[1]||'')+'民用'+marked[2]+(marked[3]||'');
 if(context.includes('民用')&&!context.endsWith(' · 当前实物')){const model=text.match(/^(外购|外部|外来|自有)?(?:制式)?(步枪|手枪)(物理在仓)?$/);if(model)return (model[1]||'')+'民用'+model[2]+(model[3]||'');}
 if(text==='制式步枪'&&context.includes('自有'))return '自有制式步枪';
 // The material ledger retains the self-owned item name 手枪; purchased pistols use 外购手枪.
 if(text==='手枪'&&(context.includes('自有')||context.endsWith(' · 当前实物')))return '自有手枪';
 return query;
}
export function equipmentLookup(query){
 const images=matchingImages(query);if(!images.length)return query;
 // The source search tokenizes hyphens; avoid a bare "-4" matching unrelated models.
 if(images[0].lookup)return images[0].lookup;
 return images[0].aliases.reduce((a,b)=>normal(a).length<=normal(b).length?a:b).replace(/[-－]/g,'');
}
function element(tag,cls,text){const el=document.createElement(tag);if(cls)el.className=cls;if(text)el.textContent=text;return el;}
function figure(image,compact=false){
 const box=element('figure','equipment-figure'+(compact?' equipment-figure-compact':'')),link=element('a','equipment-image-link');
 link.href=new URL(image.original,import.meta.url).href;link.target='_blank';link.rel='noopener';link.setAttribute('aria-label','查看'+image.name+'高清原图');
 const img=element('img');img.src=new URL(image.preview,import.meta.url).href;img.alt=image.name+'装备海报';img.width=image.width;img.height=image.height;img.loading='lazy';img.decoding='async';
 img.onerror=()=>{link.hidden=true;caption.textContent=image.name+' · 查看高清原图';caption.href=new URL(image.original,import.meta.url).href;};
 const caption=element('a','equipment-image-caption',image.name+' · 查看原图 ↗');caption.href=link.href;caption.target='_blank';caption.rel='noopener';link.append(img);box.append(link,caption);return box;
}
export function equipmentFigures(query,{compact=false,context=''}={}){
 const images=matchingImages(query,context);if(!images.length)return null;
 const out=element('div','equipment-illustrations'+(compact?' equipment-illustrations-compact':''));out.append(...images.map(image=>figure(image,compact)));return out;
}
export function equipmentGallery(onSelect){
 const section=element('details','equipment-gallery'),summary=element('summary','','装备图册 · '+equipmentImages.length+' 张原图');section.append(summary);
 let loaded=false;section.ontoggle=()=>{if(!section.open||loaded)return;loaded=true;
  section.append(element('p','source-date','按型号查看图片，点击可打开高清原图。图册不表示持有数量；配属与性能以当前存档为准。'));
  const grid=element('div','equipment-gallery-grid');for(const image of equipmentImages){const card=element('article','equipment-gallery-card');card.append(figure(image,true));const button=element('button','equipment-link','查看'+image.name+'资料 ↗');button.type='button';button.onclick=()=>onSelect(image.name);card.append(button);grid.append(card);}section.append(grid);
 };return section;
}
