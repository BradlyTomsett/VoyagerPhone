import {shipImages as voyagerShipImages} from './ship-image-data.js?v=0.8.23';
import {shadowShipImages} from './shadow-ship-image-data.js?v=0.8.23';
export const shipImages=[...voyagerShipImages,...shadowShipImages];
const byId=new Map(voyagerShipImages.map(image=>[image.id,image]));
const byName=new Map(voyagerShipImages.map(image=>[image.name,image]));
const byVesselId=new Map(shadowShipImages.map(image=>[image.vessel_id,image]));
export const maxShipLength=Math.max(...shipImages.map(image=>image.length));
export function shipImage(ship){
 if(!ship||typeof ship!=='object')return null;
 // Individual hull identity survives transfers and takes precedence over class names.
 const vessel=byVesselId.get(ship.vessel_id||ship.id||ship.entity_id);if(vessel)return vessel;
 const id=ship.class_id||ship.entity_id;
 // An unknown class must never inherit artwork just because its name overlaps.
 return id?byId.get(id)||null:byName.get(ship.class_name||ship.name)||null;
}
export function shipScale(ship){const image=shipImage(ship);return image?image.length/maxShipLength:null;}
function node(tag,cls,text){const element=document.createElement(tag);if(cls)element.className=cls;if(text)element.textContent=text;return element;}
export function shipFigure(ship,{scaled=false,lengthLabel}={}){
 const image=shipImage(ship);if(!image)return null;
 const figure=node('figure','ship-figure'+(scaled?' ship-figure-scaled':''));
 figure.dataset.shipClass=image.id;figure.dataset.shipLength=String(image.length);
 figure.style.setProperty('--ship-factor',String(scaled?shipScale(ship):1));figure.style.setProperty('--ship-frame-height',String(image.frame_height));figure.style.setProperty('--ship-canvas-width',String(image.width));
 const link=node('a','ship-scale-stage');link.href=new URL(image.original,import.meta.url).href;
 link.target='_blank';link.rel='noopener';link.setAttribute('aria-label','查看'+image.name+'高清原图');
 const img=node('img','ship-art-image');img.src=new URL(image.preview,import.meta.url).href;
 img.alt=image.name+'，舰长'+image.length+'米，'+image.features;img.width=image.width;img.height=image.height;
 img.loading='lazy';img.decoding='async';
 const caption=node('figcaption','ship-art-caption'),enlarge=node('a','ship-enlarge','点图放大 ↗');enlarge.href=link.href;enlarge.target='_blank';enlarge.rel='noopener';caption.append(node('strong','',lengthLabel||image.length+' 米'),node('span','',image.role),enlarge);
 img.onerror=()=>{link.hidden=true;caption.append(node('span','','图片暂未载入，可点击查看原图。'));};
 link.append(img);figure.append(link,caption);return figure;
}
export function shipViewTools(list){
 const bar=node('div','ship-view-tools'),group=node('div','ship-view-modes');group.setAttribute('role','group');group.setAttribute('aria-label','舰船图片显示方式');
 const scale=node('button','secondary active','舰长比例'),detail=node('button','secondary','放大细节');
 for(const button of [scale,detail])button.type='button';
 const select=large=>{list.classList.toggle('ship-preview-detailed',large);scale.classList.toggle('active',!large);detail.classList.toggle('active',large);scale.setAttribute('aria-pressed',String(!large));detail.setAttribute('aria-pressed',String(large));};
 scale.onclick=()=>select(false);detail.onclick=()=>select(true);select(false);group.append(scale,detail);
 bar.append(node('p','','舰型外观示意 · 按舰长比较体量，点击图片查看大图。'),group);return bar;
}
