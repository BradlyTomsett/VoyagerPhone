import {node,label,fmt,visible,recordView,highlights,openEquipment} from './dossier.js';
import {equipmentFigures,equipmentGallery} from './equipment-images.js';
function preview(value){const lines=[];function walk(v,key='',depth=0){if(lines.length>=7||depth>5)return;if(v&&typeof v==='object'){for(const [k,x]of Object.entries(v))walk(x,k,depth+1);}else if(v!==undefined)lines.push((/^\d+$/.test(key)?'':label(key)+'：')+fmt(v));}walk(visible(value));return lines.join('；').slice(0,550);}
export class SourceLibraryView{
 constructor(rpc,error){this.rpc=rpc;this.error=error;this.loaded=false;this.busy=false;this.query='';this.offset=0;this.next=null;this.topicGeneration=0;
  document.querySelector('#library-images').replaceChildren(equipmentGallery(openEquipment));
  document.querySelector('#library-search').onsubmit=e=>{e.preventDefault();this.query=document.querySelector('#library-query').value.trim();this.offset=0;this.search();};
  document.querySelector('#library-next').onclick=()=>{if(this.next!==null){this.offset=this.next;this.search();}};
  document.querySelector('#library-category').onchange=()=>{this.offset=0;this.search();};
  document.querySelector('#library-history').onchange=()=>{this.offset=0;this.search();};
  document.querySelector('#library-topic-close').onclick=()=>{document.querySelector('#library-topic-panel').hidden=true;this.topicGeneration++;};
 }
 invalidate(){this.loaded=false;this.topicGeneration++;document.querySelector('#library-topic-panel').hidden=true;}
 async open(ready){if(!ready){document.querySelector('#library-status').textContent='引擎就绪后可查阅存档资料，无需 API Key。';return;}if(this.loaded||this.busy)return;this.busy=true;
  try{const [summary,topics]=await Promise.all([this.rpc('library_summary'),this.rpc('library_topics')]);document.querySelector('#library-coverage').textContent=`${summary.save_version} · ${summary.indexed_records.toLocaleString('zh-CN')} 条资料片段 · ${summary.history_archives} 份历史归档 · 游戏时间 ${summary.game_time.replace('T',' ')}`;
   document.querySelector('#library-notice').textContent=summary.notice;
   document.querySelector('#library-topics').replaceChildren(...topics.map(topic=>{const b=node('button','topic-button');b.type='button';b.append(node('strong','',topic.title),node('span','',topic.description));b.onclick=()=>this.topic(topic.id);return b;}));
   document.querySelector('#library-featured').replaceChildren(...summary.cards.map(card=>{const n=node('article','source-card'),button=node('button','source-title',card.title);button.onclick=()=>{this.query=card.title;document.querySelector('#library-query').value=this.query;this.offset=0;this.search();};n.append(button,node('p','',card.text));return n;}));this.loaded=true;
  }catch(e){document.querySelector('#library-status').textContent=this.error(e.message);}finally{this.busy=false;}if(this.loaded)await this.search();
 }
 async topic(topic){const generation=++this.topicGeneration,panel=document.querySelector('#library-topic-panel'),body=document.querySelector('#library-topic-body');panel.hidden=false;body.replaceChildren(node('p','empty','正在读取专题…'));panel.scrollIntoView({behavior:'smooth',block:'start'});
  try{const data=await this.rpc('library_topic',{topic});if(generation!==this.topicGeneration)return;document.querySelector('#library-topic-title').textContent=data.title;body.replaceChildren(node('p','notice',data.notice),highlights(data),...data.records.map((r,i)=>recordView(r,topic==='army'&&i===0)).filter(Boolean));}catch(e){if(generation===this.topicGeneration)body.replaceChildren(node('p','error',this.error(e.message)));}
 }
 async search(){if(this.busy){this.pending=true;return;}this.busy=true;const status=document.querySelector('#library-status');status.textContent='正在查阅存档记录…';document.querySelector('#library-next').disabled=true;
  try{this.result=await this.rpc('library_browse',{query:this.query,offset:this.offset,limit:16,history:document.querySelector('#library-history').checked,category:document.querySelector('#library-category').value});this.next=this.result.next_offset;
   const cards=this.result.results.map(record=>{const card=node('article','source-record'),head=node('div','source-record-heading');const title=record.value?.name||record.value?.title||label(record.label);head.append(node('h3','',title),node('span','source-kind',record.kind));card.append(head,node('small','source-date','记录日期：'+record.as_of),node('p','source-excerpt',preview(record.value)));
    const pictures=equipmentFigures(title,{compact:true});if(pictures)card.append(pictures);const detail=recordView({title:'展开详细内容',value:record.value,images:false});if(detail)card.append(detail);return card;});
   document.querySelector('#library-results').replaceChildren(...cards);status.textContent=this.result.total?`找到 ${this.result.total.toLocaleString('zh-CN')} 条，显示第 ${this.result.offset+1}—${Math.min(this.result.offset+16,this.result.total)} 条。`:'未找到匹配记录，可换用人物、地点或勾选历史归档。';document.querySelector('#library-next').hidden=this.next===null;document.querySelector('#library-next').disabled=false;
  }catch(e){status.textContent=this.error(e.message);}finally{this.busy=false;if(this.pending){this.pending=false;this.search();}}
 }
}
