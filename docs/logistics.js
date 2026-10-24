// All writes use the serialized, durable BrowserGame transaction adapter.
const names={voyager:'远航者舰队',jinchuan:'金川舰队',shadow:'暗影舰队'};
const node=(tag,text='',className='')=>{const e=document.createElement(tag);e.textContent=text;e.className=className;return e;};
const fmt=n=>Number(n).toLocaleString('zh-CN',{maximumFractionDigits:6});
const messages={TRANSFER_VESSEL_INACTIVE:'这条是非现役历史记录，不能作为现役战舰转隶。',TRANSFER_QUANTITY_PRECISION:'数量最多保留6位小数。',TRANSFER_VALIDATION_FAILED:'原存档校验未通过，这笔调动没有执行；请重新核对记录。',TRANSFER_SAME_LOCATION:'调出方和接收方不能相同。',TRANSFER_QUANTITY_INVALID:'请输入大于零的有效数量。',TRANSFER_INTEGER_REQUIRED:'这类资源须按整数调动。',TRANSFER_INSUFFICIENT_STOCK:'调出方的可用数量不足。',TRANSFER_INSUFFICIENT_PERSONNEL:'所选人员分组的人数不足。',TRANSFER_STALE_PREVIEW:'存档已有变化，请重新核对数量。',TRANSFER_ITEM_NOT_FOUND:'请选择调出的物资。',TRANSFER_WAREHOUSE_INVALID:'请填写不超过50字的仓库名称。',TRANSFER_WAREHOUSE_EXISTS:'这个舰队已有同名仓库。',TRANSFER_RECOVERY_REQUIRED:'这笔调动需要核对恢复，请使用下方的恢复按钮；不会重复调拨。',TRANSFER_PERSONNEL_SOURCE_CONFLICT:'当前人员记录有冲突，无法安全调动，请先核对人员编制。',TRANSFER_STOCK_SOURCE_CONFLICT:'当前库存与批次记录不一致，请先核对存档。',TRANSFER_ID_REUSED:'这笔操作编号已被使用，请重新打开工具。'};
export class LogisticsView{
 constructor(game,error,onSaved){this.game=game;this.error=error;this.onSaved=onSaved;this.dialog=document.querySelector('#logistics');this.form=document.querySelector('#move-form');this.serial=0;this.busy=false;
  document.querySelectorAll('.logistics-open').forEach(b=>b.onclick=()=>this.open());
  this.$('move-close').onclick=()=>this.dialog.close();this.dialog.addEventListener('cancel',e=>{if(this.busy)e.preventDefault();});
  this.form.addEventListener('input',()=>this.clearPreview());
  this.$('move-kind').onchange=()=>this.rebuild();this.$('move-source').onchange=()=>this.contents();this.$('move-filter').oninput=()=>this.rebuildLocations();
  this.$('move-item').onchange=()=>this.showAvailable();this.$('move-cohort').onchange=()=>this.showAvailable();
  this.$('move-all').onclick=()=>{this.$('move-quantity').value=this.available||'';this.clearPreview();};
  this.form.onsubmit=e=>{e.preventDefault();this.preview();};this.$('move-execute').onclick=()=>this.execute();
 }
 $(id){return document.getElementById(id);}
 errorText(e){return messages[e.message]||this.error(e.message);}
 clearPreview(){this.prepared=null;this.$('move-preview').replaceChildren();this.$('move-execute').hidden=true;this.$('move-status').textContent='';}
 setBusy(value){this.busy=value;this.$('move-fields').disabled=value;this.$('move-execute').disabled=value;this.$('move-close').disabled=value;}
 async open(){if(!this.dialog.open)this.dialog.showModal();this.clearPreview();this.$('move-status').textContent='正在读取当前存档…';try{this.catalog=await this.game.rpc('transfer_catalog');this.rebuild();await this.history();}catch(e){this.$('move-status').textContent=this.errorText(e);}}
 options(select,items,value){select.replaceChildren(...items.map(r=>new Option(r.name,r.id)));select.value=items.some(r=>r.id===value)?value:items[0]?.id||'';}
 rebuild(){this.clearPreview();const kind=this.$('move-kind').value;
  this.$('move-warehouse-fields').hidden=kind!=='warehouse';this.$('move-route').hidden=kind==='warehouse';this.$('move-quantity-fields').hidden=!['items','personnel'].includes(kind);
  this.$('move-item-field').hidden=kind!=='items';this.$('move-cohort-field').hidden=kind!=='personnel';this.$('move-vessel-field').hidden=kind!=='vessels';this.$('move-filter-field').hidden=!['items','personnel'].includes(kind);
  this.$('move-check').textContent=kind==='warehouse'?'核对新仓库':'核对调动';this.rebuildLocations();
 }
 rebuildLocations(){++this.serial;if(!this.catalog)return;this.clearPreview();const kind=this.$('move-kind').value,src=this.$('move-source'),dst=this.$('move-destination');
  if(kind==='vessels'){const rows=Object.entries(names).map(([id,name])=>({id,name}));this.options(src,rows,src.value);this.options(dst,rows,dst.value===src.value?'jinchuan':dst.value);this.vessels();return;}
  if(kind==='warehouse')return;
  const filter=this.$('move-filter').value.trim().toLowerCase();const rows=this.catalog.locations.filter(r=>!filter||[r.name,names[r.fleet]].join(' ').toLowerCase().includes(filter)).map(r=>({...r,name:names[r.fleet]+' / '+r.name}));
  this.options(src,rows,src.value);this.options(dst,this.catalog.locations.map(r=>({...r,name:names[r.fleet]+' / '+r.name})),dst.value||'jinchuan:warehouse');this.contents();
 }
 vessels(){const fleet=this.$('move-source').value;this.options(this.$('move-vessel'),this.catalog.vessels.filter(r=>r.fleet===fleet&&r.active).map(r=>({...r,name:r.name+(r.active?'':'（非现役）')})),this.$('move-vessel').value);this.$('move-status').textContent='整舰转隶会携带已登记的随舰人员与物资；当前位置、舰名、性能和历史记录保留。';}
 async contents(){this.clearPreview();if(this.$('move-kind').value==='vessels'){this.vessels();return;}const location=this.$('move-source').value,generation=++this.serial;this.source=null;
  if(!location){this.$('move-status').textContent='没有匹配的调出方，请调整筛选。';return;}
  try{const data=await this.game.rpc('transfer_contents',{location});if(generation!==this.serial)return;this.source=data;
   this.options(this.$('move-item'),data.items.filter(r=>Number(r.quantity)>0).sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')).map(r=>({id:r.id,name:r.name+' · '+fmt(r.quantity)+' '+r.unit})),this.$('move-item').value);
   const groups=new Map();for(const c of data.cohorts)groups.set(String(c.T===null?'None':c.T),(groups.get(String(c.T===null?'None':c.T))||0)+c.quantity);
   this.options(this.$('move-cohort'),[{id:'all',name:'按现有分组顺序调动'},...[...groups].map(([id,n])=>({id,name:(id==='None'||id==='null'?'T未记录':'每人 T='+id)+' · '+fmt(n)+'人'}))],'all');this.showAvailable();
  }catch(e){this.$('move-status').textContent=this.errorText(e);}
 }
 showAvailable(){if(!this.source)return;const kind=this.$('move-kind').value;let text='';
  if(kind==='items'){const row=this.source.items.find(r=>r.id===this.$('move-item').value);this.available=row?.quantity||'0';this.$('move-quantity').step=row?.unit==='kg'?'any':'1';this.$('move-quantity').min=row?.unit==='kg'?'0.000001':'1';text=row?'可调 '+fmt(row.quantity)+' '+row.unit+'。'+row.basis:'这里没有已登记的可调物资。';
   if(row?.batches?.some(b=>Object.keys(b.properties||{}).length))text+=' 批次成色等记录随物资保留。';
  }else{const group=this.$('move-cohort').value;this.available=this.source.cohorts.filter(r=>group==='all'||String(r.T===null?'None':r.T)===group).reduce((n,r)=>n+r.quantity,0);this.$('move-quantity').step='1';this.$('move-quantity').min='1';text='可调 '+fmt(this.available)+' 人。保留每人的原T分组；不会因转隶自动提升战斗力。';}
  this.$('move-available').textContent=text;this.$('move-quantity').max=this.available;
 }
 request(){const kind=this.$('move-kind').value,note=this.$('move-note').value.trim();
  if(kind==='warehouse')return {kind,name:this.$('move-warehouse-name').value.trim(),fleet:this.$('move-warehouse-fleet').value,note};
  const request={kind,source:this.$('move-source').value,destination:this.$('move-destination').value,note};
  if(kind==='vessels')request.vessel=this.$('move-vessel').value;
  else{request.quantity=this.$('move-quantity').value;if(kind==='items')request.item=this.$('move-item').value;else request.personnel_group=this.$('move-cohort').value;}
  return request;
 }
 renderPreview(p){const box=node('div','','move-review');box.append(node('h3',p.description+' · '+fmt(p.quantity)+' '+p.unit));
  const table=node('table');const head=node('tr');for(const t of ['位置','调动前','调动后'])head.append(node('th',t));table.append(head);
  for(const [name,before,after]of [[p.source,p.source_before,p.source_after],[p.destination,p.destination_before,p.destination_after]]){const tr=node('tr');tr.append(node('td',name),node('td',fmt(before)),node('td',fmt(after)));table.append(tr);}box.append(table);
  if(p.carried_personnel!==undefined)box.append(node('p','随舰 '+fmt(p.carried_personnel)+' 人 · '+fmt(p.carried_items)+' 类已登记装备'));
  if(p.cohorts)box.append(node('p',p.cohorts.map(r=>fmt(r.quantity)+'人（'+(r.T===null?'T未记录':'T='+r.T)+'）').join('；')));
  if(p.note)box.append(node('p',p.note));return box;
 }
 async preview(){if(this.busy)return;this.clearPreview();this.setBusy(true);this.$('move-status').textContent='核对当前数量…';try{this.prepared=await this.game.rpc('transfer_preview',this.request());this.$('move-preview').append(this.renderPreview(this.prepared.preview));this.$('move-execute').hidden=false;this.$('move-status').textContent='核对无误后执行。此操作不推进时间，也不调用AI。';}catch(e){this.$('move-status').textContent=this.errorText(e);}finally{this.setBusy(false);}}
 async execute(){if(this.busy||!this.prepared)return;const preview=this.prepared;this.setBusy(true);this.$('move-status').textContent='正在保存这笔调动，请稍候…';try{await this.game.transfer(preview);await this.onSaved();this.prepared=null;this.$('move-execute').hidden=true;this.$('move-preview').replaceChildren(this.renderPreview(preview.preview));this.catalog=await this.game.rpc('transfer_catalog');await this.contents();this.$('move-preview').replaceChildren(this.renderPreview(preview.preview));this.$('move-status').textContent='调动已完成，已保存到此浏览器。';await this.history();}catch(e){this.prepared=null;this.$('move-execute').hidden=true;this.$('move-status').textContent=this.errorText(e);await this.history().catch(()=>{});}finally{this.setBusy(false);}}
 async history(){const data=await this.game.rpc('transfer_history');const box=this.$('move-history');box.replaceChildren();
  for(const pending of data.pending){const card=node('div','','notice');card.append(node('p','待恢复：'+pending.preview.description+'，'+pending.preview.source+' → '+pending.preview.destination));const b=node('button','核对并恢复原调动','secondary');b.onclick=async()=>{if(this.busy)return;this.setBusy(true);try{await this.game.recoverTransfer(pending.id);await this.onSaved();await this.open();}catch(e){this.$('move-status').textContent=this.errorText(e);}finally{this.setBusy(false);}};card.append(b);box.append(card);}
  for(const receipt of data.receipts){const p=receipt.preview,d=node('details','','move-receipt');d.append(node('summary',p.description+' · '+fmt(p.quantity)+p.unit+' · '+p.source+' → '+p.destination));d.append(node('p',receipt.game_time.replace('T',' ')+' · 已保存'),this.renderPreview(p));if(receipt.request.note)d.append(node('p','备注：'+receipt.request.note));box.append(d);}
  if(!data.receipts.length&&!data.pending.length)box.append(node('p','还没有内部调动记录。','empty'));
 }
}
